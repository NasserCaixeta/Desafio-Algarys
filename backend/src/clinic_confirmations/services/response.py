from uuid import UUID

from sqlalchemy.orm import Session

from clinic_confirmations.domain.enums import AppointmentStatus, MessageStatus
from clinic_confirmations.domain.errors import (
    AppointmentNotFoundError,
    MessageNotSentError,
    ResponseConflictError,
)
from clinic_confirmations.repositories.appointments import AppointmentRepository
from clinic_confirmations.schemas.messages import PatientResponseResult


def record_patient_response(
    session: Session,
    appointment_id: UUID,
    status: AppointmentStatus,
) -> PatientResponseResult:
    appointment = AppointmentRepository(session).lock_with_message(appointment_id)
    if appointment is None:
        session.commit()
        raise AppointmentNotFoundError
    message = appointment.confirmation_message
    if message is None or message.status != MessageStatus.SENT:
        session.commit()
        raise MessageNotSentError

    if appointment.status == AppointmentStatus.PENDING:
        appointment.status = status
        session.commit()
    elif appointment.status == status:
        session.commit()
    else:
        session.commit()
        raise ResponseConflictError

    return PatientResponseResult(id=appointment.id, status=appointment.status)
