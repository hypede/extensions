"""API extensions.hypede.xyz: аккаунты, расширения и темы, проверка.

Работает и на своём сервере (данные на диске), и на Vercel (данные в
Vercel Blob, см. storage.py). Сайт — статичные страницы на GitHub Pages —
ходит сюда с токеном входа в заголовке Authorization: сайт и API на разных
доменах, а куки между доменами браузеры блокируют. Изменяющие запросы
требуют ещё и заголовок X-HypeDE: 1.

Путь загрузки: автор принимает условия → файл проверяется автоматически
(checks.py; ClamAV — здесь, если он есть, или потом из GitHub Actions через
/api/scan) → версия ждёт модератора → модератор одобряет или отклоняет с
пояснением. Публично видны и скачиваются только одобренные версии; прошлая
одобренная версия остаётся доступной, пока новая на проверке.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import unicodedata

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import checks
from .auth import RateLimiter, check_password, hash_password, make_token, read_token
from .config import Config
from .repo import Repo, now
from .storage import Storage, from_env

HANDLE = re.compile(r"^[a-z0-9_-]{3,24}$")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$")
RESERVED = {"admin", "hypede", "moderator", "support", "root", "system", "api", "official", "help", "staff"}
KINDS = {"extension", "theme"}
MEDIA_NAME = re.compile(r"^[0-9a-f]+-[0-9a-f]+\.png$")
PUBLIC_CACHE = "public, max-age=30, s-maxage=60, stale-while-revalidate=300"

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


def create_app(config: Config | None = None, storage: Storage | None = None) -> FastAPI:
    config = config or Config()
    repo = Repo(storage or from_env(config.data))
    store = repo.s
    limiter = RateLimiter()
    app = FastAPI(title="HypeDE Extensions API", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config
    app.state.repo = repo
    app.add_middleware(CORSMiddleware, allow_origins=config.origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"],
                       allow_headers=["X-HypeDE", "Content-Type", "Authorization"],
                       expose_headers=["X-Checksum-SHA256", "Content-Disposition"], max_age=600)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-hypede") != "1":
            return JSONResponse({"error": "missing X-HypeDE header"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; frame-ancestors 'none'"
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    # ------------------------------------------------------------ помощники

    def client(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for", "")
        return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "?")

    def limit(request: Request, what: str, count: int, window: float) -> None:
        if not limiter.allow(f"{what}:{client(request)}", count, window):
            raise HTTPException(429, "too many requests, try again later")

    def current_user(request: Request):
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            return None
        found = read_token(config.secret, header[7:].strip())
        if not found:
            return None
        user = repo.user(found[0])
        if user is None or user.get("banned") or user.get("epoch", 0) != found[1]:
            return None
        return user

    def require_user(user=Depends(current_user)):
        if user is None:
            raise HTTPException(401, "sign in first")
        return user

    def is_moderator(user) -> bool:
        return user is not None and (user.get("role") == "moderator" or user["handle"].lower() in config.moderators
                                     or user["email"].lower() in config.moderators)

    def require_moderator(user=Depends(require_user)):
        if not is_moderator(user):
            raise HTTPException(403, "only moderators can do this")
        return user

    def media_url(folder: str, name: str) -> str:
        return f"{config.public_url}/media/{folder}/{name}" if name else ""

    def profile(user, private: bool = False) -> dict:
        data = {"handle": user["handle"], "displayName": user["display_name"], "bio": user.get("bio", ""),
                "avatar": media_url("avatars", user.get("avatar", "")), "joined": user["created_at"]}
        if private:
            data.update(email=user["email"], moderator=is_moderator(user))
        return data

    def signed_in(user) -> dict:
        return {**profile(user, private=True),
                "token": make_token(config.secret, user["id"], user.get("epoch", 0), config.session_days)}

    async def read_upload(upload: UploadFile, limit_bytes: int, what: str) -> bytes:
        data = await upload.read(limit_bytes + 1)
        if len(data) > limit_bytes:
            raise HTTPException(413, f"{what} is larger than {limit_bytes >> 20} MB")
        if not data:
            raise HTTPException(400, f"{what} is empty")
        return data

    def version_view(item, v) -> dict:
        return {"id": f"{item['id']}-{v['number']}", "number": v["number"], "status": v["status"],
                "note": v.get("note", ""), "report": v.get("report", {}), "meta": v.get("meta", {}),
                "sha256": v["sha256"], "size": v["size"], "created": v["created_at"],
                "reviewed": v.get("reviewed_at")}

    def item_view(item, viewer=None) -> dict:
        owner = repo.user(item["owner_id"])
        version = repo.approved(item)
        data = {
            "id": item["id"], "kind": item["kind"], "slug": item["slug"], "name": item["name"],
            "summary": item["summary"], "description": item.get("description", ""),
            "homepage": item.get("homepage", ""), "license": item.get("license", ""), "uuid": item.get("uuid", ""),
            "preview": media_url("previews", item.get("preview", "")),
            "author": profile(owner) if owner else None, "updated": item["updated_at"],
        }
        if version is not None:
            data["version"] = {"number": version["number"], "sha256": version["sha256"], "size": version["size"],
                               "meta": version.get("meta", {}), "approved": version.get("reviewed_at"),
                               "download": f"{config.public_url}/api/items/{item['id']}/download"}
        if viewer is not None and (viewer["id"] == item["owner_id"] or is_moderator(viewer)):
            data["versions"] = [version_view(item, v) for v in sorted(item["versions"], key=lambda v: -v["number"])]
        return data

    def card(entry: dict, kind: str) -> dict:
        return {"id": entry["id"], "kind": kind, "slug": entry["slug"], "name": entry["name"],
                "summary": entry["summary"], "preview": media_url("previews", entry.get("preview", "")),
                "updated": entry["approved"],
                "author": {"handle": entry["handle"], "displayName": entry["display"],
                           "avatar": media_url("avatars", entry.get("avatar", ""))}}

    # --------------------------------------------------------------- общее

    @app.get("/api/info")
    def info(response: Response):
        response.headers["Cache-Control"] = PUBLIC_CACHE
        return {"disclaimer": DISCLAIMER, "kinds": sorted(KINDS), "shellVersions": sorted(checks.SUPPORTED_SHELL),
                "limits": {"extension": config.max_extension, "theme": config.max_theme, "image": config.max_image}}

    # ------------------------------------------------------------- аккаунт

    @app.post("/api/auth/register")
    async def register(request: Request):
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
        if repo.email_taken(email):
            raise HTTPException(409, "this email is already registered")
        if repo.handle_taken(handle):
            raise HTTPException(409, "this nickname is taken")
        # Не больше пяти новых аккаунтов в час с одного адреса.
        limit(request, "register", 5, 3600)
        return signed_in(repo.create_user(email, hash_password(password), handle, display))

    @app.post("/api/auth/login")
    async def login(request: Request):
        limit(request, "login", 10, 600)
        body = await request.json()
        login_id = str(body.get("login", "")).strip().lower()
        user = repo.user_by_email(login_id) if "@" in login_id else repo.user_by_handle(login_id)
        # Хеш считается и для несуществующего пользователя — по времени
        # ответа нельзя узнать, есть ли такой адрес.
        stored = user["password"] if user else hash_password(secrets.token_hex(8))
        if not check_password(str(body.get("password", "")), stored) or user is None:
            raise HTTPException(401, "wrong email, nickname or password")
        if user.get("banned"):
            raise HTTPException(403, "this account is blocked")
        return signed_in(user)

    @app.post("/api/auth/logout")
    def logout(user=Depends(current_user)):
        # Выход везде: старые токены с прежней эпохой больше не действуют.
        if user is not None:
            user["epoch"] = user.get("epoch", 0) + 1
            repo.s.put_json(f"users/{user['id']}.json", user)
        return {"ok": True}

    @app.get("/api/me")
    def me(user=Depends(current_user)):
        return profile(user, private=True) if user else {"signedIn": False}

    @app.patch("/api/me")
    async def update_me(request: Request, user=Depends(require_user)):
        body = await request.json()
        old_handle = user["handle"]
        password_changed = False
        if "displayName" in body:
            display = str(body["displayName"]).strip()
            if not 1 <= len(display) <= 60:
                raise HTTPException(400, "the name must be 1–60 characters")
            user["display_name"] = display
        if "bio" in body:
            bio = str(body["bio"]).strip()
            if len(bio) > 500:
                raise HTTPException(400, "the description is longer than 500 characters")
            user["bio"] = bio
        if "handle" in body:
            handle = str(body["handle"]).strip().lower()
            if not HANDLE.match(handle) or handle in RESERVED:
                raise HTTPException(400, "the nickname must be 3–24 Latin letters, digits, _ or -")
            if handle != old_handle and repo.handle_taken(handle):
                raise HTTPException(409, "this nickname is taken")
            user["handle"] = handle
        if "password" in body:
            if not check_password(str(body.get("currentPassword", "")), user["password"]):
                raise HTTPException(403, "the current password is wrong")
            password = str(body["password"])
            if len(password) < 10:
                raise HTTPException(400, "the password must be at least 10 characters")
            user["password"] = hash_password(password)
            user["epoch"] = user.get("epoch", 0) + 1
            password_changed = True
        repo.save_user(user, old_handle)
        return signed_in(user) if password_changed else profile(user, private=True)

    @app.post("/api/me/avatar")
    async def upload_avatar(request: Request, file: UploadFile = File(...), user=Depends(require_user)):
        limit(request, "avatar", 20, 3600)
        raw = await read_upload(file, config.max_image, "the photo")
        try:
            png = checks.reencode_image(raw, 256, square=True)
        except checks.CheckError as e:
            raise HTTPException(400, str(e))
        name = f"{user['id']}-{secrets.token_hex(6)}.png"
        store.put(f"media/avatars/{name}", png, "image/png")
        if user.get("avatar"):
            store.delete(f"media/avatars/{user['avatar']}")
        user["avatar"] = name
        repo.save_user(user)
        return {"avatar": media_url("avatars", name)}

    @app.delete("/api/me/avatar")
    def delete_avatar(user=Depends(require_user)):
        if user.get("avatar"):
            store.delete(f"media/avatars/{user['avatar']}")
        user["avatar"] = ""
        repo.save_user(user)
        return {"avatar": ""}

    @app.get("/api/users/{handle}")
    def user_page(handle: str, response: Response, viewer=Depends(current_user)):
        user = repo.user_by_handle(handle.lower()) if HANDLE.match(handle.lower()) else None
        if user is None or user.get("banned"):
            raise HTTPException(404, "no such user")
        own = viewer is not None and viewer["id"] == user["id"]
        items = [item_view(i, viewer) for i in repo.items_of(user["id"]) if own or repo.approved(i)]
        items.sort(key=lambda i: -i["updated"])
        if viewer is None:
            response.headers["Cache-Control"] = PUBLIC_CACHE
        return {"user": profile(user), "items": items}

    @app.get("/media/{folder}/{name}")
    def media(folder: str, name: str):
        if folder not in ("avatars", "previews") or not MEDIA_NAME.match(name):
            raise HTTPException(404, "not found")
        data = store.get(f"media/{folder}/{name}")
        if data is None:
            raise HTTPException(404, "not found")
        # Имя картинки меняется при замене — её можно кэшировать надолго.
        return Response(data, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400, s-maxage=31536000, immutable"})

    # --------------------------------------------------------------- каталог

    @app.get("/api/items")
    def list_items(response: Response, kind: str = Query("extension"), q: str = Query("", max_length=80),
                   sort: str = Query("new"), page: int = Query(1, ge=1, le=500)):
        if kind not in KINDS:
            raise HTTPException(400, "unknown kind")
        entries = repo.catalog(kind)
        query = q.strip().lower()
        if query:
            entries = [e for e in entries if query in e["name"].lower() or query in e["summary"].lower()
                       or query in e["handle"]]
        if sort == "name":
            entries.sort(key=lambda e: e["name"].lower())
        else:
            entries.sort(key=lambda e: -(e.get("approved") or 0))
        response.headers["Cache-Control"] = PUBLIC_CACHE
        return {"items": [card(e, kind) for e in entries[(page - 1) * 30:page * 30]], "page": page}

    def find_item(kind: str, slug: str):
        item = repo.item_by_slug(kind, slug) if kind in KINDS and re.fullmatch(r"[a-z0-9-]{1,60}", slug) else None
        if item is None:
            raise HTTPException(404, "not found")
        return item

    def file_response(item, version) -> Response:
        data = store.get(version["file"])
        if data is None:
            raise HTTPException(404, "the file is missing")
        if item["kind"] == "extension":
            filename, media_type = f"{item.get('uuid') or item['slug']}.zip", "application/zip"
        else:
            filename, media_type = f"{item['slug']}.json", "application/json"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"', "X-Checksum-SHA256": version["sha256"]}
        if version["status"] == "approved":
            headers["Cache-Control"] = "public, max-age=300, s-maxage=86400"
        return Response(data, media_type=media_type, headers=headers)

    # Раньше /api/items/{kind}/{slug}: иначе «id/download» принимался бы за
    # вид и имя.
    @app.get("/api/items/{item_id}/download")
    def download(item_id: str, version: int | None = None, viewer=Depends(current_user)):
        item = repo.item(item_id)
        if item is None:
            raise HTTPException(404, "not found")
        privileged = viewer is not None and (viewer["id"] == item["owner_id"] or is_moderator(viewer))
        if version is not None and privileged:
            v = next((v for v in item["versions"] if v["number"] == version), None)
        else:
            v = repo.approved(item)
        if v is None:
            raise HTTPException(404, "no approved version yet")
        return file_response(item, v)

    @app.get("/api/items/{kind}/{slug}")
    def item_page(kind: str, slug: str, response: Response, viewer=Depends(current_user)):
        item = find_item(kind, slug)
        privileged = viewer is not None and (viewer["id"] == item["owner_id"] or is_moderator(viewer))
        if repo.approved(item) is None and not privileged:
            raise HTTPException(404, "not found")
        data = item_view(item, viewer)
        data["disclaimer"] = DISCLAIMER
        if viewer is None:
            response.headers["Cache-Control"] = PUBLIC_CACHE
        return data

    # ------------------------------------------------------------- загрузка

    async def add_version(request, item, upload, accept_terms) -> dict:
        if accept_terms not in ("true", "1", "on", "yes"):
            raise HTTPException(400, "you have to accept the terms")
        limit(request, "upload", 20, 3600)
        if item["kind"] == "extension":
            raw = await read_upload(upload, config.max_extension, "the archive")
            try:
                meta, report = checks.check_extension(raw, config.clamav)
            except checks.CheckError as e:
                raise HTTPException(400, str(e))
            if item.get("uuid") and meta["uuid"] != item["uuid"]:
                raise HTTPException(400, f"the uuid must stay {item['uuid']}")
            owner_of_uuid = repo.uuid_owner(meta["uuid"])
            if owner_of_uuid and owner_of_uuid != item.get("id"):
                raise HTTPException(409, "an extension with this uuid is already published by someone else")
            suffix = ".zip"
        else:
            raw = await read_upload(upload, config.max_theme, "the theme file")
            try:
                meta, report = checks.check_theme(raw, config.clamav)
            except checks.CheckError as e:
                raise HTTPException(400, str(e))
            suffix = ".json"
        number = max((v["number"] for v in item["versions"]), default=0) + 1
        path = f"files/{item['id']}/{number}-{secrets.token_hex(6)}{suffix}"
        store.put(path, raw, "application/zip" if suffix == ".zip" else "application/json")
        status = "rejected" if report["errors"] else "pending"
        note = ("Automatic check: " + "; ".join(report["errors"]))[:900] if report["errors"] else ""
        version = {"number": number, "file": path, "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw),
                   "meta": meta, "report": report, "status": status, "note": note, "reviewer": None,
                   "terms_at": now(), "created_at": now(), "reviewed_at": now() if status == "rejected" else None}
        item["versions"].append(version)
        if item["kind"] == "extension" and not item.get("uuid"):
            item["uuid"] = meta["uuid"]
        return version

    async def save_preview(item: dict, upload: UploadFile | None) -> None:
        if upload is None or not upload.filename:
            return
        raw = await read_upload(upload, config.max_image, "the picture")
        try:
            png = checks.reencode_image(raw, 1280)
        except checks.CheckError as e:
            raise HTTPException(400, str(e))
        name = f"{item['id']}-{secrets.token_hex(6)}.png"
        store.put(f"media/previews/{name}", png, "image/png")
        if item.get("preview"):
            store.delete(f"media/previews/{item['preview']}")
        item["preview"] = name

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
        item = {"kind": kind, "owner_id": user["id"], "name": clean_text(name, 60, "the name", True),
                "summary": clean_text(summary, 140, "the short description", True),
                "description": clean_text(description, 5000, "the description"),
                "license": clean_text(license, 60, "the license"), "homepage": clean_url(homepage),
                "preview": "", "uuid": "", "versions": [], "created_at": now(), "updated_at": now()}
        # Сначала проверить файл и картинку, потом что-то записывать.
        item["id"] = "new"
        version = await add_version(request, item, file, accept_terms)
        base = slugify(item["name"])
        slug, n = base, 2
        while repo.slug_taken(kind, slug):
            slug, n = f"{base}-{n}", n + 1
        item["slug"] = slug
        versions, item["versions"] = item["versions"], []
        item.pop("id")
        item = repo.create_item(item)
        # Файл лежал под временным именем — переложить к работе.
        for v in versions:
            data = store.get(v["file"])
            store.delete(v["file"])
            v["file"] = v["file"].replace("files/new/", f"files/{item['id']}/", 1)
            store.put(v["file"], data)
        item["versions"] = versions
        try:
            await save_preview(item, preview)
        except HTTPException:
            repo.delete_item(item)
            raise
        repo.save_item(item)
        return {"item": item_view(item, user), "version": {k: v for k, v in version.items() if k != "file"}}

    def own_item(item_id: str, user):
        item = repo.item(item_id)
        if item is None or (item["owner_id"] != user["id"] and not is_moderator(user)):
            raise HTTPException(404, "not found")
        return item

    @app.post("/api/items/{item_id}/versions")
    async def new_version(request: Request, item_id: str, accept_terms: str = Form(""),
                          file: UploadFile = File(...), user=Depends(require_user)):
        item = own_item(item_id, user)
        version = await add_version(request, item, file, accept_terms)
        repo.save_item(item)
        return {k: v for k, v in version.items() if k != "file"}

    @app.patch("/api/items/{item_id}")
    async def edit_item(item_id: str, name: str = Form(None), summary: str = Form(None),
                        description: str = Form(None), homepage: str = Form(None), license: str = Form(None),
                        preview: UploadFile | None = File(None), user=Depends(require_user)):
        item = own_item(item_id, user)
        if name is not None:
            item["name"] = clean_text(name, 60, "the name", True)
        if summary is not None:
            item["summary"] = clean_text(summary, 140, "the short description", True)
        if description is not None:
            item["description"] = clean_text(description, 5000, "the description")
        if homepage is not None:
            item["homepage"] = clean_url(homepage)
        if license is not None:
            item["license"] = clean_text(license, 60, "the license")
        await save_preview(item, preview)
        repo.save_item(item)
        return item_view(item, user)

    @app.delete("/api/items/{item_id}")
    def delete_item(item_id: str, user=Depends(require_user)):
        repo.delete_item(own_item(item_id, user))
        return {"ok": True}

    @app.get("/api/my/items")
    def my_items(user=Depends(require_user)):
        items = [item_view(i, user) for i in repo.items_of(user["id"])]
        items.sort(key=lambda i: -i["updated"])
        return {"items": items}

    # ------------------------------------------------------------ модерация

    @app.get("/api/mod/queue")
    def queue(user=Depends(require_moderator)):
        result = []
        for pending in repo.queue():
            item = repo.item(pending["item"])
            v = next((v for v in (item or {}).get("versions", []) if v["number"] == pending["number"]), None)
            if v is None or v["status"] != "pending":
                continue
            data = item_view(item, user)
            data["pending"] = version_view(item, v)
            result.append(data)
        return {"queue": result}

    def find_version(version_id: str):
        item_id, _, number = version_id.rpartition("-")
        item = repo.item(item_id)
        v = next((v for v in (item or {}).get("versions", []) if str(v["number"]) == number), None)
        if v is None:
            raise HTTPException(404, "not found")
        return item, v

    @app.post("/api/mod/versions/{version_id}/{decision}")
    async def review(request: Request, version_id: str, decision: str, user=Depends(require_moderator)):
        if decision not in ("approve", "reject"):
            raise HTTPException(404, "not found")
        body = await request.json()
        note = str(body.get("note", "")).strip()[:1000]
        item, v = find_version(version_id)
        if decision == "reject" and not note:
            raise HTTPException(400, "tell the author why")
        if decision == "approve" and v.get("report", {}).get("errors"):
            raise HTTPException(400, "this version failed the automatic check")
        v.update(status="approved" if decision == "approve" else "rejected", note=note, reviewer=user["id"],
                 reviewed_at=now())
        repo.save_item(item)
        return {"status": v["status"]}

    @app.post("/api/mod/users/{handle}/ban")
    async def ban(handle: str, request: Request, user=Depends(require_moderator)):
        body = await request.json()
        target = repo.user_by_handle(handle.lower())
        if target is None:
            raise HTTPException(404, "no such user")
        if is_moderator(target):
            raise HTTPException(400, "moderators cannot be blocked here")
        target["banned"] = bool(body.get("banned", True))
        target["epoch"] = target.get("epoch", 0) + 1
        repo.save_user(target)
        return {"banned": target["banned"]}

    # ---------------------------------------------- антивирус из GitHub Actions
    # На Vercel ClamAV не запустить, поэтому его запускает workflow
    # .github/workflows/antivirus.yml по расписанию: берёт версии без
    # проверки, сканирует и присылает итог. Доступ — по ключу
    # HYPEDE_STORE_SCAN_TOKEN (секрет репозитория и переменная Vercel).

    def require_scanner(request: Request) -> None:
        header = request.headers.get("authorization", "")
        if not config.scan_token or not hmac.compare_digest(header, f"Bearer {config.scan_token}"):
            raise HTTPException(403, "scanner only")

    @app.get("/api/scan/queue")
    def scan_queue(request: Request):
        require_scanner(request)
        todo = []
        for pending in repo.queue():
            item = repo.item(pending["item"])
            v = next((v for v in (item or {}).get("versions", []) if v["number"] == pending["number"]), None)
            if v and v.get("report", {}).get("antivirus", "unavailable") == "unavailable":
                todo.append({"id": f"{item['id']}-{v['number']}", "kind": item["kind"], "sha256": v["sha256"]})
        return {"versions": todo}

    @app.get("/api/scan/file/{version_id}")
    def scan_file(version_id: str, request: Request):
        require_scanner(request)
        item, v = find_version(version_id)
        data = store.get(v["file"])
        if data is None:
            raise HTTPException(404, "the file is missing")
        return Response(data, media_type="application/octet-stream")

    @app.post("/api/scan/{version_id}")
    async def scan_result(version_id: str, request: Request):
        require_scanner(request)
        body = await request.json()
        result = str(body.get("antivirus", ""))[:300]
        if result != "clean" and not result.startswith("infected"):
            raise HTTPException(400, "antivirus must be clean or infected: …")
        item, v = find_version(version_id)
        v.setdefault("report", {})["antivirus"] = result
        if result.startswith("infected") and v["status"] == "pending":
            v["report"].setdefault("errors", []).append("antivirus: " + result)
            v.update(status="rejected", note=f"Automatic check: antivirus: {result}", reviewed_at=now())
        repo.save_item(item)
        return {"status": v["status"]}

    return app


def main() -> None:
    import uvicorn
    uvicorn.run(create_app(), host="0.0.0.0", port=8080, proxy_headers=True, forwarded_allow_ips="127.0.0.1")
