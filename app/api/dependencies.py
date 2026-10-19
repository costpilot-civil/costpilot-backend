from fastapi import Request

from app.application.project_service import ProjectService
from app.persistence.project_repository import ProjectRepository


def get_project_service(request: Request) -> ProjectService:
    pool = request.app.state.db_pool

    repository = ProjectRepository(pool)
    return ProjectService(repository)
