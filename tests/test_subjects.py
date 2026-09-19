from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from elh.config import AppConfig
from elh.infrastructure.sqlite_database import SQLiteDatabase
from elh.models.academics import Subject
from elh.repositories.academics import SubjectRepository
from elh.services.container import ServiceContainer
from elh.web.app import create_app
from tests.test_web_security import _run_asgi_request


class SubjectManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_subjects.db"

        self.db = SQLiteDatabase(self.db_path, False)
        self.config = AppConfig(
            database_path=self.db_path,
            secret_key="test-secret-key-subjects",
        )
        self.repo = SubjectRepository(self.db)
        self.services = ServiceContainer.build(self.config, self.db)

        # Create a test student
        self.student_id = self.db.execute(
            "INSERT INTO students (student_name, class_name, contact, joining_date, status) VALUES (?, ?, ?, ?, ?)",
            ("Aarav Sharma", "10", "9812345678", "2026-01-01", "Active"),
        )
        self.student2_id = self.db.execute(
            "INSERT INTO students (student_name, class_name, contact, joining_date, status) VALUES (?, ?, ?, ?, ?)",
            ("Bikash Thapa", "10", "9812345679", "2026-01-01", "Active"),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_seeded_subjects(self):
        """Verify that standard subjects including electives are seeded upon SQLite initialization."""
        subjects = self.repo.list_subjects()
        names = {s.subject_name for s in subjects}

        required_electives = [
            "Computer Science",
            "Biology",
            "Account",
            "Opt. Mathematics",
            "Economics",
        ]
        for name in required_electives:
            self.assertIn(name, names, f"Expected {name} to be seeded in subjects table.")

        # Check by code
        cs = self.repo.get_by_code("CS-101")
        self.assertIsNotNone(cs)
        self.assertEqual(cs.subject_name, "Computer Science")
        self.assertEqual(cs.subject_type, "Optional")

    def test_subject_crud(self):
        """Verify Subject creation, update, retrieval, and deletion."""
        sub = Subject(
            id=None,
            subject_code="PHYS-101",
            subject_name="Physics",
            subject_type="Optional",
            status="Active",
            remarks="Lab science",
        )
        sub_id = self.repo.create(sub)
        self.assertIsInstance(sub_id, int)

        fetched = self.repo.get(sub_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.subject_code, "PHYS-101")
        self.assertEqual(fetched.subject_name, "Physics")

        # Update
        fetched = replace(fetched, subject_name="Advanced Physics", remarks="Theory & Lab")
        self.repo.update(fetched)

        updated = self.repo.get(sub_id)
        self.assertEqual(updated.subject_name, "Advanced Physics")
        self.assertEqual(updated.remarks, "Theory & Lab")

        # Delete
        self.repo.delete(sub_id)
        self.assertIsNone(self.repo.get(sub_id))

    def test_student_subject_assignment(self):
        """Verify student subject enrollment, listing, and removal."""
        cs = self.repo.get_by_code("CS-101")
        self.assertIsNotNone(cs)

        assign_id = self.repo.assign_student_subject(
            student_id=self.student_id,
            subject_id=cs.id,
            enrollment_type="Optional",
            assigned_date="2026-02-01",
            remarks="Major elective",
        )
        self.assertIsInstance(assign_id, int)

        # Retrieve student's assigned subjects
        student_subs = self.repo.get_student_subjects(self.student_id)
        self.assertEqual(len(student_subs), 1)
        self.assertEqual(student_subs[0].subject_name, "Computer Science")
        self.assertEqual(student_subs[0].enrollment_type, "Optional")
        self.assertEqual(student_subs[0].student_name, "Aarav Sharma")

        # Check StudentService.get_profile returns subjects
        profile = self.services.students.get_profile(self.student_id)
        self.assertIn("subjects", profile)
        self.assertEqual(len(profile["subjects"]), 1)
        self.assertEqual(profile["subjects"][0]["subject_name"], "Computer Science")

        # Remove assignment
        self.repo.remove_student_subject(self.student_id, cs.id)
        self.assertEqual(len(self.repo.get_student_subjects(self.student_id)), 0)

    def test_batch_assignment(self):
        """Verify batch assigning a subject to multiple students."""
        bio = self.repo.get_by_code("BIO-101")
        self.assertIsNotNone(bio)

        count = self.repo.batch_assign(
            student_ids=[self.student_id, self.student2_id],
            subject_id=bio.id,
            enrollment_type="Elective",
        )
        self.assertEqual(count, 2)

        subs1 = self.repo.get_student_subjects(self.student_id)
        subs2 = self.repo.get_student_subjects(self.student2_id)
        self.assertEqual(len(subs1), 1)
        self.assertEqual(subs1[0].subject_name, "Biology")
        self.assertEqual(len(subs2), 1)
        self.assertEqual(subs2[0].subject_name, "Biology")

    def test_api_subjects_and_lookups(self):
        """Verify REST API endpoints for subjects, assignments, and lookups."""
        app = create_app(self.config)

        async def _run():
            # Sign in as admin
            code, _, body_raw = await _run_asgi_request(
                app,
                "POST",
                "/api/auth/login",
                body={"username": self.config.admin_username, "password": self.config.admin_password},
            )
            self.assertEqual(code, 200)
            token = json.loads(body_raw.decode("utf-8"))["token"]
            headers = {"Authorization": f"Bearer {token}"}

            # 1. /api/lookups contains subjects
            code, _, body_raw = await _run_asgi_request(app, "GET", "/api/lookups", headers=headers)
            self.assertEqual(code, 200)
            lookups = json.loads(body_raw.decode("utf-8"))
            self.assertIn("subjects", lookups)
            subj_names = [s["subject_name"] for s in lookups["subjects"]]
            self.assertIn("Computer Science", subj_names)
            self.assertIn("Biology", subj_names)

            # 2. GET /api/subjects
            code, _, body_raw = await _run_asgi_request(app, "GET", "/api/subjects", headers=headers)
            self.assertEqual(code, 200)
            subs = json.loads(body_raw.decode("utf-8"))
            self.assertGreaterEqual(len(subs), 12)

            # 3. POST /api/subjects (Create new subject)
            code, _, body_raw = await _run_asgi_request(
                app,
                "POST",
                "/api/subjects",
                headers=headers,
                body={
                    "subject_code": "STAT-101",
                    "subject_name": "Statistics",
                    "subject_type": "Optional",
                    "status": "Active",
                    "remarks": "Applied Statistics",
                },
            )
            self.assertEqual(code, 201)
            new_id = json.loads(body_raw.decode("utf-8"))["id"]

            # 4. POST /api/students/{id}/subjects
            code, _, body_raw = await _run_asgi_request(
                app,
                "POST",
                f"/api/students/{self.student_id}/subjects",
                headers=headers,
                body={
                    "subject_id": new_id,
                    "enrollment_type": "Optional",
                    "assigned_date": "2026-03-01",
                },
            )
            self.assertEqual(code, 201)

            # 5. GET /api/students/{id}/subjects
            code, _, body_raw = await _run_asgi_request(
                app, "GET", f"/api/students/{self.student_id}/subjects", headers=headers
            )
            self.assertEqual(code, 200)
            st_subs = json.loads(body_raw.decode("utf-8"))
            self.assertEqual(len(st_subs), 1)
            self.assertEqual(st_subs[0]["subject_name"], "Statistics")

            # 6. POST /api/students/batch-assign-subject
            code, _, body_raw = await _run_asgi_request(
                app,
                "POST",
                "/api/students/batch-assign-subject",
                headers=headers,
                body={
                    "student_ids": [self.student_id, self.student2_id],
                    "subject_id": new_id,
                    "enrollment_type": "Optional",
                },
            )
            self.assertEqual(code, 200)
            res = json.loads(body_raw.decode("utf-8"))
            self.assertEqual(res["count"], 2)

            # 7. DELETE /api/students/{id}/subjects/{subject_id}
            code, _, _ = await _run_asgi_request(
                app,
                "DELETE",
                f"/api/students/{self.student_id}/subjects/{new_id}",
                headers=headers,
            )
            self.assertEqual(code, 200)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
