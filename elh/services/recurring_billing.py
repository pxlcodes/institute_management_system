from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from elh.core.settings import SettingsService
from elh.core.validation import add_days, current_month, today_iso, validate_date, validate_month
from elh.models import DueBill
from elh.services.billing import BillingService

logger = logging.getLogger("elh.services.recurring_billing")


@dataclass
class UnbilledEnrollment:
    enrollment_id: int
    student_id: int
    student_name: str
    course_name: str
    course_category: str
    level: str
    contact: str
    start_date: str
    end_date: str | None
    monthly_fee: Decimal
    admission_fee: Decimal
    discount: Decimal
    is_first_bill: bool
    estimated_amount: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "enrollment_id": self.enrollment_id,
            "student_id": self.student_id,
            "student_name": self.student_name,
            "course_name": self.course_name,
            "course_category": self.course_category,
            "level": self.level,
            "contact": self.contact,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "monthly_fee": float(self.monthly_fee),
            "admission_fee": float(self.admission_fee),
            "discount": float(self.discount),
            "is_first_bill": self.is_first_bill,
            "estimated_amount": float(self.estimated_amount),
        }


@dataclass
class AutoBillingResult:
    target_month: str
    total_eligible: int
    bills_created: int
    bills_skipped: int
    total_invoiced_amount: Decimal
    bills: list[DueBill] = field(default_factory=list)
    sms_queued_count: int = 0
    executed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_month": self.target_month,
            "total_eligible": self.total_eligible,
            "bills_created": self.bills_created,
            "bills_skipped": self.bills_skipped,
            "total_invoiced_amount": float(self.total_invoiced_amount),
            "bills_count": len(self.bills),
            "sms_queued_count": self.sms_queued_count,
            "executed_at": self.executed_at,
        }


