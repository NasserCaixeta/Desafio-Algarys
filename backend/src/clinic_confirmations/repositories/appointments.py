from datetime import date, datetime
from uuid import UUID

from sqlalchemy import ColumnElement, Date, cast, func, select
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

    def list_date_counts(self, timezone: str) -> list[tuple[date, int]]:
        local_date = cast(
            func.timezone(timezone, Appointment.scheduled_at),
            Date,
        ).label("appointment_date")
        count = func.count(Appointment.id).label("appointment_count")
        statement = select(local_date, count).group_by(local_date).order_by(local_date)
        rows = self._session.execute(statement).all()
        return [(row.appointment_date, row.appointment_count) for row in rows]

    def list_dispatch_candidates(
        self,
        start_at: datetime,
        end_at: datetime,
        *,
        appointment_ids: set[UUID] | None = None,
    ) -> list[tuple[UUID, AppointmentStatus]]:
        statement = (
            select(Appointment.id, Appointment.status)
            .where(Appointment.scheduled_at >= start_at)
            .where(Appointment.scheduled_at < end_at)
        )
        if appointment_ids is not None:
            statement = statement.where(Appointment.id.in_(appointment_ids))
        statement = statement.order_by(Appointment.id)
        return list(self._session.execute(statement).tuples().all())

    def lock_with_message(self, appointment_id: UUID) -> Appointment | None:
        statement = (
            select(Appointment)
            .options(selectinload(Appointment.confirmation_message))
            .where(Appointment.id == appointment_id)
            .with_for_update()
        )
        return self._session.scalar(statement)
