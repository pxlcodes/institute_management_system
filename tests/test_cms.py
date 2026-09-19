import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from elh.config import AppConfig
from elh.infrastructure.sqlite_database import SQLiteDatabase
from elh.services.auth import AuthService, PERMISSION_DEFINITIONS, ROLE_DEFAULTS, ROLES
from elh.services.cms import CmsService, DEFAULT_CMS_SECTIONS
from elh.web.app import create_app


async def _run_asgi_request(
    app,
    method: str,
    path: str,
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    client: tuple[str, int] = ("127.0.0.1", 50000),
) -> tuple[int, dict[str, str], bytes]:
    req_headers = []
    if headers:
        for k, v in headers.items():
            req_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))

    req_body = json.dumps(body).encode("utf-8") if body is not None else b""
    if body is not None and not any(k.lower() == "content-type" for k, _ in (headers or {}).items()):
        req_headers.append((b"content-type", b"application/json"))

    path_only, _, query = path.partition("?")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": path_only,
        "raw_path": path_only.encode("ascii"),
        "query_string": query.encode("ascii"),
        "headers": req_headers,
        "client": client,
        "server": ("testserver", 80),
    }

    res_status = 200
    res_headers: dict[str, str] = {}
    res_body = bytearray()

    async def receive():
        return {"type": "http.request", "body": req_body, "more_body": False}

    async def send(message):
        nonlocal res_status
        if message["type"] == "http.response.start":
            res_status = message["status"]
            for raw_k, raw_v in message.get("headers", []):
                k = raw_k.decode("latin-1").lower()
                v = raw_v.decode("latin-1")
                res_headers[k] = v
        elif message["type"] == "http.response.body":
            res_body.extend(message.get("body", b""))

    await app(scope, receive, send)
    return res_status, res_headers, bytes(res_body)


