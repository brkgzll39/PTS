@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo PTS Kurulum Araci
echo ========================================
echo.

where uv >nul 2>nul
if errorlevel 1 (
    echo HATA: uv bulunamadi.
    echo.
    echo uv kurmak icin PowerShell'de su komutu calistirin:
    echo powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
    echo Ardindan bu dosyayi yeniden calistirin.
    pause
    exit /b 1
)

echo Python 3.12 sanal ortami hazirlaniyor...
if not exist ".venv\Scripts\python.exe" uv venv .venv --python 3.12
if errorlevel 1 (
    echo HATA: Python 3.12 ortami olusturulamadi.
    pause
    exit /b 1
)

echo PTS bagimliliklari kuruluyor...
uv pip install --python ".venv\Scripts\python.exe" -r "backend\requirements.txt"
if errorlevel 1 (
    echo HATA: Bagimliliklar kurulamadi. Internet baglantisini kontrol edin.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m py_compile backend\main.py backend\models.py backend\schemas.py
if errorlevel 1 (
    echo HATA: Backend dogrulamasi basarisiz.
    pause
    exit /b 1
)

echo.
echo Kurulum tamamlandi.
echo Sistemi baslatmak icin calistir.bat dosyasini calistirin.
echo.
pause
endlocal
