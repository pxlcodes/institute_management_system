from __future__ import annotations

from typing import Any

from .base import (
    WhatsAppProvider,
    WhatsAppResponse,
    build_whatsapp_click_to_chat_url,
    normalize_whatsapp_recipient,
)
from .gateway import GenericWhatsAppGatewayProvider
from .meta_cloud import MetaWhatsAppCloudProvider


def create_whatsapp_provider(
    provider_name: str,
    settings: Any = None,
    config: Any = None,
    timeout: int = 15,
) -> WhatsAppProvider | None:
    """Factory to instantiate the appropriate WhatsApp Provider from settings or configuration."""
    name = (provider_name or "").strip().lower()

    default_country = "977"
    if settings and hasattr(settings, "get"):
        default_country = settings.get("whatsapp_country_code", "977") or "977"

    if "meta" in name or name == "meta_cloud":
        phone_id = ""
        token = ""
        if settings and hasattr(settings, "get"):
            phone_id = settings.get("whatsapp_meta_phone_number_id", "")
            token = settings.get("whatsapp_meta_access_token", "")
        if not phone_id and config:
            phone_id = getattr(config, "whatsapp_meta_phone_number_id", "")
        if not token and config:
            token = getattr(config, "whatsapp_meta_access_token", "")

        return MetaWhatsAppCloudProvider(
            phone_number_id=phone_id,
            access_token=token,
            default_country=default_country,
            timeout_seconds=timeout,
        )

    if "gateway" in name or "third_party" in name or "ultramsg" in name:
        endpoint = ""
        token = ""
        instance_id = ""
        if settings and hasattr(settings, "get"):
            endpoint = settings.get("whatsapp_gateway_endpoint", "")
            token = settings.get("whatsapp_gateway_token", "")
            instance_id = settings.get("whatsapp_gateway_instance_id", "")
        if not endpoint and config:
            endpoint = getattr(config, "whatsapp_gateway_endpoint", "")
        if not token and config:
            token = getattr(config, "whatsapp_gateway_token", "")

        return GenericWhatsAppGatewayProvider(
            endpoint=endpoint,
            token=token,
            instance_id=instance_id,
            default_country=default_country,
            timeout_seconds=timeout,
        )

    return None
