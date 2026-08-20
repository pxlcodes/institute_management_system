from __future__ import annotations

from decimal import Decimal

from elh.core.validation import validate_date


class EnrollmentService:
    """Reusable enrollment workflow, including the enrollment notification event."""

    STATUSES = ("Active", "Completed", "Cancelled")

    def __init__(self, db, notifications=None, date_format: str = "%Y/%m/%d"):
        self.db = db
        self.notifications = notifications
        self.date_format = date_format

    def _validated(self, values: tuple) -> tuple:
        (
            student_id,
            course_id,
            level,
            start_date,
            end_date,
            monthly_fee,
            admission_fee,
            discount,
            status,
            remarks,
        ) = values
        if not self.db.query_one("SELECT id FROM students WHERE id=?", (student_id,)):
            raise ValueError("Student was not found.")
        if not self.db.query_one("SELECT id FROM courses WHERE id=?", (course_id,)):
            raise ValueError("Course was not found.")
        clean_status = str(status).strip().title()
        if clean_status not in self.STATUSES:
            raise ValueError("Enrollment status is invalid.")
        start = validate_date(start_date, "Start date", date_format=self.date_format)
        end = validate_date(
            end_date,
            "End date",
            allow_blank=True,
            date_format=self.date_format,
        )
        amounts = tuple(Decimal(str(value)) for value in (monthly_fee, admission_fee, discount))
        if any(value < 0 for value in amounts):
            raise ValueError("Enrollment amounts cannot be negative.")
        return (
            int(student_id),
            int(course_id),
            str(level).strip(),
            start,
            end,
            *(str(value) for value in amounts),
            clean_status,
            str(remarks).strip(),
        )

    def create(self, *values, notify: bool = True) -> int:
        clean = self._validated(tuple(values))
        enrollment_id = self.db.execute(
            "INSERT INTO enrollments "
            "(student_id,course_id,level,start_date,end_date,monthly_fee,"
            "admission_fee,discount,status,remarks) VALUES (?,?,?,?,?,?,?,?,?,?)",
            clean,
        )
        if notify and self.notifications:
            row = self.db.query_one(
                "SELECT s.student_name,s.contact,c.course_name,e.start_date,e.monthly_fee "
                "FROM enrollments e JOIN students s ON s.id=e.student_id "
                "JOIN courses c ON c.id=e.course_id WHERE e.id=?",
                (enrollment_id,),
            )
            self.notifications.notify(
                "enrollment",
                "enrollment",
                enrollment_id,
                row["contact"] or "",
                {
                    "student_name": row["student_name"],
                    "course_name": row["course_name"],
                    "start_date": row["start_date"],
                    "fee": f"{Decimal(str(row['monthly_fee'])):,.2f}",
                },
            )
        return enrollment_id

    def update(self, enrollment_id: int, *values) -> None:
        clean = self._validated(tuple(values))
        self.db.execute(
            "UPDATE enrollments SET student_id=?,course_id=?,level=?,start_date=?,"
            "end_date=?,monthly_fee=?,admission_fee=?,discount=?,status=?,remarks=? "
            "WHERE id=?",
            (*clean, enrollment_id),
        )

    def create_many(self, values: list[tuple]) -> int:
        clean = [self._validated(tuple(row)) for row in values]
        return self.db.executemany(
            "INSERT INTO enrollments "
            "(student_id,course_id,level,start_date,end_date,monthly_fee,"
            "admission_fee,discount,status,remarks) VALUES (?,?,?,?,?,?,?,?,?,?)",
            clean,
        )

    def create_for_students(self, student_ids: list[int], course_id: int, *, level: str,
                            start_date: str, end_date: str, monthly_fee, admission_fee,
                            discount, remarks: str = "") -> tuple[list[int], list[int]]:
        """Create active enrollments while safely skipping an already-active course."""
        created: list[int] = []
        skipped: list[int] = []
        for student_id in dict.fromkeys(int(value) for value in student_ids):
            existing = self.db.query_one(
                "SELECT id FROM enrollments WHERE student_id=? AND course_id=? AND status='Active'",
                (student_id, course_id),
            )
            if existing:
                skipped.append(student_id)
                continue
            created.append(self.create(
                student_id, course_id, level, start_date, end_date, monthly_fee,
                admission_fee, discount, "Active", remarks,
            ))
        return created, skipped

    def create_for_attendance_students(
        self,
        student_ids: list[int],
        course_id: int,
        *,
        end_date: str,
        monthly_fee,
        admission_fee,
        discount,
        remarks: str = "",
    ) -> tuple[list[int], list[int]]:
        """Enroll present students using each student's saved class and joining date."""
        created: list[int] = []
        skipped: list[int] = []
        for student_id in dict.fromkeys(int(value) for value in student_ids):
            student = self.db.query_one(
                "SELECT class_name,joining_date FROM students WHERE id=?", (student_id,)
            )
            if not student:
                raise ValueError("Student was not found.")
            existing = self.db.query_one(
                "SELECT id FROM enrollments WHERE student_id=? AND course_id=? AND status='Active'",
                (student_id, course_id),
            )
            if existing:
                skipped.append(student_id)
                continue
            created.append(self.create(
                student_id,
                course_id,
                str(student["class_name"] or "").strip(),
                str(student["joining_date"] or "").strip(),
                end_date,
                monthly_fee,
                admission_fee,
                discount,
                "Active",
                remarks,
            ))
        return created, skipped

    def delete(self, enrollment_id: int) -> None:
        self.db.execute("DELETE FROM enrollments WHERE id=?", (enrollment_id,))
