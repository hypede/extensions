"""API extensions.hypede.xyz: аккаунты, расширения и темы, проверка.

Сайт (статичные страницы на GitHub Pages) ходит сюда с куки сессии.
Изменяющие запросы требуют заголовок X-HypeDE: 1 — чужой сайт не может его
поставить без разрешения CORS, так что подделать запрос от вашего имени
нельзя (CSRF).

Путь загрузки: автор принимает условия → файл проверяется автоматически
(checks.py) → версия ждёт модератора (pending) → модератор одобряет или
отклоняет с пояснением. Публично видны и скачиваются только одобренные
версии; прошлая одобренная версия остаётся доступной, пока новая на
проверке.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import unicodedata
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import checks
from .auth import RateLimiter, check_password, hash_password, new_token, token_hash
from .config import Config
from .db import Database, now

COOKIE = "hypede_session"
HANDLE = re.compile(r"^[a-z0-9_-]{3,24}$")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$")
RESERVED = {"admin", "hypede", "moderator", "support", "root", "system", "api", "official", "help", "staff"}
KINDS = {"extension", "theme"}

DISCLAIMER = {
    "en": "Extensions and themes are made by users. They are checked by an antivirus and by a person before "
          "they appear here, but HypeDE is not responsible for your system: you install them at your own risk.",
    "ru": "Расширения и темы создают пользователи. Прежде чем появиться здесь, они проходят проверку "
          "антивирусом и вручную, но HypeDE не несёт ответственности за вашу систему: устанавливаете вы их "
          "на свой риск.",
}


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:48] or "item"


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    for path in (config.files, config.media / "avatars", config.media / "previews"):
        path.mkdir(parents=True, exist_ok=True)
    db = Database(config.db_path)
    limiter = RateLimiter()
    app = FastAPI(title="HypeDE Extensions API", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config
    app.state.db = db
    app.add_middleware(CORSMiddleware, allow_origins=config.origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["X-HypeDE", "Content-Type"],
                       max_age=600)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-hypede") != "1":
            return JSONResponse({"error": "missing X-HypeDE header"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; frame-ancestors 'none'"
        return response

    # ------------------------------------------------------------ помощники

    def client(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for", "")
        return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "?")

    def limit(request: Request, what: str, count: int, window: float) -> None:
        if not limiter.allow(f"{what}:{client(request)}", count, window):
            raise HTTPException(429, "too many requests, try again later")

    def current_user(request: Request):
        token = request.cookies.get(COOKIE)
        if not token:
            return None
        row = db.one("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                     "WHERE s.token_hash = ? AND s.expires_at > ?", token_hash(token), now())
        if row is None or row["banned"]:
            return None
        return row

    def require_user(user=Depends(current_user)):
        if user is None:
            raise HTTPException(401, "sign in first")
        return user

    def is_moderator(user) -> bool:
        return user is not None and (user["role"] == "moderator" or user["handle"].lower() in config.moderators
                                     or user["email"].lower() in config.moderators)

    def require_moderator(user=Depends(require_user)):
        if not is_moderator(user):
            raise HTTPException(403, "only moderators can do this")
        return user

    def avatar_url(name: str) -> str:
        return f"{config.public_url}/media/avatars/{name}" if name else ""

    def profile(user, private: bool = False) -> dict:
        data = {"handle": user["handle"], "displayName": user["display_name"], "bio": user["bio"],
                "avatar": avatar_url(user["avatar"]), "joined": user["created_at"]}
        if private:
            data.update(email=user["email"], moderator=is_moderator(user))
        return data

    def start_session(response: Response, user_id: int) -> None:
        token, hashed = new_token()
        db.run("INSERT INTO sessions VALUES (?, ?, ?, ?)", hashed, user_id, now(),
               now() + config.session_days * 86400)
        response.set_cookie(COOKIE, token, max_age=config.session_days * 86400, httponly=True,
                            secure=config.secure_cookies, samesite="lax", path="/")

    async def read_upload(upload: UploadFile, limit_bytes: int, what: str) -> bytes:
        data = await upload.read(limit_bytes + 1)
        if len(data) > limit_bytes:
            raise HTTPException(413, f"{what} is larger than {limit_bytes >> 20} MB")
        if not data:
            raise HTTPException(400, f"{what} is empty")
        return data

    def item_view(row, version=None, viewer=None) -> dict:
        owner = db.one("SELECT * FROM users WHERE id = ?", row["owner_id"])
        data = {
            "id": row["id"], "kind": row["kind"], "slug": row["slug"], "name": row["name"],
            "summary": row["summary"], "description": row["description"], "homepage": row["homepage"],
            "license": row["license"], "uuid": row["uuid"], "downloads": row["downloads"],
            "preview": f"{config.public_url}/media/previews/{row['preview']}" if row["preview"] else "",
            "author": profile(owner) if owner else None, "updated": row["updated_at"],
        }
        if version is not None:
            data["version"] = {"number": version["number"], "sha256": version["sha256"], "size": version["size"],
                               "meta": json.loads(version["meta"]), "approved": version["reviewed_at"],
                               "download": f"{config.public_url}/api/items/{row['id']}/download"}
        if viewer is not None and (viewer["id"] == row["owner_id"] or is_moderator(viewer)):
            data["versions"] = [version_view(v) for v in db.all(
                "SELECT * FROM versions WHERE item_id = ? ORDER BY number DESC", row["id"])]
        return data

    def version_view(v) -> dict:
        return {"id": v["id"], "number": v["number"], "status": v["status"], "note": v["note"],
                "report": json.loads(v["report"]), "meta": json.loads(v["meta"]), "sha256": v["sha256"],
                "size": v["size"], "created": v["created_at"], "reviewed": v["reviewed_at"]}

    def latest_approved(item_id: int):
        return db.one("SELECT * FROM versions WHERE item_id = ? AND status = 'approved' "
                      "ORDER BY number DESC LIMIT 1", item_id)

    # --------------------------------------------------------------- общее

    @app.get("/api/info")
    def info():
        return {"disclaimer": DISCLAIMER, "kinds": sorted(KINDS), "shellVersions": sorted(checks.SUPPORTED_SHELL),
                "limits": {"extension": config.max_extension, "theme": config.max_theme,
                           "image": config.max_image}}

    # ------------------------------------------------------------- аккаунт

    @app.post("/api/auth/register")
    async def register(request: Request, response: Response):
        limit(request, "register-try", 30, 3600)
        body = await request.json()
        email = str(body.get("email", "")).strip().lower()
        password = str(body.get("password", ""))
        handle = str(body.get("handle", "")).strip().lower()
        display = str(body.get("displayName", "")).strip() or handle
        if not EMAIL.match(email):
            raise HTTPException(400, "enter a valid email")
        if len(password) < 10 or len(password) > 200:
            raise HTTPException(400, "the password must be at least 10 characters")
        if not HANDLE.match(handle) or handle in RESERVED:
            raise HTTPException(400, "the nickname must be 3–24 Latin letters, digits, _ or -")
        if len(display) > 60:
            raise HTTPException(400, "the name is too long")
        if db.one("SELECT 1 FROM users WHERE email = ?", email):
            raise HTTPException(409, "this email is already registered")
        if db.one("SELECT 1 FROM users WHERE handle = ?", handle):
            raise HTTPException(409, "this nickname is taken")
        # Не больше пяти новых аккаунтов в час с одного адреса.
        limit(request, "register", 5, 3600)
        user_id = db.run("INSERT INTO users (email, password, handle, display_name, created_at) "
                         "VALUES (?, ?, ?, ?, ?)", email, hash_password(password), handle, display, now())
        start_session(response, user_id)
        return profile(db.one("SELECT * FROM users WHERE id = ?", user_id), private=True)

    @app.post("/api/auth/login")
    async def login(request: Request, response: Response):
        limit(request, "login", 10, 600)
        body = await request.json()
        login_id = str(body.get("login", "")).strip().lower()
        user = db.one("SELECT * FROM users WHERE email = ? OR handle = ?", login_id, login_id)
        # Хеш считается и для несуществующего пользователя — по времени
        # ответа нельзя узнать, есть ли такой адрес.
        stored = user["password"] if user else hash_password(secrets.token_hex(8))
        if not check_password(str(body.get("password", "")), stored) or user is None:
            raise HTTPException(401, "wrong email, nickname or password")
        if user["banned"]:
            raise HTTPException(403, "this account is blocked")
        start_session(response, user["id"])
        return profile(user, private=True)

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        token = request.cookies.get(COOKIE)
        if token:
            db.run("DELETE FROM sessions WHERE token_hash = ?", token_hash(token))
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/me")
    def me(user=Depends(current_user)):
        return profile(user, private=True) if user else {"signedIn": False}

    @app.patch("/api/me")
    async def update_me(request: Request, user=Depends(require_user)):
        body = await request.json()
        fields = {}
        if "displayName" in body:
            display = str(body["displayName"]).strip()
            if not 1 <= len(display) <= 60:
                raise HTTPException(400, "the name must be 1–60 characters")
            fields["display_name"] = display
        if "bio" in body:
            bio = str(body["bio"]).strip()
            if len(bio) > 500:
                raise HTTPException(400, "the description is longer than 500 characters")
            fields["bio"] = bio
        if "handle" in body:
            handle = str(body["handle"]).strip().lower()
            if not HANDLE.match(handle) or handle in RESERVED:
                raise HTTPException(400, "the nickname must be 3–24 Latin letters, digits, _ or -")
            if handle != user["handle"] and db.one("SELECT 1 FROM users WHERE handle = ?", handle):
                raise HTTPException(409, "this nickname is taken")
            fields["handle"] = handle
        if "password" in body:
            if not check_password(str(body.get("currentPassword", "")), user["password"]):
                raise HTTPException(403, "the current password is wrong")
            password = str(body["password"])
            if len(password) < 10:
                raise HTTPException(400, "the password must be at least 10 characters")
            fields["password"] = hash_password(password)
        for column, value in fields.items():
            db.run(f"UPDATE users SET {column} = ? WHERE id = ?", value, user["id"])  # column — из списка выше
        return profile(db.one("SELECT * FROM users WHERE id = ?", user["id"]), private=True)

    @app.post("/api/me/avatar")
    async def upload_avatar(request: Request, file: UploadFile = File(...), user=Depends(require_user)):
        limit(request, "avatar", 20, 3600)
        raw = await read_upload(file, config.max_image, "the photo")
        try:
            png = checks.reencode_image(raw, 256, square=True)
        except checks.CheckError as e:
            raise HTTPException(400, str(e))
        name = f"{user['id']}-{secrets.token_hex(6)}.png"
        (config.media / "avatars" / name).write_bytes(png)
        if user["avatar"]:
            (config.media / "avatars" / user["avatar"]).unlink(missing_ok=True)
        db.run("UPDATE users SET avatar = ? WHERE id = ?", name, user["id"])
        return {"avatar": avatar_url(name)}

    @app.delete("/api/me/avatar")
    def delete_avatar(user=Depends(require_user)):
        if user["avatar"]:
            (config.media / "avatars" / user["avatar"]).unlink(missing_ok=True)
        db.run("UPDATE users SET avatar = '' WHERE id = ?", user["id"])
        return {"avatar": ""}

    @app.get("/api/users/{handle}")
    def user_page(handle: str, viewer=Depends(current_user)):
        user = db.one("SELECT * FROM users WHERE handle = ? AND banned = 0", handle.lower())
        if user is None:
            raise HTTPException(404, "no such user")
        items = []
        for row in db.all("SELECT * FROM items WHERE owner_id = ? ORDER BY updated_at DESC", user["id"]):
            version = latest_approved(row["id"])
            own = viewer is not None and viewer["id"] == user["id"]
            if version is not None or own:
                items.append(item_view(row, version, viewer))
        return {"user": profile(user), "items": items}

    @app.get("/media/{folder}/{name}")
    def media(folder: str, name: str):
        if folder not in ("avatars", "previews") or not re.fullmatch(r"[0-9a-f-]+\.png|\d+-[0-9a-f]+\.png", name):
            raise HTTPException(404, "not found")
        path = config.media / folder / name
        if not path.is_file():
            raise HTTPException(404, "not found")
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})

    # --------------------------------------------------------------- каталог

    @app.get("/api/items")
    def list_items(kind: str = Query("extension"), q: str = Query("", max_length=80),
                   sort: str = Query("popular"), page: int = Query(1, ge=1, le=500)):
        if kind not in KINDS:
            raise HTTPException(400, "unknown kind")
        order = {"popular": "i.downloads DESC", "new": "v.reviewed_at DESC", "name": "i.name COLLATE NOCASE"}
        sql = ("SELECT i.*, MAX(v.number) AS approved_number FROM items i JOIN versions v ON v.item_id = i.id "
               "AND v.status = 'approved' JOIN users u ON u.id = i.owner_id AND u.banned = 0 WHERE i.kind = ?")
        args: list = [kind]
        if q.strip():
            sql += " AND (i.name LIKE ? OR i.summary LIKE ? OR u.handle LIKE ?)"
            like = f"%{q.strip()}%"
            args += [like, like, like]
        sql += f" GROUP BY i.id ORDER BY {order.get(sort, order['popular'])} LIMIT 30 OFFSET ?"
        args.append((page - 1) * 30)
        result = []
        for row in db.all(sql, *args):
            result.append(item_view(row, latest_approved(row["id"])))
        return {"items": result, "page": page}

    def find_item(kind: str, slug: str):
        row = db.one("SELECT * FROM items WHERE kind = ? AND slug = ?", kind, slug)
        if row is None:
            raise HTTPException(404, "not found")
        return row

    # Раньше /api/items/{kind}/{slug}: иначе «1/download» принимался бы за
    # вид «1» и имя «download».
    @app.get("/api/items/{item_id}/download")
    def download(item_id: int, version: int | None = None, viewer=Depends(current_user)):
        row = db.one("SELECT * FROM items WHERE id = ?", item_id)
        if row is None:
            raise HTTPException(404, "not found")
        privileged = viewer is not None and (viewer["id"] == row["owner_id"] or is_moderator(viewer))
        if version is not None and privileged:
            v = db.one("SELECT * FROM versions WHERE item_id = ? AND number = ?", item_id, version)
        else:
            v = latest_approved(item_id)
        if v is None:
            raise HTTPException(404, "no approved version yet")
        if v["status"] == "approved":
            db.run("UPDATE items SET downloads = downloads + 1 WHERE id = ?", item_id)
        if row["kind"] == "extension":
            filename, media_type = f"{row['uuid'] or row['slug']}.zip", "application/zip"
        else:
            filename, media_type = f"{row['slug']}.json", "application/json"
        return FileResponse(config.files / v["file"], media_type=media_type, filename=filename,
                            headers={"X-Checksum-SHA256": v["sha256"]})

    @app.get("/api/items/{kind}/{slug}")
    def item_page(kind: str, slug: str, viewer=Depends(current_user)):
        row = find_item(kind, slug)
        version = latest_approved(row["id"])
        if version is None and not (viewer and (viewer["id"] == row["owner_id"] or is_moderator(viewer))):
            raise HTTPException(404, "not found")
        data = item_view(row, version, viewer)
        data["disclaimer"] = DISCLAIMER
        return data

    # ------------------------------------------------------------- загрузка

    async def save_version(request, item, user, upload, accept_terms) -> dict:
        if accept_terms not in ("true", "1", "on", "yes"):
            raise HTTPException(400, "you have to accept the terms")
        limit(request, "upload", 20, 3600)
        if item["kind"] == "extension":
            raw = await read_upload(upload, config.max_extension, "the archive")
            try:
                meta, report = checks.check_extension(raw, config.clamav)
            except checks.CheckError as e:
                raise HTTPException(400, str(e))
            if item["uuid"] and meta["uuid"] != item["uuid"]:
                raise HTTPException(400, f"the uuid must stay {item['uuid']}")
            other = db.one("SELECT id FROM items WHERE uuid = ? AND id != ?", meta["uuid"], item["id"])
            if other:
                raise HTTPException(409, "an extension with this uuid is already published by someone else")
            suffix = ".zip"
        else:
            raw = await read_upload(upload, config.max_theme, "the theme file")
            try:
                meta, report = checks.check_theme(raw, config.clamav)
            except checks.CheckError as e:
                raise HTTPException(400, str(e))
            suffix = ".json"
        digest = hashlib.sha256(raw).hexdigest()
        name = f"{item['id']}-{secrets.token_hex(8)}{suffix}"
        (config.files / name).write_bytes(raw)
        number = (db.one("SELECT MAX(number) AS n FROM versions WHERE item_id = ?", item["id"])["n"] or 0) + 1
        status = "rejected" if report["errors"] else "pending"
        note = "Automatic check: " + "; ".join(report["errors"])[:900] if report["errors"] else ""
        db.run("INSERT INTO versions (item_id, number, file, sha256, size, meta, report, status, note, terms_at, "
               "created_at, reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               item["id"], number, name, digest, len(raw), json.dumps(meta), json.dumps(report), status, note,
               now(), now(), now() if status == "rejected" else None)
        if item["kind"] == "extension" and not item["uuid"]:
            db.run("UPDATE items SET uuid = ? WHERE id = ?", meta["uuid"], item["id"])
        db.run("UPDATE items SET updated_at = ? WHERE id = ?", now(), item["id"])
        return {"number": number, "status": status, "note": note, "report": report}

    async def save_preview(item_id: int, upload: UploadFile | None) -> None:
        if upload is None or not upload.filename:
            return
        raw = await read_upload(upload, config.max_image, "the picture")
        try:
            png = checks.reencode_image(raw, 1280)
        except checks.CheckError as e:
            raise HTTPException(400, str(e))
        name = f"{item_id}-{secrets.token_hex(6)}.png"
        (config.media / "previews" / name).write_bytes(png)
        old = db.one("SELECT preview FROM items WHERE id = ?", item_id)["preview"]
        if old:
            (config.media / "previews" / old).unlink(missing_ok=True)
        db.run("UPDATE items SET preview = ? WHERE id = ?", name, item_id)

    def clean_text(value: str, maximum: int, what: str, required: bool = False) -> str:
        value = (value or "").strip()
        if required and not value:
            raise HTTPException(400, f"{what} is required")
        if len(value) > maximum:
            raise HTTPException(400, f"{what} is longer than {maximum} characters")
        return value

    def clean_url(value: str) -> str:
        value = (value or "").strip()
        if value and not re.match(r"^https://[^\s<>\"']{3,300}$", value):
            raise HTTPException(400, "the homepage must be an https:// address")
        return value

    @app.post("/api/items")
    async def create_item(request: Request, kind: str = Form(...), name: str = Form(...),
                          summary: str = Form(...), description: str = Form(""), homepage: str = Form(""),
                          license: str = Form(""), accept_terms: str = Form(""), file: UploadFile = File(...),
                          preview: UploadFile | None = File(None), user=Depends(require_user)):
        if kind not in KINDS:
            raise HTTPException(400, "unknown kind")
        name = clean_text(name, 60, "the name", True)
        summary = clean_text(summary, 140, "the short description", True)
        description = clean_text(description, 5000, "the description")
        license = clean_text(license, 60, "the license")
        homepage = clean_url(homepage)
        base = slugify(name)
        slug, n = base, 2
        while db.one("SELECT 1 FROM items WHERE kind = ? AND slug = ?", kind, slug):
            slug, n = f"{base}-{n}", n + 1
        item_id = db.run("INSERT INTO items (kind, slug, owner_id, name, summary, description, homepage, license, "
                         "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", kind, slug, user["id"],
                         name, summary, description, homepage, license, now(), now())
        item = db.one("SELECT * FROM items WHERE id = ?", item_id)
        try:
            version = await save_version(request, item, user, file, accept_terms)
            await save_preview(item_id, preview)
        except HTTPException:
            for v in db.all("SELECT file FROM versions WHERE item_id = ?", item_id):
                (config.files / v["file"]).unlink(missing_ok=True)
            db.run("DELETE FROM items WHERE id = ?", item_id)
            raise
        return {"item": item_view(db.one("SELECT * FROM items WHERE id = ?", item_id), None, user),
                "version": version}

    def own_item(item_id: int, user):
        row = db.one("SELECT * FROM items WHERE id = ?", item_id)
        if row is None or (row["owner_id"] != user["id"] and not is_moderator(user)):
            raise HTTPException(404, "not found")
        return row

    @app.post("/api/items/{item_id}/versions")
    async def new_version(request: Request, item_id: int, accept_terms: str = Form(""),
                          file: UploadFile = File(...), user=Depends(require_user)):
        item = own_item(item_id, user)
        return await save_version(request, item, user, file, accept_terms)

    @app.patch("/api/items/{item_id}")
    async def edit_item(request: Request, item_id: int, name: str = Form(None), summary: str = Form(None),
                        description: str = Form(None), homepage: str = Form(None), license: str = Form(None),
                        preview: UploadFile | None = File(None), user=Depends(require_user)):
        item = own_item(item_id, user)
        updates = {}
        if name is not None:
            updates["name"] = clean_text(name, 60, "the name", True)
        if summary is not None:
            updates["summary"] = clean_text(summary, 140, "the short description", True)
        if description is not None:
            updates["description"] = clean_text(description, 5000, "the description")
        if homepage is not None:
            updates["homepage"] = clean_url(homepage)
        if license is not None:
            updates["license"] = clean_text(license, 60, "the license")
        for column, value in updates.items():
            db.run(f"UPDATE items SET {column} = ?, updated_at = ? WHERE id = ?", value, now(), item["id"])
        await save_preview(item["id"], preview)
        return item_view(db.one("SELECT * FROM items WHERE id = ?", item["id"]), latest_approved(item["id"]), user)

    @app.delete("/api/items/{item_id}")
    def delete_item(item_id: int, user=Depends(require_user)):
        item = own_item(item_id, user)
        for v in db.all("SELECT file FROM versions WHERE item_id = ?", item["id"]):
            (config.files / v["file"]).unlink(missing_ok=True)
        if item["preview"]:
            (config.media / "previews" / item["preview"]).unlink(missing_ok=True)
        db.run("DELETE FROM items WHERE id = ?", item["id"])
        return {"ok": True}

    @app.get("/api/my/items")
    def my_items(user=Depends(require_user)):
        rows = db.all("SELECT * FROM items WHERE owner_id = ? ORDER BY updated_at DESC", user["id"])
        return {"items": [item_view(r, latest_approved(r["id"]), user) for r in rows]}

    # ------------------------------------------------------------ модерация

    @app.get("/api/mod/queue")
    def queue(user=Depends(require_moderator)):
        result = []
        for v in db.all("SELECT * FROM versions WHERE status = 'pending' ORDER BY created_at"):
            item = db.one("SELECT * FROM items WHERE id = ?", v["item_id"])
            data = item_view(item, None, user)
            data["pending"] = version_view(v)
            result.append(data)
        return {"queue": result}

    @app.post("/api/mod/versions/{version_id}/{decision}")
    async def review(request: Request, version_id: int, decision: str, user=Depends(require_moderator)):
        if decision not in ("approve", "reject"):
            raise HTTPException(404, "not found")
        body = await request.json()
        note = str(body.get("note", "")).strip()[:1000]
        v = db.one("SELECT * FROM versions WHERE id = ?", version_id)
        if v is None:
            raise HTTPException(404, "not found")
        if decision == "reject" and not note:
            raise HTTPException(400, "tell the author why")
        report = json.loads(v["report"])
        if decision == "approve" and report.get("errors"):
            raise HTTPException(400, "this version failed the automatic check")
        status = "approved" if decision == "approve" else "rejected"
        db.run("UPDATE versions SET status = ?, note = ?, reviewer_id = ?, reviewed_at = ? WHERE id = ?",
               status, note, user["id"], now(), version_id)
        db.run("UPDATE items SET updated_at = ? WHERE id = ?", now(), v["item_id"])
        return {"status": status}

    @app.post("/api/mod/users/{handle}/ban")
    async def ban(handle: str, request: Request, user=Depends(require_moderator)):
        body = await request.json()
        banned = 1 if body.get("banned", True) else 0
        target = db.one("SELECT * FROM users WHERE handle = ?", handle.lower())
        if target is None:
            raise HTTPException(404, "no such user")
        if is_moderator(target):
            raise HTTPException(400, "moderators cannot be blocked here")
        db.run("UPDATE users SET banned = ? WHERE id = ?", banned, target["id"])
        if banned:
            db.run("DELETE FROM sessions WHERE user_id = ?", target["id"])
        return {"banned": bool(banned)}

    return app


def main() -> None:
    import uvicorn
    uvicorn.run(create_app(), host="0.0.0.0", port=8080, proxy_headers=True, forwarded_allow_ips="127.0.0.1")
