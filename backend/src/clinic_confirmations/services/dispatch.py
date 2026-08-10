from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from clinic_confirmations.core.config import Settings
from clinic_confirmations.domain.enums import AppointmentStatus
from clinic_confirmations.queue.publisher import TaskPublisher, publish_message
from clinic_confirmations.repositories.appointments import AppointmentRepository
from clinic_confirmations.repositories.messages import MessageRepository
from clinic_confirmations.schemas.confirmations import DispatchResult
from clinic_confirmations.services.queries import utc_day_bounds


def dispatch_for_date(
    session: Session,
    appointment_date: date,
    settings: Settings,
    *,
    correlation_id: str,
    publisher: TaskPublisher | None = None,
) -> DispatchResult:
    start_at, end_at = utc_day_bounds(appointment_date, ZoneInfo(settings.timezone))
    candidates = AppointmentRepository(session).list_dispatch_candidates(
        start_at,
        end_at,
    )
    eligible_ids = [
        appointment_id
        for appointment_id, status in candidates
        if status == AppointmentStatus.PENDING
    ]
    created_ids = MessageRepository(session).create_pending_for_appointments(
        eligible_ids,
        max_attempts=settings.max_message_attempts,
        correlation_id=correlation_id,
        next_enqueue_at=datetime.now(UTC),
    )
    session.commit()

    created = len(created_ids)
    eligible = len(eligible_ids)
    queued = 0
    if publisher is not None:
        queued = sum(
            publish_message(session, message_id, publisher, settings).published
            for message_id in created_ids
        )
    return DispatchResult(
        eligible=eligible,
        created=created,
        already_existing=eligible - created,
        ignored=len(candidates) - eligible,
        queued=queued,
        pending_reconciliation=created - queued,
    )
