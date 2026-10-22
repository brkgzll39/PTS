@echo off
rem PTS demo ortami: gercek sisteme dokunmaz (veriler demo\ klasorunde). Bkz. araclar\demo.py
cd /d "%~dp0"
set PY=python
if exist .venv\Scripts\python.exe set PY=.venv\Scripts\python.exe
start "" cmd /c "timeout /t 8 >nul & start http://127.0.0.1:8100"
%PY% araclar\demo.py %*
pause
