from __future__ import annotations

from .base import SmsProviderResponse
from .http import post_form


class SparrowSmsProvider:
    name = "sparrow"

    def __init__(
        self,
        endpoint: str,
        token: str,
        sender_id: str,
        timeout: int = 10,
    ):
        self.endpoint = endpoint
        self.token = token
        self.sender_id = sender_id
        self.timeout = timeout

    def send(self, recipient: str, message: str) -> SmsProviderResponse:
        if not self.token.strip():
            raise ValueError("Sparrow SMS token is not configured in .env.")
        if not self.sender_id.strip():
            raise ValueError("Sparrow SMS sender ID is not configured in Application Settings.")
        status, data, raw = post_form(
            self.endpoint,
            {
                "token": self.token,
                "from": self.sender_id,
                "to": recipient,
                "text": message,
            },
            self.timeout,
        )
        response_code = str(data.get("response_code", status))
        success = 200 <= status < 300 and response_code == "200"
        detail = str(data.get("response") or raw or f"HTTP {status}")
        return SmsProviderResponse(success, response_code, detail)
