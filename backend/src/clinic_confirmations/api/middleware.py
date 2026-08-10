import re
from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response

from clinic_confirmations.core.logging import bind_context, clear_context, get_logger

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    supplied_id = request.headers.get("X-Request-ID", "")
    request_id = supplied_id if REQUEST_ID_PATTERN.fullmatch(supplied_id) else uuid4().hex
    request.state.request_id = request_id
    clear_context()
    bind_context(request_id=request_id)
    logger = get_logger()
    started_at = perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed",
            method=request.method,
            path=request.url.path,
            duration_ms=round((perf_counter() - started_at) * 1000, 3),
        )
        raise
    else:
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((perf_counter() - started_at) * 1000, 3),
        )
        return response
    finally:
        clear_context()
