# PTS - tek adimda guncelleme (2026-10-23)
#
# Gonderilen .patch dosyasini guvenle uygular:
#   1) yarim kalmis eski bir "git am" varsa temizler
#   2) bu bilgisayardaki yerel degisiklikleri kenara alir (git stash)
#   3) veritabaninin yedegini alir (backend\guncelleme_yedegi.py)
#   4) yamayi uygular, degisen Python dosyalarini derleyerek kontrol eder
#   5) PTS servisini yeniden baslatir ve /saglik ile calistigini dogrular
#   6) herhangi bir adim basarisizsa kodu ESKI haline dondurur ve servisi
#      yeniden baslatir; yerel degisiklikler her durumda geri getirilir
#
# Kullanim (proje klasorunde, YONETICI PowerShell):
#   powershell -ExecutionPolicy Bypass -File .\guncelle.ps1
#       (Indirilenler klasorundeki EN YENI .patch dosyasini kullanir, onay ister)
#   powershell -ExecutionPolicy Bypass -File .\guncelle.ps1 -Yama "C:\Users\ASUS\Downloads\x.patch"
#   -Evet        onay sormadan devam et
#   -YedekAlma   veritabani yedegi alma (onerilmez)
#
# Not: veritabani degisiklikleri yalnizca yeni sutun ekler; kod eski haline
# donse bile eski surum yeni sutunlarla sorunsuz calisir.
param(
    [string]$Yama = "",
    [string]$ServisAdi = "PTS",
    [switch]$Evet,
    [switch]$YedekAlma,
    [int]$SaglikSuresiSn = 120
)
# Windows PowerShell 5.1'de "Stop", git'in stderr'e yazdigi normal ilerleme
# mesajlarini bile hata sayar; hatalar asagida $LASTEXITCODE ile denetlenir.
$ErrorActionPreference = "Continue"
$klasor = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $klasor

function Adim([string]$m) { Write-Host ""; Write-Host "== $m" -ForegroundColor Cyan }
function Uyari([string]$m) { Write-Host "UYARI: $m" -ForegroundColor Yellow }
function Hata([string]$m) { Write-Host "HATA: $m" -ForegroundColor Red }
function GitCalistir { & git @args | Out-Host; return ($LASTEXITCODE -eq 0) }

# ---------------------------------------------------------------- hazirlik
if (-not (Test-Path (Join-Path $klasor ".git"))) {
    Hata "Bu klasor bir git deposu degil: $klasor"; exit 1
}
if ($env:OS -eq "Windows_NT" -and -not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Hata "PowerShell'i 'Yonetici olarak calistir' ile acin (servis yeniden baslatilacak)."; exit 1
}
# Windows PowerShell'de "curl" Invoke-WebRequest'in takma adidir; gercek curl.exe kullanilir.
$curl = if (Get-Command curl.exe -ErrorAction SilentlyContinue) { "curl.exe" } else { "curl" }
$python = Join-Path $klasor ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

if (-not $Yama) {
    $indirilenler = Join-Path $env:USERPROFILE "Downloads"
    $enYeni = Get-ChildItem -Path $indirilenler -Filter "*.patch" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $enYeni) { Hata "Indirilenler klasorunde .patch dosyasi yok; -Yama ile yolunu verin."; exit 1 }
    $Yama = $enYeni.FullName
}
if (-not (Test-Path $Yama)) { Hata "Yama dosyasi bulunamadi: $Yama"; exit 1 }
$yamaBilgi = Get-Item $Yama
$basliklar = @(Select-String -Path $Yama -Pattern "^Subject: " -Encoding UTF8 |
    ForEach-Object { $_.Line.Substring(9) -replace '^\[PATCH[^\]]*\]\s*', '' })

Adim "Uygulanacak guncelleme"
Write-Host ("Dosya : {0}  ({1:dd.MM.yyyy HH:mm})" -f $yamaBilgi.FullName, $yamaBilgi.LastWriteTime)
foreach ($b in $basliklar) { Write-Host "  - $b" }
if (-not $Evet) {
    $onay = Read-Host "Devam etmek icin E yazin"
    if ($onay -ne "E" -and $onay -ne "e") { Write-Host "Iptal edildi."; exit 1 }
}

# ---------------------------------------------------------------- yarim kalan am / yerel degisiklikler
if (Test-Path (Join-Path $klasor ".git\rebase-apply")) {
    Uyari "Yarim kalmis eski bir yama uygulamasi bulundu; geri aliniyor (git am --abort)."
    if (-not (GitCalistir am --abort)) { Hata "git am --abort basarisiz; elle kontrol edin."; exit 1 }
}
$eskiHead = (& git rev-parse HEAD).Trim()
$stashlandi = $false
$yerel = & git status --porcelain --untracked-files=no
if ($yerel) {
    Adim "Yerel degisiklikler kenara aliniyor (git stash)"
    if (-not (GitCalistir stash push -m "guncelle.ps1 $(Get-Date -Format 'yyyy-MM-dd HH:mm')")) {
        Hata "Yerel degisiklikler kenara alinamadi; hicbir sey degistirilmedi."; exit 1
    }
    $stashlandi = $true
}

