"""Repository for Subjects and Student Subject assignments."""

from __future__ import annotations

from typing import Iterable, Sequence

from .protocols import DatabaseGateway
from elh.models.academics import StudentSubject, Subject, TeacherSubject


class SubjectRepository:
    def __init__(self, db: DatabaseGateway):
        self.db = db

    def list_subjects(
        self,
        status: str | None = None,
        subject_type: str | None = None,
        class_level_id: int | None = None,
    ) -> list[Subject]:
        clauses = ["1=1"]
        params = []
        if status:
            clauses.append("s.status = ?")
            params.append(status)
        if subject_type:
            clauses.append("s.subject_type = ?")
            params.append(subject_type)
        if class_level_id:
            clauses.append("(s.class_level_id = ? OR s.class_level_id IS NULL)")
            params.append(class_level_id)

        sql = f"""
            SELECT s.*, cl.level_name as resolved_class_name
            FROM subjects s
            LEFT JOIN class_levels cl ON cl.id = s.class_level_id
            WHERE {' AND '.join(clauses)}
            ORDER BY s.subject_type DESC, s.subject_name ASC
        """
        rows = self.db.query(sql, tuple(params))
        result = []
        for raw in rows:
            r = dict(raw)
            result.append(
                Subject(
                    id=int(r["id"]),
                    subject_code=r["subject_code"],
                    subject_name=r["subject_name"],
                    subject_type=r.get("subject_type") or "Optional",
                    class_level_id=int(r["class_level_id"]) if r.get("class_level_id") else None,
                    class_name=r.get("resolved_class_name") or r.get("class_name"),
                    status=r.get("status") or "Active",
                    remarks=r.get("remarks") or "",
                    created_at=str(r.get("created_at") or ""),
                )
            )
        return result

    def get(self, subject_id: int) -> Subject | None:
        raw = self.db.query_one(
            """
            SELECT s.*, cl.level_name as resolved_class_name
            FROM subjects s
            LEFT JOIN class_levels cl ON cl.id = s.class_level_id
            WHERE s.id = ?
            """,
            (subject_id,),
        )
        if not raw:
            return None
        row = dict(raw)
        return Subject(
            id=int(row["id"]),
            subject_code=row["subject_code"],
            subject_name=row["subject_name"],
            subject_type=row.get("subject_type") or "Optional",
            class_level_id=int(row["class_level_id"]) if row.get("class_level_id") else None,
            class_name=row.get("resolved_class_name") or row.get("class_name"),
            status=row.get("status") or "Active",
            remarks=row.get("remarks") or "",
            created_at=str(row.get("created_at") or ""),
        )

    def get_by_code(self, subject_code: str) -> Subject | None:
        row = self.db.query_one("SELECT * FROM subjects WHERE subject_code = ?", (subject_code.strip(),))
        if not row:
            return None
        return self.get(int(row["id"]))

    def create(self, subject: Subject) -> int:
        return self.db.execute(
            """
            INSERT INTO subjects (subject_code, subject_name, subject_type, class_level_id, class_name, status, remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subject.subject_code.strip(),
                subject.subject_name.strip(),
                subject.subject_type.strip(),
                subject.class_level_id,
                subject.class_name.strip() if subject.class_name else None,
                subject.status,
                subject.remarks.strip(),
            ),
        )

    def update(self, subject: Subject) -> None:
        if subject.id is None:
            raise ValueError("Subject ID is required for update.")
        self.db.execute(
            """
            UPDATE subjects
            SET subject_code = ?, subject_name = ?, subject_type = ?, class_level_id = ?, class_name = ?, status = ?, remarks = ?
            WHERE id = ?
            """,
            (
                subject.subject_code.strip(),
                subject.subject_name.strip(),
                subject.subject_type.strip(),
                subject.class_level_id,
                subject.class_name.strip() if subject.class_name else None,
                subject.status,
                subject.remarks.strip(),
                subject.id,
            ),
        )

    def delete(self, subject_id: int) -> None:
        self.db.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))

    # -----------------------------------------------------------------------
    # Student Subject Assignments
    # -----------------------------------------------------------------------
    def get_student_subjects(self, student_id: int, status: str | None = None) -> list[StudentSubject]:
        clauses = ["ss.student_id = ?"]
        params: list[object] = [student_id]
        if status:
            clauses.append("ss.status = ?")
            params.append(status)

        sql = f"""
            SELECT ss.*, s.subject_code, s.subject_name, s.subject_type,
                   st.student_name, st.class_name
            FROM student_subjects ss
            JOIN subjects s ON s.id = ss.subject_id
            JOIN students st ON st.id = ss.student_id
            WHERE {' AND '.join(clauses)}
            ORDER BY ss.enrollment_type DESC, s.subject_name ASC
        """
        rows = self.db.query(sql, tuple(params))
        result = []
        for raw in rows:
            r = dict(raw)
            result.append(
                StudentSubject(
                    id=int(r["id"]),
                    student_id=int(r["student_id"]),
                    subject_id=int(r["subject_id"]),
                    enrollment_type=r.get("enrollment_type") or "Optional",
                    assigned_date=r.get("assigned_date"),
                    status=r.get("status") or "Active",
                    remarks=r.get("remarks") or "",
                    created_at=str(r.get("created_at") or ""),
                    subject_code=r["subject_code"],
                    subject_name=r["subject_name"],
                    subject_type=r.get("subject_type") or "Optional",
                    student_name=r["student_name"],
                    class_name=r.get("class_name") or "",
                )
            )
        return result

    def assign_student_subject(
        self,
        student_id: int,
        subject_id: int,
        enrollment_type: str = "Optional",
        assigned_date: str | None = None,
        remarks: str = "",
    ) -> int:
        existing = self.db.query_one(
            "SELECT id, status FROM student_subjects WHERE student_id = ? AND subject_id = ?",
            (student_id, subject_id),
        )
        if existing:
            self.db.execute(
                "UPDATE student_subjects SET status = 'Active', enrollment_type = ?, assigned_date = ?, remarks = ? WHERE id = ?",
                (enrollment_type, assigned_date, remarks.strip(), existing["id"]),
            )
            return int(existing["id"])

        return self.db.execute(
            """
            INSERT INTO student_subjects (student_id, subject_id, enrollment_type, assigned_date, status, remarks)
            VALUES (?, ?, ?, ?, 'Active', ?)
            """,
            (student_id, subject_id, enrollment_type, assigned_date, remarks.strip()),
        )

    def remove_student_subject(self, student_id: int, subject_id: int) -> None:
        self.db.execute(
            "DELETE FROM student_subjects WHERE student_id = ? AND subject_id = ?",
            (student_id, subject_id),
        )

    def batch_assign(
        self,
        student_ids: Sequence[int],
        subject_id: int,
        enrollment_type: str = "Optional",
        assigned_date: str | None = None,
        remarks: str = "",
    ) -> int:
        count = 0
        for sid in student_ids:
            self.assign_student_subject(sid, subject_id, enrollment_type, assigned_date, remarks)
            count += 1
        return count

    # -----------------------------------------------------------------------
    # Teacher Subject Assignments
    # -----------------------------------------------------------------------
    def get_teacher_subjects(self, teacher_id: int, status: str | None = None) -> list[TeacherSubject]:
        clauses = ["ts.teacher_id = ?"]
        params: list[object] = [teacher_id]
        if status:
            clauses.append("ts.status = ?")
            params.append(status)

        sql = f"""
            SELECT ts.*, s.subject_code, s.subject_name, s.subject_type,
                   t.teacher_name
            FROM teacher_subjects ts
            JOIN subjects s ON s.id = ts.subject_id
            JOIN teachers t ON t.id = ts.teacher_id
            WHERE {' AND '.join(clauses)}
            ORDER BY s.subject_name ASC
        """
        rows = self.db.query(sql, tuple(params))
        result = []
        for raw in rows:
            r = dict(raw)
            result.append(
                TeacherSubject(
                    id=int(r["id"]),
                    teacher_id=int(r["teacher_id"]),
                    subject_id=int(r["subject_id"]),
                    status=r.get("status") or "Active",
                    remarks=r.get("remarks") or "",
                    created_at=str(r.get("created_at") or ""),
                    subject_code=r["subject_code"],
                    subject_name=r["subject_name"],
                    subject_type=r.get("subject_type") or "Optional",
                    teacher_name=r["teacher_name"],
                )
            )
        return result

    def assign_teacher_subject(
        self,
        teacher_id: int,
        subject_id: int,
        remarks: str = "",
        sync_text: bool = True,
    ) -> int:
        existing = self.db.query_one(
            "SELECT id, status FROM teacher_subjects WHERE teacher_id = ? AND subject_id = ?",
            (teacher_id, subject_id),
        )
        if existing:
            self.db.execute(
                "UPDATE teacher_subjects SET status = 'Active', remarks = ? WHERE id = ?",
                (remarks.strip(), existing["id"]),
            )
            record_id = int(existing["id"])
        else:
            record_id = self.db.execute(
                """
                INSERT INTO teacher_subjects (teacher_id, subject_id, status, remarks)
                VALUES (?, ?, 'Active', ?)
                """,
                (teacher_id, subject_id, remarks.strip()),
            )

        if sync_text:
            self.sync_teacher_subject_text(teacher_id)
        return record_id

    def remove_teacher_subject(self, teacher_id: int, subject_id: int, sync_text: bool = True) -> None:
        self.db.execute(
            "DELETE FROM teacher_subjects WHERE teacher_id = ? AND subject_id = ?",
            (teacher_id, subject_id),
        )
        if sync_text:
            self.sync_teacher_subject_text(teacher_id)

    def set_teacher_subjects(self, teacher_id: int, subject_ids: Iterable[int]) -> list[int]:
        sids = {int(sid) for sid in subject_ids if sid}
        if sids:
            placeholders = ",".join("?" for _ in sids)
            self.db.execute(
                f"DELETE FROM teacher_subjects WHERE teacher_id = ? AND subject_id NOT IN ({placeholders})",
                (teacher_id, *sids),
            )
        else:
            self.db.execute("DELETE FROM teacher_subjects WHERE teacher_id = ?", (teacher_id,))

        created_or_updated: list[int] = []
        for sid in sids:
            rec_id = self.assign_teacher_subject(teacher_id, sid, sync_text=False)
            created_or_updated.append(rec_id)

        self.sync_teacher_subject_text(teacher_id)
        return created_or_updated

    def sync_teacher_subject_text(self, teacher_id: int) -> str:
        rows = self.db.query(
            """
            SELECT s.subject_name
            FROM teacher_subjects ts
            JOIN subjects s ON s.id = ts.subject_id
            WHERE ts.teacher_id = ? AND ts.status = 'Active'
            ORDER BY s.subject_name ASC
            """,
            (teacher_id,),
        )
        subject_names = [r["subject_name"] for r in rows]
        joined = ", ".join(subject_names)
        self.db.execute("UPDATE teachers SET subject = ? WHERE id = ?", (joined, teacher_id))
        return joined

    def get_all_teacher_subjects(self) -> dict[int, list[TeacherSubject]]:
        sql = """
            SELECT ts.*, s.subject_code, s.subject_name, s.subject_type,
                   t.teacher_name
            FROM teacher_subjects ts
            JOIN subjects s ON s.id = ts.subject_id
            JOIN teachers t ON t.id = ts.teacher_id
            WHERE ts.status = 'Active'
            ORDER BY ts.teacher_id, s.subject_name ASC
        """
        rows = self.db.query(sql)
        mapping: dict[int, list[TeacherSubject]] = {}
        for raw in rows:
            r = dict(raw)
            tid = int(r["teacher_id"])
            ts = TeacherSubject(
                id=int(r["id"]),
                teacher_id=tid,
                subject_id=int(r["subject_id"]),
                status=r.get("status") or "Active",
                remarks=r.get("remarks") or "",
                created_at=str(r.get("created_at") or ""),
                subject_code=r["subject_code"],
                subject_name=r["subject_name"],
                subject_type=r.get("subject_type") or "Optional",
                teacher_name=r["teacher_name"],
            )
            mapping.setdefault(tid, []).append(ts)
        return mapping
