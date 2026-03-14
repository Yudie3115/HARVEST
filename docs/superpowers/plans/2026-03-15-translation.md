# Translation Feature Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bidirectional translation between English and five Ugandan local languages (Luganda, Acholi, Runyankole, Ateso, Lugbara) to the Q&A and Search tabs of the Streamlit dashboard.

**Architecture:** A new `src/translation/` module wraps the Sunbird AI REST API (`/tasks/language_id` and `/tasks/nllb_translate`). The existing RAG pipeline is untouched — translation happens at the dashboard layer as a pre/post-processing step. All core components (embeddings, Qdrant, LLM) continue to operate on English text.

**Tech Stack:** Python 3.12, `httpx` (already installed), Pydantic Settings, Streamlit, Sunbird AI API, `pytest` + `unittest.mock`

**Spec:** `docs/superpowers/specs/2026-03-15-translation-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/translation/__init__.py` | Create | Public exports: `TranslationClient`, `TranslationError`, `SUPPORTED_LANGUAGES` |
| `src/translation/client.py` | Create | `TranslationClient` — Sunbird API calls, language detection, text chunking, retry logic |
| `src/config/settings.py` | Modify | Add 4 new translation settings fields |
| `.env.example` | Modify | Document the 4 new env vars |
| `tests/test_translation_client.py` | Create | Unit tests with mocked HTTP for all `TranslationClient` behaviours |
| `dashboard/app.py` | Modify | Wrap Q&A and Search with translation pre/post-processing |

---

## Chunk 1: Translation Module

### Task 1: Add settings fields and update `.env.example`

**Files:**
- Modify: `src/config/settings.py`
- Modify: `.env.example`

- [ ] **Step 1: Add 4 translation fields to `Settings` in `src/config/settings.py`**

  Open `src/config/settings.py`. After the `# Streamlit` block (around line 92), add a new section before the `# Development` block:

  ```python
  # Translation (Sunbird AI)
  sunbird_api_key: str = Field(default="")
  sunbird_api_url: str = Field(default="https://api.sunbird.ai")
  translation_enabled: bool = Field(default=True)
  translation_min_confidence: float = Field(default=0.80)
  ```

- [ ] **Step 2: Append translation section to `.env.example`**

  Add to the end of `.env.example`:

  ```dotenv
  # ── Translation (Sunbird AI) ──────────────────────────────────────────────────
  # Enables bidirectional translation for Ugandan local languages in the dashboard.
  # Supported languages: Luganda (lug), Acholi (ach), Runyankole (nyn),
  #                      Ateso (teo), Lugbara (lgg)
  # Get an API key at https://sunbird.ai
  # If SUNBIRD_API_KEY is empty, translation is automatically disabled (no network calls).
  SUNBIRD_API_KEY=your_sunbird_api_key_here
  SUNBIRD_API_URL=https://api.sunbird.ai
  TRANSLATION_ENABLED=true
  # Minimum confidence score (0–1) for language detection to trigger translation.
  # Inputs below this threshold are treated as English.
  TRANSLATION_MIN_CONFIDENCE=0.80
  ```

- [ ] **Step 3: Verify settings load without errors**

  ```bash
  cd /home/edwinm/git/post-harvest-knowledge-scraper
  python -c "from src.config.settings import settings; print(settings.sunbird_api_key, settings.translation_enabled, settings.translation_min_confidence)"
  ```

  Expected output: ` True 0.8`

- [ ] **Step 4: Commit**

  ```bash
  git add src/config/settings.py .env.example
  git commit -m "feat: add translation settings fields"
  ```

---

### Task 2: Create `TranslationError` and `SUPPORTED_LANGUAGES`

**Files:**
- Create: `src/translation/__init__.py`
- Create: `src/translation/client.py` (stub only — populated in Tasks 3 and 4)

