from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from elh.config import AppConfig
from elh.infrastructure.sqlite_database import SQLiteDatabase
from elh.services.assistant import InstituteAssistant
from elh.services.container import ServiceContainer


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_assistant.db"
        self.config = AppConfig(
            database_engine="sqlite",
            database_path=self.db_path,
            seed_demo_data=False,
            attendance_driver="disabled",
            attendance_auto_poll=False,
            pos_printer_driver="disabled",
        )
        self.db = SQLiteDatabase(self.db_path, seed_demo_data=False)
        self.services = ServiceContainer.build(self.config, self.db)
        self.assistant = InstituteAssistant(self.services, self.db)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_help_command(self):
        resp = self.assistant.execute("/help")
        self.assertEqual(resp.badge, "HELP")
        self.assertIn("Available Natural Language Queries", resp.content)

    def test_natural_language_help(self):
        resp = self.assistant.execute("What can you do?")
        self.assertEqual(resp.badge, "HELP")

    def test_stats_query(self):
        resp = self.assistant.execute("/stats")
        self.assertEqual(resp.badge, "METRICS")
        self.assertIn("Total Active Students", resp.content)

    def test_absent_and_present_queries(self):
        resp_absent = self.assistant.execute("Who is absent today?")
        self.assertIn(resp_absent.badge, ["SUCCESS", "0 ABSENT", "ABSENT"])

        resp_present = self.assistant.execute("Who is present today?")
        self.assertIn(resp_present.badge, ["INFO", "PRESENT"])

    def test_dues_and_accounts_queries(self):
        resp_dues = self.assistant.execute("/dues")
        self.assertTrue(len(resp_dues.content) > 0)

        resp_accounts = self.assistant.execute("Show cash and bank account balances")
        self.assertIn("Total Liquidity", resp_accounts.content)

    def test_student_search_query(self):
        # Insert a sample student
        self.db.execute(
            "INSERT INTO students (student_name, contact, class_name, status, joining_date) "
            "VALUES ('Bikash Sharma', '9841000000', 'Class 10', 'Active', '2026/01/01')"
        )
        resp = self.assistant.execute("/find Bikash")
        self.assertEqual(resp.badge, "1 FOUND")
        self.assertIn("Bikash Sharma", resp.content)

        # Search by phone via natural language
        resp2 = self.assistant.execute("Search student 9841000000")
        self.assertIn("9841000000", resp2.badge)
        self.assertIn("Bikash Sharma", resp2.content)

    def test_courses_and_staff_queries(self):
        resp_courses = self.assistant.execute("/courses")
        self.assertEqual(resp_courses.title, "Course Catalog")

        resp_staff = self.assistant.execute("/staff")
        self.assertEqual(resp_staff.title, "Staff Directory")

    def test_system_health_query(self):
        resp_health = self.assistant.execute("Check system health")
        self.assertEqual(resp_health.title, "System & Hardware Diagnostics")

    def test_natural_language_contact_and_person_queries(self):
        # Insert a sample student
        self.db.execute(
            "INSERT INTO students (student_name, contact, parent_name, class_name, status, joining_date, address) "
            "VALUES ('Supriya Adhikari', '9841234567', 'Ram Adhikari', 'Class 10', 'Active', '2026/01/01', 'Kathmandu')"
        )
        # Insert a sample staff member
        self.db.execute(
            "INSERT INTO teachers (teacher_name, contact, email, staff_type, subject, status, joined_date, basic_salary) "
            "VALUES ('Suresh Thapa', '9801234567', 'suresh@example.com', 'Instructor', 'Mathematics', 'Active', '2026/01/01', 25000)"
        )

        # 1. Exact contact question
        resp1 = self.assistant.execute("What is the contact no of Supriya Adhikari?")
        self.assertIn("Supriya Adhikari", resp1.title)
        self.assertIn("9841234567", resp1.content)
        self.assertIn("Ram Adhikari", resp1.content)
        self.assertIn("9841234567", resp1.badge)

        # 2. Who is question
        resp2 = self.assistant.execute("Who is Supriya Adhikari?")
        self.assertIn("Supriya Adhikari", resp2.title)
        self.assertIn("9841234567", resp2.content)

        # 3. Staff contact lookup
        resp3 = self.assistant.execute("What is the phone number of Suresh Thapa?")
        self.assertIn("Suresh Thapa", resp3.title)
        self.assertIn("9801234567", resp3.content)
        self.assertIn("suresh@example.com", resp3.content)

        # 4. Details question
        resp4 = self.assistant.execute("Tell me about Supriya Adhikari")
        self.assertIn("Supriya Adhikari", resp4.title)
        self.assertIn("Kathmandu", resp4.content)

        # 5. Direct name fallback
        resp5 = self.assistant.execute("Supriya Adhikari")
        self.assertIn("Supriya Adhikari", resp5.title)

        # 6. Non-existent person query
        resp6 = self.assistant.execute("What is the contact no of Nonexistent Person?")
        self.assertEqual(resp6.badge, "NOT FOUND")
        self.assertIn("No student or staff member matching", resp6.content)

    def test_external_ai_agent_query_and_fallback(self):
        class DummyAIAgent:
            def is_configured(self):
                return True

            def query(self, prompt, system_context=None):
                return True, f"Simulated AI guidance for: {prompt}"

        assistant_with_ai = InstituteAssistant(self.services, self.db, external_ai=DummyAIAgent())

        # 1. Unknown query automatically routes to external AI
        resp = assistant_with_ai.execute("Explain python decorators for classroom demonstration")
        self.assertEqual(resp.badge, "EXTERNAL AI")
        self.assertIn("Simulated AI guidance for", resp.content)

        # 2. Explicit /ai slash command
        resp_ai = assistant_with_ai.execute("/ai Suggest 3 tips to improve student attendance")
        self.assertEqual(resp_ai.badge, "EXTERNAL AI")
        self.assertIn("Simulated AI guidance for", resp_ai.content)

        # 3. Unconfigured AI agent fallback message
        class UnconfiguredAIAgent:
            def is_configured(self):
                return False

            def query(self, prompt, system_context=None):
                return False, "Not configured"

        assistant_no_ai = InstituteAssistant(self.services, self.db, external_ai=UnconfiguredAIAgent())
        resp_hint = assistant_no_ai.execute("unrecognized query xyz999")
        self.assertEqual(resp_hint.badge, "HINT")
        self.assertIn("Or ask external AI with: /ai", resp_hint.content)

    def test_monthly_attendance_person_query(self):
        # Insert student Aakriti Basnet
        self.db.execute(
            "INSERT INTO students (student_name, contact, parent_name, class_name, status, joining_date, address) "
            "VALUES ('Aakriti Basnet', '9841999888', 'Hari Basnet', 'Class 10', 'Active', '2026/01/01', 'Kathmandu')"
        )
        student_id = self.db.query_one("SELECT id FROM students WHERE student_name='Aakriti Basnet'")["id"]

        # Insert 3 punches across 2 different dates in the current month
        today_ad_str = datetime.now().strftime("%Y-%m-%d")
        self.db.execute(
            "INSERT INTO attendance_logs (device_user_id, person_type, person_id, occurred_at, event_type) "
            "VALUES ('DEV001', 'student', ?, ? || ' 08:30:00', 'CheckIn')",
            (student_id, today_ad_str),
        )
        self.db.execute(
            "INSERT INTO attendance_logs (device_user_id, person_type, person_id, occurred_at, event_type) "
            "VALUES ('DEV001', 'student', ?, ? || ' 16:00:00', 'CheckOut')",
            (student_id, today_ad_str),
        )

        # 1. Natural language query directly
        resp1 = self.assistant.execute("How many days does Aakriti Basnet is present this month?")
        self.assertIn("Aakriti Basnet", resp1.title)
        self.assertIn("1 day(s) present", resp1.content)
        self.assertIn("9841999888", resp1.content)

        # 2. Via /ai even when external AI is unconfigured (graceful local fallback)
        class UnconfiguredAIAgent:
            def is_configured(self):
                return False

            def query(self, prompt, system_context=None):
                return False, "Not configured"

        assistant_unconfigured = InstituteAssistant(self.services, self.db, external_ai=UnconfiguredAIAgent())
        resp2 = assistant_unconfigured.execute("/ai How many days does Aakriti Basnet is present this month?")
        self.assertIn("Aakriti Basnet", resp2.title)
        self.assertIn("1 day(s) present", resp2.content)


if __name__ == "__main__":
    unittest.main()
