"""
Unit tests for process_chat — verifying history, score threshold, enriched sources, no-results.
"""
import uuid
from unittest.mock import MagicMock, patch
import pytest


def _make_session(session_id=None):
    session = MagicMock()
    session.id = session_id or uuid.uuid4()
    return session


def _make_message(role, content):
    msg = MagicMock()
    msg.role = role
    msg.content = content
    return msg


def _make_request(session_id, message="What is post-harvest loss?"):
    from src.api.models.requests import ChatRequest

    return ChatRequest(session_id=str(session_id), message=message)


@pytest.fixture
def mocks():
    """Return a dict of pre-configured mocks for process_chat dependencies."""
    session_id = uuid.uuid4()
    db = MagicMock()

    session_obj = _make_session(session_id)
    db.get.return_value = session_obj

    # DB query uses ORDER BY created_at DESC, so newest messages come first.
    # chat_service.py then reverses the list to get chronological order.
    prior_messages = [
        _make_message("assistant", "Usually 3–5 days depending on weather."),  # newest
        _make_message("user", "How long does it take?"),
        _make_message("assistant", "Dry maize in the sun to below 13.5% moisture."),
        _make_message("user", "How do I dry maize?"),  # oldest
    ]
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
        prior_messages
    )

    llm = MagicMock()
    llm.answer_question.return_value = "Post-harvest loss is crop lost after harvest."

    embedding = MagicMock()
    embedding.embed.return_value = [0.1] * 1536

    vector_db = MagicMock()
    vector_db.search.return_value = [
        {
            "id": "abc",
            "score": 0.9,
            "payload": {
                "text": "Post-harvest loss refers to losses after harvest.",
                "source_url": "https://naro.go.ug/guide.pdf",
                "title": "NARO Guide",
                "site_name": "naro",
            },
        }
    ]

    translation = MagicMock()
    translation.detect_language.return_value = "eng"

    return {
        "session_id": session_id,
        "db": db,
        "llm": llm,
        "embedding": embedding,
        "vector_db": vector_db,
        "translation": translation,
    }


def test_history_passed_to_answer_question(mocks):
    """Prior messages should be formatted and forwarded to answer_question as history."""
    from src.api.services.chat_service import process_chat

    request = _make_request(mocks["session_id"])

    # background_tasks is not passed → BertScore block is skipped, no settings import needed
    process_chat(
        request=request,
        db=mocks["db"],
        llm_client=mocks["llm"],
        embedding_client=mocks["embedding"],
        vector_db_client=mocks["vector_db"],
        translation_client=mocks["translation"],
    )

    call_kwargs = mocks["llm"].answer_question.call_args.kwargs
    history = call_kwargs.get("history")
    assert history is not None, "history kwarg must be passed to answer_question"
    assert len(history) == 4
    assert history[0] == {"role": "user", "content": "How do I dry maize?"}
    assert history[1] == {
        "role": "assistant",
        "content": "Dry maize in the sun to below 13.5% moisture.",
    }
    assert history[2] == {"role": "user", "content": "How long does it take?"}
    assert history[3] == {"role": "assistant", "content": "Usually 3–5 days depending on weather."}


def test_history_capped_at_six_messages(mocks):
    """Only the last 6 prior messages are passed as history (3 full turns)."""
    from src.api.services.chat_service import process_chat

    # 8 prior messages in descending order (newest first, as returned by DB)
    many_messages = [
        _make_message("user", f"question {i}")
        if i % 2 == 0
        else _make_message("assistant", f"answer {i}")
        for i in range(7, -1, -1)
    ]
    mocks[
        "db"
    ].query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
        many_messages
    )

    request = _make_request(mocks["session_id"])

    process_chat(
        request=request,
        db=mocks["db"],
        llm_client=mocks["llm"],
        embedding_client=mocks["embedding"],
        vector_db_client=mocks["vector_db"],
        translation_client=mocks["translation"],
    )

    call_kwargs = mocks["llm"].answer_question.call_args.kwargs
    history = call_kwargs.get("history")
    assert history is not None
    assert len(history) == 6