function YerelDegisiklikleriGeriGetir {
    if (-not $script:stashlandi) { return }
    if (GitCalistir stash pop) { $script:stashlandi = $false; return }
    Uyari "Yerel degisiklikler otomatik geri getirilemedi; 'git stash list' ile duruyorlar. 'git stash pop' ile elle alin."
}

function SaglikliMi {
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
    $adres = "${sema}://127.0.0.1:$port/saglik"
    Write-Host "Saglik kontrolu: $adres (en fazla $SaglikSuresiSn sn)"
    for ($i = 0; $i -lt [Math]::Ceiling($SaglikSuresiSn / 2); $i++) {
        $cevap = & $curl -sk --max-time 5 $adres 2>$null
        if ("$cevap" -match '"durum"\s*:\s*"calisiyor"') {
            if ("$cevap" -match '"saglikli"\s*:\s*false') { Uyari "PTS calisiyor ama uyari var: $cevap" }
            return $true
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

function ServisiYenidenBaslat {
    if (-not $ServisAdi) { Uyari "Servis adi verilmedi; PTS'i elle yeniden baslatin."; return $true }
    if (-not (Get-Service -Name $ServisAdi -ErrorAction SilentlyContinue)) {
        Uyari "'$ServisAdi' servisi bulunamadi; PTS'i elle yeniden baslatin."; return $true
    }
    Restart-Service -Name $ServisAdi -ErrorAction SilentlyContinue
    return $?
}

function GeriAl([string]$neden) {
    Hata $neden
    Adim "Kod eski haline donduruluyor"
    if (Test-Path (Join-Path $klasor ".git\rebase-apply")) { GitCalistir am --abort | Out-Null }
    if (((& git rev-parse HEAD).Trim()) -ne $eskiHead) {
        # Yerel degisiklikler bu noktada geri getirilmis olabilir; reset --hard
        # onlari silmesin diye once tekrar kenara alinir.
        if (-not $script:stashlandi -and (& git status --porcelain --untracked-files=no)) {
            if (GitCalistir stash push -m "guncelle.ps1 geri alma") { $script:stashlandi = $true }
            else { Hata "Yerel degisiklikler korunamadi; geri alma durduruldu. 'git status' ile kontrol edin."; exit 1 }
        }
        GitCalistir reset --hard $eskiHead | Out-Null
    }
    YerelDegisiklikleriGeriGetir
    ServisiYenidenBaslat | Out-Null
    if (SaglikliMi) { Write-Host "Eski surum calisiyor. Guncelleme UYGULANMADI." -ForegroundColor Yellow }
    else { Hata "Eski surum de saglik kontrolunden gecmedi; loglar\pts.log dosyasini kontrol edin." }
    if ($script:yedekYolu) { Write-Host "Guncelleme oncesi veritabani yedegi: $script:yedekYolu" }
    exit 1
}

# ---------------------------------------------------------------- yedek
$yedekYolu = $null
if (-not $YedekAlma) {
    Adim "Veritabani yedegi aliniyor"
    $cikti = & $python -m backend.guncelleme_yedegi
    if ($LASTEXITCODE -ne 0) {
        YerelDegisiklikleriGeriGetir
        Hata "Yedek alinamadi; guncelleme yapilmadi. (Yedeksiz devam icin -YedekAlma)"; exit 1
    }
    $yedekYolu = "$($cikti | Where-Object { "$_".Trim() } | Select-Object -Last 1)".Trim()
    Write-Host "Yedek: $yedekYolu"
}

# ---------------------------------------------------------------- yama
Adim "Yama uygulaniyor"
if (-not (GitCalistir am --3way $Yama)) { GeriAl "Yama uygulanamadi (cakisma ya da zaten uygulanmis)." }
$yeniHead = (& git rev-parse HEAD).Trim()
if ($yeniHead -eq $eskiHead) { YerelDegisiklikleriGeriGetir; Write-Host "Degisiklik yok; zaten guncel."; exit 0 }

Adim "Degisen Python dosyalari kontrol ediliyor"
$pyDosyalari = @(& git diff --name-only --diff-filter=AM $eskiHead $yeniHead | Where-Object { $_ -like "*.py" })
if ($pyDosyalari.Count -gt 0) {
    & $python -m py_compile @pyDosyalari
    if ($LASTEXITCODE -ne 0) { GeriAl "Python dosyalarinda sozdizimi hatasi." }
}
Write-Host ("{0} Python dosyasi sorunsuz." -f $pyDosyalari.Count)

YerelDegisiklikleriGeriGetir

# ---------------------------------------------------------------- yeniden baslat + dogrula
Adim "PTS yeniden baslatiliyor"
if (-not (ServisiYenidenBaslat)) { GeriAl "Servis yeniden baslatilamadi." }
if (-not (SaglikliMi)) { GeriAl "Yeni surum saglik kontrolunden gecmedi." }

Adim "Guncelleme tamamlandi"
foreach ($b in $basliklar) { Write-Host "  + $b" -ForegroundColor Green }
if ($yedekYolu) { Write-Host "Guncelleme oncesi yedek: $yedekYolu" }
Write-Host "Tarayicilarda Ctrl+F5 yapin."
exit 0
