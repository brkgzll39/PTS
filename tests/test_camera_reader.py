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
        # Gerçek ANPREngine'deki detektor_esigi_etkin/detektor_esigi_kaynagi ve
        # dedektor_modeli_etkin/dedektor_modeli_kaynagi alanlarını taklit eder
        # (bkz. anpr_engine.py) — dedektor_esigi_bilgisi() ve /sistem/saglik'in
        # bunları okuyabildiğini test edebilmek için.
        self.detektor_esigi_etkin = 0.4
        self.detektor_esigi_kaynagi = "kütüphane varsayılanı (ortam değişkeni ayarlanmamış)"
        self.dedektor_modeli_etkin = "yolo-v9-t-384-license-plate-end2end"
        self.dedektor_modeli_kaynagi = "yapıcı/kütüphane varsayılanı"

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
    # farkli_okuma_sayisi (metin VARYANT sayısı) 1 olsa bile, bu okuma
    # aslında 3 AYRI karede tekrarlanıp doğrulandı -- bunu panelde ayırt
    # edebilmek için toplam_kare_sayisi AYRICA tutulur (bkz. 2026-09-17 notu).
    assert bitmis[0]["toplam_kare_sayisi"] == 3


def test_tek_karede_gorulen_okuma_toplam_kare_sayisi_bir_olur():
    """KÖK NEDEN: panelde kafa karıştıran vakanın regresyon testi -- bir araç
    sadece TEK bir karede (örn. "39 SU 877" yerine yanlışlıkla "04 SD 377"
    olarak) okunup başka hiçbir karede doğrulanmadan oturum kapanırsa,
    toplam_kare_sayisi 1 olmalı ki panel bunu diğer (birden çok karede
    doğrulanmış) kayıtlardan ayırt edip işaretleyebilsin."""
    t = camera_reader.PlakaOturumTakipcisi(oturum_kapanma_sn=1.0)
    t.guncelle("04 SD 377", 0.86, simdi=0.0)
    bitmis = t.bitmis_oturumlari_al(simdi=2.0)
    assert len(bitmis) == 1
    assert bitmis[0]["toplam_kare_sayisi"] == 1


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
    # 3 okuma yapıldı (2 farklı metin varyantına dağılsa da) -- toplam_kare_sayisi
    # bunu doğru yansıtmalı, farkli_okuma_sayisi (2) ile karıştırılmamalı.
    assert kazanan["toplam_kare_sayisi"] == 3


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


# ------------------------------------------------------------------
# "Sondan karakter eksik" düzeltmesi + kazanan-varyanta-özel güven (2026-09-18)
# ------------------------------------------------------------------
# Kullanıcı bildirimi: kamerada net görünen "02 AFP 552" plakası, TÜM
# karelerin (6/6) "oydaşmasıyla" %100 güvenle "02 AFP 55" (son rakam eksik)
# olarak kaydedildi. Araştırma: fast_alpr, dedektör kutusunu HİÇ kenar
# boşluğu eklemeden tam sınırlarından kırpıyor -- kutunun sağ kenarı son
# karaktere yakınsa o karakter OCR'a hiç ulaşmadan kırpılabiliyor. Bu
# testler hem bu düzeltmenin (yakın çağrılarda uzun varyantı tercih etme)
# hem de "guven" alanının artık KAZANAN metnin kendi güvenine ait olduğunu
# (önceden oturumdaki TÜM varyantlar arasındaki -- kazananla ilgisiz
# olabilecek -- global en yükseği raporluyordu) doğrular.

def test_sondan_karakter_eksik_yakin_cagrida_uzun_varyant_tercih_edilir():
    """KÖK NEDEN regresyonu: kullanıcının bildirdiği tam senaryo -- kısa
    (kırpılmış) varyant ÇOĞUNLUKTA ama EZİCİ değil; uzun (doğru) varyant da
    ciddi bir azınlıkla var. Uzun varyant kazanmalı."""
    t = camera_reader.PlakaOturumTakipcisi(oturum_kapanma_sn=1.0, benzerlik_esigi=2)
    t.guncelle("02 AFP 55", 1.0, simdi=0.0)
    t.guncelle("02 AFP 55", 1.0, simdi=0.1)
    t.guncelle("02 AFP 552", 0.97, simdi=0.2)
    t.guncelle("02 AFP 55", 1.0, simdi=0.3)
    t.guncelle("02 AFP 552", 0.95, simdi=0.4)

    bitmis = t.bitmis_oturumlari_al(simdi=2.0)
    assert len(bitmis) == 1
    kazanan = bitmis[0]
    assert kazanan["plaka"] == "02 AFP 552", "Sonu eksik ama çoğunlukta olan varyant yanlışlıkla kazandı"
    assert kazanan["uzun_varyant_tercih_edildi"] is True
    # guven artık KAZANAN ("02 AFP 552") varyantının kendi en yüksek güveni
    # olmalı (0.97), oturumdaki global en yüksek güven (1.0, "02 AFP 55"ye ait) DEĞİL.
    assert kazanan["guven"] == 0.97


