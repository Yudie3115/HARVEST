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

    def test_non_retryable_error_fails_fast(self):
        """400/401 should raise TranslationError immediately without retrying."""
        from src.translation import TranslationError
        client = _make_client()
        fail_response = MagicMock()
        fail_response.status_code = 401
        fail_response.text = "Unauthorized"
        with patch("httpx.Client") as mock_httpx_cls:
            mock_http = MagicMock()
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_http.post.return_value = fail_response
            mock_httpx_cls.return_value = mock_http
            with pytest.raises(TranslationError):
                client.translate("Hello", "eng", "lug")
        assert mock_http.post.call_count == 1


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
