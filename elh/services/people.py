from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from elh.core.validation import current_month, normalize_phone, parse_nepali_date, validate_date
from elh.models import Student
from elh.repositories import StudentRepository


class StudentService:
    GENDERS = ("Male", "Female", "Other")
    MAX_PHOTO_BYTES = 3 * 1024 * 1024
    PHOTO_MIME_TYPES = ("image/jpeg", "image/png")
    STATUSES = ("Active", "Inactive", "Archived")

    def __init__(
        self,
        repository: StudentRepository,
        date_format: str = "%Y-%m-%d",
        notifications=None,
    ):
        self.repository = repository
        self.date_format = date_format
        self.notifications = notifications

    def register(self, student: Student) -> int:
        clean = self.validate(student)
        student_id = self.repository.add(clean)
        if self.notifications:
            self.notifications.notify(
                "registration",
                "student",
                student_id,
                clean.contact,
                {
                    "student_name": clean.name,
                    "joining_date": clean.joining_date,
                },
            )
        return student_id

    def register_many(self, students: list[Student]) -> int:
        return self.repository.add_many([self.validate(student) for student in students])

    def update(self, student: Student) -> None:
        self.repository.update(self.validate(student))

    def get(self, student_id: int) -> Student | None:
        return self.repository.get(student_id)

    def delete(self, student_id: int) -> None:
        self.repository.delete(student_id)

    def archive(self, student_id: int) -> None:
        self.repository.set_status(student_id, "Archived")

    def restore(self, student_id: int) -> None:
        """Restore safely as inactive; administration can reactivate when ready."""
        self.repository.set_status(student_id, "Inactive")

    def validate(self, student: Student) -> Student:
        if not student.name.strip():
            raise ValueError("Student name is required.")
        gender = student.gender.strip().title()
        if gender and gender not in self.GENDERS:
            raise ValueError("Gender must be Male, Female, or Other.")
        status = student.status.strip().title() or "Active"
        if status not in self.STATUSES:
            raise ValueError("Status must be Active, Inactive, or Archived.")
        joining_date = validate_date(
            student.joining_date, "Joining date", date_format=self.date_format
        )
        date_of_birth = validate_date(
            student.date_of_birth,
            "Date of birth",
            allow_blank=True,
            date_format=self.date_format,
        )
        if date_of_birth and parse_nepali_date(date_of_birth) >= parse_nepali_date(joining_date):
            raise ValueError("Date of birth must be before the joining date.")
        if student.photo_data:
            if len(student.photo_data) > self.MAX_PHOTO_BYTES:
                raise ValueError("Student photo must be 3 MB or smaller after processing.")
            if student.photo_mime_type not in self.PHOTO_MIME_TYPES:
                raise ValueError("Student photo must be a JPEG or PNG image.")
            signatures = {
                "image/jpeg": (b"\xff\xd8\xff",),
                "image/png": (b"\x89PNG\r\n\x1a\n",),
            }
            if not any(
                student.photo_data.startswith(signature)
                for signature in signatures[student.photo_mime_type]
            ):
                raise ValueError("Student photo content does not match its image type.")
        elif student.photo_mime_type:
            raise ValueError("Photo type cannot be saved without photo data.")
        validated = Student(
            **{**student.__dict__, "name": student.name.strip(),
               "contact": normalize_phone(student.contact),
               "gender": gender, "date_of_birth": date_of_birth,
               "guardian_relationship": student.guardian_relationship.strip(),
               "parent_name": student.parent_name.strip(),
               "joining_date": joining_date, "status": status}
        )
        return validated

    def search(self, text: str = "") -> list[Student]:
        return self.repository.list(text)

    def get_profile(self, student_id: int) -> dict[str, Any]:
        """Fetch comprehensive student profile data across all institutional modules."""
        db = self.repository.db

        # 1. Student Personal & Biographical Record
        row = db.query_one(
            "SELECT s.*, COALESCE(sc.school_name, '') AS school_name, "
            "COALESCE(cl.level_name, s.class_name, '') AS class_level_name, "
            "d.device_user_id, COALESCE(du.device_name, '') AS device_user_name "
            "FROM students s "
            "LEFT JOIN schools sc ON sc.id = s.school_id "
            "LEFT JOIN class_levels cl ON cl.id = s.class_level_id "
            "LEFT JOIN device_user_mappings d ON d.person_type = 'student' AND d.person_id = s.id AND d.status = 'Active' "
            "LEFT JOIN attendance_device_users du ON du.device_user_id = d.device_user_id "
            "WHERE s.id = ?",
            (student_id,),
        )
        if not row:
            raise ValueError("Student was not found.")

        student_data = dict(row)

        # 2. Enrollments (Active & Previous)
        enrollment_rows = db.query(
            "SELECT e.id, e.course_id, c.course_name, COALESCE(c.category, '') AS category, "
            "COALESCE(e.level, '') AS level, e.start_date, e.end_date, "
            "COALESCE(e.monthly_fee, 0) AS monthly_fee, COALESCE(e.admission_fee, 0) AS admission_fee, "
            "COALESCE(e.discount, 0) AS discount, COALESCE(c.billing_type, 'Monthly') AS billing_type, "
            "COALESCE(c.instructor_name, '') AS instructor_name, e.status "
            "FROM enrollments e "
            "JOIN courses c ON c.id = e.course_id "
            "WHERE e.student_id = ? "
            "ORDER BY e.start_date DESC, e.id DESC",
            (student_id,),
        )
        active_enrollments = [dict(r) for r in enrollment_rows if r["status"] == "Active"]
        previous_enrollments = [dict(r) for r in enrollment_rows if r["status"] != "Active"]

        # 3. Financial Due Bills
        bill_rows = db.query(
            "SELECT b.id, b.bill_number, b.billing_period, b.issue_date, b.due_date, "
            "b.subtotal, b.discount, b.total_amount, b.paid_amount, "
            "(b.total_amount - b.paid_amount) AS balance, b.status, c.course_name "
            "FROM due_bills b "
            "JOIN enrollments e ON e.id = b.enrollment_id "
            "JOIN courses c ON c.id = e.course_id "
            "WHERE e.student_id = ? "
            "ORDER BY b.issue_date DESC, b.id DESC",
            (student_id,),
        )
        due_bills = [dict(r) for r in bill_rows]

        # 4. Payment Transactions & Receipts
        txn_rows = db.query(
            "SELECT st.id, st.transaction_date, st.receipt_no, st.particular, "
            "st.payment_amount, st.discount_amount, st.payment_method, "
            "COALESCE(a.account_name, '') AS account_name, COALESCE(st.remarks, '') AS remarks "
            "FROM student_transactions st "
            "LEFT JOIN accounts a ON a.id = st.account_id "
            "WHERE st.student_id = ? AND (st.payment_amount > 0 OR st.discount_amount > 0) "
            "ORDER BY st.transaction_date DESC, st.id DESC",
            (student_id,),
        )
        transactions = [dict(r) for r in txn_rows]

        total_billed = sum((Decimal(str(b["total_amount"] or 0)) for b in due_bills), Decimal("0"))
        total_paid_bills = sum((Decimal(str(b["paid_amount"] or 0)) for b in due_bills), Decimal("0"))
        total_discount = sum((Decimal(str(b["discount"] or 0)) for b in due_bills), Decimal("0"))
        total_due = max(Decimal("0"), total_billed - total_paid_bills)

        # 5. Current Month Attendance
        c_month = current_month()
        now = datetime.now()
        start_date_str = f"{now.strftime('%Y-%m')}-01 00:00:00"
        end_date_str = f"{now.strftime('%Y-%m')}-31 23:59:59"
        try:
            import nepali_datetime as nepali
            if "/" in c_month:
                y, m = (int(p) for p in c_month.split("/"))
                start_bs = nepali.date(y, m, 1)
                next_bs = nepali.date(y + 1, 1, 1) if m == 12 else nepali.date(y, m + 1, 1)
                start_date_str = f"{start_bs.to_datetime_date().isoformat()} 00:00:00"
                end_date_str = f"{(next_bs.to_datetime_date() - timedelta(days=1)).isoformat()} 23:59:59"
        except Exception:
            pass

        attendance_logs = db.query(
            "SELECT occurred_at, device_user_id, event_type "
            "FROM attendance_logs "
            "WHERE person_type = 'student' AND person_id = ? "
            "AND occurred_at BETWEEN ? AND ? "
            "ORDER BY occurred_at ASC",
            (student_id, start_date_str, end_date_str),
        )

        from collections import defaultdict
        daily_punches: dict[str, list[str]] = defaultdict(list)
        for al in attendance_logs:
            occ = al["occurred_at"]
            if isinstance(occ, datetime):
                d_str = occ.date().isoformat()
                t_str = occ.strftime("%H:%M:%S")
            else:
                occ_str = str(occ)
                d_str = occ_str[:10]
                t_str = occ_str[11:19]
            daily_punches[d_str].append(t_str)

        recent_attendance = []
        for d_str in sorted(daily_punches.keys(), reverse=True):
            times = daily_punches[d_str]
            first_in = times[0] if times else ""
            last_out = times[-1] if len(times) > 1 else first_in
            recent_attendance.append({
                "date": d_str,
                "first_in": first_in,
                "last_out": last_out,
                "punch_count": len(times),
            })

        life_row = db.query_one(
            "SELECT COUNT(DISTINCT DATE(occurred_at)) AS total_days, "
            "COUNT(*) AS total_punches, "
            "MIN(occurred_at) AS first_seen, "
            "MAX(occurred_at) AS last_seen "
            "FROM attendance_logs WHERE person_type='student' AND person_id=?",
            (student_id,),
        )

        # 6. Certificates Earned
        cert_rows = db.query(
            "SELECT cc.id, cc.certificate_number, cc.certify_date, "
            "cc.course_name_snapshot, cc.course_start_date, cc.course_end_date, "
            "cc.instructor_name, cc.principal_name, cc.pdf_path "
            "FROM course_certificates cc "
            "JOIN enrollments e ON e.id = cc.enrollment_id "
            "WHERE e.student_id = ? "
            "ORDER BY cc.certify_date DESC, cc.id DESC",
            (student_id,),
        )
        certificates = [
            {
                "id": r["id"],
                "certificate_number": r["certificate_number"],
                "certify_date": r["certify_date"],
                "course_name_snapshot": r["course_name_snapshot"],
                "course_start_date": r["course_start_date"],
                "course_end_date": r["course_end_date"],
                "instructor_name": r["instructor_name"],
                "status": "Issued" if r["pdf_path"] else "Recorded",
            }
            for r in cert_rows
        ]

        # 7. Recent SMS History
        sms_rows = db.query(
            "SELECT event_key, recipient, message_text, status, response_message, created_at "
            "FROM sms_delivery_log "
            "WHERE recipient = ? "
            "ORDER BY id DESC LIMIT 5",
            (student_data.get("contact") or "",),
        )
        recent_sms = [dict(r) for r in sms_rows]

        return {
            "student": student_data,
            "active_enrollments": active_enrollments,
            "previous_enrollments": previous_enrollments,
            "financials": {
                "total_billed": float(total_billed),
                "total_paid": float(total_paid_bills),
                "total_discount": float(total_discount),
                "total_due": float(total_due),
                "due_bills": due_bills,
                "transactions": transactions,
            },
            "attendance": {
                "current_month": c_month,
                "days_present_month": len(daily_punches),
                "total_punches_month": len(attendance_logs),
                "recent_punches": recent_attendance,
                "lifetime_days": int(life_row["total_days"] or 0) if life_row else 0,
                "lifetime_punches": int(life_row["total_punches"] or 0) if life_row else 0,
                "first_seen": str(life_row["first_seen"] or "") if life_row else "",
                "last_seen": str(life_row["last_seen"] or "") if life_row else "",
            },
            "certificates": certificates,
            "recent_sms": recent_sms,
        }
