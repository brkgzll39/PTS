"""
OPSİYONEL MODÜL: Gerçek ANPR/RTSP kamera hattı (FastALPR motoru ile).

Bu dosya sistemin ZORUNLU bir parçası değildir; ana uygulama (main.py) bu modül
kurulu olmasa da tamamen çalışır (manuel kayıt / API üzerinden kayıt ekleme ile).

Gerçek kamera bağlamak isterseniz:
  1) pip install "fast-alpr[onnx]" opencv-python requests  (Windows GPU için: fast-alpr[onnx-directml])
  2) Aşağıdaki KameraPipeline sınıfını RTSP adresinizle başlatın:

       from camera_reader import KameraPipeline
       pipeline = KameraPipeline(
           video_kaynagi="rtsp://kullanici:sifre@kamera-ip:554/Streaming/Channels/101",
           kamera_id="GIRIS-KAMERA-1",
       )
       pipeline.baslat()

  Pipeline, tespit ettiği her plakayı otomatik olarak çalışan FastAPI sunucusundaki
  POST /kayitlar/otomatik uç noktasına (görselle birlikte) gönderir; sistem geri
  kalanını (yetki kontrolü, veritabanı, LED panel bildirimi) kendisi halleder.

  Kamera/video yokken pipeline'ı doğrulamak için `video_kaynagi` yerine tek bir
  görsel dosya yolu da verilebilir (bkz. `tek_gorsel_test`); bu, kamera bağlamadan
  tespit + doğrulama + API gönderimi zincirini uçtan uca test etmeyi sağlar.

  Alternatif: Eğer ANPR kameranız plaka okumayı kendi içinde (edge) yapıyorsa
  (çoğu Hikvision/Dahua ANPR modeli gibi), bu Python pipeline'ına hiç gerek
  kalmaz — kameranın "Event Notification / ANPR Result Push" özelliğini doğrudan
  POST /kayitlar/otomatik uç noktasına yönlendirmeniz yeterlidir.

Sağlamlık notları (üretim/7-24 çalışma için):
  - Kare-okuyucu thread her zaman en son kareyi tutar (RTSP tamponu birikmez,
    böylece görüntü zamanla "gecikmeye" düşmez).
  - Her yeniden bağlanmada eski okuyucu thread bir "nesil" (generation) sayacıyla
    kapatılır; eski thread sonsuza kadar dönmez (thread sızıntısı yok).
  - `son_kare_yasi_sn()` en son karenin üstünden geçen süreyi verir; bu sayede
    "bağlantı TCP olarak açık ama görüntü donmuş" durumu da tespit edilebilir
    (main.py bunu /kameralar/{id}/saglik uç noktasında kullanır).
  - Tüm çalışma zamanı olayları `logging` üzerinden `pts.camera` logger'ına yazılır
    (uygulamanın `loglar/pts.log` dosyasına düşer); `print()` kullanılmaz.
  - `son_plaka_zamani` sözlüğü periyodik olarak budanır (çok uzun süre çalışan
    sistemlerde sınırsız büyümesin diye).
"""
import os
import re
import tempfile
import time
import threading
import logging
from collections import Counter
from typing import Optional

try:
    from backend.anpr_engine import ANPREngine  # proje kökünden çalıştırılınca
except ImportError:
    from anpr_engine import ANPREngine  # backend/ içinden doğrudan çalıştırılınca

try:
    from backend.metin_araclari import levenshtein_mesafesi
except ImportError:
    from metin_araclari import levenshtein_mesafesi

try:
    import cv2
    import requests
    KUTUPHANELER_MEVCUT = True
except ImportError:
    KUTUPHANELER_MEVCUT = False


