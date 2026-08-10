from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from clinic_confirmations.db.models import Appointment, ConfirmationMessage, MessageAttempt
from clinic_confirmations.domain.enums import AttemptResult, MessageStatus


@dataclass(frozen=True, slots=True)
class ClaimedMessage:
    id: UUID
    phone: str
    attempt_number: int
    processing_token: UUID


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

    def lock_next_reconcilable(self, now: datetime) -> ConfirmationMessage | None:
        statement = (
            select(ConfirmationMessage)
            .where(ConfirmationMessage.status == MessageStatus.PENDING)
            .where(ConfirmationMessage.enqueued_at.is_(None))
            .where(
                or_(
                    ConfirmationMessage.next_enqueue_at.is_(None),
                    ConfirmationMessage.next_enqueue_at <= now,
                )
            )
            .order_by(
                ConfirmationMessage.next_enqueue_at.asc().nullsfirst(),
                ConfirmationMessage.created_at,
                ConfirmationMessage.id,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        return self._session.scalar(statement)

    def claim_for_processing(
        self,
        message_id: UUID,
        *,
        processing_token: UUID,
        now: datetime,
    ) -> ClaimedMessage | None:
        statement = (
            update(ConfirmationMessage)
            .where(ConfirmationMessage.id == message_id)
            .where(ConfirmationMessage.status == MessageStatus.PENDING)
            .where(ConfirmationMessage.attempt_count < ConfirmationMessage.max_attempts)
            .where(
                or_(
                    ConfirmationMessage.next_enqueue_at.is_(None),
                    ConfirmationMessage.next_enqueue_at <= now,
                )
            )
            .values(
                status=MessageStatus.PROCESSING,
                attempt_count=ConfirmationMessage.attempt_count + 1,
                processing_token=processing_token,
                processing_started_at=now,
            )
            .returning(
                ConfirmationMessage.appointment_id,
                ConfirmationMessage.attempt_count,
            )
        )
        claimed = self._session.execute(statement).one_or_none()
        if claimed is None:
            return None

        appointment_id, attempt_number = claimed
        phone = self._session.scalar(
            select(Appointment.phone).where(Appointment.id == appointment_id)
        )
        if phone is None:
            self._session.rollback()
            raise RuntimeError("Claimed message has no appointment")

        self._session.add(
            MessageAttempt(
                message_id=message_id,
                attempt_number=attempt_number,
                processing_token=processing_token,
                started_at=now,
            )
        )
        self._session.commit()
        return ClaimedMessage(
            id=message_id,
            phone=phone,
            attempt_number=attempt_number,
            processing_token=processing_token,
        )

    def finalize_success(
        self,
        message_id: UUID,
        processing_token: UUID,
        *,
        now: datetime,
    ) -> bool:
        updated_id = self._session.scalar(
            update(ConfirmationMessage)
            .where(ConfirmationMessage.id == message_id)
            .where(ConfirmationMessage.status == MessageStatus.PROCESSING)
            .where(ConfirmationMessage.processing_token == processing_token)
            .values(
                status=MessageStatus.SENT,
                last_error=None,
                next_enqueue_at=None,
                processing_token=None,
                processing_started_at=None,
            )
            .returning(ConfirmationMessage.id)
        )
        if updated_id is None:
            self._session.commit()
            return False
        self._complete_attempt(
            message_id,
            processing_token,
            result=AttemptResult.SENT,
            error=None,
            now=now,
        )
        self._session.commit()
        return True

    def finalize_failure(
        self,
        message_id: UUID,
        processing_token: UUID,
        *,
        error: str,
        next_retry_at: datetime,
        now: datetime,
    ) -> bool:
        updated_id = self._session.scalar(
            update(ConfirmationMessage)
            .where(ConfirmationMessage.id == message_id)
            .where(ConfirmationMessage.status == MessageStatus.PROCESSING)
            .where(ConfirmationMessage.processing_token == processing_token)
            .values(
                status=MessageStatus.FAILED,
                last_error=error,
                enqueued_at=None,
                next_enqueue_at=next_retry_at,
                processing_token=None,
                processing_started_at=None,
            )
            .returning(ConfirmationMessage.id)
        )
        if updated_id is None:
            self._session.commit()
            return False
        self._complete_attempt(
            message_id,
            processing_token,
            result=AttemptResult.FAILED,
            error=error,
            now=now,
        )
        self._session.commit()
        return True

    def get_status(self, message_id: UUID) -> MessageStatus | None:
        return self._session.scalar(
            select(ConfirmationMessage.status).where(ConfirmationMessage.id == message_id)
        )

    def lock_by_id(self, message_id: UUID) -> ConfirmationMessage | None:
        return self._session.scalar(
            select(ConfirmationMessage)
            .where(ConfirmationMessage.id == message_id)
            .with_for_update()
        )

    def lock_due_failed(
        self,
        *,
        now: datetime,
        batch_size: int,
    ) -> list[ConfirmationMessage]:
        statement = (
            select(ConfirmationMessage)
            .where(ConfirmationMessage.status == MessageStatus.FAILED)
            .where(ConfirmationMessage.attempt_count < ConfirmationMessage.max_attempts)
            .where(ConfirmationMessage.next_enqueue_at <= now)
            .order_by(ConfirmationMessage.next_enqueue_at, ConfirmationMessage.id)
            .with_for_update(skip_locked=True)
            .limit(batch_size)
        )
        return list(self._session.scalars(statement).all())

    def lock_stale_processing(
        self,
        *,
        started_before: datetime,
        batch_size: int,
    ) -> list[ConfirmationMessage]:
        statement = (
            select(ConfirmationMessage)
            .where(ConfirmationMessage.status == MessageStatus.PROCESSING)
            .where(ConfirmationMessage.processing_started_at <= started_before)
            .order_by(ConfirmationMessage.processing_started_at, ConfirmationMessage.id)
            .with_for_update(skip_locked=True)
            .limit(batch_size)
        )
        return list(self._session.scalars(statement).all())

    def get_processing_attempt(
        self,
        message_id: UUID,
        processing_token: UUID,
    ) -> MessageAttempt | None:
        return self._session.scalar(
            select(MessageAttempt)
            .where(MessageAttempt.message_id == message_id)
            .where(MessageAttempt.processing_token == processing_token)
            .where(MessageAttempt.result == AttemptResult.PROCESSING)
        )

    def list_messages(
        self,
        *,
        status: MessageStatus | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ConfirmationMessage], int]:
        conditions: list[ColumnElement[bool]] = []
        if status is not None:
            conditions.append(ConfirmationMessage.status == status)
        total = self._session.scalar(
            select(func.count()).select_from(ConfirmationMessage).where(*conditions)
        )
        statement = (
            select(ConfirmationMessage)
            .where(*conditions)
            .order_by(ConfirmationMessage.created_at.desc(), ConfirmationMessage.id)
            .offset(offset)
            .limit(limit)
        )
        return list(self._session.scalars(statement).all()), total or 0

    def get_with_attempts(self, message_id: UUID) -> ConfirmationMessage | None:
        return self._session.scalar(
            select(ConfirmationMessage)
            .options(selectinload(ConfirmationMessage.attempts))
            .where(ConfirmationMessage.id == message_id)
        )

    def get(self, message_id: UUID) -> ConfirmationMessage | None:
        return self._session.get(ConfirmationMessage, message_id)

    def _complete_attempt(
        self,
        message_id: UUID,
        processing_token: UUID,
        *,
        result: AttemptResult,
        error: str | None,
        now: datetime,
    ) -> None:
        attempt = self._session.scalar(
            select(MessageAttempt)
            .where(MessageAttempt.message_id == message_id)
            .where(MessageAttempt.processing_token == processing_token)
            .where(MessageAttempt.result == AttemptResult.PROCESSING)
        )
        if attempt is None:
            self._session.rollback()
            raise RuntimeError("Processing attempt not found for current token")
        attempt.result = result
        attempt.error = error
        attempt.completed_at = now
