from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def test_update_project() -> None:
    app = create_app()
    project_name = f"TEST_PROJECT_{uuid4().hex}"
    project_id = None

    with TestClient(app) as client:
        pool = app.state.db_pool

        try:
            # Create temporary project
            response = client.post(
                "/projects",
                json={
                    "name": project_name,
                    "client": "Original Client",
                    "description": "Original Description",
                },
            )

            assert response.status_code == 201
            project_id = response.json()["id"]

            # Update selected fields
            response = client.patch(
                f"/projects/{project_id}",
                json={
                    "name": "Updated Test Project",
                    "description": None,
                },
            )

            assert response.status_code == 200

            data = response.json()

            assert data["id"] == project_id
            assert data["name"] == "Updated Test Project"
            assert data["description"] is None
            assert data["client"] == "Original Client"

            # Verify persistence
            response = client.get(f"/projects/{project_id}")

            assert response.status_code == 200
            assert response.json()["name"] == "Updated Test Project"
            assert response.json()["description"] is None

        finally:
            # Remove only the project created by this test
            if project_id is not None:
                with (
                    pool.connection() as conn,
                    conn.cursor() as cursor,
                ):
                    cursor.execute(
                        """
                        DELETE FROM projects
                        WHERE id = %s;
                        """,
                        (project_id,),
                    )