def test_sondan_karakter_eksik_ezici_cogunlukta_gecersiz_kilinmaz():
    """Uzun varyant sadece TEK bir kare/tesadüfi bir yanlış okumaysa (ezici
    bir çoğunluk kısa varyantı destekliyorsa), düzeltme YİNE DE devreye
    girmemeli -- gerçekten daha kısa bir plaka olma ihtimaline karşı çoğunluk
    oyu korunmalı."""
    t = camera_reader.PlakaOturumTakipcisi(oturum_kapanma_sn=1.0, benzerlik_esigi=2)
    for i in range(9):
        t.guncelle("34 AB 12", 0.98, simdi=i * 0.1)
    t.guncelle("34 AB 123", 0.90, simdi=1.0)  # 10 karede yalnızca 1 kez uzun varyant

    bitmis = t.bitmis_oturumlari_al(simdi=3.0)
    assert len(bitmis) == 1
    kazanan = bitmis[0]
    assert kazanan["plaka"] == "34 AB 12", "Ezici çoğunluktaki kısa varyant yanlışlıkla geçersiz kılındı"
    assert kazanan["uzun_varyant_tercih_edildi"] is False


def test_ortadan_karakter_farkli_varyantlarda_uzunluk_tercihi_uygulanmaz():
    """Fark SONDA değil ORTADA ise (örn. harf grubuna bir harf eklenmiş/
    çıkmışsa), bu farklı bir hata sınıfıdır -- 'sondan karakter eksik'
    düzeltmesi burada uygulanmamalı (yanlış pozitif riski)."""
    t = camera_reader.PlakaOturumTakipcisi(oturum_kapanma_sn=1.0, benzerlik_esigi=2)
    t.guncelle("34 A 1234", 0.90, simdi=0.0)
    t.guncelle("34 AB 1234", 0.85, simdi=0.1)  # ortaya bir harf eklenmiş, SONA değil

    bitmis = t.bitmis_oturumlari_al(simdi=2.0)
    assert len(bitmis) == 1
    assert bitmis[0]["uzun_varyant_tercih_edildi"] is False
    assert bitmis[0]["plaka"] == "34 A 1234"  # doğal (en çok oylu) kazanan değişmedi


def test_kazanan_guveni_azinlikta_kalan_farkli_bir_varyantin_guveninden_etkilenmez():
    """KÖK NEDEN regresyonu: azınlıkta kalan (oylamayı kaybeden) bir okumanın
    rastgele yüksek güvenli olması, panelde KAZANAN okumanın güvenmiş gibi
    GÖSTERİLMESİNE yol açmamalı -- 'guven' her zaman gerçekten kaydedilen
    metne (kazanana) ait olmalı, oturumdaki global en yükseğe değil."""
    t = camera_reader.PlakaOturumTakipcisi(oturum_kapanma_sn=1.0, benzerlik_esigi=2)
    t.guncelle("34 XYZ 111", 0.70, simdi=0.0)
    t.guncelle("34 XYZ 111", 0.75, simdi=0.1)
    t.guncelle("34 XYZ 119", 1.0, simdi=0.2)  # tek kare, çok yüksek güvenli ama AZINLIKTA (aynı uzunlukta, tek karakter farklı)

    bitmis = t.bitmis_oturumlari_al(simdi=2.0)
    assert len(bitmis) == 1
    kazanan = bitmis[0]
    assert kazanan["plaka"] == "34 XYZ 111"
    assert kazanan["guven"] == 0.75, "guven, kazanmayan '34 XYZ 119' okumasının güveninden (1.0) sızıntı yapmamalı"


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


def test_kayit_api_istegine_dogrulama_kare_sayisi_eklenir(monkeypatch, sahte_engine):
    """KÖK NEDEN regresyonu: panelin 'tek karede görülüp başka hiçbir karede
    doğrulanmadı' okumalarını (bkz. README.md'deki 2026-09-17 notu ve
    "39 SU 877"nin tek bir karede "04 SD 377" olarak yanlış okunup öylece
    kaydolduğu vaka) ayırt edebilmesi için, API'ye gönderilen istekte bu
    okumanın kaç farklı karede oy aldığı da (dogrulama_kare_sayisi) yer
    almalı -- önceden bu bilgi hiç gönderilmiyordu."""
    import numpy as np

    yakalanan = {}

    def sahte_post(url, data=None, files=None, headers=None, timeout=None):
        yakalanan["data"] = data

        class _Yanit:
            status_code = 200

        return _Yanit()

    monkeypatch.setattr(camera_reader.requests, "post", sahte_post)

    pipeline = camera_reader.KameraPipeline(
        video_kaynagi="kullanilmiyor.mp4", kamera_id="TEST-DOGRULAMA",
    )
    kare = np.full((100, 100, 3), 128, dtype=np.uint8)
    gonderilenler = pipeline._kareyi_isle(kare, oturumu_hemen_kapat=True)

    assert gonderilenler == ["34 ABC 123"]
    assert yakalanan["data"]["dogrulama_kare_sayisi"] == 1


