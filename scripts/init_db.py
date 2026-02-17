#!/usr/bin/env python3
"""
Initialize the PostgreSQL database with tables and indexes
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger  # noqa: E402
from src.storage.postgres import PostgresClient  # noqa: E402
from src.storage.models import Base  # noqa: E402


def main():
    """Initialize database"""
    logger.info("Starting database initialization...")

    db = None
    try:
        # Create database client
        db = PostgresClient()

        # Create all tables
        logger.info("Creating tables...")
        db.create_tables()

        # Verify tables
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        logger.info(f"Created {len(tables)} tables:")
        for table in tables:
            logger.info(f"  ✓ {table}")

        logger.success("✓ Database initialized successfully!")

    except Exception as e:
        logger.error(f"✗ Database initialization failed: {e}")
        sys.exit(1)
    finally:
        if db:
            db.close()


if __name__ == "__main__":
    main()
