from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.api.dependencies import get_project_service
from app.api.schemas.project import (
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
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


@router.get(
    "",
    response_model=list[ProjectResponse],
)
def list_projects(
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> list[Project]:
    return service.list_projects()


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
)
def get_project(
    project_id: Annotated[int, Path(gt=0)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> Project:
    project = service.get_project(project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    return project


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
)
def update_project(
    project_id: Annotated[int, Path(gt=0)],
    data: ProjectUpdate,
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> Project:
    changes = data.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=422,
            detail="No fields provided for update.",
        )

    project = service.update_project(
        project_id=project_id,
        changes=changes,
    )

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    return project


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_project(
    project_id: Annotated[int, Path(gt=0)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> None:
    deleted = service.delete_project(project_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )
