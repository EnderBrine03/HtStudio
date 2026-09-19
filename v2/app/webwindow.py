"""Uygulama penceresi: gömülü Chromium (QtWebEngine) + güvenli yerel içerik sunumu + izinler."""
import json
import logging
import mimetypes
import os
from urllib.parse import unquote

from PyQt5.QtCore import QByteArray, QFile, QIODevice, QTimer, QUrl, Qt
from PyQt5.QtGui import QDesktopServices, QIcon, QKeySequence
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestJob, QWebEngineUrlScheme, QWebEngineUrlSchemeHandler
from PyQt5.QtWebEngineWidgets import (QWebEnginePage, QWebEngineProfile, QWebEngineScript,
                                      QWebEngineSettings, QWebEngineView)
from PyQt5.QtWidgets import (QApplication, QFileDialog, QMainWindow, QShortcut, QStyle, QSystemTrayIcon)

from . import config, library
from .bridge import BRIDGE_JS, Bridge
from .dialogs import LibraryDialog, PermissionsDialog, ask_permission
from .permissions import AppContext

log = logging.getLogger("htstudio")


# ---------------------------------------------------------------- şema (QApplication'dan ÖNCE çağır)
def register_scheme():
    s = QWebEngineUrlScheme(QByteArray(config.SCHEME.encode()))
    s.setSyntax(QWebEngineUrlScheme.Host)
    s.setFlags(QWebEngineUrlScheme.SecureScheme | QWebEngineUrlScheme.CorsEnabled)
    QWebEngineUrlScheme.registerScheme(s)


_MIME = {".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
         ".svg": "image/svg+xml", ".wasm": "application/wasm", ".webmanifest": "application/manifest+json",
         ".mp4": "video/mp4", ".webm": "video/webm", ".ogg": "audio/ogg", ".mp3": "audio/mpeg",
         ".wav": "audio/wav", ".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff",
         ".woff2": "font/woff2", ".ico": "image/x-icon", ".txt": "text/plain; charset=utf-8"}


def mime_for(path):
    ext = os.path.splitext(path)[1].lower()
    return _MIME.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"


class AppSchemeHandler(QWebEngineUrlSchemeHandler):
    """htstudio://app/<yol>  ->  proje klasöründeki dosya. Klasör dışına çıkış reddedilir."""

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = os.path.realpath(root)

    def requestStarted(self, job):
        rel = unquote(job.requestUrl().path()).lstrip("/")
        path = os.path.realpath(os.path.join(self.root, rel)) if rel else self.root
        if not config.within(self.root, path):
            return job.fail(QWebEngineUrlRequestJob.RequestDenied)
        if os.path.isdir(path):
            path = os.path.join(path, "index.html")
        if not os.path.isfile(path):
            return job.fail(QWebEngineUrlRequestJob.UrlNotFound)
        f = QFile(path, job)
        if not f.open(QIODevice.ReadOnly):
            return job.fail(QWebEngineUrlRequestJob.RequestFailed)
        job.reply(QByteArray(mime_for(path).encode()), f)


# ---------------------------------------------------------------- web özellik izinleri
def _feature_map():
    pairs = [("Notifications", ["notifications"]), ("Geolocation", ["geolocation"]),
             ("MediaAudioCapture", ["microphone"]), ("MediaVideoCapture", ["camera"]),
             ("MediaAudioVideoCapture", ["microphone", "camera"]), ("MouseLock", ["pointerlock"]),
             ("DesktopVideoCapture", ["screen"]), ("DesktopAudioVideoCapture", ["screen", "microphone"])]
    out = {}
    for name, perms in pairs:
        f = getattr(QWebEnginePage, name, None)
        if f is not None:
            out[f] = perms
    return out


FEATURE_PERMS = None
_tray = None


def get_tray():
    global _tray
    if _tray is None and QSystemTrayIcon.isSystemTrayAvailable():
        icon = QApplication.windowIcon()
        if icon.isNull():
            icon = QApplication.style().standardIcon(QStyle.SP_ComputerIcon)
        _tray = QSystemTrayIcon(icon)
        _tray.setVisible(True)
    return _tray


