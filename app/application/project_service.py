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

    def list_projects(self) -> list[Project]:
        return self._repository.list_projects()

    def get_project(self, project_id: int) -> Project | None:
        return self._repository.get_project(project_id)

    def update_project(
        self,
        project_id: int,
        changes: dict[str, str | None],
    ) -> Project | None:
        if not changes:
            raise ValueError("No fields provided for update.")

        changes = changes.copy()

        if "name" in changes:
            name = changes["name"]

            if name is None or not name.strip():
                raise ValueError("Project name must not be empty.")

            changes["name"] = name.strip()

        return self._repository.update_project(
            project_id=project_id,
            changes=changes,
        )

    def delete_project(self, project_id: int) -> bool:
        return self._repository.delete_project(project_id)
