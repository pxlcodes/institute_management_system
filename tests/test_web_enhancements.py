import asyncio
import re
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from elh.config import AppConfig
from elh.infrastructure import create_database
from elh.web.app import create_app
from tests.test_web_security import _run_asgi_request

class WebEnhancementsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.config = replace(
            AppConfig(),
            database_engine="sqlite",
            database_path=self.db_path,
            admin_username="testadmin",
            admin_password="Admin@TestPassword2025",
            secret_key="test-secret-key-123456",
        )
        self.db = create_database(self.config)
        self.db.initialize()
        self.app = create_app(self.config)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _login(self):
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "POST",
            "/api/auth/login",
            body={"username": "testadmin", "password": "Admin@TestPassword2025"}
        ))
        self.assertEqual(status, 200)
        import json
        return json.loads(body.decode("utf-8"))["token"]

    def test_api_lookups_success(self):
        token = self._login()
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "GET",
            "/api/lookups",
            headers={"authorization": f"Bearer {token}"}
        ))
        self.assertEqual(status, 200)
        import json
        data = json.loads(body.decode("utf-8"))
        self.assertIn("teachers", data)
        self.assertIn("students", data)
        self.assertIn("roles", data)
        self.assertIn("schools", data)
        self.assertIn("classes", data)

    def test_table_headers_not_empty(self):
        status, _, body = asyncio.run(_run_asgi_request(self.app, "GET", "/assets/app.js"))
        self.assertEqual(status, 200)
        js = body.decode("utf-8")
        empty_labels = re.findall(r"label:\s*['\"]['\"]", js)
        self.assertEqual(len(empty_labels), 0, f"Found empty column labels: {empty_labels}")

    def test_user_management_functions(self):
        status, _, body = asyncio.run(_run_asgi_request(self.app, "GET", "/assets/app.js"))
        self.assertEqual(status, 200)
        js = body.decode("utf-8")
        self.assertIn("openCreateUserForStaff", js)
        self.assertIn("openCreateUserForStudent", js)
        self.assertIn("validateClientPassword", js)
        self.assertIn("preset", js)

    def test_ai_assistant_design_pattern(self):
        status, _, body = asyncio.run(_run_asgi_request(self.app, "GET", "/assets/app.js"))
        self.assertEqual(status, 200)
        js = body.decode("utf-8")
        self.assertIn("cmd-icon", js)
        self.assertIn("cmd-label", js)
        self.assertNotIn("['📊 Overview', '/stats']", js)

        status, _, body = asyncio.run(_run_asgi_request(self.app, "GET", "/assets/styles.css"))
        self.assertEqual(status, 200)
        css = body.decode("utf-8")
        self.assertIn(".quick-cmd-btn", css)
        self.assertIn(".cmd-icon", css)
        self.assertIn(".cmd-label", css)

    def test_top_navbar_mode_switch_and_user_profile(self):
        status, _, body = asyncio.run(_run_asgi_request(self.app, "GET", "/assets/app.js"))
        self.assertEqual(status, 200)
        js = body.decode("utf-8")
        self.assertIn("user-menu-wrapper", js)
        self.assertIn("user-dropdown-menu", js)
        self.assertIn("toggleUserDropdown", js)
        self.assertIn("closeUserDropdown", js)

        status, _, body = asyncio.run(_run_asgi_request(self.app, "GET", "/assets/styles.css"))
        self.assertEqual(status, 200)
        css = body.decode("utf-8")
        self.assertIn("--radius-full: 9999px", css)
        self.assertIn(".user-menu-wrapper", css)
        self.assertIn(".user-dropdown-menu", css)
    def test_public_website_endpoints(self):
        status, _, body = asyncio.run(_run_asgi_request(self.app, "GET", "/api/public/site-info"))
        self.assertEqual(status, 200)
        import json
        info = json.loads(body.decode("utf-8"))
        self.assertEqual(info["name"], "Expert Learning Hub")
        self.assertIn("Pathari", info["address"])
        self.assertIn("courses", info)

        inquiry_payload = {
            "full_name": "Roshan Dahal",
            "phone": "9800900000",
            "email": "roshan@example.com",
            "grade": "Grade 10",
            "course_interest": "SEE Master Class",
            "message": "Interested in morning coaching."
        }
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "POST",
            "/api/public/inquiry",
            body=inquiry_payload
        ))
    def test_attendance_section_cards(self):
        status, _, body = asyncio.run(_run_asgi_request(self.app, "GET", "/assets/app.js"))
        self.assertEqual(status, 200)
        js = body.decode("utf-8")
        self.assertIn("Students Present Today", js)
        self.assertIn("Students Absent Today", js)
        self.assertIn("presentStudentsSection", js)
        self.assertIn("absentStudentsSection", js)
        self.assertIn("/attendance/present-today", js)
        self.assertIn("/attendance/absent-today", js)


if __name__ == "__main__":
    unittest.main()
