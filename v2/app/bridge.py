"""JS <-> Python köprüsü (QWebChannel). Sayfada  window.htstudio  olarak görünür.
Her çağrı izin modelinden geçer (bkz. permissions.py). Yalnızca yerel (htstudio://app) sayfalarda etkindir."""
import base64
import json
import locale
import os
import platform
import subprocess

from PyQt5.QtCore import QObject, QTimer, QUrl, pyqtSlot
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QApplication, QFileDialog, QSystemTrayIcon

from . import config
from .permissions import PERM_LABELS, FsPolicy

MAX_READ_TEXT = 20 * 1024 * 1024
MAX_READ_BIN = 50 * 1024 * 1024


class Bridge(QObject):
    def __init__(self, ctx, window, tray_getter):
        super().__init__(window)
        self.ctx, self.win, self._tray = ctx, window, tray_getter
        self.policy = FsPolicy(ctx)
        self.methods = {
            "info": self.m_info,
            "permission.query": self.m_perm_query,
            "permission.request": self.m_perm_request,
            "fs.appData": lambda: self.policy.private,
            "fs.pickFolder": self.m_pick_folder,
            "fs.pickOpenFile": self.m_pick_open,
            "fs.pickSaveFile": self.m_pick_save,
            "fs.list": self.m_list,
            "fs.readText": self.m_read_text,
            "fs.readBase64": self.m_read_b64,
            "fs.writeText": self.m_write_text,
            "fs.writeBase64": self.m_write_b64,
            "fs.exists": lambda p: os.path.exists(self.policy.resolve(p)),
            "fs.mkdir": self.m_mkdir,
            "fs.remove": self.m_remove,
            "fs.stat": self.m_stat,
            "clipboard.readText": self.m_clip_read,
            "clipboard.writeText": self.m_clip_write,
            "notify": self.m_notify,
            "exec": self.m_exec,
            "open": self.m_open,
            "window.setTitle": lambda t: self.win.setWindowTitle(str(t)),
            "window.setFullscreen": self.m_fullscreen,
            "window.minimize": lambda: self.win.showMinimized(),
            "window.close": lambda: QTimer.singleShot(0, self.win.close),
        }

    @pyqtSlot(str, str, result=str)
    def call(self, method, args_json):
        try:
            fn = self.methods.get(method)
            if fn is None:
                raise ValueError("Bilinmeyen yöntem: " + method)
            args = json.loads(args_json or "[]")
            if not isinstance(args, list):
                raise ValueError("Geçersiz argümanlar")
            return json.dumps({"ok": True, "data": fn(*args)}, ensure_ascii=False)
        except Exception as e:  # noqa
            return json.dumps({"ok": False, "error": str(e) or e.__class__.__name__}, ensure_ascii=False)

    # ---- genel ----
    def m_info(self):
        return {"app": self.ctx.name, "id": self.ctx.id, "version": self.ctx.project.version,
                "launcher": config.VERSION, "os": platform.platform(), "arch": platform.machine(),
                "cpus": os.cpu_count(), "language": (locale.getdefaultlocale()[0] or ""),
                "appData": self.policy.private, "permissions": sorted(self.ctx.project.permissions)}

    def m_perm_query(self, name):
        return self.ctx.state(str(name))

    def m_perm_request(self, name):
        name = str(name)
        if name not in PERM_LABELS:
            raise ValueError("Bilinmeyen izin: " + name)
        return self.ctx.request(name, detail="Uygulama bu izni açıkça istedi.")

    # ---- dosya sistemi ----
    def m_pick_folder(self):
        self.ctx.require("fs")
        path = QFileDialog.getExistingDirectory(self.win, "Uygulamaya erişim verilecek klasörü seç")
        if not path:
            return None
        path = os.path.normpath(path)
        self.ctx.store.add_folder(self.ctx.id, path)   # seçmek = izin vermek
        return path

    def m_pick_open(self, filters=None):
        self.ctx.require("fs")
        path, _ = QFileDialog.getOpenFileName(self.win, "Dosya seç", "", str(filters or "Tüm dosyalar (*.*)"))
        if not path:
            return None
        path = os.path.normpath(path)
        self.policy.allow_file(path)
        return path

    def m_pick_save(self, suggested=""):
        self.ctx.require("fs")
        path, _ = QFileDialog.getSaveFileName(self.win, "Kaydet", str(suggested or ""))
        if not path:
            return None
        path = os.path.normpath(path)
        self.policy.allow_file(path)
        return path

    def m_list(self, path):
        rp = self.policy.resolve(path)
        out = []
        for e in list(os.scandir(rp))[:5000]:
            try:
                st = e.stat(follow_symlinks=False)
                out.append({"name": e.name, "isDir": e.is_dir(follow_symlinks=False),
                            "size": st.st_size, "mtime": int(st.st_mtime)})
            except OSError:
                continue
        out.sort(key=lambda x: (not x["isDir"], x["name"].lower()))
        return out

    def _read(self, path, limit):
        rp = self.policy.resolve(path)
        if os.path.getsize(rp) > limit:
            raise ValueError("Dosya çok büyük.")
        with open(rp, "rb") as f:
            return f.read()

    def m_read_text(self, path):
        return self._read(path, MAX_READ_TEXT).decode("utf-8", "replace")

    def m_read_b64(self, path):
        return base64.b64encode(self._read(path, MAX_READ_BIN)).decode("ascii")

    def _write(self, path, data):
        rp = self.policy.resolve(path, write=True)
        os.makedirs(os.path.dirname(rp), exist_ok=True)
        with open(rp, "wb") as f:
            f.write(data)
        return len(data)

    def m_write_text(self, path, text):
        return self._write(path, str(text).encode("utf-8"))

    def m_write_b64(self, path, b64):
        data = base64.b64decode(str(b64), validate=True)
        if len(data) > MAX_READ_BIN:
            raise ValueError("Veri çok büyük.")
        return self._write(path, data)

    def m_mkdir(self, path):
        os.makedirs(self.policy.resolve(path, write=True), exist_ok=True)
        return True

    def m_remove(self, path):
        rp = self.policy.resolve(path, write=True)
        if os.path.isdir(rp):
            os.rmdir(rp)          # yalnızca boş klasör
        else:
            os.remove(rp)
        return True

    def m_stat(self, path):
        st = os.stat(self.policy.resolve(path))
        return {"size": st.st_size, "mtime": int(st.st_mtime), "isDir": os.path.isdir(self.policy.resolve(path))}

    # ---- pano / bildirim ----
    def _need(self, perm, detail=""):
        self.ctx.require(perm)
        if not self.ctx.request(perm, detail):
            raise PermissionError("Kullanıcı '%s' iznini vermedi." % perm)

    def m_clip_read(self):
        self._need("clipboard")
        return QApplication.clipboard().text()

    def m_clip_write(self, text):
        self._need("clipboard")
        QApplication.clipboard().setText(str(text))
        return True

    def m_notify(self, title, message=""):
        self._need("notify")
        tray = self._tray()
        if tray is None:
            return False
        tray.showMessage(str(title)[:100], str(message)[:500], QSystemTrayIcon.Information, 5000)
        return True

    # ---- sistem ----
    def m_exec(self, path, args=None):
        self.ctx.require("exec")
        rp = os.path.realpath(str(path))
        if not os.path.isfile(rp):
            raise FileNotFoundError("Program bulunamadı: " + rp)
        args = [str(a) for a in (args or [])][:50]
        key = "exec:%s|%s" % (os.path.normcase(rp), json.dumps(args))
        if not self.ctx.request("exec", detail=" ".join([rp] + args), key=key):
            raise PermissionError("Kullanıcı programın çalışmasına izin vermedi.")
        subprocess.Popen([rp] + args, cwd=os.path.dirname(rp), close_fds=True)   # shell=False
        return True

    def m_open(self, target):
        target = str(target)
        if target.lower().startswith(("http://", "https://", "mailto:")):
            return QDesktopServices.openUrl(QUrl(target))
        self.ctx.require("open")
        rp = os.path.realpath(target)
        if not os.path.exists(rp):
            raise FileNotFoundError("Bulunamadı: " + rp)
        if not self.ctx.request("open", detail=rp, key="open:" + os.path.normcase(rp)):
            raise PermissionError("Kullanıcı açmaya izin vermedi.")
        if hasattr(os, "startfile"):
            os.startfile(rp)  # type: ignore[attr-defined]
            return True
        return QDesktopServices.openUrl(QUrl.fromLocalFile(rp))

    def m_fullscreen(self, on=True):
        self.win.showFullScreen() if on else self.win.showNormal()
        return bool(on)


