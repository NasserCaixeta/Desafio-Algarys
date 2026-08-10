from importlib import import_module
from importlib.util import find_spec

import pytest
from pydantic import ValidationError


def load_settings_class():  # type: ignore[no-untyped-def]
    core_spec = find_spec("clinic_confirmations.core")
    assert core_spec is not None, "core package must exist"
    spec = find_spec("clinic_confirmations.core.config")
    assert spec is not None, "core.config module must exist"
    return import_module("clinic_confirmations.core.config").Settings


def test_settings_parse_cors_and_failure_suffixes() -> None:
    settings_class = load_settings_class()

    settings = settings_class(
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
    settings_class = load_settings_class()

    with pytest.raises(ValidationError):
        settings_class(
            _env_file=None,
            database_url="postgresql+psycopg://u:p@db/app",
            redis_url="redis://redis:6379/0",
            **{field: value},
        )


def test_settings_reject_unknown_timezone() -> None:
    settings_class = load_settings_class()

    with pytest.raises(ValidationError, match="Unknown timezone"):
        settings_class(
            _env_file=None,
            database_url="postgresql+psycopg://u:p@db/app",
            redis_url="redis://redis:6379/0",
            timezone="Mars/Olympus",
        )
