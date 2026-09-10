"""FastAPI application and resource lifetime."""

import logging
from contextlib import asynccontextmanager

from agent_api_sdk import AgentAPISDKError
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from astra_interior_designer.api.sessions import router
from astra_interior_designer.config import ConfigError, Settings, load_settings
from astra_interior_designer.dependencies import Services, build_services
from astra_interior_designer.services.sandbox import SandboxUnavailable
from astra_interior_designer.services.sessions import (
    SessionConflict,
    SessionNotFound,
    SessionUnavailable,
)
from astra_interior_designer.services.storage import (
    RecordTooLarge,
    StorageConfigurationError,
    StorageConflict,
)

logger = logging.getLogger(__name__)


def create_app(
    *, settings: Settings | None = None, services: Services | None = None
) -> FastAPI:
    configuration = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if services is None:
            application.state.settings = await load_settings(configuration)
            application.state.services = await build_services(
                application.state.settings
            )
        else:
            application.state.settings = configuration
            application.state.services = services
        try:
            yield
        finally:
            await application.state.services.close()

    application = FastAPI(title="Astra Interior Designer API", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(configuration.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    application.include_router(router)

    @application.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    async def not_found(_request: Request, _error: Exception):
        return JSONResponse(
            status_code=404, content={"detail": "Session or file not found"}
        )

    async def conflict(_request: Request, _error: Exception):
        return JSONResponse(
            status_code=409,
            content={"detail": "Session operation conflicts with current state"},
        )

    async def unavailable(_request: Request, error: Exception):
        logger.warning("Service unavailable: %s", type(error).__name__)
        return JSONResponse(
            status_code=503,
            content={"detail": "Required service or configuration is unavailable"},
        )

    async def invalid_request(_request: Request, _error: Exception):
        return JSONResponse(status_code=400, content={"detail": "Invalid request data"})

    async def oversized(_request: Request, _error: Exception):
        return JSONResponse(
            status_code=413, content={"detail": "Message is too large to persist"}
        )

    async def upstream_failure(_request: Request, error: Exception):
        logger.warning("AWS operation failed: %s", type(error).__name__)
        return JSONResponse(
            status_code=502, content={"detail": "Storage operation failed"}
        )

    async def agent_failure(_request: Request, error: Exception):
        logger.warning("Agents API operation failed: %s", type(error).__name__)
        return JSONResponse(
            status_code=502, content={"detail": "Agents API operation failed"}
        )

    async def internal_error(_request: Request, error: Exception):
        logger.error("Unhandled request failure: %s", type(error).__name__)
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )

    for exception in (SessionNotFound, FileNotFoundError):
        application.add_exception_handler(exception, not_found)
    for exception in (SessionConflict, StorageConflict):
        application.add_exception_handler(exception, conflict)
    for exception in (
        SessionUnavailable,
        SandboxUnavailable,
        StorageConfigurationError,
        ConfigError,
    ):
        application.add_exception_handler(exception, unavailable)
    for exception in (BotoCoreError, ClientError):
        application.add_exception_handler(exception, upstream_failure)
    application.add_exception_handler(AgentAPISDKError, agent_failure)
    application.add_exception_handler(RecordTooLarge, oversized)
    application.add_exception_handler(ValueError, invalid_request)
    application.add_exception_handler(Exception, internal_error)
    return application


app = create_app()
