"""Merged example; preserve your actual application's other routers."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.matching import router as matching_router
from app.api.routes.projects import router as projects_router
from app.api.routes.tenders import router as tenders_router
from app.infrastructure.config import Settings
from app.infrastructure.database import create_db_pool
from app.infrastructure.material_runtime import build_material_extractor


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = Settings()  # pyright: ignore[reportCallIssue]
    material_extractor = build_material_extractor()
    pool = create_db_pool(settings)
    try:
        pool.open(wait=True)
        app.state.settings = settings
        app.state.db_pool = pool
        app.state.material_extractor = material_extractor
        yield
    finally:
        pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title="CostPilot Backend", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:1420",
            "http://127.0.0.1:1420",
        ],
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health_router)
    app.include_router(projects_router)
    app.include_router(tenders_router)
    app.include_router(matching_router)
    return app


app = create_app()
