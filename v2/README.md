# HtStudio Launcher (Python + PyQt5 / QtWebEngine)

Windows için "Android WebView" karşılığı. Gömülü Chromium (QtWebEngine) kullanır: WebView2 ya da başka
bir runtime gerekmez, Windows 7 - 11 çalışır. HTML uygulamalarını gerçek bir pencerede çalıştırır,
izin verilirse sisteme erişebilir.

## Çalıştırma (geliştirme)
    pip install -r requirements.txt      # ya da: python main.py  (eksik paketleri ilk açılışta kurmayı önerir)
    python main.py                       # Launcher penceresi
    python main.py sample-project        # bir klasörü doğrudan aç
    python main.py https://example.com   # web adresi (köprü yok, tüm izinler tek tek sorulur)
    python main.py --debug               # http://localhost:9222 üzerinden DevTools + ayrıntılı günlük
    python main.py --safe-mode           # GPU kapalı (ekran kartı sorunlarında)

Günlük: %LOCALAPPDATA%\HtStudio\htstudio.log

## Derleme (senin yaptığın kısım)
    build.bat
Çıktı: `dist\HtStudio\HtStudio.exe` (launcher). Uygulama exe'si üretmek için (Windows gerekmez):
    python pack.py dist\HtStudio\HtStudio.exe sample-project dist\HtStudio\Ornek.exe --sidecar
`--sidecar` yoksa proje ZIP'i exe'nin sonuna eklenir (tek dosya): biçim
`[exe][ZIP]["HTSPACK1"][uint32 LE uzunluk]`. Bu yöntemin PyInstaller exe'siyle çalıştığını doğrula;
çalışmazsa `--sidecar` kullan. Tarayıcıdan üretmek için aynı biçimi JSZip ile yazabilirsin.
Payload'lı exe açılınca launcher yerine doğrudan o uygulama açılır.

## Proje biçimi (launcher.json)
    {
      "id": "com.kullanici.uygulama",      // veri ayrımı için (localStorage, çerez, izinler)
      "name": "Uygulamam", "version": "1.0.0", "entry": "index.html",
      "window": { "width": 1100, "height": 700, "fullscreen": false, "resizable": true },
      "permissions": ["fs", "clipboard", "notify", "exec", "open", "geolocation", "camera", "microphone"],
      "libs": ["libs/jquery.min.js"],     // projeyle gelen .js/.css (her sayfaya otomatik yüklenir)
      "icon": "icon.png"
    }
İçerik `htstudio://app/...` adresinden sunulur: `fetch`, ES modülleri, WebGL, video vb. çalışır;
proje klasörü dışındaki hiçbir dosyaya erişilemez, `file://` kapalıdır.

## İzin modeli
1. Uygulama, kullanabileceği izinleri `permissions` içinde **bildirir**. Bildirilmeyen izin her zaman reddedilir.
2. İlk kullanımda kullanıcıya sorulur ("Kararımı hatırla" ile kalıcı olur).
3. Ctrl+Shift+P: izinleri görüntüle / sıfırla, erişim tanınan klasörleri kaldır.

| İzin | Ne sağlar |
|---|---|
| fs | Kullanıcının seçtiği klasör/dosyalarda okuma-yazma (yürütülebilir uzantılar yazılamaz) |
| clipboard | Panoya okuma/yazma |
| notify | Masaüstü bildirimi |
| exec | Program çalıştırma (her komut satırı için ayrı onay, `shell=False`) |
| open | Dosyayı varsayılan programla açma |
| geolocation, camera, microphone, screen, notifications, pointerlock | Standart web API'leri |

## JavaScript API  (`window.htstudio`, hepsi Promise döndürür)
    htstudio.info()                                  htstudio.permission.query(ad) / .request(ad)
    htstudio.fs.appData()                            // uygulamanın özel klasörü, izin gerekmez
    htstudio.fs.pickFolder() / pickOpenFile(filtre) / pickSaveFile(ad)
    htstudio.fs.list / readText / readBase64 / writeText / writeBase64 / exists / mkdir / remove / stat
    htstudio.clipboard.readText() / writeText(t)     htstudio.notify(başlık, mesaj)
    htstudio.exec(yol, [argümanlar])                 htstudio.open(yol | https-url)
    htstudio.window.setTitle / setFullscreen / minimize / close
Göreli yollar uygulamanın özel klasörüne göre çözülür. Örnek: `sample-project/app.js`.

## Kütüphane ve dosya yükleme
* **Launcher → "Yeni proje: dosya yükle…"**: yalnızca `.html .htm .css .js` seçilebilir; proje oluşturulur ve açılır.
  Dosyalar metin olmalı (ikili/exe/zip reddedilir), en fazla 5 MB.
* **Kütüphaneler…** (Ctrl+Shift+L): bir uygulamaya `.js` / `.css` kütüphanesi ekle — dosyadan veya `https://` adresinden
  (ör. cdnjs). Eklenenler her sayfaya otomatik yüklenir; F5 ile uygulanır.
* Kullanıcı projelerinin izinleri Launcher'daki **İzinler…** ekranından düzenlenir.

## Kısayollar
F5 yenile · F11 tam ekran · Ctrl+Shift+P izinler · Ctrl+Shift+L kütüphaneler

## Testler
    python -m unittest discover -s tests -v
Qt gerektirmeyen çekirdek + köprü mantığı test edilir (PyQt5 yoksa sahte modüllerle).

## Bilinen sınırlar
* Chromium sürümü PyQt5'e bağlıdır (Chromium 83). Win 10+ hedefliyorsan PySide6 (güncel Chromium) düşünülebilir.
* Özel şemadan sunulan videolar arama (seek) desteklemez.
* Gerçek pencere/izin akışları Windows'ta elle denenmelidir.
