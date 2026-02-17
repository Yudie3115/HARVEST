"""
Shared pytest fixtures
"""
import io
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Sample content fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_html() -> str:
    return """<!DOCTYPE html>
<html>
<head>
  <title>Post-Harvest Storage Guide</title>
  <meta name="description" content="Best practices for maize storage in Uganda">
</head>
<body>
  <nav><a href="/">Home</a><a href="/about">About</a></nav>
  <main>
    <h1>Post-Harvest Storage Guide for Maize</h1>
    <p>Proper post-harvest handling is critical to reducing losses. Maize should be
    dried to a moisture content below 13.5% before storage to prevent aflatoxin
    contamination.</p>
    <p>Key steps for safe storage:</p>
    <ul>
      <li>Harvest at the right time</li>
      <li>Dry thoroughly before bagging</li>
      <li>Use hermetic bags or metal silos</li>
      <li>Apply approved grain protectants</li>
      <li>Monitor regularly for pests</li>
    </ul>
    <p>This guide is produced by the National Agricultural Research Organisation (NARO)
    for smallholder farmers in Uganda.</p>
  </main>
  <footer>© NARO Uganda 2024</footer>
</body>
</html>
"""


@pytest.fixture
def sample_text() -> str:
    return (
        "Post-harvest losses in Uganda account for up to 30% of maize production. "
        "Proper drying to below 13.5% moisture content is essential before storage. "
        "Hermetic bags significantly reduce aflatoxin contamination during storage. "
        "Farmers should inspect stored grain weekly for signs of pests or mould. "
        "The use of metal silos provides excellent long-term storage for smallholders. "
    ) * 10  # Make it long enough for chunking tests


@pytest.fixture
def sample_pdf_path(tmp_path: Path) -> Path:
    """Create a minimal valid PDF file for testing"""
    pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Post-harvest guide) Tj ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000274 00000 n
0000000370 00000 n
trailer
<< /Size 6 /Root 1 0 R >>
startxref
441
%%EOF"""
    pdf_file = tmp_path / "test_document.pdf"
    pdf_file.write_bytes(pdf_content)
    return pdf_file


# ---------------------------------------------------------------------------
# Mock fixtures for external services
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client that returns predictable JSON responses"""
    mock = MagicMock()
    mock.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content='{"urls": [{"url": "https://naro.go.ug/publication.pdf", '
                            '"relevance_score": 8.5, "topics": ["storage"], '
                            '"document_type": "research_paper", "priority": "high"}]}'
                )
            )
        ]
    )
    mock.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=[0.1] * 1536, index=0)]
    )
    return mock


@pytest.fixture
def mock_llm_client(mock_openai_client):
    """LLMClient with patched OpenAI backend"""
    with patch("src.llm.client.settings") as mock_settings:
        mock_settings.openai_api_key = "sk-test"
        mock_settings.llm_provider = "openai"
        mock_settings.openai_model = "gpt-4o-mini"
        mock_settings.openai_temperature = 0.1
        mock_settings.openai_max_tokens = 8192
        mock_settings.relevance_threshold = 6.0

        with patch("openai.OpenAI", return_value=mock_openai_client):
            from src.llm.client import LLMClient
            return LLMClient(provider="openai")


@pytest.fixture
def mock_postgres():
    """Mock PostgresClient"""
    with patch("src.storage.postgres.PostgresClient") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        yield instance


@pytest.fixture
def mock_minio():
    """Mock MinIOClient"""
    with patch("src.storage.minio_client.MinIOClient") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        yield instance


@pytest.fixture
def mock_vector_db():
    """Mock VectorDBClient"""
    with patch("src.storage.vector_db.VectorDBClient") as mock_cls:
        instance = MagicMock()
        instance.search.return_value = [
            {
                "id": "abc123",
                "score": 0.92,
                "payload": {
                    "text": "Maize should be dried below 13.5% moisture.",
                    "topics": ["storage", "drying"],
                    "source_url": "https://naro.go.ug/guide.pdf",
                    "document_type": "extension_guide",
                    "relevance_score": 8.5,
                },
            }
        ]
        mock_cls.return_value = instance
        yield instance
