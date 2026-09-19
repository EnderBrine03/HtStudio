"""exe'nin sonuna eklenmiş proje ZIP'ini okur ve güvenli biçimde açar.

Biçim:  [exe][ZIP]["HTSPACK1" (8 bayt)][ZIP uzunluğu uint32 LE (4 bayt)]
Yedek:  <exeadi>.htpack  (düz ZIP)  -> exe'nin yanında
"""
import hashlib
import io
import os
import shutil
import struct
import sys
import tempfile
import zipfile

MAGIC = b"HTSPACK1"
MAX_UNPACKED = 1 << 30  # 1 GB


def own_exe():
    return sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0] or __file__)


def read_payload(exe=None):
    exe = exe or own_exe()
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


def extract_payload(data, base=None):
    """ZIP'i geçici klasöre açar (yol kaçışı ve zip-bomb korumalı). Klasör yolunu döndürür."""
    h = hashlib.sha1(data).hexdigest()[:12]
    dest = os.path.join(base or tempfile.gettempdir(), "htstudio-" + h)
    if os.path.exists(os.path.join(dest, ".ok")):
        return dest
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    root = os.path.realpath(dest)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(i.file_size for i in z.infolist()) > MAX_UNPACKED:
            raise ValueError("Proje verisi çok büyük.")
        for info in z.infolist():
            target = os.path.realpath(os.path.join(dest, info.filename))
            if target != root and not target.startswith(root + os.sep):
                raise ValueError("Geçersiz dosya yolu: " + info.filename)
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    open(os.path.join(dest, ".ok"), "w").close()
    return dest
