"""
Re-score existing documents under the current classification rules.

Use after changing the scoring prompt or topic list so old and new scores mean
the same thing.

- PROCESSED documents are re-classified from their stored chunk text. Their
  classification, chunk topics/crops/regions and admin relevance score are
  updated. Nothing is re-downloaded or re-embedded.
- SKIPPED documents that were rejected for low relevance are fully re-ingested
  (file from MinIO, or the original URL), so ones that now pass the threshold
  are chunked and become available to the chatbot.

Usage:
  python -m scripts.rescore_documents --dry-run
  python -m scripts.rescore_documents
  python -m scripts.rescore_documents --only processed --limit 10
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger  # noqa: E402

from src.config.settings import settings  # noqa: E402
from src.storage.models import (  # noqa: E402
    ContentChunk,
    Document,
    DocumentClassification,
    DocumentStatus,
)
from src.storage.postgres import PostgresClient  # noqa: E402

# Matches LLMClient.classify_content's default excerpt length.
_EXCERPT_CHARS = 4000


def _processed_documents(db: PostgresClient, limit: int | None) -> list[tuple[str, str]]:
    with db.get_session() as session:
        query = (
            session.query(Document.id, Document.url)
            .filter(Document.status == DocumentStatus.PROCESSED)
            .order_by(Document.discovered_at)
        )
        if limit:
            query = query.limit(limit)
        return [(str(doc_id), url) for doc_id, url in query.all()]


def _low_relevance_skipped(db: PostgresClient, limit: int | None) -> list[Document]:
    with db.get_session() as session:
        query = (
            session.query(Document)
            .join(DocumentClassification, DocumentClassification.document_id == Document.id)
            .filter(
                Document.status == DocumentStatus.SKIPPED,
                DocumentClassification.relevance_score < settings.relevance_threshold,
            )
            .order_by(Document.discovered_at)
        )
        if limit:
            query = query.limit(limit)
        docs = query.all()
        session.expunge_all()
        return docs


def _chunk_text(db: PostgresClient, document_id: str) -> str:
    with db.get_session() as session:
        rows = (
            session.query(ContentChunk.text)
            .filter(ContentChunk.document_id == document_id)
            .order_by(ContentChunk.chunk_index)
            .all()
        )
    text = ""
    for (chunk,) in rows:
        if len(text) >= _EXCERPT_CHARS:
            break
        text += chunk + "\n"
    return text


def rescore_processed(db: PostgresClient, document_id: str, url: str) -> float | None:
    from uuid import UUID

    from src.flows.processing import classify_document_content

    text = _chunk_text(db, document_id)
    if not text:
        logger.warning(f"{document_id}: no stored chunk text, skipping")
        return None

    classification = classify_document_content(text, url=url)
    score = classification.get("relevance_score", 0)
    doc_uuid = UUID(document_id)

    db.create_classification(doc_uuid, classification)
    db.update_document_metadata(
        doc_uuid, {"llm_classification": classification, "relevance_score": score}
    )
    with db.get_session() as session:
        session.query(ContentChunk).filter(ContentChunk.document_id == doc_uuid).update(
            {
                ContentChunk.topics: classification.get("topics", []),
                ContentChunk.crops: classification.get("crops", []),
                ContentChunk.regions: classification.get("regions", []),
            },
            synchronize_session=False,
        )
        session.commit()
    return score


def reingest_skipped(doc: Document) -> dict:
    from src.flows.manual_ingestion import ingest_manual_document
    from src.storage.minio_client import MinIOClient

    common = {"title": doc.title, "site_name": doc.site_name, "document_id": str(doc.id)}
    if doc.url.startswith("upload://"):
        # upload://<doc_uuid>/<filename> — reuse both so the same row is updated.
        doc_uuid, _, filename = doc.url.removeprefix("upload://").partition("/")
        content = MinIOClient().get_object(doc.file_path)
        return ingest_manual_document(
            content=content, filename=filename, doc_uuid=doc_uuid, **common
        )
    return ingest_manual_document(url=doc.url, **common)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--only",
        choices=["processed", "skipped"],
        help="Limit to one group (default: both)",
    )
    parser.add_argument("--limit", type=int, help="Maximum documents per group")
    parser.add_argument(
        "--dry-run", action="store_true", help="List what would be re-scored, change nothing"
    )
    args = parser.parse_args()

    db = PostgresClient()
    processed = [] if args.only == "skipped" else _processed_documents(db, args.limit)
    skipped = [] if args.only == "processed" else _low_relevance_skipped(db, args.limit)

    print(f"Processed documents to re-score:        {len(processed)}")
    print(f"Low-relevance skipped to re-ingest:     {len(skipped)}")
    if args.dry_run:
        for doc in skipped:
            print(f"  skipped: {doc.title or doc.url}")
        return 0

    rescored = failed = 0
    for i, (document_id, url) in enumerate(processed, 1):
        try:
            score = rescore_processed(db, document_id, url)
        except Exception as exc:
            logger.error(f"{document_id}: re-score failed: {exc}")
            failed += 1
            continue
        if score is not None:
            rescored += 1
            print(f"[{i}/{len(processed)}] {score:>4.1f}  {url}")

    now_processed = 0
    for i, doc in enumerate(skipped, 1):
        try:
            result = reingest_skipped(doc)
        except Exception as exc:
            logger.error(f"{doc.id}: re-ingest failed: {exc}")
            failed += 1
            continue
        if result.get("status") == "processed":
            now_processed += 1
        print(
            f"[{i}/{len(skipped)}] {result.get('status'):<9} "
            f"{result.get('relevance_score', '-')}  {doc.title or doc.url}"
        )

    print(
        f"\nRe-scored {rescored} processed documents; "
        f"{now_processed}/{len(skipped)} previously rejected documents now accepted; "
        f"{failed} errors."
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
