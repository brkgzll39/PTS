@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo uv bulunamadi. Once kurulum.bat dosyasini calistirin.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo PTS kurulumu bulunamadi. Kurulum baslatiliyor...
    call "%~dp0kurulum.bat"
    if errorlevel 1 exit /b 1
)

echo.
echo PTS baslatiliyor. Tarayicidan http://localhost:8000 adresine gidin.
echo Durdurmak icin bu pencereye gelip CTRL+C tuslarina basin.
echo.

:yeniden_baslat
".venv\Scripts\python.exe" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
if errorlevel 1 (
    echo.
    echo PTS beklenmedik sekilde durdu. 5 saniye icinde yeniden baslatiliyor...
    echo Tamamen kapatmak icin bu pencereyi kapatin.
    timeout /t 5 /nobreak >nul
    goto yeniden_baslat
)

endlocal