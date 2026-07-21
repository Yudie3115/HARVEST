"""
Tests for WhatsApp webhook helper functions and route handlers.
"""
import asyncio
import hashlib
import hmac
import json as _json
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helper: reset module-level state between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_whatsapp_state():
    """Clear in-memory dedup and rate-limit caches between tests."""
    import src.api.routes.whatsapp as wh
    wh._SEEN_IDS.clear()
    wh._PHONE_TIMESTAMPS.clear()
    yield
    wh._SEEN_IDS.clear()
    wh._PHONE_TIMESTAMPS.clear()


# ---------------------------------------------------------------------------
# _verify_signature
# ---------------------------------------------------------------------------

class TestVerifySignature:
    def _sig(self, body: bytes, secret: str) -> str:
        return "sha256=" + hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()

    def test_valid_signature_returns_true(self):
        from src.api.routes.whatsapp import _verify_signature
        body = b'{"entry": []}'
        secret = "mysecret"
        assert _verify_signature(body, self._sig(body, secret), secret) is True

    def test_wrong_signature_returns_false(self):
        from src.api.routes.whatsapp import _verify_signature
        body = b'{"entry": []}'
        assert _verify_signature(body, "sha256=wrong", "mysecret") is False

    def test_empty_signature_returns_false(self):
        from src.api.routes.whatsapp import _verify_signature
        assert _verify_signature(b"body", "", "mysecret") is False

    def test_tampered_body_returns_false(self):
        from src.api.routes.whatsapp import _verify_signature
        body = b'{"entry": []}'
        secret = "mysecret"
        sig = self._sig(body, secret)
        assert _verify_signature(b"tampered", sig, secret) is False


# ---------------------------------------------------------------------------
# _is_duplicate
# ---------------------------------------------------------------------------

class TestIsDuplicate:
    def test_first_occurrence_returns_false(self):
        from src.api.routes.whatsapp import _is_duplicate
        assert _is_duplicate("msg-abc") is False

    def test_second_occurrence_returns_true(self):
        from src.api.routes.whatsapp import _is_duplicate
        _is_duplicate("msg-abc")
        assert _is_duplicate("msg-abc") is True

    def test_different_ids_are_independent(self):
        from src.api.routes.whatsapp import _is_duplicate
        assert _is_duplicate("msg-1") is False
        assert _is_duplicate("msg-2") is False
        assert _is_duplicate("msg-1") is True
        assert _is_duplicate("msg-2") is True


# ---------------------------------------------------------------------------
# _is_rate_limited
# ---------------------------------------------------------------------------

class TestIsRateLimited:
    def test_under_limit_returns_false(self):
        from src.api.routes.whatsapp import _is_rate_limited
        assert _is_rate_limited("+256700000001", 3) is False
        assert _is_rate_limited("+256700000001", 3) is False
        assert _is_rate_limited("+256700000001", 3) is False

    def test_at_limit_returns_true(self):
        from src.api.routes.whatsapp import _is_rate_limited
        _is_rate_limited("+256700000002", 3)
        _is_rate_limited("+256700000002", 3)
        _is_rate_limited("+256700000002", 3)
        assert _is_rate_limited("+256700000002", 3) is True

    def test_different_phones_are_independent(self):
        from src.api.routes.whatsapp import _is_rate_limited
        _is_rate_limited("+256700000003", 1)
        assert _is_rate_limited("+256700000003", 1) is True
        assert _is_rate_limited("+256700000004", 1) is False


# ---------------------------------------------------------------------------
# Route integration tests
# ---------------------------------------------------------------------------

from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes.whatsapp import router
from src.api.dependencies import (
    get_db, get_llm_client, get_embedding_client,
    get_vector_db_client, get_translation_client, get_whatsapp_service,
)


def _make_client():
    """Build a TestClient with all heavy dependencies mocked out."""
    app = FastAPI()
    app.include_router(router, prefix="/webhook")
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_llm_client] = lambda: MagicMock()
    app.dependency_overrides[get_embedding_client] = lambda: MagicMock()
    app.dependency_overrides[get_vector_db_client] = lambda: MagicMock()
    app.dependency_overrides[get_translation_client] = lambda: MagicMock()
    mock_wa_service = MagicMock()
    app.dependency_overrides[get_whatsapp_service] = lambda: mock_wa_service
    return TestClient(app, raise_server_exceptions=False), mock_wa_service