- [ ] **Step 1: Write the failing test**

  Create `tests/test_translation_client.py`:

  ```python
  """
  Unit tests for TranslationClient (all HTTP mocked – no real API calls)
  """
  import pytest
  from unittest.mock import MagicMock, patch


  class TestImports:
      def test_translation_error_is_importable(self):
          from src.translation import TranslationError
          assert issubclass(TranslationError, Exception)

      def test_supported_languages_has_six_entries(self):
          from src.translation import SUPPORTED_LANGUAGES
          assert set(SUPPORTED_LANGUAGES.keys()) == {"eng", "lug", "ach", "nyn", "teo", "lgg"}

      def test_translation_client_is_importable(self):
          from src.translation import TranslationClient
          assert TranslationClient is not None
  ```

- [ ] **Step 2: Run test — expect FAIL**

  ```bash
  pytest tests/test_translation_client.py::TestImports -v
  ```

  Expected: `ModuleNotFoundError: No module named 'src.translation'`

- [ ] **Step 3: Create `src/translation/client.py` stub**

  ```python
  """
  Sunbird AI translation client
  """


  class TranslationError(Exception):
      """Raised when a Sunbird API call fails permanently."""


  class TranslationClient:
      pass
  ```

- [ ] **Step 4: Create `src/translation/__init__.py`**

  ```python
  from src.translation.client import TranslationClient, TranslationError

  SUPPORTED_LANGUAGES: dict[str, str] = {
      "lug": "Luganda",
      "ach": "Acholi",
      "nyn": "Runyankole",
      "teo": "Ateso",
      "lgg": "Lugbara",
      "eng": "English",
  }

  __all__ = ["TranslationClient", "TranslationError", "SUPPORTED_LANGUAGES"]
  ```

- [ ] **Step 5: Run tests — expect PASS**

  ```bash
  pytest tests/test_translation_client.py::TestImports -v
  ```

  Expected: 3 passed

- [ ] **Step 6: Commit**

  ```bash
  git add src/translation/__init__.py src/translation/client.py tests/test_translation_client.py
  git commit -m "feat: add TranslationError, SUPPORTED_LANGUAGES, and TranslationClient stub"
  ```

---

### Task 3: Implement `TranslationClient.__init__` and `translate()`

**Files:**
- Modify: `src/translation/client.py`
- Modify: `tests/test_translation_client.py`

The `translate()` method calls `POST /tasks/nllb_translate` with body `{"source_language": <code>, "target_language": <code>, "text": <text>}` and `Authorization: Bearer <api_key>` header. The response JSON has a `"translated_text"` field.

