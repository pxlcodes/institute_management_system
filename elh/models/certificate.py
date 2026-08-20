from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CertificateIssueRequest:
    enrollment_id: int
    certificate_number: str
    certify_date: str
    instructor_name: str
    principal_name: str
    remarks: str = ""
    created_by_user_id: int | None = None


@dataclass(frozen=True)
class CourseCertificate:
    id: int
    certificate_number: str
    enrollment_id: int
    honorific: str
    guardian_relationship: str
    date_of_birth: str
    student_name: str
    guardian_name: str
    course_name: str
    company_name: str
    course_start_date: str
    course_end_date: str
    duration_days: int
    certify_date: str
    instructor_name: str
    principal_name: str
    document_path: str = ""
    pdf_path: str = ""
    pdf_sha256: str = ""
    remarks: str = ""
