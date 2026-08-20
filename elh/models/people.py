from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Student:
    id: int | None
    name: str
    class_name: str = ""
    school_id: int | None = None
    school_name: str = ""
    contact: str = ""
    gender: str = ""
    date_of_birth: str = ""
    parent_name: str = ""
    guardian_relationship: str = ""
    joining_date: str = ""
    photo_data: bytes | None = None
    photo_mime_type: str = ""
    address: str = ""
    status: str = "Active"
    remarks: str = ""

    @property
    def school(self) -> str:
        """Display-only compatibility alias; the database stores ``school_id``."""
        return self.school_name


@dataclass(frozen=True)
class Teacher:
    id: int | None
    name: str
    contact: str = ""
    email: str = ""
    subject: str = ""
    joined_date: str = ""
    status: str = "Active"


@dataclass(frozen=True)
class School:
    id: int | None
    name: str
    address: str = ""
    contact: str = ""
    status: str = "Active"
    remarks: str = ""


@dataclass(frozen=True)
class Course:
    id: int | None
    name: str
    category: str
    billing_type: str
    default_fee: float = 0
    duration_months: int = 0
    instructor_name: str = ""
    status: str = "Active"
    remarks: str = ""