class RecurringBillingService:
    """Service to evaluate, automate, and orchestrate monthly recurring student invoicing."""

    def __init__(
        self,
        db: Any,
        billing_service: BillingService,
        settings: SettingsService,
    ):
        self.db = db
        self.billing = billing_service
        self.settings = settings

    def get_config(self) -> dict[str, Any]:
        """Return the current auto-invoicing configuration."""
        return {
            "enabled": self.settings.get_bool("auto_billing_enabled", False),
            "due_days": self.settings.get_int("auto_billing_due_days", 7),
            "auto_sms": self.settings.get_bool("auto_billing_auto_sms", True),
            "last_run_month": self.settings.get("auto_billing_last_run_month", ""),
            "last_run_at": self.settings.get("auto_billing_last_run_at", ""),
        }

    def update_config(
        self,
        enabled: bool | None = None,
        due_days: int | None = None,
        auto_sms: bool | None = None,
    ) -> dict[str, Any]:
        """Update auto-invoicing settings."""
        if enabled is not None:
            self.settings.set(
                "auto_billing_enabled",
                "true" if enabled else "false",
                "Billing",
                "Enable Auto Recurring Invoicing",
                "boolean",
                "Automatically generate recurring monthly bills for active student enrollments.",
            )
        if due_days is not None:
            days = max(1, min(60, int(due_days)))
            self.settings.set(
                "auto_billing_due_days",
                str(days),
                "Billing",
                "Auto-Invoice Due Days",
                "integer",
                "Number of calendar days after the bill issue date until payment is marked due.",
            )
        if auto_sms is not None:
            self.settings.set(
                "auto_billing_auto_sms",
                "true" if auto_sms else "false",
                "Billing",
                "Auto-Invoice SMS Notification",
                "boolean",
                "Automatically queue and dispatch SMS due notifications when auto-invoicing creates a bill.",
            )
        return self.get_config()

    def get_unbilled_enrollments(
        self, target_month: str | None = None
    ) -> list[UnbilledEnrollment]:
        """Find active enrollments eligible for billing in target_month that have not been billed."""
        target = validate_month(target_month or current_month(), "Target billing month")

        rows = self.db.query(
            "SELECT e.id, e.student_id, e.course_id, e.level, e.start_date, e.end_date, "
            "e.monthly_fee, e.admission_fee, e.discount, e.status, "
            "s.student_name, s.contact, c.course_name, c.category, c.billing_type "
            "FROM enrollments e "
            "JOIN students s ON s.id = e.student_id "
            "JOIN courses c ON c.id = e.course_id "
            "WHERE e.status = 'Active' AND s.status = 'Active' "
            "ORDER BY s.student_name, c.course_name"
        )

        if not rows:
            return []

        # Filter by start_date <= target and (end_date is null or end_date >= target)
        eligible_rows = []
        enrollment_ids = []
        for r in rows:
            start_m = self.billing.get_effective_billing_start_month(str(r["start_date"] or ""))
            end_m = str(r["end_date"] or "")[:7] if r["end_date"] else None
            if start_m and start_m > target:
                continue
            if end_m and end_m < target:
                continue
            eligible_rows.append(r)
            enrollment_ids.append(int(r["id"]))

        if not enrollment_ids:
            return []

        # Check existing bills for target_month
        billed_map = self.billing.repository.billed_months_many(enrollment_ids, [target])
        bill_counts = self.billing.repository.bill_counts(enrollment_ids)

        unbilled: list[UnbilledEnrollment] = []
        for r in eligible_rows:
            eid = int(r["id"])
            if target in billed_map.get(eid, {}):
                continue

            first_bill = bill_counts.get(eid, 0) == 0
            monthly = Decimal(str(r["monthly_fee"] or 0))
            admission = Decimal(str(r["admission_fee"] or 0)) if first_bill else Decimal("0")
            discount = Decimal(str(r["discount"] or 0)) if first_bill else Decimal("0")
            estimated = max(Decimal("0"), monthly + admission - discount)

            unbilled.append(
                UnbilledEnrollment(
                    enrollment_id=eid,
                    student_id=int(r["student_id"]),
                    student_name=str(r["student_name"]),
                    course_name=str(r["course_name"]),
                    course_category=str(r["category"] or ""),
                    level=str(r["level"] or ""),
                    contact=str(r["contact"] or ""),
                    start_date=str(r["start_date"]),
                    end_date=str(r["end_date"]) if r["end_date"] else None,
                    monthly_fee=monthly,
                    admission_fee=admission,
                    discount=discount,
                    is_first_bill=first_bill,
                    estimated_amount=estimated,
                )
            )

        return unbilled

    def preview(self, target_month: str | None = None) -> dict[str, Any]:
        """Generate a preview report of what auto-invoicing will execute."""
        target = validate_month(target_month or current_month(), "Target billing month")
        unbilled = self.get_unbilled_enrollments(target)
        total_amount = sum((item.estimated_amount for item in unbilled), Decimal("0"))
        return {
            "target_month": target,
            "unbilled_count": len(unbilled),
            "total_estimated_amount": float(total_amount),
            "unbilled_enrollments": [item.to_dict() for item in unbilled],
            "config": self.get_config(),
        }

    def run_auto_billing(
        self,
        target_month: str | None = None,
        issue_date: str | None = None,
        due_date: str | None = None,
        send_sms: bool | None = None,
        remarks: str = "Automated monthly recurring invoice",
        actor_username: str = "system",
    ) -> AutoBillingResult:
        """Execute automated monthly recurring invoicing for all unbilled active students."""
        target = validate_month(target_month or current_month(), "Target billing month")
        issue = validate_date(issue_date or today_iso(), "Issue date")

        if due_date:
            due = validate_date(due_date, "Due date")
        else:
            due_days = self.settings.get_int("auto_billing_due_days", 7)
            due = add_days(issue, due_days)

        unbilled = self.get_unbilled_enrollments(target)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not unbilled:
            logger.info("Auto-billing for %s: All active enrollments are already invoiced.", target)
            self.settings.set("auto_billing_last_run_month", target, "Billing", "Last Auto-Invoiced Month")
            self.settings.set("auto_billing_last_run_at", now_str, "Billing", "Last Auto-Invoicing Run Timestamp")
            return AutoBillingResult(
                target_month=target,
                total_eligible=0,
                bills_created=0,
                bills_skipped=0,
                total_invoiced_amount=Decimal("0"),
                bills=[],
                sms_queued_count=0,
                executed_at=now_str,
            )

        enrollment_ids = [item.enrollment_id for item in unbilled]
        results = self.billing.generate_combined_month_range(
            enrollment_ids=enrollment_ids,
            start_month=target,
            end_month=target,
            issue_date=issue,
            due_date=due,
            remarks=remarks,
        )

        created_bills = [r.bill for r in results if r.created]
        skipped_count = len(results) - len(created_bills)
        total_amount = sum((b.total_amount for b in created_bills), Decimal("0"))

        # Update last run markers in settings
        self.settings.set("auto_billing_last_run_month", target, "Billing", "Last Auto-Invoiced Month")
        self.settings.set("auto_billing_last_run_at", now_str, "Billing", "Last Auto-Invoicing Run Timestamp")

        # Record audit event
        try:
            self.db.execute(
                "INSERT INTO auth_audit_log (username, event_type, success, detail) VALUES (?,?,?,?)",
                (
                    actor_username,
                    "auto_billing",
                    1,
                    f"Generated {len(created_bills)} monthly bills for {target} totaling {self.billing.currency_symbol} {total_amount:,.2f} ({skipped_count} skipped)",
                ),
            )
        except Exception:
            pass

        logger.info(
            "Auto-billing for %s completed: %d created, %d skipped, total amount: %s",
            target,
            len(created_bills),
            skipped_count,
            total_amount,
        )

        return AutoBillingResult(
            target_month=target,
            total_eligible=len(unbilled),
            bills_created=len(created_bills),
            bills_skipped=skipped_count,
            total_invoiced_amount=total_amount,
            bills=created_bills,
            sms_queued_count=len(created_bills) if self.settings.get_bool("auto_billing_auto_sms", True) else 0,
            executed_at=now_str,
        )

    def check_and_run_scheduled(self) -> AutoBillingResult | None:
        """Check if auto-invoicing is enabled and pending for the current month; run if needed."""
        if not self.settings.get_bool("auto_billing_enabled", False):
            return None

        current = current_month()
        last_run = self.settings.get("auto_billing_last_run_month", "").strip()

        if last_run == current:
            # Already executed for this month
            return None

        logger.info("Scheduled auto-invoicing triggered for new month: %s", current)
        return self.run_auto_billing(target_month=current, actor_username="auto_scheduler")
