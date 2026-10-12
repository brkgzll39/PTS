"""
LED Panel Entegrasyon Modülü
----------------------------
Desteklenen modlar:
  - simulate : Gerçek donanım yok, mesaj sadece konsola / veritabanına yazılır (varsayılan).
  - serial   : RS232/USB seri port üzerinden bağlı LED panel (pyserial gerektirir).
  - tcp      : Ağ (Ethernet/WiFi) üzerinden IP adresiyle konuşan LED panel.
  - huidu    : Huidu HD-E62 kontrol kartı (TCP 6101, metin bitmap olarak gönderilir;
               protokol ayrıntıları backend/huidu.py'de).

Ayarlar backend/config.json dosyasında tutulur, panelden (LED Ayarları sekmesi) değiştirilebilir.

Not: Çoğu ticari LED panel kendi metin protokolüne sahiptir (örn. başına/sonuna özel
komut baytları eklemek gerekebilir). "serial" ve "tcp" modlarındaki gönderim fonksiyonlarını
kullandığınız panelin kullanım kılavuzuna göre uyarlamanız gerekebilir; iskelet burada hazır.
"""
import json
import logging
import os
import socket
import threading
from datetime import datetime
from typing import Optional, Sequence

from backend import huidu

# DÜZELTME (2026-09-25, sistem taraması): bu modül önceden TÜM durum/hata
# mesajlarını `print()` ile yazıyordu -- bir servis/arka plan sürecinin
# stdout'u tipik olarak hiçbir yerde toplanmaz/görüntülenmez, oysa main.py ve
# camera_reader.py gibi kod tabanının geri kalanı bilinçli olarak `logging`
# modülüne geçmiş durumda (camera_reader.py'nin kendi modül docstring'i bunu
# özellikle "`print()` kullanılmaz -- her şey logging modülü üzerinden
# `/sistem/loglar` uç noktasında görülebilir olmalı" diye vurguluyor). LED
# panel, güvenlik görevlisine "KARA LİSTE / YETKİSİZ ARAÇ" gibi mesajları
# gösteren FİZİKSEL tabeladır -- panel kablosu çıkarsa/IP'ye ulaşılamazsa bu
# önceden HİÇBİR yerde görünmüyordu. "pts.led" alt logger'ı, main.py'de
# tanımlanan "pts" logger'ının (loglar/pts.log dosyasına yazan) handler'ını
# miras alır (bkz. camera_reader.py'nin aynı "pts.camera" deseni), yani bu
# modülün logları da artık /sistem/loglar üzerinden görülebilir.
logger = logging.getLogger("pts.led")

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
# PTS_LED_CONFIG_FILE: normalde ayarlamanıza gerek yok. Test paketi, canlı
# kurulumun LED ayarlarını ezmemek (ve testlerin gönderdiği mesajların gerçek
# panele gitmemesi) için bunu geçici bir dizine yönlendirir.
CONFIG_YOLU = os.getenv("PTS_LED_CONFIG_FILE") or os.path.join(BACKEND_DIR, "config.json")

