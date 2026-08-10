from time import sleep


class SimulatedSendError(RuntimeError):
    """Deterministic sender failure used to exercise operational paths."""


class SimulatedSender:
    def __init__(
        self,
        failure_suffixes: tuple[str, ...],
        *,
        failure_attempts: int,
        latency_ms: int,
    ) -> None:
        self._failure_suffixes = failure_suffixes
        self._failure_attempts = failure_attempts
        self._latency_ms = latency_ms

    def send(self, *, phone: str, attempt_number: int) -> None:
        if self._latency_ms:
            sleep(self._latency_ms / 1000)
        should_fail = attempt_number <= self._failure_attempts and any(
            phone.endswith(suffix) for suffix in self._failure_suffixes
        )
        if should_fail:
            raise SimulatedSendError("simulated failure")
