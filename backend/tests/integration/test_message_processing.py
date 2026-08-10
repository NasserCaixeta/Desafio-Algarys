from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from clinic_confirmations.core.config import Settings
from clinic_confirmations.db.models import Appointment, ConfirmationMessage, MessageAttempt
from clinic_confirmations.db.session import create_session_factory
from clinic_confirmations.domain.enums import AttemptResult, MessageStatus
from clinic_confirmations.sender.simulated import SimulatedSender
from clinic_confirmations.services.message_processing import ProcessingResult, process_message


def test_success_persists_one_sent_attempt(
    database_engine: Engine,
    test_settings: Settings,
) -> None:
    session_factory = create_session_factory(database_engine)
    appointment_id, message_id = _create_committed_message(
        session_factory,
        phone="+5534999991111",
    )
    sender = SimulatedSender((), failure_attempts=0, latency_ms=0)

    try:
        result = process_message(session_factory, sender, message_id, test_settings)

        assert result.claimed is True
        assert result.status == MessageStatus.SENT
        with session_factory() as session:
            message = session.get(ConfirmationMessage, message_id)
            assert message is not None
            assert message.status == MessageStatus.SENT
            assert message.attempt_count == 1
            attempt = session.scalars(
                select(MessageAttempt).where(MessageAttempt.message_id == message_id)
            ).one()
            assert attempt.attempt_number == 1
            assert attempt.result == AttemptResult.SENT
            assert attempt.completed_at is not None
    finally:
        _delete_committed_appointment(session_factory, appointment_id)


def test_failure_persists_attempt_error_and_retry_time(
    database_engine: Engine,
    test_settings: Settings,
) -> None:
    session_factory = create_session_factory(database_engine)
    appointment_id, message_id = _create_committed_message(
        session_factory,
        phone="+5534999990000",
    )
    sender = SimulatedSender(("0000",), failure_attempts=1, latency_ms=0)

    try:
        result = process_message(session_factory, sender, message_id, test_settings)

        assert result.claimed is True
        assert result.status == MessageStatus.FAILED
        with session_factory() as session:
            message = session.get(ConfirmationMessage, message_id)
            assert message is not None
            assert message.status == MessageStatus.FAILED
            assert message.attempt_count == 1
            assert message.last_error == "simulated failure"
            assert message.enqueued_at is None
            assert message.next_enqueue_at is not None
            attempt = session.scalars(
                select(MessageAttempt).where(MessageAttempt.message_id == message_id)
            ).one()
            assert attempt.result == AttemptResult.FAILED
            assert attempt.error == "simulated failure"
    finally:
        _delete_committed_appointment(session_factory, appointment_id)


def test_duplicate_delivery_creates_one_valid_attempt(
    database_engine: Engine,
    test_settings: Settings,
) -> None:
    session_factory = create_session_factory(database_engine)
    appointment_id, message_id = _create_committed_message(
        session_factory,
        phone="+5534999991111",
    )
    sender = SimulatedSender((), failure_attempts=0, latency_ms=20)
    barrier = Barrier(2)

    def run() -> ProcessingResult:
        barrier.wait()
        return process_message(session_factory, sender, message_id, test_settings)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: run(), range(2)))

        assert sum(result.claimed for result in results) == 1
        with session_factory() as session:
            message = session.get(ConfirmationMessage, message_id)
            assert message is not None
            assert message.status == MessageStatus.SENT
            assert message.attempt_count == 1
            attempt_count = session.scalar(
                select(func.count())
                .select_from(MessageAttempt)
                .where(MessageAttempt.message_id == message_id)
            )
            assert attempt_count == 1
    finally:
        _delete_committed_appointment(session_factory, appointment_id)


def test_task_after_sent_is_noop(
    database_engine: Engine,
    test_settings: Settings,
) -> None:
    session_factory = create_session_factory(database_engine)
    appointment_id, message_id = _create_committed_message(
        session_factory,
        phone="+5534999991111",
        status=MessageStatus.SENT,
        attempt_count=1,
    )
    sender = SimulatedSender((), failure_attempts=0, latency_ms=0)

    try:
        result = process_message(session_factory, sender, message_id, test_settings)

        assert result.claimed is False
        assert result.status == MessageStatus.SENT
        with session_factory() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(MessageAttempt)
                    .where(MessageAttempt.message_id == message_id)
                )
                == 0
            )
    finally:
        _delete_committed_appointment(session_factory, appointment_id)


def _create_committed_message(
    session_factory: sessionmaker[Session],
    *,
    phone: str,
    status: MessageStatus = MessageStatus.PENDING,
    attempt_count: int = 0,
) -> tuple[UUID, UUID]:
    with session_factory() as session:
        appointment = Appointment(
            scheduled_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
            patient_name="Ana Souza",
            phone=phone,
            procedure="Consulta",
            import_fingerprint=uuid4().hex,
        )
        session.add(appointment)
        session.flush()
        message = ConfirmationMessage(
            appointment_id=appointment.id,
            status=status,
            attempt_count=attempt_count,
            max_attempts=3,
            enqueued_at=datetime.now(UTC),
            correlation_id=uuid4().hex,
        )
        session.add(message)
        session.commit()
        return appointment.id, message.id


def _delete_committed_appointment(
    session_factory: sessionmaker[Session],
    appointment_id: UUID,
) -> None:
    with session_factory() as session:
        session.execute(delete(Appointment).where(Appointment.id == appointment_id))
        session.commit()
