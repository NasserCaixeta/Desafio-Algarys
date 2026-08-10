from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from clinic_confirmations.db.models import ConfirmationMessage


class MessageRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_pending_for_appointments(
        self,
        appointment_ids: list[UUID],
        *,
        max_attempts: int,
        correlation_id: str,
        next_enqueue_at: datetime,
    ) -> list[UUID]:
        if not appointment_ids:
            return []
        values = [
            {
                "id": uuid4(),
                "appointment_id": appointment_id,
                "max_attempts": max_attempts,
                "correlation_id": correlation_id,
                "next_enqueue_at": next_enqueue_at,
            }
            for appointment_id in appointment_ids
        ]
        statement = (
            insert(ConfirmationMessage)
            .values(values)
            .on_conflict_do_nothing(index_elements=[ConfirmationMessage.appointment_id])
            .returning(ConfirmationMessage.id)
        )
        return list(self._session.scalars(statement).all())
