from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from clinic_confirmations.api.dependencies import (
    get_app_settings,
    get_db_session,
    get_task_publisher,
)
from clinic_confirmations.core.config import Settings
from clinic_confirmations.domain.enums import MessageStatus
from clinic_confirmations.queue.publisher import TaskPublisher
from clinic_confirmations.schemas.messages import (
    MessageDetail,
    MessageList,
    RetryResponse,
)
from clinic_confirmations.services.messages import (
    get_message,
    list_messages,
    retry_message,
)

router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("", response_model=MessageList)
def list_message_route(
    session: Annotated[Session, Depends(get_db_session)],
    status: Annotated[MessageStatus | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> MessageList:
    return list_messages(
        session,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/{message_id}", response_model=MessageDetail)
def get_message_route(
    message_id: UUID,
    session: Annotated[Session, Depends(get_db_session)],
) -> MessageDetail:
    return get_message(session, message_id)


@router.post("/{message_id}/retry", response_model=RetryResponse)
def retry_message_route(
    message_id: UUID,
    session: Annotated[Session, Depends(get_db_session)],
    publisher: Annotated[TaskPublisher, Depends(get_task_publisher)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> RetryResponse:
    return retry_message(session, message_id, publisher, settings)
