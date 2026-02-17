"""
Unit tests for src/utils – no external services required
"""
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

class TestHashing:
    def test_hash_content_str(self):
        from src.utils.hashing import hash_content
        h = hash_content("hello world")
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex digest

    def test_hash_content_bytes(self):
        from src.utils.hashing import hash_content
        h = hash_content(b"hello world")
        assert len(h) == 64

    def test_hash_content_deterministic(self):
        from src.utils.hashing import hash_content
        assert hash_content("test") == hash_content("test")

    def test_hash_content_different_inputs(self):
        from src.utils.hashing import hash_content
        assert hash_content("a") != hash_content("b")

    def test_hash_file(self, tmp_path):
        from src.utils.hashing import hash_file
        f = tmp_path / "test.txt"
        f.write_text("post-harvest content")
        h = hash_file(f)
        assert len(h) == 64

    def test_hash_file_consistent_with_content_hash(self, tmp_path):
        from src.utils.hashing import hash_file, hash_content
        content = b"maize storage guide"
        f = tmp_path / "file.bin"
        f.write_bytes(content)
        assert hash_file(f) == hash_content(content)

    def test_hash_url(self):
        from src.utils.hashing import hash_url
        h = hash_url("https://naro.go.ug/guide.pdf")
        assert isinstance(h, str)
        assert len(h) == 16  # First 16 chars of SHA-256

    def test_content_unchanged_true(self):
        from src.utils.hashing import content_unchanged, hash_content
        h = hash_content("same content")
        assert content_unchanged(h, h) is True

    def test_content_unchanged_false(self):
        from src.utils.hashing import content_unchanged, hash_content
        h1 = hash_content("version 1")
        h2 = hash_content("version 2")
        assert content_unchanged(h1, h2) is False


# ---------------------------------------------------------------------------
# Text processing
# ---------------------------------------------------------------------------

class TestTextProcessing:
    def test_clean_text_collapses_blank_lines(self):
        from src.utils.text_processing import clean_text
        text = "Para 1\n\n\n\n\nPara 2"
        cleaned = clean_text(text)
        assert "\n\n\n" not in cleaned

    def test_clean_text_collapses_spaces(self):
        from src.utils.text_processing import clean_text
        text = "word    with    spaces"
        cleaned = clean_text(text)
        assert "  " not in cleaned

    def test_clean_text_empty(self):
        from src.utils.text_processing import clean_text
        assert clean_text("") == ""
        assert clean_text(None) == ""

    def test_estimate_tokens(self):
        from src.utils.text_processing import estimate_tokens
        # 4 chars ≈ 1 token
        assert estimate_tokens("a" * 400) == 100
        assert estimate_tokens("") >= 1  # minimum 1

    def test_chunk_text_short_input(self, sample_text):
        from src.utils.text_processing import chunk_text
        short = "This is a short post-harvest guide."
        chunks = chunk_text(short, chunk_size=1000, chunk_overlap=100)
        assert len(chunks) == 1
        assert chunks[0] == short

    def test_chunk_text_long_input(self, sample_text):
        from src.utils.text_processing import chunk_text
        chunks = chunk_text(sample_text, chunk_size=200, chunk_overlap=50)
        assert len(chunks) > 1
        # All chunks should be non-empty
        assert all(c.strip() for c in chunks)

    def test_chunk_text_empty(self):
        from src.utils.text_processing import chunk_text
        assert chunk_text("") == []
        assert chunk_text(None) == []

    def test_chunk_text_preserves_content(self, sample_text):
        from src.utils.text_processing import chunk_text
        chunks = chunk_text(sample_text, chunk_size=200, chunk_overlap=50)
        # The combined chunks should contain the key words
        combined = " ".join(chunks)
        assert "post-harvest" in combined.lower()
        assert "maize" in combined.lower()

    def test_truncate_text(self):
        from src.utils.text_processing import truncate_text
        text = "a" * 1000
        result = truncate_text(text, max_chars=100)
        assert len(result) <= 101  # + suffix

    def test_truncate_text_short(self):
        from src.utils.text_processing import truncate_text
        text = "short text"
        assert truncate_text(text, max_chars=100) == text

    def test_extract_keywords(self):
        from src.utils.text_processing import extract_keywords
        text = "Maize storage reduces post-harvest losses in Uganda"
        matches = extract_keywords(text, ["maize", "storage", "coffee", "losses"])
        assert "maize" in matches
        assert "storage" in matches
        assert "coffee" not in matches

    def test_extract_keywords_case_insensitive(self):
        from src.utils.text_processing import extract_keywords
        text = "MAIZE STORAGE PRACTICES"
        matches = extract_keywords(text, ["maize", "storage"])
        assert "maize" in matches

    def test_remove_boilerplate(self):
        from src.utils.text_processing import remove_boilerplate
        text = "Home\nShort\nThis is a substantial paragraph about post-harvest practices."
        result = remove_boilerplate(text, min_line_length=20)
        assert "Home" not in result
        assert "post-harvest" in result
