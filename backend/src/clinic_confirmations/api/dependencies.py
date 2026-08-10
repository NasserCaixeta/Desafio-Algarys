from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from clinic_confirmations.core.config import Settings
from clinic_confirmations.queue.publisher import TaskPublisher


def get_db_session(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_task_publisher(request: Request) -> TaskPublisher:
    publisher: TaskPublisher = request.app.state.celery_app
    return publisher


def get_database_engine(request: Request) -> Engine:
    engine: Engine = request.app.state.database_engine
    return engine
