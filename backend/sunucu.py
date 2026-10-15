"""PTS sunucusunu AYNI süreçte iki portta çalıştırır (2026-10-14).

Kullanıcı isteği: "172.17.1.254:8000 adresiyle Nizamiye giriş yapacak ...
172.17.1.254:8787 ile Lojman bağlanacak, kullanıcı ve şifre gerektirmeden".

  * Ana port (PTS_PORT, varsayılan 8000): normal, kullanıcı adı/parolalı giriş.
  * Otomatik giriş portu (PTS_OTOMATIK_GIRIS_PORTU, varsayılan 8787; "0" =
    kapalı): bu porttan açılan panel, tanımlı hesapla parolasız oturum açar
    (bkz. main.py::otomatik_giris).

İKİ AYRI PTS SÜRECİ DEĞİL, tek süreç: aynı `app`, aynı veritabanı, aynı
kamera hatları, aynı canlı bildirim (SSE) yayını. İki süreç çalıştırılsaydı
her kamera iki kez okunur, her geçiş iki kez kaydedilirdi. Uygulamanın
açılış/kapanış olayları (kamera hatlarının başlatılması vb.) yalnızca ana
port sunucusunda çalışır.

Çalıştırma (proje kökünden): python -m backend.sunucu
"""
import asyncio
import contextlib
import logging
import os
import secrets
import signal
import socket

import uvicorn

logger = logging.getLogger("pts.sunucu")


def _port_ayari(ad: str, varsayilan: int) -> int:
    try:
        return int((os.environ.get(ad) or str(varsayilan)).strip())
    except ValueError:
        logger.warning("%s geçersiz (%r), varsayılan %d kullanılıyor", ad, os.environ.get(ad), varsayilan)
        return varsayilan


def _port_bos_mu(host: str, port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


class _Sunucu(uvicorn.Server):
    """Sinyalleri kendisi yakalamayan uvicorn sunucusu: iki sunucu aynı
    süreçte çalışırken CTRL+C ikisini birden durdurmalı (uvicorn'un kendi
    sinyal yakalayıcısında son kurulan öncekini ezer)."""

    @contextlib.contextmanager
    def capture_signals(self):
        yield

    def install_signal_handlers(self) -> None:  # eski uvicorn sürümleri
        pass


def main() -> None:
    host = os.environ.get("PTS_HOST", "0.0.0.0").strip() or "0.0.0.0"
    ana_port = _port_ayari("PTS_PORT", 8000)
    otomatik_port = _port_ayari("PTS_OTOMATIK_GIRIS_PORTU", 8787)

    # GÜVENLİK (2026-10-15): PTS_KAMERA_ANAHTARI .env'de yoksa bu süreç için
    # rastgele bir anahtar üretilir. Kameralar (camera_reader.py) bu sürecin
    # İÇİNDEN 127.0.0.1'e gönderdiği ve anahtarı aynı ortam değişkeninden
    # okuduğu için hiçbir ayar gerekmez; ağdaki başka bir bilgisayar ise
    # /kayitlar/otomatik'e sahte plaka kaydı (ve bariyer açma) gönderemez.
    # .env'e değer yazılmışsa o kullanılır (dışarıdan gönderen bir sistem varsa).
    if not (os.environ.get("PTS_KAMERA_ANAHTARI") or "").strip():
        os.environ["PTS_KAMERA_ANAHTARI"] = secrets.token_urlsafe(32)
        print("Kamera kayit anahtari bu calisma icin otomatik uretildi "
              "(ag uzerinden sahte plaka kaydi engellendi).", flush=True)

    from backend.main import app

    sunucular = [_Sunucu(uvicorn.Config(app, host=host, port=ana_port, lifespan="on"))]
    if otomatik_port and otomatik_port != ana_port:
        # Otomatik giriş portu doluysa ana panel yine açılsın (uvicorn bağlanamazsa
        # tüm süreci kapatır).
        if _port_bos_mu(host, otomatik_port):
            sunucular.append(_Sunucu(uvicorn.Config(app, host=host, port=otomatik_port, lifespan="off")))
            print(f"Otomatik giris (parolasiz) paneli: http://<bu bilgisayar>:{otomatik_port}", flush=True)
        else:
            print(f"UYARI: {otomatik_port} portu dolu -- otomatik giris paneli ACILMADI, "
                  f"ana panel {ana_port} portunda calismaya devam ediyor.", flush=True)

    def durdur(*_):
        for s in sunucular:
            s.should_exit = True

    signal.signal(signal.SIGINT, durdur)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, durdur)
    if hasattr(signal, "SIGBREAK"):  # Windows: konsol penceresi kapatılırken
        signal.signal(signal.SIGBREAK, durdur)

    async def calistir():
        await asyncio.gather(*(s.serve() for s in sunucular))

    asyncio.run(calistir())
    # Ana sunucu açılamadıysa (port dolu vb.) betiğin yeniden deneme mantığı
    # çalışsın diye hata koduyla çık.
    if not sunucular[0].started:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