def test_kamera_anahtari_basligindaki_satir_sonu_gonderilmeden_once_temizlenir(monkeypatch, sahte_engine):
    """GERÇEK ÜRETİMDE BULUNAN HATA (2026-09-21, bkz. main.py::
    _kamera_anahtari_degeri'nin kök neden notu): PTS_KAMERA_ANAHTARI ortam
    değişkenine Windows'ta ayarlanırken sona görünmez bir satır sonu (\n)
    karışmıştı. `requests` kütüphanesi böyle bir karakter içeren bir başlık
    değerini KABUL ETMEYİP isteği hiç göndermeden reddediyordu -- yani
    dedektörün gerçekten doğruladığı HER plaka, panelde hiçbir iz
    bırakmadan sessizce kayboluyordu. Bu test, düzeltmenin başlığa GERÇEKTEN
    temiz bir değer koyduğunu (requests'e ulaşmadan önce) doğrudan
    doğrular."""
    import numpy as np

    monkeypatch.setenv("PTS_KAMERA_ANAHTARI", "gizli-anahtar\n")
    yakalanan = {}

    def sahte_post(url, data=None, files=None, headers=None, timeout=None):
        yakalanan["headers"] = headers

        class _Yanit:
            status_code = 200

        return _Yanit()

    monkeypatch.setattr(camera_reader.requests, "post", sahte_post)

    pipeline = camera_reader.KameraPipeline(
        video_kaynagi="kullanilmiyor.mp4", kamera_id="TEST-ANAHTAR-NEWLINE",
    )
    kare = np.full((100, 100, 3), 128, dtype=np.uint8)
    pipeline._kareyi_isle(kare, oturumu_hemen_kapat=True)

    assert yakalanan["headers"]["X-PTS-Kamera-Anahtari"] == "gizli-anahtar", (
        "Başlık değeri sonundaki \\n temizlenmemiş -- requests kütüphanesi "
        "bu değeri reddedip isteği hiç göndermeyebilirdi"
    )


class _CogulPlakaEngine:
    """Ardışık `tahmin_et()` çağrılarında FARKLI plaka varyantları döndüren
    sahte motor -- gerçek bir kameranın aynı aracı birkaç karede biraz farklı
    okumasını simüle eder. farkli_okuma_sayisi'nin API isteğine kadar uçtan
    uca doğru taşındığını test etmek için (bkz. 2026-09-18 notu)."""

    def __init__(self, *a, **kw):
        self._sonuclar = iter([
            _SahteSonuc("02 AFP 55", 1.0),
            _SahteSonuc("02 AFP 55", 1.0),
            _SahteSonuc("02 AFP 552", 0.97),
        ])
        self.detektor_esigi_etkin = 0.4
        self.detektor_esigi_kaynagi = "test"
        self.dedektor_modeli_etkin = "test-model"
        self.dedektor_modeli_kaynagi = "test"

    def tahmin_et(self, frame):
        try:
            return [next(self._sonuclar)]
        except StopIteration:
            return []


def test_kayit_api_istegine_farkli_okuma_sayisi_eklenir(monkeypatch):
    """KÖK NEDEN regresyonu: kullanıcının bildirdiği "02 AFP 552" plakasının
    "02 AFP 55" olarak %100 güvenle, 6/6 karenin 'oydaşmasıyla' kaydedilmesi
    vakası -- panel önceden bu oturumda birden fazla FARKLI okuma olduğunu
    (yani kazananın azınlıkta kalan bir okumaya rağmen seçildiğini) hiçbir
    şekilde göremiyordu, bu bilgi API isteğine hiç eklenmiyordu. Artık
    farkli_okuma_sayisi de dogrulama_kare_sayisi gibi istekle birlikte
    gönderiliyor."""
    import numpy as np

    monkeypatch.setattr(camera_reader, "ANPREngine", _CogulPlakaEngine)
    monkeypatch.setattr(camera_reader, "_paylasilan_motor", None)

    yakalanan = {}

    def sahte_post(url, data=None, files=None, headers=None, timeout=None):
        yakalanan["data"] = data

        class _Yanit:
            status_code = 200

        return _Yanit()

    monkeypatch.setattr(camera_reader.requests, "post", sahte_post)

    pipeline = camera_reader.KameraPipeline(
        video_kaynagi="kullanilmiyor.mp4", kamera_id="TEST-FARKLI-OKUMA",
    )
    kare = np.full((100, 100, 3), 128, dtype=np.uint8)
    pipeline._kareyi_isle(kare)
    pipeline._kareyi_isle(kare)
    gonderilenler = pipeline._kareyi_isle(kare, oturumu_hemen_kapat=True)

    # Sonda karakter eksik düzeltmesi burada da devreye girer (2 kare "02 AFP
    # 55" oyu=2.0, 1 kare "02 AFP 552" oyu=0.97 -- oran ~0.49 >= 0.34 eşiğini
    # geçiyor), bu yüzden doğru/uzun varyant kazanır.
    assert gonderilenler == ["02 AFP 552"]
    assert yakalanan["data"]["farkli_okuma_sayisi"] == 2
    assert yakalanan["data"]["dogrulama_kare_sayisi"] == 3


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


# ================================================================
# KlasorIzleyici — "bir fotoğrafı klasöre bırakınca gerçek bir kamera
# geçişiymiş gibi kaydedilsin" özelliği
# ================================================================

def _ornek_gorsel_yaz(yol) -> None:
    """Gerçek, cv2.imread ile okunabilir küçük bir JPEG dosyası yazar."""
    kare = np.full((80, 120, 3), (40, 40, 40), dtype=np.uint8)
    cv2.imwrite(str(yol), kare)


def test_klasor_izleyici_alt_klasorleri_otomatik_olusturur(tmp_path, sahte_engine):
    kok = tmp_path / "izleme"
    izleyici = camera_reader.KlasorIzleyici(str(kok))
    assert kok.is_dir()
    assert (kok / "cikis").is_dir()
    assert (kok / "islenenler").is_dir()


