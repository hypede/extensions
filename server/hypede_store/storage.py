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
    """Приватное хранилище Vercel Blob через его HTTP API."""

    API = "https://blob.vercel-storage.com"
    VERSION = "11"

    def __init__(self, token: str):
        self.token = token
        # vercel_blob_rw_<ид хранилища>_<секрет>
        parts = token.split("_")
        if len(parts) < 5 or parts[:3] != ["vercel", "blob", "rw"]:
            raise ValueError("BLOB_READ_WRITE_TOKEN does not look like a Vercel Blob token")
        self.store = parts[3].lower()
        self.base = f"https://{self.store}.private.blob.vercel-storage.com"

    def _request(self, method: str, url: str, data: bytes | None = None, headers: dict | None = None):
        request = urllib.request.Request(url, data=data, method=method, headers={
            "authorization": f"Bearer {self.token}", "x-api-version": self.VERSION, **(headers or {})})
        return urllib.request.urlopen(request, timeout=30)

    def get(self, key):
        url = f"{self.base}/{urllib.parse.quote(_safe(key))}"
        try:
            # Свежая копия, а не закэшированная: объекты перезаписываются.
            with self._request("GET", url, headers={"cache-control": "no-cache"}) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def put(self, key, data, content_type="application/octet-stream"):
        url = f"{self.API}/?pathname={urllib.parse.quote(_safe(key))}"
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
