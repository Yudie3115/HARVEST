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


class TestCreateAccessCode:
    def test_creates_row_and_returns_plaintext_code(self):
        from src.api.services.access_service import create_access_code, hash_code, normalize_code
        db = _make_db_session()
        try:
            code_row, plaintext = create_access_code(
                db, label="Farmer Group A", monthly_limit=100, created_by="admin",
            )
            assert code_row.label == "Farmer Group A"
            assert code_row.monthly_limit == 100
            assert code_row.status == "active"
            assert code_row.code_hash == hash_code(normalize_code(plaintext))
            parts = plaintext.split("-")
            assert len(parts) == 3
        finally:
            db.close()

    def test_optional_fields_are_stored(self):
        from src.api.services.access_service import create_access_code
        db = _make_db_session()
        try:
            code_row, _ = create_access_code(
                db, label="Farmer Group B", monthly_limit=50, created_by="admin",
                organization_name="Kampala Co-op", contact_message="Call 0800-000",
            )
            assert code_row.organization_name == "Kampala Co-op"
            assert code_row.contact_message == "Call 0800-000"
        finally:
            db.close()

    def test_retries_on_hash_collision(self, monkeypatch):
        """Force the first generated code to collide, verify a second attempt succeeds.

        The second value is suffixed with a fresh uuid4 hex so its hash is unique
        per test run — a fixed literal would collide with a previous run's row in
        this shared, persistent dev database (code_hash has a unique constraint).
        """
        import src.api.services.access_service as svc
        db = _make_db_session()
        try:
            existing, existing_plain = svc.create_access_code(
                db, label="Existing", monthly_limit=10, created_by="admin",
            )
            unique_second = f"totally-different-words-{uuid.uuid4().hex}"
            calls = iter([existing_plain, unique_second])
            monkeypatch.setattr(svc, "generate_code", lambda: next(calls))

            code_row, plaintext = svc.create_access_code(
                db, label="New Group", monthly_limit=10, created_by="admin",
            )
            assert plaintext == unique_second
            assert code_row.id != existing.id
        finally:
            db.close()


class TestRedeemWebCode:
    def test_unknown_code_raises_access_invalid(self):
        from src.api.services.access_service import redeem_web_code, AccessInvalidError
        db = _make_db_session()
        try:
            with pytest.raises(AccessInvalidError):
                redeem_web_code(db, "no-such-code")
        finally:
            db.close()

    def test_revoked_code_raises_access_revoked(self):
        from src.api.services.access_service import create_access_code, redeem_web_code, AccessRevokedError
        db = _make_db_session()
        try:
            code_row, plaintext = create_access_code(
                db, label="Revoked Group", monthly_limit=10, created_by="admin",
            )
            code_row.status = "revoked"
            db.commit()

            with pytest.raises(AccessRevokedError):
                redeem_web_code(db, plaintext)
        finally:
            db.close()

    def test_successful_redemption_creates_active_web_grant(self):
        from src.api.services.access_service import create_access_code, redeem_web_code, hash_token
        from src.storage.models import AccessGrant
        db = _make_db_session()
        try:
            code_row, plaintext = create_access_code(
                db, label="Group C", monthly_limit=10, created_by="admin",
            )
            result = redeem_web_code(db, plaintext)

            assert result.access_code.id == code_row.id
            stored = db.query(AccessGrant).filter(AccessGrant.id == result.grant.id).one()
            assert stored.channel == "web"
            assert stored.status == "active"
            assert stored.identifier_hash == hash_token(result.token)
        finally:
            db.close()

    def test_redemption_is_case_and_whitespace_insensitive(self):
        from src.api.services.access_service import create_access_code, redeem_web_code
        db = _make_db_session()
        try:
            _, plaintext = create_access_code(
                db, label="Group D", monthly_limit=10, created_by="admin",
            )
            messy = "  " + plaintext.upper().replace("-", "  ") + "  "
            result = redeem_web_code(db, messy)  # should not raise
            assert result.token
        finally:
            db.close()


