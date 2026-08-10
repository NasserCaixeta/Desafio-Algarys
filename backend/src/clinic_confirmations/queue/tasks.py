from clinic_confirmations.core.config import get_settings
from clinic_confirmations.db.session import create_database_engine, create_session_factory
from clinic_confirmations.queue.celery_app import celery_app
from clinic_confirmations.queue.publisher import reconcile_enqueue


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


celery_app.task(name="clinic.reconcile_enqueue")(reconcile_enqueue_task)
