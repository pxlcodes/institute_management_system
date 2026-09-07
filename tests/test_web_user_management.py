from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from elh.config import AppConfig
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
                res_headers[raw_k.decode("latin-1").lower()] = raw_v.decode("latin-1")
        elif message["type"] == "http.response.body":
            res_body.extend(message.get("body", b""))

    await app(scope, receive, send)
    return res_status, res_headers, bytes(res_body)


class WebUserManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test_users.db"
        self.config = replace(
            AppConfig(),
            database_engine="sqlite",
            database_path=db_path,
            admin_username="superadmin",
            admin_password="SuperAdmin@Pass2025",
            operator_username="testop",
            operator_password="Operator@Pass2025",
            secret_key="unit-test-secret-key-user-management",
            date_format="%Y/%m/%d",
        )
        self.app = create_app(self.config)

    def tearDown(self):
        import gc
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def _login(self, username: str, password: str) -> str:
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/auth/login",
                body={"username": username, "password": password},
            )
        )
        self.assertEqual(status, 200, f"Login failed: {body.decode()}")
        data = json.loads(body.decode("utf-8"))
        return data["token"]

    def test_roles_permissions_endpoint(self):
        admin_token = self._login("superadmin", "SuperAdmin@Pass2025")
        status, _, body = asyncio.run(
            _run_asgi_request(
                self.app,
                "GET",
                "/api/users/roles-permissions",
                headers={"authorization": f"Bearer {admin_token}"},
            )
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("super_admin", data["roles"])
        self.assertIn("admin", data["roles"])
        self.assertIn("accountant", data["roles"])
        self.assertIn("staff", data["roles"])
        self.assertIn("student", data["roles"])
        self.assertIn("parent", data["roles"])

        perm_keys = [p["key"] for p in data["permissions"]]
        self.assertIn("portal.staff", perm_keys)
        self.assertIn("portal.student", perm_keys)
        self.assertIn("portal.parent", perm_keys)
        self.assertIn("administration.manage", perm_keys)

        self.assertIn("accountant", data["role_defaults"])
        self.assertIn("billing.manage", data["role_defaults"]["accountant"])

    def test_user_creation_lifecycle_and_linking(self):
        admin_token = self._login("superadmin", "SuperAdmin@Pass2025")

        t_status, _, t_body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/staff",
                headers={"authorization": f"Bearer {admin_token}"},
                body={
                    "teacher_name": "Ramesh Sharma",
                    "staff_type": "Teaching",
                    "contact": "9841234567",
                    "email": "ramesh@example.com",
                    "joined_date": "2025/01/01",
                    "basic_salary": 25000,
                },
            )
        )
        self.assertEqual(t_status, 201)
        teacher_id = json.loads(t_body.decode())["id"]

        s_status, _, s_body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/students",
                headers={"authorization": f"Bearer {admin_token}"},
                body={
                    "name": "Aayush Shrestha",
                    "joining_date": "2025/01/10",
                    "contact": "9812345678",
                },
            )
        )
        self.assertEqual(s_status, 201)
        student_id = json.loads(s_body.decode())["id"]

        # 1. Create Staff User linked to teacher
        create_staff_status, _, cs_body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/users",
                headers={"authorization": f"Bearer {admin_token}"},
                body={
                    "username": "ramesh_staff",
                    "password": "Staff@SecretPass2025",
                    "display_name": "Ramesh Sharma",
                    "email": "ramesh@example.com",
                    "phone": "9841234567",
                    "role": "staff",
                    "status": "Active",
                    "teacher_id": teacher_id,
                    "must_change_password": True,
                },
            )
        )
        self.assertEqual(create_staff_status, 201, cs_body.decode())
        staff_user_id = json.loads(cs_body.decode())["id"]

        # 2. Create Student User linked to student
        create_student_status, _, st_body = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/users",
                headers={"authorization": f"Bearer {admin_token}"},
                body={
                    "username": "aayush_student",
                    "password": "Student@SecretPass2025",
                    "display_name": "Aayush Shrestha",
                    "phone": "9812345678",
                    "role": "student",
                    "status": "Active",
                    "student_id": student_id,
                    "must_change_password": False,
                },
            )
        )
        self.assertEqual(create_student_status, 201, st_body.decode())
        student_user_id = json.loads(st_body.decode())["id"]

        # 3. List users and verify linked names and contact details
        list_status, _, list_body = asyncio.run(
            _run_asgi_request(
                self.app,
                "GET",
                "/api/users",
                headers={"authorization": f"Bearer {admin_token}"},
            )
        )
        self.assertEqual(list_status, 200)
        users = json.loads(list_body.decode("utf-8"))
        ramesh_user = next(u for u in users if u["username"] == "ramesh_staff")
        self.assertEqual(ramesh_user["teacher_id"], teacher_id)
        self.assertEqual(ramesh_user["teacher_name"], "Ramesh Sharma")
        self.assertEqual(ramesh_user["phone"], "9841234567")

        aayush_user = next(u for u in users if u["username"] == "aayush_student")
        self.assertEqual(aayush_user["student_id"], student_id)
        self.assertEqual(aayush_user["student_name"], "Aayush Shrestha")
        self.assertEqual(aayush_user["phone"], "9812345678")

        # 4. Get User Detail
        detail_status, _, detail_body = asyncio.run(
            _run_asgi_request(
                self.app,
                "GET",
                f"/api/users/{student_user_id}",
                headers={"authorization": f"Bearer {admin_token}"},
            )
        )
        self.assertEqual(detail_status, 200)
        detail = json.loads(detail_body.decode())
        self.assertEqual(detail["username"], "aayush_student")
        self.assertIn("portal.student", detail["permissions"])

        # 5. Update User Profile
        update_status, _, _ = asyncio.run(
            _run_asgi_request(
                self.app,
                "PUT",
                f"/api/users/{student_user_id}",
                headers={"authorization": f"Bearer {admin_token}"},
                body={
                    "display_name": "Aayush Kumar Shrestha",
                    "email": "aayush@example.com",
                    "phone": "9812345679",
                    "role": "student",
                    "status": "Active",
                    "student_id": student_id,
                },
            )
        )
        self.assertEqual(update_status, 200)

        # 6. Reset User Password
        reset_status, _, _ = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                f"/api/users/{student_user_id}/reset-password",
                headers={"authorization": f"Bearer {admin_token}"},
                body={"new_password": "NewStudentPassword@2025", "must_change_password": False},
            )
        )
        self.assertEqual(reset_status, 200)

        # 7. Student logs in with new password
        student_token = self._login("aayush_student", "NewStudentPassword@2025")
        self.assertTrue(student_token)

        # 8. Verify /api/auth/me returns student_id and phone
        me_status, _, me_body = asyncio.run(
            _run_asgi_request(
                self.app,
                "GET",
                "/api/auth/me",
                headers={"authorization": f"Bearer {student_token}"},
            )
        )
        self.assertEqual(me_status, 200)
        me_data = json.loads(me_body.decode())
        self.assertEqual(me_data["student_id"], student_id)
        self.assertEqual(me_data["phone"], "9812345679")
        self.assertEqual(me_data["display_name"], "Aayush Kumar Shrestha")

        # 9. Student accesses their own profile -> 200 OK
        sp_status, _, sp_body = asyncio.run(
            _run_asgi_request(
                self.app,
                "GET",
                f"/api/students/{student_id}/profile",
                headers={"authorization": f"Bearer {student_token}"},
            )
        )
        self.assertEqual(sp_status, 200, sp_body.decode())

        # 10. Student attempts to access another student profile -> 403 Forbidden
        other_status, _, _ = asyncio.run(
            _run_asgi_request(
                self.app,
                "GET",
                f"/api/students/{student_id + 999}/profile",
                headers={"authorization": f"Bearer {student_token}"},
            )
        )
        self.assertEqual(other_status, 403)

        # 11. Toggle User Status (Disable student user)
        toggle_status, _, _ = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                f"/api/users/{student_user_id}/toggle-status",
                headers={"authorization": f"Bearer {admin_token}"},
                body={"status": "Disabled"},
            )
        )
        self.assertEqual(toggle_status, 200)

        # 12. Disabled user cannot login -> 401
        disabled_login_status, _, _ = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                "/api/auth/login",
                body={"username": "aayush_student", "password": "NewStudentPassword@2025"},
            )
        )
        self.assertEqual(disabled_login_status, 401)

        # 13. Re-enable student user
        asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                f"/api/users/{student_user_id}/toggle-status",
                headers={"authorization": f"Bearer {admin_token}"},
                body={"status": "Active"},
            )
        )

        # 14. Unlock user endpoint
        unlock_status, _, _ = asyncio.run(
            _run_asgi_request(
                self.app,
                "POST",
                f"/api/users/{student_user_id}/unlock",
                headers={"authorization": f"Bearer {admin_token}"},
            )
        )
        self.assertEqual(unlock_status, 200)

        # 15. Verify Audit Log contains actions
        audit_status, _, audit_body = asyncio.run(
            _run_asgi_request(
                self.app,
                "GET",
                "/api/users/audit-log",
                headers={"authorization": f"Bearer {admin_token}"},
            )
        )
        self.assertEqual(audit_status, 200)
        logs = json.loads(audit_body.decode())
        event_types = [entry["event_type"] for entry in logs]
        self.assertIn("user_created", event_types)
        self.assertIn("user_updated", event_types)
        self.assertIn("password_changed", event_types)
        self.assertIn("user_status_changed", event_types)
        self.assertIn("user_unlocked", event_types)


if __name__ == "__main__":
    unittest.main()