class TestIsCodeFormat:
    def test_well_formed_three_word_code_is_true(self):
        from src.api.services.access_service import is_code_format
        assert is_code_format("mango-river-granary") is True

    def test_messy_but_well_formed_code_is_true(self):
        from src.api.services.access_service import is_code_format
        assert is_code_format("  Mango   River   Granary  ") is True

    def test_free_text_question_is_false(self):
        from src.api.services.access_service import is_code_format
        assert is_code_format("How do I dry maize?") is False

    def test_two_word_text_is_false(self):
        from src.api.services.access_service import is_code_format
        assert is_code_format("hello there") is False


class TestResolveWhatsappGrant:
    def test_no_grant_returns_none(self):
        from src.api.services.access_service import resolve_whatsapp_grant
        db = _make_db_session()
        try:
            assert resolve_whatsapp_grant(db, "+256799999999") is None
        finally:
            db.close()

    def test_active_grant_resolves(self):
        from src.api.services.access_service import (
            resolve_whatsapp_grant, hash_identifier, DOMAIN_WHATSAPP_GRANT,
        )
        from src.storage.models import AccessGrant, ChannelEnum
        db = _make_db_session()
        try:
            code = _insert_access_code(db)
            # Suffixed per the idempotency lesson from d92fa14/d7c3cd8: this raw
            # insert creates a status="active" AccessGrant, which is covered by
            # the partial unique index on (channel, identifier_hash) WHERE
            # status = 'active'. A fixed literal would collide with a leftover
            # row from a previous run against this shared, persistent dev DB.
            phone = f"+256788888888-{uuid.uuid4().hex}"
            grant = AccessGrant(
                access_code_id=code.id, channel=ChannelEnum.whatsapp,
                identifier_hash=hash_identifier(phone, domain=DOMAIN_WHATSAPP_GRANT),
                status="active",
            )
            db.add(grant)
            db.commit()

            resolved = resolve_whatsapp_grant(db, phone)
            assert resolved is not None
            assert resolved.grant.id == grant.id
        finally:
            db.close()

    def test_replaced_grant_is_not_resolved(self):
        from src.api.services.access_service import (
            resolve_whatsapp_grant, hash_identifier, DOMAIN_WHATSAPP_GRANT,
        )
        from src.storage.models import AccessGrant, ChannelEnum
        db = _make_db_session()
        try:
            code = _insert_access_code(db)
            # status="replaced" isn't covered by the partial unique index, but
            # suffixed anyway for consistency/safety per the same lesson.
            phone = f"+256777777777-{uuid.uuid4().hex}"
            db.add(AccessGrant(
                access_code_id=code.id, channel=ChannelEnum.whatsapp,
                identifier_hash=hash_identifier(phone, domain=DOMAIN_WHATSAPP_GRANT),
                status="replaced",
            ))
            db.commit()

            assert resolve_whatsapp_grant(db, phone) is None
        finally:
            db.close()


class TestRedeemWhatsappCode:
    def test_unknown_code_raises_access_invalid(self):
        from src.api.services.access_service import redeem_whatsapp_code, AccessInvalidError
        db = _make_db_session()
        try:
            with pytest.raises(AccessInvalidError):
                redeem_whatsapp_code(db, "+256766666666", "no-such-code")
        finally:
            db.close()

    def test_first_time_redemption_creates_active_grant(self):
        from src.api.services.access_service import (
            create_access_code, redeem_whatsapp_code, hash_identifier, DOMAIN_WHATSAPP_GRANT,
        )
        db = _make_db_session()
        try:
            _, plaintext = create_access_code(
                db, label="WA Group", monthly_limit=10, created_by="admin",
            )
            # Suffixed: this persists a status="active" AccessGrant via
            # redeem_whatsapp_code, covered by the partial unique index.
            phone = f"+256755555555-{uuid.uuid4().hex}"
            result = redeem_whatsapp_code(db, phone, plaintext)

            assert result.grant.status == "active"
            assert result.grant.identifier_hash == hash_identifier(phone, domain=DOMAIN_WHATSAPP_GRANT)
        finally:
            db.close()

    def test_rebinding_replaces_the_previous_active_grant(self):
        from src.api.services.access_service import create_access_code, redeem_whatsapp_code
        from src.storage.models import AccessGrant
        db = _make_db_session()
        try:
            _, first_code = create_access_code(
                db, label="WA Group A", monthly_limit=10, created_by="admin",
            )
            # Suffixed: the same lesson applies here even though the rebinding
            # logic itself is written to tolerate a pre-existing active grant
            # for this phone (that's the whole point of this test) — suffixing
            # keeps each run's assertions about *this specific pair* of grants
            # independent of any state left behind by earlier runs.
            phone = f"+256744444444-{uuid.uuid4().hex}"
            first_result = redeem_whatsapp_code(db, phone, first_code)

            _, second_code = create_access_code(
                db, label="WA Group B", monthly_limit=10, created_by="admin",
            )
            second_result = redeem_whatsapp_code(db, phone, second_code)

            db.refresh(first_result.grant)
            assert first_result.grant.status == "replaced"
            assert first_result.grant.replaced_at is not None
            assert second_result.grant.status == "active"
            assert second_result.grant.id != first_result.grant.id
        finally:
            db.close()


