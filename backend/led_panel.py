"""
LED Panel Entegrasyon Modülü
----------------------------
Desteklenen modlar:
  - simulate : Gerçek donanım yok, mesaj sadece konsola / veritabanına yazılır (varsayılan).
  - serial   : RS232/USB seri port üzerinden bağlı LED panel (pyserial gerektirir).
  - tcp      : Ağ (Ethernet/WiFi) üzerinden IP adresiyle konuşan LED panel.

Ayarlar backend/config.json dosyasında tutulur, panelden (LED Ayarları sekmesi) değiştirilebilir.

Not: Çoğu ticari LED panel kendi metin protokolüne sahiptir (örn. başına/sonuna özel
komut baytları eklemek gerekebilir). "serial" ve "tcp" modlarındaki gönderim fonksiyonlarını
kullandığınız panelin kullanım kılavuzuna göre uyarlamanız gerekebilir; iskelet burada hazır.
"""
import json
import os
import socket
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_YOLU = os.path.join(BACKEND_DIR, "config.json")

VARSAYILAN_AYARLAR = {
    "led_mod": "simulate",       # simulate | serial | tcp
    "serial_port": "COM3",
    "serial_baudrate": 9600,
    "tcp_host": "192.168.1.50",
    "tcp_port": 5000,
}


def ayarlari_oku() -> dict:
    if not os.path.exists(CONFIG_YOLU):
        ayarlari_kaydet(VARSAYILAN_AYARLAR)
        return dict(VARSAYILAN_AYARLAR)
    with open(CONFIG_YOLU, "r", encoding="utf-8") as f:
        ayarlar = json.load(f)
    # eksik anahtarları varsayılanla tamamla
    for k, v in VARSAYILAN_AYARLAR.items():
        ayarlar.setdefault(k, v)
    return ayarlar


def ayarlari_kaydet(ayarlar: dict) -> None:
    with open(CONFIG_YOLU, "w", encoding="utf-8") as f:
        json.dump(ayarlar, f, ensure_ascii=False, indent=2)


def led_mesaj_gonder(mesaj: str) -> bool:
    """Ayarlarda seçili moda göre LED panele mesaj gönderir. Başarılıysa True döner."""
    ayarlar = ayarlari_oku()
    mod = ayarlar.get("led_mod", "simulate")

    try:
        if mod == "simulate":
            print(f"[LED SİMÜLASYON] {datetime.now().strftime('%H:%M:%S')} -> {mesaj}")
            return True

        elif mod == "serial":
            try:
                import serial  # pyserial - opsiyonel bağımlılık
            except ImportError:
                print("pyserial kurulu değil. Kurulum: pip install pyserial")
                return False
            with serial.Serial(
                ayarlar["serial_port"], ayarlar["serial_baudrate"], timeout=2
            ) as ser:
                ser.write((mesaj + "\r\n").encode("utf-8"))
            return True

        elif mod == "tcp":
            with socket.create_connection(
                (ayarlar["tcp_host"], ayarlar["tcp_port"]), timeout=3
            ) as s:
                s.sendall((mesaj + "\r\n").encode("utf-8"))
            return True

        else:
            print(f"Bilinmeyen LED modu: {mod}")
            return False

    except Exception as e:
        print(f"LED mesajı gönderilemedi: {e}")
        return False
