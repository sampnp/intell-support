import logging
import re

import pytest
from fastapi import APIRouter

GENERATED_ID = re.compile(r"[0-9a-f]{32}")


@pytest.fixture
def app(app):
    router = APIRouter(prefix="/test-request-id")

    @router.get("/crash")
    def crash():
        raise RuntimeError("boom")

    app.include_router(router)
    return app


def test_generates_request_id(client):
    response = client.get("/api/health")

    assert GENERATED_ID.fullmatch(response.headers["X-Request-ID"])


def test_echoes_valid_incoming_request_id(client):
    response = client.get("/api/health", headers={"X-Request-ID": "client-abc_123.4"})

    assert response.headers["X-Request-ID"] == "client-abc_123.4"


@pytest.mark.parametrize("bad_id", ["has spaces", "x" * 65, "semi;colon"])
def test_replaces_invalid_incoming_request_id(client, bad_id):
    response = client.get("/api/health", headers={"X-Request-ID": bad_id})

    assert GENERATED_ID.fullmatch(response.headers["X-Request-ID"])


def test_error_responses_carry_request_id(client):
    not_found = client.get("/api/nope")
    assert GENERATED_ID.fullmatch(not_found.headers["X-Request-ID"])

    crash = client.get("/test-request-id/crash", headers={"X-Request-ID": "crash-1"})
    assert crash.status_code == 500
    assert crash.headers["X-Request-ID"] == "crash-1"
    assert crash.json()["error"]["details"] == {"request_id": "crash-1"}


def test_log_records_carry_request_id(client, caplog):
    caplog.set_level(logging.INFO)

    client.get("/api/health", headers={"X-Request-ID": "log-check-1"})
    client.get("/test-request-id/crash", headers={"X-Request-ID": "log-check-2"})

    access = [r for r in caplog.records if r.name == "app.request"]
    assert any(
        r.request_id == "log-check-1" and "path=/api/health status=200" in r.getMessage()
        for r in access
    )
    crash_logs = [r for r in caplog.records if r.name == "app.errors"]
    assert crash_logs and crash_logs[0].request_id == "log-check-2"
    assert crash_logs[0].exc_info is not None
