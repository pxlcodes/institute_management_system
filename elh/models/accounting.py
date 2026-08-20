from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class AccountBalance:
    account_id: int
    account_name: str
    amount: Decimal


@dataclass(frozen=True)
class MoneyMovement:
    transaction_date: str
    account_id: int
    direction: str
    amount: Decimal
    source_type: str
    source_id: int
    particular: str
    reference_no: str = ""
    remarks: str = ""
