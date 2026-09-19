from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class ReceiptLine:
    description: str
    amount: Decimal


@dataclass(frozen=True)
class Receipt:
    title: str
    receipt_number: str
    issued_at: str
    customer_name: str = ""
    lines: list[ReceiptLine] = field(default_factory=list)
    footer: str = "Thank you"
    show_amounts: bool = True
    qr_payload: str = ""
    qr_caption: str = ""
    class_name: str = ""
    contact: str = ""
    org_name: str = ""
    org_address: str = ""
    org_phone: str = ""
    org_pan: str = ""
    footer_note: str = ""

    @property
    def total(self) -> Decimal:
        return sum((line.amount for line in self.lines), Decimal("0"))
