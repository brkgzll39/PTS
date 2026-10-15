# PTS - Windows Guvenlik Duvari sikilastirma (2026-10-15)
#
# Panel portlarini (8000 ve 8787) YALNIZCA izinli bilgisayarlara acar; agdaki
# (ve internetteki) diger hicbir cihaz panele ulasamaz.
#
#   8000 (ana panel)      : PTS_ANA_PORT_OTOMATIK_GIRIS_IPLERI + -EkIpler
#   8787 (Lojman paneli)  : PTS_OTOMATIK_GIRIS_IPLERI          + -EkIpler
#   Bu bilgisayarin kendisi (localhost) her zaman erisebilir.
#
# IP'ler .env dosyasindan okunur. Yonetici olarak baska bilgisayarlardan da
# girilecekse onlari -EkIpler ile ekleyin (virgulle; 172.17.1.0/24 gibi bir
# alt ag da yazilabilir).
#
# Kullanim (proje klasorunde, YONETICI PowerShell):
#   powershell -ExecutionPolicy Bypass -File .\guvenlik_duvari.ps1
#   powershell -ExecutionPolicy Bypass -File .\guvenlik_duvari.ps1 -EkIpler "172.17.1.50,172.17.1.51"
#   powershell -ExecutionPolicy Bypass -File .\guvenlik_duvari.ps1 -Kontrol    (yalnizca durum raporu)
#
# Geri almak: wf.msc > Gelen Kurallar > "PTS ..." kurallarini silin, betigin
# devre disi biraktigi eski kurallari yeniden etkinlestirin.
param(
    [string]$EkIpler = "",
    [switch]$Kontrol
)
$ErrorActionPreference = "Stop"

$yonetici = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $yonetici) {
    Write-Host "HATA: PowerShell'i 'Yonetici olarak calistir' ile acin." -ForegroundColor Red
    exit 1
}

$klasor = Split-Path -Parent $MyInvocation.MyCommand.Path
$envDosyasi = Join-Path $klasor ".env"
$ayar = @{}
if (Test-Path $envDosyasi) {
    foreach ($satir in Get-Content $envDosyasi -Encoding UTF8) {
        $s = $satir.Trim()
        if ($s -eq "" -or $s.StartsWith("#") -or -not $s.Contains("=")) { continue }
        $i = $s.IndexOf("=")
        $ayar[$s.Substring(0, $i).Trim()] = $s.Substring($i + 1).Trim().Trim('"').Trim("'")
    }
}

function IpListesi([string]$deger) {
    if (-not $deger) { return @() }
    return @($deger.Split(",") | ForEach-Object { $_.Trim().Trim("<", ">") } | Where-Object { $_ -ne "" })
}
function Port([string]$ad, [int]$varsayilan) {
    $d = $ayar[$ad]
    if ($d -and ($d -as [int]) -ne $null) { return [int]$d }
    return $varsayilan
}

$anaPort = Port "PTS_PORT" 8000
$lojmanPort = Port "PTS_OTOMATIK_GIRIS_PORTU" 8787
$ek = IpListesi $EkIpler
$anaIpler = @(IpListesi $ayar["PTS_ANA_PORT_OTOMATIK_GIRIS_IPLERI"]) + $ek + @("127.0.0.1", "::1")
$lojmanIpler = @(IpListesi $ayar["PTS_OTOMATIK_GIRIS_IPLERI"]) + $ek + @("127.0.0.1", "::1")
$anaIpler = @($anaIpler | Select-Object -Unique)
$lojmanIpler = @($lojmanIpler | Select-Object -Unique)

Write-Host ""
Write-Host "=== Durum raporu ===" -ForegroundColor Cyan
Get-NetConnectionProfile | ForEach-Object {
    $renk = if ($_.NetworkCategory -eq "Public") { "Yellow" } else { "Gray" }
    Write-Host ("Ag: {0}  ({1}), profil: {2}" -f $_.Name, $_.InterfaceAlias, $_.NetworkCategory) -ForegroundColor $renk
}
$dinlenen = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in @($anaPort, $lojmanPort, 1433, 3389, 445) } |
    Sort-Object LocalPort -Unique
