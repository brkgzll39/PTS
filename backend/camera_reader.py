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
    from backend.metin_araclari import levenshtein_mesafesi, sondan_bir_karakter_eksik_mi
except ImportError:
    from metin_araclari import levenshtein_mesafesi, sondan_bir_karakter_eksik_mi

try:
    import cv2
    import numpy as np
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
    teşhis ucundan tetiklemek istemeyiz). Panelde/logda "PTS_ANPR_DETECTOR_ESIGI /
    PTS_ANPR_DETECTOR_MODEL ayarım kabul edildi mi?" sorusuna kod okumadan cevap
    verebilmek için eklendi. NOT: "esik"/"kaynak" anahtarları geriye dönük
    uyumluluk için korunuyor (patch #21'de eklendi); "model"/"model_kaynagi"
    burada yeni eklendi.
    """
    if _paylasilan_motor is None:
        return None
    return {
        "esik": getattr(_paylasilan_motor, "detektor_esigi_etkin", 0.4),
        "kaynak": getattr(_paylasilan_motor, "detektor_esigi_kaynagi", "bilinmiyor"),
        "model": getattr(_paylasilan_motor, "dedektor_modeli_etkin", None),
        "model_kaynagi": getattr(_paylasilan_motor, "dedektor_modeli_kaynagi", "bilinmiyor"),
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

# 2026-09-24 kullanıcı geri bildirimi ("bu plakayı neden 3 dakika içinde 3
# defa çekmiş"): bir araç bariyerde/nöbetçi kontrolünde OTURUM_MAX_SURE_SN
# (8 sn) üzerinde beklerse, oturum -- araç kareden HİÇ ayrılmamış olsa bile --
# güvenlik amaçlı süre sınırı yüzünden zorla kapatılıp YENİ bir kayıt
# gönderiliyordu; araç beklemeye devam ettikçe bu birkaç dakika boyunca
# tekrar tekrar oluyordu (bkz. KameraPipeline._kareyi_isle'deki
# "_suregelen_plakalar" mekanizması -- aynı kesintisiz görünüm için İKİNCİ
# bir kayıt üretilmesini engeller). Bu zaman aşımı, o mekanizmanın
# GÜVENLİK AĞIDIR: bir plaka _suregelen_plakalar'da bu süreden uzun süredir
# tazelenmediyse (ne 'max_sure' ne 'sessizlik' kapanışıyla), araç GERÇEKTEN
# ayrılmış sayılır ve kayıt serbest bırakılır (bkz.
# KameraPipeline._suregelen_plakalari_buda'nın docstring'i, kök neden
# açıklaması için). OTURUM_MAX_SURE_SN'in birkaç katı olacak şekilde
# seçildi -- araç kesintisiz beklerken kapanışlar arası en kötü aralık
# yaklaşık OTURUM_MAX_SURE_SN kadardır, bu yüzden geniş bir emniyet payı
# bırakılıyor.
_SUREGELEN_PLAKA_ZAMAN_ASIMI_SN = OTURUM_MAX_SURE_SN * 2.5  # = 20.0 sn

# ------------------------------------------------------------------
# "SONDAN KARAKTER EKSİK" DÜZELTMESİ (2026-09-18)
# ------------------------------------------------------------------
# Kullanıcı bildirimi: kamerada gayet net/tam karşıdan görünen bir plaka
# ("02 AFP 552"), panelde "02 AFP 55" (son rakam eksik) olarak, %100 güvenle
# ve TÜM karelerin (6/6) "oydaşmasıyla" kaydedildi. Araştırma: fast_alpr
# kütüphanesinin kaynağı incelendiğinde (bkz. README.md'deki bu tarihli not),
# dedektörün önerdiği kutu HİÇBİR kenar boşluğu (padding) eklenmeden, tam
# sınırlarından kırpılıp OCR'a öyle veriliyor -- kutunun sağ kenarı son
# karaktere birkaç piksel yakınsa o karakter OCR'a hiç ulaşmadan kırpılabilir.
# Bu durumda OCR gördüğü (eksik) karakterlerin hepsini yine de yüksek güvenle
# okur -- düşük güven eşiği bunu YAKALAYAMAZ, çünkü ortada "zayıf okunan" bir
# karakter yok, sadece hiç GÖRÜLMEMİŞ bir karakter var.
#
# Karakter kırpılması (SONDAN eksik okuma), OCR'ın var olmayan bir karakteri
# UYDURMASINDAN çok daha yaygın bir hata sınıfıdır -- bu yüzden aynı oturumda
# hem kısa hem de TAM OLARAK sonuna bir karakter eklenmiş uzun bir varyant
# görüldüyse ve kısa varyant EZİCİ bir çoğunlukla kazanmıyorsa (yani uzun
# varyant da göz ardı edilemeyecek kadar oy aldıysa), daha uzun varyant
# tercih edilir. Kısa varyant ezici çoğunluktaysa (örn. 10 karede 9 kez kısa,
# 1 kez uzun) bu YİNE DE geçersiz kılınmaz -- gerçekten farklı (daha kısa) bir
# plaka olma ihtimaline karşı çoğunluk oyu korunur.
SONDAN_EKSIK_KARAKTER_TERCIH_ORANI = 0.34  # uzun varyant, kısa varyantın en az bu oranı kadar oy aldıysa "yakın çağrı" sayılır

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
    boyunca toplanan OCR okumalarını ağırlıklı oyla birleştirir.

    NOT (2026-09-17): `farkli_okuma_sayisi` (len(self.oylar)) bu oturumda
    görülen FARKLI plaka METİN VARYANTLARININ sayısıdır -- aynı doğru metnin
    3 farklı karede tekrar tekrar okunması bunu ARTIRMAZ (hepsi aynı Counter
    anahtarına yığılır). Bir okumanın kaç FARKLI KAREDEN geldiğini (yani
    gerçekten "birden fazla kare tarafından doğrulandı mı" sorusunun cevabını)
    öğrenmek için ayrıca `toplam_kare_sayisi` tutulur -- bu, oturuma kaç kez
    `ekle()` çağrıldığının (+ ilk okuma) TOPLAMIDIR, metin farklı olsa da olsun.
    Panelde "tek bir karede görülüp hiç doğrulanmamış" okumaları (bkz.
    camera_reader.py::_kareyi_isle'deki kullanım ve README.md'deki ilgili not)
    ayırt etmek için eklendi.

    NOT (2026-09-18, düzeltme): `kazanan()`'ın döndürdüğü "guven" DEĞERİ artık
    KAZANAN metin varyantının KENDİ okumaları arasındaki en yüksek güvendir --
    ÖNCEDEN bu oturumda görülen TÜM varyantlar arasındaki (kazanan metinle
    hiç ilgisi olmayabilecek) global en yüksek güvendi. Bu, ciddi bir yanlış
    izlenim kaynağıydı: azınlıkta kalan (ve oylamayı kaybeden) hatalı bir
    okumanın rastgele yüksek güvenli olması, panelde KAZANAN (doğru olabilecek)
    okumanın güvenmiş gibi GÖSTERİLMESİNE yol açabiliyordu -- güven artık
    her zaman gerçekten kaydedilen metne aittir."""

    __slots__ = (
        "oylar", "_varyant_maks_guven", "ilk_gorulme", "son_gorulme",
        "en_iyi_jpeg", "_en_iyi_jpeg_guveni", "toplam_kare_sayisi",
    )

    def __init__(self, plaka: str, guven: float, simdi: float, jpeg: Optional[bytes] = None):
        self.oylar: "Counter[str]" = Counter({plaka: guven})
        self._varyant_maks_guven: dict[str, float] = {plaka: guven}
        self.ilk_gorulme = simdi
        self.son_gorulme = simdi
        self.en_iyi_jpeg = jpeg
        self._en_iyi_jpeg_guveni = guven
        self.toplam_kare_sayisi = 1

    def ekle(self, plaka: str, guven: float, simdi: float, jpeg: Optional[bytes] = None) -> None:
        self.oylar[plaka] += guven
        if guven > self._varyant_maks_guven.get(plaka, -1.0):
            self._varyant_maks_guven[plaka] = guven
        self.son_gorulme = simdi
        self.toplam_kare_sayisi += 1
        if jpeg is not None and guven >= self._en_iyi_jpeg_guveni:
            self._en_iyi_jpeg_guveni = guven
            self.en_iyi_jpeg = jpeg
        elif guven > self._en_iyi_jpeg_guveni:
            self._en_iyi_jpeg_guveni = guven

    def kazanan(self) -> dict:
        sirali = self.oylar.most_common()
        secilen_plaka, _agirlik = sirali[0]
        uzun_varyant_tercih_edildi = False

        # SONDAN KARAKTER EKSİK düzeltmesi: yalnızca en yüksek oylu İKİ varyant
        # karşılaştırılır (üçüncü/dördüncü sıradaki varyantlar zaten oydaşmayı
        # anlamlı biçimde etkileyemeyecek kadar azınlıktadır).
        if len(sirali) > 1:
            ilk_plaka, ilk_agirlik = sirali[0]
            ikinci_plaka, ikinci_agirlik = sirali[1]
            uzun, kisa = (
                (ikinci_plaka, ilk_plaka) if len(ikinci_plaka) > len(ilk_plaka) else (ilk_plaka, ikinci_plaka)
            )
            if (
                uzun != kisa
                and sondan_bir_karakter_eksik_mi(kisa, uzun)
                and ilk_plaka == kisa  # kısa (muhtemelen kırpılmış) varyant şu an "kazanıyor"
                and ikinci_agirlik >= ilk_agirlik * SONDAN_EKSIK_KARAKTER_TERCIH_ORANI
            ):
                secilen_plaka = uzun
                uzun_varyant_tercih_edildi = True
                logger.info(
                    "Oturum kazananı 'sondan karakter eksik' düzeltmesiyle değişti: "
                    "'%s' (oy=%.2f) yerine '%s' (oy=%.2f) seçildi -- fast_alpr'ın "
                    "kutuyu kenar boşluksuz kırpması OCR'ın son karakteri hiç "
                    "görmemesine yol açabilir (bkz. README.md'deki 2026-09-18 notu).",
                    kisa, ilk_agirlik, uzun, ikinci_agirlik,
                )

        return {
            "plaka": secilen_plaka,
            "guven": self._varyant_maks_guven[secilen_plaka],
            "farkli_okuma_sayisi": len(self.oylar),
            "toplam_oy": round(sum(self.oylar.values()), 3),
            "toplam_kare_sayisi": self.toplam_kare_sayisi,
            "jpeg": self.en_iyi_jpeg,
            "uzun_varyant_tercih_edildi": uzun_varyant_tercih_edildi,
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
        """Kapanmış oturumların kazananlarını döner -- her sözlüğe ayrıca bir
        `kapanma_nedeni` alanı eklenir ("sessizlik" | "max_sure" | "zorla"),
        çünkü ÇAĞIRAN taraf (bkz. KameraPipeline._kareyi_isle'deki
        "_suregelen_plakalar" mantığı) bunlara AYNI şekilde davranamaz:
        "sessizlik" aracın kareden GERÇEKTEN ayrıldığı anlamına gelir; "max_sure"
        ise araç HÂLÂ kareden ayrılmamışken yalnızca güvenlik amaçlı süre sınırı
        yüzünden zorla kapatıldığı anlamına gelir (bkz. 2026-09-24 notu,
        OTURUM_MAX_SURE_SN'in tanımlandığı yer) -- ikisini ayırt etmezsek,
        bariyerde bekleyen bir araç için her birkaç saniyede bir "yeni geçiş"
        kaydı üretilir.
        """
        bitmisler = []
        for anahtar in list(self._acik.keys()):
            birikim = self._acik[anahtar]
            sessiz_kaldi = simdi - birikim.son_gorulme > self.oturum_kapanma_sn
            cok_uzun_surdu = simdi - birikim.ilk_gorulme > self.max_oturum_sure_sn
            if zorla or sessiz_kaldi or cok_uzun_surdu:
                kazanan = birikim.kazanan()
                # Sıralama bilinçli: "sessizlik" (araç gerçekten ayrıldı) en
                # anlamlı/eyleme geçirilebilir sinyal olduğu için, ikisi aynı anda
                # doğru olsa bile önceliklidir; `zorla` (pipeline durduruluyor)
                # yalnızca ikisi de geçerli değilse etiket olarak kullanılır.
                kazanan["kapanma_nedeni"] = (
                    "sessizlik" if sessiz_kaldi else "max_sure" if cok_uzun_surdu else "zorla"
                )
                bitmisler.append(kazanan)
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


def _roi_pixel_sinirlarini_hesapla(roi: dict, genislik: int, yukseklik: int) -> tuple:
    """Yüzde (0-100, çözünürlükten bağımsız) cinsinden tanımlanmış bir ROI'yi
    VERİLEN karenin piksel boyutlarına göre piksel dikdörtgenine çevirir."""
    x1 = int(round(roi["x1"] / 100.0 * genislik))
    y1 = int(round(roi["y1"] / 100.0 * yukseklik))
    x2 = int(round(roi["x2"] / 100.0 * genislik))
    y2 = int(round(roi["y2"] / 100.0 * yukseklik))
    return x1, y1, x2, y2


def _kutu_roi_icinde_mi(kutu, roi_piksel: tuple) -> bool:
    """Bir tespit kutusunun MERKEZ noktası ROI dikdörtgeninin içinde mi?

    Kutunun tamamının içeride olması ŞART koşulmuyor -- bir araç/plaka ROI
    sınırına yakın durursa kutu kısmen dışarı taşabilir; bu durumda bile
    aracın "gerçekten o şeritte" olduğunu merkez noktası daha güvenilir
    yansıtır."""
    if not kutu:
        return False
    x1, y1, x2, y2 = kutu
    merkez_x = (x1 + x2) / 2
    merkez_y = (y1 + y2) / 2
    rx1, ry1, rx2, ry2 = roi_piksel
    return rx1 <= merkez_x <= rx2 and ry1 <= merkez_y <= ry2


def _roi_polygon_pixel_noktalarini_hesapla(roi: dict, genislik: int, yukseklik: int) -> list:
    """Yüzde cinsinden tanımlı SERBEST ÇİZİM (polygon) ROI noktalarını
    VERİLEN karenin piksel boyutlarına göre piksel noktalarına çevirir.

    NEDEN GEREKLİ (2026-09-20): dikdörtgen ROI (bkz. yukarıdaki
    `_roi_pixel_sinirlarini_hesapla`) her zaman yeterli değil -- kullanıcının
    kendi ifadesiyle "kare seçimde bazen farklı yönden geçen araçları da
    tespit ediyor". Bir şerit çapraz/eğik açıdan görüntüleniyorsa dikdörtgen
    komşu şeridi de kapsayabilir; serbest çizilmiş (3+ köşeli) bir çokgen,
    şeridin gerçek hattını takip ederek bu sızıntıyı engeller."""
    return [
        (int(round(n["x"] / 100.0 * genislik)), int(round(n["y"] / 100.0 * yukseklik)))
        for n in roi["noktalar"]
    ]


def _kutu_polygon_icinde_mi(kutu, poligon_piksel: list) -> bool:
    """`_kutu_roi_icinde_mi`nin polygon karşılığı: bir tespit kutusunun MERKEZ
    noktası, verilen piksel köşe noktalarıyla tanımlı çokgenin içinde mi?

    Standart "ray casting" (ışın gönderip kaç kenarı kestiğini sayma)
    algoritması kullanılır -- ekstra bir kütüphane (örn. shapely) gerektirmez,
    yalnızca kenar sayısı kadar basit aritmetik işlem yapar."""
    if not kutu or not poligon_piksel or len(poligon_piksel) < 3:
        return False
    x1, y1, x2, y2 = kutu
    merkez_x = (x1 + x2) / 2
    merkez_y = (y1 + y2) / 2
    icinde = False
    n = len(poligon_piksel)
    j = n - 1
    for i in range(n):
        xi, yi = poligon_piksel[i]
        xj, yj = poligon_piksel[j]
        # yi/yj eşitliğinde bölme sıfıra gitmesin diye çok küçük bir epsilon
        # ekleniyor -- yatay bir kenarla tam çakışan sınır durumlarını
        # dengeler, pratikte sonucu etkilemez.
        if (yi > merkez_y) != (yj > merkez_y):
            kesisim_x = (xj - xi) * (merkez_y - yi) / (yj - yi + 1e-9) + xi
            if merkez_x < kesisim_x:
                icinde = not icinde
        j = i
    return icinde


def _roi_ciz_bilgisi_hesapla(roi: Optional[dict], genislik: int, yukseklik: int) -> Optional[tuple]:
    """Bir kameranın ROI'sini (dikdörtgen ya da serbest çizim/polygon), o anki
    karenin piksel boyutuna göre, oy-birikimi filtresinin ("bu tespit ROI
    içinde mi") kullanacağı tek bir piksel-şekli tanımına çevirir. Dönüş:
    `("dikdortgen", (x1,y1,x2,y2))`, `("polygon", [(x,y), ...])` ya da ROI
    tanımlı değilse `None`.

    NOT (2026-09-23): bu şekil ÖNCEDEN ayrıca canlı önizleme karesine (artık
    kaldırılan `_kare_uzerine_ciz`) çizmek için de kullanılıyordu; kullanıcı
    isteğiyle (bkz. `_kareyi_isle`'deki ilgili not) bu görsel çizim tamamen
    kaldırıldı -- fonksiyon adı hâlâ "ciz" içeriyor ama artık YALNIZCA filtre
    hesaplaması için kullanılıyor, hiçbir şey çizmiyor."""
    if not roi:
        return None
    if roi.get("tip") == "polygon":
        return "polygon", _roi_polygon_pixel_noktalarini_hesapla(roi, genislik, yukseklik)
    return "dikdortgen", _roi_pixel_sinirlarini_hesapla(roi, genislik, yukseklik)


def _kutu_roi_ciz_bilgisiyle_icinde_mi(kutu, roi_ciz_bilgisi: Optional[tuple]) -> bool:
    """`_roi_ciz_bilgisi_hesapla`'nın döndürdüğü birleşik (tip, şekil) ikilisine
    göre, tipe uygun içeride-mi testine (`_kutu_roi_icinde_mi` ya da
    `_kutu_polygon_icinde_mi`) yönlendirir."""
    if not roi_ciz_bilgisi:
        return False
    tip, sekil = roi_ciz_bilgisi
    if tip == "polygon":
        return _kutu_polygon_icinde_mi(kutu, sekil)
    return _kutu_roi_icinde_mi(kutu, sekil)


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

    ÖNEMLİ: Bu YALNIZCA dedektöre giden kareyi etkiler. Kaydedilen/panelde/canlı
    izlemede gösterilen görsel (bkz. çağıran koddaki `_kareyi_isle`'nin
    `cv2.imencode(".jpg", frame, ...)` satırı) HER ZAMAN orijinal, işlenmemiş
    kareden üretilir — yani bu ayar kayıtların görünümünü hiç değiştirmez,
    yalnızca tespit/OCR'ın gördüğü kareyi iyileştirir."""
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
                 min_guven_skoru: float = VARSAYILAN_MIN_GUVEN_SKORU,
                 roi: Optional[dict] = None):
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
        # TESPİT ALANI SINIRI (ROI, region of interest) -- yüzde (0-100,
        # çözünürlükten bağımsız) cinsinden ya {"x1","y1","x2","y2"} (dikdörtgen,
        # eski/varsayılan biçim) ya da {"tip": "polygon", "noktalar": [{"x","y"}, ...]}
        # (2026-09-20, serbest çizim -- bkz. `_roi_ciz_bilgisi_hesapla`) ya da None
        # (sınır yok, kare tamamı geçerli). Giriş ve çıkış kameralarının
        # açıları birbirinin şeridini de görüyorsa (bkz. README.md'deki
        # 2026-09-17 notu: aynı aracın hem giriş hem çıkış kamerasında art
        # arda görünmesi), her kamera için SADECE kendi şeridine denk gelen
        # bölge tanımlanarak komşu şeritteki araçların yanlışlıkla o kameranın
        # kaydına düşmesi engellenir. Dikdörtgen bir şerit çapraz/eğik açıdan
        # görüntülendiğinde komşu şeridi de kapsayabildiği için (kullanıcı
        # geri bildirimi: "kare seçimde bazen farklı yönden geçen araçları da
        # tespit ediyor"), serbest çizim biçimi şeridin gerçek hattını takip
        # edebilir.
        self.roi = roi

        self.motor = _paylasilan_motoru_al()
        self.calisiyor = False
        self.son_plaka_zamani: dict = {}
        # 2026-09-24: bir plaka, DAHA ÖNCE bildirilmiş, KESİNTİSİZ bir görünümün
        # (oturumun OTURUM_MAX_SURE_SN yüzünden zorla kapatılıp kapatılmadığına
        # bakılmaksızın araç kareden hiç ayrılmamışken) devamındaysa burada tutulur
        # -- bkz. `_kareyi_isle`'deki kullanım ve `_suregelen_plakalari_buda`'nın
        # docstring'i (kök neden: "bu plakayı neden 3 dakika içinde 3 defa
        # çekmiş" kullanıcı geri bildirimi). Değer = plakanın en son bir kapanış
        # olayıyla (max_sure ya da henüz kapanmamış sessizlik) görüldüğü zaman.
        self._suregelen_plakalar: dict = {}
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

        # Son (temiz, işaretlenmemiş) kare -- /kameralar/{id}/goruntu ve
        # /kameralar/{id}/akis için (bkz. _kareyi_isle'deki 2026-09-23 notu).
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
        # koşullarında tespit oranını artırmak için) — kaydedilen/panelde/canlı
        # izlemede gösterilen görsel her zaman `frame`'in KENDİSİNDEN, hiç
        # işaretlenmeden üretildiği için (aşağıdaki `cv2.imencode(".jpg", frame,
        # ...)`) bu, kayıtların görünümünü etkilemez.
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
                _etkin_model = getattr(self.motor, "dedektor_modeli_etkin", "bilinmiyor")
                logger.info(
                    "[%s] Son %.0f sn içinde dedektör %d karede hiçbir plaka adayı "
                    "bulamadı (OCR'a hiç ulaşmadan elendi). Bu her zaman normaldir "
                    "(trafiksiz an); ama net görünen bir araç yine de hiç kayda "
                    "düşmüyorsa önce dedektör eşiğini (şu an %.2f, kaynak: %s) "
                    "düşürmeyi deneyin: PTS_ANPR_DETECTOR_ESIGI işletim sistemi ortam "
                    "değişkenini ayarlayıp uygulamayı YENİ bir terminalden yeniden "
                    "başlatın — bu panelin 'Min. plaka tanıma güveni' ayarından FARKLI "
                    "bir eşiktir ve panelden değiştirilemez (bkz. anpr_engine.py). Eşiği "
                    "düşürmek yetmiyorsa (BÜYÜK/net/tam karşıdan görünen bir plaka bile "
                    "kaçıyorsa) asıl sorun eşik değil, dedektör modelinin giriş "
                    "çözünürlüğü olabilir (şu an: %s) — geniş/uzak çekimlerde tüm kare "
                    "küçük bir kareye sıkıştırıldığı için plaka fark edilmeyecek kadar "
                    "küçülüyor olabilir; PTS_ANPR_DETECTOR_MODEL=yolo-v9-s-608-license-"
                    "plate-end2end gibi daha yüksek çözünürlüklü bir modele geçmeyi "
                    "deneyin (bkz. README.md, anpr_engine.py::DEDEKTOR_MODELI_BILGILERI).",
                    self.kamera_id, BOS_TESPIT_LOG_ARALIK_SN, self._bos_tespit_sayaci_son_logdan_beri,
                    _etkin_esik, _esik_kaynagi, _etkin_model,
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

        # TESPİT ALANI SINIRI (ROI): kameraya bir ROI tanımlıysa (dikdörtgen ya
        # da 2026-09-20'den itibaren serbest çizim/polygon), kare boyutuna göre
        # piksel şeklini hesaplayıp her tespiti "alan içinde mi" diye işaretle.
        # Bu, SADECE aşağıdaki oy döngüsünde hangi tespitlerin oy birikimine
        # gireceğini belirlemek için kullanılır (ROI dışı tespitler filtrelenir)
        # -- artık kare üzerine GÖRSEL olarak ÇİZİLMİYOR, bkz. aşağıdaki not.
        roi_ciz_bilgisi = None
        if self.roi:
            yukseklik, genislik = frame.shape[:2]
            roi_ciz_bilgisi = _roi_ciz_bilgisi_hesapla(self.roi, genislik, yukseklik)
            for t in tespitler:
                t["roi_icinde"] = _kutu_roi_ciz_bilgisiyle_icinde_mi(t.get("kutu"), roi_ciz_bilgisi)

        # 2026-09-23 kullanıcı isteği: "kayıtlarda tespit alanı ROI, plaka alanı
        # ve % kaç ile okunduğu raporlara/son geçişlere eklenmesin, hatta canlı
        # izlemede bile görüntü kirliliği olmasın." ÖNCEDEN burada `frame`'in bir
        # KOPYASI üzerine (ROI sınır çizgisi + her tespit için bir kutu + "PLAKA
        # %XX" metni basılı) bir "annotated" (işaretlenmiş) kare üretiliyordu ve
        # bu TEK kare hem canlı önizleme akışına (`_son_goruntu_jpeg`, dolayısıyla
        # Canlı İzleme'ye VE `/kameralar/{id}/goruntu`'ya) HEM DE (aşağıdaki oy
        # birikimine geçirilerek) KAYDEDİLEN/panelde-gösterilen/rapor edilen
        # görsele dönüşüyordu -- yani hem canlı izlemede hem arşivlenen her araç
        # fotoğrafında bu teknik/hata-ayıklama bilgileri kalıcı olarak görünüyordu.
        # Artık kare HİÇ İŞARETLENMEDEN (temiz haliyle) JPEG'e kodlanıyor ve HEM
        # canlı önizleme HEM kayıt için aynı temiz kare kullanılıyor -- ROI'nin
        # KENDİSİ (yukarıdaki `roi_ciz_bilgisi`) hâlâ hesaplanıp tespit
        # filtrelemesinde kullanılıyor, yalnızca kare üzerine ÇİZİLMİYOR. Kamera
        # kurulumu sırasında ROI'yi tanımlamak için ayrı, İSTEĞE BAĞLI açılan bir
        # araç zaten var (bkz. index.html #kameraRoiModal / app.js::kameraRoiAc)
        # -- kullanıcının orada sürükleyerek çizdiği bölge tarayıcıda kendi SVG
        # katmanıyla gösteriliyor, kare üzerine sunucu tarafında hiçbir şey
        # basılmasına gerek yok.
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
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
            if self.roi and not t.get("roi_icinde", True):
                # GÖZLEMLENEBİLİRLİK: bu tespit format ve güven olarak geçerliydi
                # ama yapılandırılmış tespit alanının (ROI) DIŞINDA kaldığı için
                # oy birikimine hiç girmedi -- tipik olarak komşu şeridi de gören
                # bir kameranın, o şeritteki (asıl kendi şeridine ait olmayan)
                # bir aracı yanlışlıkla kaydetmesini önlemek içindir (bkz.
                # README.md'deki "giriş ve çıkış kameraları birbirinin şeridini
                # görüyor" notu). `min_guven_skoru` filtresiyle aynı gözlemlenebilirlik
                # ilkesini izler: sessizce elenmez, burada loglanır.
                logger.info(
                    "[%s] Tespit yapılandırılmış alan (ROI) dışında kaldı, oy "
                    "birikimine girmedi: %s (kutu=%s)",
                    self.kamera_id, t["plaka"], t.get("kutu"),
                )
                continue
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
            if not self._oturum_gonderilmeli_mi(oturum, simdi):
                continue
            plaka = oturum["plaka"]

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
                #
                # .strip(): GERÇEK ÜRETİMDE BULUNAN HATA (2026-09-21): kullanıcı
                # bu değişkeni Windows'ta ayarlarken (kopyala-yapıştır, `setx`
                # ile çok satırlı bir değer vb.) sona görünmez bir satır sonu
                # (\n) karakteri karışmıştı. `requests`, başlık (header)
                # değerinde satır sonu karakterini KABUL ETMEZ ve isteği hiç
                # GÖNDERMEDEN "Invalid leading whitespace, reserved
                # character(s)..." hatasıyla reddeder (bkz. aşağıdaki except
                # bloğu) -- yani anahtarın kendisi doğru olsa BİLE, sondaki bu
                # tek görünmez karakter yüzünden dedektörün gerçekten
                # doğruladığı HER plaka, panelde HİÇBİR iz bırakmadan (yalnızca
                # log dosyasında bir ERROR satırı olarak) sessizce kayboluyordu.
                # Artık .strip() ile bu sınıftaki hatalara karşı bağışıklık var.
                _kamera_anahtari = (os.getenv("PTS_KAMERA_ANAHTARI") or "").strip() or None
                _istek_basliklari = {"X-PTS-Kamera-Anahtari": _kamera_anahtari} if _kamera_anahtari else {}
                with open(gecici, "rb") as f:
                    yanit = requests.post(
                        self.api_url,
                        data={"plaka_no": plaka, "kamera_id": self.kamera_id,
                              "yon": self.yon, "guven_skoru": round(oturum["guven"], 3),
                              # PANELDE "TEK KAREDE GÖRÜLDÜ, HİÇ DOĞRULANMADI" AYRIMI
                              # İÇİN (bkz. PlakaOyBirikimi.toplam_kare_sayisi ve
                              # README.md'deki ilgili not): bu okumanın kaç farklı
                              # karede tekrarlandığı/oy aldığı da kayıtla birlikte
                              # gönderilir. 1 ise operatör panelde bunu görüp o
                              # kayda özellikle dikkat edebilir (ör. "39 SU 877"nin
                              # tek bir karede "04 SD 377" olarak yanlış okunup
                              # başka hiçbir karede doğrulanmadan kaydolduğu vaka).
                              "dogrulama_kare_sayisi": oturum.get("toplam_kare_sayisi"),
                              # ŞEFFAFLIK (2026-09-18): bu oturumda kaç FARKLI metin
                              # varyantı önerildiği de kayıtla birlikte gönderilir --
                              # 1 ise tüm kareler AYNI metinde birleşti (gerçek
                              # oydaşma); 1'den büyükse kazanan, azınlıkta kalan en
                              # az bir farklı okumaya rağmen seçildi demektir. Panel
                              # artık bunu "✓ N kare" yerine "⚠ N kare (çelişkili)"
                              # olarak ayrıca işaretler (bkz. README.md'deki ilgili
                              # not) -- önceden bu bilgi yalnızca log satırına
                              # yazılıp kayıtla birlikte SAKLANMIYORDU.
                              "farkli_okuma_sayisi": oturum.get("farkli_okuma_sayisi")},
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

    def _oturum_gonderilmeli_mi(self, oturum: dict, simdi: float) -> bool:
        """Kapanmış bir oturumun (bkz. PlakaOturumTakipcisi.bitmis_oturumlari_al)
        gerçekten YENİ bir Kayit olarak API'ye gönderilip gönderilmeyeceğine
        karar verir; kararla tutarlı biçimde `self._suregelen_plakalar` ve
        `self.son_plaka_zamani`yı da günceller (bu yüzden saf/yan etkisiz bir
        fonksiyon DEĞİLDİR -- her kapanmış oturum için TAM OLARAK BİR kez,
        sırayla çağrılmalıdır).

        2026-09-24 KÖK NEDEN DÜZELTMESİ (kullanıcı geri bildirimi: "bu plakayı
        neden 3 dakika içinde 3 defa çekmiş" -- bir araç bariyerde/nöbetçi
        kontrolünde birkaç dakika beklerse, ESKİ kod her ~tekrar_gecikme_sn'de
        (varsayılan 30 sn) bir "yeni geçiş" kaydı üretiyordu, çünkü
        OTURUM_MAX_SURE_SN (8 sn) her seferinde oturumu -- araç kareden hiç
        ayrılmamışken -- zorla kapatıp yeni bir "kazanan" döndürüyordu.
        Aşağıdaki ayrım, "araç hâlâ orada duruyor" (max_sure) ile "araç
        gerçekten gitti" (sessizlik) durumlarını birbirinden ayırır."""
        plaka = oturum["plaka"]
        kapanma_nedeni = oturum.get("kapanma_nedeni")

        if kapanma_nedeni == "max_sure":
            # Araç HÂLÂ kareden ayrılmadı. Bu plaka için bu KESİNTİSİZ
            # görünüm boyunca DAHA ÖNCE zaten bir kayıt gönderildiyse
            # (_suregelen_plakalar'da varsa), bu yalnızca aynı aracın
            # kamerada beklemeye devam etmesidir -- YENİ bir geçiş değil,
            # sessizce atla (zaman damgasını TAZELE ki `_suregelen_plakalari_buda`
            # onu erken silmesin).
            if plaka in self._suregelen_plakalar:
                self._suregelen_plakalar[plaka] = simdi
                return False
            self._suregelen_plakalar[plaka] = simdi
        else:
            # "sessizlik" (araç GERÇEKTEN kareden ayrıldı) ya da "zorla"
            # (pipeline durduruluyor, elimizdeki en iyi tahmini kaybetmeyelim).
            # Bu plaka DAHA ÖNCE (bir max_sure kapanışıyla) zaten bildirildiyse,
            # bunu "akış bitti" olarak işaretleyip (aracın BİR SONRAKİ, gerçekten
            # ayrı görünüşü yeniden yeni bir geçiş sayılabilsin diye) devamında
            # ikinci bir kayıt OLUŞTURMA -- oylar zaten ilk kayıtta gönderilmişti.
            daha_once_bu_akis_icin_bildirilmis = self._suregelen_plakalar.pop(plaka, None) is not None
            if kapanma_nedeni == "sessizlik" and daha_once_bu_akis_icin_bildirilmis:
                return False

        if (plaka in self.son_plaka_zamani and
                simdi - self.son_plaka_zamani[plaka] < self.tekrar_gecikme_sn):
            return False
        self.son_plaka_zamani[plaka] = simdi
        return True

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
        """son_plaka_zamani sözlüğü süresiz büyümesin diye eski girdileri temizler
        -- ve `_suregelen_plakalar`ı da (bkz. `_suregelen_plakalari_buda`'nın
        docstring'i) güvenlik amaçlı zaman aşımıyla budar."""
        if len(self.son_plaka_zamani) >= 200:
            esik = time.time() - (self.tekrar_gecikme_sn * _PLAKA_HAFIZA_CARPANI)
            eskiler = [p for p, t in self.son_plaka_zamani.items() if t < esik]
            for p in eskiler:
                self.son_plaka_zamani.pop(p, None)
        self._suregelen_plakalari_buda()

    def _suregelen_plakalari_buda(self) -> None:
        """`_suregelen_plakalar` içindeki bir plaka -- normalde, aracın kareden
        GERÇEKTEN ayrıldığı 'sessizlik' kapanışında zaten temizlenir (bkz.
        `_kareyi_isle`) -- eğer `_SUREGELEN_PLAKA_ZAMAN_ASIMI_SN` boyunca HİÇBİR
        kapanış olayıyla (ne 'max_sure' ne 'sessizlik') tazelenmediyse burada da
        GÜVENLİK AMAÇLI temizlenir.

        NEDEN GEREKLİ: bir araç, tam bir 'max_sure' kapanışından HEMEN sonra --
        yeni bir oturum hiç açılmadan -- kareden ayrılırsa, o plaka için bir daha
        HİÇBİR kapanış olayı (dolayısıyla 'sessizlik' temizliği) oluşmaz, çünkü
        PlakaOturumTakipcisi yalnızca AÇIK bir oturumu kapatabilir, hiç açılmamış
        birini değil. Bu zaman aşımı olmasaydı, o plaka `_suregelen_plakalar`'da
        SONSUZA KADAR takılı kalır ve aracın GERÇEKTEN AYRI, meşru bir sonraki
        gelişi sessizce hiç kaydedilmezdi -- tam da bu depoda özenle kaçınılan
        "sessiz kayıp" hata sınıfının bir örneği olurdu."""
        if not self._suregelen_plakalar:
            return
        esik = time.time() - _SUREGELEN_PLAKA_ZAMAN_ASIMI_SN
        eskiler = [p for p, t in self._suregelen_plakalar.items() if t < esik]
        for p in eskiler:
            self._suregelen_plakalar.pop(p, None)

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


def toplu_dogruluk_testi(klasor: str, min_guven_skoru: float = VARSAYILAN_MIN_GUVEN_SKORU,
                          kontrast_iyilestir: bool = False) -> dict:
    """Etiketli bir fotoğraf klasörü üzerinde ANPR motorunun doğruluğunu ÖLÇER.

    CANLI SİSTEME HİÇBİR YAN ETKİSİ YOKTUR: API'ye kayıt POST ETMEZ,
    veritabanına dokunmaz, oturum/konsensüs mantığını çalıştırmaz -- yalnızca
    motor.tahmin_et() ile doğrudan çıkarım yapar (bkz. _kareyi_isle'nin aksine
    burada API çağrısı YOK). Bu yüzden PTS_ANPR_DETECTOR_ESIGI,
    PTS_ANPR_DETECTOR_MODEL veya bu fonksiyonun kendi min_guven_skoru/
    kontrast_iyilestir parametrelerini üretim sistemini hiç etkilemeden,
    GERÇEK geçmiş fotoğraflar üzerinde sayısal olarak karşılaştırmak için
    kullanılabilir (örn. "eşiği 0.25 yapınca kaç tanesi artık doğru okunuyor?").

    Klasördeki dosyalar Dahua NVR'ın ANPR olay listesinden dışa aktarılan
    fotoğraflarla AYNI adlandırma biçiminde olmalı: "ONEK_PLAKA.jpg" (örn.
    "20260917130536_34MRU796.jpg" -- dosya adının SON "_" ile ayrılmış parçası
    gerçek/etiketli plaka olarak okunur). Aynı klasörde bulunabilecek
    "..._plate.jpg" kırpılmış plaka görselleri OTOMATİK ATLANIR: bunlar
    dedektörün asıl işini (geniş bir sahnenin İÇİNDE plakayı BULMASINI) test
    etmez, çünkü plaka zaten kırpılmış görselin neredeyse tamamını kaplar --
    bu tam olarak PTS'nin sahada yaşadığı sorun (plaka insan gözüne büyük
    görünse de, kameranın TÜM sahnesi küçük bir kareye sıkıştırıldığında
    dedektöre görünmez hale gelmesi) değildir. Dosya adından geçerli bir Türk
    plaka formatı çıkarılamazsa (örn. "..._Unlicensed.jpg") o dosya
    "etiketlenemedi" sayılır ve doğruluk oranına hiç katılmaz.

    Döndürülen sözlük:
      toplam, dogru, yanlis, esik_altinda, tespit_edilemedi, gorsel_okunamadi,
      hata, etiketlenemedi, dogruluk_orani (yalnızca ETİKETLİ dosyalar
      üzerinden: dogru / (toplam - etiketlenemedi); etiketli hiç dosya yoksa
      None), detaylar (her dosya için {"dosya", "gercek_plaka", "sonuc",
      "okunan_plaka", "guven", "kare_boyutu"}).

    GÖZLEMLENEBİLİRLİK (2026-09-17 eklendi): "tespit_edilemedi" ile "görsel
    hiç okunamadı" (bozuk dosya/desteklenmeyen format) ve "motor çağrısı
    hata fırlattı" durumları BİLEREK AYRI kategoriler olarak raporlanır --
    hepsi tek bir "tespit_edilemedi" altında toplanırsa, gerçekten dedektörün
    hiçbir aday bulamadığı durum ile dosyanın hiç işlenemediği durum
    birbirinden ayırt edilemez ve yanlış sonuca varılabilir (örn. "model
    değiştirince de hâlâ 0 tespit" aslında "dosyalar hiç okunamıyor"
    anlamına gelebilir). Her dosya için ayrıca uygulama logunda (INFO
    seviyesinde) hangi kategoriye düştüğü ve varsa kare boyutu loglanır.
    """
    if not KUTUPHANELER_MEVCUT:
        raise RuntimeError(
            "Gerekli kütüphaneler kurulu değil. "
            "Kurulum: pip install \"fast-alpr[onnx]\" opencv-python"
        )
    if not os.path.isdir(klasor):
        raise ValueError(f"Klasör bulunamadı: {klasor}")

    motor = _paylasilan_motoru_al()
    etkin_model = getattr(motor, "dedektor_modeli_etkin", "bilinmiyor")
    etkin_esik = getattr(motor, "detektor_esigi_etkin", "bilinmiyor")
    logger.info(
        "toplu_dogruluk_testi başlıyor: klasor=%r, min_guven_skoru=%.3f, "
        "kontrast_iyilestir=%s, dedektör modeli=%s, dedektör eşiği=%s",
        klasor, min_guven_skoru, kontrast_iyilestir, etkin_model, etkin_esik,
    )
    sayaclar = {
        "dogru": 0, "yanlis": 0, "esik_altinda": 0, "tespit_edilemedi": 0,
        "gorsel_okunamadi": 0, "hata": 0, "etiketlenemedi": 0,
    }
    detaylar: list[dict] = []

    dosyalar = sorted(
        ad for ad in os.listdir(klasor)
        if ad.lower().endswith(KlasorIzleyici.DESTEKLENEN_UZANTILAR)
        and not os.path.splitext(ad)[0].lower().endswith("_plate")
    )

    for dosya in dosyalar:
        govde = os.path.splitext(dosya)[0]
        ham_plaka = govde.rsplit("_", 1)[-1] if "_" in govde else govde
        gercek_plaka = plaka_dogrula(ham_plaka)
        if gercek_plaka is None:
            sayaclar["etiketlenemedi"] += 1
            detaylar.append({
                "dosya": dosya, "gercek_plaka": None, "sonuc": "etiketlenemedi",
                "okunan_plaka": None, "guven": None, "kare_boyutu": None,
            })
            logger.info("toplu_dogruluk_testi[%s]: etiketlenemedi (dosya adından geçerli plaka çıkarılamadı)", dosya)
            continue

        frame = cv2.imread(os.path.join(klasor, dosya))
        if frame is None:
            sayaclar["gorsel_okunamadi"] += 1
            detaylar.append({
                "dosya": dosya, "gercek_plaka": gercek_plaka, "sonuc": "gorsel_okunamadi",
                "okunan_plaka": None, "guven": None, "kare_boyutu": None,
            })
            logger.warning(
                "toplu_dogruluk_testi[%s]: GÖRSEL OKUNAMADI (cv2.imread None döndü -- "
                "dosya bozuk, desteklenmeyen format veya yol/izin sorunu olabilir)",
                dosya,
            )
            continue

        kare_boyutu = f"{frame.shape[1]}x{frame.shape[0]}"
        try:
            dedektore_giden = _kontrast_iyilestirmesi_uygula(frame) if kontrast_iyilestir else frame
            with _motor_cagri_kilit:
                tespitler = motor.tahmin_et(dedektore_giden)
        except Exception as exc:
            sayaclar["hata"] += 1
            detaylar.append({
                "dosya": dosya, "gercek_plaka": gercek_plaka, "sonuc": "hata",
                "okunan_plaka": None, "guven": None, "kare_boyutu": kare_boyutu, "hata_mesaji": str(exc),
            })
            logger.exception("toplu_dogruluk_testi[%s]: motor çağrısı sırasında beklenmeyen hata", dosya)
            continue

        if not tespitler:
            sayaclar["tespit_edilemedi"] += 1
            detaylar.append({
                "dosya": dosya, "gercek_plaka": gercek_plaka, "sonuc": "tespit_edilemedi",
                "okunan_plaka": None, "guven": None, "kare_boyutu": kare_boyutu,
            })
            logger.info(
                "toplu_dogruluk_testi[%s]: tespit_edilemedi (kare boyutu=%s, dedektör hiçbir aday bulamadı)",
                dosya, kare_boyutu,
            )
            continue

        # Birden fazla aday varsa en yüksek güvenli olanı al -- canlı sistemdeki
        # PlakaOturumTakipcisi çok kareli oy birleştirmesinin tek-kare hali;
        # burada zaman içinde birikim yapılmadığı için oylamaya gerek yok.
        en_iyi = max(tespitler, key=lambda t: t.guven_skoru)
        okunan_plaka = plaka_dogrula(en_iyi.plaka_no)

        if en_iyi.guven_skoru < min_guven_skoru:
            sonuc = "esik_altinda"
        elif okunan_plaka == gercek_plaka:
            sonuc = "dogru"
        else:
            sonuc = "yanlis"
        sayaclar[sonuc] += 1
        detaylar.append({
            "dosya": dosya, "gercek_plaka": gercek_plaka, "sonuc": sonuc,
            "okunan_plaka": okunan_plaka or en_iyi.plaka_no, "guven": round(en_iyi.guven_skoru, 3),
            "kare_boyutu": kare_boyutu,
        })
        logger.info(
            "toplu_dogruluk_testi[%s]: %s (gerçek=%s, okunan=%s, güven=%.3f, kare boyutu=%s)",
            dosya, sonuc, gercek_plaka, okunan_plaka or en_iyi.plaka_no, en_iyi.guven_skoru, kare_boyutu,
        )

    etiketli_toplam = len(dosyalar) - sayaclar["etiketlenemedi"]
    dogruluk_orani = round(sayaclar["dogru"] / etiketli_toplam, 3) if etiketli_toplam else None
    logger.info(
        "toplu_dogruluk_testi bitti: toplam=%d, dogruluk_orani=%s, sayaclar=%s",
        len(dosyalar), dogruluk_orani, sayaclar,
    )

    return {
        "toplam": len(dosyalar),
        **sayaclar,
        "dogruluk_orani": dogruluk_orani,
        "detaylar": detaylar,
    }
