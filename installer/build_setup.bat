@echo off
setlocal
cd /d "%~dp0"
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo Inno Setup 6 bulunamadi.
    echo https://jrsoftware.org/isdl.php adresinden Inno Setup'i kurun.
    pause
    exit /b 1
)
"%ISCC%" PTS.iss
if errorlevel 1 (
    echo Setup derlemesi basarisiz.
    pause
    exit /b 1
)
echo Setup hazir: installer\output\SPY-PTS-Setup.exe
pause
