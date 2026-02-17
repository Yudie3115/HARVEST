"""
Unit tests for LLM client and embeddings (mocked – no API calls)
"""
import json
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# LLM Client
# ---------------------------------------------------------------------------

class TestLLMClient:
    """Tests for LLMClient using a mocked OpenAI backend"""

    def _make_client(self, response_content: str):
        """Helper: create an LLMClient with mocked API returning response_content"""
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=response_content))]
        )
        with patch("src.llm.client.settings") as s:
            s.openai_api_key = "sk-test"
            s.llm_provider = "openai"
            s.openai_model = "gpt-4o-mini"
            s.openai_temperature = 0.1
            s.openai_max_tokens = 8192
            s.relevance_threshold = 6.0
            with patch("openai.OpenAI", return_value=mock_openai):
                from src.llm.client import LLMClient
                return LLMClient(provider="openai"), mock_openai

    def test_classify_urls_returns_list(self):
        urls = ["https://naro.go.ug/guide.pdf", "https://naro.go.ug/about"]
        response = json.dumps({
            "urls": [
                {
                    "url": urls[0],
                    "relevance_score": 8.5,
                    "topics": ["storage"],
                    "document_type": "research_paper",
                    "priority": "high",
                },
                {
                    "url": urls[1],
                    "relevance_score": 2.0,
                    "topics": [],
                    "document_type": "webpage",
                    "priority": "low",
                },
            ]
        })
        client, _ = self._make_client(response)
        results = client.classify_urls(urls)
        assert isinstance(results, list)
        assert len(results) == 2
        assert results[0]["relevance_score"] == 8.5

    def test_classify_urls_handles_json_error(self):
        """Should return default classifications when LLM returns malformed JSON"""
        client, mock_api = self._make_client("not valid json {{}")
        results = client.classify_urls(["https://naro.go.ug/guide.pdf"])
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]["relevance_score"] == 5.0  # default

    def test_classify_content_returns_dict(self):
        response = json.dumps({
            "primary_topics": ["storage", "drying"],
            "crops_mentioned": ["maize"],
            "regions": ["Northern Uganda"],
            "document_type": "extension_guide",
            "target_audience": ["farmers"],
            "language": "en",
            "relevance_score": 8.5,
            "summary": "A guide to post-harvest storage.",
            "key_practices": ["dry to 13.5% moisture"],
            "actionable": True,
            "has_data": False,
            "technical_level": "Simple",
        })
        client, _ = self._make_client(response)
        result = client.classify_content("Maize should be dried before storage.", url="https://naro.go.ug/guide")
        assert isinstance(result, dict)
        assert result["relevance_score"] == 8.5
        assert "storage" in result["topics"]

    def test_classify_content_normalises_primary_topics(self):
        """primary_topics key should be normalised to topics"""
        response = json.dumps({
            "primary_topics": ["pest_management"],
            "relevance_score": 7.0,
        })
        client, _ = self._make_client(response)
        result = client.classify_content("About pest management.")
        assert "topics" in result
        assert "primary_topics" not in result

    def test_classify_content_default_on_failure(self):
        client, mock_api = self._make_client("{bad json")
        result = client.classify_content("Some content")
        assert result["relevance_score"] == 5.0
        assert isinstance(result["topics"], list)

    def test_default_classification(self):
        from src.llm.client import LLMClient
        default = LLMClient._default_classification("test content")
        assert "relevance_score" in default
        assert "topics" in default
        assert "crops" in default
        assert "actionable" in default


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

class TestPrompts:
    def test_url_classification_prompt_contains_urls(self):
        from src.llm.prompts import build_url_classification_prompt
        urls = ["https://naro.go.ug/a.pdf", "https://naro.go.ug/b.html"]
        prompt = build_url_classification_prompt(urls)
        assert "naro.go.ug/a.pdf" in prompt
        assert "naro.go.ug/b.html" in prompt

    def test_content_classification_prompt_contains_content(self):
        from src.llm.prompts import build_content_classification_prompt
        content = "Maize storage reduces losses."
        url = "https://naro.go.ug/guide"
        prompt = build_content_classification_prompt(content, url)
        assert content in prompt
        assert url in prompt

    def test_summarisation_prompt_truncates(self):
        from src.llm.prompts import build_summarisation_prompt
        long_text = "word " * 10000
        prompt = build_summarisation_prompt(long_text, max_length=200)
        # Prompt should not include the full 50,000-char text
        assert len(prompt) < len(long_text)


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

class TestEmbeddingClient:
    def test_embed_single_openai(self):
        mock_openai = MagicMock()
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536, index=0)]
        )
        with patch("src.llm.embeddings.settings") as s:
            s.openai_api_key = "sk-test"
            s.embedding_provider = "openai"
            s.embedding_model = "text-embedding-3-small"
            s.embedding_dimension = 1536
            s.embedding_batch_size = 32
            with patch("openai.OpenAI", return_value=mock_openai):
                from src.llm.embeddings import EmbeddingClient
                client = EmbeddingClient(provider="openai")
                vec = client.embed("Post-harvest storage guide")
                assert len(vec) == 1536
                assert vec[0] == pytest.approx(0.1)

    def test_embed_batch_openai(self):
        texts = ["text one", "text two", "text three"]
        mock_openai = MagicMock()
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[
                MagicMock(embedding=[float(i)] * 1536, index=i)
                for i in range(len(texts))
            ]
        )
        with patch("src.llm.embeddings.settings") as s:
            s.openai_api_key = "sk-test"
            s.embedding_provider = "openai"
            s.embedding_model = "text-embedding-3-small"
            s.embedding_dimension = 1536
            s.embedding_batch_size = 32
            with patch("openai.OpenAI", return_value=mock_openai):
                from src.llm.embeddings import EmbeddingClient
                client = EmbeddingClient(provider="openai")
                vecs = client.embed_batch(texts)
                assert len(vecs) == 3
                assert all(len(v) == 1536 for v in vecs)

    def test_embed_empty_string_does_not_error(self):
        mock_openai = MagicMock()
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.0] * 1536, index=0)]
        )
        with patch("src.llm.embeddings.settings") as s:
            s.openai_api_key = "sk-test"
            s.embedding_provider = "openai"
            s.embedding_model = "text-embedding-3-small"
            s.embedding_dimension = 1536
            s.embedding_batch_size = 32
            with patch("openai.OpenAI", return_value=mock_openai):
                from src.llm.embeddings import EmbeddingClient
                client = EmbeddingClient(provider="openai")
                # Empty string should be replaced with " " to avoid API errors
                vec = client.embed("")
                assert len(vec) == 1536
