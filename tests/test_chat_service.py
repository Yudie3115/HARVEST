"""
Unit tests for process_chat — verifying history is passed to answer_question.
"""
import uuid
from unittest.mock import MagicMock
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
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = prior_messages

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
    assert history[1] == {"role": "assistant", "content": "Dry maize in the sun to below 13.5% moisture."}
    assert history[2] == {"role": "user", "content": "How long does it take?"}
    assert history[3] == {"role": "assistant", "content": "Usually 3–5 days depending on weather."}


def test_history_capped_at_six_messages(mocks):
    """Only the last 6 prior messages are passed as history (3 full turns)."""
    from src.api.services.chat_service import process_chat

    # 8 prior messages in descending order (newest first, as returned by DB)
    many_messages = [
        _make_message("user", f"question {i}") if i % 2 == 0 else _make_message("assistant", f"answer {i}")
        for i in range(7, -1, -1)
    ]
    mocks["db"].query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = many_messages

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

    mocks["db"].query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

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
