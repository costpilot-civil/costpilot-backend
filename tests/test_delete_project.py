from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def test_delete_project() -> None:
    app = create_app()
    project_name = f"TEST_DELETE_{uuid4().hex}"

    with TestClient(app) as client:
        pool = app.state.db_pool

        try:
            # Create temporary project
            response = client.post(
                "/projects",
                json={"name": project_name},
            )

            assert response.status_code == 201
            project_id = response.json()["id"]

            # Delete project
            response = client.delete(f"/projects/{project_id}")

            assert response.status_code == 204
            assert response.content == b""

            # Verify project no longer exists
            response = client.get(f"/projects/{project_id}")

            assert response.status_code == 404

            # Verify repeated deletion
            response = client.delete(f"/projects/{project_id}")

            assert response.status_code == 404

        finally:
            # Clean up only data created by this test
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
