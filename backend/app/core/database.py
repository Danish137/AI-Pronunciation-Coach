from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def normalize_database_url(database_url: str) -> str:
    if not database_url.startswith("sqlite"):
        return database_url

    url = make_url(database_url)
    raw_path = url.database
    if not raw_path or raw_path == ":memory:":
        return database_url

    # SQLite URLs like sqlite:///./backend/data/app.db arrive as ./backend/data/app.db
    # while some Windows parsing paths may have an extra leading slash. Normalize both.
    cleaned_path = raw_path.lstrip("/") if raw_path.startswith("/./") else raw_path
    db_path = Path(cleaned_path)
    if not db_path.is_absolute():
        db_path = (PROJECT_ROOT / db_path).resolve()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.as_posix()}"

normalized_database_url = normalize_database_url(settings.database_url)
connect_args = {"check_same_thread": False} if normalized_database_url.startswith("sqlite") else {}

engine = create_engine(normalized_database_url, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    from ..models.attempt import Attempt

    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("attempts")}
        if "provider_mode" not in columns:
            connection.execute(text("ALTER TABLE attempts ADD COLUMN provider_mode VARCHAR(16) DEFAULT 'mock'"))
        if "duration_seconds" not in columns:
            connection.execute(text("ALTER TABLE attempts ADD COLUMN duration_seconds FLOAT DEFAULT 0"))
        if "result_payload_json" not in columns:
            connection.execute(text("ALTER TABLE attempts ADD COLUMN result_payload_json TEXT DEFAULT ''"))
        if "raw_azure_json" not in columns:
            connection.execute(text("ALTER TABLE attempts ADD COLUMN raw_azure_json TEXT DEFAULT ''"))
        if "consent_accepted" not in columns:
            connection.execute(text("ALTER TABLE attempts ADD COLUMN consent_accepted BOOLEAN DEFAULT 0"))
        if "consent_recorded_at" not in columns:
            connection.execute(text("ALTER TABLE attempts ADD COLUMN consent_recorded_at DATETIME"))
