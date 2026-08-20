from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime, timedelta

import nepali_datetime as nepali

from elh.core.validation import validate_month
from elh.hardware.attendance.base import AttendanceDevice
from elh.repositories import AttendanceRepository


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
    def __init__(self, repository: AttendanceRepository, device: AttendanceDevice):
        self.repository = repository
        self.device = device

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

    def students_present_today(self) -> list[dict]:
        now = datetime.now()
        return self.repository.students_present(
            f"{now.date().isoformat()} 00:00:00",
            f"{now.date().isoformat()} 23:59:59",
        )

    def students_with_attendance(self) -> list[dict]:
        """Return active students with at least one imported attendance punch."""
        return self.repository.students_with_attendance()