- [ ] **Step 1: Write failing tests for `translate()`**

  Append to `tests/test_translation_client.py`:

  ```python
  def _make_client(sunbird_api_key="test-key", translation_min_confidence=0.80):
      """Helper: build a TranslationClient with patched settings."""
      with patch("src.translation.client.settings") as mock_settings:
          mock_settings.sunbird_api_key = sunbird_api_key
          mock_settings.sunbird_api_url = "https://api.sunbird.ai"
          mock_settings.translation_min_confidence = translation_min_confidence
          from src.translation.client import TranslationClient
          return TranslationClient()


  class TestTranslate:
      def test_identity_returns_original_without_network_call(self):
          """source == target → return original text immediately, no HTTP."""
          client = _make_client()
          with patch("httpx.Client") as mock_httpx:
              result = client.translate("Hello", "eng", "eng")
          assert result == "Hello"
          mock_httpx.assert_not_called()

      def test_too_long_raises_translation_error(self):
          from src.translation import TranslationError
          client = _make_client()
          long_text = "a" * 10_001
          with pytest.raises(TranslationError, match="Input too long"):
              client.translate(long_text, "eng", "lug")

      def test_empty_api_key_raises_translation_error_without_network(self):
          from src.translation import TranslationError
          client = _make_client(sunbird_api_key="")
          with patch("httpx.Client") as mock_httpx:
              with pytest.raises(TranslationError):
                  client.translate("Hello", "eng", "lug")
          mock_httpx.assert_not_called()

      def test_short_text_translates_in_single_request(self):
          client = _make_client()
          mock_response = MagicMock()
          mock_response.status_code = 200
          mock_response.json.return_value = {"translated_text": "Oli otya"}
          with patch("httpx.Client") as mock_httpx_cls:
              mock_http = MagicMock()
              mock_http.__enter__ = MagicMock(return_value=mock_http)
              mock_http.__exit__ = MagicMock(return_value=False)
              mock_http.post.return_value = mock_response
              mock_httpx_cls.return_value = mock_http
              result = client.translate("How are you?", "eng", "lug")
          assert result == "Oli otya"
          assert mock_http.post.call_count == 1

      def test_transient_error_retries_and_succeeds(self):
          """503 on first attempt, 200 on second → succeeds."""
          client = _make_client()
          fail_response = MagicMock()
          fail_response.status_code = 503
          ok_response = MagicMock()
          ok_response.status_code = 200
          ok_response.json.return_value = {"translated_text": "Wayigiriza ki?"}
          with patch("httpx.Client") as mock_httpx_cls:
              mock_http = MagicMock()
              mock_http.__enter__ = MagicMock(return_value=mock_http)
              mock_http.__exit__ = MagicMock(return_value=False)
              mock_http.post.side_effect = [fail_response, ok_response]
              mock_httpx_cls.return_value = mock_http
              with patch("time.sleep"):  # suppress backoff delay in tests
                  result = client.translate("What did you learn?", "eng", "nyn")
          assert result == "Wayigiriza ki?"
          assert mock_http.post.call_count == 2

      def test_permanent_failure_raises_translation_error(self):
          """503 on all 3 attempts → TranslationError."""
          from src.translation import TranslationError
          client = _make_client()
          fail_response = MagicMock()
          fail_response.status_code = 503
          with patch("httpx.Client") as mock_httpx_cls:
              mock_http = MagicMock()
              mock_http.__enter__ = MagicMock(return_value=mock_http)
              mock_http.__exit__ = MagicMock(return_value=False)
              mock_http.post.return_value = fail_response
              mock_httpx_cls.return_value = mock_http
              with patch("time.sleep"):
                  with pytest.raises(TranslationError):
                      client.translate("Hello", "eng", "lug")
          assert mock_http.post.call_count == 3

      def test_long_text_split_into_paragraphs_and_rejoined(self):
          """Text with \\n\\n separators is split, each chunk translated, rejoined with \\n\\n."""
          client = _make_client()
          # Two paragraphs, each under 500 chars, but total > 500 to trigger chunked path
          para1 = "First paragraph about maize storage. " * 8   # ~296 chars
          para2 = "Second paragraph about drying methods. " * 8  # ~312 chars
          text = para1.strip() + "\n\n" + para2.strip()          # ~610 chars total
          responses = [
              MagicMock(status_code=200, **{"json.return_value": {"translated_text": "Omurongo ogwa kubiri."}}),
              MagicMock(status_code=200, **{"json.return_value": {"translated_text": "Omurongo ogwa kabiri."}}),
          ]
          with patch("httpx.Client") as mock_httpx_cls:
              mock_http = MagicMock()
              mock_http.__enter__ = MagicMock(return_value=mock_http)
              mock_http.__exit__ = MagicMock(return_value=False)
              mock_http.post.side_effect = responses
              mock_httpx_cls.return_value = mock_http
              result = client.translate(text, "eng", "lug")
          assert result == "Omurongo ogwa kubiri.\n\nOmurongo ogwa kabiri."
          assert mock_http.post.call_count == 2

      def test_translate_to_english_propagates_error(self):
          """translate_to_english raises TranslationError when API is down."""
          from src.translation import TranslationError
          client = _make_client(sunbird_api_key="")
          with pytest.raises(TranslationError):
              client.translate_to_english("Oli otya", "lug")

      def test_translate_from_english_propagates_error(self):
          """translate_from_english raises TranslationError when API is down."""
          from src.translation import TranslationError
          client = _make_client(sunbird_api_key="")
          with pytest.raises(TranslationError):
              client.translate_from_english("Hello", "lug")
  ```

- [ ] **Step 2: Run tests — expect FAIL**

  ```bash
  pytest tests/test_translation_client.py::TestTranslate -v
  ```

  Expected: all fail (methods not implemented)

