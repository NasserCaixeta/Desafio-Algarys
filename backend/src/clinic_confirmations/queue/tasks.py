from datetime import UTC, datetime
from uuid import UUID

from clinic_confirmations.core.config import get_settings
from clinic_confirmations.core.logging import (
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
)
from clinic_confirmations.db.session import create_database_engine, create_session_factory
from clinic_confirmations.queue.celery_app import celery_app
from clinic_confirmations.queue.publisher import reconcile_enqueue
from clinic_confirmations.sender.simulated import SimulatedSender
from clinic_confirmations.services.message_processing import process_message
from clinic_confirmations.services.retry import (
    recover_stale_processing,
    schedule_due_retries,
)

settings = get_settings()
configure_logging(
    service="worker",
    level=settings.log_level,
    json_output=settings.log_json,
)
logger = get_logger()


def reconcile_enqueue_task() -> int:
    clear_context()
    logger.info("reconciliation_started")
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            now = datetime.now(UTC)
            recover_stale_processing(
                session,
                now=now,
                lease_seconds=settings.processing_lease_seconds,
                batch_size=settings.reconciliation_batch_size,
            )
            schedule_due_retries(
                session,
                now=now,
                batch_size=settings.reconciliation_batch_size,
            )
            published = reconcile_enqueue(
                session,
                celery_app,
                settings,
                batch_size=settings.reconciliation_batch_size,
            )
            logger.info("reconciliation_completed", published_count=published)
            return published
    except Exception:
        logger.exception("reconciliation_failed")
        raise
    finally:
        engine.dispose()
        clear_context()


def process_message_task(message_id: str, correlation_id: str) -> dict[str, object]:
    clear_context()
    bind_context(correlation_id=correlation_id, message_id=message_id)
    logger.info("message_processing_started")
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
        payload: dict[str, object] = {
            "claimed": result.claimed,
            "status": result.status.value if result.status is not None else None,
            "appointment_id": (
                str(result.appointment_id) if result.appointment_id is not None else None
            ),
            "attempt_number": result.attempt_number,
            "finalized": result.finalized,
            "correlation_id": correlation_id,
        }
        logger.info(
            "message_processing_completed",
            claimed=result.claimed,
            status=payload["status"],
            appointment_id=payload["appointment_id"],
            attempt_number=result.attempt_number,
            finalized=result.finalized,
        )
        return payload
    except Exception:
        logger.exception("message_processing_failed")
        raise
    finally:
        engine.dispose()
        clear_context()


celery_app.task(name="clinic.reconcile_enqueue")(reconcile_enqueue_task)
celery_app.task(name="clinic.process_message")(process_message_task)
