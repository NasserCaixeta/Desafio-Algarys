from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from clinic_confirmations.db.models import Appointment, ConfirmationMessage
from clinic_confirmations.domain.enums import AppointmentStatus

APPOINTMENTS_URL = "/api/v1/appointments"


def test_list_filters_by_local_date_and_status(
    client: TestClient,
    appointment_factory: Callable[..., Appointment],
) -> None:
    selected = appointment_factory(
        scheduled_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
        status=AppointmentStatus.PENDING,
    )
    appointment_factory(
        scheduled_at=datetime(2026, 8, 11, 14, tzinfo=UTC),
        status=AppointmentStatus.CONFIRMED,
    )
    appointment_factory(
        scheduled_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        status=AppointmentStatus.PENDING,
    )

    response = client.get(
        APPOINTMENTS_URL,
        params={"date": "2026-08-11", "status": "pending"},
    )

    assert response.status_code == 200
    assert response.json()["pagination"] == {
        "page": 1,
        "page_size": 20,
        "total": 1,
        "total_pages": 1,
    }
    assert [item["id"] for item in response.json()["items"]] == [str(selected.id)]


def test_local_date_uses_clinic_timezone_boundaries(
    client: TestClient,
    appointment_factory: Callable[..., Appointment],
) -> None:
    before = appointment_factory(scheduled_at=datetime(2026, 8, 11, 2, 59, tzinfo=UTC))
    first = appointment_factory(scheduled_at=datetime(2026, 8, 11, 3, tzinfo=UTC))
    last = appointment_factory(scheduled_at=datetime(2026, 8, 12, 2, 59, tzinfo=UTC))
    after = appointment_factory(scheduled_at=datetime(2026, 8, 12, 3, tzinfo=UTC))

    response = client.get(APPOINTMENTS_URL, params={"date": "2026-08-11"})

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [str(first.id), str(last.id)]
    assert str(before.id) not in ids
    assert str(after.id) not in ids


def test_list_is_chronological_and_contains_message_summary(
    client: TestClient,
    appointment_factory: Callable[..., Appointment],
    message_factory: Callable[..., ConfirmationMessage],
) -> None:
    late = appointment_factory(scheduled_at=datetime(2026, 8, 11, 15, tzinfo=UTC))
    early = appointment_factory(scheduled_at=datetime(2026, 8, 11, 12, tzinfo=UTC))
    message = message_factory(
        appointment=early,
        attempt_count=2,
        last_error="Falha simulada",
    )

    response = client.get(APPOINTMENTS_URL, params={"date": "2026-08-11"})

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [str(early.id), str(late.id)]
    assert items[0]["message"] == {
        "id": str(message.id),
        "status": "pending",
        "attempt_count": 2,
        "max_attempts": 3,
        "last_error": "Falha simulada",
    }
    assert items[1]["message"] is None


def test_pagination_returns_stable_page_and_total(
    client: TestClient,
    appointment_factory: Callable[..., Appointment],
) -> None:
    appointments = [
        appointment_factory(scheduled_at=datetime(2026, 8, 11, hour, tzinfo=UTC))
        for hour in (9, 10, 11)
    ]

    response = client.get(
        APPOINTMENTS_URL,
        params={"date": "2026-08-11", "page": 2, "page_size": 2},
    )

    assert response.status_code == 200
    assert response.json()["pagination"] == {
        "page": 2,
        "page_size": 2,
        "total": 3,
        "total_pages": 2,
    }
    assert [item["id"] for item in response.json()["items"]] == [str(appointments[2].id)]


def test_empty_list_has_zero_pages(client: TestClient) -> None:
    response = client.get(APPOINTMENTS_URL, params={"date": "2026-08-11"})

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["pagination"]["total"] == 0
    assert response.json()["pagination"]["total_pages"] == 0


def test_calendar_lists_only_dates_with_appointments_in_clinic_timezone(
    client: TestClient,
    appointment_factory: Callable[..., Appointment],
) -> None:
    appointment_factory(scheduled_at=datetime(2026, 8, 11, 2, 59, tzinfo=UTC))
    appointment_factory(scheduled_at=datetime(2026, 8, 11, 3, tzinfo=UTC))
    appointment_factory(scheduled_at=datetime(2026, 8, 11, 14, tzinfo=UTC))

    response = client.get(f"{APPOINTMENTS_URL}/calendar")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"date": "2026-08-10", "count": 1},
            {"date": "2026-08-11", "count": 2},
        ]
    }


def test_calendar_is_empty_without_appointments(client: TestClient) -> None:
    response = client.get(f"{APPOINTMENTS_URL}/calendar")

    assert response.status_code == 200
    assert response.json() == {"items": []}


@pytest.mark.parametrize("size", [0, 101])
def test_page_size_bounds_return_standardized_422(client: TestClient, size: int) -> None:
    response = client.get(APPOINTMENTS_URL, params={"page_size": size})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"


def test_invalid_status_returns_standardized_422(client: TestClient) -> None:
    response = client.get(APPOINTMENTS_URL, params={"status": "unknown"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"


def test_detail_returns_appointment_with_message(
    client: TestClient,
    appointment_factory: Callable[..., Appointment],
    message_factory: Callable[..., ConfirmationMessage],
) -> None:
    appointment = appointment_factory()
    message_factory(appointment=appointment)

    response = client.get(f"{APPOINTMENTS_URL}/{appointment.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(appointment.id)
    assert response.json()["patient_name"] == "Ana Souza"
    assert response.json()["status"] == "pending"
    assert response.json()["message"]["status"] == "pending"


def test_unknown_detail_returns_standardized_404(client: TestClient) -> None:
    response = client.get(
        f"{APPOINTMENTS_URL}/{uuid4()}",
        headers={"X-Request-ID": "req-not-found"},
    )

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "appointment_not_found",
        "message": "Agendamento não encontrado.",
        "details": {},
        "request_id": "req-not-found",
    }
