import csv
import hashlib
from datetime import UTC, datetime
from io import StringIO
from zoneinfo import ZoneInfo

import phonenumbers
from sqlalchemy.orm import Session

from clinic_confirmations.domain.errors import (
    InvalidCsvEncodingError,
    InvalidCsvFormatError,
    InvalidCsvHeaderError,
)
from clinic_confirmations.repositories.appointments import AppointmentRepository
from clinic_confirmations.schemas.imports import (
    ImportReport,
    ImportRowError,
    ImportSummary,
    NormalizedImportRow,
    ParsedImport,
)

CSV_HEADER = ("data_hora", "paciente", "telefone", "procedimento")
SUPPORTED_DATETIME_FORMATS = ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M")


def parse_local_datetime(raw: str, timezone: ZoneInfo) -> datetime:
    value = raw.strip()
    for date_format in SUPPORTED_DATETIME_FORMATS:
        try:
            local_datetime = datetime.strptime(value, date_format).replace(tzinfo=timezone)
        except ValueError:
            continue
        return local_datetime.astimezone(UTC)
    raise ValueError("data_hora inválida")


def normalize_phone(raw: str) -> str:
    try:
        number = phonenumbers.parse(raw.strip(), "BR")
    except phonenumbers.NumberParseException as exc:
        raise ValueError("telefone inválido") from exc

    national_number = str(number.national_number)
    if (
        number.country_code != 55
        or len(national_number) not in {10, 11}
        or not phonenumbers.is_valid_number(number)
    ):
        raise ValueError("telefone inválido")

    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def parse_csv(content: bytes, timezone: ZoneInfo) -> ParsedImport:
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidCsvEncodingError from exc

    reader = csv.reader(StringIO(decoded, newline=""), strict=True)
    try:
        header = next(reader, None)
    except csv.Error as exc:
        raise InvalidCsvFormatError from exc
    if tuple(header or ()) != CSV_HEADER:
        raise InvalidCsvHeaderError(header)

    total_rows = 0
    valid_rows: list[NormalizedImportRow] = []
    errors: list[ImportRowError] = []

    try:
        for values in reader:
            line_number = reader.line_num
            if not values or all(not value.strip() for value in values):
                continue

            total_rows += 1
            raw_data = _raw_data(values)
            if len(values) != len(CSV_HEADER):
                errors.append(
                    ImportRowError(
                        line_number=line_number,
                        raw_data=raw_data,
                        reason="quantidade de colunas inválida",
                    )
                )
                continue

            try:
                valid_rows.append(_normalize_row(values, line_number, raw_data, timezone))
            except ValueError as exc:
                errors.append(
                    ImportRowError(
                        line_number=line_number,
                        raw_data=raw_data,
                        reason=str(exc),
                    )
                )
    except csv.Error as exc:
        raise InvalidCsvFormatError from exc

    return ParsedImport(total_rows=total_rows, valid_rows=valid_rows, errors=errors)


def import_appointments_from_csv(
    content: bytes,
    timezone: ZoneInfo,
    session: Session,
) -> ImportReport:
    parsed = parse_csv(content, timezone)
    repository = AppointmentRepository(session)
    imported_lines: list[int] = []
    duplicate_lines: list[int] = []

    for row in parsed.valid_rows:
        if repository.insert_import_row_if_absent(row) is None:
            duplicate_lines.append(row.line_number)
        else:
            imported_lines.append(row.line_number)

    session.commit()
    return ImportReport(
        summary=ImportSummary(
            total_rows=parsed.total_rows,
            imported=len(imported_lines),
            rejected=len(parsed.errors),
            duplicates=len(duplicate_lines),
        ),
        imported_lines=imported_lines,
        duplicate_lines=duplicate_lines,
        errors=parsed.errors,
    )


def _raw_data(values: list[str]) -> dict[str, str]:
    data = {
        column: values[index] if index < len(values) else ""
        for index, column in enumerate(CSV_HEADER)
    }
    if len(values) > len(CSV_HEADER):
        data["_extra"] = ",".join(values[len(CSV_HEADER) :])
    return data


def _normalize_row(
    values: list[str],
    line_number: int,
    raw_data: dict[str, str],
    timezone: ZoneInfo,
) -> NormalizedImportRow:
    date_raw, patient_raw, phone_raw, procedure_raw = values
    patient_name = _required_text(patient_raw, "paciente", max_length=160)
    procedure = _required_text(procedure_raw, "procedimento", max_length=200)
    if not date_raw.strip():
        raise ValueError("data_hora obrigatória")
    if not phone_raw.strip():
        raise ValueError("telefone obrigatório")

    scheduled_at = parse_local_datetime(date_raw, timezone)
    phone = normalize_phone(phone_raw)
    fingerprint = _fingerprint(scheduled_at, patient_name, phone, procedure)
    return NormalizedImportRow(
        line_number=line_number,
        raw_data=raw_data,
        scheduled_at=scheduled_at,
        patient_name=patient_name,
        phone=phone,
        procedure=procedure,
        import_fingerprint=fingerprint,
    )


def _required_text(raw: str, field_name: str, *, max_length: int) -> str:
    normalized = " ".join(raw.split())
    if not normalized:
        raise ValueError(f"{field_name} obrigatório")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} excede {max_length} caracteres")
    return normalized


def _fingerprint(
    scheduled_at: datetime,
    patient_name: str,
    phone: str,
    procedure: str,
) -> str:
    canonical = "\x1f".join(
        (
            scheduled_at.isoformat(),
            patient_name.casefold(),
            phone,
            procedure.casefold(),
        )
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
