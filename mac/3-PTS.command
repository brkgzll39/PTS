#!/bin/bash
# PTS'i gerçek kullanım için başlatır (veriler proje klasöründe: veritabani/, goruntuler/).
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then echo "Önce '1-Kurulum' dosyasını çalıştırın."; read -r _; exit 1; fi
if lsof -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "8000 portu dolu: PTS zaten açık olabilir. Tarayıcıda açılıyor."; open "http://127.0.0.1:8000"; read -r _; exit 0
fi
( for i in $(seq 1 90); do
    if curl -s -o /dev/null "http://127.0.0.1:8000/saglik"; then open "http://127.0.0.1:8000"; exit 0; fi
    sleep 1
  done ) &
echo "PTS başlatılıyor: http://127.0.0.1:8000  (ilk açılışta yönetici hesabını oluşturursunuz)"
echo "Kapatmak için bu pencerede Ctrl+C'ye basın."
PTS_OTOMATIK_GIRIS_PORTU=0 exec .venv/bin/python pts_baslat.py
