from psycopg.rows import class_row
from psycopg_pool import ConnectionPool

from app.domain.project import Project


class ProjectRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def create_project(
        self,
        *,
        name: str,
        project_number: str | None = None,
        client: str | None = None,
        location: str | None = None,
        description: str | None = None,
    ) -> Project:
        with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=class_row(Project)) as cursor,
        ):
            cursor.execute(
                """
                    INSERT INTO projects (
                        name,
                        project_number,
                        client,
                        location,
                        description
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING
                        id,
                        name,
                        project_number,
                        client,
                        location,
                        description,
                        created_at,
                        updated_at;
                    """,
                (
                    name,
                    project_number,
                    client,
                    location,
                    description,
                ),
            )

            project = cursor.fetchone()

            if project is None:
                raise RuntimeError("Failed to create project.")

            return project
