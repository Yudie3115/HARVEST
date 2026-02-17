"""
Content hashing utilities for document deduplication
"""
import hashlib
from pathlib import Path
from typing import Union


def hash_content(content: Union[str, bytes]) -> str:
    """
    Generate SHA-256 hash of text or bytes content

    Args:
        content: Text string or bytes to hash

    Returns:
        Hex digest string (64 characters)
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def hash_file(file_path: Union[str, Path], chunk_size: int = 65536) -> str:
    """
    Generate SHA-256 hash of a file, streaming in chunks to handle large files

    Args:
        file_path: Path to file
        chunk_size: Read chunk size in bytes

    Returns:
        Hex digest string (64 characters)
    """
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def hash_url(url: str) -> str:
    """
    Generate a short, URL-safe identifier from a URL

    Args:
        url: URL string

    Returns:
        First 16 characters of SHA-256 hex digest
    """
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def content_unchanged(new_hash: str, existing_hash: str) -> bool:
    """
    Check whether content hash matches, indicating no change

    Args:
        new_hash: SHA-256 hash of newly downloaded content
        existing_hash: SHA-256 hash stored in database

    Returns:
        True if content is identical
    """
    return new_hash == existing_hash
