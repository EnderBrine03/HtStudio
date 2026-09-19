"""Sahte PyQt5 ile: modüller içe aktarılabiliyor mu, köprü mantığı ve enjekte edilen JS doğru mu?"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()

try:
    import PyQt5.QtWebEngineWidgets  # noqa: F401  (gerçek PyQt5 varsa onu kullan)
    REAL_QT = True
except ImportError:
    import qt_stub
    qt_stub.install()
    REAL_QT = False

from app import config, permissions  # noqa: E402


class BridgeLogic(unittest.TestCase):
    def setUp(self):
        from app import bridge
        self.bridge = bridge
        self.answers = []
        proj = config.Project(tempfile.mkdtemp(), {"id": "br.test", "permissions": ["fs", "exec"]})
        store = permissions.PermissionStore(os.path.join(tempfile.mkdtemp(), "p.json"))
        self.ctx = permissions.AppContext(proj, store, lambda p, d: self.answers.pop(0))
        self.b = bridge.Bridge(self.ctx, object(), lambda: None)

    def call(self, m, *a):
        return json.loads(self.b.call(m, json.dumps(list(a))))

    def test_appdata_roundtrip(self):
        r = self.call("fs.writeText", "not.txt", "merhaba ğü")
        self.assertTrue(r["ok"])
        self.assertEqual(self.call("fs.readText", "not.txt")["data"], "merhaba ğü")
        self.assertEqual(self.call("fs.list", ".")["data"][0]["name"], "not.txt")
        self.assertTrue(self.call("fs.remove", "not.txt")["ok"])

    def test_denials(self):
        r = self.call("fs.readText", "../../secret.txt")
        self.assertFalse(r["ok"])
        self.assertIn("izni yok", r["error"])
        self.assertFalse(self.call("clipboard.readText")["ok"])       # bildirilmemiş
        self.assertFalse(self.call("nope")["ok"])
        self.assertFalse(self.call("fs.writeText", "x.exe", "MZ")["ok"])

    def test_exec_prompt_denied(self):
        self.answers = [(False, False)]
        exe = os.path.join(tempfile.mkdtemp(), "prog")
        open(exe, "w").write("")
        r = self.call("exec", exe, ["a"])
        self.assertFalse(r["ok"])
        self.assertIn("izin vermedi", r["error"])

    def test_permission_api(self):
        self.assertEqual(self.call("permission.query", "clipboard")["data"], "undeclared")
        self.assertEqual(self.call("permission.query", "fs")["data"], "prompt")
        self.assertFalse(self.call("permission.request", "bilinmeyen")["ok"])


class InjectedJS(unittest.TestCase):
    def test_bridge_js_valid_and_formats(self):
        from app import bridge
        js = bridge.BRIDGE_JS % {"QWEBCHANNEL": "function QWebChannel(){}"}
        f = os.path.join(tempfile.mkdtemp(), "b.js")
        open(f, "w", encoding="utf-8").write(js)
        if shutil.which("node"):
            r = subprocess.run(["node", "--check", f], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)


class Imports(unittest.TestCase):
    def test_modules_import(self):
        import importlib
        for m in ("app.dialogs", "app.webwindow", "app.launcher_ui"):
            importlib.import_module(m)


if __name__ == "__main__":
    unittest.main()
