"""Ana pencere: adres/dosya aç, html-css-js yükleyerek proje oluştur, projeleri yönet."""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from . import config, library
from .dialogs import LibraryDialog, PermissionsDialog
from .webwindow import AppWindow

WEB_FILTER = "Web dosyaları (*.html *.htm *.css *.js)"


class LauncherWindow(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.windows = {}            # proje id -> AppWindow (aynı uygulama iki kez açılmaz)
        self.setWindowTitle("HtStudio Launcher")
        self.resize(780, 660)
        self.setAcceptDrops(True)

        w = QWidget()
        self.setCentralWidget(w)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(32, 28, 32, 24)
        lay.setSpacing(12)

        t = QLabel("HtStudio Launcher")
        t.setObjectName("title")
        lay.addWidget(t)
        sub = QLabel("Bir siteyi, HTML dosyasını ya da klasörünü aç; veya html / css / js dosyalarını yükleyip proje oluştur.")
        sub.setWordWrap(True)
        sub.setObjectName("muted")
        lay.addWidget(sub)

        row = QHBoxLayout()
        self.addr = QLineEdit()
        self.addr.setPlaceholderText("Adres yaz veya .html / klasör yolunu yapıştır")
        self.addr.returnPressed.connect(self.open_address)
        go = QPushButton("Aç")
        go.setObjectName("primary")
        go.clicked.connect(self.open_address)
        row.addWidget(self.addr, 1)
        row.addWidget(go)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        for text, fn in (("HTML dosyası aç…", self.pick_html), ("Klasör aç…", self.pick_folder),
                         ("Yeni proje: dosya yükle…", self.new_project)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row2.addWidget(b)
        lay.addLayout(row2)

        lay.addWidget(QLabel("Projelerim ve son açılanlar"))
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self.run_selected())
        self.list.currentItemChanged.connect(lambda *_: self.update_buttons())
        lay.addWidget(self.list, 1)

        row3 = QHBoxLayout()
        self.btn_run = QPushButton("Çalıştır")
        self.btn_run.setObjectName("primary")
        self.btn_run.clicked.connect(self.run_selected)
        self.btn_add = QPushButton("Dosya ekle…")
        self.btn_add.clicked.connect(self.add_files)
        self.btn_libs = QPushButton("Kütüphaneler…")
        self.btn_libs.clicked.connect(self.libs)
        self.btn_perm = QPushButton("İzinler…")
        self.btn_perm.clicked.connect(self.perms)
        self.btn_del = QPushButton("Sil / Kaldır")
        self.btn_del.clicked.connect(self.delete_selected)
        for b in (self.btn_run, self.btn_add, self.btn_libs, self.btn_perm, self.btn_del):
            row3.addWidget(b)
        lay.addLayout(row3)
        self.refresh()

    # ---------------------------------------------------------------- liste
    def entries(self):
        out, seen = [], set()
        pd = config.projects_dir()
        for n in sorted(os.listdir(pd)):
            d = os.path.join(pd, n)
            if os.path.isfile(os.path.join(d, "launcher.json")):
                out.append(("project", d))
                seen.add(os.path.realpath(d))
        for r in config.load_recents():
            if r["kind"] != "project" and r["target"] not in seen:
                out.append((r["kind"], r["target"]))
        return out

    def refresh(self):
        self.list.clear()
        for kind, target in self.entries():
            proj = config.project_from_target(target) if kind != "url" else config.url_project(target)
            if proj is None:
                continue
            tag = {"project": "Proje", "url": "Web", "file": "Dosya", "dir": "Klasör"}.get(kind, kind)
            it = QListWidgetItem("[%s]  %s\n%s" % (tag, proj.name, target))
            it.setData(Qt.UserRole, (kind, target))
            self.list.addItem(it)
        self.update_buttons()

    def selected(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def update_buttons(self):
        sel = self.selected()
        kind = sel[0] if sel else None
        self.btn_run.setEnabled(sel is not None)
        self.btn_del.setEnabled(sel is not None)
        self.btn_add.setEnabled(kind == "project")
        self.btn_libs.setEnabled(sel is not None and kind != "url")
        self.btn_perm.setEnabled(sel is not None)

    def project_of(self, sel):
        kind, target = sel
        return config.url_project(target) if kind == "url" else config.project_from_target(target)

    # ---------------------------------------------------------------- çalıştır
    def run_project(self, proj, kind, target):
        if proj is None:
            QMessageBox.warning(self, "Açılamadı", "Geçerli bir adres, .html dosyası veya klasör değil.")
            return
        old = self.windows.get(proj.id)
        if old is not None and old.isVisible():
            old.raise_()
            old.activateWindow()
            return
        if proj.mode == "local" and not os.path.isfile(os.path.join(proj.root, proj.entry)):
            QMessageBox.warning(self, "Açılamadı", "Başlangıç dosyası bulunamadı: " + proj.entry)
            return
        win = AppWindow(proj, self.store)
        self.windows[proj.id] = win
        win.destroyed.connect(lambda *_, pid=proj.id: self.windows.pop(pid, None))
        if kind != "project":
            config.add_recent(kind, target)
            self.refresh()

    def run_selected(self):
        sel = self.selected()
        if sel:
            self.run_project(self.project_of(sel), *sel)

    def open_address(self):
        text = self.addr.text().strip()
        proj = config.project_from_target(text)
        kind = "url" if proj is not None and proj.mode == "url" else ("dir" if os.path.isdir(text) else "file")
        target = proj.url if kind == "url" and proj else text.strip('"')
        self.run_project(proj, kind, target)

    def pick_html(self):
        p, _ = QFileDialog.getOpenFileName(self, "HTML dosyası seç", "", "HTML (*.html *.htm)")
        if p:
            self.addr.setText(p)
            self.open_address()

    def pick_folder(self):
        p = QFileDialog.getExistingDirectory(self, "Proje klasörünü seç")
        if p:
            self.addr.setText(os.path.normpath(p))
            self.open_address()

    # ---------------------------------------------------------------- yükleme / düzenleme
    def new_project(self):
        files, _ = QFileDialog.getOpenFileNames(self, "HTML / CSS / JS dosyalarını seç", "", WEB_FILTER)
        if not files:
            return
        default = os.path.splitext(os.path.basename(files[0]))[0]
        name, ok = QInputDialog.getText(self, "Yeni proje", "Proje adı:", text=default)
        if not ok:
            return
        try:
            root = library.create_project(name or default, files)
        except library.LibraryError as e:
            QMessageBox.warning(self, "Proje oluşturulamadı", str(e))
            return
        self.refresh()
        self.run_project(config.load_project(root), "project", root)

    def add_files(self):
        sel = self.selected()
        if not sel or sel[0] != "project":
            return
        files, _ = QFileDialog.getOpenFileNames(self, "Projeye eklenecek dosyalar", "", WEB_FILTER)
        for f in files:
            try:
                library.add_project_file(sel[1], f)
            except library.LibraryError as e:
                QMessageBox.warning(self, "Eklenemedi", str(e))

    def libs(self):
        sel = self.selected()
        if sel:
            p = self.project_of(sel)
            if p and p.mode == "local":
                LibraryDialog(p.id, p.name, self).exec_()

    def perms(self):
        sel = self.selected()
        if sel:
            p = self.project_of(sel)
            if p:
                PermissionsDialog(p, self.store, self).exec_()

    def delete_selected(self):
        sel = self.selected()
        if not sel:
            return
        kind, target = sel
        if kind == "project":
            if QMessageBox.question(self, "Projeyi sil", "Bu proje ve dosyaları silinsin mi?\n" + target) != QMessageBox.Yes:
                return
            try:
                library.delete_project(target)
            except library.LibraryError as e:
                QMessageBox.warning(self, "Silinemedi", str(e))
        else:
            recents = [r for r in config.load_recents() if r["target"] != target]
            config.clear_recents()
            for r in reversed(recents):
                config.add_recent(r["kind"], r["target"])
        self.refresh()

    # ---------------------------------------------------------------- sürükle-bırak
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        text = urls[0].toLocalFile() if urls and urls[0].isLocalFile() else (urls[0].toString() if urls else e.mimeData().text())
        self.addr.setText(text)
        self.open_address()
