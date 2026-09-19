"""
HtStudio Bootstrapper (Windows)

Küçük bir Python programı (PyInstaller ile exe yapılır). İlk açılışta gerekli
Chromium motorunu (Electron) bir kez indirir ve TÜM HtStudio uygulamaları için
ortak klasöre kurar:  %LOCALAPPDATA%\\HtStudio\\runtime\\...
Sonraki açılışlarda indirme yoktur. Android'deki "System WebView" gibi çalışır.

Akış:
  1. Kendi exe'sinin sonundan proje ZIP'ini okur ve geçici klasöre açar.
  2. Motor yoksa: küçük bir pencerede indirir (SHA-256 doğrulamalı).
  3. shell/ dosyalarını kurar ve motoru başlatır. (Launcher arayüzü + WebView)

Yalnızca standart kütüphane kullanır; kullanıcının Python kurması gerekmez.

Test (geliştirme):  python bootstrap.py --project sample-project
"""
import ctypes
import hashlib
import io
import os
import platform
import queue
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile

APP_NAME = "HtStudio"
MAGIC = b"HTSPACK1"
SHELL_VERSION = "1"      # shell/ içeriği değişince artır
LEGACY_VER = "22.3.27"   # Windows 7 / 8 / 8.1 için son Electron
MODERN_VER = "33.0.0"    # Windows 10+ için; yayından önce güncel sürüme yükselt
MIRROR = os.environ.get("HTSTUDIO_ELECTRON_MIRROR", "https://github.com/electron/electron/releases/download")

BG, ACCENT, INK, MUTED = "#0d0d1a", "#3b6bff", "#eef2ff", "#8b93ad"


# ---------- yardımcılar ----------
def base_dir():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), APP_NAME)


def win_version():
    try:
        class OSVI(ctypes.Structure):
            _fields_ = [("size", ctypes.c_ulong), ("major", ctypes.c_ulong), ("minor", ctypes.c_ulong),
                        ("build", ctypes.c_ulong), ("platform", ctypes.c_ulong), ("csd", ctypes.c_wchar * 128)]
        o = OSVI()
        o.size = ctypes.sizeof(o)
        ctypes.windll.ntdll.RtlGetVersion(ctypes.byref(o))
        return o.major, o.minor
    except Exception:
        return 10, 0


def pick_version():
    return LEGACY_VER if win_version() < (10, 0) else MODERN_VER


def arch():
    m = (os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE")
         or platform.machine()).upper()
    if m in ("AMD64", "X86_64"):
        return "x64"
    if m == "ARM64":
        return "arm64"
    return "ia32"


def runtime_dir(ver):
    return os.path.join(base_dir(), "runtime", "electron-%s-%s" % (ver, arch()))


def runtime_ready(ver):
    return os.path.isfile(os.path.join(runtime_dir(ver), ".ok"))


def show_error(msg):
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror(APP_NAME, msg)
        r.destroy()
    except Exception:
        print(msg, file=sys.stderr)


# ---------- payload ----------
def own_exe():
    return sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)


