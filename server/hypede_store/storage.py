"""Где лежат данные: на диске (Docker, свой сервер, тесты) или в Vercel Blob.

У Vercel нет постоянного диска, поэтому там всё — аккаунты, расширения,
темы, файлы и картинки — хранится объектами в приватном хранилище Vercel
Blob. Интерфейс один: get/put/delete по ключу вроде «users/ab12.json».

Vercel Blob выбирается сам, если задан BLOB_READ_WRITE_TOKEN (Vercel
добавляет его, когда хранилище подключено к проекту).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class Storage:
    def get(self, key: str) -> bytes | None:
        raise NotImplementedError

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def get_json(self, key: str, default=None):
        raw = self.get(key)
        if raw is None:
            return default
        return json.loads(raw.decode("utf-8"))

    def put_json(self, key: str, value) -> None:
        self.put(key, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json")


def _safe(key: str) -> str:
    parts = key.split("/")
    if not key or key.startswith("/") or any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"bad storage key: {key!r}")
    return key


class LocalStorage(Storage):
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / _safe(key)

    def get(self, key):
        path = self._path(key)
        return path.read_bytes() if path.is_file() else None

    def put(self, key, data, content_type="application/octet-stream"):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)


class BlobStorage(Storage):
    """Приватное хранилище Vercel Blob через его HTTP API — так же, как это
    делает официальный клиент @vercel/blob (версия API 13)."""

    API = "https://vercel.com/api/blob"
    VERSION = "13"

    def __init__(self, token: str):
        self.token = token
        # vercel_blob_rw_<ид хранилища>_<секрет>
        parts = token.split("_")
        if len(parts) < 5 or parts[:3] != ["vercel", "blob", "rw"]:
            raise ValueError("BLOB_READ_WRITE_TOKEN does not look like a Vercel Blob token")
        self.store = parts[3]
        self.base = f"https://{self.store}.private.blob.vercel-storage.com"

    def _request(self, method: str, url: str, data: bytes | None = None, headers: dict | None = None):
        request = urllib.request.Request(url, data=data, method=method, headers={
            "authorization": f"Bearer {self.token}", "x-api-version": self.VERSION,
            "x-vercel-blob-store-id": self.store, **(headers or {})})
        return urllib.request.urlopen(request, timeout=30)

    def get(self, key):
        # cache=0 — свежая копия, а не закэшированная: документы перезаписываются.
        url = f"{self.base}/{urllib.parse.quote(_safe(key))}?cache=0"
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    url, headers={"authorization": f"Bearer {self.token}"}), timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def put(self, key, data, content_type="application/octet-stream"):
        url = f"{self.API}/?{urllib.parse.urlencode({'pathname': _safe(key)})}"
        with self._request("PUT", url, data=data, headers={
                "x-content-type": content_type, "x-add-random-suffix": "0", "x-allow-overwrite": "1",
                "x-vercel-blob-access": "private", "x-cache-control-max-age": "60"}) as response:
            response.read()

    def delete(self, key):
        body = json.dumps({"urls": [f"{self.base}/{urllib.parse.quote(_safe(key))}"]}).encode()
        try:
            with self._request("POST", f"{self.API}/delete", data=body,
                               headers={"content-type": "application/json"}) as response:
                response.read()
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise


def from_env(data_dir: Path) -> Storage:
    token = os.environ.get("BLOB_READ_WRITE_TOKEN", "")
    return BlobStorage(token) if token else LocalStorage(data_dir)
