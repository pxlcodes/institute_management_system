from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from elh.config import AppConfig
from elh.web.app import create_app
from tests.test_web_security import _run_asgi_request


class WebFullParityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp_dir.name)
        db_path = self.folder / "parity_test.db"
        self.config = replace(
            AppConfig(),
            database_engine="sqlite",
            database_path=db_path,
            backup_directory=self.folder / "backups",
            admin_username="testadmin",
            admin_password="Admin@TestPassword2025",
            operator_username="testop",
            operator_password="Operator@TestPassword2025",
            secret_key="unit-test-secret-key-full-parity",
        )
        self.app = create_app(self.config)

        # Log in as admin
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/auth/login",
                body={"username": "testadmin", "password": "Admin@TestPassword2025"},
            )
        )
        self.assertEqual(status, 200)
        self.token = json.loads(body.decode("utf-8"))["token"]
        self.headers = {"authorization": f"Bearer {self.token}"}

    def tearDown(self):
        import gc
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def test_ai_assistant_query(self):
        # Admin can access AI assistant
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/assistant/query",
                headers=self.headers,
                body={"prompt": "/help"},
            )
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("title", data)
        self.assertIn("content", data)
        self.assertIn("badge", data)

        # Operator (non-admin) cannot access AI assistant (HTTP 403 Forbidden by permission)
        op_status, _, op_body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/auth/login",
                body={"username": "testop", "password": "Operator@TestPassword2025"},
            )
        )
        self.assertEqual(op_status, 200)
        op_token = json.loads(op_body.decode("utf-8"))["token"]
        op_headers = {"authorization": f"Bearer {op_token}"}

        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/assistant/query",
                headers=op_headers,
                body={"prompt": "/help"},
            )
        )
        self.assertEqual(status, 403)

        # Even if a non-admin user is granted assistant.view permission, role guard strictly blocks
        c_status, _, c_body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/users",
                headers=self.headers,
                body={
                    "username": "test_op_with_perm",
                    "password": "Operator@TestPassword2025",
                    "display_name": "Test Op Perm",
                    "role": "operator",
                    "permissions": ["assistant.view"],
                },
            )
        )
        self.assertEqual(c_status, 201)

        v_status, _, v_body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/auth/login",
                body={"username": "test_op_with_perm", "password": "Operator@TestPassword2025"},
            )
        )
        self.assertEqual(v_status, 200)
        v_token = json.loads(v_body.decode("utf-8"))["token"]
        v_headers = {"authorization": f"Bearer {v_token}"}

        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/assistant/query",
                headers=v_headers,
                body={"prompt": "/help"},
            )
        )
        self.assertEqual(status, 403)
        err_data = json.loads(body.decode("utf-8"))
        self.assertIn("only accessible by admin and super admin", err_data.get("detail", ""))

    def test_grades_and_class_levels(self):
        # Create grade
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/grades",
                headers=self.headers,
                body={"short_name": "A+", "grade_name": "Distinction", "status": "Active", "remarks": "Outstanding"},
            )
        )
        self.assertEqual(status, 201)
        grade_id = json.loads(body.decode("utf-8"))["id"]

        # List grades
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/grades", headers=self.headers)
        )
        self.assertEqual(status, 200)
        grades = json.loads(body.decode("utf-8"))
        self.assertTrue(any(g["id"] == grade_id and g["short_name"] == "A+" for g in grades))

        # Update grade
        status, _, _ = asyncio.run(
            _run_asgi_request(
                self.app,
                "PUT",
                f"/api/grades/{grade_id}",
                headers=self.headers,
                body={"short_name": "A+", "grade_name": "Outstanding Distinction", "status": "Active", "remarks": "Updated"},
            )
        )
        self.assertEqual(status, 200)

        # Create class level
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/class-levels",
                headers=self.headers,
                body={"level_name": "Grade 11", "status": "Active", "remarks": "High School"},
            )
        )
        self.assertEqual(status, 201)
        level_id = json.loads(body.decode("utf-8"))["id"]

        # List class levels
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/class-levels", headers=self.headers)
        )
        self.assertEqual(status, 200)
        levels = json.loads(body.decode("utf-8"))
        self.assertTrue(any(l["id"] == level_id and l["level_name"] == "Grade 11" for l in levels))

    def test_student_transactions_and_accounts(self):
        # Create account
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/accounts",
                headers=self.headers,
                body={"account_name": "Cash Counter", "account_type": "Cash Counter", "opening_balance": 10000},
            )
        )
        self.assertEqual(status, 201)
        account_id = json.loads(body.decode("utf-8"))["id"]

        # Create student
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/students",
                headers=self.headers,
                body={"name": "Aarav Sharma", "joining_date": "2083/05/01", "contact": "9841234567"},
            )
        )
        self.assertEqual(status, 201)
        student_id = json.loads(body.decode("utf-8"))["id"]

        # Record student payment transaction
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/student-transactions",
                headers=self.headers,
                body={
                    "student_id": student_id,
                    "transaction_date": "2083/05/10",
                    "transaction_type": "Payment Received",
                    "particular": "Monthly tuition fee payment",
                    "payment_amount": 2500,
                    "account_id": account_id,
                    "payment_method": "Cash",
                    "receipt_no": "REC-001",
                },
            )
        )
        self.assertEqual(status, 201)
        trans_id = json.loads(body.decode("utf-8"))["id"]

        # List student transactions
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/student-transactions", headers=self.headers)
        )
        self.assertEqual(status, 200)
        transactions = json.loads(body.decode("utf-8"))
        self.assertTrue(any(t["id"] == trans_id and t["student_name"] == "Aarav Sharma" for t in transactions))

    def test_class_routines_and_pdf(self):
        # Create class level
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/class-levels",
                headers=self.headers,
                body={"level_name": "Grade 10", "status": "Active"},
            )
        )
        level_id = json.loads(body.decode("utf-8"))["id"]

        # Create routine plan
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/routines/plans",
                headers=self.headers,
                body={"plan_name": "Routine 2083 First Term", "effective_from": "2083/05/01"},
            )
        )
        self.assertEqual(status, 201)
        plan_id = json.loads(body.decode("utf-8"))["id"]

        # Create routine period
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/routines",
                headers=self.headers,
                body={
                    "class_name": "Grade 10",
                    "day_of_week": "Sunday",
                    "period_label": "Period 1",
                    "subject_name": "Mathematics",
                    "class_level_id": level_id,
                    "start_time": "07:00 AM",
                    "end_time": "07:45 AM",
                    "status": "Active",
                    "routine_plan_id": plan_id,
                },
            )
        )
        self.assertEqual(status, 201)
        routine_id = json.loads(body.decode("utf-8"))["id"]

        # List routines
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", f"/api/routines?routine_plan_id={plan_id}", headers=self.headers)
        )
        self.assertEqual(status, 200)
        routines = json.loads(body.decode("utf-8"))
        self.assertTrue(any(r["id"] == routine_id and r["subject_name"] == "Mathematics" for r in routines))

        # Download routine PDF
        status, headers, body = asyncio.run(
            _run_asgi_request(self.app, "GET", f"/api/routines/pdf?routine_plan_id={plan_id}", headers=self.headers)
        )
        self.assertEqual(status, 200)
        self.assertIn("application/pdf", headers.get("content-type", ""))
        self.assertTrue(body.startswith(b"%PDF"))

    def test_advances_and_salary_payout(self):
        # Create bank account with balance
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/accounts",
                headers=self.headers,
                body={"account_name": "Main Bank", "account_type": "Bank Account", "opening_balance": 50000},
            )
        )
        account_id = json.loads(body.decode("utf-8"))["id"]

        # Create staff member
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/staff",
                headers=self.headers,
                body={
                    "teacher_name": "Ramesh Adhikari",
                    "staff_type": "Teaching",
                    "joined_date": "2083/01/01",
                    "salary_type": "Monthly Salary",
                    "basic_salary": 25000,
                },
            )
        )
        self.assertEqual(status, 201)
        teacher_id = json.loads(body.decode("utf-8"))["id"]

        # Pay staff advance
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/advances",
                headers=self.headers,
                body={
                    "teacher_id": teacher_id,
                    "advance_date": "2083/05/02",
                    "amount": 5000,
                    "paid_from_account_id": account_id,
                    "payment_method": "Bank",
                    "reference_no": "ADV-001",
                },
            )
        )
        self.assertEqual(status, 201)
        advance_id = json.loads(body.decode("utf-8"))["id"]

        # List advances
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/advances", headers=self.headers)
        )
        self.assertEqual(status, 200)
        advances = json.loads(body.decode("utf-8"))
        self.assertTrue(any(a["id"] == advance_id and a["teacher_name"] == "Ramesh Adhikari" for a in advances))

        # Calculate salary data
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/salary/calculate",
                headers=self.headers,
                body={"teacher_id": teacher_id, "salary_month": "2083/05"},
            )
        )
        self.assertEqual(status, 200)
        calc_data = json.loads(body.decode("utf-8"))
        self.assertEqual(calc_data["outstanding_advance"], 5000.0)

        # Pay salary deducting advance
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/salary",
                headers=self.headers,
                body={
                    "teacher_id": teacher_id,
                    "salary_month": "2083/05",
                    "basic_salary": 25000,
                    "advance_deduction": 5000,
                    "payment_date": "2083/05/25",
                    "paid_from_account_id": account_id,
                    "payment_method": "Bank",
                    "voucher_no": "SAL-001",
                },
            )
        )
        self.assertEqual(status, 201)
        salary_id = json.loads(body.decode("utf-8"))["id"]

        # List salary payouts
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/salary", headers=self.headers)
        )
        self.assertEqual(status, 200)
        payouts = json.loads(body.decode("utf-8"))
        self.assertTrue(any(p["id"] == salary_id and float(p["net_salary"]) == 20000.0 for p in payouts))

        # Download payslip PDF
        status, headers, body = asyncio.run(
            _run_asgi_request(self.app, "GET", f"/api/salary/{salary_id}/payslip/pdf", headers=self.headers)
        )
        self.assertEqual(status, 200)
        self.assertIn("application/pdf", headers.get("content-type", ""))
        self.assertTrue(body.startswith(b"%PDF"))

    def test_certificates_lifecycle(self):
        # Create course
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/courses",
                headers=self.headers,
                body={
                    "course_name": "Full Stack Web Dev",
                    "category": "Computer",
                    "duration_months": 3,
                    "default_fee": 15000,
                },
            )
        )
        self.assertEqual(status, 201)
        course_id = json.loads(body.decode("utf-8"))["id"]

        # Create student
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/students",
                headers=self.headers,
                body={"name": "Sita Thapa", "contact": "9800000000", "joining_date": "2083/01/01"},
            )
        )
        self.assertEqual(status, 201)
        student_id = json.loads(body.decode("utf-8"))["id"]

        # Enroll student
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/enrollments",
                headers=self.headers,
                body={"student_id": student_id, "course_id": course_id, "start_date": "2083/01/01"},
            )
        )
        self.assertEqual(status, 201)
        enrollment_id = json.loads(body.decode("utf-8"))["id"]

        # Mark enrollment completed
        status, _, _ = asyncio.run(
            _run_asgi_request(
                self.app,
                "PUT",
                f"/api/enrollments/{enrollment_id}",
                headers=self.headers,
                body={"status": "Completed", "completion_date": "2083/04/01"},
            )
        )
        self.assertEqual(status, 200)

        # Check available enrollments
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/certificates/available-enrollments", headers=self.headers)
        )
        self.assertEqual(status, 200)
        avail = json.loads(body.decode("utf-8"))
        self.assertTrue(any(e["enrollment_id"] == enrollment_id for e in avail))

        # Check next certificate number
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/certificates/next-number", headers=self.headers)
        )
        self.assertEqual(status, 200)
        next_num = json.loads(body.decode("utf-8"))["certificate_number"]
        self.assertTrue(len(next_num) > 0)

        # Issue certificate
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/certificates",
                headers=self.headers,
                body={
                    "enrollment_id": enrollment_id,
                    "certificate_number": next_num,
                    "certify_date": "2083/04/05",
                    "instructor_name": "Senior Instructor",
                    "principal_name": "Institute Principal",
                    "remarks": "Excellence in Web Dev",
                },
            )
        )
        self.assertEqual(status, 201)
        cert_id = json.loads(body.decode("utf-8"))["id"]

        # Download certificate PDF
        status, headers, body = asyncio.run(
            _run_asgi_request(self.app, "GET", f"/api/certificates/{cert_id}/pdf", headers=self.headers)
        )
        self.assertEqual(status, 200)
        self.assertIn("application/pdf", headers.get("content-type", ""))
        self.assertTrue(body.startswith(b"%PDF"))

        # Regenerate PDF
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "POST", f"/api/certificates/{cert_id}/regenerate-pdf", headers=self.headers)
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body.decode("utf-8"))["ok"])

    def test_settings_health_and_backup(self):
        # Get settings
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/settings", headers=self.headers)
        )
        self.assertEqual(status, 200)
        settings = json.loads(body.decode("utf-8"))
        self.assertTrue(len(settings) > 0)

        # Update setting
        status, _, _ = asyncio.run(
            _run_asgi_request(
                self.app,
                "PUT",
                "/api/settings",
                headers=self.headers,
                body={"settings": {"currency_symbol": "NPR"}},
            )
        )
        self.assertEqual(status, 200)

        # System health
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/system/health", headers=self.headers)
        )
        self.assertEqual(status, 200)
        health = json.loads(body.decode("utf-8"))
        self.assertIn("status", health)
        self.assertIn("checks", health)

        # Database backup
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "POST", "/api/system/backup", headers=self.headers)
        )
        self.assertEqual(status, 200)
        backup_res = json.loads(body.decode("utf-8"))
        self.assertTrue(backup_res["ok"])
        self.assertIn("backup_path", backup_res)
