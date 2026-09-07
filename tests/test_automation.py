from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from elh.config import AppConfig
from elh.core.settings import SettingsService
from elh.core.validation import current_month, today_iso
from elh.infrastructure.sqlite_database import SQLiteDatabase
from elh.repositories import BillingRepository
from elh.services.attendance import AttendanceService
from elh.services.automation import AutomationScheduler
from elh.services.billing import BillingService
from elh.services.container import ServiceContainer
from elh.services.notifications import NotificationService
from elh.services.printing import PrintingService
from elh.services.recurring_billing import RecurringBillingService


class TestAutomationScheduler(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test_automation.db"
        self.config = AppConfig(
            database_path=self.db_path,
            database_engine="sqlite",
            backup_directory=Path(self.tmpdir.name) / "backups",
            attendance_driver="disabled",
            attendance_auto_poll=False,
            sparrow_sms_token="mock_sparrow_token",
            aakash_sms_token="mock_aakash_token",
        )
        self.db = SQLiteDatabase(self.db_path, False)
        self.settings = SettingsService(self.db)
        self.settings.ensure_defaults()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_whatsapp_opt_out_default(self):
        """WhatsApp integration must be disabled by default (opted out)."""
        self.assertFalse(self.settings.get_bool("whatsapp_enabled", False))

    def test_automation_settings_defaults(self):
        """New automation settings should have sane defaults."""
        self.assertFalse(self.settings.get_bool("auto_absence_sms_enabled", True))
        self.assertEqual(self.settings.get("auto_absence_cutoff_time", ""), "11:00")
        self.assertTrue(self.settings.get_bool("auto_backup_daily_enabled", False))
        self.assertFalse(self.settings.get_bool("auto_reminders_enabled", True))

    def test_queue_auto_absence_sms_deduplication(self):
        """Automated absence SMS should not re-queue on the same day for the same student."""
        self.settings.set("sms_enabled", "true")
        self.settings.set("sms_provider", "aakash")

        # Create student
        student_id = self.db.execute(
            "INSERT INTO students (student_name, contact, status, joining_date) "
            "VALUES ('Rohan Sharma', '9841234567', 'Active', '2026-01-01')"
        )

        notif = NotificationService(self.db, self.config)

        # Mock dispatch_async so no real network requests are attempted
        with patch.object(notif, "dispatch_async"):
            # First automated queue
            queued1, skipped1 = notif.queue_auto_absence_sms(
                attendance_date="2026/09/04",
                student_ids=[student_id],
            )
            self.assertEqual(len(queued1), 1)
            self.assertEqual(len(skipped1), 0)

            # Second automated queue for same student on same day -> must be deduplicated
            queued2, skipped2 = notif.queue_auto_absence_sms(
                attendance_date="2026/09/04",
                student_ids=[student_id],
            )
            self.assertEqual(len(queued2), 0)
            self.assertEqual(len(skipped2), 1)
            self.assertIn("Already notified", skipped2[0])

    def test_automation_scheduler_lifecycle(self):
        """Test start, stop, and status of AutomationScheduler."""
        container = ServiceContainer.build(self.config, self.db)
        scheduler = container.automation

        self.assertIsInstance(scheduler, AutomationScheduler)
        self.assertTrue(scheduler.is_running)

        status = scheduler.status()
        self.assertTrue(status["is_running"])
        self.assertIn("config", status)

        # Stop cleanly
        scheduler.stop(timeout=2.0)
        self.assertFalse(scheduler.is_running)

    def test_recurring_billing_automation(self):
        """Scheduler runs monthly recurring billing when enabled and due."""
        container = ServiceContainer.build(self.config, self.db)
        scheduler = container.automation
        scheduler.stop(timeout=1.0)  # Stop background thread to test synchronous calls

        month = current_month()

        # Seed student and course
        sid = self.db.execute(
            "INSERT INTO students (student_name, contact, status, joining_date) "
            "VALUES ('Bikash KC', '9841000001', 'Active', '2026-01-01')"
        )
        cid = self.db.execute(
            "INSERT INTO courses (course_name, duration_months, category, billing_type, status) "
            "VALUES ('English Speaking', 3, 'Language', 'Monthly', 'Active')"
        )
        self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, monthly_fee, start_date, status) "
            "VALUES (?, ?, 3000, ?, 'Active')",
            (sid, cid, f"{month}/01"),
        )

        # Enable auto billing
        self.settings.set("auto_billing_enabled", "true")
        self.settings.set("auto_billing_last_run_month", "")

        # Run scheduler check
        result = scheduler.check_recurring_billing()
        self.assertIsNotNone(result)
        self.assertEqual(result.bills_created, 1)
        self.assertEqual(self.settings.get("auto_billing_last_run_month"), month)

        # Running again in the same month should do nothing (idempotent)
        result2 = scheduler.check_recurring_billing()
        self.assertIsNone(result2)

    def test_automated_daily_backup(self):
        """Scheduler creates daily backup snapshot."""
        container = ServiceContainer.build(self.config, self.db)
        scheduler = container.automation
        scheduler.stop(timeout=1.0)

        self.settings.set("auto_backup_daily_enabled", "true")
        self.settings.set("auto_backup_last_run_date", "")

        dest = scheduler.check_daily_backup(force=True)
        self.assertIsNotNone(dest)
        self.assertTrue(dest.exists())
        self.assertEqual(
            self.settings.get("auto_backup_last_run_date"),
            datetime.now().strftime("%Y-%m-%d"),
        )

    def test_automated_due_bill_reminders(self):
        """Scheduler sends reminders for bills due in 2 days or overdue."""
        container = ServiceContainer.build(self.config, self.db)
        scheduler = container.automation
        scheduler.stop(timeout=1.0)

        self.settings.set("sms_enabled", "true")
        self.settings.set("auto_reminders_enabled", "true")

        sid = self.db.execute(
            "INSERT INTO students (student_name, contact, status, joining_date) "
            "VALUES ('Sita Rai', '9841112233', 'Active', '2026-01-01')"
        )
        cid = self.db.execute(
            "INSERT INTO courses (course_name, category, billing_type, status) VALUES ('IELTS', 'Test Prep', 'Monthly', 'Active')"
        )
        eid = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, monthly_fee, start_date, status) "
            "VALUES (?, ?, 5000, '2026-01-01', 'Active')",
            (sid, cid),
        )

        today = datetime.now().date()
        due_t2 = (today + timedelta(days=2)).strftime("%Y-%m-%d")

        self.db.execute(
            "INSERT INTO due_bills (bill_number, enrollment_id, billing_period, issue_date, due_date, "
            "subtotal, discount, total_amount, paid_amount, status) "
            "VALUES ('BILL-REMIND-01', ?, '2026/09', '2026-09-01', ?, 5000, 0, 5000, 0, 'Unpaid')",
            (eid, due_t2),
        )

        with patch.object(container.notifications, "dispatch_async"):
            res = scheduler.check_bill_reminders(force=True)
            self.assertEqual(res["status"], "completed")
            self.assertEqual(res["queued"], 1)

            # Check that sms_delivery_log has the reminder
            log = self.db.query_one(
                "SELECT * FROM sms_delivery_log WHERE event_key='due_bill_reminder'"
            )
            self.assertIsNotNone(log)
            self.assertEqual(log["recipient"], "9841112233")


if __name__ == "__main__":
    unittest.main()