VARSAYILAN_AYARLAR = {
    "led_mod": "simulate",       # simulate | serial | tcp | huidu
    "serial_port": "COM3",
    "serial_baudrate": 9600,
    "tcp_host": "192.168.1.50",
    "tcp_port": 5000,
    "huidu_host": "172.17.1.224",
    "huidu_port": huidu.VARSAYILAN_PORT,
    "huidu_iki_bolge": False,    # panel 32 px yüksekse (ör. 64x32) True: 1. satır üst, 2. satır alt bölgeye
    "huidu_genislik": huidu.VARSAYILAN_GORUNUR_GENISLIK,  # panelin gösterdiği sütun sayısı (NİZAMİYE: 64)
    # Panelin boştaki yazısı (eski Pts.exe gibi). Araç mesajı `huidu_mesaj_suresi`
    # saniye görünür, sonra bu yazıya dönülür. Boş yazı ya da 0 sn: dönülmez.
    "huidu_bekleme_yazisi": "T.P.A.O.",
    "huidu_mesaj_suresi": 10,
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


def led_mesaj_gonder(mesaj: str, satirlar: Optional[Sequence[str]] = None) -> bool:
    """Ayarlarda seçili moda göre LED panele mesaj gönderir. Başarılıysa True döner.

    `satirlar` verilirse (ör. ("HOŞ GELDİNİZ", "34ABC123")) satır tabanlı
    paneller (huidu) metni bu şekilde böler; diğer modlar yalnızca `mesaj`ı kullanır.
    """
    global _huidu_nesil
    ayarlar = ayarlari_oku()
    mod = ayarlar.get("led_mod", "simulate")

    try:
        if mod == "simulate":
            logger.info("[LED SİMÜLASYON] %s -> %s", datetime.now().strftime("%H:%M:%S"), mesaj)
            return True

        elif mod == "serial":
            try:
                import serial  # pyserial - opsiyonel bağımlılık
            except ImportError:
                logger.error("LED mesajı gönderilemedi: pyserial kurulu değil (kurulum: pip install pyserial)")
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

        elif mod == "huidu":
            with _huidu_kilidi:
                _huidu_nesil += 1
                _huidu_gonder(ayarlar, satirlar or [mesaj], bool(ayarlar["huidu_iki_bolge"]))
                _bekleme_yazisini_zamanla(ayarlar, _huidu_nesil)
            return True

        else:
            logger.error("LED mesajı gönderilemedi: bilinmeyen LED modu '%s'", mod)
            return False

    except Exception as e:
        logger.error("LED mesajı gönderilemedi (mod=%s): %s", mod, e)
        return False


# ------------------------------------------------------------------
# Huidu: boştaki yazı (T.P.A.O.)
# ------------------------------------------------------------------
# Her araç mesajı "nesil"i artırır; zamanlayıcı tetiklendiğinde bu arada yeni bir
# mesaj geldiyse (nesil değiştiyse) bekleme yazısını GÖNDERMEZ. Kilit, "kontrol et
# + gönder"in yeni bir mesajla iç içe geçip onu ezmesini önler.
_huidu_kilidi = threading.Lock()
_huidu_nesil = 0
_huidu_zamanlayici: Optional[threading.Timer] = None


def _huidu_gonder(ayarlar: dict, satirlar: Sequence[str], iki_bolge: bool) -> None:
    huidu.gonder(
        ayarlar["huidu_host"],
        int(ayarlar["huidu_port"]),
        satirlar=satirlar,
        iki_bolge=iki_bolge,
        genislik=int(ayarlar["huidu_genislik"]),
    )


def _bekleme_yazisini_zamanla(ayarlar: dict, nesil: int) -> None:
    global _huidu_zamanlayici
    if _huidu_zamanlayici is not None:
        _huidu_zamanlayici.cancel()
        _huidu_zamanlayici = None
    sure = float(ayarlar.get("huidu_mesaj_suresi") or 0)
    if sure <= 0 or not str(ayarlar.get("huidu_bekleme_yazisi") or "").strip():
        return
    _huidu_zamanlayici = threading.Timer(sure, _bekleme_yazisina_don, args=(nesil,))
    _huidu_zamanlayici.daemon = True
    _huidu_zamanlayici.start()


def _bekleme_yazisina_don(nesil: Optional[int] = None) -> bool:
    """Bekleme yazısını panele yazar. `nesil` verilmişse yalnızca o mesajdan sonra
    yeni mesaj gelmediyse yazar. Huidu modunda değilse ya da yazı boşsa hiçbir şey yapmaz."""
    with _huidu_kilidi:
        if nesil is not None and nesil != _huidu_nesil:
            return False
        ayarlar = ayarlari_oku()
        yazi = str(ayarlar.get("huidu_bekleme_yazisi") or "").strip()
        if ayarlar.get("led_mod") != "huidu" or not yazi:
            return False
        try:
            # Pts.exe gibi: yazı üst bölgede, alt bölge boş.
            _huidu_gonder(ayarlar, [yazi], iki_bolge=False)
            return True
        except Exception as e:
            logger.error("LED bekleme yazısı gönderilemedi (mod=huidu): %s", e)
            return False


def bekleme_yazisini_goster_arka_planda() -> None:
    """PTS açılışında / LED ayarları kaydedilince bekleme yazısını panele yazar.
    Panel ulaşılamazsa isteği/açılışı bekletmemek için ayrı iş parçacığında çalışır."""
    threading.Thread(target=_bekleme_yazisina_don, name="led-bekleme-yazisi", daemon=True).start()
