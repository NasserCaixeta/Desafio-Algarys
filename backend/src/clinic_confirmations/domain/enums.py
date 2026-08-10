from enum import StrEnum


def enum_values(enum_type: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_type]


class AppointmentStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DECLINED = "declined"


class MessageStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"


class AttemptResult(StrEnum):
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    ABANDONED = "abandoned"