# ================================================================
# PAYLAŞILAN ANPR MOTORU
# ================================================================
# ÖNEMLİ: Her KameraPipeline eskiden KENDİ ANPREngine'ini (dolayısıyla kendi
# onnxruntime GPU oturumunu) oluşturuyordu. Tek kamerayla bu sorunsuz çalışıyordu;
# ikinci bir kamera eklenince iki BAĞIMSIZ onnxruntime/DirectML oturumu aynı anda
# GPU'ya iş göndermeye başladı — bu, sahada gözlemlenen "DXGI_ERROR_DEVICE_HUNG"
# (GPU sürücüsü komutlara zamanında yanıt veremeyip Windows tarafından sıfırlanıyor)
# ve ardından gelen bozuk-veri/istisna hatalarının en olası nedenidir; bazı
# donanım/sürücü kombinasyonlarında bu tür bir sürücü sıfırlanması tüm sistemin
# donup kendini yeniden başlatmasına kadar gidebiliyor.
#
# Çözüm: kamera sayısından bağımsız olarak TEK bir ANPREngine (tek GPU oturumu)
# paylaşılır ve her çıkarım çağrısı aşağıdaki kilitle serileştirilir — böylece
# GPU'ya HER ZAMAN aynı anda yalnızca tek bir istek gider (tek kameralı, sorunsuz
# çalışan önceki durumla birebir aynı GPU yükü). Ayrıca toplamda tek bir model
# seti belleğe yüklendiği için VRAM kullanımı da yarıya iner.
#
# Sürücü/donanım GPU'da hâlâ kararsızsa `PTS_ANPR_PROVIDERS=cpu` ortam
# değişkeniyle (bkz. anpr_engine.py) çıkarım tamamen CPU'ya zorlanabilir.
_paylasilan_motor: Optional["ANPREngine"] = None
_motor_olusturma_kilit = threading.Lock()
_motor_cagri_kilit = threading.Lock()


def _paylasilan_motoru_al() -> "ANPREngine":
    global _paylasilan_motor
    if _paylasilan_motor is None:
        with _motor_olusturma_kilit:
            if _paylasilan_motor is None:
                _paylasilan_motor = ANPREngine()
    return _paylasilan_motor


logger = logging.getLogger("pts.camera")

PLAKA_REGEX = re.compile(r'^(\d{2})([A-PR-VYZ]{1,3})(\d{2,4})$')

# Plaka overlay stilleri
_OVERLAY_RENK = (0, 220, 80)       # yeşil kutu / metin
_OVERLAY_ARKA = (0, 0, 0)          # metin arkaplanı
_YAZI_OLCEK = 0.8
_YAZI_KALINLIK = 2

# Aynı plaka için son görülme zamanlarının ne kadar süre saklanacağı (bellek
# şişmesin diye budama eşiği = tekrar gecikmesinin birkaç katı).
_PLAKA_HAFIZA_CARPANI = 4

# ------------------------------------------------------------------
# ÇOK KARELİ OY BİRLEŞTİRME ("frame consolidation" / "read voting")
# ------------------------------------------------------------------
# Ticari ANPR sistemlerinin tek kareye göre çok daha yüksek doğruluk elde
# etmesinin başlıca sebeplerinden biri budur: bir araç kamerada birkaç kare
# boyunca görünür, her karede OCR biraz farklı (ve bazen hatalı) bir sonuç
# üretebilir; tek bir kötü kareye güvenmek yerine aynı aracın TÜM okumaları
# toplanıp ağırlıklı oy ile "kazanan" belirlenir. Düşük güvenli tek kareler de
# ayrıca eşikle (min_guven_skoru) elenir.
#
# Kaynak/gerekçe: ANPR doğruluğunu artıran teknikler üzerine 2026-09 araştırma
# notunda (ANPR_ARASTIRMA.md) belirtildiği gibi, doğruluk büyük ölçüde kamera
# donanımı/konumu tarafından belirlenir; yazılım tarafında en etkili katkı bu
# çok kareli oydaşma ve aşağıdaki bilinen-plaka çapraz kontrolüdür (bkz.
# backend/main.py::_bilinen_plakaya_yakinlik_duzelt).
OTURUM_KAPANMA_SN = 1.2      # bu kadar süre yeni okuma gelmezse oturum kapanır (kazanan gönderilir)
OTURUM_BENZERLIK_ESIGI = 2   # aynı oturuma dahil edilecek okumalar arası azami Levenshtein mesafesi
OTURUM_MAX_SURE_SN = 8.0     # bir oturum en fazla bu kadar açık kalır (çok yavaş/duran araç için emniyet)
VARSAYILAN_MIN_GUVEN_SKORU = 0.4  # bu eşiğin altındaki OCR sonuçları oylamaya hiç girmez


