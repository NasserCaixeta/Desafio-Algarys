import pytest
from pydantic import ValidationError

from clinic_confirmations.core.config import Settings


def test_settings_parse_cors_and_failure_suffixes() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://u:p@db/app",
        redis_url="redis://redis:6379/0",
        cors_origins="http://localhost:3000, http://localhost:5173",
        simulated_failure_suffixes="0000,9999",
    )

    assert settings.cors_origin_list == [
        "http://localhost:3000",
        "http://localhost:5173",
    ]
    assert settings.failure_suffix_list == ("0000", "9999")
    assert settings.timezone == "America/Sao_Paulo"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_upload_bytes", 0),
        ("max_message_attempts", 0),
        ("processing_lease_seconds", -1),
    ],
)
def test_settings_reject_non_positive_limits(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://u:p@db/app",
            redis_url="redis://redis:6379/0",
            **{field: value},
        )


def test_settings_reject_unknown_timezone() -> None:
    with pytest.raises(ValidationError, match="Unknown timezone"):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://u:p@db/app",
            redis_url="redis://redis:6379/0",
            timezone="Mars/Olympus",
        )
