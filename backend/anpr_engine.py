"""Pluggable ANPR engine for the PTS camera pipeline.

FastALPR is the preferred open-source backend when installed. The adapter keeps
the camera service independent from a particular detector or OCR implementation.
"""
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

# FastALPR kütüphanesinin resmi API referansında belgelenen, PTS_ANPR_DETECTOR_ESIGI
# ayarlanmadığında kullanılan sabit varsayılan. Yalnızca günlük mesajlarında ve
# /sistem/saglik gibi teşhis uçlarında "etkin eşik hangi kaynaktan geldi" bilgisini
# doğru raporlayabilmek için burada, tek bir yerde tanımlanır.
DEDEKTOR_ESIGI_KUTUPHANE_VARSAYILANI = 0.4

# open_image_models projesinin (fast_alpr'ın dedektörü buradan gelir) yayınladığı
# TÜM plaka dedektörü modelleri — hepsi kütüphane zaten içindeyken (ayrı bir
# "GitHub'dan entegrasyon" gerektirmeden) sadece isim değiştirerek seçilebilir.
# Kaynak: https://github.com/ankandrew/open-image-models (2026-09 itibarıyla).
# recall = gerçekte var olan plakaların kaçırılmadan tespit edilme oranı; PTS'nin
# yaşadığı "net görünen araç hiç kayda düşmüyor" şikayeti tam olarak recall
# sorunudur (yanlış pozitif değil, kaçırma). İsim = giriş görüntüsünün YOLO'ya
# verilmeden önce KARENİN TAMAMININ resize edildiği kare boyutu (256-640 px) —
# yani kamera 1920x1080 gibi geniş bir kare üretiyorsa, küçük bir model (256/384)
# tüm sahneyi bu kadar küçük bir kareye sıkıştırır ve plaka -özellikle uzak/yan
# çekimde- birkaç piksele düşüp dedektöre görünmez hale gelebilir; bu PTS'de
# gözlemlenen "büyük, net, tam karşıdan görünen plaka bile kaçıyor" durumunun en
# olası açıklamasıdır. Büyük model = daha fazla piksel = daha iyi recall, ama
# biraz daha yavaş çıkarım.
#   isim                                    boyut  precision  recall  mAP50  mAP50-95
DEDEKTOR_MODELI_BILGILERI: dict[str, dict] = {
    "yolo-v9-t-256-license-plate-end2end": {"boyut": 256, "recall": 0.797, "mAP50": 0.858},
    "yolo-v9-t-384-license-plate-end2end": {"boyut": 384, "recall": 0.863, "mAP50": 0.920},
    "yolo-v9-t-416-license-plate-end2end": {"boyut": 416, "recall": 0.894, "mAP50": 0.940},
    "yolo-v9-t-512-license-plate-end2end": {"boyut": 512, "recall": 0.901, "mAP50": 0.948},
    "yolo-v9-t-640-license-plate-end2end": {"boyut": 640, "recall": 0.896, "mAP50": 0.958},
    "yolo-v9-s-608-license-plate-end2end": {"boyut": 608, "recall": 0.917, "mAP50": 0.966},
}
DEDEKTOR_MODELI_VARSAYILAN = "yolo-v9-t-384-license-plate-end2end"


@dataclass
class PlakaSonucu:
    plaka_no: str
    guven_skoru: float
    kutu: Optional[tuple[int, int, int, int]] = None