def test_empty_history_when_no_prior_messages(mocks):
    """No prior messages → history should be None or empty (not crash)."""
    from src.api.services.chat_service import process_chat

    mocks[
        "db"
    ].query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
        []
    )

    request = _make_request(mocks["session_id"])

    result = process_chat(
        request=request,
        db=mocks["db"],
        llm_client=mocks["llm"],
        embedding_client=mocks["embedding"],
        vector_db_client=mocks["vector_db"],
        translation_client=mocks["translation"],
    )

    call_kwargs = mocks["llm"].answer_question.call_args.kwargs
    history = call_kwargs.get("history")
    # None or empty list are both acceptable — no crash is what matters
    assert history is None or history == []
    assert result.answer == "Post-harvest loss is crop lost after harvest."


def test_score_threshold_passed_to_search(mocks):
    """The vector DB search must use settings.chat_score_threshold."""
    from src.api.services.chat_service import process_chat

    mocks[
        "db"
    ].query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
        []
    )

    request = _make_request(mocks["session_id"])

    with patch("src.api.services.chat_service.settings") as mock_settings:
        mock_settings.chat_score_threshold = 0.35
        mock_settings.bertscore_enabled = False
        process_chat(
            request=request,
            db=mocks["db"],
            llm_client=mocks["llm"],
            embedding_client=mocks["embedding"],
            vector_db_client=mocks["vector_db"],
            translation_client=mocks["translation"],
        )

    call_kwargs = mocks["vector_db"].search.call_args.kwargs
    assert call_kwargs.get("score_threshold") == 0.35


def test_chat_model_options_use_effective_ollama_fallback():
    """Public model metadata should not advertise OpenAI when it will fall back."""
    from src.api.routes import chat

    with patch("src.api.routes.chat.settings") as mock_settings:
        mock_settings.llm_provider = "openai"
        mock_settings.openai_api_key = ""
        mock_settings.openai_model = "gpt-4o-mini"
        mock_settings.groq_api_key = ""
        mock_settings.groq_model = "llama-3.3-70b-versatile"
        mock_settings.ollama_model = "gemma4:e2b"

        options = chat._model_options()

    assert options == [
        {
            "value": "ollama",
            "provider": "ollama",
            "label": "gemma4:e2b",
            "sub": "Ollama",
            "is_default": True,
        }
    ]


def test_chat_model_options_include_configured_overrides():
    """When optional providers are configured, expose them as explicit choices."""
    from src.api.routes import chat

    with patch("src.api.routes.chat.settings") as mock_settings:
        mock_settings.llm_provider = "ollama"
        mock_settings.ollama_model = "gemma4:e2b"
        mock_settings.groq_api_key = "groq-key"
        mock_settings.groq_model = "llama-3.3-70b-versatile"
        mock_settings.openai_api_key = "openai-key"
        mock_settings.openai_model = "gpt-4o-mini"

        options = chat._model_options()

    assert [option["value"] for option in options] == ["ollama", "groq", "openai"]
    assert options[0]["is_default"] is True


def test_sources_include_score_and_snippet(mocks):
    """Each returned SourceRef must include score and snippet from the search hit."""
    from src.api.services.chat_service import process_chat

    mocks[
        "db"
    ].query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
        []
    )
    request = _make_request(mocks["session_id"])

    with patch("src.api.services.chat_service.settings") as mock_settings:
        mock_settings.chat_score_threshold = 0.0
        mock_settings.bertscore_enabled = False
        result = process_chat(
            request=request,
            db=mocks["db"],
            llm_client=mocks["llm"],
            embedding_client=mocks["embedding"],
            vector_db_client=mocks["vector_db"],
            translation_client=mocks["translation"],
        )

    assert len(result.sources) == 1
    src = result.sources[0]
    assert src.score == 0.9
    assert src.snippet == "Post-harvest loss refers to losses after harvest."


def test_no_results_skips_llm_and_sets_flag(mocks):
    """When no chunks pass the threshold, LLM is not called and no_results=True."""
    from src.api.services.chat_service import process_chat

    mocks["vector_db"].search.return_value = []
    mocks[
        "db"
    ].query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
        []
    )
    request = _make_request(mocks["session_id"])

    with patch("src.api.services.chat_service.settings") as mock_settings:
        mock_settings.chat_score_threshold = 0.3
        mock_settings.bertscore_enabled = False
        result = process_chat(
            request=request,
            db=mocks["db"],
            llm_client=mocks["llm"],
            embedding_client=mocks["embedding"],
            vector_db_client=mocks["vector_db"],
            translation_client=mocks["translation"],
        )

    mocks["llm"].answer_question.assert_not_called()
    assert result.no_results is True
    assert "couldn't find" in result.answer.lower()


