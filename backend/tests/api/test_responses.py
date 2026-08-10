from collections.abc import Callable
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from clinic_confirmations.db.models import Appointment, ConfirmationMessage
from clinic_confirmations.domain.enums import AppointmentStatus, MessageStatus


@pytest.mark.parametrize("answer", ["confirmed", "declined"])
def test_records_patient_answer_after_sent(
    client: TestClient,
    appointment_factory: Callable[..., Appointment],
    message_factory: Callable[..., ConfirmationMessage],
    answer: str,
) -> None:
    appointment = appointment_factory()
    message_factory(appointment=appointment, status=MessageStatus.SENT)

    response = client.post(
        f"/api/v1/appointments/{appointment.id}/response",
        json={"status": answer},
    )

    assert response.status_code == 200
    assert response.json() == {"id": str(appointment.id), "status": answer}


@pytest.mark.parametrize("message_status", ["pending", "processing", "failed"])
def test_response_requires_sent_message(
    client: TestClient,
    appointment_factory: Callable[..., Appointment],
    message_factory: Callable[..., ConfirmationMessage],
    message_status: str,
) -> None:
    appointment = appointment_factory()
    message_factory(appointment=appointment, status=message_status)

    response = client.post(
        f"/api/v1/appointments/{appointment.id}/response",
        json={"status": "confirmed"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "message_not_sent"


def test_response_requires_a_confirmation_message(
    client: TestClient,
    appointment_factory: Callable[..., Appointment],
) -> None:
    appointment = appointment_factory()

    response = client.post(
        f"/api/v1/appointments/{appointment.id}/response",
        json={"status": "confirmed"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "message_not_sent"


def test_same_answer_is_idempotent_but_opposite_conflicts(
    client: TestClient,
    appointment_factory: Callable[..., Appointment],
    message_factory: Callable[..., ConfirmationMessage],
) -> None:
    appointment = appointment_factory(status=AppointmentStatus.CONFIRMED)
    message_factory(appointment=appointment, status=MessageStatus.SENT)

    same = client.post(
        f"/api/v1/appointments/{appointment.id}/response",
        json={"status": "confirmed"},
    )
    opposite = client.post(
        f"/api/v1/appointments/{appointment.id}/response",
        json={"status": "declined"},
    )

    assert same.status_code == 200
    assert same.json()["status"] == "confirmed"
    assert opposite.status_code == 409
    assert opposite.json()["error"]["code"] == "response_conflict"


def test_response_rejects_pending_as_patient_answer(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/appointments/{uuid4()}/response",
        json={"status": "pending"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"


def test_response_for_unknown_appointment_returns_404(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/appointments/{uuid4()}/response",
        json={"status": "confirmed"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "appointment_not_found"
