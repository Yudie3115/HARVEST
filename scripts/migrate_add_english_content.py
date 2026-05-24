#!/usr/bin/env python3
"""
Migration: add english_content TEXT column to chat_messages.

Stores the English version of assistant replies so multi-turn LLM history is
sent in English regardless of the user's language, reducing token count for
non-Latin scripts.

Safe to run multiple times — uses ADD COLUMN IF NOT EXISTS.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import text
from src.storage.postgres import PostgresClient


def main():
    db = PostgresClient()
    try:
        with db.get_session() as session:
            session.execute(text("""
                ALTER TABLE chat_messages
                ADD COLUMN IF NOT EXISTS english_content TEXT
            """))
            session.commit()
        logger.success("✓ Added english_content column to chat_messages")
    except Exception as exc:
        logger.error(f"Migration failed: {exc}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
