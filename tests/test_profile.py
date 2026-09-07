from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from elh.config import AppConfig
from elh.infrastructure.sqlite_database import SQLiteDatabase
from elh.models import Student
from elh.repositories import StudentRepository
from elh.services.people import StudentService
from elh.services.reports import ReportsService
from elh.ui.desktop.pages.student_profile import StudentProfileDialog
from elh.web.app import create_app
from tests.test_web_security import _run_asgi_request


class StudentProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_elh.db"
        self.reports_dir = Path(self.temp_dir.name) / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.db = SQLiteDatabase(self.db_path, False)
        self.config = AppConfig(
            database_path=self.db_path,
            backup_directory=Path(self.temp_dir.name) / "backups",
            secret_key="test-secret-key-profile",
        )
        self.student_service = StudentService(StudentRepository(self.db))
        self.reports_service = ReportsService(self.db, self.config.app_title, self.config.currency_symbol)

        # Setup test master data
        self.school_id = self.db.execute(
            "INSERT INTO schools (school_name, address, contact) VALUES (?, ?, ?)",
            ("Everest Model School", "Kathmandu", "9800000001"),
        )
        self.class_level_id = self.db.execute(
            "INSERT INTO class_levels (level_name) VALUES (?)",
            ("Grade 10",),
        )
        self.course_id = self.db.execute(
            "INSERT INTO courses (course_name, category, billing_type, default_fee, duration_months, instructor_name, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("Advanced Mathematics", "Science & Math", "Monthly", "2500.00", 6, "Prof. Sharma", "Active"),
        )

        # Generate a dummy test image
        img = Image.new("RGB", (120, 150), color=(50, 120, 200))
        buf = BytesIO()
        img.save(buf, format="JPEG")
        self.test_photo_bytes = buf.getvalue()

        # Register a test student with photo
        self.student = Student(
            id=None,
            name="Aarav Sharma",
            class_name="Grade 10",
            school_id=self.school_id,
            contact="9841234567",
            gender="Male",
            date_of_birth="2065/04/15",
            parent_name="Ram Sharma",
            guardian_relationship="Son of Mr.",
            joining_date="2081/01/01",
            photo_data=self.test_photo_bytes,
            photo_mime_type="image/jpeg",
            address="Kathmandu Ward 4",
            status="Active",
            remarks="Excellent academic performance.",
        )
        self.student_id = self.student_service.register(self.student)
        self.db.execute(
            "UPDATE students SET class_level_id = ? WHERE id = ?",
            (self.class_level_id, self.student_id),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_profile_aggregates_complete_student_dossier(self):
        # 1. Enrollments: 1 Active, 1 Completed
        e_active_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, level, start_date, monthly_fee, admission_fee, discount, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (self.student_id, self.course_id, "Grade 10", "2081/01/01", "2500.00", "1000.00", "200.00", "Active"),
        )
        e_past_id = self.db.execute(
            "INSERT INTO enrollments (student_id, course_id, level, start_date, end_date, monthly_fee, admission_fee, discount, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (self.student_id, self.course_id, "Grade 9", "2080/01/01", "2080/12/30", "2200.00", "0.00", "0.00", "Completed"),
        )

        # 2. Due Bills: 1 Partially Paid, 1 Unpaid
        self.db.execute(
            "INSERT INTO due_bills (enrollment_id, bill_number, billing_period, issue_date, due_date, subtotal, discount, total_amount, paid_amount, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (e_active_id, "BILL-2081-001", "2081/01", "2081/01/05", "2081/01/15", "2500.00", "200.00", "2300.00", "1000.00", "Partial"),
        )
        self.db.execute(
            "INSERT INTO due_bills (enrollment_id, bill_number, billing_period, issue_date, due_date, subtotal, discount, total_amount, paid_amount, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (e_active_id, "BILL-2081-002", "2081/02", "2081/02/05", "2081/02/15", "2500.00", "0.00", "2500.00", "0.00", "Unpaid"),
        )

        # 3. Student Transaction Receipt
        self.db.execute(
            "INSERT INTO student_transactions (student_id, transaction_type, transaction_date, receipt_no, particular, payment_amount, discount_amount, payment_method, remarks) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (self.student_id, "PAYMENT", "2081/01/10", "REC-101", "Tuition Fee Baisakh", "1000.00", "0.00", "Cash", "Advance token payment"),
        )

        # 4. Attendance Log for Current Month
        now = datetime.now()
        dt1 = now.replace(hour=9, minute=5, second=0).strftime("%Y-%m-%d %H:%M:%S")
        dt2 = now.replace(hour=16, minute=30, second=0).strftime("%Y-%m-%d %H:%M:%S")
        self.db.execute(
            "INSERT INTO attendance_logs (device_user_id, person_type, person_id, occurred_at, event_type) "
            "VALUES (?, ?, ?, ?, ?)",
            ("101", "student", self.student_id, dt1, "check_in"),
        )
        self.db.execute(
            "INSERT INTO attendance_logs (device_user_id, person_type, person_id, occurred_at, event_type) "
            "VALUES (?, ?, ?, ?, ?)",
            ("101", "student", self.student_id, dt2, "check_out"),
        )

        # 5. Certificate
        self.db.execute(
            "INSERT INTO course_certificates ("
            "certificate_number, enrollment_id, honorific, guardian_relationship, "
            "date_of_birth, student_name_snapshot, guardian_name_snapshot, "
            "course_name_snapshot, company_name_snapshot, course_start_date, "
            "course_end_date, duration_days, certify_date, instructor_name, principal_name, pdf_path"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "CERT-2080-001", e_past_id, "Mr.", "Son of Mr.",
                "2065/04/15", "Aarav Sharma", "Ram Sharma",
                "Advanced Mathematics Foundation", "Expert Learning Hub", "2080/01/01",
                "2080/12/30", 365, "2080/12/30", "Prof. Sharma", "Principal", "/tmp/cert.pdf",
            ),
        )

        # 6. SMS Log
        self.db.execute(
            "INSERT INTO sms_delivery_log (event_key, entity_type, entity_id, recipient, message_text, provider, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("fee_due", "student", self.student_id, "9841234567", "Dear Parent, Aarav Sharma has pending fee.", "sparrow", "DELIVERED", "2081-01-06 10:00:00"),
        )

        # Fetch profile
        profile = self.student_service.get_profile(self.student_id)

        # Assert Student Identity & Bio
        stu = profile["student"]
        self.assertEqual(stu["student_name"], "Aarav Sharma")
        self.assertEqual(stu["school_name"], "Everest Model School")
        self.assertEqual(stu["class_level_name"], "Grade 10")
        self.assertEqual(stu["contact"], "9841234567")
        self.assertIsNotNone(stu["photo_data"])

        # Assert Enrollments
        self.assertEqual(len(profile["active_enrollments"]), 1)
        self.assertEqual(profile["active_enrollments"][0]["course_name"], "Advanced Mathematics")
        self.assertEqual(len(profile["previous_enrollments"]), 1)
        self.assertEqual(profile["previous_enrollments"][0]["status"], "Completed")

        # Assert Financials
        fin = profile["financials"]
        self.assertEqual(fin["total_billed"], 4800.0)  # 2300 + 2500
        self.assertEqual(fin["total_paid"], 1000.0)
        self.assertEqual(fin["total_due"], 3800.0)     # 4800 - 1000
        self.assertEqual(len(fin["due_bills"]), 2)
        self.assertEqual(len(fin["transactions"]), 1)
        self.assertEqual(fin["transactions"][0]["receipt_no"], "REC-101")

        # Assert Attendance
        att = profile["attendance"]
        self.assertEqual(att["days_present_month"], 1)
        self.assertEqual(att["total_punches_month"], 2)
        self.assertEqual(len(att["recent_punches"]), 1)
        self.assertEqual(att["recent_punches"][0]["punch_count"], 2)

        # Assert Certificates & SMS
        self.assertEqual(len(profile["certificates"]), 1)
        self.assertEqual(profile["certificates"][0]["certificate_number"], "CERT-2080-001")
        self.assertEqual(len(profile["recent_sms"]), 1)
        self.assertEqual(profile["recent_sms"][0]["recipient"], "9841234567")

    def test_student_profile_pdf_generation_with_photo(self):
        # Generate PDF for student with photo
        out_path = self.reports_dir / f"profile_{self.student_id}.pdf"
        result_path = self.reports_service.student_profile_pdf(self.student_id, output=out_path)

        self.assertTrue(result_path.exists())
        self.assertGreater(result_path.stat().st_size, 2000)

        with open(result_path, "rb") as f:
            header = f.read(5)
        self.assertEqual(header, b"%PDF-")

    def test_student_profile_pdf_generation_without_photo(self):
        # Register student without photo
        stu2 = Student(
            id=None,
            name="Pooja Karki",
            class_name="Grade 10",
            school_id=self.school_id,
            contact="9841112233",
            gender="Female",
            joining_date="2081/02/01",
            photo_data=None,
            status="Active",
        )
        stu2_id = self.student_service.register(stu2)

        out_path = self.reports_dir / f"profile_{stu2_id}.pdf"
        result_path = self.reports_service.student_profile_pdf(stu2_id, output=out_path)

        self.assertTrue(result_path.exists())
        self.assertGreater(result_path.stat().st_size, 2000)

        with open(result_path, "rb") as f:
            header = f.read(5)
        self.assertEqual(header, b"%PDF-")

    def test_desktop_profile_dialog_module_structure(self):
        # Verify dialog class has required methods and attributes
        self.assertTrue(hasattr(StudentProfileDialog, "load_data"))
        self.assertTrue(hasattr(StudentProfileDialog, "reload"))
        self.assertTrue(hasattr(StudentProfileDialog, "export_pdf"))
        self.assertTrue(hasattr(StudentProfileDialog, "_build_ui"))

    def test_web_student_profile_endpoints(self):
        app = create_app(self.config)

        # 1. Login as admin to get session token
        status_code, _, body = asyncio.run(
            _run_asgi_request(
                app,
                "POST",
                "/api/auth/login",
                body={"username": "admin", "password": "Admin@2025"},
            )
        )
        self.assertEqual(status_code, 200)
        import json
        login_data = json.loads(body.decode("utf-8"))
        token = login_data["token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 2. Test GET /api/students/{id}/profile
        status_code, _, body = asyncio.run(
            _run_asgi_request(
                app,
                "GET",
                f"/api/students/{self.student_id}/profile",
                headers=auth_headers,
            )
        )
        self.assertEqual(status_code, 200)
        profile_json = json.loads(body.decode("utf-8"))
        self.assertEqual(profile_json["student"]["student_name"], "Aarav Sharma")
        self.assertTrue(profile_json["student"]["has_photo"])
        self.assertNotIn("photo_data", profile_json["student"])

        # 3. Test GET /api/students/{id}/photo
        status_code, headers, body = asyncio.run(
            _run_asgi_request(
                app,
                "GET",
                f"/api/students/{self.student_id}/photo",
                headers=auth_headers,
            )
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(headers.get("content-type"), "image/jpeg")
        self.assertEqual(body, self.test_photo_bytes)

        # 4. Test GET /api/students/{id}/profile/pdf
        status_code, headers, body = asyncio.run(
            _run_asgi_request(
                app,
                "GET",
                f"/api/students/{self.student_id}/profile/pdf",
                headers=auth_headers,
            )
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(headers.get("content-type"), "application/pdf")
        self.assertTrue(body.startswith(b"%PDF-"))

        # 5. Test query param token for photo and pdf downloads
        status_code, headers, body = asyncio.run(
            _run_asgi_request(
                app,
                "GET",
                f"/api/students/{self.student_id}/photo?token={token}",
            )
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(body, self.test_photo_bytes)

        # 6. Verify web assets serve student profile view code and styles
        status_code, _, body = asyncio.run(_run_asgi_request(app, "GET", "/assets/app.js"))
        self.assertEqual(status_code, 200)
        js_text = body.decode("utf-8")
        self.assertIn("student_profile", js_text)
        self.assertIn("viewStudentProfile", js_text)
        self.assertIn("downloadStudentProfilePdf", js_text)

        status_code, _, body = asyncio.run(_run_asgi_request(app, "GET", "/assets/styles.css"))
        self.assertEqual(status_code, 200)
        css_text = body.decode("utf-8")
        self.assertIn(".profile-hero", css_text)
        self.assertIn(".profile-photo", css_text)
