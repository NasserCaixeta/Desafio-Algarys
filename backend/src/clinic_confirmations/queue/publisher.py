from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from clinic_confirmations.core.config import Settings
from clinic_confirmations.db.models import ConfirmationMessage
from clinic_confirmations.domain.enums import MessageStatus
from clinic_confirmations.repositories.messages import MessageRepository


class TaskPublisher(Protocol):
    def send_task(
        self,
        name: str,
        args: list[object] | None = None,
        kwargs: dict[str, object] | None = None,
        queue: str | None = None,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class PublicationResult:
    message_id: UUID
    published: bool
    skipped: bool = False
    error: str | None = None


def publish_message(
    session: Session,
    message_id: UUID,
    publisher: TaskPublisher,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> PublicationResult:
    message = session.get(ConfirmationMessage, message_id)
    if message is None:
        return PublicationResult(message_id=message_id, published=False, skipped=True)
    return _publish_loaded_message(
        session,
        message,
        publisher,
        settings,
        now=now or datetime.now(UTC),
    )


def reconcile_enqueue(
    session: Session,
    publisher: TaskPublisher,
    settings: Settings,
    *,
    batch_size: int,
    now: datetime | None = None,
) -> int:
    current_time = now or datetime.now(UTC)
    published_count = 0
    repository = MessageRepository(session)

    for _ in range(batch_size):
        message = repository.lock_next_reconcilable(current_time)
        if message is None:
            break
        result = _publish_loaded_message(
            session,
            message,
            publisher,
            settings,
            now=current_time,
        )
        published_count += int(result.published)

    return published_count


def _publish_loaded_message(
    session: Session,
    message: ConfirmationMessage,
    publisher: TaskPublisher,
    settings: Settings,
    *,
    now: datetime,
) -> PublicationResult:
    if message.status != MessageStatus.PENDING or message.enqueued_at is not None:
        return PublicationResult(message_id=message.id, published=False, skipped=True)

    try:
        publisher.send_task(
            "clinic.process_message",
            kwargs={
                "message_id": str(message.id),
                "correlation_id": message.correlation_id,
            },
            queue=settings.celery_queue,
        )
    except Exception as exc:
        error = str(exc)
        message.enqueue_attempts += 1
        message.last_enqueue_error = error
        message.next_enqueue_at = now + timedelta(
            seconds=_enqueue_backoff_seconds(message.enqueue_attempts, settings)
        )
        session.commit()
        return PublicationResult(
            message_id=message.id,
            published=False,
            error=error,
        )

    message.enqueued_at = now
    message.next_enqueue_at = None
    message.last_enqueue_error = None
    session.commit()
    return PublicationResult(message_id=message.id, published=True)


def _enqueue_backoff_seconds(attempt: int, settings: Settings) -> int:
    exponent = min(max(attempt - 1, 0), 30)
    base_seconds: int = settings.retry_backoff_base_seconds
    maximum_seconds: int = settings.retry_backoff_max_seconds
    return min(
        base_seconds * (1 << exponent),
        maximum_seconds,
    )