# Sayfaya enjekte edilir. Yalnızca htstudio://app kaynağında çalışır.
BRIDGE_JS = r"""
(function(){
  if (location.protocol !== 'htstudio:' || window.htstudio) return;
  %(QWEBCHANNEL)s
  var ready = new Promise(function(resolve){
    (function init(){
      if (typeof qt === 'undefined' || !qt.webChannelTransport) return setTimeout(init, 15);
      new QWebChannel(qt.webChannelTransport, function(ch){ resolve(ch.objects.bridge); });
    })();
  });
  function call(method, args){
    return ready.then(function(b){
      return new Promise(function(resolve, reject){
        b.call(method, JSON.stringify(args || []), function(raw){
          var r; try { r = JSON.parse(raw); } catch(e){ return reject(new Error('Geçersiz yanıt')); }
          if (r.ok) resolve(r.data); else reject(new Error(r.error));
        });
      });
    });
  }
  window.htstudio = {
    ready: ready.then(function(){ return true; }),
    info: function(){ return call('info'); },
    permission: {
      query:   function(n){ return call('permission.query', [n]); },
      request: function(n){ return call('permission.request', [n]); }
    },
    fs: {
      appData:      function(){ return call('fs.appData'); },
      pickFolder:   function(){ return call('fs.pickFolder'); },
      pickOpenFile: function(filters){ return call('fs.pickOpenFile', [filters]); },
      pickSaveFile: function(name){ return call('fs.pickSaveFile', [name]); },
      list:         function(p){ return call('fs.list', [p]); },
      readText:     function(p){ return call('fs.readText', [p]); },
      readBase64:   function(p){ return call('fs.readBase64', [p]); },
      writeText:    function(p, t){ return call('fs.writeText', [p, t]); },
      writeBase64:  function(p, b){ return call('fs.writeBase64', [p, b]); },
      exists:       function(p){ return call('fs.exists', [p]); },
      mkdir:        function(p){ return call('fs.mkdir', [p]); },
      remove:       function(p){ return call('fs.remove', [p]); },
      stat:         function(p){ return call('fs.stat', [p]); }
    },
    clipboard: {
      readText:  function(){ return call('clipboard.readText'); },
      writeText: function(t){ return call('clipboard.writeText', [t]); }
    },
    notify: function(title, message){ return call('notify', [title, message || '']); },
    exec:   function(path, args){ return call('exec', [path, args || []]); },
    open:   function(target){ return call('open', [target]); },
    window: {
      setTitle:      function(t){ return call('window.setTitle', [t]); },
      setFullscreen: function(on){ return call('window.setFullscreen', [on !== false]); },
      minimize:      function(){ return call('window.minimize'); },
      close:         function(){ return call('window.close'); }
    }
  };
  document.dispatchEvent(new Event('htstudio-init'));
})();
"""