def read_payload():
    """[exe][ZIP]["HTSPACK1"][uint32 LE ZIP uzunluğu]; yoksa <exe>.htpack (düz ZIP)."""
    exe = own_exe()
    try:
        with open(exe, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size > 12:
                f.seek(size - 12)
                foot = f.read(12)
                if foot[:8] == MAGIC:
                    n = struct.unpack("<I", foot[8:])[0]
                    if 0 < n <= size - 12:
                        f.seek(size - 12 - n)
                        return f.read(n)
    except OSError:
        pass
    side = os.path.splitext(exe)[0] + ".htpack"
    if os.path.isfile(side):
        with open(side, "rb") as f:
            return f.read()
    return None


def extract_payload(data):
    h = hashlib.sha1(data).hexdigest()[:12]
    dest = os.path.join(tempfile.gettempdir(), "htstudio-" + h)
    if not os.path.exists(os.path.join(dest, ".ok")):
        shutil.rmtree(dest, ignore_errors=True)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(dest)  # zipfile, ".." ve mutlak yolları temizler
        open(os.path.join(dest, ".ok"), "w").close()
    return dest


# ---------- motor indirme ----------
def fetch(url, dest, progress, cancel):
    req = urllib.request.Request(url, headers={"User-Agent": "HtStudio-Bootstrapper"})
    with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as out:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            if cancel.is_set():
                raise InterruptedError("İptal edildi.")
            chunk = r.read(64 * 1024)
            if not chunk:
                break
            out.write(chunk)
            got += len(chunk)
            progress(got, total)


def install_runtime(ver, progress, cancel):
    name = "electron-v%s-win32-%s.zip" % (ver, arch())
    base = "%s/v%s" % (MIRROR, ver)
    tmp = tempfile.mkdtemp(prefix="htstudio-dl-")
    try:
        sums = os.path.join(tmp, "SHASUMS256.txt")
        fetch(base + "/SHASUMS256.txt", sums, lambda g, t: None, cancel)
        expected = None
        with open(sums, encoding="utf-8") as f:
            for line in f:
                p = line.split()
                if len(p) == 2 and p[1].lstrip("*") == name:
                    expected = p[0].lower()
        if not expected:
            raise RuntimeError("Sağlama toplamı bulunamadı: " + name)

        zpath = os.path.join(tmp, name)
        fetch(base + "/" + name, zpath, progress, cancel)

        h = hashlib.sha256()
        with open(zpath, "rb") as f:
            for c in iter(lambda: f.read(1 << 20), b""):
                h.update(c)
        if h.hexdigest() != expected:
            raise RuntimeError("İndirilen dosya doğrulanamadı (SHA-256).")

        progress(-1, 0)  # "kuruluyor"
        final = runtime_dir(ver)
        stage = final + ".tmp"
        shutil.rmtree(stage, ignore_errors=True)
        os.makedirs(os.path.dirname(final), exist_ok=True)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(stage)
        open(os.path.join(stage, ".ok"), "w").close()
        shutil.rmtree(final, ignore_errors=True)
        os.rename(stage, final)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ensure_runtime(ver):
    """Kurulum penceresini gösterir. Başarılıysa True döner."""
    import tkinter as tk
    from tkinter import ttk, messagebox

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    root.title(APP_NAME)
    root.configure(bg=BG)
    root.resizable(False, False)
    w, h = 460, 190
    root.geometry("%dx%d+%d+%d" % (w, h, (root.winfo_screenwidth() - w) // 2, (root.winfo_screenheight() - h) // 2))

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("H.Horizontal.TProgressbar", troughcolor="#1b2033", background=ACCENT,
                    bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)

    tk.Label(root, text="Gerekli bileşenler indiriliyor", bg=BG, fg=INK,
             font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=28, pady=(28, 2))
    tk.Label(root, text="Bu işlem yalnızca ilk açılışta yapılır.", bg=BG, fg=MUTED,
             font=("Segoe UI", 10)).pack(anchor="w", padx=28)
    bar = ttk.Progressbar(root, style="H.Horizontal.TProgressbar", length=404, maximum=100)
    bar.pack(padx=28, pady=(22, 6))
    status = tk.Label(root, text="Başlıyor…", bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w")
    status.pack(fill="x", padx=28)

    q, cancel, state = queue.Queue(), threading.Event(), {"ok": False}

    def worker():
        try:
            install_runtime(ver, lambda g, t: q.put(("p", g, t)), cancel)
            q.put(("done",))
        except Exception as e:  # noqa
            q.put(("err", str(e)))

    def start():
        cancel.clear()
        threading.Thread(target=worker, daemon=True).start()

    def poll():
        try:
            while True:
                m = q.get_nowait()
                if m[0] == "p":
                    g, t = m[1], m[2]
                    if g < 0:
                        bar.configure(mode="indeterminate")
                        bar.start(12)
                        status.config(text="Kuruluyor…")
                    else:
                        if t:
                            bar["value"] = g * 100 / t
                        status.config(text="%.1f / %.1f MB" % (g / 1048576, t / 1048576) if t else "%.1f MB" % (g / 1048576))
                elif m[0] == "done":
                    state["ok"] = True
                    root.destroy()
                    return
                else:
                    bar.stop()
                    if cancel.is_set() or not messagebox.askretrycancel(APP_NAME, "İndirme başarısız:\n" + m[1]):
                        root.destroy()
                        return
                    bar.configure(mode="determinate")
                    bar["value"] = 0
                    start()
        except queue.Empty:
            pass
        root.after(80, poll)

    def on_close():
        cancel.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    start()
    root.after(80, poll)
    root.mainloop()
    return state["ok"]


# ---------- shell ----------
def install_shell():
    src = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "shell")
    dst = os.path.join(base_dir(), "shell", SHELL_VERSION)
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return dst


def main():
    args = sys.argv[1:]
    if "--project" in args:
        project = os.path.abspath(args[args.index("--project") + 1])
    else:
        data = read_payload()
        if data is None:
            show_error("Bu uygulamanın proje verisi bulunamadı.")
            return 1
        try:
            project = extract_payload(data)
        except Exception as e:
            show_error("Proje dosyaları açılamadı:\n%s" % e)
            return 1

    ver = pick_version()
    if not runtime_ready(ver) and not ensure_runtime(ver):
        return 1

    exe = os.path.join(runtime_dir(ver), "electron.exe")
    subprocess.Popen([exe, install_shell(), "--project=" + project], cwd=project, close_fds=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