foreach ($d in $dinlenen) {
    $not = switch ($d.LocalPort) {
        1433 { "SQL Server -- disaridan erisim gerekmiyorsa kapali kalmali" }
        3389 { "Uzak Masaustu -- internete ACIK OLMAMALI" }
        445 { "Dosya paylasimi -- internete ACIK OLMAMALI" }
        default { "PTS paneli" }
    }
    Write-Host ("Dinlenen port {0} ({1}): {2}" -f $d.LocalPort, $d.LocalAddress, $not)
}

$eskiKurallar = @()
foreach ($port in @($anaPort, $lojmanPort)) {
    $eskiKurallar += Get-NetFirewallPortFilter -Protocol TCP -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -contains "$port" } |
        Get-NetFirewallRule -ErrorAction SilentlyContinue |
        Where-Object { $_.Direction -eq "Inbound" -and $_.Action -eq "Allow" -and $_.Enabled -eq "True" -and
                       $_.DisplayName -notlike "PTS * - izinli bilgisayarlar" }
}
# Windows, python.exe ilk kez port actiginda "Erisime izin ver" sorusuyla
# PROGRAM bazli (tum portlar) bir kural olusturur; o kural da portu herkese acar.
$eskiKurallar += Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue |
    Where-Object { $_.Program -like "*python*.exe" } |
    Get-NetFirewallRule -ErrorAction SilentlyContinue |
    Where-Object { $_.Direction -eq "Inbound" -and $_.Action -eq "Allow" -and $_.Enabled -eq "True" }
$eskiKurallar = @($eskiKurallar | Sort-Object Name -Unique)
Write-Host ""
if ($eskiKurallar.Count -gt 0) {
    Write-Host "Portu HERKESE (adres kisiti olmadan da olabilir) acan mevcut kurallar:" -ForegroundColor Yellow
    foreach ($k in $eskiKurallar) {
        $adres = ($k | Get-NetFirewallAddressFilter).RemoteAddress -join ","
        Write-Host ("  - {0}  (uzak adres: {1}, profil: {2})" -f $k.DisplayName, $adres, $k.Profile)
    }
} else {
    Write-Host "Portu acan baska kural yok."
}

if ($Kontrol) { exit 0 }

if ((IpListesi $ayar["PTS_ANA_PORT_OTOMATIK_GIRIS_IPLERI"]).Count -eq 0 -and $ek.Count -eq 0) {
    Write-Host ""
    Write-Host "HATA: .env'de PTS_ANA_PORT_OTOMATIK_GIRIS_IPLERI bos ve -EkIpler verilmedi;" -ForegroundColor Red
    Write-Host "      bu haliyle ana panele (port $anaPort) baska hicbir bilgisayar baglanamazdi. Islem yapilmadi." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== Uygulanacak ===" -ForegroundColor Cyan
Write-Host ("Port {0} (ana panel) yalnizca: {1}" -f $anaPort, ($anaIpler -join ", "))
Write-Host ("Port {0} (Lojman)    yalnizca: {1}" -f $lojmanPort, ($lojmanIpler -join ", "))
if ($eskiKurallar.Count -gt 0) { Write-Host "Yukaridaki eski kurallar DEVRE DISI birakilacak (silinmez)." }
Write-Host "UYARI: Listede olmayan bilgisayarlar (yonetici olarak girdiginiz baskasi varsa o da) panele ulasamaz." -ForegroundColor Yellow
$onay = Read-Host "Devam etmek icin E yazin"
if ($onay -ne "E" -and $onay -ne "e") { Write-Host "Iptal edildi."; exit 1 }

foreach ($k in $eskiKurallar) { Disable-NetFirewallRule -Name $k.Name }
foreach ($ad in @("PTS $anaPort - izinli bilgisayarlar", "PTS $lojmanPort - izinli bilgisayarlar")) {
    Get-NetFirewallRule -DisplayName $ad -ErrorAction SilentlyContinue | Remove-NetFirewallRule
}
New-NetFirewallRule -DisplayName "PTS $anaPort - izinli bilgisayarlar" -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort $anaPort -RemoteAddress $anaIpler -Profile Any | Out-Null
if ($lojmanPort -gt 0) {
    New-NetFirewallRule -DisplayName "PTS $lojmanPort - izinli bilgisayarlar" -Direction Inbound -Action Allow `
        -Protocol TCP -LocalPort $lojmanPort -RemoteAddress $lojmanIpler -Profile Any | Out-Null
}
Write-Host ""
Write-Host "Tamam. Kurallar uygulandi; PTS'i yeniden baslatmaya gerek yok." -ForegroundColor Green
