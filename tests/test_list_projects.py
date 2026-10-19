from fastapi.testclient import TestClient

from app.main import create_app


def test_list_projects() -> None:
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/projects")

        assert response.status_code == 200

        data = response.json()

        assert isinstance(data, list)

        for project in data:
            assert isinstance(project["id"], int)
            assert isinstance(project["name"], str)
            assert "created_at" in project
            assert "updated_at" in project
