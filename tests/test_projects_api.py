"""Integration tests for Project CRUD APIs.

These tests use the configured PostgreSQL database. Every project created by
this module is removed, including when an assertion fails.
"""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from app.main import create_app


@pytest.fixture(scope="module")
def api() -> Iterator[tuple[TestClient, ConnectionPool]]:
    app = create_app()

    with TestClient(app) as client:
        yield client, app.state.db_pool


def _cleanup_project(
    pool: ConnectionPool,
    *,
    project_id: int | None,
    original_name: str,
) -> None:
    """Delete only the uniquely named project created by this test.

    The ID also handles cases where the test has changed the project name.
    """
    with pool.connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "DELETE FROM projects WHERE id = %s OR name = %s;",
            (project_id, original_name),
        )


def test_create_project(api: tuple[TestClient, ConnectionPool]) -> None:
    client, pool = api
    project_name = f"TEST_PROJECT_{uuid4().hex}"
    project_id: int | None = None

    try:
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
        assert response.status_code == 201

        data = response.json()
        project_id = data["id"]
        assert project_id
        assert project_id > 0
        assert data["name"] == project_name
        assert data["project_number"] == "TEST-001"
        assert data["client"] == "Test Client"

        # Verify that the API persisted the project in PostgreSQL.
        with pool.connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, name FROM projects WHERE id = %s;",
                (project_id,),
            )
            row = cursor.fetchone()

        assert row is not None
        assert row[0] == project_id
        assert row[1] == project_name
    finally:
        _cleanup_project(pool, project_id=project_id, original_name=project_name)


def test_get_project(api: tuple[TestClient, ConnectionPool]) -> None:
    client, pool = api
    project_name = f"TEST_PROJECT_{uuid4().hex}"
    project_id: int | None = None

    try:
        response = client.post(
            "/projects",
            json={"name": project_name, "project_number": "TEST-002"},
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        response = client.get(f"/projects/{project_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == project_id
        assert data["name"] == project_name
        assert data["project_number"] == "TEST-002"
    finally:
        _cleanup_project(pool, project_id=project_id, original_name=project_name)

    # Confirm that the cleanup actually removed the test project.
    assert client.get(f"/projects/{project_id}").status_code == 404


def test_list_projects(api: tuple[TestClient, ConnectionPool]) -> None:
    client, _ = api

    response = client.get("/projects")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)

    for project in data:
        assert isinstance(project["id"], int)
        assert isinstance(project["name"], str)
        assert "created_at" in project
        assert "updated_at" in project


def test_update_project(api: tuple[TestClient, ConnectionPool]) -> None:
    client, pool = api
    project_name = f"TEST_PROJECT_{uuid4().hex}"
    project_id: int | None = None

    try:
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

        response = client.get(f"/projects/{project_id}")
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Test Project"
        assert response.json()["description"] is None
    finally:
        _cleanup_project(pool, project_id=project_id, original_name=project_name)


def test_delete_project(api: tuple[TestClient, ConnectionPool]) -> None:
    client, pool = api
    project_name = f"TEST_DELETE_{uuid4().hex}"
    project_id: int | None = None

    try:
        response = client.post("/projects", json={"name": project_name})
        assert response.status_code == 201
        project_id = response.json()["id"]

        response = client.delete(f"/projects/{project_id}")
        assert response.status_code == 204
        assert response.content == b""

        response = client.get(f"/projects/{project_id}")
        assert response.status_code == 404

        response = client.delete(f"/projects/{project_id}")
        assert response.status_code == 404
    finally:
        _cleanup_project(pool, project_id=project_id, original_name=project_name)
