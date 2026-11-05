"""Тесты API: python -m pytest server/tests (из корня репозитория)."""

import base64
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from hypede_store.app import create_app
from hypede_store.config import Config

H = {"X-HypeDE": "1"}


@pytest.fixture()
def make_client(tmp_path):
    def make():
        config = Config(data=tmp_path, origins=["https://extensions.hypede.xyz"], moderators=["boss"],
                        secure_cookies=False, public_url="http://testserver", clamav="")
        return TestClient(create_app(config))
    return make


def register(client, handle, email=None, password="correct horse battery"):
    r = client.post("/api/auth/register", headers=H, json={
        "email": email or f"{handle}@example.org", "password": password, "handle": handle,
        "displayName": handle.title()})
    assert r.status_code == 200, r.text
    return r.json()


def extension_zip(uuid="clock@example.org", extra=None, shell=("50", "51")):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("metadata.json", json.dumps({"uuid": uuid, "name": "Big Clock", "description": "A clock",
                                                "shell-version": list(shell)}))
        z.writestr("extension.js", "export default class X { enable() {} disable() {} }\n")
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return out.getvalue()


def png(size=(64, 48), color=(30, 120, 200)):
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return out.getvalue()


def theme_json(**extra):
    theme = {"hypede-theme": 1, "name": "Ocean", "author": "me", "colors": {"scheme": "prefer-dark",
             "accent": "#38bdf8"}, "shelf": {"style": "floating"}}
    theme.update(extra)
    return json.dumps(theme).encode()


def upload(client, kind, data, name="Big Clock", accept="true", filename=None):
    return client.post("/api/items", headers=H, data={
        "kind": kind, "name": name, "summary": "Short text", "description": "Long text", "license": "GPL-3.0",
        "accept_terms": accept}, files={"file": (filename or ("x.zip" if kind == "extension" else "t.json"), data),
                                        "preview": ("p.png", png())})


def test_account_flow(make_client):
    client = make_client()
    me = register(client, "anna")
    assert me["handle"] == "anna" and me["moderator"] is False
    assert client.get("/api/me").json()["handle"] == "anna"

    r = client.patch("/api/me", headers=H, json={"displayName": "Анна", "bio": "Делаю темы", "handle": "anna_k"})
    assert r.status_code == 200 and r.json()["displayName"] == "Анна" and r.json()["handle"] == "anna_k"

    r = client.post("/api/me/avatar", headers=H, files={"file": ("me.jpg", png((800, 600)))})
    assert r.status_code == 200
    avatar = client.get(r.json()["avatar"].replace("http://testserver", ""))
    assert avatar.status_code == 200 and Image.open(io.BytesIO(avatar.content)).size == (256, 256)

    assert client.post("/api/me/avatar", headers=H, files={"file": ("x.png", b"not an image")}).status_code == 400

    client.post("/api/auth/logout", headers=H)
    assert client.get("/api/me").json() == {"signedIn": False}
    assert client.post("/api/auth/login", headers=H, json={"login": "anna_k", "password": "wrong password!"}
                       ).status_code == 401
    assert client.post("/api/auth/login", headers=H, json={"login": "anna@example.org",
                                                           "password": "correct horse battery"}).status_code == 200


def test_registration_rules(make_client):
    client = make_client()
    bad = [{"email": "x", "password": "correct horse battery", "handle": "okname"},
           {"email": "a@b.cd", "password": "short", "handle": "okname"},
           {"email": "a@b.cd", "password": "correct horse battery", "handle": "Плохой ник"},
           {"email": "a@b.cd", "password": "correct horse battery", "handle": "admin"}]
    for body in bad:
        assert client.post("/api/auth/register", headers=H, json=body).status_code == 400
    register(client, "first")
    assert client.post("/api/auth/register", headers=H, json={
        "email": "first@example.org", "password": "correct horse battery", "handle": "second"}).status_code == 409


def test_csrf_header_required(make_client):
    client = make_client()
    r = client.post("/api/auth/register", json={"email": "a@b.cd", "password": "correct horse battery",
                                                "handle": "nohead"})
    assert r.status_code == 403


