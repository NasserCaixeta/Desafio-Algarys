import re

from fastapi.testclient import TestClient


def test_request_id_is_preserved(client: TestClient) -> None:
    response = client.get(
        "/health/live",
        headers={"X-Request-ID": "req-test-123"},
    )

    assert response.headers["X-Request-ID"] == "req-test-123"


def test_request_id_is_generated_when_absent(client: TestClient) -> None:
    response = client.get("/health/live")

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get(
        "/health/live",
        headers={"X-Request-ID": "invalid request id"},
    )

    assert response.headers["X-Request-ID"] != "invalid request id"
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


def test_request_id_is_returned_on_standardized_error(client: TestClient) -> None:
    response = client.get(
        "/api/v1/appointments",
        params={"page_size": 0},
        headers={"X-Request-ID": "req-error-123"},
    )

    assert response.status_code == 422
    assert response.headers["X-Request-ID"] == "req-error-123"
    assert response.json()["error"]["request_id"] == "req-error-123"
