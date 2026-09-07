from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from elh.config import AppConfig
from elh.core.settings import SettingsService
from elh.core.validation import current_month, today_iso
from elh.infrastructure.sqlite_database import SQLiteDatabase
from elh.repositories import BillingRepository
from elh.services.assistant import InstituteAssistant
from elh.services.billing import BillingService
from elh.services.container import ServiceContainer
from elh.services.printing import PrintingService
from elh.services.recurring_billing import RecurringBillingService
from elh.web.app import create_app


async def _run_asgi_request(
    app,
    method: str,
    path: str,
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    client: tuple[str, int] = ("127.0.0.1", 50000),
) -> tuple[int, dict[str, str], bytes]:
    """Lightweight ASGI test helper without external dependencies."""
    req_headers = []
    if headers:
        for k, v in headers.items():
            req_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))

    req_body = json.dumps(body).encode("utf-8") if body is not None else b""
    if body is not None and not any(k.lower() == "content-type" for k, _ in (headers or {}).items()):
        req_headers.append((b"content-type", b"application/json"))

    query_string = b""
    raw_path = path
    if "?" in path:
        raw_path, qs = path.split("?", 1)
        query_string = qs.encode("latin-1")

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": raw_path,
        "raw_path": raw_path.encode("ascii"),
        "query_string": query_string,
        "headers": req_headers,
        "client": client,
        "server": ("testserver", 80),
    }

    res_status = 200
    res_headers: dict[str, str] = {}
    res_body = bytearray()

    async def receive():
        return {"type": "http.request", "body": req_body, "more_body": False}

    async def send(message):
        nonlocal res_status
        if message["type"] == "http.response.start":
            res_status = message["status"]
            for raw_k, raw_v in message.get("headers", []):
                k = raw_k.decode("latin-1").lower()
                v = raw_v.decode("latin-1")
                res_headers[k] = v
        elif message["type"] == "http.response.body":
            res_body.extend(message.get("body", b""))

    await app(scope, receive, send)
    return res_status, res_headers, bytes(res_body)


class DummyPrinter:
    def print_receipt(self, receipt):
        pass


class RecurringBillingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_elh.db"
        self.db = SQLiteDatabase(self.db_path, False)
        self.config = AppConfig(
            database_path=self.db_path,
            database_engine="sqlite",
            app_title="ELH Test Hub",
            currency_symbol="Rs.",
        )
        self.settings = SettingsService(self.db)
        self.settings.ensure_defaults()
        self.printing = PrintingService(DummyPrinter())
        self.billing_repo = BillingRepository(self.db)
        self.billing_service = BillingService(
            self.billing_repo, self.printing, "ELH Test Hub", "Rs."
        )
        self.recurring_service = RecurringBillingService(
            self.db, self.billing_service, self.settings
        )

        # Populate basic seed data
        self.school_id = self.db.execute(
            "INSERT INTO schools (school_name, status) VALUES ('Test School', 'Active')"
        )
        self.course_id = self.db.execute(
            "INSERT INTO courses (course_name, category, billing_type, default_fee, duration_months, status) "
            "VALUES ('English Spoken', 'Language', 'Monthly', 3500.00, 3, 'Active')"
        )
        self.course_id2 = self.db.execute(
            "INSERT INTO courses (course_name, category, billing_type, default_fee, duration_months, status) "
            "VALUES ('IELTS Prep', 'Test Prep', 'Monthly', 5000.00, 2, 'Active')"
        )

        # Student 1: Active, starts 2083/01
        self.s1_id = self.db.execute(
            "INSERT INTO students (student_name, class_name, contact, joining_date, status) "
            "VALUES ('Aarav Sharma', 'Class 10', '9841000001', '2083/01/01', 'Active')"
        )
        self.e1_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, level, start_date, monthly_fee, admission_fee, discount, status) "
            "VALUES (?, ?, 'Beginner', '2083/01/01', 3500.00, 500.00, 0.00, 'Active')",
            (self.s1_id, self.course_id),
        )

        # Student 2: Active, starts 2083/02
        self.s2_id = self.db.execute(
            "INSERT INTO students (student_name, class_name, contact, joining_date, status) "
            "VALUES ('Bikash KC', 'Class 12', '9841000002', '2083/02/01', 'Active')"
        )
        self.e2_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, level, start_date, monthly_fee, admission_fee, discount, status) "
            "VALUES (?, ?, 'Intermediate', '2083/02/01', 5000.00, 0.00, 500.00, 'Active')",
            (self.s2_id, self.course_id2),
        )

        # Student 3: Inactive enrollment
        self.s3_id = self.db.execute(
            "INSERT INTO students (student_name, class_name, contact, joining_date, status) "
            "VALUES ('Chetan Gurung', 'Class 11', '9841000003', '2083/01/01', 'Active')"
        )
        self.e3_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, level, start_date, monthly_fee, status) "
            "VALUES (?, ?, 'Beginner', '2083/01/01', 3500.00, 'Inactive')",
            (self.s3_id, self.course_id),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_unbilled_enrollment_discovery_and_preview(self):
        # Target month 2083/03: both e1 and e2 should be unbilled
        unbilled = self.recurring_service.get_unbilled_enrollments("2083/03")
        self.assertEqual(len(unbilled), 2)
        eids = {u.enrollment_id for u in unbilled}
        self.assertEqual(eids, {self.e1_id, self.e2_id})

        # Check preview
        prev = self.recurring_service.preview("2083/03")
        self.assertEqual(prev["target_month"], "2083/03")
        self.assertEqual(prev["unbilled_count"], 2)
        # e1 has monthly_fee 3500 + 500 admission (first bill) = 4000
        # e2 has monthly_fee 5000 - 500 discount (first bill) = 4500
        self.assertEqual(prev["total_estimated_amount"], 8500.0)

    def test_run_auto_billing_generates_due_bills_and_updates_settings(self):
        target = "2083/03"
        result = self.recurring_service.run_auto_billing(
            target_month=target,
            issue_date="2083/03/01",
            due_date="2083/03/08",
            remarks="Monthly recurring tuition",
            actor_username="test_admin",
        )

        self.assertEqual(result.target_month, target)
        self.assertEqual(result.bills_created, 2)
        self.assertEqual(result.bills_skipped, 0)
        self.assertEqual(result.total_invoiced_amount, Decimal("8500.00"))
        self.assertEqual(len(result.bills), 2)

        # Verify bills in database
        bills = self.billing_repo.list()
        self.assertEqual(len(bills), 2)

        # Verify settings updated
        self.assertEqual(self.settings.get("auto_billing_last_run_month"), target)
        self.assertTrue(self.settings.get("auto_billing_last_run_at"))

        # Verify audit log
        audit_rows = self.db.query("SELECT * FROM auth_audit_log WHERE event_type='auto_billing'")
        self.assertEqual(len(audit_rows), 1)
        self.assertEqual(audit_rows[0]["username"], "test_admin")

        # Second run for same month should skip already billed students (idempotent)
        second_run = self.recurring_service.run_auto_billing(target_month=target)
        self.assertEqual(second_run.bills_created, 0)
        self.assertEqual(second_run.total_invoiced_amount, Decimal("0"))

    def test_scheduled_auto_billing_trigger(self):
        # Disabled by default
        self.assertFalse(self.settings.get_bool("auto_billing_enabled"))
        res = self.recurring_service.check_and_run_scheduled()
        self.assertIsNone(res)

        # Enable auto billing
        self.recurring_service.update_config(enabled=True, due_days=10, auto_sms=True)
        self.assertTrue(self.settings.get_bool("auto_billing_enabled"))
        self.assertEqual(self.settings.get_int("auto_billing_due_days", 0), 10)

        # Run scheduled for current month
        res2 = self.recurring_service.check_and_run_scheduled()
        self.assertIsNotNone(res2)
        self.assertEqual(res2.target_month, current_month())
        self.assertEqual(self.settings.get("auto_billing_last_run_month"), current_month())

        # Running again right after should do nothing
        res3 = self.recurring_service.check_and_run_scheduled()
        self.assertIsNone(res3)

    def test_assistant_autobill_command_and_nlp(self):
        container = ServiceContainer.build(self.config, self.db)
        assistant = InstituteAssistant(container, self.db)

        # Status query
        resp = assistant.execute("/autobill")
        self.assertEqual(resp.badge, "AUTOBILL")
        self.assertIn("Automated Monthly Recurring Invoicing", resp.content)

        # Natural language trigger
        resp_nlp = assistant.execute("check unbilled students for this month")
        self.assertEqual(resp_nlp.badge, "AUTOBILL")

        # Execution trigger via assistant
        resp_run = assistant.execute("/autobill run")
        self.assertEqual(resp_run.badge, "COMPLETED")
        self.assertIn("Automated Recurring Billing Executed", resp_run.content)

    def test_web_api_auto_billing_endpoints(self):
        app = create_app(self.config)

        async def scenario():
            # Authenticate as operator or admin
            status, _, body = await _run_asgi_request(
                app,
                "POST",
                "/api/auth/login",
                body={"username": self.config.operator_username, "password": self.config.operator_password},
            )
            self.assertEqual(status, 200)
            token = json.loads(body)["token"]
            headers = {"authorization": f"Bearer {token}"}

            # 1. Preview endpoint
            status, _, body = await _run_asgi_request(
                app,
                "GET",
                "/api/bills/auto-billing/preview?month=2083/04",
                headers=headers,
            )
            self.assertEqual(status, 200)
            pdata = json.loads(body)
            self.assertEqual(pdata["target_month"], "2083/04")
            self.assertEqual(pdata["unbilled_count"], 2)

            # 2. Config endpoint
            status, _, body = await _run_asgi_request(
                app,
                "POST",
                "/api/bills/auto-billing/config",
                headers=headers,
                body={"enabled": True, "due_days": 14, "auto_sms": True},
            )
            self.assertEqual(status, 200)
            cdata = json.loads(body)
            self.assertTrue(cdata["enabled"])
            self.assertEqual(cdata["due_days"], 14)

            # 3. Run endpoint
            status, _, body = await _run_asgi_request(
                app,
                "POST",
                "/api/bills/auto-billing/run",
                headers=headers,
                body={"target_month": "2083/04", "remarks": "Web test auto invoicing"},
            )
            self.assertEqual(status, 200)
            rdata = json.loads(body)
            self.assertEqual(rdata["target_month"], "2083/04")
            self.assertEqual(rdata["bills_created"], 2)
            self.assertEqual(rdata["bills_skipped"], 0)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
