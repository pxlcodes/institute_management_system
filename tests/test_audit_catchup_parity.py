"""Unit tests verifying feature parity between Desktop and Web versions."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

from elh.config import AppConfig
from elh.infrastructure import create_database
from elh.web.app import create_app
from tests.test_web_security import _run_asgi_request


class FeatureParityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_parity.db"
        self.backup_dir = Path(self.temp_dir.name) / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.config = replace(
            AppConfig(),
            database_engine="sqlite",
            database_path=self.db_path,
            backup_directory=self.backup_dir,
            admin_username="testadmin",
            admin_password="Admin@TestPassword2025",
            secret_key="test-secret-key-parity-12345",
        )
        self.db = create_database(self.config)
        self.db.initialize()
        self.app = create_app(self.config)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _login(self):
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "POST",
            "/api/auth/login",
            body={"username": "testadmin", "password": "Admin@TestPassword2025"}
        ))
        self.assertEqual(status, 200)
        return json.loads(body.decode("utf-8"))["token"]

    def test_web_devices_and_printer_endpoints(self):
        token = self._login()

        # Test printer status endpoint
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "GET",
            "/api/devices/printer",
            headers={"authorization": f"Bearer {token}"}
        ))
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("driver", data)
        self.assertIn("host", data)
        self.assertIn("port", data)
        self.assertIn("width", data)
        self.assertIn("connected", data)

        # Test printer connection test endpoint
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "POST",
            "/api/devices/printer/test",
            headers={"authorization": f"Bearer {token}"}
        ))
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("ok", data)
        self.assertIn("detail", data)

    def test_web_backups_list_and_download(self):
        token = self._login()

        # Create a dummy backup file
        dummy_backup = self.backup_dir / "elh_test_20260913_120000.db"
        dummy_backup.write_bytes(b"dummy sqlite backup content")

        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "GET",
            "/api/system/backups",
            headers={"authorization": f"Bearer {token}"}
        ))
        self.assertEqual(status, 200)
        backups = json.loads(body.decode("utf-8"))
        self.assertTrue(len(backups) >= 1)
        self.assertEqual(backups[0]["filename"], dummy_backup.name)
        self.assertEqual(backups[0]["size_bytes"], len(b"dummy sqlite backup content"))

        # Test download
        status, headers, body = asyncio.run(_run_asgi_request(
            self.app,
            "GET",
            f"/api/system/backups/{dummy_backup.name}/download",
            headers={"authorization": f"Bearer {token}"}
        ))
        self.assertEqual(status, 200)
        self.assertEqual(body, b"dummy sqlite backup content")

    def test_web_assets_have_ledger_and_devices(self):
        status, _, body = asyncio.run(_run_asgi_request(self.app, "GET", "/assets/app.js"))
        self.assertEqual(status, 200)
        js = body.decode("utf-8")

        # General Ledger in Web
        self.assertIn("General Ledger", js)
        self.assertIn("exportLedgerCsv", js)
        self.assertIn("filterLedger", js)

        # Devices & Diagnostics in Web
        self.assertIn("Devices & Diagnostics", js)
        self.assertIn("testPosPrinter", js)

    def test_desktop_inquiries_page_queries(self):
        # Insert sample inquiry
        self.db.execute(
            """
            INSERT INTO website_inquiries (full_name, phone, email, grade, course_interest, message, status, created_at)
            VALUES ('Subash Basnet', '9812345678', 'subash@example.com', 'Grade 10', 'SEE Preparation', 'Interested in evening batches', 'New', '2026-09-13 10:00:00')
            """
        )

        from elh.services.container import ServiceContainer
        services = ServiceContainer.build(self.config, self.db)
        inquiries = services.cms.list_inquiries()
        self.assertTrue(len(inquiries) >= 1)
        self.assertEqual(inquiries[0]["full_name"], "Subash Basnet")

        # Test updating inquiry status
        services.cms.update_inquiry(inquiries[0]["id"], "Contacted", "Called on 9812345678, scheduled visit")
        updated = services.cms.list_inquiries()
        self.assertEqual(updated[0]["status"], "Contacted")
        self.assertEqual(updated[0]["staff_notes"], "Called on 9812345678, scheduled visit")

    def test_desktop_proxy_classes_queries(self):
        # Insert test teacher and routine
        teacher_id = self.db.execute(
            "INSERT INTO teachers (teacher_name, contact, joined_date, status) VALUES ('Prof. Sharma', '9800000001', '2083/01/01', 'Active')"
        )
        routine_id = self.db.execute(
            "INSERT INTO class_routines (class_name, period_label, subject_name, start_time, end_time, day_of_week, teacher_id, status) "
            "VALUES ('Class 10', 'Period 1', 'Physics', '07:00 AM', '08:00 AM', 'Monday', ?, 'Active')",
            (teacher_id,)
        )

        # Insert proxy class request
        proxy_id = self.db.execute(
            """
            INSERT INTO proxy_class_requests (class_date, routine_id, original_teacher_id, reason, status, proxy_status)
            VALUES ('2026-09-14', ?, ?, 'Personal emergency', 'Pending', 'Pending')
            """,
            (routine_id, teacher_id)
        )

        rows = self.db.query(
            """
            SELECT p.*, r.class_name, r.subject_name AS subject, ot.teacher_name AS original_teacher_name
            FROM proxy_class_requests p
            JOIN class_routines r ON r.id = p.routine_id
            LEFT JOIN teachers ot ON ot.id = p.original_teacher_id
            WHERE p.id = ?
            """,
            (proxy_id,)
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["class_name"], "Class 10")
        self.assertEqual(rows[0]["subject"], "Physics")
        self.assertEqual(rows[0]["original_teacher_name"], "Prof. Sharma")


if __name__ == "__main__":
    unittest.main()
