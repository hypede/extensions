"""База SQLite: пользователи, сессии, расширения и темы, их версии."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password      TEXT NOT NULL,
    handle        TEXT NOT NULL UNIQUE,          -- ник: латиница, цифры, _ и -
    display_name  TEXT NOT NULL,
    bio           TEXT NOT NULL DEFAULT '',
    avatar        TEXT NOT NULL DEFAULT '',      -- файл в media/avatars
    role          TEXT NOT NULL DEFAULT 'user',  -- user | moderator
    banned        INTEGER NOT NULL DEFAULT 0,
    created_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  INTEGER NOT NULL,
    expires_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id           INTEGER PRIMARY KEY,
    kind         TEXT NOT NULL,                  -- extension | theme
    slug         TEXT NOT NULL,
    owner_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    summary      TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    homepage     TEXT NOT NULL DEFAULT '',
    license      TEXT NOT NULL DEFAULT '',
    preview      TEXT NOT NULL DEFAULT '',       -- файл в media/previews
    uuid         TEXT NOT NULL DEFAULT '',       -- у расширений — из metadata.json
    downloads    INTEGER NOT NULL DEFAULT 0,
    created_at   INTEGER NOT NULL,
    updated_at   INTEGER NOT NULL,
    UNIQUE (kind, slug)
);
CREATE UNIQUE INDEX IF NOT EXISTS items_uuid ON items(uuid) WHERE uuid != '';

CREATE TABLE IF NOT EXISTS versions (
    id           INTEGER PRIMARY KEY,
    item_id      INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    number       INTEGER NOT NULL,
    file         TEXT NOT NULL,                  -- файл в files/
    sha256       TEXT NOT NULL,
    size         INTEGER NOT NULL,
    meta         TEXT NOT NULL DEFAULT '{}',     -- metadata.json или сведения темы
    report       TEXT NOT NULL DEFAULT '{}',     -- итог автоматической проверки
    status       TEXT NOT NULL,                  -- pending | approved | rejected
    note         TEXT NOT NULL DEFAULT '',       -- что написал модератор
    reviewer_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    terms_at     INTEGER NOT NULL,               -- когда автор принял условия
    created_at   INTEGER NOT NULL,
    reviewed_at  INTEGER,
    UNIQUE (item_id, number)
);
CREATE INDEX IF NOT EXISTS versions_status ON versions(status);
"""


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self.path = path
        with self.connect() as db:
            db.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=15, isolation_level=None, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn = conn
        return conn

    def one(self, sql: str, *args):
        return self.connect().execute(sql, args).fetchone()

    def all(self, sql: str, *args):
        return self.connect().execute(sql, args).fetchall()

    def run(self, sql: str, *args) -> int:
        cur = self.connect().execute(sql, args)
        return cur.lastrowid


def now() -> int:
    return int(time.time())
