from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from clinic_confirmations.db.models import Appointment
from clinic_confirmations.domain.enums import AppointmentStatus
from clinic_confirmations.schemas.imports import NormalizedImportRow


class AppointmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def insert_import_row_if_absent(self, row: NormalizedImportRow) -> UUID | None:
        statement = (
            insert(Appointment)
            .values(
                scheduled_at=row.scheduled_at,
                patient_name=row.patient_name,
                phone=row.phone,
                procedure=row.procedure,
                import_fingerprint=row.import_fingerprint,
            )
            .on_conflict_do_nothing(index_elements=[Appointment.import_fingerprint])
            .returning(Appointment.id)
        )
        return self._session.execute(statement).scalar_one_or_none()

    def list_with_message(
        self,
        *,
        start_at: datetime | None,
        end_at: datetime | None,
        status: AppointmentStatus | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Appointment], int]:
        conditions: list[ColumnElement[bool]] = []
        if start_at is not None:
            conditions.append(Appointment.scheduled_at >= start_at)
        if end_at is not None:
            conditions.append(Appointment.scheduled_at < end_at)
        if status is not None:
            conditions.append(Appointment.status == status)

        total = self._session.scalar(
            select(func.count()).select_from(Appointment).where(*conditions)
        )
        statement = (
            select(Appointment)
            .options(selectinload(Appointment.confirmation_message))
            .where(*conditions)
            .order_by(Appointment.scheduled_at, Appointment.id)
            .offset(offset)
            .limit(limit)
        )
        appointments = list(self._session.scalars(statement).all())
        return appointments, total or 0

    def get_with_message(self, appointment_id: UUID) -> Appointment | None:
        statement = (
            select(Appointment)
            .options(selectinload(Appointment.confirmation_message))
            .where(Appointment.id == appointment_id)
        )
        return self._session.scalar(statement)
