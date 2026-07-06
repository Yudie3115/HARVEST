"""
CLI for manually ingesting documents into the knowledge base.

Usage examples:
  python -m scripts.ingest_document --file report.pdf
  python -m scripts.ingest_document --file report.pdf --title "Maize Storage Guide" --site fao
  python -m scripts.ingest_document --url https://example.org/guide.pdf
  python -m scripts.ingest_document --url https://example.org/guide.pdf --site naro
  python -m scripts.ingest_document --dir ./guides --site fao
  python -m scripts.ingest_document --dir ./guides --recursive --site fao

Exit codes:
  0  Document(s) processed successfully (skips are allowed in --dir mode)
  1  Document skipped (low relevance or no content) or ingestion failed;
     in --dir mode: at least one file hard-failed or no matching files were found
"""
import argparse
import sys
from pathlib import Path

# Extensions the manual pipeline can extract (matches the dashboard dropzone).
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".html", ".htm"}


def _print_result(result: dict, *, prefix: str = "") -> str:
    """Print a one-line summary for a single ingestion result.

    Returns the result's status string ("processed" | "skipped" | "failed").
    """
    status = result.get("status")
    if status == "processed":
        score = result.get("relevance_score")
        score_str = f"{score:.1f}" if isinstance(score, (int, float)) else "N/A"
        print(
            f"{prefix}✓ Processed  |  "
            f"chunks={result['chunks']}  "
            f"relevance={score_str}  "
            f"id={result['document_id']}"
        )
    elif status == "skipped":
        reason = result.get("reason", "unknown")
        score = result.get("relevance_score")
        score_str = f"  relevance={score:.1f}" if score is not None else ""
        print(f"{prefix}⚠ Skipped ({reason}){score_str}", file=sys.stderr)
    else:
        print(f"{prefix}✗ Failed — check logs for details.", file=sys.stderr)
    return status


def _ingest_directory(directory: Path, *, site_name: str, recursive: bool) -> int:
    """Ingest every supported file in a directory. Returns a process exit code."""
    from src.flows.manual_ingestion import ingest_manual_document

    globber = directory.rglob if recursive else directory.glob
    all_files = sorted(p for p in globber("*") if p.is_file())
    matching = [p for p in all_files if p.suffix.lower() in SUPPORTED_EXTENSIONS]
    ignored = len(all_files) - len(matching)

    if not matching:
        print(
            f"Error: no supported files ({', '.join(sorted(SUPPORTED_EXTENSIONS))}) "
            f"found in {directory}",
            file=sys.stderr,
        )
        return 1

    counts = {"processed": 0, "skipped": 0, "failed": 0}
    for file_path in matching:
        content = file_path.read_bytes()
        result = ingest_manual_document(
            content=content,
            filename=file_path.name,
            title=None,
            site_name=site_name,
        )
        status = _print_result(result, prefix=f"{file_path.name}: ")
        counts[status if status in counts else "failed"] += 1

    print(
        f"Summary: {counts['processed']} processed, {counts['skipped']} skipped, "
        f"{counts['failed']} failed ({ignored} ignored, non-matching)"
    )
    # Skips are expected outcomes for a bulk import; only hard failures fail the run.
    return 1 if counts["failed"] else 0


def main(argv: list = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manually add document(s) to the post-harvest knowledge base."
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
    source.add_argument(
        "--dir",
        metavar="PATH",
        help="Path to a folder; every supported file inside is ingested.",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Human-readable title (optional; defaults to filename or URL). "
        "Not allowed with --dir, where each file is titled by its filename.",
    )
    parser.add_argument(
        "--site",
        default="manual",
        metavar="SITE_NAME",
        help="Source/site label stored in the DB (default: 'manual').",
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="With --dir, descend into subfolders (default: top-level only).",
    )

    args = parser.parse_args(argv)

    if args.title and args.dir:
        parser.error("--title cannot be used with --dir (each file is titled by its filename)")

    if args.dir:
        dir_path = Path(args.dir)
        if not dir_path.is_dir():
            print(f"Error: directory not found: {args.dir}", file=sys.stderr)
            return 1
        return _ingest_directory(
            dir_path, site_name=args.site, recursive=args.recursive
        )

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

    status = _print_result(result)
    return 0 if status == "processed" else 1


if __name__ == "__main__":
    sys.exit(main())
