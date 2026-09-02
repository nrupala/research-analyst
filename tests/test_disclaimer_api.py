from fastapi.testclient import TestClient
from research_analyst.server import app

client = TestClient(app)

def test_disclaimer_endpoint():
    response = client.get("/api/disclaimer")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["version"], str) and len(data["version"]) > 0
    assert "informational purposes only" in data["full"]

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "research-analyst"
    assert len(data["version"]) > 0  # matches the release tag (VERSIONING.md)