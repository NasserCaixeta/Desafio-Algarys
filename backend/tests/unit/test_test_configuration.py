import os

from clinic_confirmations.core.config import Settings


def test_settings_fixture_honors_test_redis_url(test_settings: Settings) -> None:
    expected = os.getenv("TEST_REDIS_URL", "redis://localhost:6380/0")

    assert test_settings.redis_url == expected
