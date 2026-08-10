import sys
from typing import Any, TextIO, cast

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars

_service = "application"


def configure_logging(
    *,
    service: str,
    level: str,
    json_output: bool,
    stream: TextIO | None = None,
) -> None:
    """Configure deterministic structured logging for one process."""
    global _service
    _service = service

    renderer: structlog.types.Processor
    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[
            merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level.upper()),
        logger_factory=structlog.PrintLoggerFactory(file=stream or sys.stdout),
        cache_logger_on_first_use=False,
    )


def bind_context(**values: str) -> None:
    bind_contextvars(**values)


def clear_context() -> None:
    clear_contextvars()


def get_logger(**initial_values: Any) -> structlog.typing.FilteringBoundLogger:
    return cast(
        structlog.typing.FilteringBoundLogger,
        structlog.get_logger(service=_service, **initial_values),
    )
