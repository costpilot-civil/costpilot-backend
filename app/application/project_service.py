from app.domain.project import Project
from app.persistence.project_repository import ProjectRepository


class ProjectService:
    def __init__(self, repository: ProjectRepository) -> None:
        self._repository = repository

    def create_project(
        self,
        *,
        name: str,
        project_number: str | None = None,
        client: str | None = None,
        location: str | None = None,
        description: str | None = None,
    ) -> Project:
        name = name.strip()

        if not name:
            raise ValueError("Project name must not be empty.")

        return self._repository.create_project(
            name=name,
            project_number=project_number,
            client=client,
            location=location,
            description=description,
        )
