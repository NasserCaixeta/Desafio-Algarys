from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from clinic_confirmations.core.config import Settings
from clinic_confirmations.db.models import ConfirmationMessage
from clinic_confirmations.domain.enums import MessageStatus


def test_liveness_does_not_probe_dependencies(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*_: object) -> bool:
        raise AssertionError("liveness must not probe dependencies")

    monkeypatch.setattr(
        "clinic_confirmations.services.health.check_postgresql",
        fail_if_called,
    )
    monkeypatch.setattr(
        "clinic_confirmations.services.health.check_redis",
        fail_if_called,
    )

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive", "version": "1.0.0"}


def test_readiness_reports_healthy_real_dependencies(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": {"postgresql": True, "redis": True},
    }


def test_readiness_returns_503_on_dependency_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "clinic_confirmations.services.health.check_redis",
        lambda _: False,
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "dependencies": {"postgresql": True, "redis": False},
    }


def test_status_has_version_dependencies_and_message_counts_without_secrets(
    client: TestClient,
    message_factory: Callable[..., ConfirmationMessage],
    test_settings: Settings,
) -> None:
    message_factory(status=MessageStatus.PENDING)
    message_factory(status=MessageStatus.FAILED, attempt_count=1)

    response = client.get("/status")

    assert response.status_code == 200
    assert response.json()["version"] == "1.0.0"
    assert response.json()["environment"] == "development"
    assert response.json()["dependencies"] == {"postgresql": True, "redis": True}
    assert response.json()["messages"] == {
        "pending": 1,
        "processing": 0,
        "sent": 0,
        "failed": 1,
    }
    payload = response.text
    assert test_settings.database_url not in payload
    assert test_settings.redis_url not in payload


def test_openapi_exposes_versioned_and_operational_routes(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/imports/appointments" in paths
    assert "/api/v1/confirmations/dispatch" in paths
    assert "/health/ready" in paths
    assert client.get("/docs").status_code == 200


def test_cors_preflight_allows_configured_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/appointments",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
