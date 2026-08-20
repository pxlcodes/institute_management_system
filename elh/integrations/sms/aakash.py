from __future__ import annotations

from .base import SmsProviderResponse
from .http import post_form


class AakashSmsProvider:
    name = "aakash"

    def __init__(self, endpoint: str, token: str, timeout: int = 10):
        self.endpoint = endpoint
        self.token = token
        self.timeout = timeout

    def send(self, recipient: str, message: str) -> SmsProviderResponse:
        if not self.token.strip():
            raise ValueError("Aakash SMS token is not configured in .env.")
        status, data, raw = post_form(
            self.endpoint,
            {"auth_token": self.token, "to": recipient, "text": message},
            self.timeout,
        )
        success = 200 <= status < 300 and data.get("error") is False
        code = str(data.get("response_code", status))
        detail = str(data.get("message") or raw or f"HTTP {status}")
        return SmsProviderResponse(success, code, detail)
