from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime, timedelta

import nepali_datetime as nepali

from elh.core.validation import validate_date, validate_month
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

    def mark_manual_present(
        self, person_type: str, person_id: int, attendance_date: str, attendance_time: str, reason: str,
    ) -> bool:
        """Correct a missed device punch while retaining its manual source and reason."""
        person_type = person_type.strip().lower()
        if person_type not in {"student", "teacher"}:
            raise ValueError("Person type must be Student or Staff.")
        if not self.repository.person_exists(person_type, int(person_id)):
            raise ValueError("The selected person no longer exists.")
        if not reason.strip():
            raise ValueError("A reason is required for a manual attendance correction.")
        attendance_date = validate_date(attendance_date, "Attendance date")
        try:
            parsed_time = datetime.strptime(attendance_time.strip().upper(), "%I:%M %p").time()
        except ValueError as exc:
            raise ValueError("Select a valid attendance time.") from exc
        year, month, day = (int(value) for value in attendance_date.split("/"))
        occurred_at = datetime.combine(nepali.date(year, month, day).to_datetime_date(), parsed_time)
        return self.repository.save_manual_present(person_type, int(person_id), occurred_at, reason)

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

    def teacher_period_summary(self, staff_id: int, salary_month: str) -> dict:
        """Calculate scheduled routine classes, attendance in assigned classes, and proxy assignments."""
        start_at, end_at, calendar_days = self._month_range(salary_month, "Salary month")
        start_date = datetime.fromisoformat(start_at).date()
        end_date = datetime.fromisoformat(end_at).date()

        try:
            calendar_events = self._calendar_events_between(start_date, end_date)
        except Exception:
            calendar_events = []

        try:
            routine_rows = [dict(r) for r in self.repository.db.query(
                "SELECT r.id, r.class_name, r.day_of_week, r.period_label, r.subject_name, "
                "r.course_id, r.start_time, r.end_time, "
                "p.effective_from, p.effective_to "
                "FROM class_routines r "
                "LEFT JOIN routine_plans p ON p.id = r.routine_plan_id "
                "WHERE r.teacher_id = ? AND r.status = 'Active'",
                (int(staff_id),),
            )]
        except Exception:
            routine_rows = []

        present_dates_ad: set = set()
        try:
            attendance_rows = [dict(r) for r in self.repository.db.query(
                "SELECT occurred_at FROM attendance_logs "
                "WHERE person_type = 'teacher' AND person_id = ? "
                "AND occurred_at BETWEEN ? AND ?",
                (int(staff_id), start_at, end_at),
            )]
            for row in attendance_rows:
                occ = row.get("occurred_at")
                if isinstance(occ, datetime):
                    present_dates_ad.add(occ.date())
                elif occ:
                    try:
                        present_dates_ad.add(datetime.fromisoformat(str(occ).replace(" ", "T")).date())
                    except Exception:
                        pass
        except Exception:
            present_dates_ad = set()

        proxy_rows = []
        try:
            proxy_rows = [dict(r) for r in self.repository.db.query(
                "SELECT p.id, p.routine_id, p.class_date, p.original_teacher_id, p.proxy_teacher_id, "
                "p.status, p.proxy_status, p.reason, p.leave_type, "
                "r.class_name, r.subject_name, r.period_label, r.start_time, r.end_time, "
                "COALESCE(ot.teacher_name, 'Teacher') AS original_teacher_name, "
                "COALESCE(pt.teacher_name, 'Substitute') AS proxy_teacher_name "
                "FROM proxy_class_requests p "
                "JOIN class_routines r ON r.id = p.routine_id "
                "LEFT JOIN teachers ot ON ot.id = p.original_teacher_id "
                "LEFT JOIN teachers pt ON pt.id = p.proxy_teacher_id "
                "WHERE (p.original_teacher_id = ? OR p.proxy_teacher_id = ?) "
                "AND p.status = 'Approved' "
                "AND (p.proxy_status != 'Declined' OR p.proxy_status IS NULL)",
                (int(staff_id), int(staff_id)),
            )]
        except Exception:
            proxy_rows = []

        year, month = (int(part) for part in salary_month.split("/"))
        month_prefix_1 = f"{year:04d}/{month:02d}/"
        month_prefix_2 = f"{year:04d}/{month}/"

        proxy_relieved_map: dict = {}
        proxy_relieved_list: list[dict] = []
        proxy_taken_list: list[dict] = []

        for p in proxy_rows:
            raw_date = p.get("class_date")
            ad_date = None
            bs_date = ""
            ad_iso = ""

            if isinstance(raw_date, datetime):
                ad_date = raw_date.date()
                bs_date = self._business_date_from_ad(ad_date)
                ad_iso = ad_date.isoformat()
            elif hasattr(raw_date, "year") and hasattr(raw_date, "month") and hasattr(raw_date, "day") and not isinstance(raw_date, str):
                ad_date = raw_date
                bs_date = self._business_date_from_ad(ad_date)
                ad_iso = ad_date.isoformat()
            elif raw_date:
                str_val = str(raw_date).strip().split("T")[0].split(" ")[0]
                if "/" in str_val:
                    bs_date = str_val
                    try:
                        parts = [int(x) for x in bs_date.split("/")[:3]]
                        ad_date = nepali.date(*parts).to_datetime_date()
                        ad_iso = ad_date.isoformat()
                    except Exception:
                        ad_date = None
                        ad_iso = ""
                elif "-" in str_val:
                    try:
                        ad_date = datetime.fromisoformat(str_val).date()
                        ad_iso = ad_date.isoformat()
                        bs_date = self._business_date_from_ad(ad_date)
                    except Exception:
                        ad_date = None
                        ad_iso = str_val
                        bs_date = ""

            is_in_month = False
            if bs_date:
                if bs_date.startswith(month_prefix_1) or bs_date.startswith(month_prefix_2):
                    is_in_month = True
                else:
                    try:
                        parts = [int(x) for x in bs_date.split("/")[:3]]
                        if parts[0] == year and parts[1] == month:
                            is_in_month = True
                    except Exception:
                        pass
            if not is_in_month and ad_date is not None:
                if start_date <= ad_date <= end_date:
                    is_in_month = True

            if not is_in_month:
                continue

            orig_id = p.get("original_teacher_id")
            proxy_id = p.get("proxy_teacher_id")
            routine_id = p.get("routine_id")
            display_date = bs_date or ad_iso or str(raw_date or "")

            if orig_id is not None and int(orig_id) == int(staff_id):
                if bs_date:
                    proxy_relieved_map[(routine_id, bs_date)] = p
                if ad_iso:
                    proxy_relieved_map[(routine_id, ad_iso)] = p
                if ad_date is not None:
                    proxy_relieved_map[(routine_id, ad_date)] = p
                if raw_date:
                    proxy_relieved_map[(routine_id, str(raw_date))] = p

                proxy_relieved_list.append({
                    "id": p["id"],
                    "routine_id": routine_id,
                    "class_date": display_date,
                    "class_date_bs": bs_date,
                    "class_date_ad": ad_iso,
                    "class_name": p.get("class_name") or "",
                    "subject_name": p.get("subject_name") or "",
                    "period_label": p.get("period_label") or "",
                    "start_time": p.get("start_time") or "",
                    "end_time": p.get("end_time") or "",
                    "proxy_teacher_name": p.get("proxy_teacher_name") or "Substitute",
                    "reason": p.get("reason") or "",
                    "leave_type": p.get("leave_type") or "Absent",
                })

            if proxy_id is not None and int(proxy_id) == int(staff_id):
                proxy_taken_list.append({
                    "id": p["id"],
                    "routine_id": routine_id,
                    "class_date": display_date,
                    "class_date_bs": bs_date,
                    "class_date_ad": ad_iso,
                    "class_name": p.get("class_name") or "",
                    "subject_name": p.get("subject_name") or "",
                    "period_label": p.get("period_label") or "",
                    "start_time": p.get("start_time") or "",
                    "end_time": p.get("end_time") or "",
                    "original_teacher_name": p.get("original_teacher_name") or "Regular Teacher",
                    "reason": p.get("reason") or "",
                    "leave_type": p.get("leave_type") or "Absent",
                })

        scheduled_classes = 0
        attended_classes = 0
        absent_classes = 0
        relieved_classes = 0
        routine_days: list[str] = []

        for offset in range((end_date - start_date).days + 1):
            current_date = start_date + timedelta(days=offset)
            day_name = self._day_name(current_date)
            business_date = self._business_date_from_ad(current_date)

            global_closure = any(
                event["event_type"] in {"Holiday", "Closure"}
                and event["course_id"] is None
                and event["start_date"] <= business_date <= event["end_date"]
                for event in calendar_events
            )
            if global_closure:
                continue

            for r in routine_rows:
                if r["day_of_week"] != day_name:
                    continue
                if r.get("effective_from") and r["effective_from"] > business_date:
                    continue
                if r.get("effective_to") and r["effective_to"] <= business_date:
                    continue

                if r.get("course_id"):
                    course_closure = any(
                        event["event_type"] in {"Holiday", "Closure"}
                        and event["course_id"] == r["course_id"]
                        and event["start_date"] <= business_date <= event["end_date"]
                        for event in calendar_events
                    )
                    if course_closure:
                        continue

                scheduled_classes += 1
                routine_days.append(day_name)

                # Check if relieved by proxy
                is_relieved = (
                    (r["id"], business_date) in proxy_relieved_map
                    or (r["id"], current_date) in proxy_relieved_map
                    or (r["id"], current_date.isoformat()) in proxy_relieved_map
                )
                if is_relieved:
                    relieved_classes += 1
                elif current_date in present_dates_ad:
                    attended_classes += 1
                else:
                    absent_classes += 1

        proxy_classes_taken = len(proxy_taken_list)
        proxy_classes_relieved = len(proxy_relieved_list)
        payable_classes = attended_classes + proxy_classes_taken

        return {
            "scheduled_classes": scheduled_classes,
            "attended_classes": attended_classes,
            "absent_classes": absent_classes,
            "relieved_classes": relieved_classes,
            "proxy_classes_taken": proxy_classes_taken,
            "proxy_classes_relieved": proxy_classes_relieved,
            "payable_classes": payable_classes,
            "proxy_taken_list": proxy_taken_list,
            "proxy_relieved_list": proxy_relieved_list,
            "routine_days": sorted(set(routine_days)),
            "calendar_days": calendar_days,
        }

    teacher_class_attendance_summary = teacher_period_summary

    @staticmethod
    def _day_name(value) -> str:
        return ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")[value.weekday()]

    def _working_dates_for_class(
        self, class_name: str, start_date, end_date, routine_rows: list[dict] | None = None,
        course_ids: set[int] | None = None,
    ) -> list:
        if not class_name or end_date < start_date:
            return []
        if routine_rows is None:
            routine_rows = self.repository.db.query(
                "SELECT r.day_of_week,r.course_id,p.effective_from,p.effective_to FROM class_routines r "
                "JOIN routine_plans p ON p.id=r.routine_plan_id "
                "WHERE r.class_name=? AND r.status='Active'",
                (class_name,),
            )
        calendar_events = self._calendar_events_between(start_date, end_date, course_ids)
        working_dates = []
        for offset in range((end_date - start_date).days + 1):
            current_date = start_date + timedelta(days=offset)
            business_date = self._business_date_from_ad(current_date)
            if routine_rows:
                scheduled_rows = [row for row in routine_rows if (
                    row["day_of_week"] == self._day_name(current_date)
                    and row["effective_from"] <= business_date
                    and (not row["effective_to"] or row["effective_to"] > business_date)
                )]
                if not scheduled_rows:
                    continue
            else:
                scheduled_rows = []
            global_closure = any(
                event["event_type"] in {"Holiday", "Closure"}
                and event["course_id"] is None
                and event["start_date"] <= business_date <= event["end_date"]
                for event in calendar_events
            )
            if global_closure:
                continue
            closed_courses = {
                int(event["course_id"]) for event in calendar_events
                if event["event_type"] in {"Holiday", "Closure"}
                and event["course_id"] is not None
                and event["start_date"] <= business_date <= event["end_date"]
            }
            if not routine_rows or course_ids is None or any(
                row["course_id"] is None or int(row["course_id"]) not in closed_courses
                for row in scheduled_rows
            ):
                working_dates.append(current_date)
        return working_dates

    def _calendar_events_between(self, start_date, end_date, course_ids: set[int] | None = None) -> list[dict]:
        """Return active global or applicable course calendar events overlapping an AD range."""
        start_bs = self._business_date_from_ad(start_date)
        end_bs = self._business_date_from_ad(end_date)
        sql = (
            "SELECT event.id,event.event_name,event.event_type,event.course_id,event.start_date,event.end_date,"
            "event.status,event.remarks,c.course_name FROM academic_calendar_events event "
            "LEFT JOIN courses c ON c.id=event.course_id WHERE event.status='Active' "
            "AND event.start_date<=? AND event.end_date>=?"
        )
        params: list = [end_bs, start_bs]
        if course_ids is not None:
            if course_ids:
                placeholders = ",".join("?" for _ in course_ids)
                sql += f" AND (event.course_id IS NULL OR event.course_id IN ({placeholders}))"
                params.extend(sorted(course_ids))
            else:
                sql += " AND event.course_id IS NULL"
        return self.repository.db.query(sql + " ORDER BY event.start_date,event.id", tuple(params))

    @staticmethod
    def _is_calendar_closed(business_date: str, calendar_events: list[dict]) -> bool:
        """Holiday and closure events override an otherwise scheduled routine day."""
        return any(
            event["event_type"] in {"Holiday", "Closure"}
            and event["start_date"] <= business_date <= event["end_date"]
            for event in calendar_events
        )

    def academic_calendar_month(self, month_value: str) -> list[dict]:
        """Provide a BS-month calendar for UIs without duplicating date conversion."""
        month_value = validate_month(month_value, "Calendar month")
        year, month = (int(part) for part in month_value.split("/"))
        first = nepali.date(year, month, 1)
        next_month = nepali.date(year + 1, 1, 1) if month == 12 else nepali.date(year, month + 1, 1)
        events = self._calendar_events_between(
            first.to_datetime_date(), next_month.to_datetime_date() - timedelta(days=1)
        )
        days = []
        for day in range(1, (next_month - first).days + 1):
            value = nepali.date(year, month, day)
            business_date = value.strftime("%Y/%m/%d")
            day_events = [dict(event) for event in events if event["start_date"] <= business_date <= event["end_date"]]
            days.append({
                "date": business_date,
                "day": day,
                "day_name": self._day_name(value.to_datetime_date()),
                "closed": self._is_calendar_closed(business_date, events),
                "events": day_events,
            })
        return days

    @staticmethod
    def _business_date_from_ad(value) -> str:
        return nepali.date.from_datetime_date(value).strftime("%Y/%m/%d")

    @staticmethod
    def _business_date_to_ad(value: str):
        if "/" in value:
            return nepali.date(*(int(part) for part in value.split("/"))).to_datetime_date()
        return datetime.fromisoformat(value).date()

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

    def student_attendance_alerts(self, include_suppressed: bool = False) -> list[dict]:
        """Return review alerts for active enrolled students with attendance gaps.

        Students are evaluated only on active routine days for their saved class/level.
        """
        consecutive_limit = max(1, self.settings.get_int("attendance_consecutive_absence_days", 3)) if self.settings else 3
        monthly_limit = max(1, self.settings.get_int("attendance_monthly_irregular_days", 5)) if self.settings else 5
        today_ad = datetime.now().date()
        today_bs = nepali.date.today().strftime("%Y/%m/%d")
        start_at, end_at, _ = self._month_range(nepali.date.today().strftime("%Y/%m"), "Attendance month")
        month_start_ad = datetime.fromisoformat(start_at).date()
        month_end_ad = datetime.fromisoformat(end_at).date()
        monthly_punches: dict[int, set] = defaultdict(set)
        all_punches: dict[int, set] = defaultdict(set)
        for row in self.repository.student_punch_dates():
            occurred = row["occurred_at"] if isinstance(row["occurred_at"], datetime) else datetime.fromisoformat(str(row["occurred_at"]))
            punch_date = occurred.date()
            sid = int(row["person_id"])
            all_punches[sid].add(punch_date)
            if month_start_ad <= punch_date <= month_end_ad:
                monthly_punches[sid].add(punch_date)
        rows = self.repository.db.query(
            "SELECT s.id,s.student_name,s.class_name,s.contact,s.parent_name,"
            "GROUP_CONCAT(DISTINCT c.course_name) courses,GROUP_CONCAT(DISTINCT e.course_id) course_ids,"
            "MIN(e.start_date) enrollment_start,MAX(l.occurred_at) last_seen "
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
        routine_rows = self.repository.db.query(
            "SELECT r.class_name,r.day_of_week,r.course_id,p.effective_from,p.effective_to "
            "FROM class_routines r JOIN routine_plans p ON p.id=r.routine_plan_id "
            "WHERE r.status='Active'"
        )
        routines_by_class: dict[str, list[dict]] = defaultdict(list)
        for routine in routine_rows:
            routines_by_class[str(routine["class_name"] or "")].append(routine)
        alerts = []
        for row in rows:
            try:
                enrollment_start = self._business_date_to_ad(str(row["enrollment_start"]))
            except Exception:
                continue
            if enrollment_start > today_ad:
                continue
            relevant_month_start = max(month_start_ad, enrollment_start)
            course_ids = {int(value) for value in str(row["course_ids"] or "").split(",") if value}
            working_dates = self._working_dates_for_class(
                row["class_name"] or "", enrollment_start, today_ad,
                routines_by_class.get(row["class_name"] or "", []),
                course_ids,
            )
            if not working_dates:
                continue
            sid = int(row["id"])
            student_punches = all_punches.get(sid, set())
            monthly_present = monthly_punches.get(sid, set())
            monthly_working = [day for day in working_dates if day >= relevant_month_start]
            missing_days = sum(day not in monthly_present for day in monthly_working)

            last_seen = row["last_seen"]
            last_seen_date = None
            if last_seen:
                if isinstance(last_seen, datetime):
                    last_seen_date = last_seen.date()
                else:
                    try:
                        last_seen_date = datetime.fromisoformat(str(last_seen)).date()
                    except Exception:
                        pass
                if last_seen_date and last_seen_date < enrollment_start:
                    last_seen_date = None

            consecutive_days = 0
            for day in reversed(working_dates):
                if day in student_punches or (last_seen_date and day <= last_seen_date):
                    break
                consecutive_days += 1
            reasons = []
            if consecutive_days >= consecutive_limit:
                reasons.append(f"No punch for {consecutive_days} day(s)")
            if missing_days >= monthly_limit:
                reasons.append(f"{missing_days} missing day(s) this month")
            if reasons:
                review = reviews.get(int(row["id"]))
                review_status = review["review_status"] if review else "Not reviewed"
                follow_up_date = review["follow_up_date"] if review else ""
                suppressed = (
                    review_status == "Suppressed"
                    and (not follow_up_date or str(follow_up_date) >= today_bs)
                )
                if suppressed and not include_suppressed:
                    continue
                if review_status == "Suppressed" and not suppressed:
                    review_status = "Suppression expired"
                last_seen = row["last_seen"]
                alerts.append({
                    "student_id": int(row["id"]), "student_name": row["student_name"],
                    "class_name": row["class_name"] or "", "contact": row["contact"] or "",
                    "parent_name": row["parent_name"] or "", "courses": row["courses"] or "",
                    "last_seen": last_seen,
                    "consecutive_days": consecutive_days, "monthly_missing_days": missing_days,
                    "reason": "; ".join(reasons),
                    "review_status": review_status,
                    "review_note": review["note"] if review else "",
                    "follow_up_date": follow_up_date,
                    "reviewer": review["reviewer"] if review else "",
                    "reviewed_at": review["created_at"] if review else None,
                    "suppressed": suppressed,
                })
        return sorted(alerts, key=lambda row: (-row["consecutive_days"], -row["monthly_missing_days"], row["student_name"].casefold()))

    def record_attendance_alert_review(self, student_id: int, status: str, note: str, follow_up_date: str, user_id: int | None) -> None:
        allowed = {
            "Contacted", "Monitoring", "Approved Leave", "Left Institution",
            "No Action Needed", "Suppressed",
        }
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

    def students_absent_today(self) -> list[dict]:
        """Active enrollments that have no attendance punch today.

        Enrollments beginning in the future are omitted, regardless of whether their
        stored business date is Nepali BS or ISO/AD.
        """
        today_ad = datetime.now().date()
        rows = self.repository.students_absent(
            f"{today_ad.isoformat()} 00:00:00",
            f"{today_ad.isoformat()} 23:59:59",
        )
        absent = []
        for row in rows:
            try:
                started = self._business_date_to_ad(str(row["enrollment_start"]))
            except Exception:
                continue
            course_ids = {int(value) for value in str(row["course_ids"] or "").split(",") if value}
            if started <= today_ad and self._working_dates_for_class(
                row["class_name"] or "", today_ad, today_ad, course_ids=course_ids
            ):
                absent.append(row)
        return absent

    def students_with_attendance(self) -> list[dict]:
        """Return active students with at least one imported attendance punch."""
        return self.repository.students_with_attendance()

    def students_punched_not_enrolled(self, start_at: str | None = None, end_at: str | None = None) -> list[dict]:
        return self.repository.students_punched_not_enrolled(start_at, end_at)