class ANPREngine:
    def __init__(self, detector_model: str = DEDEKTOR_MODELI_VARSAYILAN, ocr_model: str = "cct-xs-v2-global-model"):
        # PTS_ANPR_DETECTOR_MODEL ortam değişkeni, yapıcıya (constructor) verilen
        # değeri geçersiz kılar — tıpkı aşağıdaki PTS_ANPR_DETECTOR_ESIGI gibi,
        # panelden DEĞİL, ortam değişkeniyle ayarlanır ve yalnızca açılışta okunur.
        # Bilinmeyen bir isim verilirse (yazım hatası gibi) uyarı loglanır ama
        # yine de fast_alpr'a olduğu gibi geçirilir — kütüphane yeni modeller
        # eklerse burayı güncellemeden de kullanılabilsin.
        dedektor_modeli_ortam = os.environ.get("PTS_ANPR_DETECTOR_MODEL", "").strip()
        dedektor_modeli_kaynagi = "yapıcı/kütüphane varsayılanı"
        if dedektor_modeli_ortam:
            if dedektor_modeli_ortam not in DEDEKTOR_MODELI_BILGILERI:
                logger.warning(
                    "PTS_ANPR_DETECTOR_MODEL=%r bilinen model listesinde yok "
                    "(bkz. anpr_engine.py::DEDEKTOR_MODELI_BILGILERI) — yine de "
                    "olduğu gibi fast_alpr'a geçiriliyor; isimde yazım hatası "
                    "olmadığından emin olun.",
                    dedektor_modeli_ortam,
                )
            detector_model = dedektor_modeli_ortam
            dedektor_modeli_kaynagi = "PTS_ANPR_DETECTOR_MODEL ortam değişkeni"
        self.dedektor_modeli_etkin = detector_model
        self.dedektor_modeli_kaynagi = dedektor_modeli_kaynagi
        logger.info(
            "ANPR dedektör modeli = %s — kaynak: %s%s",
            detector_model, dedektor_modeli_kaynagi,
            f" (giriş boyutu: {DEDEKTOR_MODELI_BILGILERI[detector_model]['boyut']}px, "
            f"beklenen recall: {DEDEKTOR_MODELI_BILGILERI[detector_model]['recall']:.3f})"
            if detector_model in DEDEKTOR_MODELI_BILGILERI else "",
        )
        try:
            from fast_alpr import ALPR
        except ImportError as exc:
            raise RuntimeError("FastALPR kurulu değil. Kurulum: pip install fast-alpr[onnx]") from exc
        ek_parametreler: dict = {}
        # PTS_ANPR_PROVIDERS=cpu ortam değişkeni GPU hızlandırmasını (DirectML/CUDA)
        # tamamen devre dışı bırakır. Bazı GPU sürücüleri, aynı anda birden fazla
        # kamera GPU üzerinde çıkarım yaptığında kararsızlaşabiliyor (gözlemlenen
        # semptom: onnxruntime "DXGI_ERROR_DEVICE_HUNG" / "GPU başka komutlara
        # yanıt vermeyecek" hatası verip GPU sürücüsünün sıfırlanması, bu da bazı
        # sistemlerde tüm bilgisayarın donup kendini yeniden başlatmasına yol açar).
        # camera_reader.py artık tüm kameralar arasında TEK bir ANPREngine paylaşıp
        # çağrıları serileştiriyor (bkz. `_paylasilan_motoru_al`), bu riski büyük
        # ölçüde azaltır; ama sürücü/donanım hâlâ kararsızsa bu değişkenle CPU'ya
        # tamamen zorlanabilir (birkaç kamera için tipik olarak yeterince hızlıdır).
        if os.environ.get("PTS_ANPR_PROVIDERS", "").strip().lower() in ("cpu", "cpu_only", "cpu-only"):
            ek_parametreler["detector_providers"] = ["CPUExecutionProvider"]
            ek_parametreler["ocr_providers"] = ["CPUExecutionProvider"]
            ek_parametreler["ocr_device"] = "cpu"
        # ------------------------------------------------------------------
        # DEDEKTÖR GÜVEN EŞİĞİ (detector_conf_thresh) — camera_reader.py'deki
        # min_guven_skoru'ndan (OCR sonrası, bizim kendi filtremiz) TAMAMEN
        # AYRI ve ondan ÖNCE devreye giren bir eşiktir: FastALPR'ın kendi YOLO
        # tabanlı plaka DEDEKTÖRÜ, bu eşiğin altında kalan kutuları OCR'a hiç
        # göndermeden eler; ALPR.predict() o kareler için doğrudan BOŞ liste
        # döner. Bu, kütüphanenin resmi API referansında varsayılanı 0.4
        # olarak belgelenmiş bir parametredir ve önceki kod tabanında HİÇ
        # açığa çıkarılmıyordu (üstü örtülü, sabit 0.4).
        #
        # Neden önemli: "araç kamerada net/okunaklı görünüyor ama sistemde HİÇ
        # iz bırakmadan kayboluyor" şikayetlerinin bir kısmı, bizim kendi
        # loglarımızın (format uyuşmazlığı / düşük OCR güveni / API reddi —
        # bkz. camera_reader.py) hiçbirine düşmüyordu; çünkü bu üç log noktası
        # da yalnızca ALPR.predict()'in DÖNDÜRDÜĞÜ sonuçlar üzerinde çalışır.
        # Dedektör bir kareyi kendi iç eşiğinde elediğinde, o kare bizim
        # kodumuza hiç ulaşmıyor — dolayısıyla hiçbir log satırı üretilmiyordu.
        # (camera_reader.py'deki "boş tespit" loglaması bu görünmez durumu
        # ortaya çıkarmak için eklenmiştir.)
        #
        # Aynı kameradan aynı anda okuma yapabilen FARKLI bir yazılımın
        # (başka bir dedektör modeli/eşiğiyle) başarılı olması, bu değerin
        # BİZİM özel kamera açı/mesafe/aydınlatma koşullarımız için çok katı
        # olabileceğine işaret eder. PTS_ANPR_DETECTOR_ESIGI ortam değişkeniyle
        # (0.0-1.0 arası) düşürülebilir; örn. PTS_ANPR_DETECTOR_ESIGI=0.15.
        # Belirtilmezse kütüphanenin kendi varsayılanı (0.4) kullanılır —
        # davranış değişmez, sadece ayarlanabilir hâle getirilmiştir.
        #
        # ÖNEMLİ (kullanıcı karışıklığı geçmişte burada yaşandı): bu, panelin
        # "Sistem Ayarları" sekmesindeki "Min. plaka tanıma güveni" alanıyla
        # (= min_guven_skoru, veritabanında saklanır, panelden anlık değişir,
        # OCR SONRASI devreye girer) AYNI ŞEY DEĞİLDİR. PTS_ANPR_DETECTOR_ESIGI
        # panelden AYARLANAMAZ; yalnızca işletim sisteminde bir ortam değişkeni
        # olarak tanımlanabilir (örn. Windows'ta `setx PTS_ANPR_DETECTOR_ESIGI 0.25`
        # ile, ardından YENİ bir terminal penceresinden uygulamayı başlatarak —
        # `setx` zaten açık olan pencereleri veya aynı anda çalışan süreci
        # ETKİLEMEZ) ve yalnızca uygulama açılışında (tam olarak burada, bir
        # kez) okunur. Panel ayarını değiştirip yeniden başlatmak bu değeri
        # ASLA değiştirmez.
        detektor_esigi_ham = os.environ.get("PTS_ANPR_DETECTOR_ESIGI", "").strip()
        detektor_esigi_etkin = DEDEKTOR_ESIGI_KUTUPHANE_VARSAYILANI
        detektor_esigi_kaynagi = "kütüphane varsayılanı (ortam değişkeni ayarlanmamış)"
        if detektor_esigi_ham:
            try:
                detektor_esigi = float(detektor_esigi_ham.replace(",", "."))
                detektor_esigi_etkin = max(0.0, min(1.0, detektor_esigi))
                ek_parametreler["detector_conf_thresh"] = detektor_esigi_etkin
                detektor_esigi_kaynagi = f"PTS_ANPR_DETECTOR_ESIGI ortam değişkeni ({detektor_esigi_ham!r})"
            except ValueError:
                logger.warning(
                    "PTS_ANPR_DETECTOR_ESIGI=%r sayıya çevrilemedi (0.0-1.0 arası ondalık "
                    "bir sayı bekleniyor, örn. 0.25). Kütüphane varsayılanı (%.2f) kullanılacak.",
                    detektor_esigi_ham, DEDEKTOR_ESIGI_KUTUPHANE_VARSAYILANI,
                )
        # GÖZLEMLENEBİLİRLİK: uygulama her açılışta, dedektörün fiilen hangi eşikle
        # ve hangi kaynaktan çalıştığını AÇIKÇA loglar — "ayarım kabul edildi mi?"
        # sorusuna panel/log üzerinden kesin cevap vermek için (önceden bu bilgi
        # hiçbir yerde raporlanmıyordu, sadece kodun içinde sessizce uygulanıyordu).
        logger.info(
            "ANPR dedektör güven eşiği (detector_conf_thresh) = %.2f — kaynak: %s",
            detektor_esigi_etkin, detektor_esigi_kaynagi,
        )
        self.detektor_esigi_etkin = detektor_esigi_etkin
        self.detektor_esigi_kaynagi = detektor_esigi_kaynagi
        self._alpr = ALPR(detector_model=detector_model, ocr_model=ocr_model, **ek_parametreler)

    def tahmin_et(self, frame: Any) -> list[PlakaSonucu]:
        """Frame üzerinde plaka bulur; motorun sonuç nesnelerini PTS tipine çevirir."""
        sonuclar = self._alpr.predict(frame)
        donus: list[PlakaSonucu] = []
        for sonuc in sonuclar or []:
            plaka = _alan(sonuc, "plate", "text")
            if not plaka:
                continue
            guven = float(_alan(sonuc, "score", "confidence") or 0)
            kutu_verisi = _alan(sonuc, "box", "bbox")
            kutu = _kutuya_cevir(kutu_verisi)
            donus.append(PlakaSonucu(_plaka_temizle(str(plaka)), guven, kutu))
        return [sonuc for sonuc in donus if sonuc.plaka_no]


def _alan(nesne: Any, *alanlar: str) -> Any:
    for alan in alanlar:
        if isinstance(nesne, dict) and alan in nesne:
            return nesne[alan]
        if hasattr(nesne, alan):
            return getattr(nesne, alan)
    return None


def _kutuya_cevir(kutu: Any) -> Optional[tuple[int, int, int, int]]:
    if not kutu:
        return None
    try:
        if isinstance(kutu, dict):
            return tuple(int(kutu[key]) for key in ("xmin", "ymin", "xmax", "ymax"))
        return tuple(int(_alan(kutu, key) or 0) for key in ("xmin", "ymin", "xmax", "ymax"))
    except (KeyError, TypeError, ValueError):
        return None


def _plaka_temizle(metin: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", metin.upper())