- [ ] **Step 3: Implement `TranslationClient.__init__` and `translate()` in `src/translation/client.py`**

  Replace the file contents:

  ```python
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

      # ------------------------------------------------------------------
      # Internal helpers
      # ------------------------------------------------------------------

      def _translate_chunk(self, text: str, source_lang: str, target_lang: str) -> str:
          """Send a single translation request with retry logic."""
          url = f"{self._base_url}/tasks/nllb_translate"
          payload = {
              "source_language": source_lang,
              "target_language": target_lang,
              "text": text,
          }
          headers = {
              "Authorization": f"Bearer {self._api_key}",
              "Content-Type": "application/json",
          }

          last_exc: Exception | None = None
          for attempt in range(_MAX_RETRIES):
              try:
                  with httpx.Client(timeout=self._timeout) as client:
                      response = client.post(url, json=payload, headers=headers)

                  if response.status_code == 200:
                      return response.json()["translated_text"]

                  if response.status_code in _TRANSIENT_STATUS_CODES:
                      wait = 2 ** attempt
                      logger.warning(
                          f"Sunbird translate returned {response.status_code}, "
                          f"retrying in {wait}s (attempt {attempt + 1}/{_MAX_RETRIES})"
                      )
                      time.sleep(wait)
                      continue

                  # Non-retryable HTTP error
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
          ) from last_exc

      def _split_text(self, text: str) -> list[tuple[str, str]]:
          """Split text on paragraph boundaries, then sentence boundaries if needed."""
          paragraphs = text.split("\n\n")
          chunks: list[str] = []
          for para in paragraphs:
              if len(para) <= _CHUNK_SIZE:
                  chunks.append(("para", para))
              else:
                  # Split on sentence boundaries
                  sentences = para.split(". ")
                  chunks.extend(("sent", s) for s in sentences if s.strip())
          return chunks

      def _translate_chunked(
          self, text: str, source_lang: str, target_lang: str
      ) -> str:
          """Translate multi-chunk text, preserving paragraph structure."""
          raw_chunks = self._split_text(text)
          translated: list[tuple[str, str]] = []
          for kind, chunk in raw_chunks:
              t = self._translate_chunk(chunk, source_lang, target_lang)
              translated.append((kind, t))

          # Rejoin: paragraph boundaries → \n\n, sentence boundaries → space
          result_parts: list[str] = []
          i = 0
          while i < len(translated):
              kind, t = translated[i]
              if kind == "para":
                  result_parts.append(t)
                  i += 1
              else:
                  # Accumulate consecutive sentence chunks into one paragraph
                  sent_group = [t]
                  i += 1
                  while i < len(translated) and translated[i][0] == "sent":
                      sent_group.append(translated[i][1])
                      i += 1
                  result_parts.append(" ".join(sent_group))
          return "\n\n".join(result_parts)
  ```

- [ ] **Step 4: Run tests — expect PASS**

  ```bash
  pytest tests/test_translation_client.py::TestTranslate -v
  ```

  Expected: all 9 tests pass

- [ ] **Step 5: Commit**

  ```bash
  git add src/translation/client.py tests/test_translation_client.py
  git commit -m "feat: implement TranslationClient.translate() with retry and chunking"
  ```

---

### Task 4: Implement `TranslationClient.detect_language()`

**Files:**
- Modify: `src/translation/client.py`
- Modify: `tests/test_translation_client.py`

The language detection endpoint: `POST /tasks/language_id` with body `{"text": <text>}`. Response JSON contains `"language"` (code string) and `"confidence"` (float 0–1).

