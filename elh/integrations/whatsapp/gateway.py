from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from .base import WhatsAppProvider, WhatsAppResponse, normalize_whatsapp_recipient

logger = logging.getLogger("elh.integrations.whatsapp.gateway")


class GenericWhatsAppGatewayProvider(WhatsAppProvider):
    """Universal HTTP Gateway Provider for third-party WhatsApp APIs (UltraMsg, GreenAPI, etc.)."""

    name = "WhatsApp Gateway"

    def __init__(
        self,
        endpoint: str,
        token: str = "",
        instance_id: str = "",
        default_country: str = "977",
        timeout_seconds: int = 15,
    ):
        self.endpoint = (endpoint or "").strip()
        self.token = (token or "").strip()
        self.instance_id = (instance_id or "").strip()
        self.default_country = default_country or "977"
        self.timeout_seconds = max(3, int(timeout_seconds or 15))

    def send(self, recipient: str, message: str) -> WhatsAppResponse:
        if not self.endpoint:
            return WhatsAppResponse(
                success=False,
                code="CONFIG_ERROR",
                message="WhatsApp Gateway API Endpoint is not configured.",
            )

        try:
            clean_recipient = normalize_whatsapp_recipient(recipient, self.default_country)
        except Exception as exc:
            return WhatsAppResponse(success=False, code="INVALID_RECIPIENT", message=str(exc))

        # Support common gateway JSON schemas (UltraMsg / GreenAPI / Wassenger standard)
        payload = {
            "to": clean_recipient,
            "phone": clean_recipient,
            "chatId": f"{clean_recipient}@c.us",
            "body": message.strip(),
            "message": message.strip(),
        }
        if self.token:
            payload["token"] = self.token
        if self.instance_id:
            payload["instanceId"] = self.instance_id

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ELH-Management-System/2.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            headers["X-API-Key"] = self.token

        body_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.endpoint, data=body_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                status_code = resp.getcode()
                raw_resp = resp.read().decode("utf-8", errors="replace")
                msg_id = ""
                try:
                    resp_data = json.loads(raw_resp)
                    msg_id = str(resp_data.get("id") or resp_data.get("messageId") or "")
                except Exception:
                    pass

                return WhatsAppResponse(
                    success=True,
                    code=str(status_code),
                    message="Message sent via WhatsApp Gateway",
                    message_id=msg_id,
                )
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8", errors="replace")
            logger.warning("WhatsApp Gateway HTTP error %d: %s", err.code, err_body)
            return WhatsAppResponse(success=False, code=str(err.code), message=err_body[:200])
        except Exception as exc:
            logger.warning("WhatsApp Gateway network error: %s", exc)
            return WhatsAppResponse(success=False, code="NETWORK_ERROR", message=str(exc))
