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


def test_framework_http_error_uses_standard_envelope(client: TestClient) -> None:
    response = client.get(
        "/route-that-does-not-exist",
        headers={"X-Request-ID": "req-not-found-123"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Not Found",
            "details": {},
            "request_id": "req-not-found-123",
        }
    }


def test_unexpected_error_is_standardized_without_leaking_details(
    client: TestClient,
) -> None:
    def fail() -> None:
        raise RuntimeError("sensitive database detail")

    client.app.add_api_route("/_test/unexpected-error", fail)
    with TestClient(client.app, raise_server_exceptions=False) as safe_client:
        response = safe_client.get(
            "/_test/unexpected-error",
            headers={"X-Request-ID": "req-unexpected-123"},
        )

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "req-unexpected-123"
    assert response.json() == {
        "error": {
            "code": "internal_server_error",
            "message": "Não foi possível processar a requisição.",
            "details": {},
            "request_id": "req-unexpected-123",
        }
    }
    assert "sensitive database detail" not in response.text
