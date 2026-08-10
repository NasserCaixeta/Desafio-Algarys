from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from clinic_confirmations.api.dependencies import (
    get_app_settings,
    get_database_engine,
    get_db_session,
)
from clinic_confirmations.core.config import Settings
from clinic_confirmations.schemas.health import (
    LivenessResponse,
    ReadinessResponse,
    StatusResponse,
)
from clinic_confirmations.services import health as health_service

router = APIRouter(tags=["operations"])


@router.get("/health/live", response_model=LivenessResponse)
def liveness(
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> LivenessResponse:
    return LivenessResponse(version=settings.app_version)


@router.get("/health/ready", response_model=ReadinessResponse)
def readiness(
    engine: Annotated[Engine, Depends(get_database_engine)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ReadinessResponse | JSONResponse:
    dependencies = health_service.check_dependencies(engine, settings)
    ready = dependencies.postgresql and dependencies.redis
    payload = ReadinessResponse(
        status="ready" if ready else "unavailable",
        dependencies=dependencies,
    )
    if not ready:
        return JSONResponse(status_code=503, content=payload.model_dump())
    return payload


@router.get("/status", response_model=StatusResponse)
def status(
    engine: Annotated[Engine, Depends(get_database_engine)],
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> StatusResponse:
    dependencies = health_service.check_dependencies(engine, settings)
    messages = health_service.count_messages(session) if dependencies.postgresql else {}
    return StatusResponse(
        version=settings.app_version,
        environment=settings.app_env,
        dependencies=dependencies,
        messages=messages,
    )
