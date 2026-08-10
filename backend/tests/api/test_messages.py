from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from clinic_confirmations.api.dependencies import get_task_publisher
from clinic_confirmations.db.models import ConfirmationMessage, MessageAttempt
from clinic_confirmations.domain.enums import AttemptResult, MessageStatus

MESSAGES_URL = "/api/v1/messages"


class RecordingPublisher:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.error: Exception | None = None

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


@pytest.fixture(autouse=True)
def publisher(client: TestClient) -> RecordingPublisher:
    recording = RecordingPublisher()
    client.app.dependency_overrides[get_task_publisher] = lambda: recording
    return recording


def test_list_messages_filters_status_and_paginates(
    client: TestClient,
    message_factory: Callable[..., ConfirmationMessage],
) -> None:
    failed = message_factory(status=MessageStatus.FAILED, attempt_count=1)
    message_factory(status=MessageStatus.SENT, attempt_count=1)

    response = client.get(MESSAGES_URL, params={"status": "failed"})

    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 1
    assert response.json()["items"][0]["id"] == str(failed.id)
    assert response.json()["items"][0]["status"] == "failed"


def test_message_detail_includes_ordered_attempts(
    client: TestClient,
    db_session: Session,
    message_factory: Callable[..., ConfirmationMessage],
) -> None:
    message = message_factory(status=MessageStatus.FAILED, attempt_count=2)
    for number, result in ((2, AttemptResult.FAILED), (1, AttemptResult.FAILED)):
        db_session.add(
            MessageAttempt(
                message_id=message.id,
                attempt_number=number,
                processing_token=uuid4(),
                completed_at=datetime.now(UTC),
                result=result,
                error=f"failure {number}",
            )
        )
    db_session.flush()

    response = client.get(f"{MESSAGES_URL}/{message.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(message.id)
    assert [attempt["attempt_number"] for attempt in response.json()["attempts"]] == [1, 2]
    assert response.json()["attempts"][0]["result"] == "failed"


def test_manual_retry_reuses_id_and_publishes(
    client: TestClient,
    db_session: Session,
    message_factory: Callable[..., ConfirmationMessage],
    publisher: RecordingPublisher,
) -> None:
    message = message_factory(
        status=MessageStatus.FAILED,
        attempt_count=1,
        last_error="simulated failure",
    )

    response = client.post(f"{MESSAGES_URL}/{message.id}/retry")

    assert response.status_code == 200
    assert response.json()["id"] == str(message.id)
    assert response.json()["status"] == "pending"
    assert response.json()["queued"] is True
    assert response.json()["attempt_count"] == 1
    assert len(publisher.calls) == 1
    db_session.refresh(message)
    assert str(message.id) == response.json()["id"]
    assert message.enqueued_at is not None


def test_manual_retry_broker_failure_remains_reconcilable(
    client: TestClient,
    db_session: Session,
    message_factory: Callable[..., ConfirmationMessage],
    publisher: RecordingPublisher,
) -> None:
    message = message_factory(status=MessageStatus.FAILED, attempt_count=1)
    publisher.error = ConnectionError("redis unavailable")

    response = client.post(f"{MESSAGES_URL}/{message.id}/retry")

    assert response.status_code == 200
    assert response.json()["queued"] is False
    assert response.json()["pending_reconciliation"] is True
    db_session.refresh(message)
    assert message.status == MessageStatus.PENDING
    assert message.enqueued_at is None
    assert message.last_enqueue_error == "redis unavailable"


def test_retry_limit_returns_conflict(
    client: TestClient,
    message_factory: Callable[..., ConfirmationMessage],
) -> None:
    message = message_factory(
        status=MessageStatus.FAILED,
        attempt_count=3,
        max_attempts=3,
    )

    response = client.post(f"{MESSAGES_URL}/{message.id}/retry")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "retry_limit_reached"


def test_retry_non_failed_message_returns_conflict(
    client: TestClient,
    message_factory: Callable[..., ConfirmationMessage],
) -> None:
    message = message_factory(status=MessageStatus.SENT, attempt_count=1)

    response = client.post(f"{MESSAGES_URL}/{message.id}/retry")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "retry_not_allowed"


@pytest.mark.parametrize("suffix", ["", "/retry"])
def test_unknown_message_returns_404(client: TestClient, suffix: str) -> None:
    response = (
        client.post(f"{MESSAGES_URL}/{uuid4()}{suffix}")
        if suffix
        else client.get(f"{MESSAGES_URL}/{uuid4()}")
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "message_not_found"
