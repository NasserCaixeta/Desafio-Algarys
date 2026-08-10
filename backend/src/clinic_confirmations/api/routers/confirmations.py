from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from clinic_confirmations.api.dependencies import (
    get_app_settings,
    get_db_session,
    get_task_publisher,
)
from clinic_confirmations.core.config import Settings
from clinic_confirmations.queue.publisher import TaskPublisher
from clinic_confirmations.schemas.confirmations import DispatchRequest, DispatchResult
from clinic_confirmations.services.dispatch import dispatch_for_date

router = APIRouter(prefix="/confirmations", tags=["confirmations"])


@router.post("/dispatch", response_model=DispatchResult)
def dispatch_confirmations(
    payload: DispatchRequest,
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    publisher: Annotated[TaskPublisher, Depends(get_task_publisher)],
) -> DispatchResult:
    return dispatch_for_date(
        session,
        payload.date,
        settings,
        correlation_id=request.state.request_id,
        publisher=publisher,
    )
