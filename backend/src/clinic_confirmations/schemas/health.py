from typing import Literal

from pydantic import BaseModel


class LivenessResponse(BaseModel):
    status: Literal["alive"] = "alive"
    version: str


class DependencyStatus(BaseModel):
    postgresql: bool
    redis: bool


class ReadinessResponse(BaseModel):
    status: Literal["ready", "unavailable"]
    dependencies: DependencyStatus


class StatusResponse(BaseModel):
    version: str
    environment: str
    dependencies: DependencyStatus
    messages: dict[str, int]
