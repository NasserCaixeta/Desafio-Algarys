from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Barrier
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from clinic_confirmations.core.config import Settings
from clinic_confirmations.db.models import Appointment, ConfirmationMessage
from clinic_confirmations.db.session import create_session_factory
from clinic_confirmations.schemas.confirmations import DispatchResult
from clinic_confirmations.services.dispatch import dispatch_for_date


def test_simultaneous_dispatch_creates_one_message_per_appointment(
    database_engine: Engine,
    test_settings: Settings,
) -> None:
    session_factory = create_session_factory(database_engine)
    appointment_ids = _create_committed_appointments(session_factory)
    barrier = Barrier(2)

    def run_dispatch() -> DispatchResult:
        with session_factory() as session:
            barrier.wait()
            return dispatch_for_date(
                session,
                date(2026, 8, 11),
                test_settings,
                correlation_id=uuid4().hex,
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: run_dispatch(), range(2)))

        with session_factory() as session:
            message_count = session.scalar(
                select(func.count())
                .select_from(ConfirmationMessage)
                .where(ConfirmationMessage.appointment_id.in_(appointment_ids))
            )
        assert message_count == len(appointment_ids)
        assert sum(result.created for result in results) == len(appointment_ids)
        assert sum(result.already_existing for result in results) == len(appointment_ids)
    finally:
        _delete_committed_appointments(session_factory, appointment_ids)


def _create_committed_appointments(
    session_factory: sessionmaker[Session],
) -> list[UUID]:
    with session_factory() as session:
        appointments = [
            Appointment(
                scheduled_at=datetime(2026, 8, 11, hour, tzinfo=UTC),
                patient_name=f"Paciente {hour}",
                phone=f"+553499999{hour:02d}",
                procedure="Consulta",
                import_fingerprint=uuid4().hex,
            )
            for hour in (12, 13, 14)
        ]
        session.add_all(appointments)
        session.commit()
        return [appointment.id for appointment in appointments]


def _delete_committed_appointments(
    session_factory: sessionmaker[Session],
    appointment_ids: list[UUID],
) -> None:
    with session_factory() as session:
        session.execute(delete(Appointment).where(Appointment.id.in_(appointment_ids)))
        session.commit()
