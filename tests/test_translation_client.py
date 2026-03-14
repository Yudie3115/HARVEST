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
