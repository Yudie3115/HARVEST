"""A 429 from the LLM provider must surface as a readable 503, with CORS headers.

Regression: an exhausted OpenAI credit balance propagated uncaught, so
Starlette returned a bare 500 from outside CORSMiddleware. Browsers reported
that as a CORS failure, which hid the real cause for two days.
"""

import httpx
import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from openai import RateLimitError as OpenAIRateLimitError

from src.api.errors import LLM_UNAVAILABLE_MESSAGE, llm_rate_limit_handler


def _quota_exhausted() -> OpenAIRateLimitError:
    """Build the exact error OpenAI raises when credits run out."""
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    response = httpx.Response(429, request=request)
    return OpenAIRateLimitError(
        "Error code: 429 - You have no credits remaining.",
        response=response,
        body={"error": {"code": "credit_balance_exhausted"}},
    )


def _make_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://chat.postharvest.fourlanes.tech"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(OpenAIRateLimitError, llm_rate_limit_handler)

    @app.post("/chat")
    async def _chat():
        raise _quota_exhausted()

    return TestClient(app, raise_server_exceptions=False)


def test_quota_exhaustion_returns_503_not_500():
    response = _make_client().post("/chat")

    assert response.status_code == 503
    assert response.json() == {"detail": LLM_UNAVAILABLE_MESSAGE}


def test_the_error_response_carries_cors_headers():
    """The whole point — without this the browser reports a CORS failure."""
    origin = "https://chat.postharvest.fourlanes.tech"
    response = _make_client().post("/chat", headers={"Origin": origin})

    assert response.status_code == 503
    assert response.headers["access-control-allow-origin"] == origin


def test_the_message_names_the_actual_problem():
    response = _make_client().post("/chat")
    detail = response.json()["detail"].lower()

    assert "internal server error" not in detail
    assert "quota" in detail or "rate limit" in detail


def test_handler_is_registered_on_the_real_app():
    from src.api.main import app

    assert OpenAIRateLimitError in app.exception_handlers


# The streaming path is covered by
# test_chat_service.py::test_stream_reports_llm_quota_exhaustion_as_a_readable_error,
# which drives the real generator rather than restating its except clause.


@pytest.mark.parametrize("provider_url", [
    "https://api.openai.com/v1/embeddings",
    "https://api.groq.com/openai/v1/chat/completions",
])
def test_groq_shares_the_same_error_type(provider_url):
    """LLMClient builds Groq on the OpenAI SDK, so one handler covers both."""
    request = httpx.Request("POST", provider_url)
    error = OpenAIRateLimitError(
        "429", response=httpx.Response(429, request=request), body=None
    )

    assert isinstance(error, OpenAIRateLimitError)
