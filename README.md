# HtStudio Runtime (Python bootstrapper + paylaşımlı Chromium)

Her uygulama exe'si küçüktür (~10 MB). Chromium motoru ilk açılışta BİR KEZ indirilir
ve tüm HtStudio uygulamaları tarafından paylaşılır (%LOCALAPPDATA%\HtStudio\runtime).

  Windows 7/8/8.1 -> Electron 22.3.27      Windows 10+ -> Electron 33.0.0 (bootstrap.py'de değiştir)

## Akış
1. exe kendi sonundaki proje ZIP'ini okur:  [exe][ZIP]["HTSPACK1"][uint32 LE uzunluk]
   (yoksa yanındaki <exeadi>.htpack dosyasını okur)
2. Motor yoksa küçük bir pencerede indirir, SHA-256 doğrular (SHASUMS256.txt).
3. shell/ dosyalarını kurar, motoru başlatır -> launcher arayüzü -> "Oyna" -> HTML WebView'da açılır.

## Derleme (Windows gerekir; Colab olmaz)
GitHub'a yükle, Actions > build-stub > çıktı: HtStudioRuntime.exe
veya Windows'ta:
    pip install pyinstaller
    pyinstaller --onefile --noconsole --name HtStudioRuntime --add-data "shell;shell" bootstrap.py

## Proje ekleme (Windows gerekmez)
    python pack.py dist/HtStudioRuntime.exe sample-project Ornek.exe
Tarayıcıdan: browser-build.js  (aynı format)

## Geliştirme testi
    python bootstrap.py --project sample-project

## launcher.json
id, name, version, developer, description,
target {type: html|url|exe, path}, window {width,height,fullscreen,resizable},
gui {shape: horizontal|vertical, accent, background {color,image,video}},
download {url,file,force}
