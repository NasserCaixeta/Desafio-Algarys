from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from clinic_confirmations.core.config import Settings
from clinic_confirmations.db.models import ConfirmationMessage
from clinic_confirmations.domain.enums import MessageStatus
from clinic_confirmations.schemas.health import DependencyStatus


def check_postgresql(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            return bool(connection.scalar(text("SELECT 1")) == 1)
    except (SQLAlchemyError, OSError):
        return False


def check_redis(settings: Settings) -> bool:
    client: Redis[str] = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=settings.dependency_timeout_seconds,
        socket_timeout=settings.dependency_timeout_seconds,
    )
    try:
        return bool(client.ping())
    except (RedisError, OSError):
        return False
    finally:
        client.close()


def check_dependencies(engine: Engine, settings: Settings) -> DependencyStatus:
    return DependencyStatus(
        postgresql=check_postgresql(engine),
        redis=check_redis(settings),
    )


def count_messages(session: Session) -> dict[str, int]:
    counts = {status.value: 0 for status in MessageStatus}
    statement = select(ConfirmationMessage.status, func.count()).group_by(
        ConfirmationMessage.status
    )
    for status, count in session.execute(statement).tuples():
        counts[status.value] = count
    return counts
