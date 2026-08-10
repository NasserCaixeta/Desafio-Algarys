import json
from importlib import import_module
from importlib.util import find_spec
from io import StringIO


def load_logging_module():  # type: ignore[no-untyped-def]
    core_spec = find_spec("clinic_confirmations.core")
    assert core_spec is not None, "core package must exist"
    spec = find_spec("clinic_confirmations.core.logging")
    assert spec is not None, "core.logging module must exist"
    return import_module("clinic_confirmations.core.logging")


def test_json_logging_contains_service_context_and_event() -> None:
    logging_module = load_logging_module()
    stream = StringIO()
    logging_module.configure_logging(
        service="api",
        level="INFO",
        json_output=True,
        stream=stream,
    )
    logging_module.bind_context(
        request_id="req-123",
        correlation_id="corr-456",
    )

    logging_module.get_logger().info("appointment_imported", appointment_id="appt-1")

    payload = json.loads(stream.getvalue())
    assert payload["service"] == "api"
    assert payload["level"] == "info"
    assert payload["event"] == "appointment_imported"
    assert payload["request_id"] == "req-123"
    assert payload["correlation_id"] == "corr-456"
    assert payload["appointment_id"] == "appt-1"
    assert payload["timestamp"].endswith("Z")
    logging_module.clear_context()
