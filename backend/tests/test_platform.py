from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_platform_metadata_lists_octopus_as_planned_provider():
    response = client.get("/api/v1/platform")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Home Energy Intelligence"
    assert "octopus" in body["providers"]
    assert "platform_metadata" in body["capabilities"]
