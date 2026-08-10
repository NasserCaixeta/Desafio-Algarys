from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from clinic_confirmations.db.models import Appointment
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
