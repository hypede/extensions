"""Автоматическая проверка загрузок: расширения, темы, картинки.

Автоматика ничего не одобряет сама — она только отсеивает явно плохое
(вирус по ClamAV, исполняемые файлы, испорченный архив) и готовит
модератору отчёт: что в архиве, какие места кода стоит посмотреть. Публичным
расширение или тема становятся только после ручной проверки.

Отчёт: {"antivirus": "clean" | "infected: …" | "unavailable", "files": N,
"warnings": [{"file", "line", "what"}], "errors": [...]}. Если есть errors,
версия отклоняется сразу.
"""

from __future__ import annotations

import base64
import io
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from PIL import Image

SUPPORTED_SHELL = {"48", "49", "50", "51"}
UUID = re.compile(r"^[A-Za-z0-9._-]{1,64}@[A-Za-z0-9._-]{1,64}$")
MAX_FILES = 600
MAX_UNPACKED = 40 * 1024 * 1024
MAX_PIXELS = 40_000_000

# Что не должно лежать в расширении GNOME: исполняемые файлы и библиотеки.
BINARY_MAGIC = [b"\x7fELF", b"MZ", b"\xca\xfe\xba\xbe", b"\xcf\xfa\xed\xfe", b"#!/"]
FORBIDDEN_EXT = {".so", ".exe", ".dll", ".bin", ".appimage", ".deb", ".rpm", ".msi", ".dylib", ".bat", ".cmd",
                 ".ps1", ".jar", ".pyc"}
ALLOWED_EXT = {".js", ".mjs", ".json", ".css", ".xml", ".compiled", ".svg", ".png", ".jpg", ".jpeg", ".webp",
               ".gif", ".mo", ".po", ".pot", ".txt", ".md", ".ui", ".ogg", ".oga", ".wav", ".gresource", "",
               ".license", ".html", ".gschema"}

# Места кода, которые модератор должен посмотреть внимательно.
CODE_PATTERNS = [
    (re.compile(r"\b(Gio\.Subprocess|GLib\.spawn\w*|spawn_command_line\w*|Util\.spawn\w*|trySpawn\w*)\b"),
     "runs programs"),
    (re.compile(r"\b(pkexec|sudo|doas)\b"), "asks for administrator rights"),
    (re.compile(r"\b(curl|wget|nc|bash\s+-c|sh\s+-c)\b"), "shell command"),
    (re.compile(r"\b(Soup\.Session|Soup\.Message|fetch\(|XMLHttpRequest|WebSocket)\b"), "network access"),
    (re.compile(r"\beval\s*\(|\bnew\s+Function\s*\("), "runs generated code"),
    (re.compile(r"\b(GLib\.file_set_contents|replace_contents|Gio\.File\.new_for_path\(['\"]/(etc|usr|boot))"),
     "writes files"),
    (re.compile(r"(\.ssh|\.gnupg|Cookies|Login Data|keyring|\.password-store|wallet)", re.I), "touches private data"),
    (re.compile(r"\b(atob|GLib\.base64_decode)\s*\("), "decodes hidden data"),
]
MAX_LINE = 3000  # строка длиннее — похоже на сжатый или запутанный код


class CheckError(ValueError):
    pass


