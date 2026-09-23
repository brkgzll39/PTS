@echo off
setlocal enabledelayedexpansion
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

rem ================================================================
rem .ENV OTOMATIK OLUSTURMA (2026-09-23): PTS artik baslangicta ".env"
rem dosyasini GERCEKTEN okuyor (bkz. backend/__init__.py). Onceden bu
rem guvenlik-kritik anahtarlarin (PTS_LICENSE_SECRET, PTS_KAMERA_ANAHTARI,
rem PTS_ARVENTO_ANAHTARI) ayarlanmasi TAMAMEN kurulumu yapan kisiye/hafizaya
rem birakilmisti -- unutulursa sistem hicbir hata vermeden guvensiz
rem varsayilanlarla sessizce calismaya devam ederdi. Zaten bir ".env" varsa
rem (ornegin bu kurulum daha once yapilmis ya da elle olusturulmus)
rem DOKUNULMAZ -- yalnizca ILK kurulumda, dosya hic yoksa uretilir.
rem ================================================================
if not exist ".env" (
    echo.
    echo Ilk kurulum: guvenlik anahtarlari otomatik uretiliyor...
    set "PTS_YENI_LISANS_SECRET="
    set "PTS_YENI_KAMERA_ANAHTARI="
    set "PTS_YENI_ARVENTO_ANAHTARI="
    for /f "delims=" %%s in ('powershell -NoProfile -Command "[System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)) -replace '[^a-zA-Z0-9]',''" 2^>nul') do set "PTS_YENI_LISANS_SECRET=%%s"
    for /f "delims=" %%s in ('powershell -NoProfile -Command "[System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)) -replace '[^a-zA-Z0-9]',''" 2^>nul') do set "PTS_YENI_KAMERA_ANAHTARI=%%s"
    for /f "delims=" %%s in ('powershell -NoProfile -Command "[System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)) -replace '[^a-zA-Z0-9]',''" 2^>nul') do set "PTS_YENI_ARVENTO_ANAHTARI=%%s"
    if not defined PTS_YENI_LISANS_SECRET (
        echo UYARI: guvenlik anahtarlari otomatik uretilemedi ^(PowerShell calisamadi^).
        echo ".env" olusturulamadi -- .env.example'daki aciklamaya gore anahtarlari
        echo ELLE ayarlamaniz onerilir, aksi halde varsayilan/kimliksiz durumla calisir.
    ) else (
        (
            echo # Bu dosya kurulum.bat tarafindan ILK KURULUMDA otomatik olusturuldu.
            echo # Anahtarlari elle degistirmeyin/paylasmayin -- her kurulumun kendi
            echo # benzersiz degerine sahip olmasi gerekir. Ayrintili aciklama icin
            echo # .env.example dosyasina bakin.
            echo PTS_LICENSE_SECRET=!PTS_YENI_LISANS_SECRET!
            echo PTS_KAMERA_ANAHTARI=!PTS_YENI_KAMERA_ANAHTARI!
            echo PTS_ARVENTO_ANAHTARI=!PTS_YENI_ARVENTO_ANAHTARI!
        ) > ".env"
        echo .env dosyasi olusturuldu, guvenlik anahtarlari otomatik ayarlandi.
    )
) else (
    echo.
    echo .env dosyasi zaten var, dokunulmadi.
)

echo.
echo Kurulum tamamlandi.
echo Sistemi baslatmak icin calistir.bat dosyasini calistirin.
echo.
pause
endlocal
