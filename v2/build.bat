@echo off
REM HtStudio Launcher - Windows derleme betiği
REM Windows 7/8 desteği için Python 3.8 (x64) kullan; yalnızca Windows 10+ ise 3.9+ olur.
setlocal
py -3.8 -m venv venv 2>nul || py -3 -m venv venv
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller || goto :err

REM --- ÖNERİLEN: klasör çıktısı (hızlı açılır, .htpack yöntemi kesin çalışır) ---
pyinstaller --noconfirm --clean --noconsole --onedir --name HtStudio main.py || goto :err

REM --- İSTERSEN tek dosya (ilk açılışta yavaş; payload'ı exe'nin sonuna ekleme yöntemi test edilmeli) ---
REM pyinstaller --noconfirm --clean --noconsole --onefile --name HtStudio main.py

echo.
echo Cikti: dist\HtStudio\HtStudio.exe   (launcher olarak calisir)
echo Uygulama exe'si uretmek icin ornek:
echo   python pack.py dist\HtStudio\HtStudio.exe sample-project dist\HtStudio\Ornek.exe --sidecar
echo Ornek.exe ve Ornek.htpack ayni klasorde kalmali (HtStudio klasorunun icinde).
goto :eof
:err
echo Derleme basarisiz.
exit /b 1