def test_klasor_izleyici_kopyalanmakta_olan_dosyayi_islemez(tmp_path, sahte_engine):
    """Boyutu taramalar arasında DEĞİŞEN (hâlâ kopyalanıyor olabilecek) bir
    dosya, boyutu sabitlenene kadar asla işlenmemeli."""
    kok = tmp_path / "izleme"
    izleyici = camera_reader.KlasorIzleyici(str(kok))
    dosya = kok / "arac.jpg"

    dosya.write_bytes(b"x" * 100)
    izleyici._tek_tur()
    assert dosya.exists(), "ilk görüldüğü turda hiç işlenmemeli (kararlılık kontrolü)"

    dosya.write_bytes(b"x" * 250)  # hâlâ büyüyor -- kopyalama devam ediyormuş gibi
    izleyici._tek_tur()
    assert dosya.exists(), "boyutu hâlâ değişen bir dosya işlenmemeli"
    assert list((kok / "islenenler").iterdir()) == []


def test_klasor_izleyici_iki_ardisik_ayni_boyutta_basarili_tespit_on_eksiz_tasinir(tmp_path, sahte_engine, sahte_api):
    kok = tmp_path / "izleme"
    izleyici = camera_reader.KlasorIzleyici(str(kok), api_url=sahte_api.url)
    dosya = kok / "arac.jpg"
    _ornek_gorsel_yaz(dosya)

    izleyici._tek_tur()  # 1. tur: yeni görüldü, henüz işlenmedi
    assert dosya.exists()
    izleyici._tek_tur()  # 2. tur: boyut aynı -> kararlı sayılıp işlenir

    assert not dosya.exists(), "işlendikten sonra kök klasörde kalmamalı"
    islenenler = list((kok / "islenenler").glob("*.jpg"))
    assert len(islenenler) == 1
    assert "TESPIT_EDILEMEDI_" not in islenenler[0].name, "başarılı tespit yanlışlıkla başarısız olarak işaretlendi"


def test_klasor_izleyici_tespit_basarisizsa_on_ekle_isaretlenir(tmp_path, sahte_engine, sahte_api):
    kok = tmp_path / "izleme"
    izleyici = camera_reader.KlasorIzleyici(str(kok), api_url=sahte_api.url)
    # Dedektörün hiçbir aday bulamadığı gerçek sahne durumunu simüle et.
    izleyici._pipeline_al("giris").motor = _BosSonucDondurenEngine()

    dosya = kok / "arac.jpg"
    _ornek_gorsel_yaz(dosya)

    izleyici._tek_tur()
    izleyici._tek_tur()

    assert not dosya.exists()
    islenenler = list((kok / "islenenler").glob("TESPIT_EDILEMEDI_*.jpg"))
    assert len(islenenler) == 1


def test_klasor_izleyici_cikis_alt_klasorune_birakilan_dosya_cikis_yonuyle_islenir(tmp_path, sahte_engine, sahte_api):
    kok = tmp_path / "izleme"
    izleyici = camera_reader.KlasorIzleyici(str(kok), api_url=sahte_api.url)
    dosya = kok / "cikis" / "arac.jpg"
    _ornek_gorsel_yaz(dosya)

    izleyici._tek_tur()
    izleyici._tek_tur()

    assert not dosya.exists()
    assert list((kok / "islenenler").glob("*.jpg")), "cikis/ alt klasöründeki dosya da işlenmeli"
    assert izleyici._pipelinelar["cikis"].yon == "cikis"


def test_klasor_izleyici_bozuk_gorsel_dosyasi_tespit_edilemedi_olarak_isaretlenir(tmp_path, sahte_engine, sahte_api):
    """Görsel formatı olarak okunamayan (cv2.imread None dönen) bir dosya da
    -- tıpkı tespit başarısızlığı gibi -- 'islenenler/'e taşınmalı, sonsuza
    kadar tekrar tekrar denenmemeli."""
    kok = tmp_path / "izleme"
    izleyici = camera_reader.KlasorIzleyici(str(kok), api_url=sahte_api.url)
    dosya = kok / "bozuk.jpg"
    dosya.write_bytes(b"bu gecerli bir JPEG degil")

    izleyici._tek_tur()
    izleyici._tek_tur()

    assert not dosya.exists()
    assert list((kok / "islenenler").glob("TESPIT_EDILEMEDI_*.jpg"))


def test_dedektor_esigi_bilgisi_motor_olusturulmadan_once_none_doner(monkeypatch):
    """Uygulama yeni açılmış, henüz hiçbir kamera pipeline'ı ya da klasör
    izleyici başlamamışsa (paylaşılan motor tembel/lazy oluşturulduğu için
    henüz yok) dedektor_esigi_bilgisi() motoru TETİKLEMEDEN None dönmeli."""
    monkeypatch.setattr(camera_reader, "_paylasilan_motor", None)
    assert camera_reader.dedektor_esigi_bilgisi() is None


def test_dedektor_esigi_bilgisi_motor_olusturulunca_etkin_degeri_raporlar(tmp_path, sahte_engine, sahte_api):
    """Bir KlasorIzleyici (veya kamera pipeline'ı) paylaşılan motoru bir kez
    oluşturduktan sonra, dedektor_esigi_bilgisi() bu motorun fiilen hangi
    eşikle çalıştığını ve kaynağını (ortam değişkeni mi, kütüphane varsayılanı
    mı) doğru raporlamalı -- panelin 'Dedektör Eşiği' satırının ve
    /sistem/saglik'in dayandığı bilgi budur."""
    kok = tmp_path / "izleme"
    izleyici = camera_reader.KlasorIzleyici(str(kok), api_url=sahte_api.url)
    izleyici._pipeline_al("giris")  # paylaşılan motoru oluşturmaya zorlar

    bilgi = camera_reader.dedektor_esigi_bilgisi()
    assert bilgi is not None
    assert bilgi["esik"] == 0.4
    assert "varsayılan" in bilgi["kaynak"]
    assert bilgi["model"] == "yolo-v9-t-384-license-plate-end2end"
    assert "varsayılan" in bilgi["model_kaynagi"]


