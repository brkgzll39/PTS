#!/usr/bin/env bash
# PTS-Kurulum.exe (Windows, 64 bit) üretir -- Linux üzerinde, NSIS ile.
#
# 2026-10-14: Inno Setup (PTS.iss) yolu hedef bilgisayarda internet, uv ve
# Python bekliyordu. Bu betik HER ŞEYİ kurulum programının içine koyar:
#   python\    Windows için gömülü Python 3.12 (python-build-standalone,
#              SHA256 ile doğrulanır)
#   paket\     backend/requirements-windows.txt'nin Windows wheel dosyaları
#   modeller\  plaka dedektör + OCR modelleri (ilk açılışta indirilmesin)
# ve proje dosyalarını `git archive` ile alır: yalnızca depoda izlenen
# dosyalar girer -- yerel veritabanı, .env, lisans, kamera/LED ayarları,
# görüntüler ASLA pakete girmez.
#
# Gerekenler: git, makensis (apt install nsis), uv, curl, tar.
# Kullanım:   installer/setup_olustur.sh [çıktı.exe]
set -euo pipefail

KOK="$(cd "$(dirname "$0")/.." && pwd)"
CIKTI="${1:-$KOK/installer/output/PTS-Kurulum.exe}"
CALISMA="${PTS_SETUP_CALISMA:-$(mktemp -d)}"
KAYNAK="$CALISMA/kaynak"
ONBELLEK="$CALISMA/onbellek"

PY_SURUM="3.12.13"
PY_TARIH="20260718"
PY_DOSYA="cpython-${PY_SURUM}+${PY_TARIH}-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_TARIH}/${PY_DOSYA//+/%2B}"
PY_SHA256="0d422a1439ec308e03f47df551bc30f5994727c456e414b026d202bcda9b7c1c"

DEDEKTOR="yolo-v9-s-608-license-plate-end2end"   # anpr_engine.DEDEKTOR_MODELI_VARSAYILAN
OCR="cct-xs-v2-global-model"                       # anpr_engine.OCR_MODELI_VARSAYILAN

for arac in git makensis uv curl tar sha256sum; do
  command -v "$arac" >/dev/null || { echo "HATA: '$arac' bulunamadı" >&2; exit 1; }
done
mkdir -p "$KAYNAK" "$ONBELLEK"
echo "Çalışma klasörü: $CALISMA"

echo "1/5 Proje dosyaları (git archive HEAD)..."
git -C "$KOK" archive HEAD backend frontend calistir.bat kurulum.bat guvenlik_duvari.ps1 README.md .env.example \
  | tar -x -C "$KAYNAK"
# Toplu dosyalar Windows satır sonuyla (CRLF): LF'li .bat'larda cmd.exe'nin
# goto/call etiketlerini yanlış bulduğu bilinen bir hata var.
for f in "$KAYNAK"/*.bat; do sed -i 's/\r$//; s/$/\r/' "$f"; done
cat > "$KAYNAK/KURULUM-NOTLARI.txt" <<'NOT'
PTS - Plaka Tanima Sistemi
==========================

Baslatma : Masaustundeki "PTS Baslat" (ya da C:\PTS\calistir.bat)
Panel    : Masaustundeki "PTS Paneli" ya da http://localhost:8000
           Diger bilgisayarlardan: http://<bu bilgisayarin IP adresi>:8000

Ilk acilis:
 1. Panelde yonetici hesabini olusturun.
 2. Lisans sekmesinden lisans anahtarini girin.
 3. Kameralar sekmesinden kameralari, LED sekmesinden panelleri tanimlayin.

Kameralar plaka okumuyorsa: "Microsoft Visual C++ 2015-2022 Redistributable
(x64)" kurulu olmayabilir -- https://aka.ms/vs/17/release/vc_redist.x64.exe

Kaldirma veritabanini, goruntuleri ve ayarlari SILMEZ.
NOT
sed -i 's/$/\r/' "$KAYNAK/KURULUM-NOTLARI.txt"

echo "2/5 Gömülü Python $PY_SURUM (Windows)..."
if [ ! -f "$ONBELLEK/$PY_DOSYA" ]; then
  curl -sSfL "$PY_URL" -o "$ONBELLEK/$PY_DOSYA"
fi
echo "$PY_SHA256  $ONBELLEK/$PY_DOSYA" | sha256sum -c -
tar -xzf "$ONBELLEK/$PY_DOSYA" -C "$KAYNAK"   # -> python/

echo "3/5 Windows paketleri (backend/requirements-windows.txt)..."
mkdir -p "$KAYNAK/paket"
uv run --no-project --python 3.12 --with pip -- python -m pip download \
  -r "$KOK/backend/requirements-windows.txt" --no-deps -d "$KAYNAK/paket" \
  --platform win_amd64 --python-version 3.12 --implementation cp --only-binary=:all: -q

echo "4/5 Plaka modelleri..."
# Modeller kütüphanelerin kendi indiricisiyle, AYNI sürümlerle, geçici bir
# HOME altına indirilir; Windows'ta %USERPROFILE%\.cache altına kopyalanır.
SAHTE_HOME="$CALISMA/model_home"
mkdir -p "$SAHTE_HOME"
FAST_ALPR_SURUM=$(grep -E '^fast-alpr==' "$KOK/backend/requirements-windows.txt" | cut -d= -f3)
OCR_PAKET=$(grep -E '^fast-plate-ocr==' "$KOK/backend/requirements-windows.txt")
OIM_PAKET=$(grep -E '^open-image-models==' "$KOK/backend/requirements-windows.txt")
HOME="$SAHTE_HOME" uv run --no-project --python 3.12 \
  --with "fast-alpr[onnx]==${FAST_ALPR_SURUM}" --with "$OCR_PAKET" --with "$OIM_PAKET" -- python -c "
from fast_alpr import ALPR
ALPR(detector_model='$DEDEKTOR', ocr_model='$OCR')
print('modeller hazır')"
mkdir -p "$KAYNAK/modeller"
cp -r "$SAHTE_HOME/.cache/open-image-models" "$SAHTE_HOME/.cache/fast-plate-ocr" "$KAYNAK/modeller/"

echo "5/5 makensis..."
SURUM="$(date +%Y.%m.%d)"
mkdir -p "$(dirname "$CIKTI")"
makensis -V2 -DKAYNAK="$KAYNAK" -DSURUM="$SURUM" -DCIKTI="$CIKTI" "$KOK/installer/PTS.nsi"
ls -la "$CIKTI"
sha256sum "$CIKTI"
