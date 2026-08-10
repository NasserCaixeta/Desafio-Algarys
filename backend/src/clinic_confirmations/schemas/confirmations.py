from datetime import date

from pydantic import BaseModel, Field


class DispatchRequest(BaseModel):
    date: date


class DispatchResult(BaseModel):
    eligible: int = Field(ge=0)
    created: int = Field(ge=0)
    already_existing: int = Field(ge=0)
    ignored: int = Field(ge=0)
    queued: int = Field(ge=0)
    pending_reconciliation: int = Field(ge=0)
