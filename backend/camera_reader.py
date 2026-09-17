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
from urllib.parse import urlsplit, urlunsplit

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


def dedektor_esigi_bilgisi() -> Optional[dict]:
    """Paylaşılan ANPR motoru zaten oluşturulduysa (en az bir kamera pipeline'ı
    veya klasör izleyici başladıysa) fiilen uygulanan dedektör güven eşiği ve
    kaynağı (ortam değişkeni mi, kütüphane varsayılanı mı) bilgisini döner.

    Motor henüz oluşturulmadıysa None döner — bu çağrı BİLEREK motoru tetiklemez
    (ağır ONNX model yüklemesini /sistem/saglik gibi sık çağrılabilecek bir
    teşhis ucundan tetiklemek istemeyiz). Panelde/logda "PTS_ANPR_DETECTOR_ESIGI
    ayarım kabul edildi mi?" sorusuna kod okumadan cevap verebilmek için eklendi.
    """
    if _paylasilan_motor is None:
        return None
    return {
        "esik": getattr(_paylasilan_motor, "detektor_esigi_etkin", 0.4),
        "kaynak": getattr(_paylasilan_motor, "detektor_esigi_kaynagi", "bilinmiyor"),
    }


logger = logging.getLogger("pts.camera")

PLAKA_REGEX = re.compile(r'^(\d{2})([A-PR-VYZ]{1,3})(\d{2,4})$')


def _rtsp_url_maskele(url: str) -> str:
    """Loglanacak bir video kaynağı adresindeki (varsa) RTSP kullanıcı adı/
    parolasını maskeler — bkz. backend/main.py::_kamera_guvenli_gorunum ile
    AYNI amaç (API üzerinden parolanın istemciye gitmesini engellemek), ama
    burada log dosyasına (loglar/pts.log, /sistem/loglar uç noktasıyla
    servis edilir) yazılmadan ÖNCE, kaynağında uygulanır.

    GÜVENLİK GEÇMİŞİ: `baslat()` içindeki log satırı `self.video_kaynagi`'yi
    (genelde `rtsp://kullanici:sifre@ip:554/...` biçiminde) OLDUĞU GİBİ
    logluyordu — her pipeline başlangıcında/watchdog yeniden başlatmasında,
    yani sık sık. main.py'deki parola maskeleme özeni bu tek satırdan tamamen
    boşa çıkıyordu."""
    try:
        parcalar = urlsplit(url)
    except ValueError:
        return url
    if not (parcalar.username or parcalar.password):
        return url
    host = parcalar.hostname or ""
    if parcalar.port:
        host = f"{host}:{parcalar.port}"
    return urlunsplit((parcalar.scheme, f"{parcalar.username or 'kamera'}:****@{host}",
                        parcalar.path, parcalar.query, parcalar.fragment))

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

# Dedektör ardı ardına hiçbir plaka adayı bulamazsa (bkz. _kareyi_isle), bunu en
# fazla bu sıklıkta (saniye) özetleyen TEK bir log satırı yazılır. Amaç spam
# değil, "pipeline canlı ve kare işliyor ama dedektör gerçekten hiçbir şey mi
# bulamıyor" sorusuna en azından kaba bir gözlemlenebilirlik kazandırmaktır —
# bkz. anpr_engine.py::PTS_ANPR_DETECTOR_ESIGI notu.
BOS_TESPIT_LOG_ARALIK_SN = 120

