from typing import Protocol


class MessageSender(Protocol):
    def send(self, *, phone: str, attempt_number: int) -> None: ...
