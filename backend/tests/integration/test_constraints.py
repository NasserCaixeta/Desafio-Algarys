from collections.abc import Callable
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from clinic_confirmations.db.models import Appointment, ConfirmationMessage, MessageAttempt


def test_import_fingerprint_is_enforced_by_postgresql(
    db_session: Session,
    appointment_factory: Callable[..., Appointment],
) -> None:
    appointment_factory(import_fingerprint="same-fingerprint")

    with pytest.raises(IntegrityError):
        appointment_factory(import_fingerprint="same-fingerprint")


def test_confirmation_message_is_unique_per_appointment(
    db_session: Session,
    appointment_factory: Callable[..., Appointment],
    message_factory: Callable[..., ConfirmationMessage],
) -> None:
    appointment = appointment_factory()
    message_factory(appointment=appointment)

    with pytest.raises(IntegrityError):
        message_factory(appointment=appointment)


def test_attempt_number_is_unique_per_message(
    db_session: Session,
    message_factory: Callable[..., ConfirmationMessage],
) -> None:
    message = message_factory()
    db_session.add(
        MessageAttempt(
            message_id=message.id,
            attempt_number=1,
            processing_token=uuid4(),
        )
    )
    db_session.flush()
    db_session.add(
        MessageAttempt(
            message_id=message.id,
            attempt_number=1,
            processing_token=uuid4(),
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()
