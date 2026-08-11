from datetime import date
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from clinic_confirmations.api.dependencies import get_app_settings, get_db_session
from clinic_confirmations.core.config import Settings
from clinic_confirmations.domain.enums import AppointmentStatus
from clinic_confirmations.schemas.appointments import (
    AppointmentCalendar,
    AppointmentList,
    AppointmentRead,
)
from clinic_confirmations.schemas.messages import (
    PatientResponseRequest,
    PatientResponseResult,
)
from clinic_confirmations.services.queries import (
    get_appointment,
    list_appointment_dates,
    list_appointments,
)
from clinic_confirmations.services.response import record_patient_response

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("", response_model=AppointmentList)
def list_appointment_route(
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    appointment_date: Annotated[date | None, Query(alias="date")] = None,
    status: Annotated[AppointmentStatus | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AppointmentList:
    return list_appointments(
        session,
        timezone=ZoneInfo(settings.timezone),
        appointment_date=appointment_date,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/calendar", response_model=AppointmentCalendar)
def list_appointment_calendar_route(
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AppointmentCalendar:
    return list_appointment_dates(session, ZoneInfo(settings.timezone))


@router.get("/{appointment_id}", response_model=AppointmentRead)
def get_appointment_route(
    appointment_id: UUID,
    session: Annotated[Session, Depends(get_db_session)],
) -> AppointmentRead:
    return get_appointment(session, appointment_id)


@router.post("/{appointment_id}/response", response_model=PatientResponseResult)
def patient_response_route(
    appointment_id: UUID,
    payload: PatientResponseRequest,
    session: Annotated[Session, Depends(get_db_session)],
) -> PatientResponseResult:
    return record_patient_response(
        session,
        appointment_id,
        AppointmentStatus(payload.status),
    )