class PlakaOyBirikimi:
    """Tek bir 'geçiş oturumu' (aynı aracın kamera görüş alanında kaldığı süre)
    boyunca toplanan OCR okumalarını ağırlıklı oyla birleştirir."""

    __slots__ = ("oylar", "ilk_gorulme", "son_gorulme", "en_yuksek_guven", "en_iyi_jpeg")

    def __init__(self, plaka: str, guven: float, simdi: float, jpeg: Optional[bytes] = None):
        self.oylar: "Counter[str]" = Counter({plaka: guven})
        self.ilk_gorulme = simdi
        self.son_gorulme = simdi
        self.en_yuksek_guven = guven
        self.en_iyi_jpeg = jpeg

    def ekle(self, plaka: str, guven: float, simdi: float, jpeg: Optional[bytes] = None) -> None:
        self.oylar[plaka] += guven
        self.son_gorulme = simdi
        if jpeg is not None and guven >= self.en_yuksek_guven:
            self.en_yuksek_guven = guven
            self.en_iyi_jpeg = jpeg
        elif guven > self.en_yuksek_guven:
            self.en_yuksek_guven = guven

    def kazanan(self) -> dict:
        plaka, _agirlik = self.oylar.most_common(1)[0]
        return {
            "plaka": plaka,
            "guven": self.en_yuksek_guven,
            "farkli_okuma_sayisi": len(self.oylar),
            "toplam_oy": round(sum(self.oylar.values()), 3),
            "jpeg": self.en_iyi_jpeg,
        }


class PlakaOturumTakipcisi:
    """Aktif geçiş oturumlarını (her biri bir PlakaOyBirikimi) yönetir.

    Yeni bir okuma geldiğinde, hâlâ açık (yakın zamanda güncellenmiş) ve
    Levenshtein mesafesi eşik altında olan en yakın oturuma eklenir; yoksa
    yeni bir oturum açılır. `bitmis_oturumlari_al` çağrıldığında sessizliğe
    düşmüş (veya çok uzun sürmüş) oturumlar kapatılıp kazananları döndürülür.
    """

    def __init__(self, oturum_kapanma_sn: float = OTURUM_KAPANMA_SN,
                 benzerlik_esigi: int = OTURUM_BENZERLIK_ESIGI,
                 max_oturum_sure_sn: float = OTURUM_MAX_SURE_SN):
        self._acik: dict[str, PlakaOyBirikimi] = {}
        self.oturum_kapanma_sn = oturum_kapanma_sn
        self.benzerlik_esigi = benzerlik_esigi
        self.max_oturum_sure_sn = max_oturum_sure_sn

    def guncelle(self, plaka: str, guven: float, simdi: float, jpeg: Optional[bytes] = None) -> None:
        en_yakin_anahtar = None
        en_yakin_mesafe = None
        for anahtar, birikim in self._acik.items():
            if simdi - birikim.son_gorulme > self.oturum_kapanma_sn:
                continue  # zaten sessizliğe düşmüş, bitmis_oturumlari_al ile kapanacak
            mesafe = levenshtein_mesafesi(plaka, anahtar)
            if mesafe <= self.benzerlik_esigi and (en_yakin_mesafe is None or mesafe < en_yakin_mesafe):
                en_yakin_anahtar, en_yakin_mesafe = anahtar, mesafe
        if en_yakin_anahtar is not None:
            self._acik[en_yakin_anahtar].ekle(plaka, guven, simdi, jpeg)
        else:
            self._acik[plaka] = PlakaOyBirikimi(plaka, guven, simdi, jpeg)

    def bitmis_oturumlari_al(self, simdi: float, zorla: bool = False) -> list:
        bitmisler = []
        for anahtar in list(self._acik.keys()):
            birikim = self._acik[anahtar]
            sessiz_kaldi = simdi - birikim.son_gorulme > self.oturum_kapanma_sn
            cok_uzun_surdu = simdi - birikim.ilk_gorulme > self.max_oturum_sure_sn
            if zorla or sessiz_kaldi or cok_uzun_surdu:
                bitmisler.append(birikim.kazanan())
                del self._acik[anahtar]
        return bitmisler

    def acik_oturum_sayisi(self) -> int:
        return len(self._acik)


