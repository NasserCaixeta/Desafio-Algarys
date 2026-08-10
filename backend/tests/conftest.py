import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from clinic_confirmations.core.config import Settings
from clinic_confirmations.db.models import Appointment, ConfirmationMessage
from clinic_confirmations.db.session import create_database_engine, create_session_factory

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://clinic:clinic_local_password@localhost:5433/clinic_confirmations_test",
)


@pytest.fixture(scope="session")
def database_engine() -> Iterator[Engine]:
    settings = Settings(
        _env_file=None,
        database_url=TEST_DATABASE_URL,
        redis_url="redis://localhost:6380/0",
    )
    engine = create_database_engine(settings)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(database_engine: Engine) -> Iterator[Session]:
    factory = create_session_factory(database_engine)
    session = factory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def appointment_factory(db_session: Session) -> Callable[..., Appointment]:
    def create(**overrides: object) -> Appointment:
        values: dict[str, object] = {
            "scheduled_at": datetime(2026, 8, 11, 12, 30, tzinfo=UTC),
            "patient_name": "Ana Souza",
            "phone": "+5534999991111",
            "procedure": "Consulta inicial",
            "import_fingerprint": uuid4().hex,
        }
        values.update(overrides)
        appointment = Appointment(**values)
        db_session.add(appointment)
        db_session.flush()
        return appointment

    return create


@pytest.fixture
def message_factory(
    db_session: Session,
    appointment_factory: Callable[..., Appointment],
) -> Callable[..., ConfirmationMessage]:
    def create(**overrides: object) -> ConfirmationMessage:
        appointment = overrides.pop("appointment", None) or appointment_factory()
        values: dict[str, object] = {
            "appointment_id": appointment.id,
            "max_attempts": 3,
            "correlation_id": uuid4().hex,
        }
        values.update(overrides)
        message = ConfirmationMessage(**values)
        db_session.add(message)
        db_session.flush()
        return message

    return create
