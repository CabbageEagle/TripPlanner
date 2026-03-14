from collections.abc import Generator

from pgvector.psycopg import register_vector
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings


settings = get_settings()

engine = create_engine(
    settings.database_url,
    echo=settings.database_echo,
    future=True,
)


@event.listens_for(engine, "connect")
def register_pgvector(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
    del connection_record
    register_vector(dbapi_connection)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for a request-scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