- [ ] **Step 1: Write failing tests for `detect_language()`**

  Append to `tests/test_translation_client.py`:

  ```python
  class TestDetectLanguage:
      def test_high_confidence_returns_language_code(self):
          client = _make_client()
          mock_response = MagicMock()
          mock_response.status_code = 200
          mock_response.json.return_value = {"language": "lug", "confidence": 0.95}
          with patch("httpx.Client") as mock_httpx_cls:
              mock_http = MagicMock()
              mock_http.__enter__ = MagicMock(return_value=mock_http)
              mock_http.__exit__ = MagicMock(return_value=False)
              mock_http.post.return_value = mock_response
              mock_httpx_cls.return_value = mock_http
              result = client.detect_language("Oli otya")
          assert result == "lug"

      def test_low_confidence_returns_none(self):
          """Confidence below threshold → None (treat as English)."""
          client = _make_client(translation_min_confidence=0.80)
          mock_response = MagicMock()
          mock_response.status_code = 200
          mock_response.json.return_value = {"language": "lug", "confidence": 0.60}
          with patch("httpx.Client") as mock_httpx_cls:
              mock_http = MagicMock()
              mock_http.__enter__ = MagicMock(return_value=mock_http)
              mock_http.__exit__ = MagicMock(return_value=False)
              mock_http.post.return_value = mock_response
              mock_httpx_cls.return_value = mock_http
              result = client.detect_language("test")
          assert result is None

      def test_english_detection_returns_none(self):
          """Detecting 'eng' returns None — no translation needed."""
          client = _make_client()
          mock_response = MagicMock()
          mock_response.status_code = 200
          mock_response.json.return_value = {"language": "eng", "confidence": 0.99}
          with patch("httpx.Client") as mock_httpx_cls:
              mock_http = MagicMock()
              mock_http.__enter__ = MagicMock(return_value=mock_http)
              mock_http.__exit__ = MagicMock(return_value=False)
              mock_http.post.return_value = mock_response
              mock_httpx_cls.return_value = mock_http
              result = client.detect_language("How are you?")
          assert result is None

      def test_empty_api_key_returns_none_without_network(self):
          client = _make_client(sunbird_api_key="")
          with patch("httpx.Client") as mock_httpx:
              result = client.detect_language("Oli otya")
          assert result is None
          mock_httpx.assert_not_called()

      def test_api_failure_returns_none(self):
          """Any API error during detection → None (degrade gracefully)."""
          client = _make_client()
          with patch("httpx.Client") as mock_httpx_cls:
              mock_http = MagicMock()
              mock_http.__enter__ = MagicMock(return_value=mock_http)
              mock_http.__exit__ = MagicMock(return_value=False)
              mock_http.post.side_effect = Exception("connection refused")
              mock_httpx_cls.return_value = mock_http
              result = client.detect_language("Oli otya")
          assert result is None

      def test_unsupported_language_returns_none(self):
          """Language code not in SUPPORTED_LANGUAGES → None."""
          client = _make_client()
          mock_response = MagicMock()
          mock_response.status_code = 200
          mock_response.json.return_value = {"language": "fra", "confidence": 0.97}
          with patch("httpx.Client") as mock_httpx_cls:
              mock_http = MagicMock()
              mock_http.__enter__ = MagicMock(return_value=mock_http)
              mock_http.__exit__ = MagicMock(return_value=False)
              mock_http.post.return_value = mock_response
              mock_httpx_cls.return_value = mock_http
              result = client.detect_language("Bonjour")
          assert result is None
  ```

- [ ] **Step 2: Run tests — expect FAIL**

  ```bash
  pytest tests/test_translation_client.py::TestDetectLanguage -v
  ```

  Expected: all fail (`detect_language` not implemented)

- [ ] **Step 3: Add `detect_language()` to `TranslationClient` in `src/translation/client.py`**

  Add after `translate_from_english()`:

  ```python
      def detect_language(self, text: str) -> str | None:
          """Detect the language of text.

          Returns a language code (e.g. "lug") if detected with confidence
          >= settings.translation_min_confidence and the code is in
          SUPPORTED_LANGUAGES (excluding "eng", which needs no translation).
          Returns None on low confidence, unsupported language, English, or any
          API failure.
          """
          if not self._api_key:
              return None

          url = f"{self._base_url}/tasks/language_id"
          headers = {
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
              confidence = data.get("confidence", 0.0)

              if confidence < self._min_confidence:
                  return None

              from src.translation import SUPPORTED_LANGUAGES
              if lang not in SUPPORTED_LANGUAGES or lang == "eng":
                  return None

              return lang

          except Exception as exc:
              logger.warning(f"Language detection failed: {exc}")
              return None
  ```

