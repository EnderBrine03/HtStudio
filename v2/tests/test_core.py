"""Qt gerektirmeyen çekirdek testleri:  python -m unittest discover -s tests -v"""
import io
import os
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
_TMP = tempfile.mkdtemp()
os.environ["LOCALAPPDATA"] = _TMP

from app import config, library, payload, permissions  # noqa: E402
import pack  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def write(path, data=b""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode())
    return path


class PayloadTests(unittest.TestCase):
    def test_roundtrip_append_and_sidecar(self):
        d = tempfile.mkdtemp()
        stub = write(os.path.join(d, "stub.exe"), b"MZ" + b"\0" * 4000)
        out = os.path.join(d, "app.exe")
        n = pack.pack(stub, os.path.join(ROOT, "sample-project"), out)
        data = payload.read_payload(out)
        self.assertEqual(len(data), n)
        p = payload.extract_payload(data, base=d)
        self.assertTrue(os.path.isfile(os.path.join(p, "launcher.json")))
        out2 = os.path.join(d, "side.exe")
        pack.pack(stub, os.path.join(ROOT, "sample-project"), out2, sidecar=True)
        self.assertEqual(payload.read_payload(out2), data)
        self.assertIsNone(payload.read_payload(stub))

    def test_zip_slip_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("../evil.txt", "x")
        with self.assertRaises(ValueError):
            payload.extract_payload(buf.getvalue(), base=tempfile.mkdtemp())


class LibraryTests(unittest.TestCase):
    def test_names(self):
        self.assertEqual(library.validate_name("a/b/jquery.min.js", library.LIB_EXT), "jquery.min.js")
        for bad in ("x.exe", "x.png", "con.js", "..js", "a.js.exe", "x.html"):
            with self.assertRaises(library.LibraryError):
                library.validate_name(bad, library.LIB_EXT)

    def test_content(self):
        with self.assertRaises(library.LibraryError):
            library.check_content(b"MZ\x90\x00binary")
        with self.assertRaises(library.LibraryError):
            library.check_content(b"var a;\x00")
        self.assertIn("ğ", library.check_content("var s='ğ'".encode("utf-8")))

    def test_libs_lifecycle(self):
        d = tempfile.mkdtemp()
        js = write(os.path.join(d, "lib.js"), "window.L=1;")
        css = write(os.path.join(d, "s.css"), "body{}")
        library.add_lib_file("t.app", js)
        library.add_lib_file("t.app", css)
        self.assertEqual([x[0] for x in library.enabled_sources("t.app")], ["lib.js", "s.css"])
        library.set_enabled("t.app", "lib.js", False)
        self.assertEqual([x[0] for x in library.enabled_sources("t.app")], ["s.css"])
        library.remove_lib("t.app", "s.css")
        self.assertEqual(library.list_libs("t.app").__len__(), 1)
        with self.assertRaises(library.LibraryError):
            library.add_lib_url("t.app", "http://x.com/a.js")

    def test_create_project(self):
        d = tempfile.mkdtemp()
        h = write(os.path.join(d, "index.html"), "<h1>x</h1>")
        c = write(os.path.join(d, "a.css"), "h1{}")
        root = library.create_project("Deneme Proje", [h, c])
        cfg = config.read_json(os.path.join(root, "launcher.json"), {})
        self.assertEqual(cfg["entry"], "index.html")
        proj = config.load_project(root)
        self.assertTrue(proj.user_owned)
        with self.assertRaises(library.LibraryError):
            library.create_project("x", [c])                       # html yok
        with self.assertRaises(library.LibraryError):
            library.create_project("x", [write(os.path.join(d, "p.png"), "x"), h])
        library.set_declared_permissions(root, ["fs", "clipboard"])
        self.assertEqual(config.load_project(root).permissions, {"fs", "clipboard"})
        library.delete_project(root)
        self.assertFalse(os.path.exists(root))
        with self.assertRaises(library.LibraryError):
            library.delete_project(d)                              # kullanıcı projesi değil