# ------------------------------------------------------------------
# toplu_dogruluk_testi() — canlı sisteme dokunmadan, etiketli bir fotoğraf
# klasörü üzerinde ANPR doğruluğunu ölçen araç (bkz. camera_reader.py'deki
# fonksiyonun docstring'i; Dahua NVR'ın ANPR dışa aktarım adlandırmasıyla
# ("ONEK_PLAKA.jpg" / "ONEK_PLAKA_plate.jpg") uyumlu).
# ------------------------------------------------------------------

class _SahteSiraliMotor:
    """Her tahmin_et() çağrısında, önceden verilen sırayla bir sonraki canned
    yanıtı döndürür. toplu_dogruluk_testi() dosyaları sorted(os.listdir(...))
    sırasıyla işlediği için, test dosyalarını bu sıraya göre adlandırıp hangi
    çağrının hangi dosyaya karşılık geldiğini önceden biliriz."""

    def __init__(self, sirali_sonuclar):
        self._sirali_sonuclar = list(sirali_sonuclar)
        self._cagri_sayisi = 0

    def tahmin_et(self, frame):
        sonuc = self._sirali_sonuclar[self._cagri_sayisi]
        self._cagri_sayisi += 1
        if isinstance(sonuc, Exception):
            raise sonuc
        return sonuc


@pytest.fixture
def sahte_sirali_motor(monkeypatch):
    """sahte_engine'in aksine, motoru burada BİZ oluşturup doğrudan paylaşılan
    singleton'a yerleştiriyoruz -- her dosya için FARKLI bir canned yanıt
    vermemiz gerektiği için (gerçek/sahte ANPREngine hep AYNI yanıtı verir)."""
    def _kur(sirali_sonuclar):
        motor = _SahteSiraliMotor(sirali_sonuclar)
        monkeypatch.setattr(camera_reader, "_paylasilan_motor", motor)
        return motor
    return _kur


def test_toplu_dogruluk_testi_tum_sonuc_kategorilerini_dogru_sayar(tmp_path, sahte_sirali_motor):
    kok = tmp_path / "etiketli_fotograflar"
    kok.mkdir()
    # Sıralama önemli: sorted(os.listdir(...)) ile eşleşsin diye 01.. öneki kullanıldı.
    _ornek_gorsel_yaz(kok / "01_34ABC123.jpg")   # doğru okunacak
    _ornek_gorsel_yaz(kok / "02_06AA22.jpg")     # yanlış okunacak (06AA23 dönecek)
    _ornek_gorsel_yaz(kok / "03_35BC456.jpg")    # eşik altında kalacak
    _ornek_gorsel_yaz(kok / "04_41CD789.jpg")    # dedektör hiç aday bulamayacak
    _ornek_gorsel_yaz(kok / "05_Unlicensed.jpg")  # dosya adından geçerli plaka çıkarılamaz
    _ornek_gorsel_yaz(kok / "06_34ABC123_plate.jpg")  # kırpılmış plaka görseli -- ATLANMALI

    sahte_sirali_motor([
        [_SahteSonuc("34ABC123", 0.90)],
        [_SahteSonuc("06AA23", 0.90)],
        [_SahteSonuc("35BC456", 0.20)],
        [],
    ])

    sonuc = camera_reader.toplu_dogruluk_testi(str(kok))

    assert sonuc["toplam"] == 5  # "_plate.jpg" dosyası toplama hiç katılmadı
    assert sonuc["dogru"] == 1
    assert sonuc["yanlis"] == 1
    assert sonuc["esik_altinda"] == 1
    assert sonuc["tespit_edilemedi"] == 1
    assert sonuc["etiketlenemedi"] == 1
    assert sonuc["dogruluk_orani"] == pytest.approx(1 / 4)  # 5 - 1 etiketlenemedi = 4 etiketli dosya

    detay_sozlugu = {d["dosya"]: d for d in sonuc["detaylar"]}
    assert detay_sozlugu["01_34ABC123.jpg"]["sonuc"] == "dogru"
    assert detay_sozlugu["02_06AA22.jpg"]["sonuc"] == "yanlis"
    assert detay_sozlugu["02_06AA22.jpg"]["okunan_plaka"] == "06 AA 23"
    assert detay_sozlugu["03_35BC456.jpg"]["sonuc"] == "esik_altinda"
    assert detay_sozlugu["04_41CD789.jpg"]["sonuc"] == "tespit_edilemedi"
    assert detay_sozlugu["05_Unlicensed.jpg"]["sonuc"] == "etiketlenemedi"
    assert "06_34ABC123_plate.jpg" not in detay_sozlugu


