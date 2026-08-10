from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from clinic_confirmations.api.error_handlers import register_error_handlers
from clinic_confirmations.api.middleware import request_context_middleware
from clinic_confirmations.api.routers.appointments import router as appointments_router
from clinic_confirmations.api.routers.confirmations import router as confirmations_router
from clinic_confirmations.api.routers.health import router as health_router
from clinic_confirmations.api.routers.imports import router as imports_router
from clinic_confirmations.api.routers.messages import router as messages_router
from clinic_confirmations.core.config import Settings, get_settings
from clinic_confirmations.core.logging import configure_logging
from clinic_confirmations.db.session import create_database_engine, create_session_factory
from clinic_confirmations.queue.celery_app import create_celery_app


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(
        service="api",
        level=resolved_settings.log_level,
        json_output=resolved_settings.log_json,
    )
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
    app.state.database_engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.celery_app = create_celery_app(resolved_settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )
    app.middleware("http")(request_context_middleware)

    register_error_handlers(app)
    app.include_router(appointments_router, prefix="/api/v1")
    app.include_router(confirmations_router, prefix="/api/v1")
    app.include_router(imports_router, prefix="/api/v1")
    app.include_router(messages_router, prefix="/api/v1")
    app.include_router(health_router)
    return app


app = create_app()
