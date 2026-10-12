"""
Unit tests for LLM client and embeddings (mocked – no API calls)
"""
import json
import pytest
from unittest.mock import MagicMock, patch


class TestLLMClientStreaming:
    """Tests for stream_answer() generator"""

    def _make_client_and_mock(self, tokens: list):
        mock_openai = MagicMock()
        chunks = [MagicMock(choices=[MagicMock(delta=MagicMock(content=t))]) for t in tokens]
        # Final chunk with content=None (OpenAI end-of-stream marker)
        chunks.append(MagicMock(choices=[MagicMock(delta=MagicMock(content=None))]))
        mock_openai.chat.completions.create.return_value = iter(chunks)

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

    def test_stream_answer_yields_tokens(self):
        tokens = ["Hello", " world", "!"]
        client, mock_api = self._make_client_and_mock(tokens)
        chunks = [{"text": "Some content.", "source_url": "https://naro.go.ug/guide.pdf"}]

        result = list(client.stream_answer("What is storage?", chunks=chunks))

        call_kwargs = mock_api.chat.completions.create.call_args.kwargs
        assert call_kwargs.get("stream") is True
        assert result == ["Hello", " world", "!"]

    def test_stream_answer_with_history_includes_prior_turns(self):
        client, mock_api = self._make_client_and_mock(["answer"])
        history = [
            {"role": "user", "content": "prior question"},
            {"role": "assistant", "content": "prior answer"},
        ]
        chunks = [{"text": "Content.", "source_url": "https://naro.go.ug/guide.pdf"}]

        list(client.stream_answer("follow up?", chunks=chunks, history=history))

        call_kwargs = mock_api.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["system", "user", "assistant", "user"]

    def test_stream_answer_skips_none_deltas(self):
        client, _ = self._make_client_and_mock(["a", "b"])
        chunks = [{"text": "Content.", "source_url": "https://naro.go.ug/guide.pdf"}]
        result = list(client.stream_answer("q", chunks=chunks))
        assert None not in result
        assert result == ["a", "b"]