class PopupCatcher(QWebEnginePage):
    """window.open / target=_blank isteklerini yakalar."""

    def __init__(self, owner):
        super().__init__(owner.profile(), owner)
        self.owner = owner

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        self.owner.open_popup(url)
        QTimer.singleShot(0, self.deleteLater)
        return False


class AppPage(QWebEnginePage):
    def __init__(self, profile, ctx, parent=None):
        super().__init__(profile, parent)
        self.ctx = ctx
        self.featurePermissionRequested.connect(self._on_feature)

    def _on_feature(self, origin, feature):
        global FEATURE_PERMS
        if FEATURE_PERMS is None:
            FEATURE_PERMS = _feature_map()
        perms = FEATURE_PERMS.get(feature)
        where = self.ctx.name if origin.scheme() == config.SCHEME else origin.toString()
        ok = bool(perms) and all(self.ctx.request(p, detail=where) for p in perms)
        self.setFeaturePermission(origin, feature,
                                  QWebEnginePage.PermissionGrantedByUser if ok else QWebEnginePage.PermissionDeniedByUser)

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        scheme = url.scheme()
        if not is_main_frame:
            return scheme != "file"                      # alt çerçeveler yerel dosya okuyamaz
        if scheme in ("about", "blob", "data"):
            return True
        if self.ctx.project.mode == "local":
            if scheme == config.SCHEME:
                return True
            if scheme in ("http", "https", "mailto"):    # dış bağlantılar sistem tarayıcısında açılır
                QDesktopServices.openUrl(url)
            return False
        return scheme in ("http", "https")               # web modunda file:// yasak

    def createWindow(self, window_type):
        return PopupCatcher(self)

    def javaScriptConsoleMessage(self, level, message, line, source):
        log.debug("JS[%s:%s] %s", source, line, message)


