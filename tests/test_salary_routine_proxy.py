import asyncio
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from dataclasses import replace

import nepali_datetime as nepali

from elh.config import AppConfig
from elh.infrastructure import create_database
from elh.web.app import create_app
from tests.test_web_security import _run_asgi_request


class SalaryRoutineProxyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.config = replace(
            AppConfig(),
            database_engine="sqlite",
            database_path=self.db_path,
            admin_username="testadmin",
            admin_password="Admin@TestPassword2025",
            secret_key="test-secret-key-123456",
        )
        self.db = create_database(self.config)
        self.db.initialize()
        self.app = create_app(self.config)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _login(self):
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "POST",
            "/api/auth/login",
            body={"username": "testadmin", "password": "Admin@TestPassword2025"}
        ))
        self.assertEqual(status, 200)
        return json.loads(body.decode("utf-8"))["token"]

    def test_per_class_salary_with_routine_attendance_and_proxy(self):
        token = self._login()
        headers = {"authorization": f"Bearer {token}"}

        # 1. Create Teacher A (Per Class) and Teacher B (Monthly)
        t_a_id = self.db.execute(
            "INSERT INTO teachers (teacher_name, contact, joined_date, salary_type, basic_salary, status) "
            "VALUES ('Teacher Alpha', '9800000001', '2083/01/01', 'Per Class Payment', 800.0, 'Active')"
        )
        t_b_id = self.db.execute(
            "INSERT INTO teachers (teacher_name, contact, joined_date, salary_type, basic_salary, status) "
            "VALUES ('Teacher Beta', '9800000002', '2083/01/01', 'Monthly Salary', 25000.0, 'Active')"
        )
        account_id = self.db.execute(
            "INSERT INTO accounts (account_name, account_type, opening_balance, status) "
            "VALUES ('Main Cash', 'Cash Counter', 100000.0, 'Active')"
        )

        # 2. Create routine plan and class routines
        plan_id = self.db.execute(
            "INSERT INTO routine_plans (plan_name, effective_from, effective_to, status) "
            "VALUES ('Term 1 Routine', '2083/01/01', '2083/12/30', 'Active')"
        )
        # Routine 1: Sunday 10:00 AM for Teacher Alpha
        r1_id = self.db.execute(
            "INSERT INTO class_routines (class_name, day_of_week, period_label, subject_name, teacher_id, routine_plan_id, status) "
            "VALUES ('Grade 10', 'Sunday', '1st Period', 'Mathematics', ?, ?, 'Active')",
            (t_a_id, plan_id),
        )
        # Routine 2: Monday 11:00 AM for Teacher Alpha
        r2_id = self.db.execute(
            "INSERT INTO class_routines (class_name, day_of_week, period_label, subject_name, teacher_id, routine_plan_id, status) "
            "VALUES ('Grade 10', 'Monday', '2nd Period', 'Mathematics', ?, ?, 'Active')",
            (t_a_id, plan_id),
        )
        # Routine 3: Tuesday 10:00 AM for Teacher Beta
        r3_id = self.db.execute(
            "INSERT INTO class_routines (class_name, day_of_week, period_label, subject_name, teacher_id, routine_plan_id, status) "
            "VALUES ('Grade 9', 'Tuesday', '1st Period', 'Science', ?, ?, 'Active')",
            (t_b_id, plan_id),
        )

        # In BS month 2083/05 (Bhadra 2083):
        # Let's see how many Sundays and Mondays exist in 2083/05:
        first_bs = nepali.date(2083, 5, 1)
        next_bs = nepali.date(2083, 6, 1)
        start_ad = first_bs.to_datetime_date()
        end_ad = next_bs.to_datetime_date()

        # Let's find dates for Sunday and Monday
        sundays = []
        mondays = []
        tuesdays = []
        from datetime import timedelta
        curr = start_ad
        while curr < end_ad:
            bs_date_str = nepali.date.from_datetime_date(curr).strftime("%Y/%m/%d")
            if curr.weekday() == 6:  # Sunday
                sundays.append((curr, bs_date_str))
            elif curr.weekday() == 0:  # Monday
                mondays.append((curr, bs_date_str))
            elif curr.weekday() == 1:  # Tuesday
                tuesdays.append((curr, bs_date_str))
            curr += timedelta(days=1)

        total_scheduled_a = len(sundays) + len(mondays)
        self.assertGreater(total_scheduled_a, 0)

        # 3. Add biometric attendance punches for Teacher Alpha for some dates
        # Teacher Alpha punches in on all Sundays, but misses all Mondays except one
        attended_sundays = sundays
        for ad_dt, bs_str in attended_sundays:
            self.db.execute(
                "INSERT INTO attendance_logs (device_user_id, person_type, person_id, occurred_at, event_type) "
                "VALUES ('DEV-01', 'teacher', ?, ?, 'Check-in')",
                (t_a_id, f"{ad_dt.isoformat()} 09:30:00"),
            )
        # Teacher Alpha also punches in on the first Monday
        first_monday = mondays[0]
        self.db.execute(
            "INSERT INTO attendance_logs (device_user_id, person_type, person_id, occurred_at, event_type) "
            "VALUES ('DEV-01', 'teacher', ?, ?, 'Check-in')",
            (t_a_id, f"{first_monday[0].isoformat()} 09:45:00"),
        )

        # 4. Proxy scenarios:
        # Scenario A: Teacher Alpha was on leave on the 2nd Monday, and Teacher Beta took it as approved proxy
        second_monday = mondays[1]
        self.db.execute(
            "INSERT INTO proxy_class_requests (routine_id, class_date, original_teacher_id, proxy_teacher_id, "
            "status, proxy_status, reason) VALUES (?, ?, ?, ?, 'Approved', 'Accepted', 'Sick leave')",
            (r2_id, second_monday[1], t_a_id, t_b_id),
        )

        # Scenario B: Teacher Beta was absent on the 1st Tuesday, and Teacher Alpha substituted as approved proxy
        first_tuesday = tuesdays[0]
        self.db.execute(
            "INSERT INTO proxy_class_requests (routine_id, class_date, original_teacher_id, proxy_teacher_id, "
            "status, proxy_status, reason) VALUES (?, ?, ?, ?, 'Approved', 'Accepted', 'Training')",
            (r3_id, first_tuesday[1], t_b_id, t_a_id),
        )

        # 5. Call calculate API for Teacher Alpha
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "POST",
            "/api/salary/calculate",
            headers=headers,
            body={"teacher_id": t_a_id, "salary_month": "2083/05"},
        ))
        self.assertEqual(status, 200)
        calc = json.loads(body.decode("utf-8"))

        # Verify scheduled classes
        self.assertEqual(calc["scheduled_classes"], total_scheduled_a)

        # Attended classes = len(sundays) + 1 (first monday)
        expected_attended = len(sundays) + 1
        self.assertEqual(calc["attended_classes"], expected_attended)

        # Relieved by proxy = 1 (second monday)
        self.assertEqual(calc["relieved_classes"], 1)
        self.assertEqual(calc["proxy_classes_relieved"], 1)

        # Proxy taken = 1 (first tuesday substitute for Beta)
        self.assertEqual(calc["proxy_classes_taken"], 1)
        self.assertEqual(len(calc["proxy_taken_list"]), 1)
        self.assertEqual(calc["proxy_taken_list"][0]["original_teacher_name"], "Teacher Beta")

        # Payable classes = attended (expected_attended) + proxy_taken (1)
        expected_payable = expected_attended + 1
        self.assertEqual(calc["payable_classes"], expected_payable)

        # Basic salary suggested = expected_payable * 800
        expected_basic = round(expected_payable * 800.0, 2)
        self.assertEqual(calc["suggested_basic"], expected_basic)
        self.assertEqual(calc["net_total"], expected_basic)

    def test_monthly_salary_with_advance_and_proxy_bonus(self):
        token = self._login()
        headers = {"authorization": f"Bearer {token}"}

        # Create Teacher Beta (Monthly Salary 30,000)
        t_id = self.db.execute(
            "INSERT INTO teachers (teacher_name, contact, joined_date, salary_type, basic_salary, status) "
            "VALUES ('Teacher Beta', '9800000002', '2083/01/01', 'Monthly Salary', 30000.0, 'Active')"
        )
        acc_id = self.db.execute(
            "INSERT INTO accounts (account_name, account_type, opening_balance, status) "
            "VALUES ('Bank A', 'Bank', 100000.0, 'Active')"
        )
        # Advance with monthly deduction
        self.db.execute(
            "INSERT INTO teacher_advances (teacher_id, advance_date, amount, paid_from_account_id, monthly_deduction, recovered_amount, status) "
            "VALUES (?, '2083/04/10', 10000.0, ?, 3000.0, 0.0, 'Outstanding')",
            (t_id, acc_id),
        )

        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "POST",
            "/api/salary/calculate",
            headers=headers,
            body={"teacher_id": t_id, "salary_month": "2083/05"},
        ))
        self.assertEqual(status, 200)
        calc = json.loads(body.decode("utf-8"))
        self.assertEqual(calc["outstanding_advance"], 10000.0)
        self.assertEqual(calc["suggested_advance_deduction"], 3000.0)
        self.assertEqual(calc["suggested_basic"], 30000.0)
        # Net = 30000 - 3000 = 27000
        self.assertEqual(calc["net_total"], 27000.0)

    def test_academic_calendar_holiday_exclusion(self):
        # When a day is a holiday/closure in academic_calendar_events, it is not counted in scheduled classes
        t_id = self.db.execute(
            "INSERT INTO teachers (teacher_name, contact, joined_date, salary_type, basic_salary, status) "
            "VALUES ('Teacher Gamma', '9800000003', '2083/01/01', 'Per Class Payment', 500.0, 'Active')"
        )
        plan_id = self.db.execute(
            "INSERT INTO routine_plans (plan_name, effective_from, effective_to, status) "
            "VALUES ('Plan Gamma', '2083/01/01', '2083/12/30', 'Active')"
        )
        self.db.execute(
            "INSERT INTO class_routines (class_name, day_of_week, period_label, subject_name, teacher_id, routine_plan_id, status) "
            "VALUES ('Grade 8', 'Wednesday', '1st Period', 'English', ?, ?, 'Active')",
            (t_id, plan_id),
        )

        token = self._login()
        headers = {"authorization": f"Bearer {token}"}

        # Count wednesdays in 2083/05 before holiday
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "POST",
            "/api/salary/calculate",
            headers=headers,
            body={"teacher_id": t_id, "salary_month": "2083/05"},
        ))
        self.assertEqual(status, 200)
        calc_before = json.loads(body.decode("utf-8"))
        count_before = calc_before["scheduled_classes"]
        self.assertGreater(count_before, 0)

        # Mark all of 2083/05 as a Holiday/Closure
        self.db.execute(
            "INSERT INTO academic_calendar_events (event_name, event_type, start_date, end_date, status) "
            "VALUES ('Dashain Vacation', 'Holiday', '2083/05/01', '2083/05/32', 'Active')"
        )
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "POST",
            "/api/salary/calculate",
            headers=headers,
            body={"teacher_id": t_id, "salary_month": "2083/05"},
        ))
        self.assertEqual(status, 200)
        calc_after = json.loads(body.decode("utf-8"))
        self.assertEqual(calc_after["scheduled_classes"], 0)
        self.assertEqual(calc_after["attended_classes"], 0)
        self.assertEqual(calc_after["payable_classes"], 0)
