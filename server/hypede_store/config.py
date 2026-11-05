"""Настройки сервиса — из переменных окружения.

HYPEDE_STORE_DATA        каталог данных: база, файлы, картинки (./data)
HYPEDE_STORE_ORIGINS     адреса сайта, которым можно ходить в API с входом
                         (через запятую; https://extensions.hypede.xyz)
HYPEDE_STORE_MODERATORS  ники или адреса почты модераторов (через запятую)
HYPEDE_STORE_SECURE      1 — куки только по HTTPS (по умолчанию 1)
HYPEDE_STORE_PUBLIC_URL  внешний адрес API, для ссылок (https://api.extensions.hypede.xyz)
HYPEDE_STORE_CLAMAV      путь к clamdscan или clamscan; пусто — найти самому
"""

from __future__ import annotations

import os
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

    # Пределы.
    max_extension: int = 10 * 1024 * 1024
    max_theme: int = 64 * 1024 * 1024
    max_image: int = 8 * 1024 * 1024
    session_days: int = 30

    @property
    def db_path(self) -> Path:
        return self.data / "store.sqlite3"

    @property
    def files(self) -> Path:
        return self.data / "files"

    @property
    def media(self) -> Path:
        return self.data / "media"