def test_toplu_dogruluk_testi_min_guven_skoru_parametresi_esigi_degistirir(tmp_path, sahte_sirali_motor):
    """Aynı okuma (güven=0.20), varsayılan eşikte (0.4) 'esik_altinda' sayılırken,
    daha düşük bir min_guven_skoru ile çağrıldığında 'dogru' sayılmalı -- bu,
    kullanıcının farklı eşik değerlerini canlı sisteme dokunmadan karşılaştırmasını
    sağlayan tam olarak bu parametredir."""
    kok = tmp_path / "etiketli_fotograflar"
    kok.mkdir()
    _ornek_gorsel_yaz(kok / "01_34ABC123.jpg")

    sahte_sirali_motor([[_SahteSonuc("34ABC123", 0.20)]])
    varsayilan_sonuc = camera_reader.toplu_dogruluk_testi(str(kok))
    assert varsayilan_sonuc["esik_altinda"] == 1
    assert varsayilan_sonuc["dogru"] == 0

    sahte_sirali_motor([[_SahteSonuc("34ABC123", 0.20)]])
    dusuk_esikli_sonuc = camera_reader.toplu_dogruluk_testi(str(kok), min_guven_skoru=0.1)
    assert dusuk_esikli_sonuc["dogru"] == 1
    assert dusuk_esikli_sonuc["esik_altinda"] == 0


def test_toplu_dogruluk_testi_kontrast_iyilestir_parametresi_hatasiz_calisir(tmp_path, sahte_sirali_motor):
    """kontrast_iyilestir=True verildiğinde dedektöre CLAHE uygulanmış kare
    gitmeli ve akış hatasız tamamlanmalı (motor sahte olduğu için gerçek
    piksel farkı doğrulanmaz, yalnızca uçtan uca çalıştığı doğrulanır)."""
    kok = tmp_path / "etiketli_fotograflar"
    kok.mkdir()
    _ornek_gorsel_yaz(kok / "01_34ABC123.jpg")

    sahte_sirali_motor([[_SahteSonuc("34ABC123", 0.90)]])
    sonuc = camera_reader.toplu_dogruluk_testi(str(kok), kontrast_iyilestir=True)
    assert sonuc["dogru"] == 1


def test_toplu_dogruluk_testi_olmayan_klasor_hata_verir(sahte_engine):
    with pytest.raises(ValueError):
        camera_reader.toplu_dogruluk_testi("/var/olmayan/bir/klasor/kesinlikle")


def test_toplu_dogruluk_testi_bozuk_gorsel_ayri_kategoride_sayilir(tmp_path, sahte_sirali_motor):
    """2026-09-17 sahada yaşanan karışıklık: 'tespit_edilemedi' (dedektör
    gerçekten hiçbir aday bulamadı) ile 'dosya hiç açılamadı' aynı kategoride
    toplanınca, farklı model/eşik denemelerinde HEP 0 sonuç almak 'dedektör
    kaçırıyor' ile 'dosyalar okunamıyor' arasında ayırt edilemiyordu. Bu test,
    cv2.imread'in None döndüğü bir dosyanın artık kendi ayrı kategorisinde
    ('gorsel_okunamadi') sayıldığını doğrular."""
    kok = tmp_path / "etiketli_fotograflar"
    kok.mkdir()
    (kok / "01_34ABC123.jpg").write_bytes(b"bu gecerli bir JPEG degil")

    sahte_sirali_motor([])  # motor hiç çağrılmamalı -- görsel okunamadan önce elenir
    sonuc = camera_reader.toplu_dogruluk_testi(str(kok))

    assert sonuc["gorsel_okunamadi"] == 1
    assert sonuc["tespit_edilemedi"] == 0
    assert sonuc["detaylar"][0]["sonuc"] == "gorsel_okunamadi"


def test_toplu_dogruluk_testi_motor_hata_firlatirsa_ayri_kategoride_sayilir_ve_devam_eder(tmp_path, sahte_sirali_motor):
    """Motor çağrısı sırasında beklenmeyen bir istisna fırlarsa (ör. ONNX
    çalışma zamanı hatası) tüm toplu test çökmemeli -- o dosya 'hata'
    kategorisinde işaretlenip bir sonraki dosyaya geçilmeli."""
    kok = tmp_path / "etiketli_fotograflar"
    kok.mkdir()
    _ornek_gorsel_yaz(kok / "01_34ABC123.jpg")
    _ornek_gorsel_yaz(kok / "02_06AA22.jpg")

    sahte_sirali_motor([
        RuntimeError("onnxruntime: beklenmeyen çıkarım hatası"),
        [_SahteSonuc("06AA22", 0.9)],
    ])
    sonuc = camera_reader.toplu_dogruluk_testi(str(kok))

    assert sonuc["hata"] == 1
    assert sonuc["dogru"] == 1  # ikinci dosya sorunsuz işlenmeye devam etti
    detay_sozlugu = {d["dosya"]: d for d in sonuc["detaylar"]}
    assert detay_sozlugu["01_34ABC123.jpg"]["sonuc"] == "hata"
    assert "onnxruntime" in detay_sozlugu["01_34ABC123.jpg"]["hata_mesaji"]
    assert detay_sozlugu["02_06AA22.jpg"]["sonuc"] == "dogru"


# ------------------------------------------------------------------
# TESPİT ALANI SINIRI (ROI) -- bkz. README.md'deki 2026-09-17 notu: giriş ve
# çıkış kameralarının açıları birbirinin şeridini de görebiliyor, bu yüzden
# aynı araç her iki kamerada da tespit edilip hem "giriş" hem "çıkış" olarak
# ayrı ayrı kaydedilebiliyor. ROI, her kameranın SADECE kendi şeridine denk
# gelen bölgeyi izlemesini sağlayarak bunu engeller.
# ------------------------------------------------------------------

