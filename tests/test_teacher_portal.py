from __future__ import annotations

import asyncio
import gc
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from elh.config import AppConfig
from elh.infrastructure import create_database
from elh.web.app import create_app
from tests.test_web_security import _run_asgi_request


class TeacherPortalTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_teacher_portal.db"
        self.config = replace(
            AppConfig(),
            database_engine="sqlite",
            database_path=self.db_path,
            admin_username="testadmin",
            admin_password="Admin@TestPassword2025",
            secret_key="unit-test-secret-key-teacher-portal",
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

        # 1. Create Teacher A and Teacher B via /api/staff
        t_a_res = json.loads(
            asyncio.run(
                _run_asgi_request(
                    self.app,
                    "POST",
                    "/api/staff",
                    headers=self.admin_headers,
                    body={
                        "teacher_name": "Prof. Ram Sharma",
                        "staff_type": "Teaching",
                        "contact": "9841111111",
                        "email": "ram@elh.edu.np",
                        "subject": "Mathematics",
                        "basic_salary": 45000,
                        "status": "Active",
                        "joined_date": "2080/01/01",
                    },
                )
            )[2].decode("utf-8")
        )
        self.teacher_a_id = t_a_res["id"]

        t_b_res = json.loads(
            asyncio.run(
                _run_asgi_request(
                    self.app,
                    "POST",
                    "/api/staff",
                    headers=self.admin_headers,
                    body={
                        "teacher_name": "Dr. Sita Thapa",
                        "staff_type": "Teaching",
                        "contact": "9842222222",
                        "email": "sita@elh.edu.np",
                        "subject": "Science",
                        "basic_salary": 50000,
                        "status": "Active",
                        "joined_date": "2080/02/01",
                    },
                )
            )[2].decode("utf-8")
        )
        self.teacher_b_id = t_b_res["id"]

        # 2. Create Class Levels
        self.gr10_class_id = self.db.execute("INSERT INTO class_levels (level_name, status) VALUES ('Grade 10', 'Active')")
        self.gr9_class_id = self.db.execute("INSERT INTO class_levels (level_name, status) VALUES ('Grade 9', 'Active')")

        # 3. Create Students and Courses
        st1_res = json.loads(
            asyncio.run(
                _run_asgi_request(
                    self.app,
                    "POST",
                    "/api/students",
                    headers=self.admin_headers,
                    body={"name": "Aarav Sharma", "class_name": "Grade 10", "joining_date": "2083/01/01", "contact": "9841000001"},
                )
            )[2].decode("utf-8")
        )
        self.student_1_id = st1_res["id"]
        self.db.execute("UPDATE students SET class_level_id=? WHERE id=?", (self.gr10_class_id, self.student_1_id))

        st2_res = json.loads(
            asyncio.run(
                _run_asgi_request(
                    self.app,
                    "POST",
                    "/api/students",
                    headers=self.admin_headers,
                    body={"name": "Bibek Karki", "class_name": "Grade 9", "joining_date": "2083/01/01", "contact": "9841000002"},
                )
            )[2].decode("utf-8")
        )
        self.student_2_id = st2_res["id"]
        self.db.execute("UPDATE students SET class_level_id=? WHERE id=?", (self.gr9_class_id, self.student_2_id))

        course_res = json.loads(
            asyncio.run(
                _run_asgi_request(
                    self.app,
                    "POST",
                    "/api/courses",
                    headers=self.admin_headers,
                    body={
                        "course_name": "Advanced Calculus",
                        "category": "Mathematics",
                        "instructor_name": "Prof. Ram Sharma",
                        "default_fee": 3500,
                        "duration_months": 3,
                    },
                )
            )[2].decode("utf-8")
        )
        self.course_id = course_res["id"]

        # Enroll student 2 in course
        asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/enrollments",
                headers=self.admin_headers,
                body={"student_id": self.student_2_id, "course_id": self.course_id, "start_date": "2083/01/01", "monthly_fee": 3500},
            )
        )

        # 4. Create Routine Plan and Routine Periods
        plan_res = json.loads(
            asyncio.run(
                _run_asgi_request(
                    self.app,
                    "POST",
                    "/api/routines/plans",
                    headers=self.admin_headers,
                    body={"plan_name": "Academic Year 2083 Regular", "effective_from": "2083/01/01", "status": "Active"},
                )
            )[2].decode("utf-8")
        )
        self.plan_id = plan_res["id"]

        # Add 2 periods for Teacher A (Grade 10 and Advanced Calculus)
        asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/routines",
                headers=self.admin_headers,
                body={
                    "routine_plan_id": self.plan_id,
                    "class_name": "Grade 10",
                    "class_level_id": self.gr10_class_id,
                    "subject_name": "Compulsory Math",
                    "teacher_id": self.teacher_a_id,
                    "day_of_week": "Sunday",
                    "period_label": "Period 1",
                    "start_time": "09:00",
                    "end_time": "09:45",
                    "status": "Active",
                },
            )
        )
        asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/routines",
                headers=self.admin_headers,
                body={
                    "routine_plan_id": self.plan_id,
                    "class_name": "Grade 10",
                    "class_level_id": self.gr10_class_id,
                    "course_id": self.course_id,
                    "subject_name": "Advanced Calculus",
                    "teacher_id": self.teacher_a_id,
                    "day_of_week": "Monday",
                    "period_label": "Period 2",
                    "start_time": "10:00",
                    "end_time": "10:45",
                    "status": "Active",
                },
            )
        )

        # Add 1 period for Teacher B (Grade 9 Science)
        asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/routines",
                headers=self.admin_headers,
                body={
                    "routine_plan_id": self.plan_id,
                    "class_name": "Grade 9",
                    "class_level_id": self.gr9_class_id,
                    "subject_name": "Physics",
                    "teacher_id": self.teacher_b_id,
                    "day_of_week": "Sunday",
                    "period_label": "Period 3",
                    "start_time": "11:00",
                    "end_time": "11:45",
                    "status": "Active",
                },
            )
        )

        # 5. Insert Salary payouts, Advances, and Attendance directly into DB
        with self.db.connect() as conn:
            acc_cur = conn.execute(
                "INSERT INTO accounts (account_name, account_type, opening_balance, status) VALUES ('Main Cash', 'Cash Counter', 500000, 'Active')"
            )
            account_id = acc_cur.lastrowid

            cur_a = conn.execute(
                """
                INSERT INTO salary_payouts
                (teacher_id, salary_month, basic_salary, extra_payment, bonus,
                 allowance, advance_deduction, other_deduction, net_salary,
                 attendance_days, working_hours, class_count,
                 payment_date, paid_from_account_id, payment_method,
                 voucher_no, status, remarks)
                VALUES (?, '2083/04', '45000', '2000', '1500', '1000', '5000', '0', '44500',
                        25, '150.0', 40, '2083/04/30', ?, 'Bank Transfer', 'V-001', 'Paid', 'July Salary')
                """,
                (self.teacher_a_id, account_id),
            )
            self.salary_payout_a_id = cur_a.lastrowid

            cur_b = conn.execute(
                """
                INSERT INTO salary_payouts
                (teacher_id, salary_month, basic_salary, extra_payment, bonus,
                 allowance, advance_deduction, other_deduction, net_salary,
                 attendance_days, working_hours, class_count,
                 payment_date, paid_from_account_id, payment_method,
                 voucher_no, status, remarks)
                VALUES (?, '2083/04', '50000', '0', '0', '0', '0', '0', '50000',
                        26, '160.0', 44, '2083/04/30', ?, 'Bank Transfer', 'V-002', 'Paid', 'July Salary')
                """,
                (self.teacher_b_id, account_id),
            )
            self.salary_payout_b_id = cur_b.lastrowid

            conn.execute(
                """
                INSERT INTO teacher_advances
                (teacher_id, advance_date, amount, recovered_amount, paid_from_account_id,
                 payment_method, reference_no, recovery_method,
                 recovery_start_month, monthly_deduction, status, remarks)
                VALUES (?, '2083/04/10', '10000', '5000', ?, 'Cash', 'ADV-01', 'Monthly Deduction', '2083/04', '5000', 'Partially Recovered', 'Festival advance')
                """,
                (self.teacher_a_id, account_id),
            )

            conn.execute(
                """
                INSERT INTO attendance_logs (device_user_id, person_type, person_id, occurred_at, event_type)
                VALUES
                ('T-01', 'teacher', ?, '2026-09-01 09:15:00', 'CHECK_IN'),
                ('T-01', 'teacher', ?, '2026-09-01 16:30:00', 'CHECK_OUT')
                """,
                (self.teacher_a_id, self.teacher_a_id),
            )
            conn.execute(
                """
                INSERT INTO attendance_logs (device_user_id, person_type, person_id, occurred_at, event_type)
                VALUES
                ('T-02', 'teacher', ?, '2026-09-01 09:30:00', 'CHECK_IN')
                """,
                (self.teacher_b_id,),
            )

        # 6. Create user accounts for Teacher A and Teacher B
        asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/users",
                headers=self.admin_headers,
                body={
                    "username": "ram_teacher",
                    "password": "Teacher@Password2025",
                    "display_name": "Prof. Ram Sharma",
                    "role": "staff",
                    "teacher_id": self.teacher_a_id,
                },
            )
        )
        asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/users",
                headers=self.admin_headers,
                body={
                    "username": "sita_teacher",
                    "password": "Teacher@Password2025",
                    "display_name": "Dr. Sita Thapa",
                    "role": "teacher",
                    "teacher_id": self.teacher_b_id,
                },
            )
        )

        # Login as Teacher A
        l_status, _, l_body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/auth/login",
                body={"username": "ram_teacher", "password": "Teacher@Password2025"},
            )
        )
        self.assertEqual(l_status, 200)
        self.teacher_a_token = json.loads(l_body.decode("utf-8"))["token"]
        self.teacher_a_headers = {"authorization": f"Bearer {self.teacher_a_token}"}

        # Login as Teacher B
        l_status_b, _, l_body_b = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/auth/login",
                body={"username": "sita_teacher", "password": "Teacher@Password2025"},
            )
        )
        self.assertEqual(l_status_b, 200)
        self.teacher_b_token = json.loads(l_body_b.decode("utf-8"))["token"]
        self.teacher_b_headers = {"authorization": f"Bearer {self.teacher_b_token}"}

    def tearDown(self):
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except (PermissionError, OSError):
            pass

    def test_teacher_dashboard_kpis_and_overview(self):
        """Verify GET /api/dashboard returns the 4 required KPIs and detailed datasets for the logged-in teacher."""
        status, _, body = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/dashboard", headers=self.teacher_a_headers)
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))

        # Role & Teacher Profile
        self.assertIn(data["role"], ("staff", "teacher"))
        teacher = data["teacher"]
        self.assertEqual(teacher["id"], self.teacher_a_id)
        self.assertEqual(teacher["teacher_name"], "Prof. Ram Sharma")
        self.assertEqual(teacher["monthly_salary"], 45000)

        # 1. Total classes this week
        metrics = data["metrics"]
        self.assertEqual(metrics["total_classes_week"], 2)  # Sunday & Monday periods
        self.assertEqual(len(data["weekly_routines"]), 2)

        # 2. No of students assigned in class to them
        # Teacher A teaches Grade 10 (Student 1 is Grade 10) and Advanced Calculus (Student 2 is enrolled)
        self.assertEqual(metrics["total_students_assigned"], 2)
        assigned_student_ids = [s["id"] for s in data["assigned_students"]]
        self.assertIn(self.student_1_id, assigned_student_ids)
        self.assertIn(self.student_2_id, assigned_student_ids)

        # 3. Payment history, advances, other payments, and pending payment
        # Net salary received = 45000 + 2000 + 1500 + 1000 - 5000 = 44500
        self.assertEqual(metrics["total_salary_paid"], 44500)
        # Other payments = extra_payment (2000) + bonus (1500) + allowance (1000) = 4500
        self.assertEqual(metrics["total_other_payments"], 4500)
        self.assertEqual(data["payment_summary"]["total_advances_received"], 10000)
        # Advance recovered was 5000, so remaining pending = 5000
        self.assertEqual(data["payment_summary"]["total_advances_pending"], 5000)
        # Verify payout list and advances list
        self.assertEqual(len(data["salary_payouts"]), 1)
        self.assertEqual(data["salary_payouts"][0]["id"], self.salary_payout_a_id)
        self.assertEqual(len(data["advances"]), 1)
        self.assertEqual(data["advances"][0]["amount"], 10000)

        # 4. Attendance history of his/her own
        att = data["attendance_history"]
        self.assertIn("month_days", att)
        self.assertIn("lifetime_days", att)
        self.assertGreaterEqual(len(att["daily_logs"]), 1)

    def test_teacher_dedicated_sub_endpoints(self):
        """Verify dedicated endpoints: /api/teacher/classes, /api/teacher/attendance, /api/teacher/payments."""
        # 1. /api/teacher/classes
        s_cls, _, b_cls = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/teacher/classes", headers=self.teacher_a_headers)
        )
        self.assertEqual(s_cls, 200)
        d_cls = json.loads(b_cls.decode("utf-8"))
        self.assertEqual(d_cls["total_classes_week"], 2)
        self.assertEqual(d_cls["total_students"], 2)

        # 2. /api/teacher/attendance
        s_att, _, b_att = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/teacher/attendance", headers=self.teacher_a_headers)
        )
        self.assertEqual(s_att, 200)
        d_att = json.loads(b_att.decode("utf-8"))
        self.assertIn("history", d_att)
        self.assertGreaterEqual(len(d_att["history"]["daily_logs"]), 1)

        # 3. /api/teacher/payments
        s_pay, _, b_pay = asyncio.run(
            _run_asgi_request(self.app, "GET", "/api/teacher/payments", headers=self.teacher_a_headers)
        )
        self.assertEqual(s_pay, 200)
        d_pay = json.loads(b_pay.decode("utf-8"))
        summary = d_pay["summary"]
        self.assertEqual(summary["total_salary_paid"], 44500)
        self.assertEqual(summary["total_other_payments"], 4500)
        self.assertEqual(summary["total_advances_received"], 10000)
        self.assertEqual(summary["total_advances_pending"], 5000)
        self.assertEqual(len(d_pay["salaries"]), 1)
        self.assertEqual(d_pay["salaries"][0]["teacher_id"], self.teacher_a_id)

    def test_teacher_routines_filtering_and_pdf(self):
        """Verify GET /api/routines and /api/routines/pdf filter to the teacher's own schedule and prevent unauthorized modifications."""
        # Query routines for active plan
        s_rout, _, b_rout = asyncio.run(
            _run_asgi_request(
                self.app, "GET", f"/api/routines?routine_plan_id={self.plan_id}", headers=self.teacher_a_headers
            )
        )
        self.assertEqual(s_rout, 200)
        routines = json.loads(b_rout.decode("utf-8"))
        self.assertEqual(len(routines), 2)
        for r in routines:
            self.assertEqual(r["teacher_id"], self.teacher_a_id)

        # PDF download of routine
        s_pdf, h_pdf, b_pdf = asyncio.run(
            _run_asgi_request(
                self.app, "GET", f"/api/routines/pdf?routine_plan_id={self.plan_id}", headers=self.teacher_a_headers
            )
        )
        self.assertEqual(s_pdf, 200)
        self.assertEqual(dict(h_pdf).get("content-type"), "application/pdf")
        self.assertTrue(len(b_pdf) > 100)

        # Teacher cannot add new routine periods without master_data.manage
        s_create, _, _ = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/routines",
                headers=self.teacher_a_headers,
                body={
                    "routine_plan_id": self.plan_id,
                    "class_name": "Grade 10",
                    "class_level_id": self.gr10_class_id,
                    "subject_name": "Chemistry",
                    "teacher_id": self.teacher_a_id,
                    "day_of_week": "Friday",
                    "period_label": "Period 4",
                    "start_time": "12:00",
                    "end_time": "12:45",
                },
            )
        )
        self.assertEqual(s_create, 403)

    def test_teacher_payslip_isolation(self):
        """Verify teacher can download own payslip PDF, but is strictly forbidden from downloading another teacher's payslip."""
        # Teacher A can download own payslip
        s_own, h_own, b_own = asyncio.run(
            _run_asgi_request(
                self.app, "GET", f"/api/salary/{self.salary_payout_a_id}/payslip/pdf", headers=self.teacher_a_headers
            )
        )
        self.assertEqual(s_own, 200)
        self.assertEqual(dict(h_own).get("content-type"), "application/pdf")
        self.assertTrue(len(b_own) > 100)

        # Teacher A tries to download Teacher B's payslip -> 403 Forbidden
        s_other, _, b_other = asyncio.run(
            _run_asgi_request(
                self.app, "GET", f"/api/salary/{self.salary_payout_b_id}/payslip/pdf", headers=self.teacher_a_headers
            )
        )
        self.assertEqual(s_other, 403)
        self.assertIn("You do not have permission for this payslip", json.loads(b_other.decode("utf-8"))["detail"])

    def test_teacher_portal_unlinked_user_behavior(self):
        """Verify user with role staff but no teacher_id linked handles requests gracefully."""
        # Create staff user without teacher_id
        asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/users",
                headers=self.admin_headers,
                body={
                    "username": "unlinked_staff",
                    "password": "Staff@Password2025",
                    "display_name": "Unlinked Staff",
                    "role": "staff",
                },
            )
        )
        s_l, _, b_l = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/auth/login",
                body={"username": "unlinked_staff", "password": "Staff@Password2025"},
            )
        )
        token = json.loads(b_l.decode("utf-8"))["token"]
        headers = {"authorization": f"Bearer {token}"}

        # Dashboard should return fallback teacher with id=0 and empty KPIs without crashing
        status, _, body = asyncio.run(_run_asgi_request(self.app, "GET", "/api/dashboard", headers=headers))
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data["teacher"]["id"], 0)
        self.assertEqual(data["metrics"]["total_classes_week"], 0)
        self.assertEqual(data["metrics"]["total_students_assigned"], 0)
