"""HtStudio Launcher - giriş noktası.

  python main.py                      -> Launcher penceresi
  python main.py <klasör|.html|url>   -> doğrudan uygulamayı aç
  python main.py --project <klasör>   -> proje klasörünü çalıştır (geliştirme)
  --debug      : uzaktan hata ayıklama (http://localhost:9222) + ayrıntılı günlük
  --safe-mode  : GPU hızlandırmayı kapat (eski/sorunlu ekran kartları için)

exe'nin sonunda gömülü proje varsa (bkz. pack.py) launcher açılmaz, o uygulama çalışır.
"""
import logging
import os
import sys
import traceback

from app import config, deps


def setup_logging(debug):
    path = os.path.join(config.data_root(), "htstudio.log")
    handler = logging.FileHandler(path, encoding="utf-8")       # (Python 3.8'de basicConfig(encoding=) yok)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    return path


def main(argv):
    args = argv[1:]
    debug, safe = "--debug" in args, "--safe-mode" in args
    log_path = setup_logging(debug)

    if not deps.ensure():          # geliştirme modunda eksik paketleri kurar; exe'de atlanır
        return 1

    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    if safe:
        flags += " --disable-gpu"
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags.strip()
    if debug:
        os.environ.setdefault("QTWEBENGINE_REMOTE_DEBUGGING", "9222")

    from PyQt5.QtCore import QCoreApplication, Qt
    from PyQt5 import QtWebEngineWidgets  # noqa: F401  (QApplication'dan önce içe aktarılmalı)
    from app import payload, webwindow
    from app.dialogs import STYLE
    from app.permissions import PermissionStore

    webwindow.register_scheme()                                   # QApplication'dan ÖNCE
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    from PyQt5.QtWidgets import QApplication, QMessageBox
    qapp = QApplication(sys.argv)
    qapp.setApplicationName(config.APP_NAME)
    qapp.setStyleSheet(STYLE)

    def hook(t, v, tb):
        logging.error("".join(traceback.format_exception(t, v, tb)))
        try:
            QMessageBox.critical(None, "HtStudio", "Beklenmeyen hata:\n%s\n\nAyrıntı: %s" % (v, log_path))
        except Exception:  # noqa
            pass
    sys.excepthook = hook

    store = PermissionStore()
    positional = [a for a in args if not a.startswith("--")]
    project = None
    if "--project" in args:
        i = args.index("--project")
        project = config.project_from_target(args[i + 1] if i + 1 < len(args) else "")
    elif positional:
        project = config.project_from_target(positional[0])
    else:
        data = payload.read_payload()                             # exe'ye gömülü uygulama var mı?
        if data:
            try:
                project = config.load_project(payload.extract_payload(data))
            except Exception as e:  # noqa
                QMessageBox.critical(None, "HtStudio", "Gömülü proje açılamadı:\n%s" % e)
                return 1

    if project is not None:
        first = webwindow.AppWindow(project, store)
    else:
        from app.launcher_ui import LauncherWindow
        first = LauncherWindow(store)
        first.show()
    qapp._first = first                                            # referansı canlı tut
    return qapp.exec_()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
