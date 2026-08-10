from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.orm import Session, sessionmaker

from clinic_confirmations.core.config import Settings
from clinic_confirmations.domain.enums import MessageStatus
from clinic_confirmations.domain.transitions import retry_delay_seconds
from clinic_confirmations.repositories.messages import MessageRepository
from clinic_confirmations.sender.base import MessageSender


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    claimed: bool
    status: MessageStatus | None
    attempt_number: int | None = None
    finalized: bool = False


def process_message(
    session_factory: sessionmaker[Session],
    sender: MessageSender,
    message_id: UUID,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> ProcessingResult:
    current_time = now or datetime.now(UTC)
    processing_token = uuid4()
    with session_factory() as session:
        repository = MessageRepository(session)
        claimed = repository.claim_for_processing(
            message_id,
            processing_token=processing_token,
            now=current_time,
        )
        if claimed is None:
            return ProcessingResult(
                claimed=False,
                status=repository.get_status(message_id),
            )

    try:
        sender.send(phone=claimed.phone, attempt_number=claimed.attempt_number)
    except Exception as exc:
        error = str(exc) or type(exc).__name__
        completed_at = current_time if now is not None else datetime.now(UTC)
        retry_at = completed_at + timedelta(
            seconds=retry_delay_seconds(
                attempt=claimed.attempt_number,
                base=settings.retry_backoff_base_seconds,
                maximum=settings.retry_backoff_max_seconds,
            )
        )
        with session_factory() as session:
            finalized = MessageRepository(session).finalize_failure(
                claimed.id,
                claimed.processing_token,
                error=error,
                next_retry_at=retry_at,
                now=completed_at,
            )
        return ProcessingResult(
            claimed=True,
            status=MessageStatus.FAILED if finalized else MessageStatus.PROCESSING,
            attempt_number=claimed.attempt_number,
            finalized=finalized,
        )

    with session_factory() as session:
        finalized = MessageRepository(session).finalize_success(
            claimed.id,
            claimed.processing_token,
            now=current_time if now is not None else datetime.now(UTC),
        )
    return ProcessingResult(
        claimed=True,
        status=MessageStatus.SENT if finalized else MessageStatus.PROCESSING,
        attempt_number=claimed.attempt_number,
        finalized=finalized,
    )
