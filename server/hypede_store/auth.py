"""Пароли, сессии и ограничение частоты запросов."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque

# scrypt из стандартной библиотеки: n=2^15 — около 50 мс на проверку.
_N, _R, _P = 1 << 15, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=128 * 1024 * 1024)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _algo, n, r, p, salt, digest = stored.split("$")
        expected = bytes.fromhex(digest)
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                                maxmem=128 * 1024 * 1024)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Токен входа без хранения на сервере: «id.эпоха.срок» с подписью HMAC.
# Эпоха лежит в аккаунте; «Выйти» и смена пароля увеличивают её, и все
# выданные раньше токены перестают действовать.

def make_token(secret: str, uid: str, epoch: int, days: int) -> str:
    payload = f"{uid}.{epoch}.{int(time.time()) + days * 86400}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=") + "." + signature


def read_token(secret: str, token: str) -> tuple[str, int] | None:
    try:
        encoded, signature = token.rsplit(".", 1)
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        uid, epoch, expires = payload.split(".")
        if int(expires) < time.time():
            return None
        return uid, int(epoch)
    except (ValueError, UnicodeDecodeError):
        return None


class RateLimiter:
    """Не больше limit событий за window секунд с одного адреса."""

    def __init__(self):
        self._events: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window: float) -> bool:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] > window:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            return True
