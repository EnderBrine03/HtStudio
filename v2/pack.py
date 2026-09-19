"""Derlenmiş HtStudio exe'sine proje ekler. Windows gerekmez.

  python pack.py <HtStudio.exe> <proje-klasörü> <çıktı.exe>             # tek dosya (payload exe'nin sonuna eklenir)
  python pack.py <HtStudio.exe> <proje-klasörü> <çıktı.exe> --sidecar   # exe + yanında <ad>.htpack

Proje klasörünün kökünde launcher.json olmalı.
--sidecar: PyInstaller --onedir çıktısında en güvenli yoldur (çıktı.exe'yi aynı klasöre koy).
"""
import io
import os
import shutil
import struct
import sys
import zipfile


def build_zip(project):
    if not os.path.isfile(os.path.join(project, "launcher.json")):
        sys.exit("Hata: %s/launcher.json bulunamadı." % project)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(project):
            for n in files:
                p = os.path.join(root, n)
                z.write(p, os.path.relpath(p, project).replace(os.sep, "/"))
    return buf.getvalue()


def pack(stub, project, out, sidecar=False):
    data = build_zip(project)
    shutil.copyfile(stub, out)
    if sidecar:
        with open(os.path.splitext(out)[0] + ".htpack", "wb") as f:
            f.write(data)
    else:
        with open(out, "ab") as f:
            f.write(data + b"HTSPACK1" + struct.pack("<I", len(data)))
    return len(data)


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(a) != 3:
        sys.exit(__doc__)
    n = pack(a[0], a[1], a[2], sidecar="--sidecar" in sys.argv)
    print("Oluşturuldu: %s  (proje verisi: %d KB)" % (a[2], n // 1024))
