from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from clinic_confirmations.db.base import Base, EntityMixin
from clinic_confirmations.domain.enums import AttemptResult, enum_values

if TYPE_CHECKING:
    from clinic_confirmations.db.models.confirmation_message import ConfirmationMessage


class MessageAttempt(EntityMixin, Base):
    __tablename__ = "message_attempts"
    __table_args__ = (
        UniqueConstraint(
            "message_id",
            "attempt_number",
            name="uq_message_attempts_message_number",
        ),
    )

    message_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("confirmation_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(nullable=False)
    processing_token: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[AttemptResult] = mapped_column(
        Enum(AttemptResult, name="attempt_result", values_callable=enum_values),
        nullable=False,
        default=AttemptResult.PROCESSING,
        server_default=AttemptResult.PROCESSING.value,
    )
    error: Mapped[str | None] = mapped_column(Text)

    message: Mapped[ConfirmationMessage] = relationship(back_populates="attempts")