def antivirus(path: Path, scanner: str = "") -> str:
    """«clean», «infected: …» или «unavailable». Без ClamAV ничего не одобряется
    автоматически — версия просто ждёт ручной проверки, как и всегда."""
    scanner = scanner or shutil.which("clamdscan") or shutil.which("clamscan") or ""
    if not scanner:
        return "unavailable"
    argv = [scanner, "--no-summary", "--infected"]
    if Path(scanner).name == "clamscan":
        argv.append("--recursive")
    try:
        result = subprocess.run(argv + [str(path)], capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    if result.returncode == 0:
        return "clean"
    if result.returncode == 1:
        found = result.stdout.strip().splitlines()[-1:] or ["threat found"]
        return "infected: " + found[0].split(":", 1)[-1].strip().removesuffix(" FOUND")
    return "unavailable"


# ------------------------------------------------------------- расширения

def check_extension(raw: bytes, scanner: str = "") -> tuple[dict, dict]:
    """Проверить zip расширения GNOME Shell. Возвращает (metadata, отчёт)."""
    report = {"kind": "extension", "warnings": [], "errors": [], "files": 0}
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise CheckError("this is not a zip archive")
    infos = archive.infolist()
    report["files"] = len(infos)
    if len(infos) > MAX_FILES:
        raise CheckError(f"too many files in the archive (more than {MAX_FILES})")
    if sum(i.file_size for i in infos) > MAX_UNPACKED:
        raise CheckError("the archive unpacks to more than 40 MB")

    names = {}
    for info in infos:
        name = info.filename
        path = PurePosixPath(name)
        if name.startswith("/") or ".." in path.parts or "\\" in name:
            raise CheckError(f"unsafe path in the archive: {name}")
        # Символьные ссылки (атрибуты Unix) в расширении не нужны.
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise CheckError(f"symbolic link in the archive: {name}")
        if info.is_dir():
            continue
        names[name] = info

    # metadata.json — в корне архива (как у gnome-extensions pack).
    if "metadata.json" not in names:
        raise CheckError("metadata.json must be at the root of the archive")
    if "extension.js" not in names:
        raise CheckError("extension.js must be at the root of the archive")
    try:
        meta = json.loads(archive.read("metadata.json").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise CheckError(f"metadata.json is not valid JSON ({e})")
    if not isinstance(meta, dict):
        raise CheckError("metadata.json must be an object")
    uuid = str(meta.get("uuid", ""))
    if not UUID.match(uuid):
        raise CheckError("metadata.json: uuid must look like name@author.example")
    for key in ("name", "description"):
        if not str(meta.get(key, "")).strip():
            raise CheckError(f"metadata.json: no {key}")
    versions = meta.get("shell-version")
    if not isinstance(versions, list) or not all(isinstance(v, str) for v in versions):
        raise CheckError("metadata.json: shell-version must be a list of strings")
    if not {v.split(".")[0] for v in versions} & SUPPORTED_SHELL:
        raise CheckError("metadata.json: shell-version must include a GNOME Shell version HypeDE runs "
                         f"({', '.join(sorted(SUPPORTED_SHELL))})")

    for name, info in names.items():
        suffix = PurePosixPath(name).suffix.lower()
        data = archive.read(info)
        if suffix in FORBIDDEN_EXT:
            report["errors"].append(f"{name}: executable files are not allowed in extensions")
            continue
        if any(data.startswith(m) for m in BINARY_MAGIC[:4]):
            report["errors"].append(f"{name}: compiled program inside the extension")
            continue
        if data.startswith(b"#!/"):
            report["warnings"].append({"file": name, "line": 1, "what": "script that can be run"})
        if suffix not in ALLOWED_EXT and not name.endswith(".gschema.xml"):
            report["warnings"].append({"file": name, "line": 0, "what": f"unusual file type {suffix or '(none)'}"})
        if suffix in (".js", ".mjs"):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                report["errors"].append(f"{name}: not a text file")
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if len(line) > MAX_LINE:
                    report["warnings"].append({"file": name, "line": number, "what": "very long line (minified or obfuscated code)"})
                for pattern, what in CODE_PATTERNS:
                    if pattern.search(line):
                        report["warnings"].append({"file": name, "line": number, "what": what,
                                                   "code": line.strip()[:200]})
    report["warnings"] = report["warnings"][:300]

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "extension.zip"
        path.write_bytes(raw)
        report["antivirus"] = antivirus(path, scanner)
    if report["antivirus"].startswith("infected"):
        report["errors"].append("antivirus: " + report["antivirus"])

    clean_meta = {k: meta[k] for k in ("uuid", "name", "description", "shell-version", "version", "url",
                                       "settings-schema", "gettext-domain") if k in meta}
    return clean_meta, report


# ------------------------------------------------------------------ темы

# Группы и ключи формата темы HypeDE (apps/theme/hypede_theme.py, TABLE).
THEME_KEYS = {
    "colors": {"scheme", "accent", "gnome-accent", "shelf", "menus"},
    "wallpaper": {"light", "dark", "fit", "color", "live", "live-speed"},
    "shelf": {"position", "alignment", "style", "size", "icon-size", "opacity", "blur", "indicator",
              "hover-zoom", "show-date"},
    "launcher": {"style", "columns", "icon-size", "labels", "opacity", "blur"},
    "desktop": {"icons", "icon-size", "show-home", "show-trash"},
    "windows": {"corner-radius", "rounded-windows", "window-radius", "animations", "animation-speed", "genie",
                "jelly", "buttons", "notifications", "greeting"},
    "lockscreen": {"style", "clock", "clock-color", "clock-size", "message", "wallpaper", "blur", "dim", "waves",
                   "cards"},
    "fonts": {"interface", "documents", "monospace"},
    "icons": {"theme", "cursor", "cursor-size"},
    "sounds": {"theme"},
}
THEME_TOP = {"hypede-theme", "name", "author", "description", "files"} | set(THEME_KEYS)
MEDIA_MAGIC = {
    ".png": [(0, b"\x89PNG\r\n\x1a\n")], ".jpg": [(0, b"\xff\xd8\xff")], ".jpeg": [(0, b"\xff\xd8\xff")],
    ".gif": [(0, b"GIF87a"), (0, b"GIF89a")], ".webp": [(8, b"WEBP")], ".mp4": [(4, b"ftyp")],
    ".mov": [(4, b"ftyp"), (4, b"moov")], ".webm": [(0, b"\x1a\x45\xdf\xa3")], ".mkv": [(0, b"\x1a\x45\xdf\xa3")],
}


def _check_svg(name: str, raw: bytes) -> None:
    import xml.etree.ElementTree as ET
    text = raw.decode("utf-8", "strict")
    if re.search(r"<!DOCTYPE|<!ENTITY|<\?xml-stylesheet", text, re.I):
        raise CheckError(f"{name}: SVG with DOCTYPE or entities")
    root = ET.fromstring(text)
    if root.tag.rsplit("}", 1)[-1] != "svg":
        raise CheckError(f"{name}: not an SVG")
    bad = {"script", "foreignobject", "iframe", "embed", "object", "audio", "video", "image"}
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1].lower()
        if tag in bad:
            raise CheckError(f"{name}: <{tag}> is not allowed in SVG")
        for k, v in el.attrib.items():
            attr = k.rsplit("}", 1)[-1].lower()
            if attr.startswith("on") or "javascript:" in v.lower():
                raise CheckError(f"{name}: script in SVG")
            if attr == "href" and not v.startswith("#"):
                raise CheckError(f"{name}: external link in SVG")
            if re.search(r"url\(\s*['\"]?(?!#)", v, re.I):
                raise CheckError(f"{name}: external address in SVG")


def check_theme(raw: bytes, scanner: str = "") -> tuple[dict, dict]:
    """Проверить JSON темы HypeDE. Возвращает (сведения, отчёт)."""
    report = {"kind": "theme", "warnings": [], "errors": [], "files": 0}
    try:
        theme = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise CheckError(f"not a JSON theme file ({e})")
    if not isinstance(theme, dict) or theme.get("hypede-theme") != 1:
        raise CheckError("not a HypeDE theme (\"hypede-theme\": 1 is missing)")
    if not str(theme.get("name") or "").strip():
        raise CheckError("the theme has no name")
    for key in theme:
        if key not in THEME_TOP:
            report["errors"].append(f"unknown field “{key}”")
    for group, keys in THEME_KEYS.items():
        value = theme.get(group)
        if value is None:
            continue
        if not isinstance(value, dict):
            report["errors"].append(f"{group} must be an object")
            continue
        for key, item in value.items():
            if key not in keys:
                report["errors"].append(f"{group}.{key}: unknown setting")
            elif isinstance(item, (dict, list)):
                report["errors"].append(f"{group}.{key}: must be a simple value")
            elif isinstance(item, str) and item.startswith(("http:", "https:", "ftp:", "smb:", "sftp:")):
                report["errors"].append(f"{group}.{key}: network addresses are not allowed")
    files = theme.get("files") or {}
    if not isinstance(files, dict):
        raise CheckError("files must be an object")
    report["files"] = len(files)
    with tempfile.TemporaryDirectory() as tmp:
        for name, blob in files.items():
            safe = PurePosixPath(str(name)).name
            ext = PurePosixPath(safe).suffix.lower()
            try:
                data = base64.b64decode(blob, validate=True)
            except (ValueError, TypeError):
                report["errors"].append(f"{safe}: broken base64")
                continue
            try:
                if ext == ".svg":
                    _check_svg(safe, data)
                elif ext in MEDIA_MAGIC:
                    if not any(data[o:o + len(s)] == s for o, s in MEDIA_MAGIC[ext]):
                        raise CheckError(f"{safe}: content does not match {ext}")
                    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                        _open_image(data, safe)
                else:
                    raise CheckError(f"{safe}: such files are not allowed in themes")
            except (CheckError, UnicodeDecodeError, SyntaxError) as e:
                report["errors"].append(str(e))
                continue
            (Path(tmp) / f"{len(list(Path(tmp).iterdir()))}{ext}").write_bytes(data)
        (Path(tmp) / "theme.json").write_bytes(raw)
        report["antivirus"] = antivirus(Path(tmp), scanner)
    if report["antivirus"].startswith("infected"):
        report["errors"].append("antivirus: " + report["antivirus"])
    info = {"name": str(theme["name"])[:80], "author": str(theme.get("author") or "")[:80],
            "description": str(theme.get("description") or "")[:300],
            "scheme": (theme.get("colors") or {}).get("scheme", "default"),
            "accent": (theme.get("colors") or {}).get("accent", "")}
    return info, report


# --------------------------------------------------------------- картинки

def _open_image(raw: bytes, name: str = "image") -> Image.Image:
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        probe = Image.open(io.BytesIO(raw))
        probe.verify()
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (OSError, Image.DecompressionBombError, SyntaxError, ValueError) as e:
        raise CheckError(f"{name}: not a valid image ({e.__class__.__name__})")
    if image.width * image.height > MAX_PIXELS:
        raise CheckError(f"{name}: the image is too large")
    return image


def reencode_image(raw: bytes, max_side: int, square: bool = False) -> bytes:
    """Пересобрать картинку в PNG: из файла остаются только пиксели —
    метаданные и всё, что могло прятаться в файле, пропадают."""
    image = _open_image(raw)
    image = image.convert("RGBA")
    if square:
        side = min(image.width, image.height)
        left, top = (image.width - side) // 2, (image.height - side) // 2
        image = image.crop((left, top, left + side, top + side))
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()