class AppWindow(QMainWindow):
    def __init__(self, project, store):
        super().__init__()
        self.project, self.store = project, store
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.ctx = AppContext(project, store, lambda perm, detail: ask_permission(self, project.name, perm, detail))
        self.setWindowTitle(project.name)

        icon = os.path.join(project.root, str(project.cfg.get("icon", ""))) if project.root and project.cfg.get("icon") else ""
        if icon and os.path.isfile(icon) and config.within(project.root, icon):
            self.setWindowIcon(QIcon(icon))

        # --- profil (her uygulamanın çerezleri/localStorage'ı ayrı) ---
        self.profile = QWebEngineProfile(project.id, self)
        base = config.app_dir(project.id, "profile")
        self.profile.setPersistentStoragePath(os.path.join(base, "data"))
        self.profile.setCachePath(os.path.join(base, "cache"))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        self.profile.downloadRequested.connect(self._on_download)
        if hasattr(self.profile, "setNotificationPresenter"):
            self.profile.setNotificationPresenter(self._present_notification)

        self.handler = None
        if project.mode == "local":
            self.handler = AppSchemeHandler(project.root, self)
            self.profile.installUrlSchemeHandler(QByteArray(config.SCHEME.encode()), self.handler)

        # --- sayfa ---
        self.page = AppPage(self.profile, self.ctx, self)
        self._settings()
        self.view = QWebEngineView(self)
        self.view.setPage(self.page)
        self.setCentralWidget(self.view)
        self.page.fullScreenRequested.connect(self._on_fullscreen)

        if project.mode == "local":
            self._install_bridge()
            self._install_libs()

        # --- pencere ---
        w = project.window
        self.resize(int(w["width"]), int(w["height"]))
        if not w.get("resizable", True):
            self.setFixedSize(int(w["width"]), int(w["height"]))
        for keys, fn in (("F5", self.view.reload), ("F11", self.toggle_fullscreen),
                         ("Ctrl+Shift+P", self.show_permissions), ("Ctrl+Shift+L", self.show_libs)):
            QShortcut(QKeySequence(keys), self, activated=fn)

        self.view.load(QUrl(project.start_url()))
        if w.get("fullscreen"):
            self.showFullScreen()
        else:
            self.show()

    # ---------------------------------------------------------------- kurulum
    def _settings(self):
        s = self.page.settings()
        def setting(name, value):
            attr = getattr(QWebEngineSettings, name, None)
            if attr is not None:
                s.setAttribute(attr, value)
        setting("LocalContentCanAccessFileUrls", False)
        setting("LocalContentCanAccessRemoteUrls", False)
        setting("JavascriptCanOpenWindows", True)
        setting("JavascriptCanAccessClipboard", False)   # pano yalnızca köprü + izin ile
        setting("PlaybackRequiresUserGesture", False)
        setting("FullScreenSupportEnabled", True)
        setting("ScreenCaptureEnabled", True)
        setting("WebGLEnabled", True)
        setting("Accelerated2dCanvasEnabled", True)
        setting("PluginsEnabled", False)

    def _script(self, name, source, point):
        sc = QWebEngineScript()
        sc.setName(name)
        sc.setSourceCode(source)
        sc.setInjectionPoint(point)
        sc.setWorldId(QWebEngineScript.MainWorld)
        sc.setRunsOnSubFrames(False)
        self.page.scripts().insert(sc)

    def _install_bridge(self):
        f = QFile(":/qtwebchannel/qwebchannel.js")
        if not f.open(QIODevice.ReadOnly):
            log.warning("qwebchannel.js bulunamadı; htstudio köprüsü devre dışı.")
            return
        qwc = bytes(f.readAll()).decode("utf-8", "replace")
        f.close()
        self.bridge = Bridge(self.ctx, self, get_tray)
        self.channel = QWebChannel(self.page)
        self.channel.registerObject("bridge", self.bridge)
        self.page.setWebChannel(self.channel, QWebEngineScript.MainWorld)
        self._script("htstudio-bridge", BRIDGE_JS % {"QWEBCHANNEL": qwc}, QWebEngineScript.DocumentCreation)

    def _install_libs(self):
        sources = []
        for rel in self.project.libs:                      # geliştiricinin projeyle gönderdiği kütüphaneler
            p = os.path.join(self.project.root, rel)
            if rel.lower().endswith((".js", ".css")) and config.within(self.project.root, p) and os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8") as fh:
                        sources.append((rel, os.path.splitext(rel)[1].lower(), fh.read()))
                except OSError:
                    pass
        sources += library.enabled_sources(self.project.id)  # kullanıcının eklediği kütüphaneler
        for name, ext, text in sources:
            if ext == ".js":
                self._script("lib:" + name, text, QWebEngineScript.DocumentCreation)
            else:
                css = ("(function(){var s=document.createElement('style');s.setAttribute('data-htstudio-lib',%s);"
                       "s.textContent=%s;(document.head||document.documentElement).appendChild(s);})();"
                       % (json.dumps(name), json.dumps(text)))
                self._script("lib:" + name, css, QWebEngineScript.DocumentReady)

    # ---------------------------------------------------------------- olaylar
    def open_popup(self, url):
        if url.scheme() in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)
        elif url.scheme() == config.SCHEME and self.project.mode == "local":
            self.view.load(url)

    def _on_download(self, item):
        path, _ = QFileDialog.getSaveFileName(self, "Dosyayı kaydet", item.path())
        if not path:
            item.cancel()
            return
        if hasattr(item, "setDownloadFileName"):
            item.setDownloadDirectory(os.path.dirname(path))
            item.setDownloadFileName(os.path.basename(path))
        else:
            item.setPath(path)
        item.accept()

    def _present_notification(self, note):
        tray = get_tray()
        if tray:
            tray.showMessage(note.title(), note.message())
        note.show()

    def _on_fullscreen(self, req):
        req.accept()
        self.showFullScreen() if req.toggleOn() else self.showNormal()

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def show_permissions(self):
        PermissionsDialog(self.project, self.store, self).exec_()

    def show_libs(self):
        if self.project.mode == "local":
            LibraryDialog(self.project.id, self.project.name, self).exec_()

    def closeEvent(self, e):
        try:
            self.view.setPage(None)
            self.page.deleteLater()
        except Exception:  # noqa
            pass
        super().closeEvent(e)
