from __future__ import annotations

from typing import Protocol

from elh.models import Receipt


class ReceiptPrinterError(RuntimeError):
    pass


class ReceiptPrinter(Protocol):
    def print_receipt(self, receipt: Receipt) -> None: ...
    def health(self) -> tuple[bool, str]: ...