class TestRedemptionThrottling:
    def test_under_limit_does_not_raise(self):
        from src.api.services.access_service import check_redemption_throttle
        db = _make_db_session()
        try:
            check_redemption_throttle(db, "+256733333333-under-limit")  # no exception
        finally:
            db.close()

    def test_at_limit_raises_redemption_rate_limited(self, monkeypatch):
        from src.config import settings as settings_module
        monkeypatch.setattr(settings_module.settings, "redemption_max_attempts_per_hour", 3)
        from src.api.services.access_service import (
            check_redemption_throttle, record_failed_redemption_attempt,
            RedemptionRateLimitedError,
        )
        db = _make_db_session()
        identifier = "+256722222222-at-limit"
        try:
            for _ in range(3):
                record_failed_redemption_attempt(db, identifier)
            with pytest.raises(RedemptionRateLimitedError):
                check_redemption_throttle(db, identifier)
        finally:
            db.close()

    def test_different_identifiers_are_independent(self, monkeypatch):
        from src.config import settings as settings_module
        monkeypatch.setattr(settings_module.settings, "redemption_max_attempts_per_hour", 1)
        from src.api.services.access_service import (
            check_redemption_throttle, record_failed_redemption_attempt,
        )
        db = _make_db_session()
        try:
            record_failed_redemption_attempt(db, "+256711111111-a")
            check_redemption_throttle(db, "+256711111111-b")  # independent identifier, no exception
        finally:
            db.close()

    def test_clear_resets_the_window(self, monkeypatch):
        from src.config import settings as settings_module
        monkeypatch.setattr(settings_module.settings, "redemption_max_attempts_per_hour", 1)
        from src.api.services.access_service import (
            check_redemption_throttle, record_failed_redemption_attempt,
            clear_redemption_throttle,
        )
        db = _make_db_session()
        identifier = "+256700111222-clear"
        try:
            record_failed_redemption_attempt(db, identifier)
            clear_redemption_throttle(db, identifier)
            check_redemption_throttle(db, identifier)  # window cleared, no exception
        finally:
            db.close()

    def test_attempts_older_than_one_hour_do_not_count(self, monkeypatch):
        from src.config import settings as settings_module
        monkeypatch.setattr(settings_module.settings, "redemption_max_attempts_per_hour", 1)
        from src.api.services.access_service import check_redemption_throttle, hash_identifier, DOMAIN_REDEMPTION_THROTTLE
        from src.storage.models import RedemptionAttempt
        db = _make_db_session()
        identifier = "+256700333444-stale"
        try:
            stale = RedemptionAttempt(
                identifier_hash=hash_identifier(identifier, domain=DOMAIN_REDEMPTION_THROTTLE),
                attempted_at=datetime.now(timezone.utc) - timedelta(hours=2),
            )
            db.add(stale)
            db.commit()

            check_redemption_throttle(db, identifier)  # only a 2h-old attempt, no exception
        finally:
            db.close()