- [ ] **Step 4: Run all translation tests — expect PASS**

  ```bash
  pytest tests/test_translation_client.py -v
  ```

  Expected: all tests pass

- [ ] **Step 5: Run full test suite to check for regressions**

  ```bash
  pytest --tb=short -q
  ```

  Expected: all existing tests still pass

- [ ] **Step 6: Commit**

  ```bash
  git add src/translation/client.py tests/test_translation_client.py
  git commit -m "feat: implement detect_language() with confidence threshold and graceful degradation"
  ```

---

## Chunk 2: Dashboard Integration

### Task 5: Integrate translation into the Q&A tab

**Files:**
- Modify: `dashboard/app.py`

The existing `_answer_question()` returns `tuple[str | None, list]`. This task changes it to `tuple[str | None, list, str | None]` and adds the translation pre/post-processing.

- [ ] **Step 1: Add a `_get_translator()` cache helper at the top of `dashboard/app.py`**

  After the `_get_llm()` function (around line 44), add:

  ```python
  @st.cache_resource(ttl=3600)
  def _get_translator():
      try:
          from src.config.settings import settings
          if not settings.translation_enabled:
              return None
          from src.translation import TranslationClient
          return TranslationClient()
      except Exception:
          return None
  ```

- [ ] **Step 2: Update `_answer_question()` return type and body**

  Replace the entire `_answer_question` function (lines 131–144):

  ```python
  def _answer_question(
      question: str, top_k: int, score_threshold: float
  ) -> tuple[str | None, list, str | None]:
      """Retrieve relevant chunks and synthesise a grounded answer.

      Returns (answer, results, detected_lang).
      detected_lang is None when the question is English or translation is disabled.
      """
      from src.config.settings import settings
      from src.translation import TranslationError, SUPPORTED_LANGUAGES

      detected_lang: str | None = None
      english_question = question

      # --- Translation: query → English ---
      if settings.translation_enabled:
          translator = _get_translator()
          if translator is not None:
              detected_lang = translator.detect_language(question)
              if detected_lang is not None:
                  try:
                      english_question = translator.translate_to_english(question, detected_lang)
                  except TranslationError as exc:
                      st.warning(f"Could not translate your question — searching in original language. ({exc})")
                      detected_lang = None

      results = _semantic_search(english_question, top_k)
      results = [r for r in results if r.get("score", 0) >= score_threshold]
      if not results:
          return None, [], None

      chunk_payloads = [r["payload"] for r in results]
      llm = _get_llm()
      if llm is None:
          return None, results, None

      answer = llm.answer_question(english_question, chunk_payloads)

      # --- Translation: answer → local language ---
      if detected_lang is not None and settings.translation_enabled:
          translator = _get_translator()
          if translator is not None:
              try:
                  answer = translator.translate_from_english(answer, detected_lang)
              except TranslationError:
                  answer = answer + "\n\n*(Could not translate answer — showing in English)*"

      return answer, results, detected_lang
  ```

- [ ] **Step 3: Update the call site**

  Find this line by searching for the string (line number will have shifted from previous edits):

  ```python
  answer, results = _answer_question(question.strip(), qa_top_k, qa_threshold)
  ```

  Replace with:

  ```python
  answer, results, detected_lang = _answer_question(question.strip(), qa_top_k, qa_threshold)
  ```

- [ ] **Step 4: Add language badge to the Q&A answer display**

  Find the block immediately after the `_answer_question` call that shows the answer:

  ```python
          if answer is None and not results:
  ```

  After the `st.divider()` before `st.markdown("**Answer:**")`, add:

  ```python
              if detected_lang is not None:
                  from src.translation import SUPPORTED_LANGUAGES
                  lang_name = SUPPORTED_LANGUAGES.get(detected_lang, detected_lang)
                  st.caption(f"Detected: {lang_name} — answering in {lang_name}")
  ```

  The full block should look like:

  ```python
          else:
              st.divider()
              if detected_lang is not None:
                  from src.translation import SUPPORTED_LANGUAGES
                  lang_name = SUPPORTED_LANGUAGES.get(detected_lang, detected_lang)
                  st.caption(f"Detected: {lang_name} — answering in {lang_name}")
              st.markdown("**Answer:**")
              st.info(answer)
              # ... rest of sources display unchanged
  ```

