from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class DueBill:
    id: int
    bill_number: str
    enrollment_id: int
    student_id: int
    student_name: str
    course_name: str
    billing_period: str
    issue_date: str
    due_date: str
    subtotal: Decimal
    discount: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    status: str
    pdf_path: str = ""


@dataclass(frozen=True)
class BillGenerationResult:
    bill: DueBill
    created: bool
