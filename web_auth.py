"""Minimal signed web sessions and per-IP login throttling.

The operator username and randomly generated admin token are stored in secrets.json.
No token is embedded into regular page links or browser-side JavaScript.
"""
from __future__ import annotations

from http.cookies import SimpleCookie
import hashlib
import hmac
import secrets
import threading
import time

COOKIE_NAME = "ok5tvr_session"
SESSION_SECONDS = 12 * 60 * 60


class SessionAuth:
    def __init__(self, signing_secret: str):
        self.secret = hashlib.sha256(
            b"ok5tvr-aprs-web-session-v1\0" + signing_secret.encode("ascii")
        ).digest()

    def issue(self, now: int | None = None) -> str:
        expiry = int(time.time() if now is None else now) + SESSION_SECONDS
        nonce = secrets.token_hex(12)
        payload = f"{expiry}.{nonce}"
        digest = hmac.new(self.secret, payload.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{payload}.{digest}"

    def verify(self, token: str, now: int | None = None) -> bool:
        if not isinstance(token, str) or len(token) > 160:
            return False
        try:
            stamp, nonce, digest = token.split(".")
            expiry = int(stamp)
            if len(nonce) != 24 or len(digest) != 64 or not nonce.isascii():
                return False
            if any(x not in "0123456789abcdef" for x in nonce + digest):
                return False
            current = int(time.time() if now is None else now)
            if expiry <= current or expiry > current + SESSION_SECONDS:
                return False
        except (ValueError, AttributeError):
            return False
        expected = hmac.new(self.secret, f"{stamp}.{nonce}".encode("ascii"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest, expected)

    def from_header(self, header: str, now: int | None = None) -> bool:
        if not header or len(header) > 4096:
            return False
        cookies = SimpleCookie()
        try:
            cookies.load(header)
            item = cookies.get(COOKIE_NAME)
            return bool(item and self.verify(item.value, now))
        except (ValueError, TypeError):
            return False

    @staticmethod
    def cookie(value: str) -> str:
        return (f"{COOKIE_NAME}={value}; Path=/; Max-Age={SESSION_SECONDS}; "
                "HttpOnly; SameSite=Strict")

    @staticmethod
    def clear_cookie() -> str:
        return f"{COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"


class LoginThrottle:
    """Fail closed after six invalid attempts from the same address in 2 min."""
    def __init__(self):
        self._lock = threading.Lock()
        self._attempts: dict[str, list[float]] = {}

    def allowed(self, ip: str) -> bool:
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._attempts.get(ip, []) if now - t < 120]
            if recent:
                self._attempts[ip] = recent
            else:
                self._attempts.pop(ip, None)
            return len(recent) < 6

    def failure(self, ip: str) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._attempts) > 256:
                self._attempts = {
                    key: [t for t in values if now - t < 120]
                    for key, values in self._attempts.items()
                    if any(now - t < 120 for t in values)
                }
            recent = [t for t in self._attempts.get(ip, []) if now - t < 120]
            self._attempts[ip] = recent + [now]

    def success(self, ip: str) -> None:
        with self._lock:
            self._attempts.pop(ip, None)
