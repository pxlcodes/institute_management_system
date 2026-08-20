from __future__ import annotations

from elh.config import AppConfig

from .aakash import AakashSmsProvider
from .sparrow import SparrowSmsProvider


def create_sms_provider(
    provider_name: str,
    config: AppConfig,
    sender_id: str,
    timeout: int,
):
    provider = provider_name.strip().lower()
    if provider == "aakash":
        return AakashSmsProvider(
            config.aakash_sms_endpoint,
            config.aakash_sms_token,
            timeout,
        )
    if provider == "sparrow":
        return SparrowSmsProvider(
            config.sparrow_sms_endpoint,
            config.sparrow_sms_token,
            sender_id,
            timeout,
        )
    raise ValueError("SMS provider must be Aakash or Sparrow.")
