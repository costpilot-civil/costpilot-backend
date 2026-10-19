from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def test_get_project() -> None:
    app = create_app()
    project_name = f"TEST_PROJECT_{uuid4().hex}"

    with TestClient(app) as client:
        pool = app.state.db_pool
        project_id = None

        try:
            # Create a temporary project
            response = client.post(
                "/projects",
                json={
                    "name": project_name,
                    "project_number": "TEST-002",
                },
            )

            assert response.status_code == 201
            project_id = response.json()["id"]

            # Retrieve the project
            response = client.get(f"/projects/{project_id}")

            assert response.status_code == 200

            data = response.json()

            assert data["id"] == project_id
            assert data["name"] == project_name
            assert data["project_number"] == "TEST-002"

        finally:
            # Clean up only this test's project
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

        # Verify that the deleted project is not found
        if project_id is not None:
            response = client.get(f"/projects/{project_id}")

            assert response.status_code == 404
            assert response.json()["detail"] == "Project not found."
