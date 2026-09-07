from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class WhatsAppResponse:
    success: bool
    code: str
    message: str
    message_id: str = ""


class WhatsAppProvider(Protocol):
    name: str

    def send(self, recipient: str, message: str) -> WhatsAppResponse: ...


def normalize_whatsapp_recipient(value: str, default_country: str = "977") -> str:
    """Normalize phone number to international E.164-style digits without plus (e.g. 9779841234567)."""
    digits = re.sub(r"\D", "", str(value or ""))
    country = re.sub(r"\D", "", str(default_country or "977"))

    # Already has country code prefix
    if digits.startswith(country) and len(digits) == len(country) + 10:
        return digits

    # Standard 10-digit Nepal mobile number (e.g. 98XXXXXXXX)
    if len(digits) == 10 and digits.startswith("9"):
        return f"{country}{digits}"

    # Number already formatted internationally
    if len(digits) >= 10:
        return digits

    raise ValueError(f"Invalid phone number for WhatsApp: '{value}'")


def build_whatsapp_click_to_chat_url(
    recipient: str,
    message: str,
    default_country: str = "977",
) -> str:
    """Construct official WhatsApp universal click-to-chat URL (https://wa.me/...)."""
    normalized_phone = normalize_whatsapp_recipient(recipient, default_country)
    encoded_text = urllib.parse.quote(message.strip())
    return f"https://wa.me/{normalized_phone}?text={encoded_text}"