class TestCmsServiceAndRole(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "cms_test.db"
        self.db = SQLiteDatabase(self.db_path, seed_demo_data=False)
        self.config = AppConfig(
            database_path=self.db_path,
            database_engine="sqlite",
            secret_key="unit-test-secret-key-for-web-session"
        )
        self.auth = AuthService(self.db, self.config)
        self.cms = CmsService(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_role_and_permission_definitions(self):
        self.assertIn("cms_manager", ROLES)
        perm_keys = {p[0] for p in PERMISSION_DEFINITIONS}
        self.assertIn("cms.manage", perm_keys)
        cms_manager_defaults = ROLE_DEFAULTS.get("cms_manager")
        self.assertIsNotNone(cms_manager_defaults)
        self.assertIn("cms.manage", cms_manager_defaults)
        self.assertIn("dashboard.view", cms_manager_defaults)

    def test_get_all_cms_content_returns_defaults(self):
        content = self.cms.get_all_content()
        self.assertIsInstance(content, dict)
        for key in ["hero", "general", "stats", "courses", "iot_showcase", "languages", "pillars", "events", "testimonials", "faqs"]:
            self.assertIn(key, content)
            self.assertEqual(content[key], DEFAULT_CMS_SECTIONS[key])

    def test_save_and_get_cms_section(self):
        custom_hero = {
            "badge": "Custom Badge 2083",
            "title": "Custom Title Here",
            "subtitle": "Custom Subtitle",
            "announcement_active": True,
            "announcement_text": "Special Announcement Test"
        }
        saved = self.cms.save_section("hero", custom_hero, updated_by="admin")
        self.assertEqual(saved["badge"], "Custom Badge 2083")

        fetched = self.cms.get_section("hero")
        self.assertEqual(fetched["badge"], "Custom Badge 2083")
        self.assertEqual(fetched["title"], "Custom Title Here")

    def test_reset_defaults(self):
        custom_hero = {"badge": "Modified"}
        self.cms.save_section("hero", custom_hero, updated_by="admin")
        self.assertEqual(self.cms.get_section("hero")["badge"], "Modified")

        reset_content = self.cms.reset_defaults(updated_by="admin")
        self.assertEqual(reset_content["hero"]["badge"], DEFAULT_CMS_SECTIONS["hero"]["badge"])

    def test_inquiry_lifecycle(self):
        inquiry_id = self.cms.create_inquiry(
            full_name="Pooja Sharma",
            phone="9800000000",
            email="pooja@example.com",
            course_interest="Grade 10 SEE Master Class",
            grade="Grade 10",
            message="Interested in morning coaching."
        )
        self.assertGreater(inquiry_id, 0)

        inquiries = self.cms.list_inquiries()
        self.assertEqual(len(inquiries), 1)
        self.assertEqual(inquiries[0]["full_name"], "Pooja Sharma")
        self.assertEqual(inquiries[0]["status"], "New")

        self.cms.update_inquiry(inquiry_id, status="Contacted", staff_notes="Called student")
        updated = self.cms.list_inquiries()[0]
        self.assertEqual(updated["status"], "Contacted")
        self.assertEqual(updated["staff_notes"], "Called student")

        self.assertEqual(len(self.cms.list_inquiries(status="Contacted")), 1)
        self.assertEqual(len(self.cms.list_inquiries(status="Enrolled")), 0)

        self.assertEqual(len(self.cms.list_inquiries(search="pooja")), 1)
        self.assertEqual(len(self.cms.list_inquiries(search="nonexistent")), 0)

        self.cms.delete_inquiry(inquiry_id)
        self.assertEqual(len(self.cms.list_inquiries()), 0)


class TestCmsApiEndpoints(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "cms_api_test.db"
        self.config = AppConfig(
            database_path=self.db_path,
            database_engine="sqlite",
            secret_key="unit-test-secret-key-for-web-session"
        )
        self.app = create_app(self.config)
        self.auth = self.app.state.auth
        self.services = self.app.state.services

        admin_session = self.auth.authenticate("admin", self.config.admin_password)

        self.auth.create_user(
            username="cmsuser",
            password="Password123!",
            display_name="CMS Manager",
            email="cms@example.com",
            role="cms_manager",
            status="Active",
            permissions=set(),
            actor=admin_session,
            must_change_password=False,
        )

        self.auth.create_user(
            username="student1",
            password="Password123!",
            display_name="Student One",
            email="student@example.com",
            role="student",
            status="Active",
            permissions=set(),
            actor=admin_session,
            must_change_password=False,
        )

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_public_website_data_accessible_without_auth(self):
        status, _, body = asyncio.run(_run_asgi_request(self.app, "GET", "/api/public/website-data"))
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("hero", data)
        self.assertIn("general", data)
        self.assertIn("courses", data)
        self.assertEqual(data["general"]["name"], "Expert Learning Hub")

    def test_public_inquiry_submission(self):
        payload = {
            "full_name": "Rohan Thapa",
            "phone": "9812345678",
            "email": "rohan@example.com",
            "course_name": "+2 Science Core & Entrance Prep",
            "grade_level": "Grade 11",
            "message": "Looking for evening Physics batch."
        }
        status, _, body = asyncio.run(_run_asgi_request(self.app, "POST", "/api/public/inquiry", body=payload))
        self.assertEqual(status, 200)
        resp_data = json.loads(body.decode("utf-8"))
        self.assertTrue(resp_data.get("ok"))

    def test_cms_content_auth_enforcement(self):
        # Unauthenticated request should fail
        status, _, _ = asyncio.run(_run_asgi_request(self.app, "GET", "/api/cms/content"))
        self.assertEqual(status, 401)

        # Login as student (no cms.manage permission)
        token_mgr = self.app.state.token_manager
        student_session = self.auth.authenticate("student1", "Password123!")
        student_token = token_mgr.create_token(student_session.user_id, "student1", "student")

        status, _, _ = asyncio.run(_run_asgi_request(
            self.app,
            "GET",
            "/api/cms/content",
            headers={"authorization": f"Bearer {student_token}"}
        ))
        self.assertEqual(status, 403)

        # Login as cmsuser (has cms.manage permission via cms_manager role)
        cms_session = self.auth.authenticate("cmsuser", "Password123!")
        cms_token = token_mgr.create_token(cms_session.user_id, "cmsuser", "cms_manager")

        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "GET",
            "/api/cms/content",
            headers={"authorization": f"Bearer {cms_token}"}
        ))
        self.assertEqual(status, 200)
        self.assertIn("hero", json.loads(body.decode("utf-8")))

        # PUT section
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "PUT",
            "/api/cms/sections/general",
            headers={"authorization": f"Bearer {cms_token}"},
            body={"data": {"name": "Expert Learning Hub International", "tagline": "Empowering Future"}}
        ))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body.decode("utf-8"))["name"], "Expert Learning Hub International")

        # Verify public website-data immediately reflects change
        status, _, body = asyncio.run(_run_asgi_request(self.app, "GET", "/api/public/website-data"))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body.decode("utf-8"))["general"]["name"], "Expert Learning Hub International")

    def test_cms_inquiries_management_endpoints(self):
        # Create inquiry via service
        inquiry_id = self.services.cms.create_inquiry(
            full_name="Sita Rai",
            phone="9801122334",
            course_interest="Korean Language"
        )

        token_mgr = self.app.state.token_manager
        cms_session = self.auth.authenticate("cmsuser", "Password123!")
        cms_token = token_mgr.create_token(cms_session.user_id, "cmsuser", "cms_manager")

        # List inquiries
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "GET",
            "/api/cms/inquiries",
            headers={"authorization": f"Bearer {cms_token}"}
        ))
        self.assertEqual(status, 200)
        inquiries = json.loads(body.decode("utf-8"))
        self.assertEqual(len(inquiries), 1)

        # Update inquiry
        status, _, _ = asyncio.run(_run_asgi_request(
            self.app,
            "PUT",
            f"/api/cms/inquiries/{inquiry_id}",
            headers={"authorization": f"Bearer {cms_token}"},
            body={"status": "Counseling Scheduled", "staff_notes": "Counseling on 2083/05/18"}
        ))
        self.assertEqual(status, 200)

        # Delete inquiry
        status, _, _ = asyncio.run(_run_asgi_request(
            self.app,
            "DELETE",
            f"/api/cms/inquiries/{inquiry_id}",
            headers={"authorization": f"Bearer {cms_token}"}
        ))
        self.assertEqual(status, 200)

        # Confirm deleted
        status, _, body = asyncio.run(_run_asgi_request(
            self.app,
            "GET",
            "/api/cms/inquiries",
            headers={"authorization": f"Bearer {cms_token}"}
        ))
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body.decode("utf-8"))), 0)


if __name__ == "__main__":
    unittest.main()