# ------------------------------------------------------------------
# HAM KARE TEŞHİS KAYDI (opsiyonel, varsayılan KAPALI)
# ------------------------------------------------------------------
# PTS_ANPR_DETECTOR_ESIGI'yi düşürmek sorunu ÇÖZMEZSE (yani dedektör eşiği
# değil de başka bir şey — plaka bölgesi kareye hiç girmiyor, kamera görüntü
# işleme ayarları görüntüyü aşırı bozuyor, çözünürlük çok düşük vb. — asıl
# neden ise), bunu KÖR bir şekilde eşik deneyerek değil, dedektöre GERÇEKTEN
# giden ham kareyi gözle görerek anlamak gerekir. PTS_HAM_KARE_KAYIT_DIZINI
# ortam değişkeni bir dizin yoluna ayarlanırsa, dedektörün hiçbir aday
# bulamadığı kareler (yani "boş tespit" logunu tetikleyen TAM OLARAK aynı
# kareler) o dizine periyodik olarak (kamera başına en fazla
# HAM_KARE_KAYIT_ARALIK_SN'de bir) JPEG olarak kaydedilir. Disk şişmesin diye
# hem kayıt sıklığı sınırlıdır hem de kamera başına en fazla
# HAM_KARE_MAKS_DOSYA_KAMERA_BASINA dosya tutulur (eskiler otomatik silinir).
# Varsayılan olarak KAPALIDIR; yalnızca teşhis sırasında açılması, sorun
# netleşince kapatılması önerilir.
HAM_KARE_KAYIT_ARALIK_SN = 5.0
HAM_KARE_MAKS_DOSYA_KAMERA_BASINA = 300


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


def _kontrast_iyilestirme_aktif_mi() -> bool:
    """PTS_GORUNTU_ON_ISLEME_KONTRAST ayarlıysa (üretim davranışını sessizce
    değiştirmemek için VARSAYILAN KAPALI), dedektöre verilen kare önce
    kontrast iyileştirmesinden geçirilir (bkz. _kontrast_iyilestirmesi_uygula).
    Diğer opsiyonel bayraklarla aynı şekilde her çağrıda TAZE okunur (import
    zamanında değil) ki testlerde/toplu doğruluk testinde davranış tutarlı olsun."""
    return os.environ.get("PTS_GORUNTU_ON_ISLEME_KONTRAST", "").strip().lower() in ("1", "true", "evet", "yes")


