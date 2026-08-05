"""Apply pending Alembic migrations programmatically.

Used at API startup and by scripts/init_db.py so local/dev environments
always end up on the schema the code expects, instead of relying on
SQLAlchemy's create_all() (which never alters existing tables).
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from loguru import logger

from src.config.settings import settings

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def upgrade_to_head() -> None:
    """Run `alembic upgrade head` against the configured database."""
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", str(settings.database_url))
    logger.info("Applying database migrations (alembic upgrade head)...")
    command.upgrade(config, "head")
    logger.info("Database schema is up to date")
