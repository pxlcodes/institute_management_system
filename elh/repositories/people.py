from __future__ import annotations

from elh.models import Student, Teacher
from .protocols import DatabaseGateway


class StudentRepository:
    def __init__(self, db: DatabaseGateway):
        self.db = db

    def get(self, student_id: int) -> Student | None:
        row = self.db.query_one(
            "SELECT s.*,sc.school_name FROM students s "
            "LEFT JOIN schools sc ON sc.id=s.school_id WHERE s.id=?", (student_id,)
        )
        return self._model(row) if row else None

    def list(self, search: str = "") -> list[Student]:
        pattern = f"%{search.strip()}%"
        rows = self.db.query(
            "SELECT s.id,s.student_name,s.class_name,s.school_id,s.contact,s.gender," 
            "s.date_of_birth,s.parent_name,s.guardian_relationship,s.joining_date," 
            "s.photo_mime_type,s.address,s.status,s.remarks,sc.school_name,NULL photo_data "
            "FROM students s LEFT JOIN schools sc ON sc.id=s.school_id "
            "WHERE s.student_name LIKE ? OR s.contact LIKE ? OR sc.school_name LIKE ? "
            "OR s.gender LIKE ? "
            "ORDER BY s.student_name", (pattern, pattern, pattern, pattern),
        )
        return [self._model(row) for row in rows]

    def add(self, student: Student) -> int:
        return self.db.execute(
            "INSERT INTO students (student_name,class_name,school_id,contact,gender," 
            "date_of_birth,parent_name,guardian_relationship,joining_date,photo_data," 
            "photo_mime_type,address,status,remarks) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (student.name, student.class_name, student.school_id, student.contact,
             student.gender, student.date_of_birth, student.parent_name,
             student.guardian_relationship, student.joining_date, student.photo_data,
             student.photo_mime_type, student.address, student.status, student.remarks),
        )

    def add_many(self, students: list[Student]) -> int:
        return self.db.executemany(
            "INSERT INTO students (student_name,class_name,school_id,contact,gender," 
            "date_of_birth,parent_name,guardian_relationship,joining_date,photo_data," 
            "photo_mime_type,address,status,remarks) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (student.name, student.class_name, student.school_id, student.contact,
                 student.gender, student.date_of_birth, student.parent_name,
                 student.guardian_relationship, student.joining_date, student.photo_data,
                 student.photo_mime_type, student.address, student.status, student.remarks)
                for student in students
            ],
        )

    def update(self, student: Student) -> None:
        if student.id is None:
            raise ValueError("Student ID is required for an update.")
        self.db.execute(
            "UPDATE students SET student_name=?,class_name=?,school_id=?,contact=?,gender=?," 
            "date_of_birth=?,parent_name=?,guardian_relationship=?,joining_date=?," 
            "photo_data=?,photo_mime_type=?,address=?,status=?,remarks=? WHERE id=?",
            (student.name, student.class_name, student.school_id, student.contact,
             student.gender, student.date_of_birth, student.parent_name,
             student.guardian_relationship, student.joining_date, student.photo_data,
             student.photo_mime_type, student.address, student.status, student.remarks,
             student.id),
        )

    def delete(self, student_id: int) -> None:
        self.db.execute("DELETE FROM students WHERE id=?", (student_id,))

    @staticmethod
    def _model(row) -> Student:
        return Student(
            id=int(row["id"]), name=row["student_name"], class_name=row["class_name"] or "",
            school_id=int(row["school_id"]) if row["school_id"] is not None else None,
            school_name=row["school_name"] or "", contact=row["contact"] or "",
            gender=row["gender"] or "", date_of_birth=row["date_of_birth"] or "",
            parent_name=row["parent_name"] or "",
            guardian_relationship=row["guardian_relationship"] or "",
            joining_date=row["joining_date"], photo_data=row["photo_data"],
            photo_mime_type=row["photo_mime_type"] or "",
            address=row["address"] or "", status=row["status"], remarks=row["remarks"] or "",
        )


class TeacherRepository:
    def __init__(self, db: DatabaseGateway):
        self.db = db

    def get(self, teacher_id: int) -> Teacher | None:
        row = self.db.query_one("SELECT * FROM teachers WHERE id = ?", (teacher_id,))
        if not row:
            return None
        return Teacher(
            id=int(row["id"]), name=row["teacher_name"], contact=row["contact"] or "",
            email=row["email"] or "", subject=row["subject"] or "",
            joined_date=row["joined_date"], status=row["status"],
        )
