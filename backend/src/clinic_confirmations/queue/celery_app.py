from celery import Celery

from clinic_confirmations.core.config import Settings, get_settings


def create_celery_app(settings: Settings) -> Celery:
    app = Celery(
        "clinic_confirmations",
        broker=settings.redis_url,
        include=["clinic_confirmations.queue.tasks"],
    )
    app.conf.update(
        task_default_queue=settings.celery_queue,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        enable_utc=True,
        timezone="UTC",
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        worker_redirect_stdouts=False,
        worker_hijack_root_logger=False,
        broker_transport_options={"visibility_timeout": settings.celery_visibility_timeout_seconds},
        beat_schedule={
            "reconcile-enqueue": {
                "task": "clinic.reconcile_enqueue",
                "schedule": settings.reconciliation_interval_seconds,
            }
        },
    )
    return app


celery_app = create_celery_app(get_settings())
