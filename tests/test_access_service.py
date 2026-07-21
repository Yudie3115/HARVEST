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


class TestAccessErrors:
    def test_error_codes_and_statuses_match_the_contract(self):
        from src.api.services.access_service import (
            AccessRequiredError, AccessInvalidError, AccessRevokedError,
            SessionForbiddenError, QuotaExhaustedError, GlobalLimitReachedError,
            RedemptionRateLimitedError,
        )
        expected = {
            AccessRequiredError: ("access_required", 401),
            AccessInvalidError: ("access_invalid", 401),
            AccessRevokedError: ("access_revoked", 403),
            SessionForbiddenError: ("session_forbidden", 403),
            QuotaExhaustedError: ("quota_exhausted", 429),
            GlobalLimitReachedError: ("global_limit_reached", 503),
            RedemptionRateLimitedError: ("redemption_rate_limited", 429),
        }
        for cls, (code, status) in expected.items():
            err = cls("some message")
            assert err.code == code
            assert err.http_status == status
            assert err.message == "some message"
            assert err.period_resets_at is None

    def test_quota_exhausted_carries_period_resets_at(self):
        import datetime
        from src.api.services.access_service import QuotaExhaustedError
        reset = datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc)
        err = QuotaExhaustedError("exhausted", period_resets_at=reset)
        assert err.period_resets_at == reset


# ---------------------------------------------------------------------------
# Integration tests against the real local Postgres database
# ---------------------------------------------------------------------------
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.config.settings import settings

_engine = create_engine(str(settings.database_url))
_Session = sessionmaker(bind=_engine)


def _make_db_session():
    return _Session()


def _insert_access_code(db, monthly_limit=5, status="active", period_start=None, code_hash=None):
    from src.storage.models import AccessCode
    code = AccessCode(
        id=uuid.uuid4(),
        code_hash=code_hash or uuid.uuid4().hex,
        label="Test Group",
        monthly_limit=monthly_limit,
        status=status,
        usage_count=0,
        period_start=period_start or datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ),
        created_by="tester",
    )
    db.add(code)
    db.commit()
    db.refresh(code)
    return code


def _reset_global_counter(db, usage_count=0, period_start=None):
    from src.storage.models import GlobalUsageCounter
    row = db.get(GlobalUsageCounter, 1)
    row.usage_count = usage_count
    row.period_start = period_start or datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    db.commit()


class TestResolveWebGrant:
    def test_missing_token_raises_access_required(self):
        from src.api.services.access_service import resolve_web_grant, AccessRequiredError
        db = _make_db_session()
        try:
            with pytest.raises(AccessRequiredError):
                resolve_web_grant(db, None)
        finally:
            db.close()

    def test_unknown_token_raises_access_invalid(self):
        from src.api.services.access_service import resolve_web_grant, AccessInvalidError
        db = _make_db_session()
        try:
            with pytest.raises(AccessInvalidError):
                resolve_web_grant(db, "nonexistent-token")
        finally:
            db.close()

    def test_active_web_grant_resolves(self):
        from src.api.services.access_service import resolve_web_grant, hash_token
        from src.storage.models import AccessGrant, ChannelEnum
        db = _make_db_session()
        try:
            code = _insert_access_code(db)
            token = f"web-token-abc-{uuid.uuid4().hex}"
            grant = AccessGrant(
                id=uuid.uuid4(),
                access_code_id=code.id,
                channel=ChannelEnum.web,
                identifier_hash=hash_token(token),
                status="active",
            )
            db.add(grant)
            db.commit()

            resolved = resolve_web_grant(db, token)
            assert resolved.grant.id == grant.id
            assert resolved.access_code.id == code.id
        finally:
            db.close()

    def test_revoked_code_still_resolves_grant(self):
        """resolve_web_grant does not gate on code status — callers do."""
        from src.api.services.access_service import resolve_web_grant, hash_token
        from src.storage.models import AccessGrant, ChannelEnum
        db = _make_db_session()
        try:
            code = _insert_access_code(db, status="revoked")
            token = f"web-token-revoked-{uuid.uuid4().hex}"
            db.add(AccessGrant(
                id=uuid.uuid4(), access_code_id=code.id, channel=ChannelEnum.web,
                identifier_hash=hash_token(token), status="active",
            ))
            db.commit()

            resolved = resolve_web_grant(db, token)
            assert resolved.access_code.status == "revoked"
        finally:
            db.close()


class TestRequireActiveCode:
    def test_active_code_passes(self):
        from src.api.services.access_service import require_active_code
        from src.storage.models import AccessCode
        require_active_code(AccessCode(status="active"))  # no exception

    def test_revoked_code_raises(self):
        from src.api.services.access_service import require_active_code, AccessRevokedError
        from src.storage.models import AccessCode
        with pytest.raises(AccessRevokedError):
            require_active_code(AccessCode(status="revoked"))


