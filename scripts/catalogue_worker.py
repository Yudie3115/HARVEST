#!/usr/bin/env python3
"""Run the lightweight database-backed catalogue worker."""
import argparse
import time

from loguru import logger

from src.api.services.catalogue_service import claim_next_job, run_claimed_job
from src.config.settings import settings
from src.llm.client import LLMClient
from src.llm.embeddings import EmbeddingClient
from src.storage.postgres import PostgresClient
from src.storage.vector_db import VectorDBClient
from src.translation.client import TranslationClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()

    postgres = PostgresClient()
    llm = LLMClient()
    embeddings = EmbeddingClient()
    translations = TranslationClient()
    vectors = VectorDBClient(collection=settings.catalogue_collection_name)
    vectors.ensure_collection()
    logger.info("Catalogue worker ready")

    try:
        while True:
            with postgres.get_session() as db:
                job = claim_next_job(db)
                if job:
                    run_claimed_job(
                        db,
                        job,
                        llm_client=llm,
                        embedding_client=embeddings,
                        translation_client=translations,
                        catalogue_vector_client=vectors,
                    )
            if args.once:
                break
            if not job:
                time.sleep(args.poll_seconds)
    finally:
        postgres.close()


if __name__ == "__main__":
    main()
