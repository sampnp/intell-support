"""Shared fixtures. DB tests run against the `support_test` database, inside a transaction that
is rolled back after each test. Qdrant is replaced by the in-memory client."""

from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import security
from app.core.security import create_access_token, hash_password
from app.db import get_db, make_engine
from app.main import create_app
from app.models.ticket import Ticket
from app.models.user import Role, User
from app.schemas.tickets import TicketCreate
from app.services import tickets as ticket_service
from app.services.ingestion import get_session_factory
from app.services.vector_store import get_qdrant_client

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Every user created by `make_user` has this password.
DEFAULT_PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def fast_bcrypt(monkeypatch):
    # The production work factor (12) would make the suite slow.
    monkeypatch.setattr(security, "BCRYPT_ROUNDS", 4)


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

    @contextmanager
    def test_session():
        # Background work (ingestion) uses the test session too, and must not close it.
        yield db_session

    application.dependency_overrides[get_db] = lambda: db_session
    application.dependency_overrides[get_qdrant_client] = lambda: qdrant_client
    application.dependency_overrides[get_session_factory] = lambda: test_session
    return application


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def make_user(db_session):
    """Factory: insert a user (role `user` by default) with DEFAULT_PASSWORD."""
    counter = 0

    def _make_user(
        *,
        role: Role = Role.user,
        email: str | None = None,
        full_name: str = "Test User",
        password: str = DEFAULT_PASSWORD,
    ) -> User:
        nonlocal counter
        counter += 1
        user = User(
            email=email or f"{role}{counter}@example.com",
            full_name=full_name,
            password_hash=hash_password(password),
            role=role,
        )
        db_session.add(user)
        db_session.flush()
        return user

    return _make_user


@pytest.fixture
def user(make_user):
    return make_user(role=Role.user, full_name="Regular User")


@pytest.fixture
def agent(make_user):
    return make_user(role=Role.agent, full_name="Support Agent")


@pytest.fixture
def make_ticket(db_session):
    """Factory: create a ticket through the service (so it has its `created` event).

    Extra keyword fields (e.g. status, assigned_to) are set directly afterwards."""

    def _make_ticket(
        owner: User,
        *,
        title: str = "Cannot sync my files",
        description: str = "The desktop app has been stuck on 'syncing' since this morning.",
        category: str = "sync",
        priority: str = "medium",
        **fields,
    ) -> Ticket:
        data = TicketCreate(
            title=title, description=description, category=category, priority=priority
        )
        ticket = ticket_service.create_ticket(db_session, owner, data)
        for name, value in fields.items():
            setattr(ticket, name, value)
        db_session.flush()
        return ticket

    return _make_ticket


@pytest.fixture
def auth_headers():
    """Return the Authorization header for a user."""

    def _auth_headers(for_user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(for_user.id)}"}

    return _auth_headers


@pytest.fixture(scope="session")
def sample_kb() -> Path:
    """The Acme Cloud sample KB, mounted into the container by docker-compose.yml."""
    path = Path(get_settings().sample_kb_dir)
    if not (path / "malformed").is_dir():
        pytest.fail(f"Sample KB not found at {path}; is ./sample_kb mounted (docker-compose.yml)?")
    return path


@pytest.fixture
def upload(client, auth_headers):
    """POST a file to /api/kb/documents. `source` is a Path or a (filename, bytes) pair.

    Background processing has finished by the time this returns (TestClient runs it)."""

    def _upload(as_user: User, source, *, title: str | None = None):
        if isinstance(source, Path):
            filename, data = source.name, source.read_bytes()
        else:
            filename, data = source
        return client.post(
            "/api/kb/documents",
            files={"file": (filename, data)},
            data={"title": title} if title is not None else None,
            headers=auth_headers(as_user),
        )

    return _upload
