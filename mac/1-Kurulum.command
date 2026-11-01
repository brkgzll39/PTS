#!/bin/bash
# PTS — Mac kurulumu (bir kez çalıştırılır). Python 3.12'yi ve gerekli paketleri
# proje klasörünün içine kurar; Mac'teki başka hiçbir şeyi değiştirmez.
cd "$(dirname "$0")" || exit 1
xattr -dr com.apple.quarantine . 2>/dev/null   # internetten inen dosyaların engelini kaldır
set -e
echo "== PTS Mac kurulumu =="

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  echo "uv (Python kurulum aracı) indiriliyor..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

if [ ! -x .venv/bin/python ]; then
  echo "Python 3.12 hazırlanıyor..."
  uv venv .venv --python 3.12
fi

echo "Paketler kuruluyor (ilk seferde birkaç dakika sürebilir)..."
uv pip install --python .venv/bin/python -r backend/requirements-mac.txt

echo "Plaka okuma paketleri kuruluyor (canlı kamera için; demo için gerekmez)..."
if uv pip install --python .venv/bin/python -r backend/requirements-mac-anpr.txt; then
  echo "Plaka okuma paketleri kuruldu."
else
  echo "UYARI: Plaka okuma paketleri kurulamadı. Demo ve panel çalışır; canlı kamera okuması çalışmaz."
fi

if [ ! -f .env ]; then
  anahtar() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 40; }
  {
    echo "# PTS güvenlik anahtarları — kurulumda kendiliğinden üretildi. Kimseyle paylaşmayın."
    echo "PTS_LICENSE_SECRET=$(anahtar)"
    echo "PTS_KAMERA_ANAHTARI=$(anahtar)"
    echo "PTS_ARVENTO_ANAHTARI=$(anahtar)"
  } > .env
  chmod 600 .env
  echo ".env oluşturuldu (güvenlik anahtarları)."
fi

chmod +x ./*.command 2>/dev/null || true
.venv/bin/python -c "import backend.main" >/dev/null 2>&1 && echo "Kontrol: PTS açılabiliyor." || echo "UYARI: PTS içe aktarılamadı; bu pencerenin çıktısını gönderin."
echo ""
echo "Kurulum tamam. Şimdi '2-Demo' ya da '3-PTS' dosyasına çift tıklayın."
read -r -p "Kapatmak için Enter'a basın..." _
