#!/usr/bin/env python3
"""Exercise the main workflow against the containerized application."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_ROOT = os.getenv("SMOKE_API_ROOT", "http://127.0.0.1:3000/api/v1").rstrip("/")
SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "appointments.csv"
APPOINTMENT_DATE = "2030-01-15"
SUCCESS_PATIENT = "Smoke Sucesso"
RETRY_PATIENT = "Smoke Retry"


def request_json(
    method: str,
    path: str,
    *,
    payload: dict[str, object] | None = None,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request_headers = {"Accept": "application/json", **(headers or {})}
    request_body = body
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        request_body = json.dumps(payload).encode()
    request = urllib.request.Request(
        f"{API_ROOT}{path}",
        data=request_body,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode(errors="replace")
        raise AssertionError(f"{method} {path} returned {exc.code}: {error_body}") from exc


def upload_sample() -> dict[str, Any]:
    boundary = "clinic-confirmations-smoke-boundary"
    content = SAMPLE.read_bytes()
    body = b"".join(
        (
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="file"; filename="appointments.csv"\r\n',
            b"Content-Type: text/csv\r\n\r\n",
            content,
            f"\r\n--{boundary}--\r\n".encode(),
        )
    )
    return request_json(
        "POST",
        "/imports/appointments",
        body=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )


def list_smoke_appointments(*, status: str | None = None) -> list[dict[str, Any]]:
    suffix = f"&status={status}" if status else ""
    page = request_json(
        "GET",
        f"/appointments?date={APPOINTMENT_DATE}&page_size=100{suffix}",
    )
    expected_names = {SUCCESS_PATIENT, RETRY_PATIENT}
    return [item for item in page["items"] if item["patient_name"] in expected_names]


def wait_until_sent() -> list[dict[str, Any]]:
    deadline = time.monotonic() + 45
    last_statuses: dict[str, str | None] = {}
    while time.monotonic() < deadline:
        appointments = list_smoke_appointments()
        last_statuses = {
            item["patient_name"]: item["message"]["status"] if item["message"] else None
            for item in appointments
        }
        if len(appointments) == 2 and all(status == "sent" for status in last_statuses.values()):
            return appointments
        time.sleep(1)
    raise AssertionError(f"messages did not reach sent within 45s: {last_statuses}")


def validate_attempt_history(appointments: list[dict[str, Any]]) -> None:
    by_patient = {item["patient_name"]: item for item in appointments}
    success_detail = request_json("GET", f"/messages/{by_patient[SUCCESS_PATIENT]['message']['id']}")
    retry_detail = request_json("GET", f"/messages/{by_patient[RETRY_PATIENT]['message']['id']}")

    assert success_detail["attempt_count"] == 1, success_detail
    assert [attempt["result"] for attempt in success_detail["attempts"]] == ["sent"]
    assert retry_detail["attempt_count"] == 2, retry_detail
    assert [attempt["result"] for attempt in retry_detail["attempts"]] == ["failed", "sent"]


def confirm_success_patient(appointments: list[dict[str, Any]]) -> None:
    appointment = next(
        item for item in appointments if item["patient_name"] == SUCCESS_PATIENT
    )
    if appointment["status"] == "pending":
        result = request_json(
            "POST",
            f"/appointments/{appointment['id']}/response",
            payload={"status": "confirmed"},
        )
        assert result["status"] == "confirmed", result
    elif appointment["status"] != "confirmed":
        raise AssertionError(f"unexpected existing response: {appointment['status']}")

    confirmed = list_smoke_appointments(status="confirmed")
    assert any(item["id"] == appointment["id"] for item in confirmed), confirmed


def main() -> int:
    print(f"[smoke] API: {API_ROOT}")
    report = upload_sample()
    summary = report["summary"]
    assert summary["rejected"] == 0, report
    assert summary["imported"] + summary["duplicates"] == 2, report
    print(f"[smoke] import: {summary}")

    appointments = list_smoke_appointments()
    assert {item["patient_name"] for item in appointments} == {
        SUCCESS_PATIENT,
        RETRY_PATIENT,
    }, appointments
    print("[smoke] appointments listed")

    dispatch = request_json("POST", "/confirmations/dispatch", payload={"date": APPOINTMENT_DATE})
    assert dispatch["eligible"] + dispatch["ignored"] == 2, dispatch
    assert dispatch["created"] + dispatch["already_existing"] == dispatch["eligible"], dispatch
    print(f"[smoke] dispatch: {dispatch}")

    appointments = wait_until_sent()
    validate_attempt_history(appointments)
    print("[smoke] worker and automatic retry verified")

    confirm_success_patient(appointments)
    print("[smoke] patient confirmation verified")
    print("[smoke] PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, ValueError, KeyError) as exc:
        print(f"[smoke] FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