def test_roi_pixel_sinirlari_yuzdeden_dogru_hesaplanir():
    roi = {"x1": 25, "y1": 10, "x2": 75, "y2": 90}
    x1, y1, x2, y2 = camera_reader._roi_pixel_sinirlarini_hesapla(roi, genislik=200, yukseklik=100)
    assert (x1, y1, x2, y2) == (50, 10, 150, 90)


@pytest.mark.parametrize("kutu, roi_piksel, beklenen", [
    ((10, 10, 100, 60), (0, 0, 50, 100), False),    # merkez (55,35) -- x sınırın dışında
    ((10, 10, 100, 60), (50, 0, 100, 100), True),   # merkez (55,35) -- x sınırın içinde
    (None, (0, 0, 50, 100), False),                 # kutu yoksa asla içeride sayılmaz
])
def test_kutu_roi_icinde_mi_merkez_noktasina_gore_karar_verir(kutu, roi_piksel, beklenen):
    assert camera_reader._kutu_roi_icinde_mi(kutu, roi_piksel) is beklenen


def test_roi_disindaki_tespit_oy_birikimine_hic_girmez_ve_api_ye_gonderilmez(sahte_engine):
    """KÖK NEDEN düzeltmesi: iki kamera aynı bariyeri farklı açılardan
    izlediğinde (veya açıları örtüştüğünde), bir kameranın ROI'si komşu
    şeridi dışarıda bırakacak şekilde daraltılırsa, o şeritteki bir araç
    (sahte motorun sabit kutusu (10,10,100,60), 100x100'lük karede merkezi
    (55,35)) artık bu kameranın kaydına hiç düşmemeli."""
    import numpy as np

    pipeline = camera_reader.KameraPipeline(
        video_kaynagi="kullanilmiyor.mp4", kamera_id="TEST-ROI-DISI",
        roi={"x1": 0, "y1": 0, "x2": 50, "y2": 100},  # yalnızca SOL yarı geçerli
    )
    kare = np.zeros((100, 100, 3), dtype=np.uint8)
    gonderilenler = pipeline._kareyi_isle(kare, oturumu_hemen_kapat=True)

    assert gonderilenler == [], "ROI dışındaki (sağ yarıdaki) bir tespit yine de gönderildi"
    assert pipeline._oturum_takipcisi.acik_oturum_sayisi() == 0


def test_roi_icindeki_tespit_normal_sekilde_islenir(monkeypatch, sahte_engine):
    """Aynı senaryo ama ROI bu sefer tespitin GERÇEKTEN olduğu tarafı
    kapsıyor -- normal şekilde oy birikimine girip API'ye gönderilmeli,
    ROI'nin varlığı meşru tespitleri de engellememeli.

    (requests.post gerçek ağa gitmesin diye sahte_post ile taklit
    ediliyor -- bkz. test_kayit_api_istegine_dogrulama_kare_sayisi_eklenir'deki
    aynı desen.)"""
    import numpy as np

    def sahte_post(url, data=None, files=None, headers=None, timeout=None):
        class _Yanit:
            status_code = 200

        return _Yanit()

    monkeypatch.setattr(camera_reader.requests, "post", sahte_post)

    pipeline = camera_reader.KameraPipeline(
        video_kaynagi="kullanilmiyor.mp4", kamera_id="TEST-ROI-ICI",
        roi={"x1": 50, "y1": 0, "x2": 100, "y2": 100},  # yalnızca SAĞ yarı geçerli
    )
    kare = np.zeros((100, 100, 3), dtype=np.uint8)
    gonderilenler = pipeline._kareyi_isle(kare, oturumu_hemen_kapat=True)

    assert gonderilenler == ["34 ABC 123"]


# ------------------------------------------------------------------
# TESPİT ALANI SINIRI -- SERBEST ÇİZİM (POLYGON) (2026-09-20)
#
# Kullanıcı geri bildirimi (birebir): "alan sınırına serbest çizim ekleme
# şansımız var mı kare seçimde bazen farklı yönden geçen araçları da tespit
# ediyor bunu istemiyorum". Bir şerit çapraz/eğik açıdan görüntülendiğinde,
# şeridin gerçek hattını bir DİKDÖRTGEN her zaman doğru takip edemez --
# dikdörtgen, şeklin bounding-box'ını (en geniş noktasını) kapsamak zorunda
# kaldığı için komşu şeridi de içine alabilir. Serbest çizim (polygon), şeridin
# gerçek köşe noktalarını takip ettiği için bu sızıntıyı engeller.
# ------------------------------------------------------------------

def test_roi_polygon_pixel_noktalari_yuzdeden_dogru_hesaplanir():
    roi = {"tip": "polygon", "noktalar": [{"x": 25, "y": 10}, {"x": 75, "y": 10}, {"x": 50, "y": 90}]}
    noktalar = camera_reader._roi_polygon_pixel_noktalarini_hesapla(roi, genislik=200, yukseklik=100)
    assert noktalar == [(50, 10), (150, 10), (100, 90)]


@pytest.mark.parametrize("kutu, poligon, beklenen", [
    # Basit bir kare (0,0)-(100,100) -- merkez içeride/dışarıda.
    ((10, 10, 30, 30), [(0, 0), (100, 0), (100, 100), (0, 100)], True),   # merkez (20,20) -- içeride
    ((110, 10, 130, 30), [(0, 0), (100, 0), (100, 100), (0, 100)], False),  # merkez (120,20) -- dışarıda
    (None, [(0, 0), (100, 0), (100, 100), (0, 100)], False),               # kutu yoksa asla içeride sayılmaz
    ((10, 10, 30, 30), [(0, 0), (100, 0)], False),                          # 2 noktayla geçerli bir çokgen olmaz
])
def test_kutu_polygon_icinde_mi_ray_casting_ile_dogru_karar_verir(kutu, poligon, beklenen):
    assert camera_reader._kutu_polygon_icinde_mi(kutu, poligon) is beklenen


