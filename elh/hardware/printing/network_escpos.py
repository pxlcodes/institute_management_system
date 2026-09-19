from __future__ import annotations

import socket
from decimal import Decimal

from elh.models import Receipt
from .base import ReceiptPrinterError


class NetworkEscPosPrinter:
    """Dependency-free ESC/POS adapter for Ethernet printers using raw port 9100."""

    def __init__(self, host: str, port: int = 9100, width: int = 42):
        if not host:
            raise ValueError("ELH_POS_PRINTER_HOST is required for a network ESC/POS printer.")
        self.host, self.port, self.width = host, port, width

    def _render(self, receipt: Receipt) -> bytes:
        lines = []
        if getattr(receipt, "org_name", ""):
            lines.append(receipt.org_name.center(self.width))
        if getattr(receipt, "org_address", ""):
            lines.append(receipt.org_address.center(self.width))
        meta = []
        if getattr(receipt, "org_phone", ""):
            meta.append(f"Phone: {receipt.org_phone}")
        if getattr(receipt, "org_pan", ""):
            meta.append(f"PAN: {receipt.org_pan}")
        if meta:
            lines.append(" | ".join(meta).center(self.width))
        if getattr(receipt, "org_name", ""):
            lines.append("-" * self.width)

        lines.append(receipt.title.center(self.width))
        lines.append(f"Bill No : {receipt.receipt_number}")
        lines.append(f"Date    : {receipt.issued_at}")
        if receipt.customer_name:
            lines.append(f"Student : {receipt.customer_name}")
        if getattr(receipt, "contact", ""):
            lines.append(f"Contact : {receipt.contact}")
        if getattr(receipt, "class_name", ""):
            lines.append(f"Class   : {receipt.class_name}")
        lines.append("-" * self.width)
        for item in receipt.lines:
            if receipt.show_amounts and item.amount != Decimal("0"):
                amount = f"{item.amount:,.2f}"
                desc_max = self.width - len(amount) - 1
                lines.append(f"{item.description[:desc_max]:<{desc_max}} {amount}")
            else:
                lines.append(item.description[:self.width])
        lines.append("-" * self.width)
        if receipt.show_amounts:
            lines.append(f"TOTAL {receipt.total:,.2f}".rjust(self.width))

        text_part = b"\x1b@" + "\n".join(lines).encode("utf-8", errors="replace") + b"\n"

        qr_part = b""
        if getattr(receipt, "qr_payload", None):
            from elh.core.payment_qr import PaymentQrEngine
            caption = getattr(receipt, "qr_caption", "") or "Scan to Pay via Fonepay / eSewa"
            qr_part += b"\n" + caption.center(self.width).encode("utf-8", errors="replace") + b"\n\n"
            qr_part += PaymentQrEngine.build_escpos_raster(
                receipt.qr_payload,
                printer_chars=self.width,
            )
            qr_part += b"\n"

        footer_lines = [""]
        if getattr(receipt, "footer_note", ""):
            footer_lines.append(receipt.footer_note.center(self.width))
        if receipt.footer:
            footer_lines.append(receipt.footer.center(self.width))
        footer_lines.extend(["", "", "", "", "", ""])
        footer_part = "\n".join(footer_lines).encode("utf-8", errors="replace") + b"\x1dV\x00"
        return text_part + qr_part + footer_part

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
