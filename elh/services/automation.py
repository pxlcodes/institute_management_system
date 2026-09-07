from __future__ import annotations

import logging
import threading
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from elh.config import AppConfig
from elh.core.backup import BackupService
from elh.core.settings import SettingsService
from elh.core.validation import today_iso
from elh.services.attendance import AttendanceService
from elh.services.notifications import NotificationService
from elh.services.recurring_billing import AutoBillingResult, RecurringBillingService

logger = logging.getLogger("elh.services.automation")


class AutomationScheduler:
    """Thread-safe background daemon orchestrating periodic institutional automation.

    Automated jobs executed:
    1. Recurring Monthly Invoicing: Automatically generates monthly due bills and queues SMS notices.
    2. Daily Absence SMS Dispatcher: Evaluates unpunched active students after the cutoff time and
       dispatches absence SMS to parents with zero duplicate deliveries.
    3. Due Date & Overdue Bill Reminders: Dispatches friendly pre-due and overdue escalation SMS.
    4. SMS Outbox Worker: Ensures pending SMS deliveries are dispatched across network reconnects.
    5. Daily Automated DB Backup: Creates a verified snapshot in the backups/ directory.
    """

    def __init__(
        self,
        db: Any,
        config: AppConfig,
        settings: SettingsService,
        notifications: NotificationService,
        recurring_billing: RecurringBillingService,
        attendance: AttendanceService,
        check_interval_seconds: int = 60,
    ):
        self.db = db
        self.config = config
        self.settings = settings
        self.notifications = notifications
        self.recurring_billing = recurring_billing
        self.attendance = attendance
        self.check_interval_seconds = max(5, int(check_interval_seconds))

        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Operational metrics
        self.last_run_at: datetime | None = None
        self.last_check_status: dict[str, Any] = {}
        self.total_runs_count: int = 0

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """Start the background automation worker thread."""
        with self._lock:
            if self.is_running:
                return True
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._worker_loop,
                daemon=True,
                name="elh-automation-scheduler",
            )
            self._thread.start()
            logger.info(
                "Automation background scheduler started (check interval: %ds).",
                self.check_interval_seconds,
            )
            return True

    def stop(self, timeout: float = 3.0) -> None:
        """Signal the background worker to stop and wait for completion."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None
        logger.info("Automation background scheduler stopped.")

    def _worker_loop(self) -> None:
        # Give services a brief moment on startup before triggering first cycle
        if not self._stop_event.wait(3.0):
            try:
                self.run_due_jobs()
            except Exception as exc:
                logger.warning("Initial automation run encountered an issue: %s", exc)

        while not self._stop_event.is_set():
            if self._stop_event.wait(self.check_interval_seconds):
                break
            try:
                self.run_due_jobs()
            except Exception as exc:
                logger.warning("Periodic automation run encountered an issue: %s", exc)

    def run_due_jobs(self, force: bool = False) -> dict[str, Any]:
        """Execute all scheduled tasks that are currently due or forced."""
        with self._lock:
            results: dict[str, Any] = {}

            # 1. SMS Dispatch Guard
            try:
                results["sms_dispatched"] = self.check_sms_dispatch()
            except Exception as exc:
                results["sms_dispatched_error"] = str(exc)

            # 2. Recurring Monthly Invoicing
            try:
                billing_res = self.check_recurring_billing()
                results["recurring_billing"] = billing_res.to_dict() if billing_res else None
            except Exception as exc:
                results["recurring_billing_error"] = str(exc)

            # 3. Daily Absence SMS Dispatch
            try:
                results["absence_sms"] = self.check_daily_absence_sms(force=force)
            except Exception as exc:
                results["absence_sms_error"] = str(exc)

            # 4. Due & Overdue Bill Reminders
            try:
                results["bill_reminders"] = self.check_bill_reminders(force=force)
            except Exception as exc:
                results["bill_reminders_error"] = str(exc)

            # 5. Automated Daily Backup Snapshot
            try:
                backup_path = self.check_daily_backup(force=force)
                results["daily_backup"] = str(backup_path) if backup_path else None
            except Exception as exc:
                results["daily_backup_error"] = str(exc)

            self.last_run_at = datetime.now()
            self.last_check_status = results
            self.total_runs_count += 1
            return results

    def check_sms_dispatch(self) -> int:
        """Ensure pending SMS outbox records are processed."""
        if not self.settings.get_bool("sms_enabled", False):
            return 0
        return self.notifications.dispatch_pending(limit=20)

    def check_recurring_billing(self) -> AutoBillingResult | None:
        """Check if monthly auto-invoicing is due and run it."""
        if not self.settings.get_bool("auto_billing_enabled", False):
            return None
        return self.recurring_billing.check_and_run_scheduled()

    def check_daily_absence_sms(self, force: bool = False) -> dict[str, Any]:
        """Evaluate unpunched students and dispatch daily absence SMS to parents."""
        if not force:
            if not self.settings.get_bool("auto_absence_sms_enabled", False):
                return {"status": "disabled"}
            if not self.settings.get_bool("sms_enabled", False):
                return {"status": "sms_disabled"}

        today_str = today_iso()
        today_date_norm = datetime.now().strftime("%Y-%m-%d")
        last_run_date = self.settings.get("auto_absence_last_run_date", "").strip()

        if not force and last_run_date == today_date_norm:
            return {"status": "already_run_today", "date": last_run_date}

        if not force:
            cutoff = self.settings.get("auto_absence_cutoff_time", "11:00").strip()
            try:
                cutoff_h, cutoff_m = (int(x) for x in cutoff.split(":"))
            except Exception:
                cutoff_h, cutoff_m = 11, 0
            now = datetime.now()
            if (now.hour, now.minute) < (cutoff_h, cutoff_m):
                return {"status": "before_cutoff", "cutoff": cutoff}

        absent_students = self.attendance.students_absent_today()
        if not absent_students:
            self.settings.set(
                "auto_absence_last_run_date",
                today_date_norm,
                "Attendance",
                "Last Auto Absence Run Date",
            )
            return {"status": "no_absentees", "queued": 0, "skipped": 0}

        student_ids = [int(r["id"]) for r in absent_students]
        queued, skipped = self.notifications.queue_auto_absence_sms(today_str, student_ids)

        self.settings.set(
            "auto_absence_last_run_date",
            today_date_norm,
            "Attendance",
            "Last Auto Absence Run Date",
        )
        logger.info(
            "Auto daily absence SMS executed: %d queued, %d skipped",
            len(queued),
            len(skipped),
        )
        return {
            "status": "completed",
            "date": today_date_norm,
            "queued": len(queued),
            "skipped": len(skipped),
            "skipped_details": skipped,
        }

    def check_bill_reminders(self, force: bool = False) -> dict[str, Any]:
        """Dispatch pre-due and overdue SMS reminders for outstanding bills."""
        if not force:
            if not self.settings.get_bool("auto_reminders_enabled", False):
                return {"status": "disabled"}
            if not self.settings.get_bool("sms_enabled", False):
                return {"status": "sms_disabled"}

        today_str = datetime.now().strftime("%Y-%m-%d")
        last_run = self.settings.get("auto_reminders_last_run_date", "").strip()
        if not force and last_run == today_str:
            return {"status": "already_run_today"}

        if not force:
            # Run in the morning (at or after 09:30 AM)
            now = datetime.now()
            if now.hour < 9 or (now.hour == 9 and now.minute < 30):
                return {"status": "before_reminder_time"}

        bills = self.db.query(
            "SELECT b.id, b.bill_number, b.billing_period, b.issue_date, b.due_date, "
            "b.total_amount, b.paid_amount, s.student_name, s.contact, c.course_name "
            "FROM due_bills b "
            "JOIN enrollments e ON e.id = b.enrollment_id "
            "JOIN students s ON s.id = e.student_id "
            "JOIN courses c ON c.id = e.course_id "
            "WHERE b.status != 'Paid' AND b.total_amount > b.paid_amount"
        )
        if not bills:
            self.settings.set(
                "auto_reminders_last_run_date",
                today_str,
                "Billing",
                "Last Reminders Run Date",
            )
            return {"status": "no_pending_bills", "queued": 0}

        queued_count = 0
        today_date = datetime.now().date()

        for b in bills:
            due_str = str(b["due_date"] or "")
            if not due_str or not b["contact"]:
                continue
            clean_due = due_str.replace("/", "-")
            try:
                due_d = datetime.strptime(clean_due[:10], "%Y-%m-%d").date()
            except Exception:
                continue

            diff_days = (due_d - today_date).days
            unpaid_amt = Decimal(str(b["total_amount"])) - Decimal(str(b["paid_amount"]))
            context = {
                "student_name": b["student_name"],
                "course_name": b["course_name"],
                "bill_number": b["bill_number"],
                "amount": f"{unpaid_amt:,.2f}",
                "due_date": b["due_date"],
                "period": b["billing_period"],
            }

            # T-2 days reminder
            if diff_days == 2:
                entity_type = f"due_remind_t2_{clean_due[:10]}"[:50]
                existing = self.db.query_one(
                    "SELECT id FROM sms_delivery_log WHERE event_key='due_bill_reminder' "
                    "AND entity_type=? AND entity_id=?",
                    (entity_type, b["id"]),
                )
                if not existing:
                    log_id = self.notifications.notify(
                        "due_bill_reminder", entity_type, b["id"], b["contact"], context
                    )
                    if log_id:
                        queued_count += 1

            # Due today reminder
            elif diff_days == 0:
                entity_type = f"due_remind_t0_{clean_due[:10]}"[:50]
                existing = self.db.query_one(
                    "SELECT id FROM sms_delivery_log WHERE event_key='due_bill_reminder' "
                    "AND entity_type=? AND entity_id=?",
                    (entity_type, b["id"]),
                )
                if not existing:
                    log_id = self.notifications.notify(
                        "due_bill_reminder", entity_type, b["id"], b["contact"], context
                    )
                    if log_id:
                        queued_count += 1

            # Overdue notice: 3 or 7 days past due date
            elif diff_days in (-3, -7):
                entity_type = f"overdue_{abs(diff_days)}d_{clean_due[:10]}"[:50]
                existing = self.db.query_one(
                    "SELECT id FROM sms_delivery_log WHERE event_key='due_bill_overdue' "
                    "AND entity_type=? AND entity_id=?",
                    (entity_type, b["id"]),
                )
                if not existing:
                    log_id = self.notifications.notify(
                        "due_bill_overdue", entity_type, b["id"], b["contact"], context
                    )
                    if log_id:
                        queued_count += 1

        self.settings.set(
            "auto_reminders_last_run_date",
            today_str,
            "Billing",
            "Last Reminders Run Date",
        )
        return {"status": "completed", "queued": queued_count}

    def check_daily_backup(self, force: bool = False) -> Path | None:
        """Create an automated verified database backup if scheduled."""
        if not force and not self.settings.get_bool("auto_backup_daily_enabled", True):
            return None

        today_str = datetime.now().strftime("%Y-%m-%d")
        last_backup_date = self.settings.get("auto_backup_last_run_date", "").strip()

        if not force and last_backup_date == today_str:
            return None

        now_hour = datetime.now().hour
        # Take evening backup after classes (>= 18:00) unless forced or never backed up
        if not force and last_backup_date and now_hour < 18:
            return None

        if self.config.database_engine == "sqlite" and not self.config.database_path.exists():
            return None

        try:
            backup_svc = BackupService(self.config)
            dest = backup_svc.create()
            self.settings.set(
                "auto_backup_last_run_date",
                today_str,
                "Application",
                "Last Auto-Backup Date",
            )
            logger.info("Automated daily backup created successfully: %s", dest)
            return dest
        except Exception as exc:
            logger.warning("Automated daily backup encountered an issue: %s", exc)
            return None

    def status(self) -> dict[str, Any]:
        """Return operational status and statistics of the automation scheduler."""
        return {
            "is_running": self.is_running,
            "interval_seconds": self.check_interval_seconds,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "total_runs_count": self.total_runs_count,
            "last_check_status": self.last_check_status,
            "config": {
                "auto_billing_enabled": self.settings.get_bool("auto_billing_enabled", False),
                "auto_absence_sms_enabled": self.settings.get_bool("auto_absence_sms_enabled", False),
                "auto_absence_cutoff_time": self.settings.get("auto_absence_cutoff_time", "11:00"),
                "auto_reminders_enabled": self.settings.get_bool("auto_reminders_enabled", False),
                "auto_backup_daily_enabled": self.settings.get_bool("auto_backup_daily_enabled", True),
                "sms_enabled": self.settings.get_bool("sms_enabled", False),
            },
        }
