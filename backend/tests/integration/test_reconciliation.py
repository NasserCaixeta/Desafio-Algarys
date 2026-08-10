from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Lock
from uuid import UUID, uuid4

from sqlalchemy import delete
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from clinic_confirmations.core.config import Settings
from clinic_confirmations.db.models import Appointment, ConfirmationMessage
from clinic_confirmations.db.session import create_session_factory
from clinic_confirmations.queue.publisher import reconcile_enqueue


class CountingPublisher:
    def __init__(self) -> None:
        self.count = 0
        self._lock = Lock()

    def send_task(
        self,
        name: str,
        args: list[object] | None = None,
        kwargs: dict[str, object] | None = None,
        queue: str | None = None,
    ) -> object:
        with self._lock:
            self.count += 1
        return object()


def test_reconciliation_republishes_only_unmarked_due_messages(
    db_session: Session,
    message_factory: Callable[..., ConfirmationMessage],
    test_settings: Settings,
) -> None:
    now = datetime(2026, 8, 11, 12, tzinfo=UTC)
    due = message_factory(next_enqueue_at=now - timedelta(seconds=1))
    future = message_factory(next_enqueue_at=now + timedelta(seconds=1))
    marked = message_factory(
        next_enqueue_at=now - timedelta(seconds=1),
        enqueued_at=now - timedelta(seconds=2),
    )
    publisher = CountingPublisher()

    first_count = reconcile_enqueue(
        db_session,
        publisher,
        test_settings,
        batch_size=10,
        now=now,
    )
    second_count = reconcile_enqueue(
        db_session,
        publisher,
        test_settings,
        batch_size=10,
        now=now,
    )

    assert first_count == 1
    assert second_count == 0
    db_session.refresh(due)
    db_session.refresh(future)
    db_session.refresh(marked)
    assert due.enqueued_at == now
    assert future.enqueued_at is None
    assert marked.enqueued_at is not None
    assert publisher.count == 1


def test_two_reconcilers_publish_a_due_message_only_once(
    database_engine: Engine,
    test_settings: Settings,
) -> None:
    session_factory = create_session_factory(database_engine)
    now = datetime(2026, 8, 11, 12, tzinfo=UTC)
    appointment_id = _create_committed_due_message(session_factory, now)
    publisher = CountingPublisher()
    barrier = Barrier(2)

    def reconcile() -> int:
        with session_factory() as session:
            barrier.wait()
            return reconcile_enqueue(
                session,
                publisher,
                test_settings,
                batch_size=1,
                now=now,
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            counts = list(pool.map(lambda _: reconcile(), range(2)))

        assert sum(counts) == 1
        assert publisher.count == 1
        with session_factory() as session:
            message = session.query(ConfirmationMessage).filter_by(
                appointment_id=appointment_id
            ).one()
            assert message.enqueued_at == now
    finally:
        _delete_appointment(session_factory, appointment_id)


def _create_committed_due_message(
    session_factory: sessionmaker[Session],
    now: datetime,
) -> UUID:
    with session_factory() as session:
        appointment = Appointment(
            scheduled_at=now,
            patient_name="Reconciliação concorrente",
            phone="+5534999998888",
            procedure="Consulta",
            import_fingerprint=uuid4().hex,
        )
        session.add(appointment)
        session.flush()
        session.add(
            ConfirmationMessage(
                appointment_id=appointment.id,
                max_attempts=3,
                correlation_id=uuid4().hex,
                next_enqueue_at=now,
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
