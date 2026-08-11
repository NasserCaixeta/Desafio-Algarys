from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from clinic_confirmations.domain.enums import AppointmentStatus, MessageStatus
from clinic_confirmations.schemas.common import Pagination


class AppointmentMessageSummary(BaseModel):
    id: UUID
    status: MessageStatus
    attempt_count: int = Field(ge=0)
    max_attempts: int = Field(gt=0)
    last_error: str | None


class AppointmentRead(BaseModel):
    id: UUID
    scheduled_at: datetime
    patient_name: str
    phone: str
    procedure: str
    status: AppointmentStatus
    message: AppointmentMessageSummary | None


class AppointmentList(BaseModel):
    items: list[AppointmentRead]
    pagination: Pagination


class AppointmentDateSummary(BaseModel):
    date: date
    count: int = Field(gt=0)


class AppointmentCalendar(BaseModel):
    items: list[AppointmentDateSummary]