def _whatsapp_payload(
    sender: str = "+256700000000",
    text: str = "Hello",
    msg_id: str = "wamid.test123",
    msg_type: str = "text",
) -> dict:
    payload: dict = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": sender,
                        "id": msg_id,
                        "type": msg_type,
                    }]
                }
            }]
        }]
    }
    if msg_type == "text":
        payload["entry"][0]["changes"][0]["value"]["messages"][0]["text"] = {"body": text}
    return payload


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _patch_active_whatsapp_grant(monkeypatch):
    """Patch access_service so the webhook treats every phone as already granted."""
    import src.api.routes.whatsapp as route_mod
    resolved = MagicMock()
    resolved.grant.id = "grant-1"
    resolved.access_code.id = "code-1"
    resolved.access_code.status = "active"
    monkeypatch.setattr(route_mod.access_service, "resolve_whatsapp_grant", lambda db, phone: resolved)
    monkeypatch.setattr(route_mod.access_service, "reserve_quota", lambda db, code_id: None)
    return resolved


class TestWebhookVerify:
    def test_valid_token_returns_challenge(self):
        client, _ = _make_client()
        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_verify_token = "test-token"
            resp = client.get(
                "/webhook/whatsapp",
                params={"hub.mode": "subscribe", "hub.verify_token": "test-token", "hub.challenge": "42"},
            )
        assert resp.status_code == 200
        assert resp.json() == 42

    def test_wrong_token_returns_403(self):
        client, _ = _make_client()
        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_verify_token = "test-token"
            resp = client.get(
                "/webhook/whatsapp",
                params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42"},
            )
        assert resp.status_code == 403


