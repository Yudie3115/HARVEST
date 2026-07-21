"""Unit tests for src.api.services.access_service."""
import hashlib
import hmac

import pytest


@pytest.fixture(autouse=True)
def _fixed_secret(monkeypatch):
    from src.config import settings as settings_module
    monkeypatch.setattr(settings_module.settings, "access_hash_secret", "test-secret")
    yield


class TestNormalizeCode:
    def test_trims_and_lowercases(self):
        from src.api.services.access_service import normalize_code
        assert normalize_code("  Mango-River-Granary  ") == "mango-river-granary"

    def test_collapses_whitespace_separators(self):
        from src.api.services.access_service import normalize_code
        assert normalize_code("mango   river   granary") == "mango-river-granary"

    def test_collapses_repeated_hyphens_and_underscores(self):
        from src.api.services.access_service import normalize_code
        assert normalize_code("mango--river__granary") == "mango-river-granary"

    def test_already_normalized_is_unchanged(self):
        from src.api.services.access_service import normalize_code
        assert normalize_code("mango-river-granary") == "mango-river-granary"


class TestGenerateCode:
    def test_returns_three_hyphenated_words(self):
        from src.api.services.access_service import generate_code, normalize_code
        code = generate_code()
        assert code == normalize_code(code)  # already normalized
        parts = code.split("-")
        assert len(parts) == 3
        assert all(part.isalpha() for part in parts)

    def test_words_come_from_the_committed_word_list(self):
        from pathlib import Path
        from src.api.services.access_service import generate_code

        wordlist_path = (
            Path(__file__).resolve().parents[1]
            / "src" / "api" / "services" / "wordlists" / "access_code_words_v1.txt"
        )
        allowed = set(wordlist_path.read_text().split())
        for _ in range(20):
            for part in generate_code().split("-"):
                assert part in allowed

    def test_successive_calls_are_not_all_identical(self):
        from src.api.services.access_service import generate_code
        codes = {generate_code() for _ in range(10)}
        assert len(codes) > 1


class TestHashCode:
    def test_matches_manual_hmac_sha256(self):
        from src.api.services.access_service import hash_code
        expected = hmac.new(
            b"test-secret", b"access_code:mango-river-granary", hashlib.sha256
        ).hexdigest()
        assert hash_code("mango-river-granary") == expected

    def test_is_deterministic(self):
        from src.api.services.access_service import hash_code
        assert hash_code("mango-river-granary") == hash_code("mango-river-granary")

    def test_different_codes_hash_differently(self):
        from src.api.services.access_service import hash_code
        assert hash_code("mango-river-granary") != hash_code("apple-river-granary")


class TestHashToken:
    def test_matches_plain_sha256(self):
        from src.api.services.access_service import hash_token
        token = "abc123"
        assert hash_token(token) == hashlib.sha256(token.encode()).hexdigest()


class TestHashIdentifier:
    def test_domain_separation_changes_the_digest(self):
        from src.api.services.access_service import hash_identifier
        a = hash_identifier("+256700000000", domain="domain-a")
        b = hash_identifier("+256700000000", domain="domain-b")
        assert a != b

    def test_matches_manual_domain_separated_hmac(self):
        from src.api.services.access_service import hash_identifier
        expected = hmac.new(
            b"test-secret", b"domain-a:+256700000000", hashlib.sha256
        ).hexdigest()
        assert hash_identifier("+256700000000", domain="domain-a") == expected


class TestGenerateWebToken:
    def test_returns_high_entropy_url_safe_string(self):
        from src.api.services.access_service import generate_web_token
        token = generate_web_token()
        assert len(token) >= 32
        assert token != generate_web_token()