def _kontrast_iyilestirmesi_uygula(frame):
    """CLAHE (Contrast Limited Adaptive Histogram Equalization) ile,
    aydınlatması dengesiz (gölge/farlardan gelen parlama/gece IR modu gibi)
    kareleri dedektöre vermeden önce iyileştirir. Yalnızca LAB renk uzayının
    L (parlaklık) kanalına uygulanır — renk bilgisini bozmadan, zaten parlak
    bölgeleri (naif histogram eşitlemenin aksine) tamamen "yakmadan" yerel
    kontrastı güçlendirir. Bu, ANPR literatüründe düşük ışık/parlama
    koşullarında tespit oranını artırmak için standart, düşük riskli bir
    ilk-basamak tekniğidir.

    ÖNEMLİ: Bu YALNIZCA dedektöre giden kareyi etkiler. Kaydedilen/panelde
    gösterilen fotoğraf (bkz. çağıran koddaki `annotated = frame.copy()`)
    HER ZAMAN orijinal, işlenmemiş kareden üretilir — yani bu ayar kayıtların
    görünümünü hiç değiştirmez, yalnızca tespit/OCR'ın gördüğü kareyi
    iyileştirir."""
    try:
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_kanali, a_kanali, b_kanali = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l_kanali = clahe.apply(l_kanali)
        lab = cv2.merge((l_kanali, a_kanali, b_kanali))
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    except Exception:
        logger.exception("Kontrast iyileştirme uygulanamadı, orijinal kare kullanılıyor")
        return frame


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
        # GÖZLEMLENEBİLİRLİK: dedektör hiçbir plaka bulamazsa (sonuc listesi
        # tamamen boşsa) bunu HER karede loglamak günlük dosyasını gereksiz
        # şişirir (boş yol/trafiksiz an normaldir); ama hiç loglamamak da
        # "dedektör gerçekten çalışıyor mu, hiç mi tespit etmiyor" sorusunu
        # tamamen görünmez bırakır. Bu yüzden en fazla BOS_TESPIT_LOG_ARALIK_SN'de
        # bir, art arda süregelen boş sonuç durumunda özet bir satır loglanır.
        self._son_bos_tespit_log_zamani: float = 0.0
        self._bos_tespit_sayaci_son_logdan_beri: int = 0
        # HAM KARE TEŞHİS KAYDI (bkz. modül başındaki not) için son kayıt zamanı.
        self._son_ham_kare_kayit_zamani: float = 0.0
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
        logger.info("Kamera pipeline başlatıldı: %s (%s)", self.kamera_id, _rtsp_url_maskele(self.video_kaynagi))

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
        # PTS_GORUNTU_ON_ISLEME_KONTRAST ayarlıysa, dedektöre ORİJİNAL kare
        # yerine kontrastı iyileştirilmiş bir kopyası verilir (gece/parlama
        # koşullarında tespit oranını artırmak için) — kaydedilen/panelde
        # gösterilen görsel her zaman `frame`'in kendisinden üretildiği için
        # (aşağıdaki `annotated = frame.copy()`) bu, kayıtların görünümünü
        # etkilemez.
        dedektore_giden_kare = (
            _kontrast_iyilestirmesi_uygula(frame) if _kontrast_iyilestirme_aktif_mi() else frame
        )
        # GPU'ya (varsa DirectML/CUDA) aynı anda yalnızca TEK bir kameranın çıkarım
        # isteği gitmesini garanti eder — bkz. modül başındaki "PAYLAŞILAN ANPR
        # MOTORU" notu (çoklu kamerada GPU sürücüsü çökmesi/sıfırlanması riski).
        with _motor_cagri_kilit:
            motor_sonuclari = self.motor.tahmin_et(dedektore_giden_kare)

        if not motor_sonuclari:
            # GÖZLEMLENEBİLİRLİK: dedektör bu karede TEK bir plaka adayı bile
            # bulamadı — bu, aşağıdaki format/güven filtrelerinden ÖNCEKİ bir
            # aşamadır (FastALPR'ın kendi dahili detector_conf_thresh eşiği;
            # bkz. anpr_engine.py). "Araç net görünüyor ama hiç kayda düşmüyor"
            # şikayetlerinde, sorun bizim OCR-sonrası filtrelerimizde DEĞİL de
            # burada (dedektör hiçbir kutu önermiyor) olabilir — ve o durumda
            # camera_reader.py'deki diğer üç log noktası da (format uyuşmazlığı,
            # düşük OCR güveni, API reddi) SESSİZ kalır, çünkü hiçbiri hiç
            # tetiklenmez. Bu satır o görünmez boşluğu en azından kaba biçimde
            # açığa çıkarır.
            self._bos_tespit_sayaci_son_logdan_beri += 1
            _simdi_mono = time.monotonic()
            if _simdi_mono - self._son_bos_tespit_log_zamani >= BOS_TESPIT_LOG_ARALIK_SN:
                # DİKKAT: buradaki eşik değeri motor.detektor_esigi_etkin'den, yani
                # FİİLEN UYGULANMAKTA OLAN değerden okunur — sabit bir metin DEĞİLDİR.
                # Böylece "ayarımı düşürdüm ama log hâlâ eskisini söylüyor" karışıklığı
                # yaşanmaz: bu satır PTS_ANPR_DETECTOR_ESIGI ayarlanıp ayarlanmadığını
                # ve şu an hangi değerin geçerli olduğunu her zaman doğru yansıtır.
                _etkin_esik = getattr(self.motor, "detektor_esigi_etkin", 0.4)
                _esik_kaynagi = getattr(self.motor, "detektor_esigi_kaynagi", "bilinmiyor")
                logger.info(
                    "[%s] Son %.0f sn içinde dedektör %d karede hiçbir plaka adayı "
                    "bulamadı (OCR'a hiç ulaşmadan elendi). Bu her zaman normaldir "
                    "(trafiksiz an); ama net görünen bir araç yine de hiç kayda "
                    "düşmüyorsa dedektör eşiğini (şu an %.2f, kaynak: %s) düşürmeyi "
                    "deneyin: PTS_ANPR_DETECTOR_ESIGI işletim sistemi ortam değişkenini "
                    "ayarlayıp uygulamayı YENİ bir terminalden yeniden başlatın — bu "
                    "panelin 'Min. plaka tanıma güveni' ayarından FARKLI bir eşiktir "
                    "ve panelden değiştirilemez (bkz. anpr_engine.py).",
                    self.kamera_id, BOS_TESPIT_LOG_ARALIK_SN, self._bos_tespit_sayaci_son_logdan_beri,
                    _etkin_esik, _esik_kaynagi,
                )
                self._son_bos_tespit_log_zamani = _simdi_mono
                self._bos_tespit_sayaci_son_logdan_beri = 0

            ham_kare_dizini = os.environ.get("PTS_HAM_KARE_KAYIT_DIZINI", "").strip()
            if ham_kare_dizini:
                self._ham_kareyi_kaydet_gerekirse(frame, _simdi_mono, ham_kare_dizini)

        for sonuc in motor_sonuclari:
            plaka = plaka_dogrula(sonuc.plaka_no)
            if not plaka:
                # GÖZLEMLENEBİLİRLİK: OCR bir şey okudu ama Türk plaka formatına
                # uymadığı için tamamen sessizce atlanıyordu — "kamera görüntü
                # alıyor, araç net görünüyor ama hiçbir zaman kayda düşmüyor"
                # şikayetlerinde bunun neden olduğunu ayırt edebilmek için loglanır.
                logger.info(
                    "[%s] OCR okuması Türk plaka formatına uymadı, atlandı: '%s' (güven=%.2f)",
                    self.kamera_id, sonuc.plaka_no, sonuc.guven_skoru,
                )
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
                # GÖZLEMLENEBİLİRLİK: format olarak geçerli bir plaka okundu ama
                # güven eşiğinin altında kaldığı için oy birikimine HİÇ girmedi —
                # bunu da (yukarıdaki format-uyuşmazlığı gibi) loglamazsak, "araç
                # net görünüyor ama hiç kayda düşmüyor" şikayetlerinde neyin
                # sessizce elendiğini asla bilemeyiz.
                logger.info(
                    "[%s] Düşük güvenli okuma oy birikimine girmedi: %s (güven=%.2f < eşik=%.2f)",
                    self.kamera_id, t["plaka"], t["guven"], self.min_guven_skoru,
                )
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
                # GÜVENLİK/DOĞRULUK: /kayitlar/otomatik uç noktası PTS_KAMERA_ANAHTARI
                # ayarlıysa X-PTS-Kamera-Anahtari başlığını zorunlu kılıyor (bkz.
                # main.py::kayit_ekle_otomatik) — ama bu istek daha önce bu başlığı
                # HİÇ göndermiyordu. Yani bir kullanıcı README'nin kendi önerdiği
                # güvenlik sıkılaştırmasını (backend farklı bir ağdaysa
                # PTS_KAMERA_ANAHTARI ayarlamak) uygularsa, kendi Python
                # pipeline'ının tespit ettiği HER plaka sessizce 401 ile
                # reddedilir hale gelirdi (kamera görüntü alıyor, tespit ediyor,
                # ama hiçbir zaman kayda düşmüyor — tam da bu depoda defalarca
                # peşine düşülen semptom sınıfı). Artık aynı ortam değişkeni
                # burada da okunup başlığa ekleniyor.
                _kamera_anahtari = os.getenv("PTS_KAMERA_ANAHTARI")
                _istek_basliklari = {"X-PTS-Kamera-Anahtari": _kamera_anahtari} if _kamera_anahtari else {}
                with open(gecici, "rb") as f:
                    yanit = requests.post(
                        self.api_url,
                        data={"plaka_no": plaka, "kamera_id": self.kamera_id,
                              "yon": self.yon, "guven_skoru": round(oturum["guven"], 3)},
                        files={"gorsel": f},
                        headers=_istek_basliklari,
                        timeout=5,
                    )
                if yanit.status_code >= 400:
                    # GÖZLEMLENEBİLİRLİK: istek sunucuya ULAŞTI (bağlantı hatası
                    # yok, bu yüzden except bloğuna hiç düşmedi) ama sunucu
                    # reddetti (doğrulama hatası, hız sınırı vb.). Önceden bu
                    # durum kontrol edilmiyordu ve SESSİZCE "gönderildi" say
                    # ılıyordu — "araç net görünüyor, API'ye gönderilemedi hatası
                    # da yok ama yine de kayda düşmüyor" gibi iz bırakmayan bir
                    # kayıp sınıfına yol açabiliyordu.
                    logger.error(
                        "[%s] API isteği sunucu tarafından reddedildi (HTTP %d): %s — plaka: %s",
                        self.kamera_id, yanit.status_code, yanit.text[:200], plaka,
                    )
                else:
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

    def _ham_kareyi_kaydet_gerekirse(self, frame, simdi_mono: float, dizin: str) -> None:
        """PTS_HAM_KARE_KAYIT_DIZINI ayarlıysa, dedektörün hiçbir aday bulamadığı
        (yani "boş tespit" logunu tetikleyen) ham kareyi bu dizine kaydeder —
        bkz. modül başındaki "HAM KARE TEŞHİS KAYDI" notu."""
        if simdi_mono - self._son_ham_kare_kayit_zamani < HAM_KARE_KAYIT_ARALIK_SN:
            return
        self._son_ham_kare_kayit_zamani = simdi_mono
        try:
            os.makedirs(dizin, exist_ok=True)
            guvenli_ad = re.sub(r"[^A-Za-z0-9_-]", "_", self.kamera_id)
            dosya_adi = f"{guvenli_ad}_{int(time.time())}.jpg"
            cv2.imwrite(os.path.join(dizin, dosya_adi), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
            self._ham_kare_dosyalarini_buda(dizin, guvenli_ad)
        except Exception as exc:
            logger.warning("[%s] Ham teşhis karesi kaydedilemedi: %s", self.kamera_id, exc)

    @staticmethod
    def _ham_kare_dosyalarini_buda(dizin: str, guvenli_ad: str) -> None:
        """Bu kamera için diskte birikmiş ham teşhis karesi sayısını sınırlar
        (yalnızca en yeni HAM_KARE_MAKS_DOSYA_KAMERA_BASINA dosya tutulur)."""
        try:
            onek = guvenli_ad + "_"
            dosyalar = sorted(f for f in os.listdir(dizin) if f.startswith(onek))
            fazla = len(dosyalar) - HAM_KARE_MAKS_DOSYA_KAMERA_BASINA
            for eski in dosyalar[:max(fazla, 0)]:
                try:
                    os.remove(os.path.join(dizin, eski))
                except OSError:
                    pass
        except OSError:
            pass

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


class KlasorIzleyici:
    """Gerçek bir kamera bağlı olmadan (ya da bağlıyken bile) bir klasöre
    bırakılan araç fotoğraflarını, sanki gerçek bir kameradan gelmiş gibi
    otomatik olarak tespit edip kaydeden arka plan görevi.

    Kullanım: `PTS_GORSEL_IZLEME_DIZINI` ortam değişkenini bir klasöre
    ayarlayın (main.py açılışta bu sınıfı otomatik başlatır). Kök klasörün
    DOĞRUDAN içine bırakılan fotoğraflar GİRİŞ, `cikis/` alt klasörüne
    bırakılanlar ÇIKIŞ olarak işlenir. İşlenen (başarılı ya da başarısız)
    her dosya `islenenler/` alt klasörüne taşınır ki bir daha işlenmesin ve
    kullanıcı ne olduğunu görebilsin (tespit başarısızsa dosya adının başına
    `TESPIT_EDILEMEDI_` eklenir — bu, dedektör eşiğini gerçek, sorunlu
    fotoğraflarla test etmek için özellikle kullanışlıdır, bkz. README
    "Araç net görünüyor ama hiç kayda düşmüyor" bölümü).

    Bir dosyanın hâlâ kopyalanmakta (yarım yazılmış) olabileceğini hesaba
    katar: bir dosya yalnızca İKİ ARDIŞIK taramada AYNI boyutta görülürse
    "tamamlanmış" sayılıp işlenir. Bu yüzden bir fotoğrafın işlenmesi en az
    bir tarama aralığı kadar gecikir — kasıtlıdır, yarım/bozuk dosya okuma
    riskini ortadan kaldırır.

    Tespit için gerçek `KameraPipeline._kareyi_isle()` yolunu (paylaşılan
    ANPR motoru + oturum/oydaşma mantığı + `/kayitlar/otomatik` API çağrısı
    dahil) kullanır — yani yetki kontrolü, veritabanı kaydı ve LED panel
    bildirimi de dahil olmak üzere sistemin geri kalanı, gerçek bir kameradan
    gelen tespit ile TAMAMEN aynı şekilde işler."""

    DESTEKLENEN_UZANTILAR = (".jpg", ".jpeg", ".jpe", ".png", ".bmp")

    def __init__(self, kok_klasor: str, api_url: str = "http://localhost:8000/kayitlar/otomatik",
                 tarama_araligi_sn: float = 5.0):
        if not KUTUPHANELER_MEVCUT:
            raise RuntimeError(
                "Gerekli kütüphaneler kurulu değil. "
                "Kurulum: pip install \"fast-alpr[onnx]\" opencv-python requests"
            )
        self.kok_klasor = kok_klasor
        self.api_url = api_url
        self.tarama_araligi_sn = tarama_araligi_sn
        self.calisiyor = False
        self._thread: Optional[threading.Thread] = None
        # Yön başına kalıcı KameraPipeline nesnesi — ardışık fotoğraflar
        # arasında oturum/oydaşma ve "aynı plakayı kısa sürede tekrar
        # kaydetme" (tekrar_gecikme_sn) durumunu korumak için (gerçek bir
        # kameranın aynı aracı birden çok karede görmesiyle aynı mantık).
        self._pipelinelar: dict = {}
        # Boyutu henüz kararlı hale gelmemiş aday dosyalar: yol -> son görülen boyut
        self._adaylar: dict = {}

        os.makedirs(self.kok_klasor, exist_ok=True)
        os.makedirs(os.path.join(self.kok_klasor, "cikis"), exist_ok=True)
        os.makedirs(os.path.join(self.kok_klasor, "islenenler"), exist_ok=True)

    def baslat(self) -> None:
        self.calisiyor = True
        self._thread = threading.Thread(target=self._dongu, daemon=True, name="pts-klasor-izleyici")
        self._thread.start()
        logger.info(
            "Klasör izleyici başlatıldı: %s (her %s sn bir taranır; kök=giriş, cikis/=çıkış)",
            self.kok_klasor, self.tarama_araligi_sn,
        )

    def durdur(self) -> None:
        self.calisiyor = False
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    def _pipeline_al(self, yon: str) -> "KameraPipeline":
        if yon not in self._pipelinelar:
            self._pipelinelar[yon] = KameraPipeline(
                video_kaynagi=f"klasor-izleme:{yon}",  # gerçek bir RTSP/dosya kaynağı değil, sadece etiket
                api_url=self.api_url,
                kamera_id=f"KLASOR-{'GIRIS' if yon == 'giris' else 'CIKIS'}",
                yon=yon,
            )
        return self._pipelinelar[yon]

    def _aday_dosyalari_tara(self) -> list:
        """Kök klasördeki (giriş) ve `cikis/` alt klasöründeki görsel dosyaları
        listeler. `islenenler/` klasörünün kendisi taranmaz (yalnızca hedef)."""
        adaylar = []
        for yon, klasor in (("giris", self.kok_klasor), ("cikis", os.path.join(self.kok_klasor, "cikis"))):
            try:
                dosyalar = os.listdir(klasor)
            except OSError:
                continue
            for ad in sorted(dosyalar):
                if not ad.lower().endswith(self.DESTEKLENEN_UZANTILAR):
                    continue
                tam_yol = os.path.join(klasor, ad)
                if not os.path.isfile(tam_yol):
                    continue
                adaylar.append((yon, tam_yol))
        return adaylar

    def _tek_tur(self) -> None:
        mevcut_yollar = set()
        for yon, tam_yol in self._aday_dosyalari_tara():
            mevcut_yollar.add(tam_yol)
            try:
                boyut = os.path.getsize(tam_yol)
            except OSError:
                continue
            onceki = self._adaylar.get(tam_yol)
            if onceki is None or onceki != boyut:
                # Yeni görülen ya da hâlâ büyüyen (muhtemelen kopyalanıyor) bir
                # dosya — boyutunu kaydet, bir sonraki turda tekrar bakılacak.
                self._adaylar[tam_yol] = boyut
                continue
            # İki ardışık tarama aynı boyutu gördü -> kopyalama tamamlanmış say.
            del self._adaylar[tam_yol]
            self._dosyayi_isle(yon, tam_yol)

        # Artık var olmayan (işlenmiş/silinmiş/elle kaldırılmış) dosyaları
        # takip listesinden temizle ki sonsuza kadar birikmesin.
        for yol in list(self._adaylar):
            if yol not in mevcut_yollar:
                del self._adaylar[yol]

    def _dosyayi_isle(self, yon: str, tam_yol: str) -> None:
        frame = cv2.imread(tam_yol)
        if frame is None:
            logger.warning(
                "Klasör izleyici: görsel okunamadı (bozuk/desteklenmeyen format olabilir): %s", tam_yol,
            )
            self._islenenlere_tasi(tam_yol, basarili=False)
            return
        try:
            pipeline = self._pipeline_al(yon)
            gonderilenler = pipeline._kareyi_isle(frame, oturumu_hemen_kapat=True)
        except Exception:
            logger.exception("Klasör izleyici: %s işlenirken beklenmeyen hata", tam_yol)
            self._islenenlere_tasi(tam_yol, basarili=False)
            return
        if gonderilenler:
            logger.info("Klasör izleyici: %s -> tespit edilip kaydedildi: %s", os.path.basename(tam_yol), gonderilenler)
        else:
            logger.warning(
                "Klasör izleyici: %s içinde geçerli formatta/yeterli güvende bir plaka tespit "
                "edilemedi (gerçek bir kamerada da aynı fotoğraf aynı sonucu verirdi — dedektör "
                "güven eşiğini düşürmeyi deneyin: PTS_ANPR_DETECTOR_ESIGI, bkz. anpr_engine.py)",
                os.path.basename(tam_yol),
            )
        self._islenenlere_tasi(tam_yol, basarili=bool(gonderilenler))

    def _islenenlere_tasi(self, tam_yol: str, basarili: bool) -> None:
        islenenler_klasoru = os.path.join(self.kok_klasor, "islenenler")
        os.makedirs(islenenler_klasoru, exist_ok=True)
        taban_ad = os.path.basename(tam_yol)
        on_ek = "" if basarili else "TESPIT_EDILEMEDI_"
        hedef = os.path.join(islenenler_klasoru, f"{on_ek}{int(time.time())}_{taban_ad}")
        try:
            os.replace(tam_yol, hedef)
        except OSError as exc:
            logger.warning("Klasör izleyici: %s taşınamadı: %s", tam_yol, exc)

    def _dongu(self) -> None:
        while self.calisiyor:
            try:
                self._tek_tur()
            except Exception:
                logger.exception("Klasör izleyici turunda beklenmeyen hata")
            time.sleep(self.tarama_araligi_sn)


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
