from collections.abc import Mapping

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from clinic_confirmations.core.config import Settings
from clinic_confirmations.db.models import Appointment

IMPORT_URL = "/api/v1/imports/appointments"
HEADER = b"data_hora,paciente,telefone,procedimento\n"


def csv_bytes(*rows: bytes) -> bytes:
    return HEADER + b"\n".join(rows) + b"\n"


def csv_file(content: bytes) -> Mapping[str, tuple[str, bytes, str]]:
    return {"file": ("agenda.csv", content, "text/csv")}


def test_import_keeps_valid_rows_and_reports_invalid_ones(
    client: TestClient, db_session: Session
) -> None:
    content = csv_bytes(
        b"11/08/2026 09:30,Ana,34999991111,Consulta",
        b"invalid,Beto,123,Retorno",
    )

    response = client.post(IMPORT_URL, files=csv_file(content))

    assert response.status_code == 200
    assert response.json()["summary"] == {
        "total_rows": 2,
        "imported": 1,
        "rejected": 1,
        "duplicates": 0,
    }
    assert response.json()["imported_lines"] == [2]
    assert response.json()["duplicate_lines"] == []
    assert response.json()["appointment_dates"] == ["2026-08-11"]
    assert response.json()["errors"] == [
        {
            "line_number": 3,
            "raw_data": {
                "data_hora": "invalid",
                "paciente": "Beto",
                "telefone": "123",
                "procedimento": "Retorno",
            },
            "reason": "data_hora inválida",
        }
    ]
    stored = db_session.scalars(select(Appointment)).one()
    assert stored.patient_name == "Ana"
    assert stored.phone == "+5534999991111"
    assert stored.scheduled_at.isoformat() == "2026-08-11T12:30:00+00:00"


def test_duplicate_reimport_is_reported(client: TestClient) -> None:
    content = csv_bytes(b"11/08/2026 09:30,Ana,34999991111,Consulta")
    first = client.post(IMPORT_URL, files=csv_file(content))

    response = client.post(IMPORT_URL, files=csv_file(content))

    assert first.json()["summary"]["imported"] == 1
    assert response.status_code == 200
    assert response.json()["summary"] == {
        "total_rows": 1,
        "imported": 0,
        "rejected": 0,
        "duplicates": 1,
    }
    assert response.json()["imported_lines"] == []
    assert response.json()["duplicate_lines"] == [2]


def test_duplicate_rows_in_same_file_are_reported(client: TestClient) -> None:
    row = b"11/08/2026 09:30,Ana,34999991111,Consulta"

    response = client.post(IMPORT_URL, files=csv_file(csv_bytes(row, row)))

    assert response.status_code == 200
    assert response.json()["summary"]["imported"] == 1
    assert response.json()["summary"]["duplicates"] == 1
    assert response.json()["imported_lines"] == [2]
    assert response.json()["duplicate_lines"] == [3]
    assert response.json()["appointment_dates"] == ["2026-08-11"]


def test_import_reports_sorted_unique_valid_appointment_dates(client: TestClient) -> None:
    response = client.post(
        IMPORT_URL,
        files=csv_file(
            csv_bytes(
                b"12/08/2026 09:30,Ana,34999991111,Consulta",
                b"11/08/2026 10:30,Beto,34999992222,Retorno",
                b"12/08/2026 11:30,Carla,34999993333,Avaliacao",
                b"invalid,Dora,123,Retorno",
            )
        ),
    )

    assert response.status_code == 200
    assert response.json()["appointment_dates"] == ["2026-08-11", "2026-08-12"]


def test_missing_header_returns_standardized_422(client: TestClient) -> None:
    response = client.post(
        IMPORT_URL,
        files=csv_file(b"Ana,34999991111\n"),
        headers={"X-Request-ID": "req-header-test"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_csv_header",
            "message": (
                "Cabeçalho CSV inválido. Esperado: data_hora,paciente,telefone,procedimento."
            ),
            "details": {
                "expected": ["data_hora", "paciente", "telefone", "procedimento"],
                "received": ["Ana", "34999991111"],
            },
            "request_id": "req-header-test",
        }
    }


def test_completely_invalid_csv_reports_every_data_row(client: TestClient) -> None:
    content = csv_bytes(b"invalid,Ana,123,", b"invalid,Beto,456,")

    response = client.post(IMPORT_URL, files=csv_file(content))

    assert response.status_code == 200
    assert response.json()["summary"] == {
        "total_rows": 2,
        "imported": 0,
        "rejected": 2,
        "duplicates": 0,
    }
    assert [error["line_number"] for error in response.json()["errors"]] == [2, 3]


def test_oversized_file_returns_standardized_413(
    client: TestClient, test_settings: Settings
) -> None:
    response = client.post(
        IMPORT_URL,
        files=csv_file(b"x" * (test_settings.max_upload_bytes + 1)),
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_too_large"


def test_invalid_utf8_returns_standardized_422(client: TestClient) -> None:
    response = client.post(IMPORT_URL, files=csv_file(b"\xff\xfeinvalid"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_csv_encoding"


def test_missing_multipart_file_uses_standard_error_shape(client: TestClient) -> None:
    response = client.post(IMPORT_URL)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"
    assert response.json()["error"]["details"]
