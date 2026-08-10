from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from clinic_confirmations.core.config import Settings
from clinic_confirmations.db.models import ConfirmationMessage
from clinic_confirmations.queue.publisher import publish_message


class FakeTaskPublisher:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def send_task(
        self,
        name: str,
        args: list[object] | None = None,
        kwargs: dict[str, object] | None = None,
        queue: str | None = None,
    ) -> object:
        self.calls.append({"name": name, "args": args, "kwargs": kwargs, "queue": queue})
        if self.error is not None:
            raise self.error
        return object()


def test_publish_success_marks_current_delivery(
    db_session: Session,
    message_factory: Callable[..., ConfirmationMessage],
    test_settings: Settings,
) -> None:
    message = message_factory(next_enqueue_at=datetime.now(UTC) - timedelta(seconds=1))
    publisher = FakeTaskPublisher()

    result = publish_message(db_session, message.id, publisher, test_settings)

    db_session.refresh(message)
    assert result.published is True
    assert result.skipped is False
    assert message.enqueued_at is not None
    assert message.next_enqueue_at is None
    assert message.last_enqueue_error is None
    assert publisher.calls == [
        {
            "name": "clinic.process_message",
            "args": None,
            "kwargs": {
                "message_id": str(message.id),
                "correlation_id": message.correlation_id,
            },
            "queue": "confirmations",
        }
    ]


def test_publish_failure_leaves_message_reconcilable(
    db_session: Session,
    message_factory: Callable[..., ConfirmationMessage],
    test_settings: Settings,
) -> None:
    now = datetime(2026, 8, 11, 12, tzinfo=UTC)
    message = message_factory(next_enqueue_at=now)
    publisher = FakeTaskPublisher(ConnectionError("redis unavailable"))

    result = publish_message(
        db_session,
        message.id,
        publisher,
        test_settings,
        now=now,
    )

    db_session.refresh(message)
    assert result.published is False
    assert result.skipped is False
    assert result.error == "redis unavailable"
    assert message.enqueued_at is None
    assert message.enqueue_attempts == 1
    assert message.last_enqueue_error == "redis unavailable"
    assert message.next_enqueue_at == now + timedelta(seconds=5)


def test_publish_does_not_send_an_already_marked_delivery(
    db_session: Session,
    message_factory: Callable[..., ConfirmationMessage],
    test_settings: Settings,
) -> None:
    message = message_factory(enqueued_at=datetime.now(UTC))
    publisher = FakeTaskPublisher()

    result = publish_message(db_session, message.id, publisher, test_settings)

    assert result.published is False
    assert result.skipped is True
    assert publisher.calls == []


def test_celery_configuration_is_safe_for_duplicate_delivery(
    test_settings: Settings,
) -> None:
    from clinic_confirmations.queue.celery_app import create_celery_app

    app = create_celery_app(test_settings)

    assert app.conf.task_serializer == "json"
    assert app.conf.accept_content == ["json"]
    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost is True
    assert app.conf.worker_prefetch_multiplier == 1
    assert app.conf.broker_transport_options["visibility_timeout"] == 3600
    assert "reconcile-enqueue" in app.conf.beat_schedule
