from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def create_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    """Create sessions without connecting during application import."""
    url = database_url or get_settings().postgres_dsn
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    if url.startswith("sqlite"):
        from app.database.base import Base
        import app.database.models  # noqa: F401
        Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
