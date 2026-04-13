"""
WhatsApp Cloud API client — sends outbound text messages via Meta's Graph API.
"""
import httpx
from loguru import logger

_GRAPH_API_VERSION = "v18.0"
_GRAPH_API_BASE = "https://graph.facebook.com"


class WhatsAppService:
    """Thin wrapper around the Meta WhatsApp Cloud API for sending messages."""

    def __init__(self, token: str, phone_number_id: str):
        self._token = token
        self._phone_number_id = phone_number_id
        self._timeout = httpx.Timeout(15.0, connect=5.0)

    def send_text(self, recipient_phone: str, message: str) -> None:
        """
        Send a plain-text WhatsApp message to *recipient_phone*.

        Args:
            recipient_phone: E.164 phone number of the recipient, e.g. "+256700000000".
            message: Text body to send (max 4096 chars per Meta docs).

        Raises:
            httpx.HTTPStatusError: If the Graph API returns a non-2xx status.
        """
        url = (
            f"{_GRAPH_API_BASE}/{_GRAPH_API_VERSION}"
            f"/{self._phone_number_id}/messages"
        )
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient_phone,
            "type": "text",
            "text": {"body": message},
        }

        logger.debug(
            f"WhatsApp → {recipient_phone} "
            f"({len(message)} chars via phone_number_id={self._phone_number_id})"
        )

        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(url, json=payload, headers=headers)

        if not response.is_success:
            logger.error(
                f"WhatsApp API error {response.status_code}: {response.text}"
            )
        response.raise_for_status()

        logger.info(f"WhatsApp message sent to {recipient_phone}")
