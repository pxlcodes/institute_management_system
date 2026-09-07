from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from elh.config import AppConfig
from elh.infrastructure import create_database
from elh.web.app import create_app
from tests.test_web_security import _run_asgi_request


class StudentPortalTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_student_portal.db"
        self.config = replace(
            AppConfig(),
            database_engine="sqlite",
            database_path=self.db_path,
            admin_username="testadmin",
            admin_password="Admin@TestPassword2025",
            secret_key="unit-test-secret-key-student-portal",
            date_format="%Y/%m/%d",
        )
        self.db = create_database(self.config)
        self.db.initialize()
        self.app = create_app(self.config)

        # Login as admin to set up test fixtures
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

        # Create two students: Student A and Student B
        st_a = json.loads(
            asyncio.run(
                _run_asgi_request(
                    self.app,
                    "POST",
                    "/api/students",
                    headers=self.admin_headers,
                    body={"name": "Aarav Sharma", "class_name": "Grade 10", "joining_date": "2083/05/01", "contact": "9841000001"},
                )
            )[2].decode("utf-8")
        )
        self.student_a_id = st_a["id"]

        st_b = json.loads(
            asyncio.run(
                _run_asgi_request(
                    self.app,
                    "POST",
                    "/api/students",
                    headers=self.admin_headers,
                    body={"name": "Bibek Karki", "class_name": "Grade 10", "joining_date": "2083/05/01", "contact": "9841000002"},
                )
            )[2].decode("utf-8")
        )
        self.student_b_id = st_b["id"]

        # Create course & enrollment for Student A
        course_res = json.loads(
            asyncio.run(
                _run_asgi_request(
                    self.app,
                    "POST",
                    "/api/courses",
                    headers=self.admin_headers,
                    body={"course_name": "Science & Tech", "category": "General", "default_fee": 3000, "duration_months": 3},
                )
            )[2].decode("utf-8")
        )
        self.course_id = course_res["id"]

        enr_a = json.loads(
            asyncio.run(
                _run_asgi_request(
                    self.app,
                    "POST",
                    "/api/enrollments",
                    headers=self.admin_headers,
                    body={"student_id": self.student_a_id, "course_id": self.course_id, "start_date": "2083/05/01", "monthly_fee": 3000},
                )
            )[2].decode("utf-8")
        )
        self.enrollment_a_id = enr_a["id"]

        # Generate bill for Student A
        asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/bills/generate",
                headers=self.admin_headers,
                body={
                    "enrollment_ids": [self.enrollment_a_id],
                    "start_month": "2083/05",
                    "end_month": "2083/05",
                    "issue_date": "2083/05/01",
                    "due_date": "2083/05/15",
                },
            )
        )

        # Create student user account for Student A
        asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/users",
                headers=self.admin_headers,
                body={
                    "username": "aarav",
                    "password": "Student@Password2025",
                    "display_name": "Aarav Sharma",
                    "role": "student",
                    "student_id": self.student_a_id,
                },
            )
        )

        # Create student user account for Student B
        asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/users",
                headers=self.admin_headers,
                body={
                    "username": "bibek",
                    "password": "Student@Password2025",
                    "display_name": "Bibek Karki",
                    "role": "student",
                    "student_id": self.student_b_id,
                },
            )
        )

        # Login as Student A
        l_status, _, l_body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/auth/login",
                body={"username": "aarav", "password": "Student@Password2025"},
            )
        )
        self.assertEqual(l_status, 200)
        self.student_a_token = json.loads(l_body.decode("utf-8"))["token"]
        self.student_a_headers = {"authorization": f"Bearer {self.student_a_token}"}

        # Login as Student B
        l_status_b, _, l_body_b = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/auth/login",
                body={"username": "bibek", "password": "Student@Password2025"},
            )
        )
        self.assertEqual(l_status_b, 200)
        self.student_b_token = json.loads(l_body_b.decode("utf-8"))["token"]
        self.student_b_headers = {"authorization": f"Bearer {self.student_b_token}"}

    def tearDown(self):
        import gc
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def test_student_dashboard_success(self):
        """Student dashboard must load cleanly without SQL errors and contain student data."""
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/dashboard", headers=self.student_a_headers)
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data["role"], "student")
        self.assertEqual(data["student"]["id"], self.student_a_id)
        self.assertEqual(data["student"]["student_name"], "Aarav Sharma")
        self.assertEqual(data["metrics"]["enrollments"], 1)
        self.assertEqual(data["metrics"]["outstanding"], 3000.0)
        self.assertEqual(len(data["due_bills"]), 1)
        self.assertIn("today_weekday", data)

    def test_student_bills_isolation(self):
        """Student A must only see their own bills, Student B must see none."""
        # Student A sees 1 bill
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/bills", headers=self.student_a_headers)
        )
        self.assertEqual(status, 200)
        bills_a = json.loads(body.decode("utf-8"))
        self.assertEqual(len(bills_a), 1)
        self.assertEqual(bills_a[0]["student_name"], "Aarav Sharma")
        bill_a_id = bills_a[0]["id"]

        # Student B sees 0 bills
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/bills", headers=self.student_b_headers)
        )
        self.assertEqual(status, 200)
        bills_b = json.loads(body.decode("utf-8"))
        self.assertEqual(len(bills_b), 0)

        # Student A can get payment QR for their own bill
        qr_status, _, qr_body = asyncio.run(
            _run_asgi_request(self.app, "GET", f"/api/bills/{bill_a_id}/qr", headers=self.student_a_headers)
        )
        self.assertEqual(qr_status, 200)
        qr_data = json.loads(qr_body.decode("utf-8"))
        self.assertTrue(qr_data["enabled"])

        # Student B cannot access Student A's bill QR
        qr_forbidden, _, _ = asyncio.run(
            _run_asgi_request(self.app, "GET", f"/api/bills/{bill_a_id}/qr", headers=self.student_b_headers)
        )
        self.assertEqual(qr_forbidden, 403)

    def test_frontend_assets_include_student_dashboard(self):
        """Frontend app.js must include renderStudentDashboard, openBillPaymentQrModal, and Student Portal navigation."""
        status, _, body = asyncio.run(_run_asgi_request(self.app, "GET", "/assets/app.js"))
        self.assertEqual(status, 200)
        js = body.decode("utf-8")
        self.assertIn("renderStudentDashboard", js)
        self.assertIn("openBillPaymentQrModal", js)
        self.assertIn("Student Portal", js)
        self.assertIn("data.role === 'student'", js)
        self.assertIn("switchRoutineCourse", js)

    def test_student_portal_timetable_isolation(self):
        """Student must only see timetable periods of their enrolled class and enrolled course(s)."""
        # Create a second course that Student A is NOT enrolled in
        other_course_res = json.loads(
            asyncio.run(
                _run_asgi_request(
                    self.app,
                    "POST",
                    "/api/courses",
                    headers=self.admin_headers,
                    body={"course_name": "Music & Arts", "category": "General", "default_fee": 2000, "duration_months": 2},
                )
            )[2].decode("utf-8")
        )
        other_course_id = other_course_res["id"]

        # Look up routine plan
        plans = json.loads(
            asyncio.run(
                _run_asgi_request(self.app, "GET", "/api/routines/plans", headers=self.admin_headers)
            )[2].decode("utf-8")
        )
        plan_id = plans[0]["id"]

        # Ensure Grade 10 class level exists
        asyncio.run(
            _run_asgi_request(
                self.app, "POST", "/api/class-levels", headers=self.admin_headers,
                body={"level_name": "Grade 10", "status": "Active"},
            )
        )
        classes = json.loads(
            asyncio.run(
                _run_asgi_request(self.app, "GET", "/api/lookups", headers=self.admin_headers)
            )[2].decode("utf-8")
        )["classes"]
        gr10_class = next((c for c in classes if c["level_name"] == "Grade 10"), None)
        self.assertIsNotNone(gr10_class)
        gr10_class_id = gr10_class["id"]

        # Ensure Student A is mapped to gr10_class_id
        self.db.execute("UPDATE students SET class_level_id=? WHERE id=?", (gr10_class_id, self.student_a_id))

        # Create 4 routine periods:
        # 1. Grade 10 Math (Course: None) -> Should be visible to Student A
        asyncio.run(
            _run_asgi_request(
                self.app, "POST", "/api/routines", headers=self.admin_headers,
                body={
                    "class_name": "Grade 10", "class_level_id": gr10_class_id, "day_of_week": "Sunday",
                    "period_label": "1st", "subject_name": "General Math", "status": "Active",
                    "routine_plan_id": plan_id,
                },
            )
        )

        # 2. Grade 10 Science Lab (Course: Science & Tech, self.course_id) -> Enrolled by Student A -> Should be visible
        asyncio.run(
            _run_asgi_request(
                self.app, "POST", "/api/routines", headers=self.admin_headers,
                body={
                    "class_name": "Grade 10", "class_level_id": gr10_class_id, "day_of_week": "Sunday",
                    "period_label": "2nd", "subject_name": "Science Lab", "course_id": self.course_id,
                    "status": "Active", "routine_plan_id": plan_id,
                },
            )
        )

        # 3. Grade 10 Music (Course: Music & Arts, other_course_id) -> NOT enrolled by Student A -> MUST NOT be visible
        asyncio.run(
            _run_asgi_request(
                self.app, "POST", "/api/routines", headers=self.admin_headers,
                body={
                    "class_name": "Grade 10", "class_level_id": gr10_class_id, "day_of_week": "Sunday",
                    "period_label": "3rd", "subject_name": "Guitar Class", "course_id": other_course_id,
                    "status": "Active", "routine_plan_id": plan_id,
                },
            )
        )

        # 4. Grade 9 Nepali (Different class) -> MUST NOT be visible to Student A
        asyncio.run(
            _run_asgi_request(
                self.app, "POST", "/api/routines", headers=self.admin_headers,
                body={
                    "class_name": "Grade 9", "day_of_week": "Sunday",
                    "period_label": "1st", "subject_name": "Nepali Grade 9", "status": "Active",
                    "routine_plan_id": plan_id,
                },
            )
        )

        # Student A fetches routines:
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", f"/api/routines?routine_plan_id={plan_id}", headers=self.student_a_headers)
        )
        self.assertEqual(status, 200)
        st_a_routines = json.loads(body.decode("utf-8"))
        subject_names = [r["subject_name"] for r in st_a_routines]
        self.assertIn("General Math", subject_names)
        self.assertIn("Science Lab", subject_names)
        self.assertNotIn("Guitar Class", subject_names)
        self.assertNotIn("Nepali Grade 9", subject_names)

        # Student A filters by enrolled course (self.course_id)
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", f"/api/routines?routine_plan_id={plan_id}&course_id={self.course_id}", headers=self.student_a_headers)
        )
        self.assertEqual(status, 200)
        filtered_c = json.loads(body.decode("utf-8"))
        self.assertEqual(len(filtered_c), 1)
        self.assertEqual(filtered_c[0]["subject_name"], "Science Lab")

        # Student A attempts to filter by un-enrolled course (other_course_id) -> Returns empty list
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", f"/api/routines?routine_plan_id={plan_id}&course_id={other_course_id}", headers=self.student_a_headers)
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body.decode("utf-8")), [])

        # Student A checks dashboard today's schedule -> Should only contain enrolled class & course
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/dashboard", headers=self.student_a_headers)
        )
        self.assertEqual(status, 200)
        dash_data = json.loads(body.decode("utf-8"))
        today_subs = [r["subject_name"] for r in dash_data.get("today_routine", [])]
        self.assertNotIn("Guitar Class", today_subs)
        self.assertNotIn("Nepali Grade 9", today_subs)

        # Student A downloads timetable PDF -> 200 OK
        status, headers, body = asyncio.run(
            _run_asgi_request(self.app, "GET", f"/api/routines/pdf?routine_plan_id={plan_id}", headers=self.student_a_headers)
        )
        self.assertEqual(status, 200)
        self.assertEqual(dict(headers).get("content-type"), "application/pdf")

        # Student A attempts to download PDF for un-enrolled course -> 403 Forbidden
        status, _, _ = asyncio.run(
            _run_asgi_request(self.app, "GET", f"/api/routines/pdf?routine_plan_id={plan_id}&course_id={other_course_id}", headers=self.student_a_headers)
        )
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
