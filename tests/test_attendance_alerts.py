import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from elh.hardware.attendance.disabled import DisabledAttendanceDevice
from elh.infrastructure.sqlite_database import SQLiteDatabase
from elh.repositories.attendance import AttendanceRepository
from elh.services.attendance import AttendanceService
from elh.core.settings import SettingsService


class AttendanceAlertsTests(unittest.TestCase):
    def test_consecutive_absence_does_not_reset_to_enrollment_start_across_month_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            db = SQLiteDatabase(Path(folder) / "alerts.db", False)
            course_id = db.execute(
                "INSERT INTO courses (course_name, category, billing_type, default_fee, status) "
                "VALUES ('Science', 'Tuition', 'Monthly', 1000, 'Active')"
            )
            # Student 1: punched yesterday (in previous Nepali month or yesterday)
            s1_id = db.execute(
                "INSERT INTO students (student_name, class_name, joining_date, status) "
                "VALUES ('Student Recent', 'Class 10', '2083/03/01', 'Active')"
            )
            # Student 2: punched 13 working days ago
            s2_id = db.execute(
                "INSERT INTO students (student_name, class_name, joining_date, status) "
                "VALUES ('Student Absent', 'Class 10', '2083/03/01', 'Active')"
            )
            # Enroll both from 2083/03/01
            for sid in (s1_id, s2_id):
                db.execute(
                    "INSERT INTO enrollments (student_id, course_id, start_date, monthly_fee, status) "
                    "VALUES (?, ?, '2083/03/01', 1000, 'Active')",
                    (sid, course_id),
                )

            # Create routine plan and routines for Class 10 (every day of week 0-6 except Saturday 5)
            plan_id = db.execute(
                "INSERT INTO routine_plans (plan_name, effective_from, effective_to, status) "
                "VALUES ('Default Plan', '2083/01/01', '2083/12/30', 'Active')"
            )
            for day_name in ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"):
                db.execute(
                    "INSERT INTO class_routines (routine_plan_id, class_name, day_of_week, period_label, subject_name, start_time, end_time, course_id, status) "
                    "VALUES (?, 'Class 10', ?, 'Period 1', 'Science', '08:00', '09:00', ?, 'Active')",
                    (plan_id, day_name, course_id),
                )

            # Student 1 punched yesterday (2026-09-16, Bhadra 31, 2083)
            # Student 2 punched on 2026-09-02 (Bhadra 17, 2083)
            db.execute(
                "INSERT INTO attendance_logs (device_user_id, person_type, person_id, occurred_at, event_type) "
                "VALUES ('u1', 'student', ?, '2026-09-16 17:00:00', 'Punch')",
                (s1_id,),
            )
            db.execute(
                "INSERT INTO attendance_logs (device_user_id, person_type, person_id, occurred_at, event_type) "
                "VALUES ('u2', 'student', ?, '2026-09-02 17:00:00', 'Punch')",
                (s2_id,),
            )

            # Student 3: never punched
            s3_id = db.execute(
                "INSERT INTO students (student_name, class_name, joining_date, status) "
                "VALUES ('Student Never Punched', 'Class 10', '2083/05/20', 'Active')"
            )
            db.execute(
                "INSERT INTO enrollments (student_id, course_id, start_date, monthly_fee, status) "
                "VALUES (?, ?, '2083/05/20', 1000, 'Active')",
                (s3_id, course_id),
            )

            # Student 4: punched today
            s4_id = db.execute(
                "INSERT INTO students (student_name, class_name, joining_date, status) "
                "VALUES ('Student Today', 'Class 10', '2083/03/01', 'Active')"
            )
            db.execute(
                "INSERT INTO enrollments (student_id, course_id, start_date, monthly_fee, status) "
                "VALUES (?, ?, '2083/03/01', 1000, 'Active')",
                (s4_id, course_id),
            )
            db.execute(
                "INSERT INTO attendance_logs (device_user_id, person_type, person_id, occurred_at, event_type) "
                "VALUES ('u4', 'student', ?, '2026-09-17 08:30:00', 'Punch')",
                (s4_id,),
            )

            settings = SettingsService(db)
            repo = AttendanceRepository(db)
            service = AttendanceService(repo, DisabledAttendanceDevice(), settings=settings)

            class MockDateTimeMeta(type):
                def __instancecheck__(cls, instance):
                    return isinstance(instance, datetime)

            class MockDateTime(datetime, metaclass=MockDateTimeMeta):
                @classmethod
                def now(cls):
                    return datetime(2026, 9, 17, 10, 0, 0)

            from unittest.mock import patch
            import nepali_datetime as nepali

            with patch("elh.services.attendance.datetime", MockDateTime), \
                 patch.object(nepali.date, "today", return_value=nepali.date(2083, 6, 1)):
                alerts = service.student_attendance_alerts()
                alerts_by_id = {a["student_id"]: a for a in alerts}

                # Student 1 only missed 1 day (today), threshold is 3 -> NOT in alerts
                self.assertNotIn(s1_id, alerts_by_id)

                # Student 2 missed 13 routine days since 2026-09-02, NOT 80+ days
                self.assertIn(s2_id, alerts_by_id)
                self.assertEqual(alerts_by_id[s2_id]["consecutive_days"], 13)
                self.assertIn("No punch for 13 day(s)", alerts_by_id[s2_id]["reason"])

                # Student 4 punched today -> 0 consecutive days, NOT in alerts
                self.assertNotIn(s4_id, alerts_by_id)

                # Student 3 never punched -> missed all routine days since 2083/05/20
                self.assertIn(s3_id, alerts_by_id)
                self.assertGreater(alerts_by_id[s3_id]["consecutive_days"], 5)

                # Review suppression test
                service.record_attendance_alert_review(
                    s2_id, "Suppressed", "Medical excuse", "2083/06/15", None,
                )
                alerts_after_suppress = service.student_attendance_alerts(include_suppressed=False)
                self.assertNotIn(s2_id, {a["student_id"]: a for a in alerts_after_suppress})

                alerts_with_suppressed = service.student_attendance_alerts(include_suppressed=True)
                self.assertIn(s2_id, {a["student_id"]: a for a in alerts_with_suppressed})
