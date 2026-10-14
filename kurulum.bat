@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ========================================
echo PTS Kurulum Araci
echo ========================================
echo.

rem ================================================================
rem KURULUM PAKETI (2026-10-14): PTS-Kurulum.exe ile kurulduysa klasorde
rem gomulu Python 3.12 ("python\"), tum Windows paketleri ("paket\") ve
rem plaka modelleri ("modeller\") bulunur -- internet ve uv GEREKMEZ.
rem Bunlar yoksa (proje klasoru elle kopyalandiysa) eskisi gibi uv ile
rem internetten kurulur.
rem ================================================================
if exist "python\python.exe" (
    echo Gomulu Python 3.12 kullaniliyor...
    if not exist ".venv\Scripts\python.exe" "python\python.exe" -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo HATA: Python sanal ortami olusturulamadi.
        goto hata
    )
    echo PTS bagimliliklari kuruluyor ^(kamera kutuphaneleri dahil^)...
    if exist "paket\" (
        ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --no-index --find-links paket -r "backend\requirements-windows.txt"
    ) else (
        ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "backend\requirements-windows.txt"
    )
    if errorlevel 1 (
        echo HATA: Bagimliliklar kurulamadi.
        goto hata
    )
    goto bagimliliklar_tamam
)

where uv >nul 2>nul
if errorlevel 1 (
    echo HATA: uv bulunamadi.
    echo.
    echo uv kurmak icin PowerShell'de su komutu calistirin:
    echo powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
    echo Ardindan bu dosyayi yeniden calistirin.
    goto hata
)

echo Python 3.12 sanal ortami hazirlaniyor...
if not exist ".venv\Scripts\python.exe" uv venv .venv --python 3.12
if errorlevel 1 (
    echo HATA: Python 3.12 ortami olusturulamadi.
    goto hata
)

echo PTS bagimliliklari kuruluyor...
uv pip install --python ".venv\Scripts\python.exe" -r "backend\requirements-windows.txt"
if errorlevel 1 (
    echo HATA: Bagimliliklar kurulamadi. Internet baglantisini kontrol edin.
    goto hata
)

:bagimliliklar_tamam
call :modelleri_kopyala

rem Kamera kutuphaneleri (onnxruntime) Microsoft Visual C++ 2015-2022
rem calisma zamanina ihtiyac duyar; cogu bilgisayarda vardir ama yoksa
rem kameralar acilista "DLL load failed" ile hic calismaz. Burada acikca
rem denenir ki sorun kurulumda, anlasilir bir mesajla gorulsun.
".venv\Scripts\python.exe" -c "import onnxruntime, cv2, fast_alpr" >nul 2>nul
if errorlevel 1 (
    echo.
    echo ============================================================
    echo UYARI: Kamera kutuphaneleri yuklenemedi. Buyuk ihtimalle bu
    echo bilgisayarda Microsoft Visual C++ 2015-2022 Redistributable x64
    echo kurulu degil. Panel calisir ama kameralar plaka OKUMAZ.
    echo Cozum: https://aka.ms/vs/17/release/vc_redist.x64.exe dosyasini
    echo indirip kurun, ardindan PTS'i yeniden baslatin.
    echo ============================================================
    echo.
)

".venv\Scripts\python.exe" -m py_compile backend\main.py backend\models.py backend\schemas.py
if errorlevel 1 (
    echo HATA: Backend dogrulamasi basarisiz.
    goto hata
)

rem ================================================================
rem 2026-10-14: anahtar uretimi eskiden statik
rem RandomNumberGenerator.GetBytes(32) cagiriyordu; bu yalnizca .NET 6+
rem (PowerShell 7) icinde var -- Windows'la gelen PowerShell 5.1'de hata
rem verip .env HIC olusturulmuyordu. Create().GetBytes($b) her ikisinde de
rem calisir.
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
    for /f "delims=" %%s in ('powershell -NoProfile -Command "$b=New-Object byte[] 32;[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b);[System.Convert]::ToBase64String($b) -replace '[^a-zA-Z0-9]',''" 2^>nul') do set "PTS_YENI_LISANS_SECRET=%%s"
    for /f "delims=" %%s in ('powershell -NoProfile -Command "$b=New-Object byte[] 32;[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b);[System.Convert]::ToBase64String($b) -replace '[^a-zA-Z0-9]',''" 2^>nul') do set "PTS_YENI_KAMERA_ANAHTARI=%%s"
    for /f "delims=" %%s in ('powershell -NoProfile -Command "$b=New-Object byte[] 32;[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b);[System.Convert]::ToBase64String($b) -replace '[^a-zA-Z0-9]',''" 2^>nul') do set "PTS_YENI_ARVENTO_ANAHTARI=%%s"
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
if /i not "%~1" == "otomatik" pause
endlocal
exit /b 0

:hata
rem "otomatik": kurulum programi (PTS-Kurulum.exe) cagirdi -- pencerede
rem beklemeden hata koduyla don, kurulum programi kullaniciya bildirir.
if /i not "%~1" == "otomatik" pause
endlocal
exit /b 1

:modelleri_kopyala
rem Plaka modelleri kutuphanelerin kullanici basina onbellek klasorunde
rem aranir (%%USERPROFILE%%\.cache). Kurulum paketindeki kopyalar oraya
rem tasinir ki ilk acilista internetten indirilmesi gerekmesin. /D: yalnizca
rem eksik/eski dosyalar kopyalanir.
if exist "modeller\open-image-models\" xcopy "modeller\open-image-models" "%USERPROFILE%\.cache\open-image-models\" /E /I /D /Y /Q >nul
if exist "modeller\fast-plate-ocr\" xcopy "modeller\fast-plate-ocr" "%USERPROFILE%\.cache\fast-plate-ocr\" /E /I /D /Y /Q >nul
exit /b 0
