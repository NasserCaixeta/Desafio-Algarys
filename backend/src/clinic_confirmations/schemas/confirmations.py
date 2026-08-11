from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class DispatchRequest(BaseModel):
    date: date
    appointment_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=1000)


class DispatchResult(BaseModel):
    eligible: int = Field(ge=0)
    created: int = Field(ge=0)
    already_existing: int = Field(ge=0)
    ignored: int = Field(ge=0)
    queued: int = Field(ge=0)
    pending_reconciliation: int = Field(ge=0)
