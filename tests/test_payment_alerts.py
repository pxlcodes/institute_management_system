from __future__ import annotations

import asyncio
import gc
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import nepali_datetime as nepali

from elh.config import AppConfig
from elh.infrastructure import create_database
from elh.web.app import create_app
from tests.test_web_security import _run_asgi_request


class PaymentAlertTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_payment_alerts.db"
        self.config = replace(
            AppConfig(),
            database_engine="sqlite",
            database_path=self.db_path,
            admin_username="testadmin",
            admin_password="Admin@TestPassword2025",
            operator_username="testop",
            operator_password="Operator@TestPassword2025",
            secret_key="unit-test-secret-key-payment-alerts",
            date_format="%Y/%m/%d",
        )
        self.db = create_database(self.config)
        self.db.initialize()
        from elh.services.container import ServiceContainer
        self.services = ServiceContainer.build(self.config, self.db)
        self.app = create_app(self.config)

        # Login as admin
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/auth/login",
                body={"username": "testadmin", "password": "Admin@TestPassword2025"},
            )
        )
        self.assertEqual(status, 200)
        self.admin_token = json.loads(body.decode("utf-8"))["token"]
        self.admin_headers = {"authorization": f"Bearer {self.admin_token}"}

        # Create basic test data: Course, Student, Enrollment
        today_bs = nepali.date.today()
        # Dates relative to today
        # Past due date (overdue)
        past_y = today_bs.year
        past_m = today_bs.month - 1 if today_bs.month > 1 else 12
        if today_bs.month == 1:
            past_y -= 1
        self.past_due_date = f"{past_y:04d}/{past_m:02d}/15"

        # Future due date
        fut_y = today_bs.year
        fut_m = today_bs.month + 1 if today_bs.month < 12 else 1
        if today_bs.month == 12:
            fut_y += 1
        self.future_due_date = f"{fut_y:04d}/{fut_m:02d}/15"

        # Far future resume date for suppression
        self.far_future_date = f"{today_bs.year + 2:04d}/01/01"
        self.past_expired_date = f"{today_bs.year - 2:04d}/01/01"

        course_id = self.db.execute(
            "INSERT INTO courses (course_name, category, billing_type, default_fee, duration_months, status) "
            "VALUES ('Maths 10', 'Tuition', 'Monthly', 1500, 12, 'Active')"
        )
        self.course_id = course_id

        student_id = self.db.execute(
            "INSERT INTO students (student_name, class_name, contact, status, joining_date) "
            "VALUES ('Rohan Shrestha', 'Grade 10', '9841234567', 'Active', '2080/01/01')"
        )
        self.student_id = student_id

        enrollment_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, level, start_date, monthly_fee, status) "
            "VALUES (?, ?, 'Grade 10', '2080/01/01', 1500, 'Active')",
            (student_id, course_id),
        )
        self.enrollment_id = enrollment_id

    def tearDown(self):
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def test_overdue_payment_alerts_detection(self):
        services = self.services

        # Bill 1: Overdue unpaid
        b1_id = self.db.execute(
            "INSERT INTO due_bills (bill_number, enrollment_id, billing_period, issue_date, due_date, "
            "subtotal, discount, total_amount, paid_amount, status) "
            "VALUES ('BILL-OVERDUE', ?, '2083/01', '2083/01/01', ?, 1500, 0, 1500, 0, 'Due')",
            (self.enrollment_id, self.past_due_date),
        )

        # Bill 2: Future due date (not overdue)
        self.db.execute(
            "INSERT INTO due_bills (bill_number, enrollment_id, billing_period, issue_date, due_date, "
            "subtotal, discount, total_amount, paid_amount, status) "
            "VALUES ('BILL-FUTURE', ?, '2083/02', '2083/02/01', ?, 1500, 0, 1500, 0, 'Due')",
            (self.enrollment_id, self.future_due_date),
        )

        # Bill 3: Past due date but already paid
        self.db.execute(
            "INSERT INTO due_bills (bill_number, enrollment_id, billing_period, issue_date, due_date, "
            "subtotal, discount, total_amount, paid_amount, status) "
            "VALUES ('BILL-PAID', ?, '2083/03', '2083/03/01', ?, 1500, 0, 1500, 1500, 'Paid')",
            (self.enrollment_id, self.past_due_date),
        )

        alerts = services.billing.payment_alerts(include_suppressed=False)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["bill_id"], b1_id)
        self.assertEqual(alerts[0]["bill_number"], "BILL-OVERDUE")
        self.assertEqual(alerts[0]["student_name"], "Rohan Shrestha")
        self.assertEqual(alerts[0]["balance"], 1500.0)
        self.assertGreater(alerts[0]["days_overdue"], 0)
        self.assertEqual(alerts[0]["review_status"], "Not reviewed")

    def test_payment_alert_review_and_suppression(self):
        services = self.services

        b_id = self.db.execute(
            "INSERT INTO due_bills (bill_number, enrollment_id, billing_period, issue_date, due_date, "
            "subtotal, discount, total_amount, paid_amount, status) "
            "VALUES ('BILL-SUPP', ?, '2083/01', '2083/01/01', ?, 2000, 0, 2000, 500, 'Partial')",
            (self.enrollment_id, self.past_due_date),
        )

        # Initially active alert
        alerts = services.billing.payment_alerts(include_suppressed=False)
        self.assertEqual(len(alerts), 1)
        self.assertFalse(alerts[0]["suppressed"])

        # Suppress with future follow-up date
        services.billing.record_payment_alert_review(
            bill_id=b_id,
            status="Suppressed",
            note="Parent requested extension until next month",
            follow_up_date=self.far_future_date,
            user_id=1,
        )

        # Without suppressed: 0 alerts
        alerts_active = services.billing.payment_alerts(include_suppressed=False)
        self.assertEqual(len(alerts_active), 0)

        # With suppressed: 1 alert, marked suppressed
        alerts_all = services.billing.payment_alerts(include_suppressed=True)
        self.assertEqual(len(alerts_all), 1)
        self.assertTrue(alerts_all[0]["suppressed"])
        self.assertEqual(alerts_all[0]["review_status"], "Suppressed")
        self.assertEqual(alerts_all[0]["follow_up_date"], self.far_future_date)
        self.assertEqual(alerts_all[0]["review_note"], "Parent requested extension until next month")

        # Test expired suppression: record review with past follow_up_date
        services.billing.record_payment_alert_review(
            bill_id=b_id,
            status="Suppressed",
            note="Old suppression",
            follow_up_date=self.past_expired_date,
            user_id=1,
        )
        alerts_resurfaced = services.billing.payment_alerts(include_suppressed=False)
        self.assertEqual(len(alerts_resurfaced), 1)
        self.assertFalse(alerts_resurfaced[0]["suppressed"])
        self.assertEqual(alerts_resurfaced[0]["review_status"], "Suppression expired")

    def test_payment_alert_review_validation(self):
        services = self.services

        # Invalid status
        with self.assertRaises(ValueError):
            services.billing.record_payment_alert_review(
                bill_id=1,
                status="InvalidStatus",
                note="bad",
                follow_up_date="",
                user_id=1,
            )

        # Non-existent bill
        with self.assertRaises(ValueError):
            services.billing.record_payment_alert_review(
                bill_id=99999,
                status="Promise to Pay",
                note="bad",
                follow_up_date="",
                user_id=1,
            )

    def test_web_api_dashboard_and_billing_alerts(self):
        # Create an overdue bill
        b_id = self.db.execute(
            "INSERT INTO due_bills (bill_number, enrollment_id, billing_period, issue_date, due_date, "
            "subtotal, discount, total_amount, paid_amount, status) "
            "VALUES ('BILL-API-1', ?, '2083/01', '2083/01/01', ?, 3000, 0, 3000, 0, 'Due')",
            (self.enrollment_id, self.past_due_date),
        )

        # GET /api/dashboard contains payment_alerts
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/dashboard", headers=self.admin_headers)
        )
        self.assertEqual(status, 200)
        dash_data = json.loads(body.decode("utf-8"))
        self.assertIn("payment_alerts", dash_data)
        self.assertEqual(len(dash_data["payment_alerts"]), 1)
        self.assertEqual(dash_data["metrics"]["overdue_bills_count"], 1)
        self.assertEqual(dash_data["metrics"]["overdue_amount"], 3000.0)

        # GET /api/billing/alerts
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/billing/alerts", headers=self.admin_headers)
        )
        self.assertEqual(status, 200)
        alerts_data = json.loads(body.decode("utf-8"))
        self.assertEqual(len(alerts_data), 1)

        # POST /api/billing/alerts/{bill_id}/review to suppress
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                f"/api/billing/alerts/{b_id}/review",
                headers=self.admin_headers,
                body={
                    "status": "Suppressed",
                    "note": "Spoke with father; promised payment by next month",
                    "follow_up_date": self.far_future_date,
                },
            )
        )
        self.assertEqual(status, 200)
        res = json.loads(body.decode("utf-8"))
        self.assertTrue(res.get("ok"))

        # GET /api/billing/alerts without include_suppressed is now empty
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/billing/alerts", headers=self.admin_headers)
        )
        self.assertEqual(status, 200)
        alerts_active = json.loads(body.decode("utf-8"))
        self.assertEqual(len(alerts_active), 0)

        # GET /api/billing/alerts?include_suppressed=true has the suppressed alert
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/billing/alerts?include_suppressed=true", headers=self.admin_headers)
        )
        self.assertEqual(status, 200)
        alerts_all = json.loads(body.decode("utf-8"))
        self.assertEqual(len(alerts_all), 1)
        self.assertTrue(alerts_all[0]["suppressed"])
        self.assertEqual(alerts_all[0]["review_status"], "Suppressed")

    def test_student_dashboard_overdue_alerts(self):
        # Create student user
        asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/users",
                headers=self.admin_headers,
                body={
                    "username": "rohan_student",
                    "password": "Student@Password2025",
                    "display_name": "Rohan Shrestha",
                    "role": "student",
                    "student_id": self.student_id,
                },
            )
        )

        # Login as student
        l_status, _, l_body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/auth/login",
                body={"username": "rohan_student", "password": "Student@Password2025"},
            )
        )
        self.assertEqual(l_status, 200)
        st_token = json.loads(l_body.decode("utf-8"))["token"]
        st_headers = {"authorization": f"Bearer {st_token}"}

        # Create overdue bill
        self.db.execute(
            "INSERT INTO due_bills (bill_number, enrollment_id, billing_period, issue_date, due_date, "
            "subtotal, discount, total_amount, paid_amount, status) "
            "VALUES ('BILL-ST-1', ?, '2083/01', '2083/01/01', ?, 1200, 0, 1200, 0, 'Due')",
            (self.enrollment_id, self.past_due_date),
        )

        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/dashboard", headers=st_headers)
        )
        self.assertEqual(status, 200)
        dash_data = json.loads(body.decode("utf-8"))
        self.assertEqual(dash_data["role"], "student")
        self.assertIn("overdue_alerts", dash_data)
        self.assertEqual(len(dash_data["overdue_alerts"]), 1)
        self.assertEqual(dash_data["overdue_alerts"][0]["bill_number"], "BILL-ST-1")
        self.assertEqual(dash_data["metrics"]["overdue_bills_count"], 1)

