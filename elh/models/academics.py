"""Academics and curriculum domain models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Subject:
    id: int | None
    subject_code: str
    subject_name: str
    subject_type: str = "Optional"  # "Optional" or "Compulsory"
    class_level_id: int | None = None
    class_name: str | None = None
    status: str = "Active"
    remarks: str = ""
    created_at: str | None = None


@dataclass(frozen=True)
class StudentSubject:
    id: int | None
    student_id: int
    subject_id: int
    enrollment_type: str = "Optional"  # "Optional", "Compulsory", "Elective"
    assigned_date: str | None = None
    status: str = "Active"
    remarks: str = ""
    created_at: str | None = None
    # Enriched fields
    subject_code: str = ""
    subject_name: str = ""
    subject_type: str = "Optional"
    student_name: str = ""
    class_name: str = ""


@dataclass(frozen=True)
class TeacherSubject:
    id: int | None
    teacher_id: int
    subject_id: int
    status: str = "Active"
    remarks: str = ""
    created_at: str | None = None
    # Enriched fields
    subject_code: str = ""
    subject_name: str = ""
    subject_type: str = "Optional"
    teacher_name: str = ""

