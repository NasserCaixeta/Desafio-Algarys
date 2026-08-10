from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from clinic_confirmations.domain.enums import (
    AppointmentStatus,
    AttemptResult,
    MessageStatus,
)
from clinic_confirmations.schemas.common import Pagination


class PatientResponseRequest(BaseModel):
    status: Literal["confirmed", "declined"]


class PatientResponseResult(BaseModel):
    id: UUID
    status: AppointmentStatus


class MessageAttemptRead(BaseModel):
    id: UUID
    attempt_number: int = Field(gt=0)
    started_at: datetime
    completed_at: datetime | None
    result: AttemptResult
    error: str | None


class MessageRead(BaseModel):
    id: UUID
    appointment_id: UUID
    status: MessageStatus
    attempt_count: int = Field(ge=0)
    max_attempts: int = Field(gt=0)
    last_error: str | None
    enqueued_at: datetime | None
    next_enqueue_at: datetime | None


class MessageDetail(MessageRead):
    attempts: list[MessageAttemptRead]


class MessageList(BaseModel):
    items: list[MessageRead]
    pagination: Pagination


class RetryResponse(BaseModel):
    id: UUID
    status: MessageStatus
    attempt_count: int = Field(ge=0)
    max_attempts: int = Field(gt=0)
    queued: bool
    pending_reconciliation: bool
    enqueued_at: datetime | None
    next_enqueue_at: datetime | None
