import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from sqlalchemy.pool import StaticPool

from app.database.base import Base
import app.database.models  # noqa: F401 - registers model metadata


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:  # type: ignore[no-untyped-def]
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
