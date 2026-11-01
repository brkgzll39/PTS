#!/bin/bash
# PTS demo: örnek kurum ve örnek geçişlerle çalışır; gerçek veriye dokunmaz.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then echo "Önce '1-Kurulum' dosyasını çalıştırın."; read -r _; exit 1; fi
PORT=8100
( for i in $(seq 1 90); do
    if curl -s -o /dev/null "http://127.0.0.1:$PORT/saglik"; then open "http://127.0.0.1:$PORT"; exit 0; fi
    sleep 1
  done ) &
echo "Demo açılıyor; tarayıcı kendiliğinden açılacak."
echo "Giriş:  demo / Demo12345 (yönetici)    kapi / Kapi12345 (Kapı Modu)"
echo "Kapatmak için bu pencerede Ctrl+C'ye basın."
PTS_OTOMATIK_GIRIS_PORTU=0 exec .venv/bin/python araclar/demo.py --port $PORT --klasor "$HOME/PTS-Demo" "$@"
