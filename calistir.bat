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
set "ilk_baslatma=1"

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
rem
rem 2026-09-25: Bu "dur ve kullaniciya sor" davranisi artik YALNIZCA ilk
rem baslatmada gecerli (kullanici o anda pencerenin basinda). Bir cokmeden
rem SONRAKI otomatik yeniden baslatmalarda port hala doluysa (tipik neden:
rem coken surecin soketi birkac saniye daha birakmamasi), betik artik
rem kapanip gorevli kimse fark edene kadar nizamiyeyi PTS'siz birakmiyor --
rem bekleyip tekrar deniyor.
set "port_pid="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /C:":8000 " ^| findstr /C:"LISTENING"') do set "port_pid=%%p"
if defined port_pid if not "%ilk_baslatma%" == "1" (
    echo.
    echo UYARI: 8000 portu hala dolu ^(PID %port_pid%^). 30 saniye sonra tekrar denenecek...
    timeout /t 30 /nobreak >nul
    goto yeniden_baslat
)
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

set "ilk_baslatma=0"
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

rem ================================================================
rem 2026-09-25 (sistem taramasi): Eskiden art arda 5 kisa cokmeden sonra
rem betik "pause" + "exit" ile KALICI olarak duruyordu. Bu, gozetimsiz
rem calisan bir nizamiye sisteminde en kotu sonuc: gecici ama birkac
rem dakika suren bir sorun (ag surucusu gec gelmesi, SQL Server'in
rem henuz ayaga kalkmamis olmasi, disk anlik dolu vb.) tum sistemi biri
rem gelip pencereye bakana kadar -- belki saatlerce -- kapali birakiyordu.
rem Artik durmuyoruz; bunun yerine bekleme suresini ARTIRIYORUZ (5 sn ->
rem 60 sn -> 5 dk) ki kalici bir yapilandirma hatasi logu/CPU'yu
rem bogmasin, ama sorun kendiliginden duzeldiginde PTS de kendiliginden
rem geri gelsin.
set /a bekleme_sn=5
if %deneme% GEQ 5 set /a bekleme_sn=60
if %deneme% GEQ 10 set /a bekleme_sn=300

echo.
if %deneme% GEQ 5 (
    echo ============================================================
    echo UYARI: PTS art arda %deneme% kez kisa surede beklenmedik sekilde durdu.
    echo Bu genellikle tekrar eden ayni bir soruna ^(yanlis yapilandirma,
    echo veritabanina ulasilamamasi, eksik bagimlilik vb.^) isaret eder.
    echo Olasi nedeni gormek icin loglar\pts.log dosyasina bakin.
    echo Otomatik yeniden baslatma DURDURULMUYOR -- sorun duzeldiginde PTS
    echo kendiliginden geri gelecek.
    echo ============================================================
)
echo PTS beklenmedik sekilde durdu ^(deneme %deneme%^). %bekleme_sn% saniye icinde yeniden baslatiliyor...
echo Tamamen kapatmak icin bu pencereyi kapatin.
timeout /t %bekleme_sn% /nobreak >nul
goto yeniden_baslat

:son
endlocal
