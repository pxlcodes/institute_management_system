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

    @property
    def total(self) -> Decimal:
        return sum((line.amount for line in self.lines), Decimal("0"))
