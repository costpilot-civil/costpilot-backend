from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def test_create_project() -> None:
    project_name = f"TEST_PROJECT_{uuid4().hex}"

    app = create_app()

    with TestClient(app) as client:
        pool = app.state.db_pool

        try:
            # Create project through API
            response = client.post(
                "/projects",
                json={
                    "name": project_name,
                    "project_number": "TEST-001",
                    "client": "Test Client",
                    "location": "Frankfurt",
                    "description": "Integration test project",
                },
            )

            # Validate API response
            assert response.status_code == 201

            data = response.json()

            assert data["id"] > 0
            assert data["name"] == project_name
            assert data["project_number"] == "TEST-001"
            assert data["client"] == "Test Client"

            # Verify database persistence
            with (
                pool.connection() as conn,
                conn.cursor() as cursor,
            ):
                cursor.execute(
                    """
                    SELECT id, name
                    FROM projects
                    WHERE id = %s;
                    """,
                    (data["id"],),
                )

                row = cursor.fetchone()

            assert row is not None
            assert row[0] == data["id"]
            assert row[1] == project_name

        finally:
            # Remove only the project created by this test
            with (
                pool.connection() as conn,
                conn.cursor() as cursor,
            ):
                cursor.execute(
                    """
                    DELETE FROM projects
                    WHERE name = %s;
                    """,
                    (project_name,),
                )
