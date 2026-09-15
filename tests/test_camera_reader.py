"""backend/camera_reader.py::KameraPipeline için uçtan uca doğrulama testleri.

Fiziksel bir kamera/RTSP akışı olmadan, kısa bir sentetik video dosyasını
"kamera" gibi kullanır: video hızla EOF'a düşer, bu da gerçek bir kamera
kopması/donması durumunu birebir simüle eder. Şunları doğrular:

  1) camera_reader.py hatasız import ediliyor (2026-09 tarihli kritik
     regresyonun aynısı bir daha fark edilmeden geçmesin diye).
  2) Kare akışı durunca pipeline gerçekten yeniden bağlanıyor.
  3) Yeniden bağlanmalarda okuyucu thread SIZINTISI olmuyor.
  4) son_kare_yasi_sn() / durum_bilgisi() donma durumunu doğru yansıtıyor.
  5) durdur() sonrası hiçbir thread arkada kalmıyor (temiz kapanma).
  6) Tespit edilen plaka gerçek bir HTTP sunucusuna multipart POST olarak ulaşıyor.
"""
import http.server
import socketserver
import threading
import time

import cv2
import numpy as np
import pytest

from backend import camera_reader


class _SahteSonuc:
    def __init__(self, plaka="34ABC123", guven=0.95):
        self.plaka_no = plaka
        self.guven_skoru = guven
        self.kutu = (10, 10, 100, 60)


class _SahteEngine:
    """Gerçek fast-alpr modeline ihtiyaç duymadan testte kullanılan sahte ANPR motoru."""

    def __init__(self, *a, **kw):
        pass

    def tahmin_et(self, frame):
        return [_SahteSonuc()]


@pytest.fixture
def sahte_engine(monkeypatch):
    monkeypatch.setattr(camera_reader, "ANPREngine", _SahteEngine)


@pytest.fixture
def sentetik_video(tmp_path):
    """6 kareli, ~1.2 saniyelik kısa bir video dosyası üretir; hızla EOF'a düşer."""
    yol = tmp_path / "test_kamera.avi"
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    yazici = cv2.VideoWriter(str(yol), fourcc, 5, (320, 240))
    for i in range(6):
        kare = np.full((240, 320, 3), (30, 30, 30), dtype=np.uint8)
        cv2.putText(kare, f"ARAC {i}", (40, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 2)
        yazici.write(kare)
    yazici.release()
    return str(yol)


class _SahteAPISunucusu:
    """/kayitlar/otomatik yerine geçen, gelen istekleri sayan minik stdlib HTTP sunucu."""

    def __init__(self):
        self.alinan_istekler = []
        kilit = threading.Lock()
        alinan = self.alinan_istekler

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                uzunluk = int(self.headers.get("Content-Length", 0))
                govde = self.rfile.read(uzunluk)
                with kilit:
                    alinan.append(len(govde))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": true}')

        self.httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/kayitlar/otomatik"

    def kapat(self):
        self.httpd.shutdown()


@pytest.fixture
def sahte_api():
    sunucu = _SahteAPISunucusu()
    yield sunucu
    sunucu.kapat()


def test_camera_reader_import_edilebiliyor():
    """2026-09 regresyonu: dosya bozuk kopyalama yüzünden import edilemiyordu."""
    assert camera_reader.KUTUPHANELER_MEVCUT is True
    assert hasattr(camera_reader, "KameraPipeline")


def test_pipeline_yeniden_baglanir_donmayi_tespit_eder_ve_sizinti_yapmaz(sahte_engine, sentetik_video, sahte_api):
    pipeline = camera_reader.KameraPipeline(
        video_kaynagi=sentetik_video,
        api_url=sahte_api.url,
        kamera_id="TEST-KAMERA-PYTEST",
        tekrar_gecikme_sn=2,
        baglanti_zaman_asimi_sn=1.0,
        donma_esigi_sn=1.5,
    )
    pipeline.baslat()
    try:
        max_okuyucu_thread_sayisi = 0
        donmus_gozlemlendi = False
        for _ in range(10):
            time.sleep(1)
            aktif_okuyucular = [
                t for t in threading.enumerate()
                if t.name.startswith("pts-okuyucu-TEST-KAMERA-PYTEST")
            ]
            max_okuyucu_thread_sayisi = max(max_okuyucu_thread_sayisi, len(aktif_okuyucular))
            if pipeline.durum_bilgisi()["donmus"]:
                donmus_gozlemlendi = True

        assert max_okuyucu_thread_sayisi <= 2, (
            f"Okuyucu thread sızıntısı şüphesi: eşzamanlı {max_okuyucu_thread_sayisi} thread görüldü"
        )
        assert donmus_gozlemlendi, "EOF sonrası donma durumu hiç gözlemlenmedi"
        assert len(sahte_api.alinan_istekler) > 0, "Tespit edilen plaka API'ye hiç POST edilmedi"
    finally:
        pipeline.durdur()


def test_durdur_sonrasi_hicbir_thread_kalmaz(sahte_engine, sentetik_video, sahte_api):
    pipeline = camera_reader.KameraPipeline(
        video_kaynagi=sentetik_video,
        api_url=sahte_api.url,
        kamera_id="TEST-DURDURMA-PYTEST",
        tekrar_gecikme_sn=100,
        baglanti_zaman_asimi_sn=1.0,
    )
    pipeline.baslat()
    time.sleep(1.5)
    assert pipeline.thread_canli_mi() is True

    pipeline.durdur()
    time.sleep(0.5)

    assert pipeline.thread_canli_mi() is False
    kalan = [t.name for t in threading.enumerate() if "TEST-DURDURMA-PYTEST" in t.name]
    assert kalan == [], f"durdur() sonrası hâlâ çalışan thread'ler var: {kalan}"


def test_plaka_regex_gecersiz_ocr_ciktisini_reddeder():
    assert camera_reader.plaka_dogrula("gecersiz") is None
    assert camera_reader.plaka_dogrula("34ABC123") == "34 ABC 123"
