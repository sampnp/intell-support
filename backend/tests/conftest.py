"""Shared fixtures. DB tests run against the `support_test` database, inside a transaction that
is rolled back after each test. Qdrant is replaced by the in-memory client."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db, make_engine
from app.main import create_app
from app.services.vector_store import get_qdrant_client

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def test_engine():
    url = get_settings().test_database_url
    db_name = make_url(url).database or ""
    if not db_name.endswith("_test"):
        pytest.exit(
            f"Refusing to run tests against database {db_name!r}: its name must end in '_test'.",
            returncode=1,
        )

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    # ConfigParser treats '%' as interpolation, and URL-escaped passwords can contain it.
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")

    engine = make_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    connection = test_engine.connect()
    transaction = connection.begin()
    # Commits inside the code under test only release a savepoint; everything is rolled back.
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def qdrant_client():
    client = QdrantClient(location=":memory:")
    yield client
    client.close()


@pytest.fixture
def app(db_session, qdrant_client):
    application = create_app()
    application.dependency_overrides[get_db] = lambda: db_session
    application.dependency_overrides[get_qdrant_client] = lambda: qdrant_client
    return application


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
