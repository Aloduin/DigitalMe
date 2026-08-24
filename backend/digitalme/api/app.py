"""FastAPI application factory."""

from fastapi import FastAPI

from digitalme import __version__
from digitalme.config import get_settings


def create_app() -> FastAPI:
    """Build the API without performing database migrations or external calls."""

    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
