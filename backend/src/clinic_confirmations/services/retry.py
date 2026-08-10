from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from clinic_confirmations.db.models import ConfirmationMessage
from clinic_confirmations.domain.enums import AttemptResult, MessageStatus
from clinic_confirmations.domain.errors import (
    MessageNotFoundError,
    RetryLimitReachedError,
    RetryNotAllowedError,
)
from clinic_confirmations.repositories.messages import MessageRepository


@dataclass(frozen=True, slots=True)
class ManualRetryResult:
    id: UUID


def schedule_manual_retry(
    session: Session,
    message_id: UUID,
    *,
    now: datetime,
) -> ManualRetryResult:
    message = MessageRepository(session).lock_by_id(message_id)
    if message is None:
        session.rollback()
        raise MessageNotFoundError
    if message.status != MessageStatus.FAILED:
        session.rollback()
        raise RetryNotAllowedError
    if message.attempt_count >= message.max_attempts:
        session.rollback()
        raise RetryLimitReachedError

    _make_pending(message, now)
    session.commit()
    return ManualRetryResult(id=message.id)


def schedule_due_retries(
    session: Session,
    *,
    now: datetime,
    batch_size: int,
) -> int:
    messages = MessageRepository(session).lock_due_failed(
        now=now,
        batch_size=batch_size,
    )
    for message in messages:
        _make_pending(message, now)
    session.commit()
    return len(messages)


def recover_stale_processing(
    session: Session,
    *,
    now: datetime,
    lease_seconds: int,
    batch_size: int,
) -> int:
    repository = MessageRepository(session)
    messages = repository.lock_stale_processing(
        started_before=now - timedelta(seconds=lease_seconds),
        batch_size=batch_size,
    )
    for message in messages:
        token = message.processing_token
        if token is not None:
            attempt = repository.get_processing_attempt(message.id, token)
            if attempt is not None:
                attempt.result = AttemptResult.ABANDONED
                attempt.error = "processing lease expired"
                attempt.completed_at = now

        message.last_error = "processing lease expired"
        message.processing_token = None
        message.processing_started_at = None
        message.enqueued_at = None
        if message.attempt_count < message.max_attempts:
            message.status = MessageStatus.PENDING
            message.next_enqueue_at = now
        else:
            message.status = MessageStatus.FAILED
            message.next_enqueue_at = None

    session.commit()
    return len(messages)


def _make_pending(message: ConfirmationMessage, now: datetime) -> None:
    message.status = MessageStatus.PENDING
    message.enqueued_at = None
    message.next_enqueue_at = now
    message.processing_token = None
    message.processing_started_at = None