class PermissionTests(unittest.TestCase):
    def ctx(self, perms, answers):
        proj = config.Project(tempfile.mkdtemp(), {"id": "perm.test", "permissions": perms})
        store = permissions.PermissionStore(os.path.join(tempfile.mkdtemp(), "p.json"))
        calls = []
        def prompt(perm, detail):
            calls.append(perm)
            return answers.pop(0)
        return permissions.AppContext(proj, store, prompt), calls, store

    def test_declared_gate_and_remember(self):
        ctx, calls, store = self.ctx(["clipboard"], [(True, True), (False, False)])
        self.assertFalse(ctx.request("camera"))                    # bildirilmemiş
        self.assertEqual(calls, [])
        self.assertTrue(ctx.request("clipboard"))
        self.assertTrue(ctx.request("clipboard"))                  # hatırlandı, tekrar sorulmaz
        self.assertEqual(calls, ["clipboard"])
        self.assertEqual(ctx.state("clipboard"), "allow")
        self.assertEqual(ctx.state("fs"), "undeclared")

    def test_deny_not_remembered(self):
        ctx, calls, _ = self.ctx(["notify"], [(False, False), (True, False)])
        self.assertFalse(ctx.request("notify"))
        self.assertTrue(ctx.request("notify"))
        self.assertEqual(len(calls), 2)

    def test_fs_policy(self):
        ctx, _, store = self.ctx(["fs"], [])
        pol = permissions.FsPolicy(ctx)
        inside = pol.resolve("notlar/a.txt", write=True)           # özel klasör: izin gerekmez
        self.assertTrue(inside.startswith(pol.private))
        with self.assertRaises(PermissionError):
            pol.resolve("../../evil.txt")                           # kaçış
        outside = tempfile.mkdtemp()
        with self.assertRaises(PermissionError):
            pol.resolve(os.path.join(outside, "x.txt"))             # verilmemiş klasör
        store.add_folder(ctx.id, outside)
        self.assertTrue(pol.resolve(os.path.join(outside, "x.txt")))
        with self.assertRaises(PermissionError):
            pol.resolve(os.path.join(outside, "run.exe"), write=True)
        with self.assertRaises(PermissionError):
            pol.resolve(os.path.join(outside, "..", "y.txt"))
        # bildirilmemiş fs
        ctx2, _, s2 = self.ctx([], [])
        pol2 = permissions.FsPolicy(ctx2)
        s2.add_folder(ctx2.id, outside)
        with self.assertRaises(PermissionError):
            pol2.resolve(os.path.join(outside, "x.txt"))

    @unittest.skipIf(os.name == "nt", "symlink testi")
    def test_symlink_escape(self):
        ctx, _, store = self.ctx(["fs"], [])
        pol = permissions.FsPolicy(ctx)
        secret = tempfile.mkdtemp()
        os.symlink(secret, os.path.join(pol.private, "link"))
        with self.assertRaises(PermissionError):
            pol.resolve("link/gizli.txt")


class ConfigTests(unittest.TestCase):
    def test_targets(self):
        d = tempfile.mkdtemp()
        h = write(os.path.join(d, "oyun.html"), "<p>")
        p = config.project_from_target(h)
        self.assertEqual((p.mode, p.entry), ("local", "oyun.html"))
        self.assertEqual(config.project_from_target("example.com").url, "https://example.com")
        self.assertIsNone(config.project_from_target("bir cümle"))
        self.assertEqual(config.project_from_target(d).entry, "oyun.html")
        self.assertEqual(p.start_url(), "htstudio://app/oyun.html")

    def test_within(self):
        d = tempfile.mkdtemp()
        self.assertTrue(config.within(d, os.path.join(d, "a", "b")))
        self.assertFalse(config.within(d, os.path.join(d, "..")))
        self.assertFalse(config.within(os.path.join(d, "a"), os.path.join(d, "ab")))

    def test_recents(self):
        config.add_recent("url", "a.com"); config.add_recent("url", "b.com"); config.add_recent("url", "a.com")
        self.assertEqual([r["target"] for r in config.load_recents()], ["a.com", "b.com"])


if __name__ == "__main__":
    unittest.main()
