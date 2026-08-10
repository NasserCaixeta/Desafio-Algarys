from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from clinic_confirmations.db.base import Base, EntityMixin
from clinic_confirmations.domain.enums import AppointmentStatus, enum_values

if TYPE_CHECKING:
    from clinic_confirmations.db.models.confirmation_message import ConfirmationMessage


class Appointment(EntityMixin, Base):
    __tablename__ = "appointments"
    __table_args__ = (
        UniqueConstraint("import_fingerprint", name="uq_appointments_import_fingerprint"),
        Index("ix_appointments_scheduled_at", "scheduled_at"),
        Index("ix_appointments_status_scheduled_at", "status", "scheduled_at"),
    )

    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    patient_name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str] = mapped_column(String(16), nullable=False)
    procedure: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, name="appointment_status", values_callable=enum_values),
        nullable=False,
        default=AppointmentStatus.PENDING,
        server_default=AppointmentStatus.PENDING.value,
    )
    import_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    confirmation_message: Mapped[ConfirmationMessage | None] = relationship(
        back_populates="appointment",
        uselist=False,
    )
