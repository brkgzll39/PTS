# PTS - kutuphane (Python paketi) guvenlik guncellemesi (2026-11-06)
#
# Yonetim Paneli > Yazilim Guncellemeleri > "Guncellemeleri uygula" / "Geri al"
# dugmeleri bu betigi Windows zamanlanmis gorevi olarak (SYSTEM hesabiyla) baslatir;
# PTS servisinin DISINDA calisir, servis yeniden baslarken yarida kesilmez.
# Elle de calistirilabilir (proje klasorunde, YONETICI PowerShell):
#   powershell -ExecutionPolicy Bypass -File .\kutuphane_guncelle.ps1 -Islem uygula
#   powershell -ExecutionPolicy Bypass -File .\kutuphane_guncelle.ps1 -Islem geri-al
#
# Adimlar (ayrintilar backend\yazilim_guncelleme.py):
#   1) kurulu surumleri yedekler, plandaki paketleri kurar, ekran karti motorunu
#      (DirectML) dogrular/onarir, uygulamanin acilabildigini dener; sorun olursa
#      kendisi eski surumlere doner ve servise DOKUNMAZ
#   2) PTS servisini yeniden baslatir, /saglik ile acildigini dogrular
#   3) 3 dakika boyunca /saglik yanit suresini izler (2026-11-06'daki gibi
#      sayfalarin acilmamasi durumunu yakalar); sorun olursa eski surumlere
#      doner ve servisi yeniden baslatir
# Her calismanin kaydi: veritabani\yazilim_guncelleme\son_islem.log
param(
    [ValidateSet("uygula", "geri-al")][string]$Islem = "uygula",
    [string]$ServisAdi = "PTS",
    [int]$SaglikSuresiSn = 120,
    [int]$IzlemeSn = 180
)
$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
$env:PYTHONIOENCODING = "utf-8"
$klasor = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $klasor
$kayitKlasoru = Join-Path $klasor "veritabani\yazilim_guncelleme"
New-Item -ItemType Directory -Force -Path $kayitKlasoru | Out-Null
try { Start-Transcript -Path (Join-Path $kayitKlasoru "son_islem.log") -Force | Out-Null } catch { }

$curl = if (Get-Command curl.exe -ErrorAction SilentlyContinue) { "curl.exe" } else { "curl" }
$python = Join-Path $klasor ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

function Adim([string]$m) { Write-Host ""; Write-Host "== $m" }

function SaglikAdresi {
    $ayar = @{}
    $envDosyasi = Join-Path $klasor ".env"
    if (Test-Path $envDosyasi) {
        foreach ($satir in Get-Content $envDosyasi -Encoding UTF8) {
            $s = $satir.Trim()
            if ($s -eq "" -or $s.StartsWith("#") -or -not $s.Contains("=")) { continue }
            $i = $s.IndexOf("=")
            $ayar[$s.Substring(0, $i).Trim()] = $s.Substring($i + 1).Trim().Trim('"').Trim("'")
        }
    }
    $port = if ($ayar["PTS_PORT"]) { $ayar["PTS_PORT"] } else { "8000" }
    $sema = if (@("1", "true", "evet", "on") -contains "$($ayar['PTS_HTTPS'])".ToLower()) { "https" } else { "http" }
    return "${sema}://127.0.0.1:$port/saglik"
}

function SaglikliMi([int]$sureSn) {
    $adres = SaglikAdresi
    for ($i = 0; $i -lt [Math]::Ceiling($sureSn / 2); $i++) {
        $cevap = & $curl -sk --max-time 5 $adres 2>$null
        if ("$cevap" -match '"durum"\s*:\s*"calisiyor"') { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

# Yeniden baslatmadan sonra: paneller yeniden baglanirken /saglik her 10 sn'de
# 10 sn icinde yanit vermeli (veritabani baglantisi tukenirse /saglik da bekler).
function IzlemeBasarili([int]$sureSn) {
    $adres = SaglikAdresi
    $bitis = (Get-Date).AddSeconds($sureSn)
    $hata = 0
    while ((Get-Date) -lt $bitis) {
        $cevap = & $curl -sk --max-time 10 $adres 2>$null
        if ("$cevap" -match '"durum"\s*:\s*"calisiyor"') { $hata = 0 } else { $hata++ }
        if ($hata -ge 2) { return $false }
        Start-Sleep -Seconds 10
    }
    return $true
}

function ServisiYenidenBaslat {
    if (-not (Get-Service -Name $ServisAdi -ErrorAction SilentlyContinue)) {
        Write-Host "UYARI: '$ServisAdi' servisi bulunamadi; PTS'i elle yeniden baslatin."
        return $false
    }
    Stop-Service -Name $ServisAdi -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    # pip'in kullanimdaki dosyalari tasidigi gecici klasorler (~il, ~ryptography ...)
    Get-ChildItem (Join-Path $klasor ".venv\Lib\site-packages") -Filter "~*" -Directory -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Start-Service -Name $ServisAdi -ErrorAction SilentlyContinue
    return $?
}

# Sonuc kodu backend\yazilim_guncelleme.py'de Turkce metne cevrilir (bu dosya ASCII kalsin).
function IzlemeSonucu([string]$kod) {
    & $python -m backend.yazilim_guncelleme izleme-sonucu $kod "$IzlemeSn" | Out-Null
}

Adim "Islem: $Islem"
& $python -m backend.yazilim_guncelleme $Islem
if ($LASTEXITCODE -ne 0) {
    Write-Host "Kutuphaneler degistirilemedi ya da dogrulama basarisiz; eski surumler yerinde. Servise dokunulmadi."
    if ($Islem -eq "uygula") { IzlemeSonucu "kurulum" } else { IzlemeSonucu "geri_al_basarisiz" }
    try { Stop-Transcript | Out-Null } catch { }
    exit 1
}

Adim "PTS yeniden baslatiliyor"
$yenidenBasladi = ServisiYenidenBaslat
if (-not $yenidenBasladi -and -not (Get-Service -Name $ServisAdi -ErrorAction SilentlyContinue)) {
    IzlemeSonucu "servis_yok"
    try { Stop-Transcript | Out-Null } catch { }
    exit 1
}
$saglikli = $yenidenBasladi -and (SaglikliMi $SaglikSuresiSn)
if ($saglikli) {
    Adim "$IzlemeSn sn izleniyor (paneller yeniden baglaniyor)"
    $saglikli = IzlemeBasarili $IzlemeSn
}

if ($saglikli) {
    IzlemeSonucu "ok"
    Adim "Tamamlandi"
    try { Stop-Transcript | Out-Null } catch { }
    exit 0
}

if ($Islem -eq "uygula") {
    Adim "Sorun goruldu; eski surumlere donuluyor"
    & $python -m backend.yazilim_guncelleme geri-al
    ServisiYenidenBaslat | Out-Null
    $eskiSaglikli = SaglikliMi $SaglikSuresiSn
    if ($eskiSaglikli) { IzlemeSonucu "geri_donuldu" } else { IzlemeSonucu "eski_de_yanit_yok" }
} else {
    IzlemeSonucu "geri_al_yanit_yok"
}
try { Stop-Transcript | Out-Null } catch { }
exit 1
