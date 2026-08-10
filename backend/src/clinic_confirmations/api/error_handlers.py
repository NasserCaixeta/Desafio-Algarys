from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from clinic_confirmations.domain.errors import (
    InvalidCsvEncodingError,
    InvalidCsvFormatError,
    InvalidCsvHeaderError,
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
