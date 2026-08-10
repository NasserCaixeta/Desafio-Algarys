from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID, uuid4

from sqlalchemy import delete
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from clinic_confirmations.db.models import Appointment, ConfirmationMessage
from clinic_confirmations.db.session import create_session_factory
from clinic_confirmations.domain.enums import AppointmentStatus, MessageStatus
from clinic_confirmations.domain.errors import ResponseConflictError
from clinic_confirmations.services.response import record_patient_response


def test_opposite_simultaneous_responses_have_one_winner_and_one_conflict(
    database_engine: Engine,
) -> None:
    session_factory = create_session_factory(database_engine)
    appointment_id = _create_sent_appointment(session_factory)
    barrier = Barrier(2)

    def answer(status: AppointmentStatus) -> AppointmentStatus | type[Exception]:
        with session_factory() as session:
            barrier.wait()
            try:
                return record_patient_response(session, appointment_id, status).status
            except ResponseConflictError:
                return ResponseConflictError

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(
                pool.map(answer, (AppointmentStatus.CONFIRMED, AppointmentStatus.DECLINED))
            )

        winners = [outcome for outcome in outcomes if outcome is not ResponseConflictError]
        assert len(winners) == 1
        assert outcomes.count(ResponseConflictError) == 1
        with session_factory() as session:
            appointment = session.get(Appointment, appointment_id)
            assert appointment is not None
            assert appointment.status == winners[0]
    finally:
        _delete_appointment(session_factory, appointment_id)


def _create_sent_appointment(session_factory: sessionmaker[Session]) -> UUID:
    with session_factory() as session:
        appointment = Appointment(
            scheduled_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
            patient_name="Resposta concorrente",
            phone="+5534999997777",
            procedure="Consulta",
            import_fingerprint=uuid4().hex,
        )
        session.add(appointment)
        session.flush()
        session.add(
            ConfirmationMessage(
                appointment_id=appointment.id,
                status=MessageStatus.SENT,
                attempt_count=1,
                max_attempts=3,
                correlation_id=uuid4().hex,
            )
        )
        session.commit()
        return appointment.id


def _delete_appointment(
    session_factory: sessionmaker[Session],
    appointment_id: UUID,
) -> None:
    with session_factory() as session:
        session.execute(delete(Appointment).where(Appointment.id == appointment_id))
        session.commit()
