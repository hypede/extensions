"""Настройки сервиса — из переменных окружения.

HYPEDE_STORE_DATA        каталог данных: база, файлы, картинки (./data)
HYPEDE_STORE_ORIGINS     адреса сайта, которым можно ходить в API с входом
                         (через запятую; https://extensions.hypede.xyz)
HYPEDE_STORE_MODERATORS  ники или адреса почты модераторов (через запятую)
HYPEDE_STORE_SECURE      1 — куки только по HTTPS (по умолчанию 1)
HYPEDE_STORE_PUBLIC_URL  внешний адрес API, для ссылок (https://api.extensions.hypede.xyz)
HYPEDE_STORE_CLAMAV      путь к clamdscan или clamscan; пусто — найти самому
HYPEDE_STORE_SECRET      ключ подписи токенов входа (обязателен в бою)
HYPEDE_STORE_SCAN_TOKEN  ключ для проверки антивирусом из GitHub Actions
BLOB_READ_WRITE_TOKEN    задан — данные хранятся в Vercel Blob, а не на диске
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


def _list(name: str, default: str = "") -> list[str]:
    return [p.strip() for p in os.environ.get(name, default).split(",") if p.strip()]


@dataclass
class Config:
    data: Path = field(default_factory=lambda: Path(os.environ.get("HYPEDE_STORE_DATA", "data")).resolve())
    origins: list[str] = field(default_factory=lambda: _list(
        "HYPEDE_STORE_ORIGINS", "https://extensions.hypede.xyz,http://localhost:8000,http://127.0.0.1:8000"))
    moderators: list[str] = field(default_factory=lambda: [m.lower() for m in _list("HYPEDE_STORE_MODERATORS")])
    secure_cookies: bool = field(default_factory=lambda: os.environ.get("HYPEDE_STORE_SECURE", "1") != "0")
    public_url: str = field(default_factory=lambda: os.environ.get(
        "HYPEDE_STORE_PUBLIC_URL", "https://api.extensions.hypede.xyz").rstrip("/"))
    clamav: str = field(default_factory=lambda: os.environ.get("HYPEDE_STORE_CLAMAV", ""))
    # Без ключа в окружении — случайный: входы сбросятся при перезапуске.
    secret: str = field(default_factory=lambda: os.environ.get("HYPEDE_STORE_SECRET") or secrets.token_hex(32))
    scan_token: str = field(default_factory=lambda: os.environ.get("HYPEDE_STORE_SCAN_TOKEN", ""))

    # Пределы. На Vercel запрос и ответ функции — не больше 4,5 МБ, поэтому
    # файлы — до 4 МБ (расширениям хватает с запасом; темам — с обоями JPEG).
    max_extension: int = 4 * 1024 * 1024
    max_theme: int = 4 * 1024 * 1024
    max_image: int = 4 * 1024 * 1024
    session_days: int = 30
