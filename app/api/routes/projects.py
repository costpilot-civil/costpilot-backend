from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_project_service
from app.api.schemas.project import ProjectCreate, ProjectResponse
from app.application.project_service import ProjectService
from app.domain.project import Project

router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
)


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    data: ProjectCreate,
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> Project:
    return service.create_project(
        name=data.name,
        project_number=data.project_number,
        client=data.client,
        location=data.location,
        description=data.description,
    )
