from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response

from clinic_confirmations.api.error_handlers import register_error_handlers
from clinic_confirmations.api.routers.appointments import router as appointments_router
from clinic_confirmations.api.routers.confirmations import router as confirmations_router
from clinic_confirmations.api.routers.imports import router as imports_router
from clinic_confirmations.api.routers.messages import router as messages_router
from clinic_confirmations.core.config import Settings, get_settings
from clinic_confirmations.db.session import create_database_engine, create_session_factory
from clinic_confirmations.queue.celery_app import create_celery_app


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    engine = create_database_engine(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.session_factory = create_session_factory(engine)
    app.state.celery_app = create_celery_app(resolved_settings)

    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID")
        if not request_id or len(request_id) > 64:
            request_id = uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    register_error_handlers(app)
    app.include_router(appointments_router, prefix="/api/v1")
    app.include_router(confirmations_router, prefix="/api/v1")
    app.include_router(imports_router, prefix="/api/v1")
    app.include_router(messages_router, prefix="/api/v1")
    return app


app = create_app()
