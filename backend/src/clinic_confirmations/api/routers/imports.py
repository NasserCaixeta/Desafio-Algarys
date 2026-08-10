from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from clinic_confirmations.api.dependencies import get_app_settings, get_db_session
from clinic_confirmations.core.config import Settings
from clinic_confirmations.domain.errors import UploadTooLargeError
from clinic_confirmations.schemas.imports import ImportReport
from clinic_confirmations.services.csv_import import import_appointments_from_csv

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/appointments", response_model=ImportReport)
async def import_appointments(
    file: Annotated[UploadFile, File(description="Agenda no formato CSV documentado")],
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ImportReport:
    try:
        content = await file.read(settings.max_upload_bytes + 1)
    finally:
        await file.close()
    if len(content) > settings.max_upload_bytes:
        raise UploadTooLargeError(settings.max_upload_bytes)

    return import_appointments_from_csv(content, ZoneInfo(settings.timezone), session)
