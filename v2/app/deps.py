"""Geliştirme modunda (python main.py) eksik paketleri ilk açılışta kurar.
Derlenmiş exe'de bu adım atlanır: her şey exe'nin içine gömülüdür."""
import importlib
import subprocess
import sys

REQUIRED = [("PyQt5", "PyQt5>=5.15.9"), ("PyQt5.QtWebEngineWidgets", "PyQtWebEngine>=5.15.6")]


def missing():
    out = []
    for mod, pkg in REQUIRED:
        try:
            importlib.import_module(mod)
        except ImportError:
            out.append(pkg)
    return out


def _ask(text):
    if sys.stdin is not None and sys.stdin.isatty():
        return input(text + " [E/h] ").strip().lower() not in ("h", "n", "hayır", "hayir")
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        ok = messagebox.askyesno("HtStudio", text)
        r.destroy()
        return ok
    except Exception:
        return True


def ensure():
    if getattr(sys, "frozen", False):
        return True
    need = missing()
    if not need:
        return True
    if not _ask("Eksik paketler var: %s\nŞimdi kurulsun mu?" % ", ".join(need)):
        return False
    code = subprocess.call([sys.executable, "-m", "pip", "install", "--disable-pip-version-check"] + need)
    importlib.invalidate_caches()
    if code != 0 or missing():
        print("Kurulum başarısız. Elle deneyin:  pip install -r requirements.txt", file=sys.stderr)
        return False
    return True
