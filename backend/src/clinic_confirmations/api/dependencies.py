from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from clinic_confirmations.core.config import Settings


def get_db_session(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings
