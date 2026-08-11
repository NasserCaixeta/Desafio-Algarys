from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from clinic_confirmations.api.dependencies import get_task_publisher
from clinic_confirmations.db.models import Appointment, ConfirmationMessage
from clinic_confirmations.domain.enums import AppointmentStatus

DISPATCH_URL = "/api/v1/confirmations/dispatch"


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


def test_repeated_dispatch_does_not_duplicate_messages(
    client: TestClient,
    db_session: Session,
    appointment_factory: Callable[..., Appointment],
    publisher: RecordingPublisher,
) -> None:
    eligible = [
        appointment_factory(scheduled_at=datetime(2026, 8, 11, hour, tzinfo=UTC))
        for hour in (12, 13)
    ]
    appointment_factory(
        scheduled_at=datetime(2026, 8, 11, 14, tzinfo=UTC),
        status=AppointmentStatus.CONFIRMED,
    )
    appointment_factory(scheduled_at=datetime(2026, 8, 12, 12, tzinfo=UTC))

    first = client.post(
        DISPATCH_URL,
        json={"date": "2026-08-11"},
        headers={"X-Request-ID": "req-dispatch"},
    )
    second = client.post(DISPATCH_URL, json={"date": "2026-08-11"})

    assert first.status_code == 200
    assert first.json() == {
        "eligible": 2,
        "created": 2,
        "already_existing": 0,
        "ignored": 1,
        "queued": 2,
        "pending_reconciliation": 0,
    }
    assert second.status_code == 200
    assert second.json() == {
        "eligible": 2,
        "created": 0,
        "already_existing": 2,
        "ignored": 1,
        "queued": 0,
        "pending_reconciliation": 0,
    }
    messages = db_session.scalars(select(ConfirmationMessage)).all()
    assert {message.appointment_id for message in messages} == {
        appointment.id for appointment in eligible
    }
    assert all(message.correlation_id == "req-dispatch" for message in messages)
    assert all(message.enqueued_at is not None for message in messages)
    assert all(message.next_enqueue_at is None for message in messages)
    assert len(publisher.calls) == 2
    assert all(call["name"] == "clinic.process_message" for call in publisher.calls)
    assert all(call["queue"] == "confirmations" for call in publisher.calls)
    assert all(
        call["kwargs"]["correlation_id"] == "req-dispatch"
        for call in publisher.calls
        if call["kwargs"] is not None
    )


def test_dispatch_uses_local_date_boundaries(
    client: TestClient,
    db_session: Session,
    appointment_factory: Callable[..., Appointment],
) -> None:
    before = appointment_factory(scheduled_at=datetime(2026, 8, 11, 2, 59, tzinfo=UTC))
    first = appointment_factory(scheduled_at=datetime(2026, 8, 11, 3, tzinfo=UTC))
    last = appointment_factory(scheduled_at=datetime(2026, 8, 12, 2, 59, tzinfo=UTC))
    after = appointment_factory(scheduled_at=datetime(2026, 8, 12, 3, tzinfo=UTC))

    response = client.post(DISPATCH_URL, json={"date": "2026-08-11"})

    assert response.status_code == 200
    assert response.json()["created"] == 2
    appointment_ids = set(db_session.scalars(select(ConfirmationMessage.appointment_id)))
    assert appointment_ids == {first.id, last.id}
    assert before.id not in appointment_ids
    assert after.id not in appointment_ids


def test_dispatch_creates_messages_only_for_selected_appointments(
    client: TestClient,
    db_session: Session,
    appointment_factory: Callable[..., Appointment],
) -> None:
    selected = appointment_factory()
    unselected = appointment_factory(scheduled_at=datetime(2026, 8, 11, 13, tzinfo=UTC))

    response = client.post(
        DISPATCH_URL,
        json={"date": "2026-08-11", "appointment_ids": [str(selected.id)]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "eligible": 1,
        "created": 1,
        "already_existing": 0,
        "ignored": 0,
        "queued": 1,
        "pending_reconciliation": 0,
    }
    appointment_ids = set(db_session.scalars(select(ConfirmationMessage.appointment_id)))
    assert appointment_ids == {selected.id}
    assert unselected.id not in appointment_ids


def test_dispatch_selection_ignores_unknown_outside_date_and_ineligible_ids(
    client: TestClient,
    db_session: Session,
    appointment_factory: Callable[..., Appointment],
) -> None:
    eligible = appointment_factory()
    ineligible = appointment_factory(
        scheduled_at=datetime(2026, 8, 11, 13, tzinfo=UTC),
        status=AppointmentStatus.CONFIRMED,
    )
    outside_date = appointment_factory(scheduled_at=datetime(2026, 8, 12, 12, tzinfo=UTC))

    response = client.post(
        DISPATCH_URL,
        json={
            "date": "2026-08-11",
            "appointment_ids": [
                str(eligible.id),
                str(ineligible.id),
                str(outside_date.id),
                str(uuid4()),
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "eligible": 1,
        "created": 1,
        "already_existing": 0,
        "ignored": 3,
        "queued": 1,
        "pending_reconciliation": 0,
    }
    assert set(db_session.scalars(select(ConfirmationMessage.appointment_id))) == {eligible.id}


def test_dispatch_rejects_empty_selection(client: TestClient) -> None:
    response = client.post(
        DISPATCH_URL,
        json={"date": "2026-08-11", "appointment_ids": []},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"


def test_dispatch_empty_date_returns_zero_counts(client: TestClient) -> None:
    response = client.post(DISPATCH_URL, json={"date": "2026-08-11"})

    assert response.status_code == 200
    assert all(value == 0 for value in response.json().values())


def test_dispatch_rejects_invalid_date(client: TestClient) -> None:
    response = client.post(DISPATCH_URL, json={"date": "11/08/2026"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"


def test_dispatch_sets_configured_attempt_limit(
    client: TestClient,
    db_session: Session,
    appointment_factory: Callable[..., Appointment],
) -> None:
    appointment_factory()

    response = client.post(DISPATCH_URL, json={"date": "2026-08-11"})

    assert response.status_code == 200
    assert db_session.scalar(select(func.max(ConfirmationMessage.max_attempts))) == 3


def test_broker_failure_keeps_created_message_for_reconciliation(
    client: TestClient,
    db_session: Session,
    appointment_factory: Callable[..., Appointment],
    publisher: RecordingPublisher,
) -> None:
    appointment_factory()
    publisher.error = ConnectionError("redis unavailable")

    response = client.post(DISPATCH_URL, json={"date": "2026-08-11"})

    assert response.status_code == 200
    assert response.json()["created"] == 1
    assert response.json()["queued"] == 0
    assert response.json()["pending_reconciliation"] == 1
    message = db_session.scalars(select(ConfirmationMessage)).one()
    assert message.enqueued_at is None
    assert message.enqueue_attempts == 1
    assert message.last_enqueue_error == "redis unavailable"
    assert message.next_enqueue_at is not None
