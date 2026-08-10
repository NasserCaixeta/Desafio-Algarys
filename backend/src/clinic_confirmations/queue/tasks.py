from uuid import UUID

from clinic_confirmations.core.config import get_settings
from clinic_confirmations.db.session import create_database_engine, create_session_factory
from clinic_confirmations.queue.celery_app import celery_app
from clinic_confirmations.queue.publisher import reconcile_enqueue
from clinic_confirmations.sender.simulated import SimulatedSender
from clinic_confirmations.services.message_processing import process_message


def reconcile_enqueue_task() -> int:
    settings = get_settings()
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            return reconcile_enqueue(
                session,
                celery_app,
                settings,
                batch_size=settings.reconciliation_batch_size,
            )
    finally:
        engine.dispose()


def process_message_task(message_id: str, correlation_id: str) -> dict[str, object]:
    settings = get_settings()
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    sender = SimulatedSender(
        settings.failure_suffix_list,
        failure_attempts=settings.simulated_failure_attempts,
        latency_ms=settings.simulated_latency_ms,
    )
    try:
        result = process_message(
            session_factory,
            sender,
            UUID(message_id),
            settings,
        )
        return {
            "claimed": result.claimed,
            "status": result.status.value if result.status is not None else None,
            "attempt_number": result.attempt_number,
            "finalized": result.finalized,
            "correlation_id": correlation_id,
        }
    finally:
        engine.dispose()


celery_app.task(name="clinic.reconcile_enqueue")(reconcile_enqueue_task)
celery_app.task(name="clinic.process_message")(process_message_task)
