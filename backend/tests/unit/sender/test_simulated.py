import pytest

from clinic_confirmations.sender.simulated import SimulatedSender, SimulatedSendError


@pytest.mark.parametrize("attempt", [1, 2])
def test_sender_fails_configured_initial_attempts(attempt: int) -> None:
    sender = SimulatedSender(
        failure_suffixes=("0000",),
        failure_attempts=2,
        latency_ms=0,
    )

    with pytest.raises(SimulatedSendError, match="simulated failure"):
        sender.send(phone="+5534999990000", attempt_number=attempt)


def test_sender_succeeds_after_configured_failure_attempts() -> None:
    sender = SimulatedSender(
        failure_suffixes=("0000",),
        failure_attempts=1,
        latency_ms=0,
    )

    sender.send(phone="+5534999990000", attempt_number=2)


def test_sender_succeeds_for_phone_without_failure_suffix() -> None:
    sender = SimulatedSender(
        failure_suffixes=("0000", "9999"),
        failure_attempts=10,
        latency_ms=0,
    )

    sender.send(phone="+5534999991111", attempt_number=1)


def test_sender_with_zero_failure_attempts_always_succeeds() -> None:
    sender = SimulatedSender(
        failure_suffixes=("0000",),
        failure_attempts=0,
        latency_ms=0,
    )

    sender.send(phone="+5534999990000", attempt_number=1)
