from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from elh.config import ROOT_DIR, AppConfig


def _b64url_encode(data: bytes) -> str:
    """Encode bytes to unpadded urlsafe base64 string."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    """Decode unpadded urlsafe base64 string to bytes."""
    rem = len(data) % 4
    if rem > 0:
        data += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data.encode("ascii"))


def resolve_secret_key(config: AppConfig | None = None) -> bytes:
    """Resolve a strong persistent secret key for signing session tokens."""
    if config and config.secret_key.strip():
        return config.secret_key.strip().encode("utf-8")

    key_file = ROOT_DIR / ".secret_key"
    if key_file.exists():
        try:
            stored = key_file.read_text(encoding="utf-8").strip()
            if len(stored) >= 32:
                return stored.encode("utf-8")
        except Exception:
            pass

    # Generate and persist a new strong 64-character hex key
    new_key = secrets.token_hex(32)
    try:
        key_file.write_text(new_key, encoding="utf-8")
    except Exception:
        pass
    return new_key.encode("utf-8")


class TokenManager:
    """Creates and verifies tamper-proof, time-bound session tokens (HMAC-SHA256)."""

    def __init__(self, secret_key: bytes | str | None = None):
        if isinstance(secret_key, str):
            self.secret_key = secret_key.encode("utf-8")
        elif isinstance(secret_key, bytes):
            self.secret_key = secret_key
        else:
            self.secret_key = resolve_secret_key()
        self._revoked_tokens: dict[str, float] = {}  # jti -> expiry timestamp

    def _cleanup_revoked(self) -> None:
        """Prune expired revoked tokens from memory."""
        now = time.time()
        self._revoked_tokens = {
            jti: exp for jti, exp in self._revoked_tokens.items() if exp > now
        }

    def create_token(
        self,
        user_id: int,
        username: str,
        role: str,
        expiry_minutes: int = 1440,
    ) -> str:
        """Generate a signed, expiring session token."""
        now = int(time.time())
        exp = now + int(expiry_minutes * 60)
        jti = secrets.token_hex(16)

        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "uid": int(user_id),
            "sub": username,
            "role": role,
            "iat": now,
            "exp": exp,
            "jti": jti,
        }

        header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        signature = hmac.new(self.secret_key, signing_input, hashlib.sha256).digest()
        signature_b64 = _b64url_encode(signature)

        return f"{header_b64}.{payload_b64}.{signature_b64}"

    def decode_token(self, token: str) -> dict[str, Any] | None:
        """Verify token signature, expiration, and revocation status."""
        if not token or not isinstance(token, str):
            return None

        parts = token.strip().split(".")
        if len(parts) != 3:
            return None

        header_b64, payload_b64, signature_b64 = parts

        try:
            signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
            expected_signature = hmac.new(self.secret_key, signing_input, hashlib.sha256).digest()
            actual_signature = _b64url_decode(signature_b64)

            if not hmac.compare_digest(expected_signature, actual_signature):
                return None

            payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        except Exception:
            return None

        now = time.time()
        if not isinstance(payload, dict):
            return None

        exp = payload.get("exp")
        if not isinstance(exp, (int, float)) or exp <= now:
            return None

        jti = payload.get("jti")
        if jti and self.is_revoked(jti):
            return None

        return payload

    def revoke_token(self, token: str) -> bool:
        """Revoke a token by its jti identifier."""
        payload = self.decode_token(token)
        if payload and "jti" in payload and "exp" in payload:
            self._cleanup_revoked()
            self._revoked_tokens[payload["jti"]] = float(payload["exp"])
            return True
        return False

    def is_revoked(self, jti: str) -> bool:
        """Check if token identifier has been revoked."""
        exp = self._revoked_tokens.get(jti)
        if exp is None:
            return False
        if exp <= time.time():
            self._revoked_tokens.pop(jti, None)
            return False
        return True


@dataclass
class RateLimitEntry:
    attempts: list[float]
    locked_until: float = 0.0


class RateLimiter:
    """Sliding window rate limiter to mitigate brute-force authentication attacks."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 60, lock_seconds: int = 300):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lock_seconds = lock_seconds
        self._entries: dict[str, RateLimitEntry] = {}

    def is_rate_limited(self, key: str) -> tuple[bool, int]:
        """Check if key is rate-limited. Returns (is_limited, retry_after_seconds)."""
        now = time.time()
        entry = self._entries.get(key)
        if not entry:
            return False, 0

        # Check explicit lock
        if entry.locked_until > now:
            return True, int(entry.locked_until - now) + 1

        # Prune older attempts
        entry.attempts = [t for t in entry.attempts if now - t < self.window_seconds]
        if len(entry.attempts) >= self.max_attempts:
            entry.locked_until = now + self.lock_seconds
            return True, self.lock_seconds

        return False, 0

    def record_failure(self, key: str) -> tuple[bool, int]:
        """Record a failed login attempt. Returns (is_now_limited, retry_after)."""
        now = time.time()
        if key not in self._entries:
            self._entries[key] = RateLimitEntry(attempts=[now])
        else:
            entry = self._entries[key]
            entry.attempts = [t for t in entry.attempts if now - t < self.window_seconds]
            entry.attempts.append(now)
            if len(entry.attempts) >= self.max_attempts:
                entry.locked_until = now + self.lock_seconds
                return True, self.lock_seconds
        return False, 0

    def record_success(self, key: str) -> None:
        """Clear rate limit entry on successful authentication."""
        self._entries.pop(key, None)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Applies secure HTTP headers to all incoming/outgoing responses."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
