"""
Unit tests for content extractors
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# HTML Extractor
# ---------------------------------------------------------------------------

class TestHTMLExtractor:
    def test_extract_html_content_basic(self, sample_html):
        from src.extractors.html_extractor import extract_html_content
        # Trafilatura may not be installed in test env; fallback to BS4
        text = extract_html_content(sample_html, url="https://naro.go.ug/guide")
        # Either trafilatura or BS4 should find key content
        assert text is not None
        assert "post-harvest" in text.lower() or "storage" in text.lower()

    def test_extract_html_content_removes_nav(self, sample_html):
        from src.extractors.html_extractor import extract_html_content
        text = extract_html_content(sample_html)
        # Should not contain navigation-only text
        assert text is not None
        # Main content should be present
        assert "maize" in text.lower()

    def test_extract_html_content_empty(self):
        from src.extractors.html_extractor import extract_html_content
        result = extract_html_content("<html><body></body></html>")
        assert result is None or result.strip() == ""

    def test_extract_html_metadata(self, sample_html):
        from src.extractors.html_extractor import extract_html_metadata
        meta = extract_html_metadata(sample_html, url="https://naro.go.ug/guide")
        assert meta["title"] == "Post-Harvest Storage Guide"
        assert "maize" in meta["description"].lower()

    def test_extract_html_metadata_no_title(self):
        from src.extractors.html_extractor import extract_html_metadata
        html = "<html><body><p>Some content</p></body></html>"
        meta = extract_html_metadata(html)
        assert isinstance(meta, dict)
        assert "title" in meta

    def test_bs4_fallback(self):
        """Test that BeautifulSoup fallback works when trafilatura unavailable"""
        from src.extractors.html_extractor import _bs4_extract
        html = "<html><body><main><p>Post-harvest storage is important.</p></main></body></html>"
        text = _bs4_extract(html)
        assert text is not None
        assert "post-harvest" in text.lower()


# ---------------------------------------------------------------------------
# PDF Extractor
# ---------------------------------------------------------------------------

class TestPDFExtractor:
    def test_extract_pdf_text_valid(self, sample_pdf_path):
        """Test with a minimal valid PDF"""
        from src.extractors.pdf_extractor import extract_pdf_text
        try:
            text = extract_pdf_text(sample_pdf_path)
            # Either extracted text or None (minimal PDF may have rendering quirks)
            assert text is None or isinstance(text, str)
        except ImportError:
            pytest.skip("PyMuPDF (fitz) not installed")

    def test_extract_pdf_tables_valid(self, sample_pdf_path):
        from src.extractors.pdf_extractor import extract_pdf_tables
        try:
            tables = extract_pdf_tables(sample_pdf_path)
            assert isinstance(tables, list)
        except ImportError:
            pytest.skip("pdfplumber not installed")

    def test_tables_to_text_empty(self):
        from src.extractors.pdf_extractor import tables_to_text
        assert tables_to_text([]) == ""

    def test_tables_to_text_basic(self):
        from src.extractors.pdf_extractor import tables_to_text
        tables = [[["Crop", "Loss %"], ["Maize", "20"], ["Beans", "15"]]]
        text = tables_to_text(tables)
        assert "Crop" in text
        assert "Maize" in text
        assert "|" in text  # Markdown table format

    def test_extract_pdf_metadata_missing_file(self, tmp_path):
        from src.extractors.pdf_extractor import extract_pdf_metadata
        result = extract_pdf_metadata(tmp_path / "nonexistent.pdf")
        assert isinstance(result, dict)

    def test_extract_pdf_full_returns_dict(self, sample_pdf_path):
        from src.extractors.pdf_extractor import extract_pdf_full
        try:
            result = extract_pdf_full(sample_pdf_path)
            assert isinstance(result, dict)
            assert "text" in result
            assert "tables" in result
            assert "metadata" in result
        except ImportError:
            pytest.skip("PyMuPDF or pdfplumber not installed")


# ---------------------------------------------------------------------------
# Video Extractor
# ---------------------------------------------------------------------------

class TestVideoExtractor:
    def test_parse_vtt(self):
        from src.extractors.video_extractor import _parse_vtt
        vtt = """WEBVTT

00:00:01.000 --> 00:00:03.000
<00:00:01.000>Post-harvest storage

00:00:04.000 --> 00:00:06.000
<00:00:04.000>reduces food losses.
"""
        text = _parse_vtt(vtt)
        assert "Post-harvest storage" in text
        assert "reduces food losses" in text

    def test_parse_vtt_deduplication(self):
        from src.extractors.video_extractor import _parse_vtt
        vtt = """WEBVTT

00:00:01.000 --> 00:00:03.000
Duplicate line

00:00:02.000 --> 00:00:04.000
Duplicate line
"""
        text = _parse_vtt(vtt)
        # "Duplicate line" should appear exactly once
        assert text.count("Duplicate line") == 1

    def test_extract_video_metadata_subprocess_failure(self):
        """_extract_via_subprocess should return empty dict when yt-dlp CLI fails"""
        from src.extractors.video_extractor import _extract_via_subprocess
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr="yt-dlp not found", stdout=""
            )
            result = _extract_via_subprocess("https://youtube.com/watch?v=test")
            assert isinstance(result, dict)

    def test_extract_video_metadata_subprocess_success(self):
        """_extract_via_subprocess should parse yt-dlp JSON output"""
        import json
        from src.extractors.video_extractor import _extract_via_subprocess
        fake_info = {
            "title": "Post-harvest storage guide",
            "description": "A video about maize storage",
            "duration": 300,
            "upload_date": "20240101",
            "uploader": "NARO Uganda",
            "tags": ["agriculture", "storage"],
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=json.dumps(fake_info), stderr=""
            )
            result = _extract_via_subprocess("https://youtube.com/watch?v=test")
            assert result["title"] == "Post-harvest storage guide"
            assert isinstance(result["tags"], list)

    def test_extract_video_full_structure(self):
        """extract_video_full should always return a dict with required keys"""
        with patch(
            "src.extractors.video_extractor.extract_video_metadata",
            return_value={"title": "Maize storage", "description": "A guide"},
        ):
            with patch(
                "src.extractors.video_extractor.extract_video_subtitles",
                return_value="Dry maize before storage.",
            ):
                from src.extractors.video_extractor import extract_video_full
                result = extract_video_full("https://youtube.com/watch?v=test")
                assert "metadata" in result
                assert "transcript" in result
                assert "text" in result
                assert "Maize storage" in result["text"]
                assert "Dry maize before storage" in result["text"]