def plaka_dogrula(text: str) -> Optional[str]:
    """OCR çıktısını Türk plaka formatına göre doğrular/temizler. Geçersizse None döner."""
    temiz = text.upper().replace(" ", "")
    eslesme = PLAKA_REGEX.match(temiz)
    if eslesme:
        il_kodu = int(eslesme.group(1))
        if 1 <= il_kodu <= 81:
            return f"{eslesme.group(1)} {eslesme.group(2)} {eslesme.group(3)}"
    return None


def _kare_uzerine_ciz(frame, tespitler: list) -> None:
    """Tespit edilen plakaları kare üzerine in-place çizer."""
    for t in tespitler:
        if t.get("kutu"):
            x1, y1, x2, y2 = t["kutu"]
            cv2.rectangle(frame, (x1, y1), (x2, y2), _OVERLAY_RENK, 2)
        metin = f"{t['plaka']}  {t['guven']:.0%}"
        kutu_x = t["kutu"][0] if t.get("kutu") else 10
        kutu_y = (t["kutu"][1] - 10) if t.get("kutu") else 30
        kutu_y = max(kutu_y, 20)
        (tw, th), _ = cv2.getTextSize(metin, cv2.FONT_HERSHEY_SIMPLEX, _YAZI_OLCEK, _YAZI_KALINLIK)
        cv2.rectangle(frame, (kutu_x - 3, kutu_y - th - 6), (kutu_x + tw + 3, kutu_y + 4), _OVERLAY_ARKA, -1)
        cv2.putText(frame, metin, (kutu_x, kutu_y), cv2.FONT_HERSHEY_SIMPLEX, _YAZI_OLCEK, _OVERLAY_RENK, _YAZI_KALINLIK)