class TestReserveQuota:
    @pytest.fixture(autouse=True)
    def _reset_global_counter_before_and_after(self):
        """Reset the shared `global_usage_counters` singleton (id=1) to a
        clean state (usage_count=0, period_start=current UTC month start)
        both before and after every test in this class.

        This must use real, committed UPDATE statements rather than a
        db.rollback()-based transactional fixture: the singleton row is
        shared process-wide (not per-test), and
        test_concurrent_reservations_never_exceed_the_code_limit below
        spins up separate threads with their own sessions that issue real
        commits against it. A rollback in this fixture's own session would
        never see, and could not undo, commits made by other sessions/
        threads. So cleanup has to be an explicit real UPDATE + commit
        against the persistent DB, matching how the row actually gets
        mutated.
        """
        db = _make_db_session()
        try:
            _reset_global_counter(db, usage_count=0)
        finally:
            db.close()
        yield
        db = _make_db_session()
        try:
            _reset_global_counter(db, usage_count=0)
        finally:
            db.close()

    def test_successful_reservation_increments_both_counters(self):
        from src.api.services.access_service import reserve_quota
        db = _make_db_session()
        try:
            code = _insert_access_code(db, monthly_limit=5)
            _reset_global_counter(db, usage_count=0)

            reserve_quota(db, code.id)

            db.refresh(code)
            from src.storage.models import GlobalUsageCounter
            global_row = db.get(GlobalUsageCounter, 1)
            assert code.usage_count == 1
            assert global_row.usage_count == 1
        finally:
            db.close()

    def test_exhausted_code_quota_raises_quota_exhausted(self):
        from src.api.services.access_service import reserve_quota, QuotaExhaustedError
        db = _make_db_session()
        try:
            code = _insert_access_code(db, monthly_limit=1)
            _reset_global_counter(db, usage_count=0)
            reserve_quota(db, code.id)  # first message succeeds

            with pytest.raises(QuotaExhaustedError) as exc_info:
                reserve_quota(db, code.id)  # second exceeds monthly_limit=1
            assert exc_info.value.period_resets_at is not None
        finally:
            db.close()

    def test_revoked_code_raises_access_revoked(self):
        from src.api.services.access_service import reserve_quota, AccessRevokedError
        db = _make_db_session()
        try:
            code = _insert_access_code(db, monthly_limit=5, status="revoked")
            _reset_global_counter(db, usage_count=0)
            with pytest.raises(AccessRevokedError):
                reserve_quota(db, code.id)
        finally:
            db.close()

    def test_exhausted_global_quota_raises_global_limit_reached(self, monkeypatch):
        from src.config import settings as settings_module
        monkeypatch.setattr(settings_module.settings, "global_monthly_message_limit", 1)
        from src.api.services.access_service import reserve_quota, GlobalLimitReachedError
        db = _make_db_session()
        try:
            code_a = _insert_access_code(db, monthly_limit=5)
            code_b = _insert_access_code(db, monthly_limit=5)
            _reset_global_counter(db, usage_count=0)
            reserve_quota(db, code_a.id)  # brings global usage to 1 == limit

            with pytest.raises(GlobalLimitReachedError):
                reserve_quota(db, code_b.id)
        finally:
            db.close()

    def test_stale_period_start_lazily_resets_before_reserving(self):
        from src.api.services.access_service import reserve_quota
        db = _make_db_session()
        try:
            last_month = datetime.now(timezone.utc).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            ) - timedelta(days=1)
            last_month_start = last_month.replace(day=1)
            code = _insert_access_code(db, monthly_limit=1, period_start=last_month_start)
            db.execute(
                text("UPDATE access_codes SET usage_count = 1 WHERE id = :id"),
                {"id": code.id},
            )
            _reset_global_counter(db, usage_count=0, period_start=last_month_start)
            db.commit()

            reserve_quota(db, code.id)  # should not raise — stale period resets first

            db.refresh(code)
            assert code.usage_count == 1
        finally:
            db.close()

    def test_concurrent_reservations_never_exceed_the_code_limit(self):
        """Two threads race to reserve against a monthly_limit=1 code; exactly one wins."""
        import threading
        from src.api.services.access_service import reserve_quota, QuotaExhaustedError

        setup_db = _make_db_session()
        try:
            code = _insert_access_code(setup_db, monthly_limit=1)
            _reset_global_counter(setup_db, usage_count=0)
            code_id = code.id
        finally:
            setup_db.close()

        results = []

        def _attempt():
            db = _make_db_session()
            try:
                try:
                    reserve_quota(db, code_id)
                    results.append("ok")
                except QuotaExhaustedError:
                    results.append("exhausted")
            finally:
                db.close()

        threads = [threading.Thread(target=_attempt) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sorted(results) == ["exhausted", "ok"]

        verify_db = _make_db_session()
        try:
            from src.storage.models import AccessCode
            final = verify_db.get(AccessCode, code_id)
            assert final.usage_count == 1
        finally:
            verify_db.close()
