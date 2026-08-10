from datetime import UTC
from zoneinfo import ZoneInfo

import pytest

from clinic_confirmations.domain.errors import (
    InvalidCsvEncodingError,
    InvalidCsvHeaderError,
)
from clinic_confirmations.services.csv_import import (
    normalize_phone,
    parse_csv,
    parse_local_datetime,
)

TIMEZONE = ZoneInfo("America/Sao_Paulo")
HEADER = "data_hora,paciente,telefone,procedimento\n"


def csv_bytes(*rows: str) -> bytes:
    return (HEADER + "\n".join(rows) + "\n").encode()


@pytest.mark.parametrize("raw", ["2026-08-11 09:30", "11/08/2026 09:30"])
def test_parse_supported_dates(raw: str) -> None:
    parsed = parse_local_datetime(raw, TIMEZONE)

    assert parsed.tzinfo is UTC
    assert parsed.isoformat() == "2026-08-11T12:30:00+00:00"


@pytest.mark.parametrize("raw", ["(34) 99999-1111", "+55 34 99999-1111"])
def test_normalize_brazilian_phone(raw: str) -> None:
    assert normalize_phone(raw) == "+5534999991111"


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ("invalid,Ana,34999991111,Consulta", "data_hora inválida"),
        ("11/08/2026 09:30,Ana,123,Consulta", "telefone inválido"),
        ("11/08/2026 09:30,,34999991111,Consulta", "paciente obrigatório"),
        ("11/08/2026 09:30,Ana,34999991111,", "procedimento obrigatório"),
    ],
)
def test_invalid_rows_are_reported_without_aborting_valid_rows(row: str, reason: str) -> None:
    result = parse_csv(
        csv_bytes(row, "11/08/2026 10:30,Bia,34999992222,Retorno"),
        TIMEZONE,
    )

    assert result.total_rows == 2
    assert len(result.valid_rows) == 1
    assert result.errors[0].line_number == 2
    assert result.errors[0].raw_data["data_hora"] == row.split(",")[0]
    assert result.errors[0].reason == reason


def test_blank_row_is_ignored_and_partial_row_is_rejected() -> None:
    result = parse_csv(
        csv_bytes("", "  ,  ,  ,  ", "11/08/2026 09:30,Ana,,Consulta"),
        TIMEZONE,
    )

    assert result.total_rows == 1
    assert result.valid_rows == []
    assert len(result.errors) == 1
    assert result.errors[0].line_number == 4
    assert result.errors[0].reason == "telefone obrigatório"


def test_header_accepts_bom_but_not_wrong_names() -> None:
    result = parse_csv(
        b"\xef\xbb\xbfdata_hora,paciente,telefone,procedimento\n",
        TIMEZONE,
    )

    assert result.total_rows == 0
    with pytest.raises(InvalidCsvHeaderError) as exc_info:
        parse_csv(b"data,nome,fone,servico\n", TIMEZONE)
    assert exc_info.value.received == ("data", "nome", "fone", "servico")


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"\n",
        b"data_hora,paciente,telefone\n",
        b"DATA_HORA,paciente,telefone,procedimento\n",
    ],
)
def test_missing_or_non_official_header_is_rejected(content: bytes) -> None:
    with pytest.raises(InvalidCsvHeaderError):
        parse_csv(content, TIMEZONE)


def test_invalid_utf8_is_rejected_as_a_file_error() -> None:
    with pytest.raises(InvalidCsvEncodingError):
        parse_csv(b"\xff\xfedata_hora,paciente,telefone,procedimento\n", TIMEZONE)


def test_valid_row_is_normalized_and_fingerprinted() -> None:
    first = parse_csv(
        csv_bytes("11/08/2026 09:30,  ANA   Souza  ,(34) 99999-1111, Consulta   inicial "),
        TIMEZONE,
    ).valid_rows[0]
    equivalent = parse_csv(
        csv_bytes("2026-08-11 09:30,ana souza,+55 34 99999-1111,consulta inicial"),
        TIMEZONE,
    ).valid_rows[0]

    assert first.line_number == 2
    assert first.scheduled_at.isoformat() == "2026-08-11T12:30:00+00:00"
    assert first.patient_name == "ANA Souza"
    assert first.phone == "+5534999991111"
    assert first.procedure == "Consulta inicial"
    assert len(first.import_fingerprint) == 64
    assert first.import_fingerprint == equivalent.import_fingerprint


@pytest.mark.parametrize(
    "row",
    [
        "11/08/2026 09:30,Ana,34999991111",
        "11/08/2026 09:30,Ana,34999991111,Consulta,extra",
    ],
)
def test_wrong_column_count_rejects_only_the_row(row: str) -> None:
    result = parse_csv(csv_bytes(row), TIMEZONE)

    assert result.total_rows == 1
    assert result.valid_rows == []
    assert result.errors[0].reason == "quantidade de colunas inválida"


def test_all_invalid_rows_are_returned_in_physical_line_order() -> None:
    result = parse_csv(
        csv_bytes(
            "invalid,Ana,34999991111,Consulta",
            "11/08/2026 09:30,Bia,123,Retorno",
        ),
        TIMEZONE,
    )

    assert result.total_rows == 2
    assert result.valid_rows == []
    assert [error.line_number for error in result.errors] == [2, 3]


@pytest.mark.parametrize(
    ("patient", "procedure", "reason"),
    [
        ("A" * 161, "Consulta", "paciente excede 160 caracteres"),
        ("Ana", "C" * 201, "procedimento excede 200 caracteres"),
    ],
)
def test_text_limits_match_database_columns(patient: str, procedure: str, reason: str) -> None:
    result = parse_csv(
        csv_bytes(f"11/08/2026 09:30,{patient},34999991111,{procedure}"),
        TIMEZONE,
    )

    assert result.valid_rows == []
    assert result.errors[0].reason == reason
