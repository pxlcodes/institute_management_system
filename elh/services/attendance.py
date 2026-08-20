from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime, timedelta

import nepali_datetime as nepali

from elh.core.validation import validate_month
from elh.hardware.attendance.base import AttendanceDevice
from elh.repositories import AttendanceRepository
from elh.core.settings import SettingsService


@dataclass(frozen=True)
class AttendanceSyncResult:
    received: int
    saved: int
    unmapped: int


@dataclass(frozen=True)
class DeviceUserSyncResult:
    received: int
    stored: int


@dataclass(frozen=True)
class DeviceNameSyncResult:
    registered: int
    updated: int
    missing: int


class AttendanceService:
    def __init__(self, repository: AttendanceRepository, device: AttendanceDevice, settings: SettingsService | None = None):
        self.repository = repository
        self.device = device
        self.settings = settings

    def sync(self) -> AttendanceSyncResult:
        events = self.device.fetch_events()
        mappings = self.repository.mappings_for(
            [event.device_user_id for event in events]
        )
        unmapped = sum(
            1 for event in events if event.device_user_id not in mappings
        )
        saved = self.repository.save_events(events, mappings)
        return AttendanceSyncResult(len(events), saved, unmapped)

    def sync_device_users(self) -> DeviceUserSyncResult:
        users = self.device.fetch_users()
        stored = self.repository.save_device_users(users)
        return DeviceUserSyncResult(received=len(users), stored=stored)

    def sync_registered_names_to_device(self) -> DeviceNameSyncResult:
        names = self.repository.registered_device_names()
        updated, missing = self.device.sync_user_names(names)
        # Re-read the device directory so the local cache reflects the actual device state.
        self.repository.save_device_users(self.device.fetch_users())
        return DeviceNameSyncResult(registered=len(names), updated=updated, missing=missing)

    def map_device_user(
        self,
        device_user_id: str,
        person_type: str,
        person_id: int,
        status: str = "Active",
    ) -> None:
        device_user_id = device_user_id.strip()
        person_type = person_type.strip().lower()
        if not device_user_id:
            raise ValueError("Device User ID is required.")
        if person_type not in {"student", "teacher"}:
            raise ValueError("Person type must be Student or Staff.")
        if not self.repository.person_exists(person_type, person_id):
            raise ValueError("The selected person no longer exists.")
        self.repository.save_mapping(device_user_id, person_type, person_id, status)

    def assign_person_device(
        self,
        person_type: str,
        person_id: int,
        device_user_id: str | None,
    ) -> None:
        """Assign one active attendance-device identity to a person."""
        person_type = person_type.strip().lower()
        if person_type not in {"student", "teacher"}:
            raise ValueError("Person type must be Student or Staff.")
        if not self.repository.person_exists(person_type, person_id):
            raise ValueError("The selected person no longer exists.")

        selected_device = (device_user_id or "").strip()
        self.repository.deactivate_person_mappings(
            person_type,
            person_id,
            selected_device or None,
        )
        if selected_device:
            self.repository.save_mapping(
                selected_device,
                person_type,
                person_id,
                "Active",
            )

    def staff_totals(self, start_at: str, end_at: str):
        grouped = defaultdict(lambda: defaultdict(list))
        for row in self.repository.staff_logs(start_at, end_at):
            occurred = row["occurred_at"]
            if not isinstance(occurred, datetime):
                occurred = datetime.fromisoformat(str(occurred))
            grouped[(int(row["person_id"]),row["teacher_name"])][occurred.date()].append(occurred)

        totals = []
        for staff in self.repository.staff_members():
            person_id = int(staff["id"])
            name = staff["teacher_name"]
            days = grouped.get((person_id, name), {})
            punches = sum(len(values) for values in days.values())
            seconds = 0.0
            all_times = []
            for values in days.values():
                values.sort()
                all_times.extend(values)
                if len(values) >= 2:
                    seconds += (values[-1] - values[0]).total_seconds()
            totals.append({
                "person_id": person_id,
                "name": name,
                "staff_type": staff["staff_type"],
                "days": len(days),
                "punches": punches,
                "hours": round(seconds / 3600, 2),
                "first": min(all_times) if all_times else None,
                "last": max(all_times) if all_times else None,
            })
        return sorted(totals, key=lambda item: item["name"].casefold())

    def staff_month_summary(self, staff_id: int, salary_month: str) -> dict:
        """Return optional attendance guidance for a Nepali salary month."""
        start_at, end_at, calendar_days = self._month_range(salary_month, "Salary month")

        summary = next(
            (
                row
                for row in self.staff_totals(start_at, end_at)
                if int(row["person_id"]) == int(staff_id)
            ),
            None,
        )
        if summary is None:
            return {
                "person_id": int(staff_id),
                "days": 0,
                "punches": 0,
                "hours": 0.0,
                "calendar_days": calendar_days,
                "first": None,
                "last": None,
            }
        return {**summary, "calendar_days": calendar_days}

    @staticmethod
    def _month_range(month_value: str, field_name: str) -> tuple[str, str, int]:
        month_value = validate_month(month_value, field_name)
        year, month = (int(part) for part in month_value.split("/"))
        start_bs = nepali.date(year, month, 1)
        next_bs = nepali.date(year + 1, 1, 1) if month == 12 else nepali.date(year, month + 1, 1)
        start_ad = start_bs.to_datetime_date()
        end_ad = next_bs.to_datetime_date() - timedelta(days=1)
        return (
            f"{start_ad.isoformat()} 00:00:00",
            f"{end_ad.isoformat()} 23:59:59",
            (next_bs - start_bs).days,
        )

    def student_month_totals(self, month_value: str) -> list[dict]:
        """Attendance days and hours for every active student in a BS month."""
        start_at, end_at, _days_in_month = self._month_range(month_value, "Attendance month")
        grouped = defaultdict(lambda: defaultdict(list))
        for row in self.repository.student_logs(start_at, end_at):
            occurred = row["occurred_at"]
            if not isinstance(occurred, datetime):
                occurred = datetime.fromisoformat(str(occurred))
            grouped[(int(row["person_id"]), row["student_name"])][occurred.date()].append(occurred)

        totals = []
        for student in self.repository.student_members():
            person_id = int(student["id"])
            name = student["student_name"]
            days = grouped.get((person_id, name), {})
            punches = sum(len(values) for values in days.values())
            seconds = sum(
                (max(values) - min(values)).total_seconds()
                for values in days.values()
                if len(values) >= 2
            )
            totals.append({
                "person_id": person_id,
                "name": name,
                "class_name": student["class_name"] or "",
                "days": len(days),
                "punches": punches,
                "hours": round(seconds / 3600, 2),
            })
        return totals

    def student_attendance_alerts(self) -> list[dict]:
        """Return review alerts for active enrolled students with attendance gaps.

        These are calendar-day indicators; administrators should account for holidays and
        approved leave before taking action.
        """
        consecutive_limit = max(1, self.settings.get_int("attendance_consecutive_absence_days", 3)) if self.settings else 3
        monthly_limit = max(1, self.settings.get_int("attendance_monthly_irregular_days", 5)) if self.settings else 5
        today_ad = datetime.now().date()
        start_at, end_at, _ = self._month_range(nepali.date.today().strftime("%Y/%m"), "Attendance month")
        monthly_punches: dict[int, set] = defaultdict(set)
        for row in self.repository.student_logs(start_at, end_at):
            occurred = row["occurred_at"] if isinstance(row["occurred_at"], datetime) else datetime.fromisoformat(str(row["occurred_at"]))
            monthly_punches[int(row["person_id"])].add(occurred.date())
        rows = self.repository.db.query(
            "SELECT s.id,s.student_name,s.class_name,s.contact,s.parent_name,"
            "GROUP_CONCAT(DISTINCT c.course_name) courses,MIN(e.start_date) enrollment_start,MAX(l.occurred_at) last_seen "
            "FROM students s JOIN enrollments e ON e.student_id=s.id AND e.status='Active' "
            "JOIN courses c ON c.id=e.course_id "
            "LEFT JOIN attendance_logs l ON l.person_type='student' AND l.person_id=s.id "
            "WHERE s.status='Active' GROUP BY s.id,s.student_name,s.class_name,s.contact,s.parent_name"
        )
        review_rows = self.repository.db.query(
            "SELECT r.*,COALESCE(u.display_name,u.username,'') reviewer FROM attendance_alert_reviews r "
            "LEFT JOIN app_users u ON u.id=r.reviewed_by_user_id "
            "WHERE r.id IN (SELECT MAX(id) FROM attendance_alert_reviews GROUP BY student_id)"
        )
        reviews = {int(row["student_id"]): row for row in review_rows}
        alerts = []
        month_start_ad = datetime.fromisoformat(start_at).date()
        for row in rows:
            try:
                start_value = str(row["enrollment_start"])
                if "/" in start_value:
                    start_parts = [int(value) for value in start_value.split("/")]
                    enrollment_start = nepali.date(*start_parts).to_datetime_date()
                else:
                    enrollment_start = datetime.fromisoformat(start_value).date()
            except Exception:
                continue
            if enrollment_start > today_ad:
                continue
            last_seen = row["last_seen"]
            last_date = datetime.fromisoformat(str(last_seen)).date() if last_seen else None
            anchor = max(enrollment_start, last_date) if last_date else enrollment_start
            consecutive_days = max(0, (today_ad - anchor).days)
            relevant_month_start = max(month_start_ad, enrollment_start)
            expected_days = max(0, (today_ad - relevant_month_start).days + 1)
            present_days = len(monthly_punches.get(int(row["id"]), set()))
            missing_days = max(0, expected_days - present_days)
            reasons = []
            if consecutive_days >= consecutive_limit:
                reasons.append(f"No punch for {consecutive_days} day(s)")
            if missing_days >= monthly_limit:
                reasons.append(f"{missing_days} missing day(s) this month")
            if reasons:
                review = reviews.get(int(row["id"]))
                alerts.append({
                    "student_id": int(row["id"]), "student_name": row["student_name"],
                    "class_name": row["class_name"] or "", "contact": row["contact"] or "",
                    "parent_name": row["parent_name"] or "", "courses": row["courses"] or "",
                    "last_seen": last_seen,
                    "consecutive_days": consecutive_days, "monthly_missing_days": missing_days,
                    "reason": "; ".join(reasons),
                    "review_status": review["review_status"] if review else "Not reviewed",
                    "review_note": review["note"] if review else "",
                    "follow_up_date": review["follow_up_date"] if review else "",
                    "reviewer": review["reviewer"] if review else "",
                    "reviewed_at": review["created_at"] if review else None,
                })
        return sorted(alerts, key=lambda row: (-row["consecutive_days"], -row["monthly_missing_days"], row["student_name"].casefold()))

    def record_attendance_alert_review(self, student_id: int, status: str, note: str, follow_up_date: str, user_id: int | None) -> None:
        allowed = {"Contacted", "Monitoring", "Approved Leave", "Left Institution", "No Action Needed"}
        if status not in allowed:
            raise ValueError("Select a valid review status.")
        self.repository.db.execute(
            "INSERT INTO attendance_alert_reviews (student_id,review_status,note,follow_up_date,reviewed_by_user_id) VALUES (?,?,?,?,?)",
            (int(student_id), status, note.strip(), follow_up_date.strip() or None, user_id),
        )

    def students_present_today(self) -> list[dict]:
        now = datetime.now()
        return self.repository.students_present(
            f"{now.date().isoformat()} 00:00:00",
            f"{now.date().isoformat()} 23:59:59",
        )

    def students_with_attendance(self) -> list[dict]:
        """Return active students with at least one imported attendance punch."""
        return self.repository.students_with_attendance()
