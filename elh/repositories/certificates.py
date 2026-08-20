from __future__ import annotations

from elh.models import CertificateIssueRequest, CourseCertificate


class CertificateRepository:
    def __init__(self, db):
        self.db = db

    def completed_enrollments_without_certificate(self):
        return self.db.query(
            "SELECT e.id enrollment_id,e.start_date,e.end_date,e.status," 
            "s.student_name,s.contact,s.gender,s.date_of_birth,s.parent_name," 
            "s.guardian_relationship,c.course_name,c.instructor_name course_instructor," 
            "COALESCE((SELECT principal_name FROM company_profile WHERE id=1),'') company_principal "
            "FROM enrollments e JOIN students s ON s.id=e.student_id "
            "JOIN courses c ON c.id=e.course_id "
            "LEFT JOIN course_certificates cc ON cc.enrollment_id=e.id "
            "WHERE e.status='Completed' AND e.end_date IS NOT NULL AND e.end_date<>'' "
            "AND cc.id IS NULL ORDER BY s.student_name,c.course_name,e.end_date"
        )

    def enrollment(self, enrollment_id: int):
        return self.db.query_one(
            "SELECT e.id enrollment_id,e.start_date,e.end_date,e.status," 
            "s.student_name,s.contact,s.gender,s.date_of_birth,s.parent_name," 
            "s.guardian_relationship,c.course_name,c.duration_months," 
            "c.instructor_name course_instructor," 
            "COALESCE((SELECT company_name FROM company_profile WHERE id=1),?) company_name," 
            "COALESCE((SELECT principal_name FROM company_profile WHERE id=1),'') company_principal "
            "FROM enrollments e JOIN students s ON s.id=e.student_id "
            "JOIN courses c ON c.id=e.course_id WHERE e.id=?",
            ("Expert Learning Hub", enrollment_id),
        )

    def certificate_numbers(self, prefix: str, year: int) -> list[str]:
        return [
            str(row["certificate_number"])
            for row in self.db.query(
                "SELECT certificate_number FROM course_certificates "
                "WHERE certificate_number LIKE ?",
                (f"{prefix}-{year}-%",),
            )
        ]

    def by_enrollment(self, enrollment_id: int):
        return self.db.query_one(
            "SELECT id,certificate_number FROM course_certificates WHERE enrollment_id=?",
            (enrollment_id,),
        )

    def number_exists(self, certificate_number: str) -> bool:
        return bool(
            self.db.query_one(
                "SELECT id FROM course_certificates WHERE certificate_number=?",
                (certificate_number,),
            )
        )

    def create(
        self,
        request: CertificateIssueRequest,
        enrollment,
        duration_days: int,
        honorific: str,
    ) -> int:
        return self.db.execute(
            "INSERT INTO course_certificates "
            "(certificate_number,enrollment_id,honorific,guardian_relationship,date_of_birth," 
            "student_name_snapshot,guardian_name_snapshot,course_name_snapshot,company_name_snapshot," 
            "course_start_date,course_end_date,duration_days,certify_date,instructor_name," 
            "principal_name,created_by_user_id,remarks) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                request.certificate_number,
                request.enrollment_id,
                honorific,
                enrollment["guardian_relationship"] or "",
                enrollment["date_of_birth"] or "",
                enrollment["student_name"],
                enrollment["parent_name"],
                enrollment["course_name"],
                enrollment["company_name"],
                enrollment["start_date"],
                enrollment["end_date"],
                duration_days,
                request.certify_date,
                request.instructor_name,
                request.principal_name,
                request.created_by_user_id,
                request.remarks,
            ),
        )

    def update_document_path(self, certificate_id: int, document_path: str) -> None:
        self.db.execute(
            "UPDATE course_certificates SET document_path=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (document_path, certificate_id),
        )

    def update_pdf(self, certificate_id: int, pdf_path: str, pdf_sha256: str) -> None:
        self.db.execute(
            "UPDATE course_certificates SET pdf_path=?,pdf_sha256=?,"
            "updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (pdf_path, pdf_sha256, certificate_id),
        )

    def delete_failed_issue(self, certificate_id: int) -> None:
        self.db.execute("DELETE FROM course_certificates WHERE id=?", (certificate_id,))

    def get(self, certificate_id: int) -> CourseCertificate | None:
        row = self.db.query_one(
            "SELECT id,certificate_number,enrollment_id,honorific,guardian_relationship," 
            "date_of_birth,student_name_snapshot,guardian_name_snapshot,course_name_snapshot," 
            "company_name_snapshot,course_start_date,course_end_date,duration_days,certify_date," 
            "instructor_name,principal_name,document_path,pdf_path,pdf_sha256,remarks "
            "FROM course_certificates WHERE id=?",
            (certificate_id,),
        )
        if not row:
            return None
        return CourseCertificate(
            id=int(row["id"]),
            certificate_number=row["certificate_number"],
            enrollment_id=int(row["enrollment_id"]),
            honorific=row["honorific"],
            guardian_relationship=row["guardian_relationship"],
            date_of_birth=row["date_of_birth"],
            student_name=row["student_name_snapshot"],
            guardian_name=row["guardian_name_snapshot"],
            course_name=row["course_name_snapshot"],
            company_name=row["company_name_snapshot"],
            course_start_date=row["course_start_date"],
            course_end_date=row["course_end_date"],
            duration_days=int(row["duration_days"]),
            certify_date=row["certify_date"],
            instructor_name=row["instructor_name"],
            principal_name=row["principal_name"],
            document_path=row["document_path"] or "",
            pdf_path=row["pdf_path"] or "",
            pdf_sha256=row["pdf_sha256"] or "",
            remarks=row["remarks"] or "",
        )

    def student_photo(self, enrollment_id: int):
        return self.db.query_one(
            "SELECT s.photo_data,s.photo_mime_type FROM enrollments e "
            "JOIN students s ON s.id=e.student_id WHERE e.id=?",
            (enrollment_id,),
        )

    def list(self):
        return self.db.query(
            "SELECT id,certificate_number,student_name_snapshot,course_name_snapshot," 
            "course_start_date,course_end_date,duration_days,certify_date," 
            "instructor_name,document_path,pdf_path,pdf_sha256,created_at "
            "FROM course_certificates ORDER BY certify_date DESC,id DESC"
        )
