from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from .base import WhatsAppProvider, WhatsAppResponse, normalize_whatsapp_recipient

logger = logging.getLogger("elh.integrations.whatsapp.meta")


class MetaWhatsAppCloudProvider(WhatsAppProvider):
    """Official Meta WhatsApp Business Cloud API provider."""

    name = "Meta Cloud API"

    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        default_country: str = "977",
        timeout_seconds: int = 15,
        api_version: str = "v20.0",
    ):
        self.phone_number_id = (phone_number_id or "").strip()
        self.access_token = (access_token or "").strip()
        self.default_country = default_country or "977"
        self.timeout_seconds = max(3, int(timeout_seconds or 15))
        self.endpoint = f"https://graph.facebook.com/{api_version}/{self.phone_number_id}/messages"

    def send(self, recipient: str, message: str) -> WhatsAppResponse:
        if not self.phone_number_id:
            return WhatsAppResponse(
                success=False,
                code="CONFIG_ERROR",
                message="Meta WhatsApp Phone Number ID is not configured.",
            )
        if not self.access_token:
            return WhatsAppResponse(
                success=False,
                code="CONFIG_ERROR",
                message="Meta WhatsApp Access Token is not configured.",
            )

        try:
            clean_recipient = normalize_whatsapp_recipient(recipient, self.default_country)
        except Exception as exc:
            return WhatsAppResponse(success=False, code="INVALID_RECIPIENT", message=str(exc))

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_recipient,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message.strip(),
            },
        }

        body_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "ELH-Management-System/2.0",
        }

        req = urllib.request.Request(self.endpoint, data=body_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                status_code = resp.getcode()
                resp_data = json.loads(resp.read().decode("utf-8"))
                msg_id = ""
                if "messages" in resp_data and resp_data["messages"]:
                    msg_id = resp_data["messages"][0].get("id", "")
                return WhatsAppResponse(
                    success=True,
                    code=str(status_code),
                    message="Message dispatched via Meta Cloud API",
                    message_id=msg_id,
                )
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8", errors="replace")
            logger.warning("Meta WhatsApp Cloud API HTTP error %d: %s", err.code, err_body)
            err_msg = f"HTTP {err.code}"
            try:
                parsed = json.loads(err_body)
                if "error" in parsed:
                    err_msg = parsed["error"].get("message", err_msg)
            except Exception:
                err_msg = err_body[:200]
            return WhatsAppResponse(success=False, code=str(err.code), message=err_msg)
        except Exception as exc:
            logger.warning("Meta WhatsApp Cloud API network error: %s", exc)
            return WhatsAppResponse(success=False, code="NETWORK_ERROR", message=str(exc))
