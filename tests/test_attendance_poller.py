from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from elh.config import AppConfig
from elh.models import AttendanceEvent
from elh.repositories import AttendanceRepository
from elh.services.attendance import AttendanceService, AttendanceSyncResult
from elh.services.attendance_poller import AttendancePoller
from elh.web.app import create_app
from tests.test_web_security import _run_asgi_request


class DummyDevice:
    def __init__(self, events: list[AttendanceEvent] | None = None, fail: bool = False):
        self.events = events or []
        self.fail = fail

    def fetch_events(self) -> list[AttendanceEvent]:
        if self.fail:
            from elh.hardware.attendance.base import AttendanceDeviceError
            raise AttendanceDeviceError("Cannot reach dummy biometric device.")
        return list(self.events)

    def fetch_users(self):
        return []

    def sync_user_names(self, names: dict[str, str]):
        return len(names), 0

    def health(self):
        return (not self.fail, "Dummy OK" if not self.fail else "Disconnected")


class AttendancePollerTests(unittest.TestCase):
    def test_poller_lifecycle_and_metrics(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "poller_test.db"
            from elh.infrastructure.sqlite_database import SQLiteDatabase
            db = SQLiteDatabase(db_path, seed_demo_data=False)

            event1 = AttendanceEvent("101", datetime(2026, 8, 31, 8, 30, 0), "check-in", "SER123", "fingerprint")
            device = DummyDevice([event1])
            repo = AttendanceRepository(db)
            service = AttendanceService(repo, device)

            imported_results = []
            poller = AttendancePoller(
                service,
                interval_seconds=1,
                enabled=True,
                on_punches_imported=lambda r: imported_results.append(r),
            )

            self.assertTrue(poller.is_enabled)
            self.assertFalse(poller.is_running)

            # 1. Immediate Poll
            result = poller.poll_now()
            self.assertEqual(result.received, 1)
            self.assertEqual(result.saved, 1)
            self.assertEqual(poller.total_saved_count, 1)
            self.assertEqual(poller.poll_count, 1)
            self.assertTrue(poller.device_healthy)
            self.assertIsNone(poller.last_error)
            self.assertEqual(len(imported_results), 1)

            # 2. Second poll: duplicate punch should result in saved=0
            result2 = poller.poll_now()
            self.assertEqual(result2.received, 1)
            self.assertEqual(result2.saved, 0)
            self.assertEqual(poller.total_saved_count, 1)

            # 3. Start background thread and stop
            started = poller.start()
            self.assertTrue(started)
            self.assertTrue(poller.is_running)
            time.sleep(0.1)
            poller.stop(timeout=1.0)
            self.assertFalse(poller.is_running)

            # 4. Error resilience
            device.fail = True
            with self.assertRaises(Exception):
                poller.poll_now()
            self.assertFalse(poller.device_healthy)
            self.assertIn("Cannot reach dummy", poller.last_error or "")

            status = poller.status()
            self.assertEqual(status["enabled"], True)
            self.assertEqual(status["running"], False)
            self.assertFalse(status["device_healthy"])

    def test_poller_web_api_endpoints(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "test_poller_web.db"
            config = replace(
                AppConfig(),
                database_engine="sqlite",
                database_path=db_path,
                admin_username="testadmin",
                admin_password="Admin@TestPassword2025",
                attendance_driver="disabled",
                attendance_auto_poll=False,
                secret_key="unit-test-secret-key-for-web-session",
            )
            app = create_app(config)

            # Login as admin
            _, _, login_body = asyncio.run(
                _run_asgi_request(
                    app,
                    "POST",
                    "/api/auth/login",
                    body={"username": "testadmin", "password": "Admin@TestPassword2025"},
                )
            )
            token = json.loads(login_body.decode("utf-8"))["token"]
            auth_header = {"authorization": f"Bearer {token}"}

            # 1. Get poller status
            status_code, _, body = asyncio.run(
                _run_asgi_request(app, "GET", "/api/attendance/poller/status", headers=auth_header)
            )
            self.assertEqual(status_code, 200)
            status_data = json.loads(body.decode("utf-8"))
            self.assertIn("enabled", status_data)
            self.assertIn("running", status_data)
            self.assertIn("interval_seconds", status_data)

            # 2. Trigger poller
            status_code, _, body = asyncio.run(
                _run_asgi_request(app, "POST", "/api/attendance/poller/trigger", headers=auth_header)
            )
            self.assertEqual(status_code, 200)
            trigger_data = json.loads(body.decode("utf-8"))
            self.assertTrue(trigger_data["ok"])

            # 3. Update poller config
            status_code, _, body = asyncio.run(
                _run_asgi_request(
                    app,
                    "POST",
                    "/api/attendance/poller/config",
                    headers=auth_header,
                    body={"interval_seconds": 30, "enabled": False},
                )
            )
            self.assertEqual(status_code, 200)
            config_data = json.loads(body.decode("utf-8"))
            self.assertEqual(config_data["interval_seconds"], 30)
            self.assertFalse(config_data["enabled"])


if __name__ == "__main__":
    unittest.main()