def test_min_top_score_blocks_nonstreaming_synthesis(mocks):
    from src.api.services.chat_service import process_chat

    mocks["vector_db"].search.return_value[0]["score"] = 0.49
    request = _make_request(mocks["session_id"])

    with patch("src.api.services.chat_service.settings") as mock_settings:
        mock_settings.chat_score_threshold = 0.3
        mock_settings.chat_min_top_score = 0.5
        result = process_chat(
            request=request,
            db=mocks["db"],
            llm_client=mocks["llm"],
            embedding_client=mocks["embedding"],
            vector_db_client=mocks["vector_db"],
            translation_client=mocks["translation"],
        )

    mocks["llm"].answer_question.assert_not_called()
    assert result.no_results is True
    metrics = [
        call.args[0]
        for call in mocks["db"].add.call_args_list
        if getattr(call.args[0], "metric_name", None) == "chat_retrieval_top_score"
    ]
    assert metrics[0].metric_value == 0.49
    assert metrics[0].extra_metadata["outcome"] == "below_min_top_score"


def test_min_top_score_allows_nonstreaming_synthesis_above_threshold(mocks):
    from src.api.services.chat_service import process_chat

    mocks["vector_db"].search.return_value[0]["score"] = 0.6
    request = _make_request(mocks["session_id"])

    with patch("src.api.services.chat_service.settings") as mock_settings:
        mock_settings.chat_score_threshold = 0.3
        mock_settings.chat_min_top_score = 0.5
        result = process_chat(
            request=request,
            db=mocks["db"],
            llm_client=mocks["llm"],
            embedding_client=mocks["embedding"],
            vector_db_client=mocks["vector_db"],
            translation_client=mocks["translation"],
        )

    mocks["llm"].answer_question.assert_called_once()
    assert result.no_results is False
    metrics = [
        call.args[0]
        for call in mocks["db"].add.call_args_list
        if getattr(call.args[0], "metric_name", None) == "chat_retrieval_top_score"
    ]
    assert metrics[0].metric_value == 0.6
    assert metrics[0].extra_metadata["outcome"] == "synthesized"


def test_disabled_min_top_score_observes_without_blocking(mocks):
    from src.api.services.chat_service import process_chat

    mocks["vector_db"].search.return_value[0]["score"] = 0.01
    request = _make_request(mocks["session_id"])

    with patch("src.api.services.chat_service.settings") as mock_settings:
        mock_settings.chat_score_threshold = 0.0
        mock_settings.chat_min_top_score = None
        result = process_chat(
            request=request,
            db=mocks["db"],
            llm_client=mocks["llm"],
            embedding_client=mocks["embedding"],
            vector_db_client=mocks["vector_db"],
            translation_client=mocks["translation"],
        )

    mocks["llm"].answer_question.assert_called_once()
    assert result.no_results is False


def test_min_top_score_blocks_stream_before_tokens(mocks):
    import json

    from src.api.services.chat_service import process_chat_stream

    mocks["vector_db"].search.return_value[0]["score"] = 0.4
    request = _make_request(mocks["session_id"])

    with patch("src.api.services.chat_service.settings") as mock_settings:
        mock_settings.chat_score_threshold = 0.3
        mock_settings.chat_min_top_score = 0.5
        events = list(
            process_chat_stream(
                request=request,
                db=mocks["db"],
                llm_client=mocks["llm"],
                embedding_client=mocks["embedding"],
                vector_db_client=mocks["vector_db"],
                translation_client=mocks["translation"],
            )
        )

    mocks["llm"].stream_answer.assert_not_called()
    payload = json.loads(events[-1].removeprefix("data: "))
    assert payload["type"] == "done"
    assert payload["no_results"] is True


