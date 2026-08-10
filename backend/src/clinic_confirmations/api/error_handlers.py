from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from clinic_confirmations.domain.errors import (
    AppointmentNotFoundError,
    InvalidCsvEncodingError,
    InvalidCsvFormatError,
    InvalidCsvHeaderError,
    MessageNotFoundError,
    MessageNotSentError,
    ResponseConflictError,
    RetryLimitReachedError,
    RetryNotAllowedError,
    UploadTooLargeError,
)


def _request_id(request: Request) -> str:
    request_id: str = request.state.request_id
    return request_id


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": jsonable_encoder(details if details is not None else {}),
                "request_id": _request_id(request),
            }
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def framework_http_error(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed"}
        message = exc.detail if isinstance(exc.detail, str) else "Erro ao processar a requisição."
        return _error_response(
            request,
            status_code=exc.status_code,
            code=codes.get(exc.status_code, "http_error"),
            message=message,
            details={} if isinstance(exc.detail, str) else exc.detail,
        )

    @app.exception_handler(MessageNotFoundError)
    async def message_not_found(request: Request, exc: MessageNotFoundError) -> JSONResponse:
        return _error_response(
            request,
            status_code=404,
            code="message_not_found",
            message=str(exc),
        )

    @app.exception_handler(MessageNotSentError)
    async def message_not_sent(request: Request, exc: MessageNotSentError) -> JSONResponse:
        return _error_response(
            request,
            status_code=409,
            code="message_not_sent",
            message=str(exc),
        )

    @app.exception_handler(ResponseConflictError)
    async def response_conflict(request: Request, exc: ResponseConflictError) -> JSONResponse:
        return _error_response(
            request,
            status_code=409,
            code="response_conflict",
            message=str(exc),
        )

    @app.exception_handler(RetryLimitReachedError)
    async def retry_limit_reached(request: Request, exc: RetryLimitReachedError) -> JSONResponse:
        return _error_response(
            request,
            status_code=409,
            code="retry_limit_reached",
            message=str(exc),
        )

    @app.exception_handler(RetryNotAllowedError)
    async def retry_not_allowed(request: Request, exc: RetryNotAllowedError) -> JSONResponse:
        return _error_response(
            request,
            status_code=409,
            code="retry_not_allowed",
            message=str(exc),
        )

    @app.exception_handler(AppointmentNotFoundError)
    async def appointment_not_found(
        request: Request, exc: AppointmentNotFoundError
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=404,
            code="appointment_not_found",
            message=str(exc),
        )

    @app.exception_handler(InvalidCsvHeaderError)
    async def invalid_csv_header(request: Request, exc: InvalidCsvHeaderError) -> JSONResponse:
        return _error_response(
            request,
            status_code=422,
            code="invalid_csv_header",
            message=str(exc),
            details={"expected": exc.expected, "received": exc.received},
        )

    @app.exception_handler(InvalidCsvEncodingError)
    async def invalid_csv_encoding(request: Request, exc: InvalidCsvEncodingError) -> JSONResponse:
        return _error_response(
            request,
            status_code=422,
            code="invalid_csv_encoding",
            message=str(exc),
        )

    @app.exception_handler(InvalidCsvFormatError)
    async def invalid_csv_format(request: Request, exc: InvalidCsvFormatError) -> JSONResponse:
        return _error_response(
            request,
            status_code=422,
            code="invalid_csv_format",
            message=str(exc),
        )

    @app.exception_handler(UploadTooLargeError)
    async def upload_too_large(request: Request, exc: UploadTooLargeError) -> JSONResponse:
        return _error_response(
            request,
            status_code=413,
            code="upload_too_large",
            message=str(exc),
            details={"max_bytes": exc.max_bytes},
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(
            request,
            status_code=422,
            code="request_validation_error",
            message="A requisição possui dados inválidos.",
            details=exc.errors(),
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, _: Exception) -> JSONResponse:
        response = _error_response(
            request,
            status_code=500,
            code="internal_server_error",
            message="Não foi possível processar a requisição.",
        )
        # ServerErrorMiddleware renders this response outside the request middleware,
        # so the correlation header must be attached here as well.
        response.headers["X-Request-ID"] = _request_id(request)
        return response
