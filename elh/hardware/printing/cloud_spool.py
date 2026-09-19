from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from elh.hardware.printing.base import ReceiptPrinter, ReceiptPrinterError
from elh.models import Receipt, ReceiptLine


def receipt_to_dict(receipt: Receipt) -> dict[str, Any]:
    """Convert Receipt dataclass into a JSON-serializable dictionary."""
    return {
        "title": receipt.title,
        "receipt_number": receipt.receipt_number,
        "issued_at": receipt.issued_at,
        "customer_name": receipt.customer_name,
        "lines": [
            {"description": line.description, "amount": str(line.amount)}
            for line in receipt.lines
        ],
        "footer": receipt.footer,
        "show_amounts": receipt.show_amounts,
        "qr_payload": receipt.qr_payload,
        "qr_caption": receipt.qr_caption,
        "class_name": receipt.class_name,
        "contact": receipt.contact,
        "org_name": receipt.org_name,
        "org_address": receipt.org_address,
        "org_phone": receipt.org_phone,
        "org_pan": receipt.org_pan,
        "footer_note": receipt.footer_note,
    }


def dict_to_receipt(data: dict[str, Any]) -> Receipt:
    """Reconstruct a Receipt dataclass from a dictionary."""
    return Receipt(
        title=data.get("title", "RECEIPT"),
        receipt_number=data.get("receipt_number", ""),
        issued_at=data.get("issued_at", ""),
        customer_name=data.get("customer_name", ""),
        lines=[
            ReceiptLine(description=item["description"], amount=Decimal(str(item["amount"])))
            for item in data.get("lines", [])
        ],
        footer=data.get("footer", "Thank you"),
        show_amounts=data.get("show_amounts", True),
        qr_payload=data.get("qr_payload", ""),
        qr_caption=data.get("qr_caption", ""),
        class_name=data.get("class_name", ""),
        contact=data.get("contact", ""),
        org_name=data.get("org_name", ""),
        org_address=data.get("org_address", ""),
        org_phone=data.get("org_phone", ""),
        org_pan=data.get("org_pan", ""),
        footer_note=data.get("footer_note", ""),
    )


class CloudSpoolReceiptPrinter:
    """Spools print receipts into a central database queue.

    Used when the ELH web app is hosted remotely (e.g. cPanel) and cannot directly
    reach the institute's internal LAN POS printer. The Institute Admin PC runs a
    sync service that pulls pending jobs and prints them locally.
    """

    def __init__(self, db=None):
        self.db = db

    def print_receipt(self, receipt: Receipt) -> None:
        if self.db is None:
            raise ReceiptPrinterError("Database not configured for Cloud Print Spooler.")
        payload = json.dumps(receipt_to_dict(receipt), ensure_ascii=False)
        self.db.execute(
            """
            INSERT INTO pos_print_queue (receipt_number, customer_name, title, payload_json, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)
            """,
            (receipt.receipt_number, receipt.customer_name, receipt.title, payload),
        )

    def health(self) -> tuple[bool, str]:
        if self.db is None:
            return (False, "Cloud Spool database connection unavailable")
        try:
            row = self.db.query_one("SELECT COUNT(*) AS pending_count FROM pos_print_queue WHERE status = 'pending'")
            pending = row["pending_count"] if row else 0
            return (True, f"Cloud Print Spool active ({pending} pending in institute queue)")
        except Exception as exc:
            return (False, f"Cloud Spool database error: {exc}")
