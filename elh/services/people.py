from __future__ import annotations

from elh.core.validation import normalize_phone, parse_nepali_date, validate_date
from elh.models import Student
from elh.repositories import StudentRepository


class StudentService:
    GENDERS = ("Male", "Female", "Other")
    MAX_PHOTO_BYTES = 3 * 1024 * 1024
    PHOTO_MIME_TYPES = ("image/jpeg", "image/png")
    STATUSES = ("Active", "Inactive")

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

    def validate(self, student: Student) -> Student:
        if not student.name.strip():
            raise ValueError("Student name is required.")
        gender = student.gender.strip().title()
        if gender and gender not in self.GENDERS:
            raise ValueError("Gender must be Male, Female, or Other.")
        status = student.status.strip().title() or "Active"
        if status not in self.STATUSES:
            raise ValueError("Status must be Active or Inactive.")
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