- [ ] **Step 5: Smoke-test dashboard startup**

  ```bash
  cd /home/edwinm/git/post-harvest-knowledge-scraper
  python -c "import ast, sys; ast.parse(open('dashboard/app.py').read()); print('Syntax OK')"
  ```

  Expected: `Syntax OK`

- [ ] **Step 6: Run full test suite**

  ```bash
  pytest --tb=short -q
  ```

  Expected: all tests pass

- [ ] **Step 7: Commit**

  ```bash
  git add dashboard/app.py
  git commit -m "feat: add translation to Q&A tab — auto-detect language, round-trip translation"
  ```

---

### Task 6: Integrate translation into the Search tab

**Files:**
- Modify: `dashboard/app.py`

- [ ] **Step 1: Wrap the search query with translation in the Search tab block**

  Find the Search tab (Tab 3) block. The current query handling starts with:

  ```python
      if query:
          with st.spinner("Searching…"):
              results = _semantic_search(query, top_k=top_k)
  ```

  Replace with:

  ```python
      if query:
          with st.spinner("Searching…"):
              from src.config.settings import settings
              search_query = query
              search_lang: str | None = None
              if settings.translation_enabled:
                  translator = _get_translator()
                  if translator is not None:
                      search_lang = translator.detect_language(query)
                      if search_lang is not None:
                          try:
                              from src.translation import TranslationError
                              search_query = translator.translate_to_english(query, search_lang)
                          except TranslationError:
                              search_lang = None
              results = _semantic_search(search_query, top_k=top_k)
  ```

- [ ] **Step 2: Show translation caption when translation occurred**

  Immediately after `results = _semantic_search(search_query, top_k=top_k)` and before `if results:`, add:

  ```python
          if search_lang is not None:
              from src.translation import SUPPORTED_LANGUAGES
              lang_name = SUPPORTED_LANGUAGES.get(search_lang, search_lang)
              st.caption(f"Searching in English (translated from {lang_name})")
  ```

- [ ] **Step 3: Smoke-test syntax**

  ```bash
  python -c "import ast; ast.parse(open('dashboard/app.py').read()); print('Syntax OK')"
  ```

  Expected: `Syntax OK`

- [ ] **Step 4: Run full test suite**

  ```bash
  pytest --tb=short -q
  ```

  Expected: all tests pass

- [ ] **Step 5: Commit**

  ```bash
  git add dashboard/app.py
  git commit -m "feat: add translation to Search tab — auto-detect and translate query to English"
  ```

---

### Task 7: Final wiring check and connection status

**Files:**
- Modify: `dashboard/app.py`

Add Sunbird AI to the System Status connection check so operators can see whether the translation service is reachable.

- [ ] **Step 1: Add Sunbird check to `_check_connections()`**

  Find the `_check_connections` function. After the `"LLM Service"` block, add:

  ```python
      # Sunbird AI (translation)
      try:
          from src.config.settings import settings
          if settings.translation_enabled and settings.sunbird_api_key:
              from src.translation import TranslationClient
              t = TranslationClient()
              # Cheap probe: detect language on a known English string
              t.detect_language("test")
              results["Sunbird AI (Translation)"] = True
          else:
              results["Sunbird AI (Translation)"] = False
      except Exception:
          results["Sunbird AI (Translation)"] = False
  ```

- [ ] **Step 2: Syntax check**

  ```bash
  python -c "import ast; ast.parse(open('dashboard/app.py').read()); print('Syntax OK')"
  ```

- [ ] **Step 3: Run full test suite one final time**

  ```bash
  pytest --tb=short -q
  ```

  Expected: all tests pass

- [ ] **Step 4: Final commit**

  ```bash
  git add dashboard/app.py
  git commit -m "feat: add Sunbird AI translation to connection status check"
  ```
