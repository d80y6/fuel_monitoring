from fastapi.testclient import TestClient


def test_api_starts_and_serves_health():
    from fmp.api.main import app

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api"}
