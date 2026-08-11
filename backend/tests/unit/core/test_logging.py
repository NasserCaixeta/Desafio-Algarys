import json
from io import StringIO

from clinic_confirmations.core.logging import (
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
)


def test_json_logging_contains_service_context_and_event() -> None:
    stream = StringIO()
    configure_logging(
        service="api",
        level="INFO",
        json_output=True,
        stream=stream,
    )
    bind_context(
        request_id="req-123",
        correlation_id="corr-456",
    )

    get_logger().info("appointment_imported", appointment_id="appt-1")

    payload = json.loads(stream.getvalue())
    assert payload["service"] == "api"
    assert payload["level"] == "info"
    assert payload["event"] == "appointment_imported"
    assert payload["request_id"] == "req-123"
    assert payload["correlation_id"] == "corr-456"
    assert payload["appointment_id"] == "appt-1"
    assert payload["timestamp"].endswith("Z")
    clear_context()
