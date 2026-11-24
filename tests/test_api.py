from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_home_page_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "Science Diagram Maker" in response.text


def test_results_endpoint_returns_five_complete_results():
    data = client.get("/api/results").json()["results"]
    assert len(data) == 5
    for item in data:
        for field in ("concept_name", "svg", "checks", "cost_usd", "retries", "tokens", "model"):
            assert field in item
        assert len(item["checks"]) == 5