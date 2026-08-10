from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from clinic_confirmations.db.base import Base, EntityMixin
from clinic_confirmations.domain.enums import MessageStatus, enum_values

if TYPE_CHECKING:
    from clinic_confirmations.db.models.appointment import Appointment
    from clinic_confirmations.db.models.message_attempt import MessageAttempt


class ConfirmationMessage(EntityMixin, Base):
    __tablename__ = "confirmation_messages"
    __table_args__ = (
        UniqueConstraint("appointment_id", name="uq_confirmation_messages_appointment_id"),
        CheckConstraint(
            "attempt_count >= 0",
            name="attempt_count_non_negative",
        ),
        CheckConstraint("max_attempts > 0", name="max_attempts_positive"),
        CheckConstraint(
            "enqueue_attempts >= 0",
            name="enqueue_attempts_non_negative",
        ),
        Index("ix_confirmation_messages_status_next_enqueue", "status", "next_enqueue_at"),
        Index("ix_confirmation_messages_processing_started_at", "processing_started_at"),
    )

    appointment_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus, name="message_status", values_callable=enum_values),
        nullable=False,
        default=MessageStatus.PENDING,
        server_default=MessageStatus.PENDING.value,
    )
    attempt_count: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    max_attempts: Mapped[int] = mapped_column(nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enqueue_attempts: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    last_enqueue_error: Mapped[str | None] = mapped_column(Text)
    next_enqueue_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_token: Mapped[UUID | None] = mapped_column(Uuid)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)

    appointment: Mapped[Appointment] = relationship(back_populates="confirmation_message")
    attempts: Mapped[list[MessageAttempt]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="MessageAttempt.attempt_number",
    )
