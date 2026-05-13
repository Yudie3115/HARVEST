"""
Unit tests for WhatsAppService (mocked HTTP — no real API calls).
"""
import pytest
from unittest.mock import MagicMock, patch


class TestWhatsAppServiceApiVersion:
    def test_uses_v21_api_version(self):
        from src.api.services.whatsapp_service import _GRAPH_API_VERSION
        assert _GRAPH_API_VERSION == "v21.0"


class TestWhatsAppServiceTruncation:
    def _make_service(self):
        from src.api.services.whatsapp_service import WhatsAppService
        return WhatsAppService(token="tok", phone_number_id="123")

    def _mock_httpx_success(self):
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post = MagicMock(return_value=mock_response)
        return mock_client

    def test_short_message_sent_unchanged(self):
        svc = self._make_service()
        mock_client = self._mock_httpx_success()
        with patch("httpx.Client", return_value=mock_client):
            svc.send_text("+256700000000", "Hello")
        payload = mock_client.post.call_args[1]["json"]
        assert payload["text"]["body"] == "Hello"

    def test_message_over_4000_chars_is_truncated(self):
        svc = self._make_service()
        mock_client = self._mock_httpx_success()
        long_msg = "x" * 5000
        with patch("httpx.Client", return_value=mock_client):
            svc.send_text("+256700000000", long_msg)
        payload = mock_client.post.call_args[1]["json"]
        body = payload["text"]["body"]
        assert len(body) <= 4000
        assert "[Response truncated]" in body

    def test_message_exactly_4000_chars_not_truncated(self):
        svc = self._make_service()
        mock_client = self._mock_httpx_success()
        msg = "y" * 4000
        with patch("httpx.Client", return_value=mock_client):
            svc.send_text("+256700000000", msg)
        payload = mock_client.post.call_args[1]["json"]
        assert payload["text"]["body"] == msg
