"""Shared handling for upstream LLM failures.

A 429 from OpenAI (rate limit, or an exhausted credit balance) used to
propagate uncaught. Starlette's ServerErrorMiddleware then returned a bare
500 — and because that middleware sits *outside* CORSMiddleware, the
response carried no Access-Control-Allow-Origin header, so browsers
reported it as a CORS failure rather than an upstream outage.

Registering this as an exception handler keeps the response inside the
middleware stack, so it gets CORS headers and a message that says what is
actually wrong.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger
from openai import RateLimitError

# 503 rather than 429: the client is not being rate limited, our upstream
# dependency is unavailable. Retrying the same request later is correct.
LLM_UNAVAILABLE_STATUS = 503
LLM_UNAVAILABLE_MESSAGE = (
    "The AI service is temporarily unavailable — its rate limit or credit "
    "quota has been exceeded. Please try again shortly."
)


async def llm_rate_limit_handler(request: Request, exc: RateLimitError) -> JSONResponse:
    """Return a readable 503 when the LLM provider refuses with a 429."""
    logger.error(
        f"Upstream LLM rate limit on {request.method} {request.url.path}: {exc}"
    )
    return JSONResponse(
        status_code=LLM_UNAVAILABLE_STATUS,
        content={"detail": LLM_UNAVAILABLE_MESSAGE},
    )
