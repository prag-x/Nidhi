from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from alembic import command
from app.db import Base

ROOT = Path(__file__).resolve().parents[1]


def test_migrations_match_models(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    monkeypatch.setenv("NIDHI_DATABASE_URL", url)
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "alembic"))
        command.upgrade(cfg, "head")
    finally:
        get_settings.cache_clear()
    engine = create_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"Models changed without a migration: {diff}"
