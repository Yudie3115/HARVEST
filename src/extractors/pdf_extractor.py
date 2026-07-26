"""
PDF content extraction using PyMuPDF (text) and pdfplumber (tables)
"""
from pathlib import Path
from typing import Optional, List, Dict, Union
from loguru import logger


def extract_pdf_text(file_path: Union[str, Path]) -> Optional[str]:
    """
    Extract plain text from a PDF using PyMuPDF (fitz).

    Handles:
    - Standard text PDFs
    - Basic layout recovery (reading order)

    Args:
        file_path: Path to the PDF file

    Returns:
        Extracted text, or None on failure
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(file_path))
        pages_text: List[str] = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            # "text" mode preserves reading order better than default
            text = page.get_text("text")
            if text.strip():
                pages_text.append(text.strip())

        page_count = len(doc)
        doc.close()
        full_text = "\n\n".join(pages_text)
        logger.debug(
            f"PyMuPDF extracted {len(full_text)} chars from {file_path} " f"({page_count} pages)"
        )
        return full_text if full_text.strip() else None

    except Exception as e:
        logger.error(f"PDF text extraction failed for {file_path}: {e}")
        return None


def extract_pdf_tables(file_path: Union[str, Path]) -> List[List[List[str]]]:
    """
    Extract tables from a PDF using pdfplumber.

    Args:
        file_path: Path to the PDF file

    Returns:
        List of tables, where each table is a list of rows,
        and each row is a list of cell strings.
    """
    try:
        import pdfplumber

        tables: List[List[List[str]]] = []
        with pdfplumber.open(str(file_path)) as pdf:
            for page in pdf.pages:
                page_tables = page.extract_tables()
                for table in page_tables:
                    # Normalise None cells to empty string
                    clean_table = [[cell or "" for cell in row] for row in table]
                    tables.append(clean_table)

        logger.debug(f"pdfplumber extracted {len(tables)} tables from {file_path}")
        return tables

    except Exception as e:
        logger.warning(f"PDF table extraction failed for {file_path}: {e}")
        return []


def tables_to_text(tables: List[List[List[str]]]) -> str:
    """
    Convert extracted tables to a plain-text markdown representation

    Args:
        tables: Nested list output from extract_pdf_tables

    Returns:
        Markdown string
    """
    parts: List[str] = []
    for table in tables:
        if not table:
            continue
        rows = []
        for i, row in enumerate(table):
            row_str = " | ".join(row)
            rows.append(f"| {row_str} |")
            if i == 0:
                # Header separator
                rows.append("|" + "|".join(["---"] * len(row)) + "|")
        parts.append("\n".join(rows))
    return "\n\n".join(parts)


def extract_pdf_metadata(file_path: Union[str, Path]) -> Dict:
    """
    Extract document-level metadata from a PDF

    Args:
        file_path: Path to the PDF file

    Returns:
        Metadata dictionary (title, author, subject, page_count, etc.)
    """
    meta: Dict = {}
    try:
        import fitz

        doc = fitz.open(str(file_path))
        raw_meta = doc.metadata or {}
        page_count = doc.page_count
        doc.close()

        meta = {
            "title": raw_meta.get("title", ""),
            "author": raw_meta.get("author", ""),
            "subject": raw_meta.get("subject", ""),
            "creator": raw_meta.get("creator", ""),
            "page_count": page_count,
        }
    except Exception as e:
        logger.warning(f"PDF metadata extraction failed for {file_path}: {e}")

    return meta


def extract_pdf_full(file_path: Union[str, Path]) -> Dict:
    """
    Convenience function: extract text, tables, and metadata from a PDF.

    Args:
        file_path: Path to the PDF file

    Returns:
        Dictionary with keys: text, tables_text, metadata
    """
    text = extract_pdf_text(file_path) or ""
    tables = extract_pdf_tables(file_path)
    table_text = tables_to_text(tables)
    metadata = extract_pdf_metadata(file_path)

    # Append table text after main body text
    combined = text
    if table_text:
        combined = f"{text}\n\n--- Tables ---\n\n{table_text}"

    return {
        "text": combined,
        "tables": tables,
        "metadata": metadata,
    }
