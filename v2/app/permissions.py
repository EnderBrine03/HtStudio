"""İzin deposu, uygulama bağlamı ve dosya sistemi politikası. (Qt gerektirmez.)

Model (Android'e benzer):
  1. Uygulama, launcher.json -> "permissions" içinde hangi izinleri isteyebileceğini BİLDİRİR.
  2. Bildirilmeyen izin her zaman reddedilir.
  3. Bildirilen izin ilk kullanımda kullanıcıya sorulur; karar isteğe bağlı hatırlanır.
"""
import os

from . import config

PERM_LABELS = {
    "fs":            "Seçtiğin klasörlerdeki dosyaları okuma/yazma",
    "clipboard":     "Panoya (kopyala/yapıştır) erişme",
    "notify":        "Masaüstü bildirimi gösterme",
    "exec":          "Bilgisayarında bir program çalıştırma",
    "open":          "Bir dosyayı sistem varsayılan programıyla açma",
    "geolocation":   "Konumuna erişme",
    "camera":        "Kamerana erişme",
    "microphone":    "Mikrofonuna erişme",
    "notifications": "Web bildirimleri gösterme",
    "screen":        "Ekranını paylaşma",
    "pointerlock":   "Fare imlecini kilitleme",
}

# Yazma yoluyla çalıştırılabilir dosya bırakılmasını engeller
BLOCKED_WRITE_EXT = {".exe", ".dll", ".bat", ".cmd", ".com", ".scr", ".msi", ".ps1", ".psm1",
                     ".vbs", ".vbe", ".jse", ".wsf", ".wsh", ".lnk", ".reg", ".hta", ".cpl", ".jar", ".pif"}


def label(perm):
    key = perm.split(":", 1)[0]
    return PERM_LABELS.get(key, perm)


class PermissionStore:
    """{app_id: {"perms": {anahtar: "allow"|"deny"}, "folders": [yol, ...]}}"""

    def __init__(self, path=None):
        self.path = path or os.path.join(config.data_root(), "permissions.json")
        d = config.read_json(self.path, {})
        self.data = d if isinstance(d, dict) else {}

    def _app(self, app_id):
        return self.data.setdefault(app_id, {"perms": {}, "folders": []})

    def _save(self):
        config.write_json(self.path, self.data)

    def get(self, app_id, key):
        return self.data.get(app_id, {}).get("perms", {}).get(key)

    def set(self, app_id, key, value):
        self._app(app_id).setdefault("perms", {})[key] = value
        self._save()

    def remove(self, app_id, key):
        self.data.get(app_id, {}).get("perms", {}).pop(key, None)
        self._save()

    def decisions(self, app_id):
        return dict(self.data.get(app_id, {}).get("perms", {}))

    def reset(self, app_id):
        self.data.pop(app_id, None)
        self._save()

    def folders(self, app_id):
        return list(self.data.get(app_id, {}).get("folders", []))

    def add_folder(self, app_id, path):
        path = os.path.realpath(path)
        f = self._app(app_id).setdefault("folders", [])
        if path not in f:
            f.append(path)
            self._save()

    def remove_folder(self, app_id, path):
        f = self.data.get(app_id, {}).get("folders", [])
        if path in f:
            f.remove(path)
            self._save()


class AppContext:
    """Bir uygulamanın izin kararlarını verir. prompt(perm, detail) -> (izin_verildi, hatırla)"""

    def __init__(self, project, store, prompt):
        self.project, self.store, self.prompt = project, store, prompt

    @property
    def id(self):
        return self.project.id

    @property
    def name(self):
        return self.project.name

    def is_declared(self, perm):
        return self.project.mode != "local" or perm in self.project.permissions

    def require(self, perm):
        if not self.is_declared(perm):
            raise PermissionError("'%s' izni launcher.json içindeki \"permissions\" listesinde bildirilmemiş." % perm)

    def state(self, perm):
        if not self.is_declared(perm):
            return "undeclared"
        return self.store.get(self.id, perm) or "prompt"

    def request(self, perm, detail="", key=None):
        if not self.is_declared(perm):
            return False
        key = key or perm
        st = self.store.get(self.id, key)
        if st == "allow":
            return True
        if st == "deny":
            return False
        allowed, remember = self.prompt(perm, detail)
        if remember:
            self.store.set(self.id, key, "allow" if allowed else "deny")
        return bool(allowed)


class FsPolicy:
    """JS'in dosya erişimini sınırlar.
       * Uygulamanın özel klasörü (appData): izin gerekmez
       * Kullanıcının seçtiği klasörler/dosyalar: 'fs' izni gerekir
       * Diğer her yer: reddedilir (.. ve symlink kaçışları çözülür)"""

    def __init__(self, ctx):
        self.ctx = ctx
        self.private = os.path.realpath(config.app_dir(ctx.id, "data"))
        self.files = set()  # oturum boyunca seçilen tek tek dosyalar

    def allow_file(self, path):
        self.files.add(os.path.normcase(os.path.realpath(path)))

    def resolve(self, path, write=False):
        path = str(path)
        if not os.path.isabs(path):
            path = os.path.join(self.private, path)
        rp = os.path.realpath(path)
        if write and os.path.splitext(rp)[1].lower() in BLOCKED_WRITE_EXT:
            raise PermissionError("Bu dosya türü yazılamaz: " + os.path.splitext(rp)[1])
        if config.within(self.private, rp):
            return rp
        self.ctx.require("fs")
        if os.path.normcase(rp) in self.files:
            return rp
        for root in self.ctx.store.folders(self.ctx.id):
            if config.within(root, rp):
                return rp
        raise PermissionError("Bu yol için erişim izni yok: " + rp)