def test_min_top_score_allows_stream_synthesis_above_threshold(mocks):
    import json

    from src.api.services.chat_service import process_chat_stream

    mocks["vector_db"].search.return_value[0]["score"] = 0.6
    mocks["llm"].stream_answer.return_value = ["Post", "-harvest loss."]
    mocks["llm"].suggest_followup_questions.return_value = ["How can these losses be measured?"]
    request = _make_request(mocks["session_id"])

    with patch("src.api.services.chat_service.settings") as mock_settings:
        mock_settings.chat_score_threshold = 0.3
        mock_settings.chat_min_top_score = 0.5
        events = list(
            process_chat_stream(
                request=request,
                db=mocks["db"],
                llm_client=mocks["llm"],
                embedding_client=mocks["embedding"],
                vector_db_client=mocks["vector_db"],
                translation_client=mocks["translation"],
            )
        )

    mocks["llm"].stream_answer.assert_called_once()
    payload = json.loads(events[-1].removeprefix("data: "))
    assert payload["type"] == "done"
    assert payload["no_results"] is False
    assert payload["suggested_questions"] == [
        {
            "text": "How can these losses be measured?",
            "kind": "generated",
            "catalogue_entry_id": None,
        }
    ]
    stages = [
        json.loads(event.removeprefix("data: "))["stage"]
        for event in events
        if json.loads(event.removeprefix("data: ")).get("type") == "status"
    ]
    assert stages == [
        "preparing",
        "language",
        "searching",
        "reading_sources",
        "synthesizing",
        "followups",
    ]
    metrics = [
        call.args[0]
        for call in mocks["db"].add.call_args_list
        if getattr(call.args[0], "metric_name", None) == "chat_retrieval_top_score"
    ]
    assert metrics[0].metric_value == 0.6
    assert metrics[0].extra_metadata["outcome"] == "synthesized"


def test_sources_are_grouped_into_enriched_document_references(mocks):
    from src.api.services.chat_service import process_chat
    from src.storage.models import Document, DocumentClassification

    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        url="https://example.org/maize-guide.pdf",
        public_source_url="https://example.org/maize-guide.pdf",
        title="Maize Drying Guide",
        site_name="naro",
        publicly_visible=True,
    )
    document.classification = DocumentClassification(
        summary="A practical guide to safe moisture targets and drying methods.",
        topics=["drying", "quality_control"],
        document_category="extension_guide",
    )
    mocks["vector_db"].search.return_value = [
        {
            "id": "chunk-one",
            "score": 0.91,
            "payload": {
                "document_id": str(document_id),
                "text": "Dry maize before storage.",
                "source_url": document.url,
            },
        },
        {
            "id": "chunk-two",
            "score": 0.86,
            "payload": {
                "document_id": str(document_id),
                "text": "Use a moisture meter where possible.",
                "source_url": document.url,
            },
        },
    ]
    session = _make_session(mocks["session_id"])
    mocks["db"].get.side_effect = lambda model, value: document if model is Document else session

    result = process_chat(
        request=_make_request(mocks["session_id"]),
        db=mocks["db"],
        llm_client=mocks["llm"],
        embedding_client=mocks["embedding"],
        vector_db_client=mocks["vector_db"],
        translation_client=mocks["translation"],
    )

    assert len(result.sources) == 1
    source = result.sources[0]
    assert source.title == "Maize Drying Guide"
    assert source.summary.startswith("A practical guide")
    assert source.citation_indices == [1, 2]
    assert source.library_url == f"/documents/{document_id}"


def test_suggestions_mix_reviewed_catalogue_and_generated_questions(mocks):
    from src.api.services.chat_service import _suggest_questions
    from src.storage.models import CatalogueEntry, CatalogueStatusEnum

    entry = CatalogueEntry(
        id=uuid.uuid4(),
        question_en="How can maize moisture be measured?",
        answer_en="Use a calibrated moisture meter.",
        status=CatalogueStatusEnum.approved,
    )
    catalogue_vectors = MagicMock()
    catalogue_vectors.search.return_value = [
        {
            "id": str(entry.id),
            "score": 0.78,
            "payload": {"catalogue_entry_id": str(entry.id)},
        }
    ]
    mocks["db"].get.return_value = entry
    mocks["llm"].suggest_followup_questions.return_value = ["Which drying surface is safest?"]

    with patch("src.api.services.chat_service.settings") as config:
        config.catalogue_match_observation_threshold = 0.0
        config.catalogue_suggestion_threshold = 0.65
        result = _suggest_questions(
            mocks["db"],
            llm_client=mocks["llm"],
            translation_client=mocks["translation"],
            catalogue_vector_db_client=catalogue_vectors,
            query_vector=[0.1] * 1536,
            question="How should maize be dried?",
            answer="Dry it to a safe moisture content.",
            chunks=[{"text": "Dry maize on a clean surface."}],
            language="eng",
        )

    assert [item.kind for item in result] == ["catalogue", "generated"]
    assert result[0].catalogue_entry_id == str(entry.id)
