@echo off
setlocal enabledelayedexpansion
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

set /a deneme=0

:yeniden_baslat

rem ================================================================
rem PORT ONCEDEN KONTROLU (2026-09-16): Daha once bu betik, 8000 portu
rem baskasi tarafindan kullanildiginda ("WinError 10048") kor korune
rem uvicorn'u baslatmayi deniyor, kacinilmaz sekilde patliyor, 5 saniye
rem bekleyip TEKRAR deniyor -- sonsuza kadar. Kullaniciya ASLA neden
rem calismadigi soylenmiyordu, sadece "beklenmedik sekilde durdu" gibi
rem belirsiz bir mesaj goruyorlardi. Bu genellikle PTS'in kapatilmamis
rem eski bir kopyasinin (baska bir pencere, ya da NSSM/Windows Servisi
rem olarak kurulmussa arka plandaki servis) portu zaten tutmasindan
rem kaynaklanir. Artik baslamadan ONCE port bos mu diye bakiyoruz ve
rem doluysa hangi PID oldugunu soyleyip ne yapilmasi gerektigini
rem aciklayip DURUYORUZ -- garantili basarisiz bir baslatma denemesi
rem yapip kullaniciyi sonsuz bir dongude birakmiyoruz.
set "port_pid="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /C:":8000 " ^| findstr /C:"LISTENING"') do set "port_pid=%%p"
if defined port_pid (
    echo.
    echo ============================================================
    echo HATA: 8000 portu zaten baska bir islem tarafindan kullaniliyor ^(PID %port_pid%^).
    echo Bu genellikle PTS'in kapatilmamis eski bir kopyasinin ^(baska bir
    echo pencere, ya da Windows Servisi olarak kurulduysa arka plandaki
    echo servisin^) portu zaten tutmasindan kaynaklanir.
    echo.
    echo Cozum:
    echo   1^) O islemin gercekten eski/artik bir PTS kopyasi oldugundan
    echo      emin olmak icin: tasklist /FI "PID eq %port_pid%"
    echo   2^) Eminseniz kapatmak icin: taskkill /PID %port_pid% /F
    echo   3^) PTS'i Windows Servisi olarak da kurduysaniz ^(NSSM^), ikisini
    echo      AYNI ANDA calistirmayin -- yalnizca birini secin.
    echo Ardindan bu pencereyi kapatip PTS'i tekrar baslatin.
    echo ============================================================
    pause
    exit /b 1
)

for /f %%t in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()"') do set "baslangic_zamani=%%t"

".venv\Scripts\python.exe" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
set "cikis_kodu=%errorlevel%"

if "%cikis_kodu%" == "0" goto :son

for /f %%t in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()"') do set "bitis_zamani=%%t"
set /a calisma_suresi=%bitis_zamani%-%baslangic_zamani%

rem En az 60 saniye sorunsuz calistiysa bu, kalici bir yapilandirma
rem sorunu degil GECICI bir olaydi (aginin bir anlik kesintisi vb.) --
rem deneme sayacini sifirlayip normal otomatik-yeniden-baslatmaya devam
rem ediyoruz. Calisma cok kisa surduyse (ayni sorunun hemen tekrar
rem etme ihtimali yuksek, tipik ornek: bir baslangic/yapilandirma
rem hatasi) sayaci artiriyoruz.
if %calisma_suresi% GEQ 60 (
    set /a deneme=0
)
set /a deneme+=1

if %deneme% GEQ 5 (
    echo.
    echo ============================================================
    echo PTS art arda %deneme% kez kisa surede beklenmedik sekilde durdu.
    echo Bu genellikle tekrar eden ayni sorunun ^(yanlis yapilandirma,
    echo eksik bagimlilik, vb.^) her seferinde hemen tekrar olustugu
    echo anlamina gelir -- otomatik yeniden baslatma DURDURULDU.
    echo Olasi nedeni gormek icin loglar\pts.log dosyasina bakin.
    echo ============================================================
    pause
    exit /b 1
)

echo.
echo PTS beklenmedik sekilde durdu ^(deneme %deneme%/5^). 5 saniye icinde yeniden baslatiliyor...
echo Tamamen kapatmak icin bu pencereyi kapatin.
timeout /t 5 /nobreak >nul
goto yeniden_baslat

:son
endlocal
