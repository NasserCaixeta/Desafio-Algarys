from collections.abc import Callable
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from clinic_confirmations.db.models import Appointment, ConfirmationMessage
from clinic_confirmations.domain.enums import AppointmentStatus

DISPATCH_URL = "/api/v1/confirmations/dispatch"


def test_repeated_dispatch_does_not_duplicate_messages(
    client: TestClient,
    db_session: Session,
    appointment_factory: Callable[..., Appointment],
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
        "queued": 0,
        "pending_reconciliation": 2,
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
    assert all(message.next_enqueue_at is not None for message in messages)


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
