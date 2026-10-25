"""Database engine, session factory and the `get_db` FastAPI dependency (sync SQLAlchemy 2.0)."""

from collections.abc import Iterator

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

# Stable constraint names so Alembic autogenerate produces predictable migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def make_engine(url: str, **kwargs) -> Engine:
    # Sessions run in UTC so timestamptz values round-trip consistently.
    return create_engine(
        url, pool_pre_ping=True, connect_args={"options": "-c timezone=utc"}, **kwargs
    )


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
