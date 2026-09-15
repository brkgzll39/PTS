#!/bin/bash
cd "$(dirname "$0")/backend"
echo "Bağımlılıklar kuruluyor (ilk çalıştırmada biraz sürebilir)..."
pip install -r requirements.txt
echo ""
echo "Sunucu başlatılıyor... Tarayıcıdan http://localhost:8000 adresine gidin."
echo "Durdurmak için CTRL+C tuşlarına basın."
echo ""
uvicorn main:app --host 0.0.0.0 --port 8000
