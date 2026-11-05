"""Данные каталога поверх Storage: документы JSON и индексы к ним.

    users/<id>.json             аккаунт (почта, хеш пароля, ник, имя, фото, описание)
    index/email/<sha256>.json   почта → id пользователя
    index/handle/<ник>.json     ник → id пользователя
    index/owner/<id>.json       id работ пользователя
    items/<id>.json             расширение или тема со всеми версиями
    index/slug/<вид>/<имя>.json адрес на сайте → id работы
    index/uuid/<uuid>.json      uuid расширения → id работы
    catalog/<вид>.json          одобренные работы — то, что видит каталог
    queue.json                  версии, которые ждут модератора
    files/…, media/…            файлы версий, фото и картинки

Документов немного, писать в них редко (регистрация, публикация,
проверка), а каталог читается одним документом — это укладывается в
лимиты Vercel Blob. Одновременная запись двух людей в один индекс возможна,
но для каталога такого размера маловероятна; уникальность ника, почты и uuid
проверяется перед записью.
"""

from __future__ import annotations

import hashlib
import secrets
import time

from .storage import Storage


def now() -> int:
    return int(time.time())


def new_id() -> str:
    return secrets.token_hex(6)


def email_key(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()


class Repo:
    def __init__(self, storage: Storage):
        self.s = storage

    # ------------------------------------------------------------ аккаунты

    def user(self, uid: str):
        return self.s.get_json(f"users/{uid}.json") if uid and uid.isalnum() else None

    def _by_index(self, key: str):
        ref = self.s.get_json(key)
        return self.user(ref["id"]) if ref else None

    def user_by_handle(self, handle: str):
        return self._by_index(f"index/handle/{handle}.json")

    def user_by_email(self, email: str):
        return self._by_index(f"index/email/{email_key(email)}.json")

    def handle_taken(self, handle: str) -> bool:
        return self.s.get_json(f"index/handle/{handle}.json") is not None

    def email_taken(self, email: str) -> bool:
        return self.s.get_json(f"index/email/{email_key(email)}.json") is not None

    def create_user(self, email: str, password_hash: str, handle: str, display: str) -> dict:
        user = {"id": new_id(), "email": email, "password": password_hash, "handle": handle,
                "display_name": display, "bio": "", "avatar": "", "role": "user", "banned": False,
                "created_at": now(), "epoch": 0}
        self.s.put_json(f"users/{user['id']}.json", user)
        self.s.put_json(f"index/email/{email_key(email)}.json", {"id": user["id"]})
        self.s.put_json(f"index/handle/{handle}.json", {"id": user["id"]})
        return user

    def save_user(self, user: dict, old_handle: str | None = None) -> None:
        self.s.put_json(f"users/{user['id']}.json", user)
        if old_handle and old_handle != user["handle"]:
            self.s.put_json(f"index/handle/{user['handle']}.json", {"id": user["id"]})
            self.s.delete(f"index/handle/{old_handle}.json")
        # Имя, ник и фото автора показываются в каталоге — обновить там.
        for item in self.items_of(user["id"]):
            self.refresh_catalog(item)

    # --------------------------------------------------------------- работы

    def item(self, iid: str):
        return self.s.get_json(f"items/{iid}.json") if iid and iid.isalnum() else None

    def item_by_slug(self, kind: str, slug: str):
        ref = self.s.get_json(f"index/slug/{kind}/{slug}.json")
        return self.item(ref["id"]) if ref else None

    def uuid_owner(self, uuid: str):
        ref = self.s.get_json(f"index/uuid/{uuid}.json")
        return ref["id"] if ref else None

    def slug_taken(self, kind: str, slug: str) -> bool:
        return self.s.get_json(f"index/slug/{kind}/{slug}.json") is not None

    def items_of(self, uid: str) -> list[dict]:
        ids = self.s.get_json(f"index/owner/{uid}.json", {"items": []})["items"]
        return [i for i in (self.item(iid) for iid in ids) if i]

    def create_item(self, item: dict) -> dict:
        item["id"] = new_id()
        item.setdefault("versions", [])
        self.s.put_json(f"items/{item['id']}.json", item)
        self.s.put_json(f"index/slug/{item['kind']}/{item['slug']}.json", {"id": item["id"]})
        owned = self.s.get_json(f"index/owner/{item['owner_id']}.json", {"items": []})
        owned["items"].append(item["id"])
        self.s.put_json(f"index/owner/{item['owner_id']}.json", owned)
        return item

    def save_item(self, item: dict) -> None:
        item["updated_at"] = now()
        self.s.put_json(f"items/{item['id']}.json", item)
        if item.get("uuid"):
            self.s.put_json(f"index/uuid/{item['uuid']}.json", {"id": item["id"]})
        self.refresh_catalog(item)
        self.refresh_queue(item)

    def delete_item(self, item: dict) -> None:
        for v in item["versions"]:
            self.s.delete(v["file"])
        if item.get("preview"):
            self.s.delete(f"media/previews/{item['preview']}")
        self.s.delete(f"index/slug/{item['kind']}/{item['slug']}.json")
        if item.get("uuid"):
            self.s.delete(f"index/uuid/{item['uuid']}.json")
        owned = self.s.get_json(f"index/owner/{item['owner_id']}.json", {"items": []})
        owned["items"] = [i for i in owned["items"] if i != item["id"]]
        self.s.put_json(f"index/owner/{item['owner_id']}.json", owned)
        item["versions"] = []
        self.refresh_catalog(item, remove=True)
        self.refresh_queue(item)
        self.s.delete(f"items/{item['id']}.json")

    # ---------------------------------------------------- каталог и очередь

    @staticmethod
    def approved(item: dict):
        versions = [v for v in item.get("versions", []) if v["status"] == "approved"]
        return max(versions, key=lambda v: v["number"]) if versions else None

    def catalog(self, kind: str) -> list[dict]:
        return self.s.get_json(f"catalog/{kind}.json", {"items": []})["items"]

    def refresh_catalog(self, item: dict, remove: bool = False) -> None:
        """Запись работы в каталоге: краткие сведения и автор. Без одобренной
        версии или у заблокированного автора — работы в каталоге нет."""
        entries = [e for e in self.catalog(item["kind"]) if e["id"] != item["id"]]
        version = None if remove else self.approved(item)
        owner = self.user(item["owner_id"]) if version else None
        if version and owner and not owner.get("banned"):
            entries.append({"id": item["id"], "slug": item["slug"], "name": item["name"],
                            "summary": item["summary"], "preview": item.get("preview", ""),
                            "approved": version["reviewed_at"], "number": version["number"],
                            "owner": owner["id"], "handle": owner["handle"],
                            "display": owner["display_name"], "avatar": owner.get("avatar", "")})
        before = self.catalog(item["kind"])
        if entries != before:
            self.s.put_json(f"catalog/{item['kind']}.json", {"items": entries})

    def queue(self) -> list[dict]:
        return self.s.get_json("queue.json", {"pending": []})["pending"]

    def refresh_queue(self, item: dict) -> None:
        pending = [p for p in self.queue() if p["item"] != item["id"]]
        pending += [{"item": item["id"], "number": v["number"], "created": v["created_at"]}
                    for v in item.get("versions", []) if v["status"] == "pending"]
        pending.sort(key=lambda p: p["created"])
        if pending != self.queue():
            self.s.put_json("queue.json", {"pending": pending})
