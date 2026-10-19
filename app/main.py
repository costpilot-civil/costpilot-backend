from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.projects import router as projects_router
from app.api.routes.tenders import router as tenders_router
from app.infrastructure.config import Settings
from app.infrastructure.database import create_db_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = Settings()  # pyright: ignore[reportCallIssue]
    pool = create_db_pool(settings)
    try:
        pool.open(wait=True)
        app.state.settings = settings
        app.state.db_pool = pool
        yield
    finally:
        pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title="CostPilot Backend", version="0.1.0", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(projects_router)
    app.include_router(tenders_router)
    return app


app = create_app()
