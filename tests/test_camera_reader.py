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

    def __init__(self, *a, plaka="34ABC123", guven=0.95, **kw):
        self._plaka = plaka
        self._guven = guven

    def tahmin_et(self, frame):
        return [_SahteSonuc(self._plaka, self._guven)]


@pytest.fixture
def sahte_engine(monkeypatch):
    monkeypatch.setattr(camera_reader, "ANPREngine", _SahteEngine)
    # Tüm kameralar arasında paylaşılan motor artık modül seviyesinde tekil
    # (singleton) olarak önbelleğe alınıyor (bkz. camera_reader._paylasilan_motoru_al
    # — çoklu kamerada GPU sürücüsü çökmesini önlemek için eklendi). Bu önbellek
    # sıfırlanmazsa önceki bir testte oluşturulmuş motor kalıcı kalır ve bu testin
    # yukarıdaki monkeypatch'ini sessizce görmezden gelir; monkeypatch ile
    # sıfırlıyoruz ki test sonunda otomatik olarak eski haline dönsün.
    monkeypatch.setattr(camera_reader, "_paylasilan_motor", None)


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


# ------------------------------------------------------------------
# Çok kareli oy birleştirme (PlakaOturumTakipcisi) — doğruluğu artıran
# "frame consolidation" mantığının kendisi. Gerçek zamanlamaya bağlı olmasın
# diye burada sahte (elle verilen) zaman damgaları kullanılır.
# ------------------------------------------------------------------

def test_ayni_plakanin_tekrarlanan_okumalari_tek_oturumda_birlesir():
    t = camera_reader.PlakaOturumTakipcisi(oturum_kapanma_sn=1.0)
    t.guncelle("34 ABC 123", 0.80, simdi=0.0)
    t.guncelle("34 ABC 123", 0.90, simdi=0.2)
    t.guncelle("34 ABC 123", 0.60, simdi=0.4)
    assert t.acik_oturum_sayisi() == 1

    bitmis = t.bitmis_oturumlari_al(simdi=2.0)  # 1.0 sn'den fazla sessizlik → kapanır
    assert len(bitmis) == 1
    assert bitmis[0]["plaka"] == "34 ABC 123"
    assert bitmis[0]["farkli_okuma_sayisi"] == 1
    assert bitmis[0]["guven"] == 0.90  # görülen en yüksek güven


def test_farkli_okumalarin_oydasmasiyla_cogunluk_kazanir():
    """Aynı aracın karelerinde OCR 2 kere doğru, 1 kere hatalı okursa (tek
    karaktarlik fark), çoğunluk oyu doğru okumayı kazanmalı — bu, tek bir kötü
    karenin karar bozmasını engelleyen tam da bu özelliğin amacı."""
    t = camera_reader.PlakaOturumTakipcisi(oturum_kapanma_sn=1.0, benzerlik_esigi=2)
    t.guncelle("34 ABC 123", 0.85, simdi=0.0)
    t.guncelle("34 ABC 128", 0.55, simdi=0.2)   # hatalı tek karakter (OCR gürültüsü)
    t.guncelle("34 ABC 123", 0.88, simdi=0.4)
    assert t.acik_oturum_sayisi() == 1, "Benzer okumalar aynı oturumda birleşmeliydi"

    bitmis = t.bitmis_oturumlari_al(simdi=2.0)
    assert len(bitmis) == 1
    kazanan = bitmis[0]
    assert kazanan["plaka"] == "34 ABC 123", "Çoğunluk oyu (2/3) yerine azınlık kazandı"
    assert kazanan["farkli_okuma_sayisi"] == 2


def test_farkli_araclarin_oturumlari_karismaz():
    t = camera_reader.PlakaOturumTakipcisi(oturum_kapanma_sn=1.0, benzerlik_esigi=2)
    t.guncelle("34 ABC 123", 0.9, simdi=0.0)
    t.guncelle("06 ZZZ 999", 0.9, simdi=0.1)  # tamamen farklı bir plaka/araç
    assert t.acik_oturum_sayisi() == 2

    bitmis = {b["plaka"] for b in t.bitmis_oturumlari_al(simdi=2.0)}
    assert bitmis == {"34 ABC 123", "06 ZZZ 999"}


