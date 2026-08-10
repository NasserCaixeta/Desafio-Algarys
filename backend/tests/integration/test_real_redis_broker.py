from uuid import uuid4

from redis import Redis

from clinic_confirmations.core.config import Settings
from clinic_confirmations.queue.celery_app import create_celery_app


def test_celery_places_json_task_on_real_redis_broker(
    test_settings: Settings,
) -> None:
    queue_name = f"confirmations-test-{uuid4().hex}"
    settings = test_settings.model_copy(
        update={
            "redis_url": "redis://localhost:6380/15",
            "celery_queue": queue_name,
        }
    )
    redis_client = Redis.from_url(settings.redis_url)
    celery_app = create_celery_app(settings)
    redis_client.delete(queue_name)

    try:
        celery_app.send_task(
            "clinic.process_message",
            kwargs={"message_id": str(uuid4()), "correlation_id": uuid4().hex},
            queue=queue_name,
        )

        assert redis_client.llen(queue_name) == 1
    finally:
        redis_client.delete(queue_name)
        celery_app.close()
        redis_client.close()
