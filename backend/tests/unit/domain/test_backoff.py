import pytest

from clinic_confirmations.domain.transitions import retry_delay_seconds


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [(1, 5), (2, 10), (3, 20), (8, 60)],
)
def test_exponential_backoff_is_bounded(attempt: int, expected: int) -> None:
    assert retry_delay_seconds(attempt=attempt, base=5, maximum=60) == expected


@pytest.mark.parametrize(
    ("attempt", "base", "maximum"),
    [(0, 5, 60), (1, 0, 60), (1, 5, 0)],
)
def test_backoff_rejects_non_positive_inputs(attempt: int, base: int, maximum: int) -> None:
    with pytest.raises(ValueError):
        retry_delay_seconds(attempt=attempt, base=base, maximum=maximum)
