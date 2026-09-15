"""Database connection configuration for SQLite and SQL Server deployments."""
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJE_KOKU = os.path.dirname(BACKEND_DIR)
DB_KLASORU = os.path.join(PROJE_KOKU, "veritabani")
os.makedirs(DB_KLASORU, exist_ok=True)
DB_YOLU = os.path.join(DB_KLASORU, "pts.db")
CONFIG_YOLU = os.path.join(BACKEND_DIR, "database_config.json")


def _veritabani_urlini_oku() -> str:
    """Prefer environment configuration, then installer config, then SQLite."""
    url = os.getenv("PTS_DATABASE_URL")
    if url:
        return url
    if os.path.exists(CONFIG_YOLU):
        try:
            with open(CONFIG_YOLU, "r", encoding="utf-8") as dosya:
                url = json.load(dosya).get("database_url")
                if url:
                    return url
        except (OSError, json.JSONDecodeError):
            pass
    return f"sqlite:///{DB_YOLU}"

SQLALCHEMY_DATABASE_URL = _veritabani_urlini_oku()
engine_kwargs = {}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
