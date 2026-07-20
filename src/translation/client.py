"""
Sunbird AI translation client
"""
import time
from loguru import logger

import httpx

from src.config.settings import settings


class TranslationError(Exception):
    """Raised when a Sunbird API call fails permanently."""


_TRANSIENT_STATUS_CODES = {429, 503, 504}
_MAX_RETRIES = 3
_CHUNK_SIZE = 500  # characters


class TranslationClient:

    def __init__(self):
        self._api_key = settings.sunbird_api_key
        self._base_url = settings.sunbird_api_url.rstrip("/")
        self._min_confidence = settings.translation_min_confidence
        self._timeout = httpx.Timeout(15.0, connect=5.0, read=15.0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate text between supported language codes.

        Evaluation order:
          1. source_lang == target_lang → return text unchanged (no network call).
          2. len(text) > 10,000 → raise TranslationError("Input too long").
          3. empty API key → raise TranslationError immediately (no network call).
          4. len(text) <= 500 → single API call.
          5. Otherwise → split on paragraph/sentence boundaries, translate each
             chunk, rejoin.
        """
        if source_lang == target_lang:
            return text

        if len(text) > 10_000:
            raise TranslationError("Input too long (max 10,000 characters)")

        if not self._api_key:
            raise TranslationError("SUNBIRD_API_KEY is not configured")

        if len(text) <= _CHUNK_SIZE:
            return self._translate_chunk(text, source_lang, target_lang)

        return self._translate_chunked(text, source_lang, target_lang)

    def translate_to_english(self, text: str, source_lang: str) -> str:
        """Convenience wrapper: translate from source_lang to English."""
        return self.translate(text, source_lang, "eng")

    def translate_from_english(self, text: str, target_lang: str) -> str:
        """Convenience wrapper: translate from English to target_lang."""
        return self.translate(text, "eng", target_lang)

    def check_connection(self) -> bool:
        """Return True if the Sunbird API is reachable and responds with 200."""
        if not self._api_key:
            return False
        url = f"{self._base_url}/tasks/language_id"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, json={"text": "test"}, headers=headers)
            return response.status_code == 200
        except Exception:
            return False

    def detect_language(self, text: str) -> str | None:
        """Detect the language of text.

        Returns a language code (e.g. "lug") if detected with confidence
        >= self._min_confidence and the code is in SUPPORTED_LANGUAGES
        (excluding "eng", which needs no translation).
        Returns None on low confidence, unsupported language, English, or any
        API failure.
        """
        if not self._api_key:
            return None

        url = f"{self._base_url}/tasks/language_id"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, json={"text": text}, headers=headers)

            if response.status_code != 200:
                logger.warning(f"Language detection returned {response.status_code}")
                return None

            data = response.json()
            lang = data.get("language")

            # The language_id API does not always return a confidence score.
            # Only apply the threshold when the field is explicitly present.
            confidence = data.get("confidence")
            if confidence is not None and confidence < self._min_confidence:
                return None

            from src.translation import SUPPORTED_LANGUAGES
            if lang not in SUPPORTED_LANGUAGES or lang == "eng":
                return None

            return lang

        except Exception as exc:
            logger.warning(f"Language detection failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _translate_chunk(self, text: str, source_lang: str, target_lang: str) -> str:
        """Send a single translation request with retry logic."""
        url = f"{self._base_url}/tasks/translate"
        payload = {
            "source_language": source_lang,
            "target_language": target_lang,
            "text": text,
        }
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        logger.debug(
            f"Sunbird translate → POST {url} "
            f"(source={source_lang}, target={target_lang}, len={len(text)})"
        )

        last_exc: Exception | None = None
        last_status: int | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(url, json=payload, headers=headers)

                logger.debug(
                    f"Sunbird translate ← {response.status_code} "
                    f"(attempt {attempt + 1}/{_MAX_RETRIES}), "
                    f"url={response.url}, body={response.text[:200]!r}"
                )

                if response.status_code == 200:
                    data = response.json()
                    # The API wraps the result: {"output": {"translated_text": ...}}
                    output = data.get("output", data)
                    if "translated_text" not in output:
                        raise TranslationError(
                            f"Sunbird API returned 200 but missing 'translated_text' key: {data}"
                        )
                    return output["translated_text"]

                if response.status_code in _TRANSIENT_STATUS_CODES:
                    last_status = response.status_code
                    wait = 2 ** attempt
                    logger.warning(
                        f"Sunbird translate returned {response.status_code}, "
                        f"retrying in {wait}s (attempt {attempt + 1}/{_MAX_RETRIES})"
                    )
                    time.sleep(wait)
                    continue

                # Non-retryable HTTP error — log full detail to aid debugging
                logger.error(
                    f"Sunbird translate failed: {response.status_code} {response.reason_phrase} "
                    f"url={response.url!r} body={response.text!r}"
                )
                raise TranslationError(
                    f"Sunbird API error {response.status_code}: {response.text}"
                )

            except TranslationError:
                raise
            except Exception as exc:
                # Network / timeout errors are treated as transient
                wait = 2 ** attempt
                logger.warning(
                    f"Sunbird translate network error: {exc}, "
                    f"retrying in {wait}s (attempt {attempt + 1}/{_MAX_RETRIES})"
                )
                last_exc = exc
                time.sleep(wait)

        raise TranslationError(
            f"Sunbird translate failed after {_MAX_RETRIES} attempts"
            + (f" (last status: {last_status})" if last_status else "")
        ) from last_exc

    def _translate_chunked(
        self, text: str, source_lang: str, target_lang: str
    ) -> str:
        """Translate text longer than _CHUNK_SIZE, one line at a time.

        Never sends a chunk spanning more than one original line to the
        translation API — markdown constructs (table rows, list items,
        headings) depend on line breaks, and an API call payload merging
        two lines together can't be trusted to preserve that boundary in
        its response. A single line still over _CHUNK_SIZE falls back to
        sentence-boundary splitting, rejoined with spaces.
        """
        lines = text.split("\n")
        translated_lines = []
        for line in lines:
            if not line.strip():
                translated_lines.append(line)
            elif len(line) <= _CHUNK_SIZE:
                translated_lines.append(self._translate_chunk(line, source_lang, target_lang))
            else:
                translated_lines.append(self._translate_long_line(line, source_lang, target_lang))
        return "\n".join(translated_lines)

    def _translate_long_line(self, line: str, source_lang: str, target_lang: str) -> str:
        """Translate a single line too long for one request, split on sentences."""
        sentences = line.split(". ")
        translated: list[str] = []
        for j, s in enumerate(sentences):
            if not s.strip():
                continue
            # Re-append period to all but the last fragment
            chunk_text = s if j == len(sentences) - 1 else s + "."
            translated.append(self._translate_chunk(chunk_text, source_lang, target_lang))
        return " ".join(translated)