class TestWebhookPost:
    def _post(self, client, payload: dict, secret: str = "", extra_headers: dict = None):
        body = _json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if secret:
            headers["X-Hub-Signature-256"] = _sign(body, secret)
        if extra_headers:
            headers.update(extra_headers)
        return client.post("/webhook/whatsapp", content=body, headers=headers)

    def test_invalid_signature_returns_403(self):
        client, _ = _make_client()
        payload = _whatsapp_payload()
        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_app_secret = "real-secret"
            s.api_rate_limit_whatsapp = 30
            body = _json.dumps(payload).encode()
            resp = client.post(
                "/webhook/whatsapp",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": "sha256=invalidsignature",
                },
            )
        assert resp.status_code == 403

    def test_no_app_secret_configured_skips_verification(self, monkeypatch):
        _patch_active_whatsapp_grant(monkeypatch)
        client, _ = _make_client()
        payload = _whatsapp_payload()
        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_app_secret = ""
            s.api_rate_limit_whatsapp = 30
            with patch("src.api.routes.whatsapp.process_chat") as mock_chat:
                mock_chat.return_value = MagicMock(answer="Reply")
                with patch("src.api.routes.whatsapp._is_duplicate", return_value=False):
                    resp = self._post(client, payload)
        assert resp.status_code == 200

    def test_duplicate_message_returns_duplicate_status(self):
        client, _ = _make_client()
        payload = _whatsapp_payload(msg_id="wamid.dup")
        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_app_secret = ""
            s.api_rate_limit_whatsapp = 30
            with patch("src.api.routes.whatsapp._is_duplicate", return_value=True):
                resp = self._post(client, payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "duplicate"

    def test_rate_limited_phone_returns_rate_limited_status(self):
        client, _ = _make_client()
        payload = _whatsapp_payload()
        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_app_secret = ""
            s.api_rate_limit_whatsapp = 30
            with patch("src.api.routes.whatsapp._is_duplicate", return_value=False):
                with patch("src.api.routes.whatsapp._is_rate_limited", return_value=True):
                    resp = self._post(client, payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "rate_limited"

    def test_non_text_message_sends_polite_reply(self, monkeypatch):
        _patch_active_whatsapp_grant(monkeypatch)
        client, mock_svc = _make_client()
        payload = _whatsapp_payload(msg_type="image")
        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_app_secret = ""
            s.api_rate_limit_whatsapp = 30
            with patch("src.api.routes.whatsapp._is_duplicate", return_value=False):
                with patch("src.api.routes.whatsapp._is_rate_limited", return_value=False):
                    resp = self._post(client, payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"
        mock_svc.send_text.assert_called_once()
        reply_text = mock_svc.send_text.call_args[0][1]
        assert "text" in reply_text.lower() or "type" in reply_text.lower()

    def test_text_message_runs_pipeline_and_replies(self, monkeypatch):
        _patch_active_whatsapp_grant(monkeypatch)
        client, mock_svc = _make_client()
        payload = _whatsapp_payload(text="What is maize drying?")
        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_app_secret = ""
            s.api_rate_limit_whatsapp = 30
            with patch("src.api.routes.whatsapp._is_duplicate", return_value=False):
                with patch("src.api.routes.whatsapp._is_rate_limited", return_value=False):
                    with patch("src.api.routes.whatsapp.process_chat") as mock_chat:
                        mock_chat.return_value = MagicMock(answer="Dry at 14% moisture.")
                        resp = self._post(client, payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        mock_svc.send_text.assert_called_once_with("+256700000000", "Dry at 14% moisture.")

    def test_pipeline_timeout_sends_error_and_returns_timeout(self, monkeypatch):
        _patch_active_whatsapp_grant(monkeypatch)
        client, mock_svc = _make_client()
        payload = _whatsapp_payload(text="slow question")
        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_app_secret = ""
            s.api_rate_limit_whatsapp = 30
            with patch("src.api.routes.whatsapp._is_duplicate", return_value=False):
                with patch("src.api.routes.whatsapp._is_rate_limited", return_value=False):
                    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                        resp = self._post(client, payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "timeout"
        mock_svc.send_text.assert_called_once()


class TestWebhookAccessGating:
    def _post(self, client, payload: dict, secret: str = "", extra_headers: dict = None):
        body = _json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if secret:
            headers["X-Hub-Signature-256"] = _sign(body, secret)
        if extra_headers:
            headers.update(extra_headers)
        return client.post("/webhook/whatsapp", content=body, headers=headers)

    def test_non_code_message_with_no_grant_sends_welcome_prompt(self):
        client, mock_svc = _make_client()
        payload = _whatsapp_payload(text="How do I dry maize?")
        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_app_secret = ""
            s.api_rate_limit_whatsapp = 30
            with patch("src.api.routes.whatsapp._is_duplicate", return_value=False):
                with patch("src.api.routes.whatsapp._is_rate_limited", return_value=False):
                    with patch(
                        "src.api.routes.whatsapp.access_service.resolve_whatsapp_grant",
                        return_value=None,
                    ):
                        resp = self._post(client, payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "awaiting_code"
        mock_svc.send_text.assert_called_once()
        reply = mock_svc.send_text.call_args[0][1]
        assert "code" in reply.lower()

    def test_code_shaped_message_attempts_redemption(self):
        client, mock_svc = _make_client()
        payload = _whatsapp_payload(text="mango-river-granary")
        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_app_secret = ""
            s.api_rate_limit_whatsapp = 30
            with patch("src.api.routes.whatsapp._is_duplicate", return_value=False):
                with patch("src.api.routes.whatsapp._is_rate_limited", return_value=False):
                    with patch(
                        "src.api.routes.whatsapp.access_service.resolve_whatsapp_grant",
                        return_value=None,
                    ):
                        with patch(
                            "src.api.routes.whatsapp.access_service.check_redemption_throttle",
                        ):
                            with patch(
                                "src.api.routes.whatsapp.access_service.redeem_whatsapp_code",
                            ) as mock_redeem:
                                fake_result = MagicMock()
                                fake_result.access_code.label = "Group A"
                                mock_redeem.return_value = fake_result
                                resp = self._post(client, payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "redeemed"
        mock_redeem.assert_called_once()
        mock_svc.send_text.assert_called_once()

    def test_invalid_code_shaped_message_records_failed_attempt(self):
        client, mock_svc = _make_client()
        payload = _whatsapp_payload(text="bad-bad-bad")
        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_app_secret = ""
            s.api_rate_limit_whatsapp = 30
            with patch("src.api.routes.whatsapp._is_duplicate", return_value=False):
                with patch("src.api.routes.whatsapp._is_rate_limited", return_value=False):
                    with patch(
                        "src.api.routes.whatsapp.access_service.resolve_whatsapp_grant",
                        return_value=None,
                    ):
                        with patch(
                            "src.api.routes.whatsapp.access_service.check_redemption_throttle",
                        ):
                            with patch(
                                "src.api.routes.whatsapp.access_service.record_failed_redemption_attempt",
                            ) as mock_record:
                                from src.api.services.access_service import AccessInvalidError
                                with patch(
                                    "src.api.routes.whatsapp.access_service.redeem_whatsapp_code",
                                    side_effect=AccessInvalidError("nope"),
                                ):
                                    resp = self._post(client, payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "invalid_code"
        mock_record.assert_called_once()

    def test_revoked_existing_grant_sends_blocked_message_and_skips_chat(self, monkeypatch):
        client, mock_svc = _make_client()
        payload = _whatsapp_payload(text="How long should I dry maize?")
        resolved = MagicMock()
        resolved.access_code.status = "revoked"
        monkeypatch.setattr(
            "src.api.routes.whatsapp.access_service.resolve_whatsapp_grant",
            lambda db, phone: resolved,
        )
        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_app_secret = ""
            s.api_rate_limit_whatsapp = 30
            with patch("src.api.routes.whatsapp._is_duplicate", return_value=False):
                with patch("src.api.routes.whatsapp._is_rate_limited", return_value=False):
                    with patch("src.api.routes.whatsapp.process_chat") as mock_chat:
                        resp = self._post(client, payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "access_revoked"
        mock_chat.assert_not_called()
        mock_svc.send_text.assert_called_once()

    def test_quota_exhausted_sends_mapped_message_and_skips_chat(self, monkeypatch):
        client, mock_svc = _make_client()
        payload = _whatsapp_payload(text="How long should I dry maize?")
        resolved = MagicMock()
        resolved.access_code.status = "active"
        resolved.access_code.id = "code-1"
        monkeypatch.setattr(
            "src.api.routes.whatsapp.access_service.resolve_whatsapp_grant",
            lambda db, phone: resolved,
        )
        from src.api.services.access_service import QuotaExhaustedError

        def _raise(db, code_id):
            raise QuotaExhaustedError("exhausted")
        monkeypatch.setattr("src.api.routes.whatsapp.access_service.reserve_quota", _raise)

        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_app_secret = ""
            s.api_rate_limit_whatsapp = 30
            with patch("src.api.routes.whatsapp._is_duplicate", return_value=False):
                with patch("src.api.routes.whatsapp._is_rate_limited", return_value=False):
                    with patch("src.api.routes.whatsapp.process_chat") as mock_chat:
                        resp = self._post(client, payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "quota_exhausted"
        mock_chat.assert_not_called()
        mock_svc.send_text.assert_called_once()

    def test_code_shaped_ordinary_question_with_existing_grant_falls_through_to_chat(
        self, monkeypatch
    ):
        """A natural 3-word question (e.g. 'dry my maize') from an already-authorized
        phone must not be swallowed as a failed redemption attempt — it should reach
        the normal chat pipeline instead."""
        client, mock_svc = _make_client()
        payload = _whatsapp_payload(text="dry my maize")
        resolved = MagicMock()
        resolved.access_code.status = "active"
        resolved.access_code.id = "code-1"
        resolved.grant.id = "grant-1"
        monkeypatch.setattr(
            "src.api.routes.whatsapp.access_service.resolve_whatsapp_grant",
            lambda db, phone: resolved,
        )
        monkeypatch.setattr(
            "src.api.routes.whatsapp.access_service.reserve_quota",
            lambda db, code_id: None,
        )
        monkeypatch.setattr(
            "src.api.routes.whatsapp.access_service.check_redemption_throttle",
            lambda db, identifier: None,
        )
        from src.api.services.access_service import AccessInvalidError

        mock_record = MagicMock()
        monkeypatch.setattr(
            "src.api.routes.whatsapp.access_service.record_failed_redemption_attempt",
            mock_record,
        )
        monkeypatch.setattr(
            "src.api.routes.whatsapp.access_service.redeem_whatsapp_code",
            MagicMock(side_effect=AccessInvalidError("nope")),
        )

        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_app_secret = ""
            s.api_rate_limit_whatsapp = 30
            with patch("src.api.routes.whatsapp._is_duplicate", return_value=False):
                with patch("src.api.routes.whatsapp._is_rate_limited", return_value=False):
                    with patch("src.api.routes.whatsapp.process_chat") as mock_chat:
                        mock_chat.return_value = MagicMock(answer="Dry maize to 14% moisture.")
                        resp = self._post(client, payload)

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        mock_chat.assert_called_once()
        mock_svc.send_text.assert_called_once_with(
            "+256700000000", "Dry maize to 14% moisture."
        )
        # The false-positive code-format match must not burn the redemption
        # throttle budget or tell the user their "code" was invalid.
        mock_record.assert_not_called()

    def test_code_shaped_real_replacement_code_with_existing_grant_still_rebinds(
        self, monkeypatch
    ):
        """Regression guard: a phone with an existing (e.g. revoked) grant that sends a
        genuine replacement code must still redeem/rebind normally — the fix for the
        false-positive case above must not break legitimate rebinding."""
        client, mock_svc = _make_client()
        payload = _whatsapp_payload(text="mango-river-granary")
        resolved = MagicMock()
        resolved.access_code.status = "revoked"
        resolved.access_code.id = "code-old"
        resolved.grant.id = "grant-old"
        monkeypatch.setattr(
            "src.api.routes.whatsapp.access_service.resolve_whatsapp_grant",
            lambda db, phone: resolved,
        )
        monkeypatch.setattr(
            "src.api.routes.whatsapp.access_service.check_redemption_throttle",
            lambda db, identifier: None,
        )
        fake_result = MagicMock()
        fake_result.access_code.label = "Group B"
        mock_redeem = MagicMock(return_value=fake_result)
        monkeypatch.setattr(
            "src.api.routes.whatsapp.access_service.redeem_whatsapp_code", mock_redeem
        )
        mock_clear = MagicMock()
        monkeypatch.setattr(
            "src.api.routes.whatsapp.access_service.clear_redemption_throttle", mock_clear
        )

        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_app_secret = ""
            s.api_rate_limit_whatsapp = 30
            with patch("src.api.routes.whatsapp._is_duplicate", return_value=False):
                with patch("src.api.routes.whatsapp._is_rate_limited", return_value=False):
                    with patch("src.api.routes.whatsapp.process_chat") as mock_chat:
                        resp = self._post(client, payload)

        assert resp.status_code == 200
        assert resp.json()["status"] == "redeemed"
        mock_redeem.assert_called_once()
        mock_clear.assert_called_once()
        mock_chat.assert_not_called()
        mock_svc.send_text.assert_called_once()
        reply = mock_svc.send_text.call_args[0][1]
        assert "Group B" in reply

    def test_code_shaped_message_logs_redacted_placeholder(self):
        """Plaintext access codes must never be written to the application log."""
        client, _ = _make_client()
        payload = _whatsapp_payload(text="mango-river-granary")
        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_app_secret = ""
            s.api_rate_limit_whatsapp = 30
            with patch("src.api.routes.whatsapp._is_duplicate", return_value=False):
                with patch("src.api.routes.whatsapp._is_rate_limited", return_value=False):
                    with patch(
                        "src.api.routes.whatsapp.access_service.resolve_whatsapp_grant",
                        return_value=None,
                    ):
                        with patch(
                            "src.api.routes.whatsapp.access_service.check_redemption_throttle",
                        ):
                            with patch(
                                "src.api.routes.whatsapp.access_service.redeem_whatsapp_code",
                            ) as mock_redeem:
                                fake_result = MagicMock()
                                fake_result.access_code.label = "Group A"
                                mock_redeem.return_value = fake_result
                                with patch("src.api.routes.whatsapp.logger") as mock_logger:
                                    resp = self._post(client, payload)

        assert resp.status_code == 200
        logged_messages = " ".join(
            str(call.args[0]) for call in mock_logger.info.call_args_list
        )
        assert "mango-river-granary" not in logged_messages
        assert "redacted" in logged_messages.lower()

    def test_ordinary_question_logs_message_body_unredacted(self):
        """Non-code-shaped messages are ordinary questions, not secrets — keep logging
        them as before."""
        client, _ = _make_client()
        payload = _whatsapp_payload(text="How do I dry maize?")
        with patch("src.api.routes.whatsapp.settings") as s:
            s.whatsapp_app_secret = ""
            s.api_rate_limit_whatsapp = 30
            with patch("src.api.routes.whatsapp._is_duplicate", return_value=False):
                with patch("src.api.routes.whatsapp._is_rate_limited", return_value=False):
                    with patch(
                        "src.api.routes.whatsapp.access_service.resolve_whatsapp_grant",
                        return_value=None,
                    ):
                        with patch("src.api.routes.whatsapp.logger") as mock_logger:
                            resp = self._post(client, payload)

        assert resp.status_code == 200
        logged_messages = " ".join(
            str(call.args[0]) for call in mock_logger.info.call_args_list
        )
        assert "How do I dry maize?" in logged_messages
        assert "redacted" not in logged_messages.lower()
