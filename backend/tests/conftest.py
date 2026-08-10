import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from clinic_confirmations.api.dependencies import get_db_session
from clinic_confirmations.core.config import Settings
from clinic_confirmations.db.models import Appointment, ConfirmationMessage
from clinic_confirmations.db.session import create_database_engine
from clinic_confirmations.main import create_app

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://clinic:clinic_local_password@localhost:5433/clinic_confirmations_test",
)
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6380/0")


@pytest.fixture(scope="session")
def database_engine() -> Iterator[Engine]:
    settings = Settings(
        _env_file=None,
        database_url=TEST_DATABASE_URL,
        redis_url=TEST_REDIS_URL,
    )
    engine = create_database_engine(settings)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(database_engine: Engine) -> Iterator[Session]:
    connection = database_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    yield session
    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url=TEST_DATABASE_URL,
        redis_url=TEST_REDIS_URL,
    )


@pytest.fixture
def client(db_session: Session, test_settings: Settings) -> Iterator[TestClient]:
    app = create_app(test_settings)

    def override_db_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


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