class KameraPipeline:
    def __init__(self, video_kaynagi: str, api_url: str = "http://localhost:8000/kayitlar/otomatik",
                 kamera_id: str = "KAMERA-1", tekrar_gecikme_sn: int = 30, yon: str = "giris",
                 baglanti_zaman_asimi_sn: float = 8.0, donma_esigi_sn: float = 10.0,
                 min_guven_skoru: float = VARSAYILAN_MIN_GUVEN_SKORU):
        if not KUTUPHANELER_MEVCUT:
            raise RuntimeError(
                "Gerekli kütüphaneler kurulu değil. "
                "Kurulum: pip install \"fast-alpr[onnx]\" opencv-python requests"
            )
        self.video_kaynagi = video_kaynagi
        self.api_url = api_url
        self.kamera_id = kamera_id
        self.yon = yon
        self.tekrar_gecikme_sn = tekrar_gecikme_sn
        # Kare akmayı bırakırsa bu kadar saniye sonra yeniden bağlanılır.
        self.baglanti_zaman_asimi_sn = baglanti_zaman_asimi_sn
        # Bu kadar saniyedir taze kare yoksa "donmuş" olarak raporlanır (dışarıya,
        # örn. sağlık uç noktasına, bilgi amaçlı — yeniden bağlanma zaten yukarıdaki
        # zaman aşımıyla otomatik tetiklenir).
        self.donma_esigi_sn = donma_esigi_sn
        # Bu güven skorunun altındaki OCR sonuçları oy birikimine hiç girmez.
        self.min_guven_skoru = min_guven_skoru

        self.motor = _paylasilan_motoru_al()
        self.calisiyor = False
        self.son_plaka_zamani: dict = {}
        # Çok kareli oy birleştirme: bir aracın kamerada kaldığı birden çok
        # karenin okumaları burada toplanıp oydaşmayla kesinleştirilir.
        self._oturum_takipcisi = PlakaOturumTakipcisi()

        # Gecikme-serbest akış: okuyucu thread sadece en son kareyi tutar
        self._son_kare = None
        self._kare_kilit = threading.Lock()
        self._kare_guncellendi = threading.Event()
        # Okuyucu thread'lerin "nesli" — her yeniden bağlanmada artar, eski
        # thread'ler kendi neslinin geçersiz olduğunu görüp sonlanır (sızıntı yok).
        self._gen = 0
        self._gen_kilit = threading.Lock()

        # Son annotated frame (goruntu endpoint'i için)
        self._goruntu_kilit = threading.Lock()
        self._son_goruntu_jpeg: Optional[bytes] = None

        # Son tespit sonuçları (frontend overlay için)
        self._son_tespitler: list = []

        # Gözlemlenebilirlik / durum bilgisi
        self._son_kare_zamani: Optional[float] = None  # time.monotonic()
        self._baslangic_zamani: Optional[float] = None
        self._yeniden_baglanma_sayisi = 0
        self._dongu_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Dışarıya açık: son JPEG kareyi döner (pipeline çalışırken hızlı)
    # ------------------------------------------------------------------

    def son_goruntu_al(self) -> Optional[bytes]:
        with self._goruntu_kilit:
            return self._son_goruntu_jpeg

    def son_tespitler_al(self) -> list:
        return list(self._son_tespitler)

    def son_kare_yasi_sn(self) -> Optional[float]:
        """Son alınan karenin üzerinden geçen süre (sn). Hiç kare gelmediyse None."""
        if self._son_kare_zamani is None:
            return None
        return max(0.0, time.monotonic() - self._son_kare_zamani)

    def thread_canli_mi(self) -> bool:
        """Döngü thread'i gerçekten hayatta mı? (calisiyor bayrağı tek başına yeterli
        değildir: thread beklenmedik bir istisnayla ölmüş olsa bile bayrak True kalabilir.
        Dışarıdaki bekçi/gözetleyici bu metodla gerçek canlılığı kontrol etmelidir.)"""
        return self._dongu_thread is not None and self._dongu_thread.is_alive()

    def durum_bilgisi(self) -> dict:
        """Sağlık kontrolü / arayüz için tek çağrıda tüm pipeline durumu."""
        yas = self.son_kare_yasi_sn()
        donmus = self.calisiyor and (yas is None or yas > self.donma_esigi_sn)
        calisma_suresi = (time.monotonic() - self._baslangic_zamani) if self._baslangic_zamani else 0.0
        return {
            "calisiyor": self.calisiyor,
            "son_kare_yasi_sn": round(yas, 1) if yas is not None else None,
            "donmus": donmus,
            "yeniden_baglanma_sayisi": self._yeniden_baglanma_sayisi,
            "calisma_suresi_sn": round(calisma_suresi, 0),
        }

    # ------------------------------------------------------------------
    # Pipeline kontrolü
    # ------------------------------------------------------------------

    def baslat(self) -> None:
        self.calisiyor = True
        self._baslangic_zamani = time.monotonic()
        self._dongu_thread = threading.Thread(target=self._dongu, daemon=True, name=f"pts-pipeline-{self.kamera_id}")
        self._dongu_thread.start()
        logger.info("Kamera pipeline başlatıldı: %s (%s)", self.kamera_id, self.video_kaynagi)

    def durdur(self) -> None:
        self.calisiyor = False
        # Okuyucu/döngü thread'lerinin kendi kendine çıkması için nesli geçersiz kıl.
        with self._gen_kilit:
            self._gen += 1
        if self._dongu_thread is not None:
            self._dongu_thread.join(timeout=3.0)
        logger.info("Kamera pipeline durduruldu: %s", self.kamera_id)

    # ------------------------------------------------------------------
    # İç metodlar
    # ------------------------------------------------------------------

    def _kare_okuyucu(self, cap, gen: int) -> None:
        """Ayrı thread: RTSP tamponunu sürekli boşaltır, sadece en son kareyi saklar.
        Bu sayede işleyici thread her zaman gecikme-serbest taze kareyle çalışır.

        `gen` bu thread'in ait olduğu bağlantı neslidir; pipeline yeniden bağlanıp
        `self._gen`'i artırdığında bu thread bir sonraki turda kendini durdurur —
        böylece eski (kapatılmış) cap nesnesi üzerinde sonsuza kadar dönmez."""
        ardarda_hata = 0
        while self.calisiyor and gen == self._gen:
            try:
                ret, frame = cap.read()
            except Exception as exc:
                ardarda_hata += 1
                if ardarda_hata == 1:
                    logger.warning("[%s] Kare okuma hatası: %s", self.kamera_id, exc)
                time.sleep(0.2)
                continue
            if ret and frame is not None:
                ardarda_hata = 0
                with self._kare_kilit:
                    self._son_kare = frame
                self._son_kare_zamani = time.monotonic()
                self._kare_guncellendi.set()
            else:
                time.sleep(0.05)

    def _kareyi_isle(self, frame, oturumu_hemen_kapat: bool = False) -> list:
        """Kareyi ANPR motoruna verir. Format olarak geçerli ve yeterince güvenli
        okumalar oturum takipçisine (çok kareli oy birikimine) beslenir; yalnızca
        oydaşmayla KESİNLEŞEN sonuçlar API'ye gönderilir (bkz. PlakaOturumTakipcisi).

        `oturumu_hemen_kapat=True`: tek görsel/tek kare testlerinde (bkz.
        `tek_gorsel_test`) birden fazla kare gelmeyeceği için, bu karedeki
        okumaların oturumu beklemeden hemen kesinleştirilmesini sağlar."""
        tespitler = []
        # GPU'ya (varsa DirectML/CUDA) aynı anda yalnızca TEK bir kameranın çıkarım
        # isteği gitmesini garanti eder — bkz. modül başındaki "PAYLAŞILAN ANPR
        # MOTORU" notu (çoklu kamerada GPU sürücüsü çökmesi/sıfırlanması riski).
        with _motor_cagri_kilit:
            motor_sonuclari = self.motor.tahmin_et(frame)
        for sonuc in motor_sonuclari:
            plaka = plaka_dogrula(sonuc.plaka_no)
            if not plaka:
                continue
            tespitler.append({
                "plaka": plaka,
                "guven": sonuc.guven_skoru,
                "kutu": list(sonuc.kutu) if sonuc.kutu else None,
            })

        # Kare üstüne tüm tespitleri çiz (overlay kopyası) — bu, oy birikimine
        # girme eşiğinden bağımsız olarak operatöre HER geçerli-formatlı ham
        # okumayı gösterir (şeffaflık için).
        annotated = frame.copy()
        _kare_uzerine_ciz(annotated, tespitler)
        _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
        jpeg_bytes = buf.tobytes()
        with self._goruntu_kilit:
            self._son_goruntu_jpeg = jpeg_bytes
        self._son_tespitler = tespitler

        simdi = time.time()

        # ÖNEMLİ SIRALAMA: yeni okumaları eklemeden ÖNCE, bu kareden önce zaten
        # sessizliğe düşmüş oturumları kapatıp kazananlarını al. Aksi halde
        # guncelle() aynı plaka anahtarıyla YENİ bir oturum açıp eskisinin
        # (henüz gönderilmemiş) birikmiş oylarının üzerine sessizce yazar —
        # tam da bu depoda daha önce görülen "sessiz üzerine yazma" hata
        # sınıfının bir başka biçimi olurdu.
        bitmis_oturumlar = self._oturum_takipcisi.bitmis_oturumlari_al(simdi)

        for t in tespitler:
            if t["guven"] < self.min_guven_skoru:
                continue  # düşük güvenli tek kare — oy birikimine hiç girmesin
            self._oturum_takipcisi.guncelle(t["plaka"], t["guven"], simdi, jpeg_bytes)

        if oturumu_hemen_kapat:
            bitmis_oturumlar += self._oturum_takipcisi.bitmis_oturumlari_al(simdi, zorla=True)

        gonderilenler = []
        for oturum in bitmis_oturumlar:
            plaka = oturum["plaka"]
            if (plaka in self.son_plaka_zamani and
                    simdi - self.son_plaka_zamani[plaka] < self.tekrar_gecikme_sn):
                continue
            self.son_plaka_zamani[plaka] = simdi

            gonderilecek_jpeg = oturum["jpeg"] or jpeg_bytes
            gecici = os.path.join(tempfile.gettempdir(), f"{plaka.replace(' ', '')}_{int(simdi)}.jpg")
            with open(gecici, "wb") as f:
                f.write(gonderilecek_jpeg)
            try:
                with open(gecici, "rb") as f:
                    requests.post(
                        self.api_url,
                        data={"plaka_no": plaka, "kamera_id": self.kamera_id,
                              "yon": self.yon, "guven_skoru": round(oturum["guven"], 3)},
                        files={"gorsel": f},
                        timeout=5,
                    )
                gonderilenler.append(plaka)
                if oturum["farkli_okuma_sayisi"] > 1:
                    logger.info(
                        "[%s] Plaka %d farklı okumanın oydaşmasıyla kesinleşti: %s (güven=%.2f, toplam oy=%.2f)",
                        self.kamera_id, oturum["farkli_okuma_sayisi"], plaka, oturum["guven"], oturum["toplam_oy"],
                    )
            except Exception as e:
                logger.error("[%s] API'ye gönderilemedi: %s", self.kamera_id, e)
            finally:
                try:
                    os.remove(gecici)
                except OSError:
                    pass

        self._plaka_hafizasini_buda()
        return gonderilenler

    def _plaka_hafizasini_buda(self) -> None:
        """son_plaka_zamani sözlüğü süresiz büyümesin diye eski girdileri temizler."""
        if len(self.son_plaka_zamani) < 200:
            return
        esik = time.time() - (self.tekrar_gecikme_sn * _PLAKA_HAFIZA_CARPANI)
        eskiler = [p for p, t in self.son_plaka_zamani.items() if t < esik]
        for p in eskiler:
            self.son_plaka_zamani.pop(p, None)

    def _cap_ac(self):
        os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "quiet")
        # stimeout: soket okuma zaman aşımı (mikrosaniye) — kamera susarsa
        # OpenCV'nin süresiz beklemek yerine makul bir sürede hata vermesini sağlar
        # (pipeline zaten bunu _yeniden_baglan ile toparlıyor). max_delay: FFmpeg'in
        # arabelleğe alabileceği azami gecikme. Bu ikisi her koşulda güvenlidir,
        # transport'tan bağımsız olarak eklenir.
        secenekler = ["stimeout;5000000", "max_delay;500000"]
        # RTSP varsayılan olarak UDP üzerinden akar; H.264 gibi büyük I-frame'li
        # kodeklerde tek bir kayıp UDP paketi tüm GOP'u (sonraki keyframe'e kadar
        # olan tüm kareleri) bozabilir ("takılma/donma"). TCP'ye zorlamak bunu
        # azaltabilir AMA sahada gözlemlendi ki bazı kamera/ağ/NAT kombinasyonları
        # RTSP-üzerinden-TCP'yi hiç desteklemiyor veya kararsız çalışıyor — bu
        # durumda TCP'ye zorlamak "İlk bağlantı açılamadı" / sık yeniden bağlanma
        # artışına yol açıp durumu İYİLEŞTİRECEĞİNE KÖTÜLEŞTİRİYOR (hatta bir
        # geçişin hiç yakalanamamasına kadar gidebiliyor). Bu yüzden transport
        # ZORLAMA artık VARSAYILAN DEĞİL — yalnızca PTS_RTSP_TRANSPORT=tcp (veya
        # =udp) ortam değişkeniyle açıkça istenirse etkinleşir; aksi halde
        # FFmpeg'in kendi varsayılanı kullanılır (bu, önceki (2026-09 öncesi)
        # sorunsuz çalışan davranışla aynıdır).
        transport = os.environ.get("PTS_RTSP_TRANSPORT", "").strip().lower()
        if transport in ("tcp", "udp"):
            secenekler.insert(0, f"rtsp_transport;{transport}")
        # setdefault DEĞİL: her kamera aynı süreçte aynı seçenekleri görsün diye
        # (aksi halde ilk açılan kameranın ortam değişkeni kalıcı olur, sonraki
        # kameralar/yeniden bağlanmalar bunu değiştiremezdi).
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "|".join(secenekler)
        cap = cv2.VideoCapture(self.video_kaynagi, cv2.CAP_FFMPEG)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        return cap

    def _yeniden_baglan(self, eski_cap) -> tuple:
        """Eski cap'i kapatır, yeni bağlantı açar, yeni nesil ile okuyucu thread başlatır."""
        with self._gen_kilit:
            self._gen += 1
            gen = self._gen
        try:
            eski_cap.release()
        except Exception:
            pass
        cap = self._cap_ac()
        okuyucu = threading.Thread(target=self._kare_okuyucu, args=(cap, gen), daemon=True,
                                    name=f"pts-okuyucu-{self.kamera_id}-{gen}")
        okuyucu.start()
        return cap, gen

    def _dongu(self) -> None:
        """Ana pipeline döngüsü. Tamamı try/except ile sarılı: beklenmeyen bir
        istisna thread'i sessizce öldürmez, önce loglanır — dışarıdaki bekçi
        (main.py) `thread_canli_mi()` ile gerçek ölümü tespit edip yeniden başlatabilir."""
        cap = None
        try:
            cap = self._cap_ac()
            if not cap.isOpened():
                logger.warning("[%s] İlk bağlantı açılamadı, yeniden denenecek…", self.kamera_id)
            with self._gen_kilit:
                gen = self._gen
            okuyucu = threading.Thread(target=self._kare_okuyucu, args=(cap, gen), daemon=True,
                                        name=f"pts-okuyucu-{self.kamera_id}-{gen}")
            okuyucu.start()

            while self.calisiyor:
                # Taze kare gelene kadar bekle (zaman aşımı = baglanti_zaman_asimi_sn)
                guncellendi = self._kare_guncellendi.wait(timeout=self.baglanti_zaman_asimi_sn)
                if not self.calisiyor:
                    break
                if not guncellendi:
                    # Süre içinde kare gelmedi → yeniden bağlan
                    self._yeniden_baglanma_sayisi += 1
                    logger.warning("[%s] %.0f sn kare gelmedi, yeniden bağlanıyor (deneme #%d)…",
                                    self.kamera_id, self.baglanti_zaman_asimi_sn, self._yeniden_baglanma_sayisi)
                    time.sleep(min(2 * self._yeniden_baglanma_sayisi, 15))
                    if not self.calisiyor:
                        break
                    cap, _ = self._yeniden_baglan(cap)
                    continue

                self._kare_guncellendi.clear()
                with self._kare_kilit:
                    kare = self._son_kare

                if kare is not None:
                    if self._yeniden_baglanma_sayisi:
                        logger.info("[%s] Bağlantı toparlandı.", self.kamera_id)
                    self._yeniden_baglanma_sayisi = 0
                    try:
                        self._kareyi_isle(kare)
                    except Exception as exc:
                        logger.error("[%s] Kare işleme hatası: %s", self.kamera_id, exc)

                # Tam akış → sadece ANPR frekansını sınırla, görüntü okuyucu thread'i yavaşlamıyor
                time.sleep(0.25)
        except Exception as exc:
            logger.error("[%s] Pipeline döngüsü beklenmedik şekilde çöktü: %s", self.kamera_id, exc, exc_info=True)
            self.calisiyor = False
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass


def tek_gorsel_test(gorsel_yolu: str, api_url: str = "http://localhost:8000/kayitlar/otomatik",
                    kamera_id: str = "TEST-KAMERA", yon: str = "giris"):
    """Kamera/video olmadan tek bir görsel üzerinde pipeline'ı uçtan uca doğrular.

    Örnek: python -c "from camera_reader import tek_gorsel_test; tek_gorsel_test('arac.jpg')"
    """
    if not KUTUPHANELER_MEVCUT:
        raise RuntimeError(
            "Gerekli kütüphaneler kurulu değil. "
            "Kurulum: pip install \"fast-alpr[onnx]\" opencv-python requests"
        )
    frame = cv2.imread(gorsel_yolu)
    if frame is None:
        raise ValueError(f"Görsel okunamadı: {gorsel_yolu}")
    pipeline = KameraPipeline(video_kaynagi=gorsel_yolu, api_url=api_url, kamera_id=kamera_id, yon=yon)
    gonderilenler = pipeline._kareyi_isle(frame, oturumu_hemen_kapat=True)
    if gonderilenler:
        print(f"Tespit edilip gönderilen plakalar: {gonderilenler}")
    else:
        print("Görselde geçerli formatta bir plaka tespit edilemedi.")
    return gonderilenler