def test_roi_ciz_bilgisi_hesapla_roi_yoksa_none_doner():
    assert camera_reader._roi_ciz_bilgisi_hesapla(None, 200, 100) is None


def test_roi_ciz_bilgisi_hesapla_tip_belirtilmemisse_dikdortgen_varsayilir():
    """Eski (2026-09-18 öncesi) kaydedilmiş ROI'lerde "tip" anahtarı hiç
    YOK -- geriye dönük uyumluluk için bu, dikdörtgen olarak ele alınmalı."""
    roi = {"x1": 0, "y1": 0, "x2": 50, "y2": 100}
    tip, sekil = camera_reader._roi_ciz_bilgisi_hesapla(roi, genislik=100, yukseklik=100)
    assert tip == "dikdortgen"
    assert sekil == (0, 0, 50, 100)


def test_roi_ciz_bilgisi_hesapla_polygon_tipini_dogru_hesaplar():
    roi = {"tip": "polygon", "noktalar": [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 50, "y": 100}]}
    tip, sekil = camera_reader._roi_ciz_bilgisi_hesapla(roi, genislik=100, yukseklik=100)
    assert tip == "polygon"
    assert sekil == [(0, 0), (50, 0), (50, 100)]


def test_kutu_roi_ciz_bilgisiyle_icinde_mi_iki_tipi_de_dogru_yonlendirir():
    dikdortgen_bilgisi = ("dikdortgen", (50, 0, 100, 100))
    polygon_bilgisi = ("polygon", [(0, 0), (50, 0), (50, 100), (0, 100)])
    # merkez (55,35) -- dikdörtgende (50-100) içeride, polygon'da (0-50) dışarıda.
    assert camera_reader._kutu_roi_ciz_bilgisiyle_icinde_mi((10, 10, 100, 60), dikdortgen_bilgisi) is True
    assert camera_reader._kutu_roi_ciz_bilgisiyle_icinde_mi((10, 10, 100, 60), polygon_bilgisi) is False
    assert camera_reader._kutu_roi_ciz_bilgisiyle_icinde_mi((10, 10, 100, 60), None) is False


def test_capraz_seritte_dikdortgen_kapsardi_ama_polygon_roi_dogru_disinda_birakir(sahte_engine):
    """TAM DA kullanıcının şikayet ettiği senaryo: kamera açısı şeridi çapraz
    gösteriyor. Aşağıdaki polygon, üstte dar (x: 0-30) altta geniş (x: 0-70)
    bir şerit tanımlıyor -- yani şeridin GERÇEK hattı sabit tespit kutusunun
    (10,10,100,60), merkezi (55,35)) BULUNDUĞU yeri kapsamıyor. Ama bu
    polygon'un bounding-box'ı (0,0)-(70,100) bir DİKDÖRTGEN ROI olarak
    kullanılsaydı x=55 bu aralığın İÇİNDE kalacağı için tespiti YANLIŞLIKLA
    kabul ederdi. Serbest çizim, şeridin gerçek (eğik) hattını takip ettiği
    için bu komşu şerit sızıntısını doğru şekilde engellemeli."""
    pipeline = camera_reader.KameraPipeline(
        video_kaynagi="kullanilmiyor.mp4", kamera_id="TEST-ROI-POLYGON-DISI",
        roi={"tip": "polygon", "noktalar": [
            {"x": 0, "y": 0}, {"x": 30, "y": 0}, {"x": 70, "y": 100}, {"x": 0, "y": 100},
        ]},
    )
    kare = np.zeros((100, 100, 3), dtype=np.uint8)
    gonderilenler = pipeline._kareyi_isle(kare, oturumu_hemen_kapat=True)

    assert gonderilenler == [], (
        "Çapraz şeridi doğru takip eden polygon ROI, komşu şeritteki tespiti yine de kabul etti"
    )
    assert pipeline._oturum_takipcisi.acik_oturum_sayisi() == 0


def test_polygon_roi_icindeki_tespit_normal_sekilde_islenir(monkeypatch, sahte_engine):
    """Aynı çapraz şerit senaryosu ama polygon bu sefer tespitin GERÇEKTEN
    olduğu tarafı (merkez (55,35)) kapsıyor -- serbest çizim ROI'nin varlığı
    meşru tespitleri de engellememeli."""
    def sahte_post(url, data=None, files=None, headers=None, timeout=None):
        class _Yanit:
            status_code = 200

        return _Yanit()

    monkeypatch.setattr(camera_reader.requests, "post", sahte_post)

    pipeline = camera_reader.KameraPipeline(
        video_kaynagi="kullanilmiyor.mp4", kamera_id="TEST-ROI-POLYGON-ICI",
        roi={"tip": "polygon", "noktalar": [
            {"x": 40, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}, {"x": 20, "y": 100},
        ]},
    )
    kare = np.zeros((100, 100, 3), dtype=np.uint8)
    gonderilenler = pipeline._kareyi_isle(kare, oturumu_hemen_kapat=True)

    assert gonderilenler == ["34 ABC 123"]