def test_extension_review_flow(make_client):
    author = make_client()
    register(author, "dev")
    r = upload(author, "extension", extension_zip(extra={"lib.js": "const p = new Gio.Subprocess({argv: ['ls']});"}))
    assert r.status_code == 200, r.text
    item = r.json()["item"]
    assert r.json()["version"]["status"] == "pending"
    warnings = r.json()["version"]["report"]["warnings"]
    assert any(w["what"] == "runs programs" and w["file"] == "lib.js" for w in warnings)
    assert r.json()["version"]["report"]["antivirus"] == "unavailable"

    # Пока не одобрено — в каталоге нет, скачать нельзя.
    anon = make_client()
    assert anon.get("/api/items?kind=extension").json()["items"] == []
    assert anon.get(f"/api/items/extension/{item['slug']}").status_code == 404
    assert anon.get(f"/api/items/{item['id']}/download").status_code == 404
    assert author.get(f"/api/items/extension/{item['slug']}").json()["versions"][0]["status"] == "pending"

    # Обычный пользователь не модератор.
    assert author.get("/api/mod/queue").status_code == 403

    boss = make_client()
    me = register(boss, "boss")
    assert me["moderator"] is True
    queue = boss.get("/api/mod/queue").json()["queue"]
    assert len(queue) == 1
    version_id = queue[0]["pending"]["id"]
    assert boss.post(f"/api/mod/versions/{version_id}/reject", headers=H, json={}).status_code == 400
    assert boss.post(f"/api/mod/versions/{version_id}/approve", headers=H, json={"note": "ok"}).status_code == 200

    listed = anon.get("/api/items?kind=extension").json()["items"]
    assert [i["slug"] for i in listed] == [item["slug"]]
    page = anon.get(f"/api/items/extension/{item['slug']}").json()
    assert "не несёт ответственности" in page["disclaimer"]["ru"]
    assert page["uuid"] == "clock@example.org"
    file = anon.get(f"/api/items/{item['id']}/download")
    assert file.status_code == 200 and file.headers["content-type"] == "application/zip"
    assert zipfile.ZipFile(io.BytesIO(file.content)).read("metadata.json")
    assert anon.get(f"/api/items/extension/{item['slug']}").json()["downloads"] == 1

    # Новая версия ждёт проверки, а старая остаётся доступной.
    r = author.post(f"/api/items/{item['id']}/versions", headers=H, data={"accept_terms": "true"},
                    files={"file": ("x.zip", extension_zip())})
    assert r.json()["status"] == "pending" and r.json()["number"] == 2
    assert anon.get(f"/api/items/extension/{item['slug']}").json()["version"]["number"] == 1

    # Чужой uuid в новой версии — нельзя.
    r = author.post(f"/api/items/{item['id']}/versions", headers=H, data={"accept_terms": "true"},
                    files={"file": ("x.zip", extension_zip(uuid="other@example.org"))})
    assert r.status_code == 400

    # Тот же uuid другим автором — нельзя.
    thief = make_client()
    register(thief, "thief")
    assert upload(thief, "extension", extension_zip(), name="Copy").status_code == 409


def test_bad_extensions_are_rejected(make_client):
    client = make_client()
    register(client, "dev2")
    assert upload(client, "extension", b"not a zip").status_code == 400
    assert upload(client, "extension", extension_zip(), accept="").status_code == 400
    assert upload(client, "extension", extension_zip(shell=("40",))).status_code == 400
    # Программа внутри — отклоняется автоматически.
    r = upload(client, "extension", extension_zip(uuid="elf@example.org", extra={"helper": b"\x7fELF\x02\x01\x01"}))
    assert r.status_code == 200 and r.json()["version"]["status"] == "rejected"
    assert "compiled program" in r.json()["version"]["note"]
    # Выход из архива (zip slip).
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("metadata.json", "{}")
        z.writestr("../evil.js", "x")
    assert upload(client, "extension", out.getvalue()).status_code == 400


def test_theme_flow(make_client):
    client = make_client()
    register(client, "artist")
    wallpaper = base64.b64encode(png((320, 200))).decode()
    r = upload(client, "theme", theme_json(files={"wall.png": wallpaper},
                                           wallpaper={"light": "wall.png", "dark": "wall.png"}), name="Ocean")
    assert r.status_code == 200, r.text
    assert r.json()["version"]["status"] == "pending"

    r = upload(client, "theme", theme_json(colors={"scheme": "default"}, extra_field=1), name="Bad")
    assert r.json()["version"]["status"] == "rejected"
    r = upload(client, "theme", theme_json(files={"evil.svg": base64.b64encode(
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>').decode()}), name="Evil")
    assert r.json()["version"]["status"] == "rejected"
    r = upload(client, "theme", theme_json(wallpaper={"light": "https://example.org/a.png"}), name="Remote")
    assert r.json()["version"]["status"] == "rejected"
    assert upload(client, "theme", b'{"name": "x"}', name="NotTheme").status_code == 400


def test_profile_page_shows_only_approved_to_others(make_client):
    author = make_client()
    register(author, "maker")
    upload(author, "theme", theme_json(), name="Pending One")
    anon = make_client()
    page = anon.get("/api/users/maker").json()
    assert page["user"]["displayName"] == "Maker" and page["items"] == []
    assert len(author.get("/api/users/maker").json()["items"]) == 1
    assert "email" not in page["user"]
