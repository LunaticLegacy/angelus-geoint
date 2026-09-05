"""HTTP installation for the rebuilt Angelus backend."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from ..core import AngelusCore
from .runs import router as runs_router
from .sessions import router as sessions_router
from .providers import router as providers_router
from .workspace_directory import router as workspace_directory_router
from .settings import router as settings_router
from .session_console import router as session_console_router
from .plugins import router as plugins_router
from .external_agent_hub import router as external_agent_hub_router
from .geoint import router as geoint_router
from .geoint_basemaps import router as basemaps_router
from ..geoint.basemaps import BasemapStore


def include_api_routes(app: FastAPI, core: AngelusCore) -> None:
    """Install API routes and the local GEOINT workbench assets on one host."""
    app.state.angelus_core = core
    app.state.basemaps = BasemapStore(core.state_root / "geoint" / "basemaps.json")
    frontend_root = Path(__file__).resolve().parents[2] / "frontend"

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        """Serve the GEOINT drought-investigation workbench."""
        return FileResponse(
            frontend_root / "templates" / "geoint.html",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        """Serve the GEOINT mark for hosts that still request favicon.ico."""
        return FileResponse(frontend_root / "static" / "geoint-mark.svg", media_type="image/svg+xml")

    @app.on_event("startup")
    def start_core() -> None:
        """Start the app without taking ownership of Uvicorn's SIGINT handler.

        Uvicorn receives Ctrl+C, initiates ASGI shutdown, and then this app's
        shutdown hook calls ``core.shutdown`` to force-stop and persist live
        attempts.  Replacing Uvicorn's handler here would consume Ctrl+C and
        leave the server running.
        """

    @app.on_event("shutdown")
    def stop_core() -> None:
        """Force-stop live attempts before the ASGI host exits."""
        core.shutdown()

    app.include_router(runs_router)
    app.include_router(sessions_router)
    app.include_router(providers_router)
    app.include_router(workspace_directory_router)
    app.include_router(settings_router)
    app.include_router(session_console_router)
    app.include_router(plugins_router)
    app.include_router(external_agent_hub_router)
    app.include_router(geoint_router)
    app.include_router(basemaps_router)
    app.mount("/static", StaticFiles(directory=frontend_root / "static"), name="static")


__all__ = ["include_api_routes"]
