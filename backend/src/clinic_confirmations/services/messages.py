from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from clinic_confirmations.core.config import Settings
from clinic_confirmations.db.models import ConfirmationMessage
from clinic_confirmations.domain.enums import MessageStatus
from clinic_confirmations.domain.errors import MessageNotFoundError
from clinic_confirmations.queue.publisher import TaskPublisher, publish_message
from clinic_confirmations.repositories.messages import MessageRepository
from clinic_confirmations.schemas.common import Pagination
from clinic_confirmations.schemas.messages import (
    MessageAttemptRead,
    MessageDetail,
    MessageList,
    MessageRead,
    RetryResponse,
)
from clinic_confirmations.services.retry import schedule_manual_retry


def list_messages(
    session: Session,
    *,
    status: MessageStatus | None,
    page: int,
    page_size: int,
) -> MessageList:
    messages, total = MessageRepository(session).list_messages(
        status=status,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return MessageList(
        items=[_to_read(message) for message in messages],
        pagination=Pagination(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


def get_message(session: Session, message_id: UUID) -> MessageDetail:
    message = MessageRepository(session).get_with_attempts(message_id)
    if message is None:
        raise MessageNotFoundError
    return MessageDetail(
        **_to_read(message).model_dump(),
        attempts=[
            MessageAttemptRead(
                id=attempt.id,
                attempt_number=attempt.attempt_number,
                started_at=attempt.started_at,
                completed_at=attempt.completed_at,
                result=attempt.result,
                error=attempt.error,
            )
            for attempt in message.attempts
        ],
    )


def retry_message(
    session: Session,
    message_id: UUID,
    publisher: TaskPublisher,
    settings: Settings,
) -> RetryResponse:
    schedule_manual_retry(session, message_id, now=datetime.now(UTC))
    publication = publish_message(session, message_id, publisher, settings)
    message = MessageRepository(session).get(message_id)
    if message is None:
        raise MessageNotFoundError
    return RetryResponse(
        id=message.id,
        status=message.status,
        attempt_count=message.attempt_count,
        max_attempts=message.max_attempts,
        queued=publication.published,
        pending_reconciliation=not publication.published,
        enqueued_at=message.enqueued_at,
        next_enqueue_at=message.next_enqueue_at,
    )


def _to_read(message: ConfirmationMessage) -> MessageRead:
    return MessageRead(
        id=message.id,
        appointment_id=message.appointment_id,
        status=message.status,
        attempt_count=message.attempt_count,
        max_attempts=message.max_attempts,
        last_error=message.last_error,
        enqueued_at=message.enqueued_at,
        next_enqueue_at=message.next_enqueue_at,
    )
