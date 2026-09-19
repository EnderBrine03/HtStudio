"""Kütüphane yönetimi ve dosya yükleme. (Qt gerektirmez.)

Kurallar:
  * Kütüphane      : yalnızca .js / .css  (dosyadan veya https:// adresinden)
  * Proje dosyası  : yalnızca .html / .htm / .css / .js
  * Her dosya metin olmalı (ikili/exe/zip reddedilir), en fazla 5 MB
"""
import os
import re
import shutil
import urllib.request
from urllib.parse import unquote, urlparse

from . import config

ALLOWED_EXT = {".html", ".htm", ".css", ".js"}
LIB_EXT = {".css", ".js"}
MAX_BYTES = 5 * 1024 * 1024
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)} | {"LPT%d" % i for i in range(1, 10)}


class LibraryError(Exception):
    pass


def validate_name(name, allowed):
    name = os.path.basename(str(name).replace("\\", "/")).strip()
    stem, ext = os.path.splitext(name)
    if ext.lower() not in allowed:
        raise LibraryError("Yalnızca %s dosyaları eklenebilir." % ", ".join(sorted(allowed)))
    if (not re.fullmatch(r"[\w][\w.\- ]{0,100}", name) or name.endswith((".", " "))
            or stem.upper() in _RESERVED):
        raise LibraryError("Geçersiz dosya adı: " + name)
    return name


def check_content(data):
    """Metin dosyası mı? Değilse LibraryError. Metni döndürür."""
    if len(data) > MAX_BYTES:
        raise LibraryError("Dosya çok büyük (en fazla 5 MB).")
    if b"\x00" in data or data[:2] in (b"MZ", b"PK") or data[:4] == b"\x7fELF":
        raise LibraryError("Bu dosya metin (html/css/js) değil.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1254", "replace")


def _read_capped(path):
    try:
        with open(path, "rb") as f:
            return f.read(MAX_BYTES + 1)
    except OSError as e:
        raise LibraryError("Dosya okunamadı: %s" % e)


# ------------------------------------------------------------------ kütüphaneler
def _lib_dir(app_id):
    return config.app_dir(app_id, "libs")


def _index_path(app_id):
    return os.path.join(config.app_dir(app_id), "libs.json")


def _load_index(app_id):
    idx = config.read_json(_index_path(app_id), [])
    return [x for x in idx if isinstance(x, dict) and x.get("name")] if isinstance(idx, list) else []


def list_libs(app_id):
    d = _lib_dir(app_id)
    return [x for x in _load_index(app_id) if os.path.isfile(os.path.join(d, x["name"]))]


def _register(app_id, name, text, source):
    with open(os.path.join(_lib_dir(app_id), name), "w", encoding="utf-8", newline="") as f:
        f.write(text)
    idx = [x for x in _load_index(app_id) if x["name"] != name]
    idx.append({"name": name, "enabled": True, "source": source})
    config.write_json(_index_path(app_id), idx)
    return name


def add_lib_file(app_id, src_path):
    name = validate_name(src_path, LIB_EXT)
    return _register(app_id, name, check_content(_read_capped(src_path)), "file")


def add_lib_url(app_id, url, timeout=20):
    p = urlparse(url.strip())
    if p.scheme != "https" or not p.netloc:
        raise LibraryError("Yalnızca https:// adresleri desteklenir.")
    name = validate_name(unquote(p.path.rsplit("/", 1)[-1]), LIB_EXT)
    req = urllib.request.Request(url.strip(), headers={"User-Agent": "HtStudio"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(MAX_BYTES + 1)
    except Exception as e:
        raise LibraryError("İndirilemedi: %s" % e)
    return _register(app_id, name, check_content(data), url.strip())


def set_enabled(app_id, name, enabled):
    idx = _load_index(app_id)
    for x in idx:
        if x["name"] == name:
            x["enabled"] = bool(enabled)
    config.write_json(_index_path(app_id), idx)


def remove_lib(app_id, name):
    name = os.path.basename(name)
    try:
        os.remove(os.path.join(_lib_dir(app_id), name))
    except OSError:
        pass
    config.write_json(_index_path(app_id), [x for x in _load_index(app_id) if x["name"] != name])


def enabled_sources(app_id):
    """[(ad, '.js'|'.css', metin)] - eklenme sırasıyla."""
    out = []
    d = _lib_dir(app_id)
    for x in list_libs(app_id):
        if not x.get("enabled", True):
            continue
        try:
            with open(os.path.join(d, x["name"]), "r", encoding="utf-8") as f:
                out.append((x["name"], os.path.splitext(x["name"])[1].lower(), f.read()))
        except OSError:
            pass
    return out


# ------------------------------------------------------------------ kullanıcı projeleri
def slugify(name):
    return re.sub(r"[^\w\-]+", "-", str(name).strip().lower()).strip("-")[:40] or "proje"


def create_project(name, files):
    """Seçilen .html/.css/.js dosyalarından yeni proje oluşturur. Klasör yolunu döndürür."""
    if not files:
        raise LibraryError("En az bir dosya seç.")
    items, seen = [], set()
    for f in files:                       # önce hepsini doğrula, sonra yaz
        nm = validate_name(f, ALLOWED_EXT)
        if nm.lower() in seen:
            raise LibraryError("Aynı ada sahip iki dosya var: " + nm)
        seen.add(nm.lower())
        items.append((nm, check_content(_read_capped(f))))
    htmls = [n for n, _ in items if n.lower().endswith(config.HTML_EXT)]
    if not htmls:
        raise LibraryError("En az bir .html dosyası gerekli.")
    entry = next((n for n in htmls if n.lower() == "index.html"), htmls[0])

    base = slugify(name)
    slug, n = base, 2
    while os.path.exists(os.path.join(config.projects_dir(), slug)):
        slug, n = "%s-%d" % (base, n), n + 1
    root = os.path.join(config.projects_dir(), slug)
    os.makedirs(root)
    for nm, text in items:
        with open(os.path.join(root, nm), "w", encoding="utf-8", newline="") as f:
            f.write(text)
    config.write_json(os.path.join(root, "launcher.json"), {
        "id": "user." + slug, "name": str(name).strip() or slug, "version": "1.0.0",
        "entry": entry, "permissions": []})
    return root


def _require_user_project(root):
    if not config.within(config.projects_dir(), root):
        raise LibraryError("Yalnızca kendi oluşturduğun projeler değiştirilebilir.")


def add_project_file(root, src_path):
    _require_user_project(root)
    nm = validate_name(src_path, ALLOWED_EXT)
    text = check_content(_read_capped(src_path))
    with open(os.path.join(root, nm), "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return nm


def set_declared_permissions(root, perms):
    _require_user_project(root)
    p = os.path.join(root, "launcher.json")
    cfg = config.read_json(p, {})
    cfg["permissions"] = sorted(set(perms))
    config.write_json(p, cfg)


def delete_project(root):
    _require_user_project(root)
    shutil.rmtree(root, ignore_errors=True)
