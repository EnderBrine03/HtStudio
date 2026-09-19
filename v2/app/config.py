"""Yollar, proje/manifest okuma, son açılanlar. (Qt gerektirmez.)"""
import hashlib
import json
import os
import re
from urllib.parse import urlparse

APP_NAME = "HtStudio"
VERSION = "2.0.0"
SCHEME = "htstudio"       # yerel içerik htstudio://app/... adresinden sunulur
SCHEME_HOST = "app"
HTML_EXT = (".html", ".htm")

DEFAULT_WINDOW = {"width": 1100, "height": 700, "fullscreen": False, "resizable": True}


def safe_id(s):
    s = re.sub(r"[^A-Za-z0-9._-]", "_", str(s)).strip("._")[:80]
    return s or "app"


def data_root():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    p = os.path.join(base, APP_NAME)
    os.makedirs(p, exist_ok=True)
    return p


def app_dir(app_id, *sub):
    p = os.path.join(data_root(), "apps", safe_id(app_id), *sub)
    os.makedirs(p, exist_ok=True)
    return p


def projects_dir():
    p = os.path.join(data_root(), "projects")
    os.makedirs(p, exist_ok=True)
    return p


def within(root, path):
    """path, root'un içinde mi? (symlink'ler çözülür)"""
    root = os.path.normcase(os.path.realpath(root))
    path = os.path.normcase(os.path.realpath(path))
    try:
        return os.path.commonpath([root, path]) == root
    except ValueError:  # farklı sürücüler
        return False


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


class Project:
    """Çalıştırılabilir bir uygulama: yerel klasör (mode='local') ya da web adresi (mode='url')."""

    def __init__(self, root, cfg, mode="local", url=""):
        self.root = os.path.realpath(root) if root else ""
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self.mode = mode
        self.url = url
        default_id = "local-" + hashlib.sha1((self.root or url).encode("utf-8")).hexdigest()[:10]
        self.id = safe_id(self.cfg.get("id") or default_id)
        self.name = str(self.cfg.get("name") or os.path.basename(self.root) or url or APP_NAME)
        self.version = str(self.cfg.get("version") or "1.0.0")
        self.permissions = {str(p) for p in self.cfg.get("permissions", [])}
        w = self.cfg.get("window")
        self.window = {**DEFAULT_WINDOW, **(w if isinstance(w, dict) else {})}
        entry = self.cfg.get("entry") or (self.cfg.get("target") or {}).get("path") or "index.html"
        self.entry = str(entry).replace("\\", "/").lstrip("/")
        self.libs = [str(x) for x in self.cfg.get("libs", [])]

    @property
    def user_owned(self):
        return bool(self.root) and within(projects_dir(), self.root)

    def start_url(self):
        if self.mode == "url":
            return self.url
        return "%s://%s/%s" % (SCHEME, SCHEME_HOST, self.entry)


def _guess_entry(root):
    if os.path.isfile(os.path.join(root, "index.html")):
        return "index.html"
    try:
        for n in sorted(os.listdir(root)):
            if n.lower().endswith(HTML_EXT):
                return n
    except OSError:
        pass
    return "index.html"


def load_project(root):
    cfg = read_json(os.path.join(root, "launcher.json"), {})
    if not isinstance(cfg, dict):
        cfg = {}
    if not (cfg.get("entry") or (cfg.get("target") or {}).get("path")):
        cfg["entry"] = _guess_entry(root)
    return Project(root, cfg)


def url_project(url):
    host = urlparse(url).netloc or "web"
    return Project(None, {"id": "web-" + host, "name": host}, mode="url", url=url)


def project_from_target(text):
    """Klasör, .html dosyası veya web adresi -> Project (olmazsa None)."""
    text = (text or "").strip().strip('"')
    if not text:
        return None
    if os.path.isdir(text):
        return load_project(text)
    if os.path.isfile(text) and text.lower().endswith(HTML_EXT):
        d, f = os.path.split(os.path.abspath(text))
        pid = "file-" + hashlib.sha1(os.path.abspath(text).encode("utf-8")).hexdigest()[:10]
        return Project(d, {"id": pid, "name": os.path.splitext(f)[0], "entry": f})
    p = urlparse(text)
    if p.scheme in ("http", "https") and p.netloc:
        return url_project(text)
    if "." in text and " " not in text and not os.path.exists(text):
        return url_project("https://" + text)
    return None


# ---- son açılanlar ----
def _settings_path():
    return os.path.join(data_root(), "settings.json")


def load_recents():
    s = read_json(_settings_path(), {})
    r = s.get("recents", []) if isinstance(s, dict) else []
    return [x for x in r if isinstance(x, dict) and x.get("target")]


def add_recent(kind, target, limit=12):
    s = read_json(_settings_path(), {})
    if not isinstance(s, dict):
        s = {}
    r = [x for x in s.get("recents", []) if x.get("target") != target]
    r.insert(0, {"kind": kind, "target": target})
    s["recents"] = r[:limit]
    write_json(_settings_path(), s)


def clear_recents():
    s = read_json(_settings_path(), {})
    if isinstance(s, dict):
        s["recents"] = []
        write_json(_settings_path(), s)
