"""Application factory and router registration."""

from fastapi import FastAPI

from astra_interior_designer.api import auth, health, sessions
from astra_interior_designer.dependencies import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(sessions.router)

    return app