class TestLLMClientHistory:
    """Tests for history-aware LLM generation"""

    def _make_client_and_mock(self, response_content: str):
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

    def test_generate_without_history_sends_two_messages(self):
        client, mock_api = self._make_client_and_mock("hello")
        client._generate("my question", system_prompt="sys", response_format="")
        call_args = mock_api.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "my question"

    def test_generate_with_history_inserts_turns_before_current(self):
        client, mock_api = self._make_client_and_mock("follow-up answer")
        history = [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "first answer"},
        ]
        client._generate(
            "second question", system_prompt="sys", response_format="", history=history
        )
        call_args = mock_api.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        # system + 2 history + current user
        assert len(messages) == 4
        assert messages[0]["role"] == "system"
        assert messages[1] == {"role": "user", "content": "first question"}
        assert messages[2] == {"role": "assistant", "content": "first answer"}
        assert messages[3]["role"] == "user"
        assert messages[3]["content"] == "second question"

    def test_answer_question_with_history_passes_history_to_generate(self):
        client, mock_api = self._make_client_and_mock("answer with history")
        history = [
            {"role": "user", "content": "what is drying?"},
            {"role": "assistant", "content": "Drying reduces moisture content."},
        ]
        chunks = [
            {
                "text": "Maize should be dried below 13.5%.",
                "source_url": "https://naro.go.ug/guide.pdf",
            }
        ]
        result = client.answer_question("What temperature?", chunks=chunks, history=history)
        assert result == "answer with history"
        call_args = mock_api.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        roles = [m["role"] for m in messages]
        # system, user (drying?), assistant (drying answer), user (current)
        assert roles == ["system", "user", "assistant", "user"]

    def test_answer_question_without_history_unchanged(self):
        client, mock_api = self._make_client_and_mock("normal answer")
        chunks = [{"text": "Store in hermetic bags.", "source_url": "https://naro.go.ug/guide.pdf"}]
        result = client.answer_question("How to store?", chunks=chunks)
        assert result == "normal answer"
        call_args = mock_api.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_suggest_followups_returns_bounded_unique_questions(self):
        client, _ = self._make_client_and_mock(
            '{"questions":["How is moisture measured?",'
            '"How is moisture measured?","Which dryer is suitable?","A fourth?"]}'
        )

        result = client.suggest_followup_questions(
            "How should maize be dried?",
            "Dry maize to a safe moisture content.",
            [{"text": "Use raised tarpaulins and monitor moisture."}],
        )

        assert result == [
            "How is moisture measured?",
            "Which dryer is suitable?",
            "A fourth?",
        ]


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
        response = json.dumps(
            {
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
            }
        )
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
        response = json.dumps(
            {
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
            }
        )
        client, _ = self._make_client(response)
        result = client.classify_content(
            "Maize should be dried before storage.", url="https://naro.go.ug/guide"
        )
        assert isinstance(result, dict)
        assert result["relevance_score"] == 8.5
        assert "storage" in result["topics"]

    def test_classify_content_normalises_primary_topics(self):
        """primary_topics key should be normalised to topics"""
        response = json.dumps(
            {
                "primary_topics": ["pest_management"],
                "relevance_score": 7.0,
            }
        )
        client, _ = self._make_client(response)
        result = client.classify_content("About pest management.")
        assert "topics" in result
        assert "primary_topics" not in result

    def test_classify_content_default_on_failure(self):
        client, mock_api = self._make_client("{bad json")
        result = client.classify_content("Some content")
        assert result["relevance_score"] == 5.0
        assert result["classification_failed"] is True
        assert isinstance(result["topics"], list)

    def test_classify_content_retries_when_score_missing(self):
        from src.llm.client import LLMClient

        client = LLMClient.__new__(LLMClient)
        client.provider = "test"
        client._generate = MagicMock(
            side_effect=[
                json.dumps({"topics": ["storage"]}),
                "{bad json",
                json.dumps({"topics": ["storage"], "relevance_score": "8"}),
            ]
        )
        result = client.classify_content("Maize storage.")
        assert client._generate.call_count == 3
        assert result["relevance_score"] == 8.0
        assert "classification_failed" not in result

    def test_classify_content_gives_up_after_three_attempts(self):
        from src.llm.client import LLMClient

        client = LLMClient.__new__(LLMClient)
        client.provider = "test"
        client._generate = MagicMock(return_value=json.dumps({"topics": ["storage"]}))
        result = client.classify_content("Maize storage.")
        assert client._generate.call_count == 3
        assert result["classification_failed"] is True

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

    def test_classification_prompts_cover_all_three_crop_stages(self):
        from src.llm.prompts import (
            build_content_classification_prompt,
            build_url_classification_prompt,
        )

        content_prompt = build_content_classification_prompt("text", "https://x.org")
        url_prompt = build_url_classification_prompt(["https://x.org/a.pdf"])
        for prompt in (content_prompt, url_prompt):
            assert "field_pests_and_diseases" in prompt
            assert "seed_and_varieties" in prompt
            assert "harvest_timing_and_methods" in prompt
            assert "storage" in prompt
        assert "pre-harvest, harvest and post-harvest" in content_prompt

    def test_harvest_is_its_own_topic_stage(self):
        from src.config.site_configs import (
            HARVEST_TOPICS,
            POST_HARVEST_TOPICS,
            PRE_HARVEST_TOPICS,
            TOPICS,
        )

        assert HARVEST_TOPICS == ["harvest_timing_and_methods"]
        assert "harvest_timing_and_methods" not in PRE_HARVEST_TOPICS
        assert TOPICS == PRE_HARVEST_TOPICS + HARVEST_TOPICS + POST_HARVEST_TOPICS

    def test_llm_client_uses_shared_classification_prompt(self):
        from src.llm.client import LLMClient

        client = LLMClient.__new__(LLMClient)
        client.provider = "test"
        client._generate = MagicMock(return_value='{"relevance_score": 8}')
        client.classify_content("Planting maize early in the season.", url="https://x.org")
        prompt = client._generate.call_args.kwargs["prompt"]
        assert "drought_and_water_stress" in prompt

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
            data=[MagicMock(embedding=[float(i)] * 1536, index=i) for i in range(len(texts))]
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
