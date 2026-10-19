from psycopg import sql
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

    def list_projects(self) -> list[Project]:
        with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=class_row(Project)) as cursor,
        ):
            cursor.execute(
                """
                SELECT
                    id,
                    name,
                    project_number,
                    client,
                    location,
                    description,
                    created_at,
                    updated_at
                FROM projects
                ORDER BY created_at DESC, id DESC;
                """
            )

            return cursor.fetchall()

    def get_project(self, project_id: int) -> Project | None:
        with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=class_row(Project)) as cursor,
        ):
            cursor.execute(
                """
                SELECT
                    id,
                    name,
                    project_number,
                    client,
                    location,
                    description,
                    created_at,
                    updated_at
                FROM projects
                WHERE id = %s;
                """,
                (project_id,),
            )

            return cursor.fetchone()

    def update_project(
        self,
        project_id: int,
        changes: dict[str, str | None],
    ) -> Project | None:
        allowed_fields = {
            "name",
            "project_number",
            "client",
            "location",
            "description",
        }

        if not changes or not changes.keys() <= allowed_fields:
            raise ValueError("Invalid project update fields.")

        assignments = sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(field)) for field in changes
        )

        query = sql.SQL(
            """
            UPDATE projects
            SET {}
            WHERE id = %s
            RETURNING
                id,
                name,
                project_number,
                client,
                location,
                description,
                created_at,
                updated_at;
            """
        ).format(assignments)

        params = (*changes.values(), project_id)

        with (
            self._pool.connection() as conn,
            conn.cursor(row_factory=class_row(Project)) as cursor,
        ):
            cursor.execute(query, params)
            return cursor.fetchone()

    def delete_project(self, project_id: int) -> bool:
        with (
            self._pool.connection() as conn,
            conn.cursor() as cursor,
        ):
            cursor.execute(
                """
                DELETE FROM projects
                WHERE id = %s
                RETURNING id;
                """,
                (project_id,),
            )

            return cursor.fetchone() is not None
