"""
Text processing utilities: chunking, cleaning, tokenisation
"""
import re
from typing import List

from loguru import logger

from src.config.settings import settings


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """
    Normalise whitespace and remove control characters from extracted text

    Args:
        text: Raw extracted text

    Returns:
        Cleaned text
    """
    if not text:
        return ""

    # Collapse multiple newlines to two
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse multiple spaces / tabs to a single space
    text = re.sub(r"[ \t]+", " ", text)
    # Strip leading/trailing whitespace from each line
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)
    # Final strip
    return text.strip()


def remove_boilerplate(text: str, min_line_length: int = 20) -> str:
    """
    Remove very short lines that are likely navigation / footer boilerplate

    Args:
        text: Cleaned text
        min_line_length: Lines shorter than this are dropped

    Returns:
        Text with boilerplate removed
    """
    lines = text.splitlines()
    filtered = [
        line for line in lines
        if len(line.strip()) >= min_line_length or line.strip() == ""
    ]
    return "\n".join(filtered)


# ---------------------------------------------------------------------------
# Tokenisation (approximate, no external dependency required)
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """
    Approximate token count using the ~4 chars-per-token heuristic

    Args:
        text: Text to estimate

    Returns:
        Estimated token count
    """
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    chunk_size: int = None,
    chunk_overlap: int = None,
) -> List[str]:
    """
    Split text into overlapping chunks based on approximate token count.

    The algorithm:
    1. Split on paragraph boundaries (double newlines)
    2. Accumulate paragraphs until the chunk_size token limit is reached
    3. Add the next paragraph(s) as overlap for the following chunk

    Args:
        text: Source text to chunk
        chunk_size: Maximum tokens per chunk (default from settings)
        chunk_overlap: Overlap tokens between consecutive chunks

    Returns:
        List of text chunks
    """
    chunk_size = chunk_size or settings.chunk_size
    chunk_overlap = chunk_overlap or settings.chunk_overlap

    if not text or estimate_tokens(text) <= chunk_size:
        return [text] if text else []

    # Split into paragraphs; fall back to sentences if text has no blank lines
    paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
    if len(paragraphs) <= 1:
        # Fall back to sentence splitting
        paragraphs = re.split(r"(?<=[.!?])\s+", text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks: List[str] = []
    current_parts: List[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = estimate_tokens(para)

        # If a single paragraph exceeds chunk_size, split it by sentences
        if para_tokens > chunk_size:
            sentences = re.split(r"(?<=[.!?])\s+", para)
            for sentence in sentences:
                st = estimate_tokens(sentence)
                if current_tokens + st > chunk_size and current_parts:
                    chunks.append(" ".join(current_parts))
                    # Keep overlap
                    overlap_parts, overlap_tokens = _trim_to_tokens(
                        current_parts, chunk_overlap
                    )
                    current_parts = overlap_parts
                    current_tokens = overlap_tokens
                current_parts.append(sentence)
                current_tokens += st
            continue

        if current_tokens + para_tokens > chunk_size and current_parts:
            chunks.append("\n\n".join(current_parts))
            # Keep overlap
            overlap_parts, overlap_tokens = _trim_to_tokens(
                current_parts, chunk_overlap
            )
            current_parts = overlap_parts
            current_tokens = overlap_tokens

        current_parts.append(para)
        current_tokens += para_tokens

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    logger.debug(f"Chunked text into {len(chunks)} chunks (size≈{chunk_size} tokens)")
    return chunks


def _trim_to_tokens(parts: List[str], max_tokens: int):
    """
    Return the trailing portion of *parts* that fits within max_tokens,
    together with its token count.
    """
    kept: List[str] = []
    tokens = 0
    for part in reversed(parts):
        pt = estimate_tokens(part)
        if tokens + pt > max_tokens:
            break
        kept.insert(0, part)
        tokens += pt
    return kept, tokens


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

def truncate_text(text: str, max_chars: int = 500, suffix: str = "…") -> str:
    """Truncate text to max_chars and append suffix if truncated"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + suffix


def extract_keywords(text: str, keywords: List[str]) -> List[str]:
    """
    Return which keywords from the provided list appear in the text (case-insensitive)

    Args:
        text: Source text
        keywords: List of keywords to search for

    Returns:
        Matched keywords
    """
    lower = text.lower()
    return [kw for kw in keywords if kw.lower() in lower]
