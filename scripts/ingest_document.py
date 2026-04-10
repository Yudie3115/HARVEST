"""
CLI for manually ingesting a single document into the knowledge base.

Usage examples:
  python -m scripts.ingest_document --file report.pdf
  python -m scripts.ingest_document --file report.pdf --title "Maize Storage Guide" --site fao
  python -m scripts.ingest_document --url https://example.org/guide.pdf
  python -m scripts.ingest_document --url https://example.org/guide.pdf --site naro

Exit codes:
  0  Document processed successfully
  1  Document skipped (low relevance or no content) or ingestion failed
"""
import argparse
import sys
from pathlib import Path


def main(argv: list = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manually add a document to the post-harvest knowledge base."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--file",
        metavar="PATH",
        help="Path to a local file (PDF, DOCX, HTML).",
    )
    source.add_argument(
        "--url",
        metavar="URL",
        help="URL of a remote document to download and ingest.",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Human-readable title (optional; defaults to filename or URL).",
    )
    parser.add_argument(
        "--site",
        default="manual",
        metavar="SITE_NAME",
        help="Source/site label stored in the DB (default: 'manual').",
    )

    args = parser.parse_args(argv)

    from src.flows.manual_ingestion import ingest_manual_document

    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"Error: file not found: {args.file}", file=sys.stderr)
            return 1
        content = file_path.read_bytes()
        result = ingest_manual_document(
            content=content,
            filename=file_path.name,
            title=args.title,
            site_name=args.site,
        )
    else:
        result = ingest_manual_document(
            url=args.url,
            title=args.title,
            site_name=args.site,
        )

    status = result.get("status")
    if status == "processed":
        score = result.get("relevance_score")
        score_str = f"{score:.1f}" if isinstance(score, (int, float)) else "N/A"
        print(
            f"✓ Processed  |  "
            f"chunks={result['chunks']}  "
            f"relevance={score_str}  "
            f"id={result['document_id']}"
        )
        return 0
    elif status == "skipped":
        reason = result.get("reason", "unknown")
        score = result.get("relevance_score")
        score_str = f"  relevance={score:.1f}" if score is not None else ""
        print(f"⚠ Skipped ({reason}){score_str}", file=sys.stderr)
        return 1
    else:
        print(f"✗ Failed — check logs for details.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