def test_eski_oturum_yeni_okumayla_sessizce_kaybolmaz():
    """Regresyon testi: Bir oturum sessizliğe düşüp YENİ bir okuma (aynı plaka,
    uzun bir aradan sonra) geldiğinde, eski oturumun oyları önce KAZANAN olarak
    alınmalı; yeni okumayla aynı anahtara sessizce üzerine yazılıp kaybolmamalı."""
    t = camera_reader.PlakaOturumTakipcisi(oturum_kapanma_sn=1.0)
    t.guncelle("34 ABC 123", 0.9, simdi=0.0)

    # Aynı plaka, oturum kapanma süresinden çok sonra tekrar görülüyor (ör. bir
    # sonraki araç ya da aynı aracın çok sonra tekrar geçmesi).
    onceki_bitmis = t.bitmis_oturumlari_al(simdi=5.0)
    assert len(onceki_bitmis) == 1, "Eski oturum, yeni okuma işlenmeden ÖNCE kazanan olarak alınabilmeli"
    assert onceki_bitmis[0]["plaka"] == "34 ABC 123"

    t.guncelle("34 ABC 123", 0.7, simdi=5.1)
    assert t.acik_oturum_sayisi() == 1  # bu artık YENİ bir oturum


def test_zorla_kapatma_bekelemeden_kazanani_dondurur():
    t = camera_reader.PlakaOturumTakipcisi(oturum_kapanma_sn=100.0)
    t.guncelle("34 ABC 123", 0.9, simdi=0.0)
    assert t.bitmis_oturumlari_al(simdi=0.01) == []  # henüz sessizliğe düşmedi
    bitmis = t.bitmis_oturumlari_al(simdi=0.01, zorla=True)
    assert len(bitmis) == 1 and bitmis[0]["plaka"] == "34 ABC 123"


def test_dusuk_guvenli_okuma_pipeline_isleyisinde_oya_hic_girmez(sahte_engine):
    """min_guven_skoru eşiğinin altındaki bir okuma oy birikimine hiç
    girmemeli — pipeline seviyesinde entegrasyon testi."""
    import numpy as np

    pipeline = camera_reader.KameraPipeline(
        video_kaynagi="kullanilmiyor.mp4", kamera_id="TEST-ESIK", min_guven_skoru=0.9,
    )
    pipeline.motor = _SahteEngine(guven=0.5)

    kare = np.zeros((100, 100, 3), dtype=np.uint8)
    gonderilenler = pipeline._kareyi_isle(kare, oturumu_hemen_kapat=True)
    assert gonderilenler == [], "0.5 güvenli okuma, 0.9 eşiğinin altında olmasına rağmen gönderildi"
    assert pipeline._oturum_takipcisi.acik_oturum_sayisi() == 0


class _BosSonucDondurenEngine:
    """Dedektörün HİÇBİR aday bulamadığı durumu simüle eder (boş liste)."""

    def __init__(self, *a, **kw):
        pass

    def tahmin_et(self, frame):
        return []


def test_bos_tespitte_ham_kare_teshis_dizinine_kaydedilir(monkeypatch, tmp_path, sahte_engine):
    """PTS_HAM_KARE_KAYIT_DIZINI ayarlıysa, dedektörün hiçbir aday bulamadığı
    (boş tespit) kareler bu dizine kaydedilmeli — sahadaki 'araç net görünüyor
    ama dedektör hiçbir şey bulamıyor' vakalarını gözle doğrulayabilmek için."""
    import numpy as np

    dizin = tmp_path / "ham_kareler"
    monkeypatch.setenv("PTS_HAM_KARE_KAYIT_DIZINI", str(dizin))

    pipeline = camera_reader.KameraPipeline(
        video_kaynagi="kullanilmiyor.mp4", kamera_id="TEST-HAM-KARE",
    )
    pipeline.motor = _BosSonucDondurenEngine()

    kare = np.full((100, 100, 3), 128, dtype=np.uint8)
    pipeline._kareyi_isle(kare, oturumu_hemen_kapat=True)

    kaydedilenler = list(dizin.glob("TEST-HAM-KARE_*.jpg"))
    assert len(kaydedilenler) == 1, "Boş tespitte tam olarak bir ham teşhis karesi kaydedilmeliydi"


def test_bos_tespit_disinda_ham_kare_kaydedilmez(monkeypatch, tmp_path, sahte_engine):
    """Dedektör bir şey BULDUĞUNDA (boş tespit değilken) ham kare kaydı
    tetiklenmemeli — bu özellik yalnızca 'sessiz kayıp' teşhisi içindir."""
    import numpy as np

    dizin = tmp_path / "ham_kareler"
    monkeypatch.setenv("PTS_HAM_KARE_KAYIT_DIZINI", str(dizin))

    pipeline = camera_reader.KameraPipeline(
        video_kaynagi="kullanilmiyor.mp4", kamera_id="TEST-HAM-KARE-2",
    )
    pipeline.motor = _SahteEngine(guven=0.95)

    kare = np.full((100, 100, 3), 128, dtype=np.uint8)
    pipeline._kareyi_isle(kare, oturumu_hemen_kapat=True)

    assert not dizin.exists() or list(dizin.glob("*.jpg")) == []
