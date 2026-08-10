from datetime import datetime

from pydantic import BaseModel, Field


class NormalizedImportRow(BaseModel):
    line_number: int = Field(ge=2)
    raw_data: dict[str, str]
    scheduled_at: datetime
    patient_name: str
    phone: str
    procedure: str
    import_fingerprint: str = Field(min_length=64, max_length=64)


class ImportRowError(BaseModel):
    line_number: int = Field(ge=2)
    raw_data: dict[str, str]
    reason: str


class ParsedImport(BaseModel):
    total_rows: int = Field(ge=0)
    valid_rows: list[NormalizedImportRow] = Field(default_factory=list)
    errors: list[ImportRowError] = Field(default_factory=list)
