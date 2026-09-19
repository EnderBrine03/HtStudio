"""Kullanıcı arayüzü parçaları: tema, izin sorusu, kütüphane ve izin yönetimi."""
import html
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QCheckBox, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
                             QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)

from . import library
from .permissions import PERM_LABELS, label

STYLE = """
QWidget{background:#0d0d1a;color:#eef2ff;font-family:"Segoe UI";font-size:10pt}
QLabel#title{font-size:20pt;font-weight:600}
QLabel#muted,QLabel.muted{color:#8b93ad}
QLineEdit,QListWidget{background:#111827;border:1px solid #2a3350;border-radius:6px;padding:6px}
QListWidget::item{padding:8px 6px;border-radius:4px}
QListWidget::item:selected{background:#22305f}
QPushButton{background:#1b2440;border:1px solid #2a3350;border-radius:6px;padding:8px 14px}
QPushButton:hover{border-color:#3b6bff}
QPushButton:disabled{color:#5c6480;background:#141a2e}
QPushButton#primary{background:#3b6bff;border-color:#3b6bff;color:white;font-weight:600}
QPushButton#primary:hover{background:#00d4ff;color:#001018}
QMessageBox,QDialog{background:#0d0d1a}
"""


def ask_permission(parent, app_name, perm, detail=""):
    """-> (izin_verildi, hatırla)"""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle("İzin isteği")
    box.setTextFormat(Qt.RichText)
    box.setText("<b>%s</b> şunu yapmak istiyor:" % html.escape(app_name))
    info = label(perm)
    if detail:
        info += "\n\n" + detail
    box.setInformativeText(info)
    remember = QCheckBox("Kararımı hatırla")
    box.setCheckBox(remember)
    allow = box.addButton("İzin ver", QMessageBox.AcceptRole)
    deny = box.addButton("Reddet", QMessageBox.RejectRole)
    box.setDefaultButton(deny)
    box.exec_()
    return box.clickedButton() is allow, remember.isChecked()


class LibraryDialog(QDialog):
    """Uygulamaya .js / .css kütüphanesi ekle (dosyadan veya https adresinden)."""

    def __init__(self, app_id, app_name, parent=None):
        super().__init__(parent)
        self.app_id = app_id
        self.setWindowTitle("Kütüphaneler - " + app_name)
        self.resize(520, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Eklenen .js ve .css dosyaları bu uygulamanın her sayfasına otomatik yüklenir.\n"
                             "Değişiklikler sayfa yenilenince (F5) uygulanır."))
        self.list = QListWidget()
        self.list.itemChanged.connect(self._toggled)
        lay.addWidget(self.list)
        row = QHBoxLayout()
        for text, fn in (("Dosyadan ekle…", self.add_file), ("URL'den ekle…", self.add_url), ("Kaldır", self.remove)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        close = QPushButton("Kapat")
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        lay.addWidget(close)
        self.refresh()

    def refresh(self):
        self.list.blockSignals(True)
        self.list.clear()
        for x in library.list_libs(self.app_id):
            it = QListWidgetItem(x["name"])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if x.get("enabled", True) else Qt.Unchecked)
            it.setData(Qt.UserRole, x["name"])
            it.setToolTip(str(x.get("source", "")))
            self.list.addItem(it)
        self.list.blockSignals(False)

    def _toggled(self, item):
        library.set_enabled(self.app_id, item.data(Qt.UserRole), item.checkState() == Qt.Checked)

    def _try(self, fn, *a):
        try:
            fn(self.app_id, *a)
        except library.LibraryError as e:
            QMessageBox.warning(self, "Eklenemedi", str(e))

    def add_file(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Kütüphane seç", "", "Kütüphane dosyaları (*.js *.css)")
        for p in paths:
            self._try(library.add_lib_file, p)
        self.refresh()

    def add_url(self):
        url, ok = QInputDialog.getText(self, "URL'den ekle", "https:// ile başlayan .js veya .css adresi:")
        if ok and url.strip():
            self._try(library.add_lib_url, url)
            self.refresh()

    def remove(self):
        it = self.list.currentItem()
        if it:
            library.remove_lib(self.app_id, it.data(Qt.UserRole))
            self.refresh()


class PermissionsDialog(QDialog):
    """Bildirilen izinler, verilen kararlar ve erişim tanınan klasörler."""

    def __init__(self, project, store, parent=None):
        super().__init__(parent)
        self.project, self.store = project, store
        self.setWindowTitle("İzinler - " + project.name)
        self.resize(560, 560)
        lay = QVBoxLayout(self)

        editable = project.mode == "local" and project.user_owned
        head = ("Bu uygulamanın isteyebileceği izinler:" if editable else
                "Uygulamanın bildirdiği izinler (yalnızca geliştirici değiştirebilir):")
        lay.addWidget(QLabel(head))
        self.declared = QListWidget()
        for key, text in PERM_LABELS.items():
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, key)
            it.setFlags((it.flags() | Qt.ItemIsUserCheckable) if editable else (it.flags() & ~Qt.ItemIsEnabled))
            it.setCheckState(Qt.Checked if key in project.permissions else Qt.Unchecked)
            self.declared.addItem(it)
        self.declared.setEnabled(project.mode == "local")
        lay.addWidget(self.declared, 3)

        lay.addWidget(QLabel("Verilen kararlar:"))
        self.decisions = QListWidget()
        lay.addWidget(self.decisions, 2)
        b = QPushButton("Seçili kararı sıfırla")
        b.clicked.connect(self.reset_one)
        lay.addWidget(b)

        lay.addWidget(QLabel("Erişim tanınan klasörler:"))
        self.folders = QListWidget()
        lay.addWidget(self.folders, 2)
        b2 = QPushButton("Seçili klasörü kaldır")
        b2.clicked.connect(self.remove_folder)
        lay.addWidget(b2)

        ok = QPushButton("Kaydet ve kapat")
        ok.setObjectName("primary")
        ok.clicked.connect(self.save)
        lay.addWidget(ok)
        self.refresh()

    def refresh(self):
        self.decisions.clear()
        for k, v in sorted(self.store.decisions(self.project.id).items()):
            it = QListWidgetItem("%s  →  %s" % (label(k) if ":" not in k else k, "İzinli" if v == "allow" else "Reddedildi"))
            it.setData(Qt.UserRole, k)
            self.decisions.addItem(it)
        self.folders.clear()
        for f in self.store.folders(self.project.id):
            self.folders.addItem(f)

    def reset_one(self):
        it = self.decisions.currentItem()
        if it:
            self.store.remove(self.project.id, it.data(Qt.UserRole))
            self.refresh()

    def remove_folder(self):
        it = self.folders.currentItem()
        if it:
            self.store.remove_folder(self.project.id, it.text())
            self.refresh()

    def save(self):
        if self.project.mode == "local" and self.project.user_owned:
            perms = [self.declared.item(i).data(Qt.UserRole) for i in range(self.declared.count())
                     if self.declared.item(i).checkState() == Qt.Checked]
            try:
                library.set_declared_permissions(self.project.root, perms)
                self.project.permissions = set(perms)
            except library.LibraryError as e:
                QMessageBox.warning(self, "Kaydedilemedi", str(e))
        self.accept()
