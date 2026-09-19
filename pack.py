"""Kullanım:  python pack.py <HtStudioRuntime.exe> <proje-klasörü> <çıktı.exe>
Proje klasörünün kökünde launcher.json bulunmalı. Windows gerekmez (Linux'ta da çalışır)."""
import io
import os
import shutil
import struct
import sys
import zipfile


def pack(stub, project, out):
    if not os.path.isfile(os.path.join(project, "launcher.json")):
        sys.exit("Hata: %s/launcher.json bulunamadı." % project)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(project):
            for n in files:
                p = os.path.join(root, n)
                z.write(p, os.path.relpath(p, project).replace(os.sep, "/"))
    data = buf.getvalue()
    shutil.copyfile(stub, out)
    with open(out, "ab") as f:
        f.write(data + b"HTSPACK1" + struct.pack("<I", len(data)))
    return len(data)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    n = pack(*sys.argv[1:])
    print("Oluşturuldu: %s  (proje verisi: %d KB)" % (sys.argv[3], n // 1024))
