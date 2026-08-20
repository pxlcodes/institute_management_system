from __future__ import annotations

import socket

from elh.models import Receipt
from .base import ReceiptPrinterError


class NetworkEscPosPrinter:
    """Dependency-free ESC/POS adapter for Ethernet printers using raw port 9100."""

    def __init__(self, host: str, port: int = 9100, width: int = 42):
        if not host:
            raise ValueError("ELH_POS_PRINTER_HOST is required for a network ESC/POS printer.")
        self.host, self.port, self.width = host, port, width

    def _render(self, receipt: Receipt) -> bytes:
        lines = [receipt.title.center(self.width), f"Receipt: {receipt.receipt_number}",
                 f"Date: {receipt.issued_at}"]
        if receipt.customer_name:
            lines.append(f"Name: {receipt.customer_name}")
        lines.append("-" * self.width)
        for item in receipt.lines:
            amount = f"{item.amount:.2f}"
            lines.append(f"{item.description[:self.width-len(amount)-1]:<{self.width-len(amount)}}{amount}")
        lines.extend(["-" * self.width, f"TOTAL {receipt.total:.2f}".rjust(self.width),
                      "", receipt.footer.center(self.width), "", "", "", "", "", ""])
        return b"\x1b@" + "\n".join(lines).encode("utf-8", errors="replace") + b"\x1dV\x00"

    def print_receipt(self, receipt: Receipt) -> None:
        try:
            with socket.create_connection((self.host, self.port), timeout=5) as connection:
                connection.sendall(self._render(receipt))
        except OSError as exc:
            raise ReceiptPrinterError(f"Cannot print to {self.host}:{self.port}: {exc}") from exc

    def health(self) -> tuple[bool, str]:
        try:
            with socket.create_connection((self.host, self.port), timeout=2):
                return True, f"POS printer reachable at {self.host}:{self.port}"
        except OSError as exc:
            return False, str(exc)
