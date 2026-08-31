from __future__ import annotations

import asyncio
import json
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from elh.config import AppConfig
from elh.web.app import create_app
from elh.web.security import RateLimiter, TokenManager, resolve_secret_key


async def _run_asgi_request(
    app,
    method: str,
    path: str,
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    client: tuple[str, int] = ("127.0.0.1", 50000),
) -> tuple[int, dict[str, str], bytes]:
    """Lightweight ASGI test helper without external dependencies."""
    req_headers = []
    if headers:
        for k, v in headers.items():
            req_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))

    req_body = json.dumps(body).encode("utf-8") if body is not None else b""
    if body is not None and not any(k.lower() == "content-type" for k, _ in (headers or {}).items()):
        req_headers.append((b"content-type", b"application/json"))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
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


class WebSecurityTests(unittest.TestCase):
    def test_token_manager_lifecycle_and_tampering(self):
        manager = TokenManager("my-super-secret-key-32-bytes-long!")
        token = manager.create_token(user_id=42, username="alice", role="operator", expiry_minutes=60)
        self.assertIsInstance(token, str)

        payload = manager.decode_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["uid"], 42)
        self.assertEqual(payload["sub"], "alice")
        self.assertEqual(payload["role"], "operator")

        # Tampering with payload
        parts = token.split(".")
        tampered_token = f"{parts[0]}.{parts[1][:-2]}AA.{parts[2]}"
        self.assertIsNone(manager.decode_token(tampered_token))

        # Revocation
        self.assertFalse(manager.is_revoked(payload["jti"]))
        revoked = manager.revoke_token(token)
        self.assertTrue(revoked)
        self.assertTrue(manager.is_revoked(payload["jti"]))
        self.assertIsNone(manager.decode_token(token))

    def test_token_expiration(self):
        manager = TokenManager("my-super-secret-key-32-bytes-long!")
        # Expired token (-1 minute)
        expired_token = manager.create_token(user_id=1, username="admin", role="admin", expiry_minutes=-1)
        self.assertIsNone(manager.decode_token(expired_token))

    def test_rate_limiter_throttling(self):
        limiter = RateLimiter(max_attempts=3, window_seconds=10, lock_seconds=30)
        key = "127.0.0.1:testuser"

        # First 2 attempts allowed
        limiter.record_failure(key)
        limiter.record_failure(key)
        is_limited, _ = limiter.is_rate_limited(key)
        self.assertFalse(is_limited)

        # 3rd failure locks it
        limiter.record_failure(key)
        is_limited, retry_after = limiter.is_rate_limited(key)
        self.assertTrue(is_limited)
        self.assertGreater(retry_after, 0)

        # Success clears the lockout
        limiter.record_success(key)
        is_limited, _ = limiter.is_rate_limited(key)
        self.assertFalse(is_limited)

    def test_web_auth_endpoints_end_to_end(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "test_web.db"
            config = replace(
                AppConfig(),
                database_engine="sqlite",
                database_path=db_path,
                admin_username="testadmin",
                admin_password="Admin@TestPassword2025",
                operator_username="testop",
                operator_password="Operator@TestPassword2025",
                secret_key="unit-test-secret-key-for-web-session",
            )
            app = create_app(config)

            # 1. Login with invalid password
            status_code, _, body = asyncio.run(
                _run_asgi_request(
                    app,
                    "POST",
                    "/api/auth/login",
                    body={"username": "testadmin", "password": "WrongPassword!"},
                )
            )
            self.assertEqual(status_code, 401)

            # 2. Login with valid credentials
            status_code, headers, body = asyncio.run(
                _run_asgi_request(
                    app,
                    "POST",
                    "/api/auth/login",
                    body={"username": "testadmin", "password": "Admin@TestPassword2025"},
                )
            )
            self.assertEqual(status_code, 200)
            data = json.loads(body.decode("utf-8"))
            token = data["token"]
            self.assertIn("set-cookie", headers)
            self.assertIn("elh_session=", headers["set-cookie"])
            self.assertEqual(data["user"]["username"], "testadmin")
            self.assertEqual(data["user"]["role"], "admin")
            self.assertIn("x-content-type-options", headers)
            self.assertEqual(headers["x-content-type-options"], "nosniff")

            # 3. Access /api/auth/me with Bearer token
            status_code, _, body = asyncio.run(
                _run_asgi_request(
                    app,
                    "GET",
                    "/api/auth/me",
                    headers={"authorization": f"Bearer {token}"},
                )
            )
            self.assertEqual(status_code, 200)
            me_data = json.loads(body.decode("utf-8"))
            self.assertEqual(me_data["username"], "testadmin")

            # 4. Access /api/auth/me with Cookie
            status_code, _, body = asyncio.run(
                _run_asgi_request(
                    app,
                    "GET",
                    "/api/auth/me",
                    headers={"cookie": f"elh_session={token}"},
                )
            )
            self.assertEqual(status_code, 200)

            # 5. Refresh token
            status_code, headers, body = asyncio.run(
                _run_asgi_request(
                    app,
                    "POST",
                    "/api/auth/refresh",
                    headers={"authorization": f"Bearer {token}"},
                )
            )
            self.assertEqual(status_code, 200)
            refreshed_data = json.loads(body.decode("utf-8"))
            new_token = refreshed_data["token"]
            self.assertNotEqual(token, new_token)

            # 6. Logout revokes token
            status_code, _, _ = asyncio.run(
                _run_asgi_request(
                    app,
                    "POST",
                    "/api/auth/logout",
                    headers={"authorization": f"Bearer {new_token}"},
                )
            )
            self.assertEqual(status_code, 200)

            # Accessing after logout must be rejected with 401
            status_code, _, _ = asyncio.run(
                _run_asgi_request(
                    app,
                    "GET",
                    "/api/auth/me",
                    headers={"authorization": f"Bearer {new_token}"},
                )
            )
            self.assertEqual(status_code, 401)


if __name__ == "__main__":
    unittest.main()
