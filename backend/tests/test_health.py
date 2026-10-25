from app.db import get_db
from app.services.vector_store import get_qdrant_client


class FailingQdrant:
    def get_collections(self):
        raise ConnectionError("qdrant unreachable")


class FailingSession:
    def execute(self, *args, **kwargs):
        raise ConnectionError("database unreachable")


def test_health_all_ok(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "db": "ok",
        "qdrant": "ok",
        "embedder": "not_configured",
    }


def test_health_qdrant_down_is_degraded(app, client):
    app.dependency_overrides[get_qdrant_client] = lambda: FailingQdrant()

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["qdrant"] == "error"
    assert body["db"] == "ok"


def test_health_db_down_is_degraded(app, client):
    app.dependency_overrides[get_db] = lambda: FailingSession()

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db"] == "error"
    assert body["qdrant"] == "ok"
