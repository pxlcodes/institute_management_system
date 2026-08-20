from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SmsProviderResponse:
    success: bool
    code: str
    message: str


class SmsProvider(Protocol):
    name: str

    def send(self, recipient: str, message: str) -> SmsProviderResponse: ...
