from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from clinic_confirmations.db.models import Appointment
from clinic_confirmations.domain.enums import AppointmentStatus
from clinic_confirmations.domain.errors import AppointmentNotFoundError
from clinic_confirmations.repositories.appointments import AppointmentRepository
from clinic_confirmations.schemas.appointments import (
    AppointmentCalendar,
    AppointmentDateSummary,
    AppointmentList,
    AppointmentMessageSummary,
    AppointmentRead,
)
from clinic_confirmations.schemas.common import Pagination


def list_appointments(
    session: Session,
    *,
    timezone: ZoneInfo,
    appointment_date: date | None,
    status: AppointmentStatus | None,
    page: int,
    page_size: int,
) -> AppointmentList:
    start_at, end_at = optional_utc_day_bounds(appointment_date, timezone)
    appointments, total = AppointmentRepository(session).list_with_message(
        start_at=start_at,
        end_at=end_at,
        status=status,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return AppointmentList(
        items=[_to_read(appointment) for appointment in appointments],
        pagination=Pagination(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


def get_appointment(session: Session, appointment_id: UUID) -> AppointmentRead:
    appointment = AppointmentRepository(session).get_with_message(appointment_id)
    if appointment is None:
        raise AppointmentNotFoundError
    return _to_read(appointment)


def list_appointment_dates(session: Session, timezone: ZoneInfo) -> AppointmentCalendar:
    dates = AppointmentRepository(session).list_date_counts(timezone.key)
    return AppointmentCalendar(
        items=[
            AppointmentDateSummary(date=appointment_date, count=count)
            for appointment_date, count in dates
        ]
    )


def optional_utc_day_bounds(
    appointment_date: date | None,
    timezone: ZoneInfo,
) -> tuple[datetime | None, datetime | None]:
    if appointment_date is None:
        return None, None
    return utc_day_bounds(appointment_date, timezone)


def utc_day_bounds(
    appointment_date: date,
    timezone: ZoneInfo,
) -> tuple[datetime, datetime]:
    start_local = datetime.combine(appointment_date, time.min, tzinfo=timezone)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def _to_read(appointment: Appointment) -> AppointmentRead:
    message = appointment.confirmation_message
    message_summary = (
        AppointmentMessageSummary(
            id=message.id,
            status=message.status,
            attempt_count=message.attempt_count,
            max_attempts=message.max_attempts,
            last_error=message.last_error,
        )
        if message is not None
        else None
    )
    return AppointmentRead(
        id=appointment.id,
        scheduled_at=appointment.scheduled_at,
        patient_name=appointment.patient_name,
        phone=appointment.phone,
        procedure=appointment.procedure,
        status=appointment.status,
        message=message_summary,
    )
