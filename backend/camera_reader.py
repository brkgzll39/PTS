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
"""
import os
import re
import tempfile
import time
import threading
from typing import Optional

try:
    from backend.anpr_engine import ANPREngine  # proje kökünden çalıştırılınca
except ImportError:
    from anpr_engine import ANPREngine  # backend/ içinden doğrudan çalıştırılınca

try:
    import cv2
    import requests
    KUTUPHANELER_MEVCUT = True
except ImportError:
    KUTUPHANELER_MEVCUT = False


PLAKA_REGEX = re.compile(r'^(\d{2})([A-PR-VYZ]{1,3})(\d{2,4})$')

# Plaka overlay stilleri
_OVERLAY_RENK = (0, 220, 80)       # yeşil kutu / metin
_OVERLAY_ARKA = (0, 0, 0)          # metin arkaplanı
_YAZI_OLCEK = 0.8
_YAZI_KALINLIK = 2


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
                 kamera_id: str = "KAMERA-1", tekrar_gecikme_sn: int = 30, yon: str = "giris"):
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
        self.motor = ANPREngine()
        self.calisiyor = False
        self.son_plaka_zamani: dict = {}

        # Gecikme-serbest akış: okuyucu thread sadece en son kareyi tutar
        self._son_kare = None
        self._kare_kilit = threading.Lock()
        self._kare_guncellendi = threading.Event()

        # Son annotated frame (goruntu endpoint'i için)
        self._goruntu_kilit = threading.Lock()
        self._son_goruntu_jpeg: Optional[bytes] = None

        # Son tespit sonuçları (frontend overlay için)
        self._son_tespitler: list = []

    # ------------------------------------------------------------------
    # Dışarıya açık: son JPEG kareyi döner (pipeline çalışırken hızlı)
    # ------------------------------------------------------------------

    def son_goruntu_al(self) -> Optional[bytes]:
        with self._goruntu_kilit:
            return self._son_goruntu_jpeg

    def son_tespitler_al(self) -> list:
        return list(self._son_tespitler)

    # ------------------------------------------------------------------
    # Pipeline kontrolü
    # ------------------------------------------------------------------

    def baslat(self) -> None:
        self.calisiyor = True
        threading.Thread(target=self._dongu, daemon=True, name=f"pts-pipeline-{self.kamera_id}").start()
        print(f"Kamera pipeline başlatıldı: {self.kamera_id}")

    def durdur(self) -> None:
        self.calisiyor = False

    # ------------------------------------------------------------------
    # İç metodlar
    # ------------------------------------------------------------------

    def _kare_okuyucu(self, cap) -> None:
        """Ayrı thread: RTSP tamponunu sürekli boşaltır, sadece en son kareyi saklar.
        Bu sayede işleyici thread her zaman gecikme-serbest taze kareyle çalışır."""
        while self.calisiyor:
            ret, frame = cap.read()
            if ret and frame is not None:
                with self._kare_kilit:
                    self._son_kare = frame
                self._kare_guncellendi.set()
            else:
                time.sleep(0.05)

    def _kareyi_isle(self, frame) -> list:
        """Kareyi ANPR motoruna verir, geçerli plakaları API'ye gönderir."""
        tespitler = []
        for sonuc in self.motor.tahmin_et(frame):
            plaka = plaka_dogrula(sonuc.plaka_no)
            if not plaka:
                continue
            tespitler.append({
                "plaka": plaka,
                "guven": sonuc.guven_skoru,
                "kutu": list(sonuc.kutu) if sonuc.kutu else None,
            })

        # Kare üstüne tüm tespitleri çiz (overlay kopyası)
        annotated = frame.copy()
        _kare_uzerine_ciz(annotated, tespitler)
        _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
        with self._goruntu_kilit:
            self._son_goruntu_jpeg = buf.tobytes()
        self._son_tespitler = tespitler

        gonderilenler = []
        for t in tespitler:
            plaka = t["plaka"]
            simdi = time.time()
            if (plaka in self.son_plaka_zamani and
                    simdi - self.son_plaka_zamani[plaka] < self.tekrar_gecikme_sn):
                continue
            self.son_plaka_zamani[plaka] = simdi

            gecici = os.path.join(tempfile.gettempdir(), f"{plaka.replace(' ', '')}_{int(simdi)}.jpg")
            cv2.imwrite(gecici, annotated)  # annotated frame gönder
            try:
                with open(gecici, "rb") as f:
                    requests.post(
                        self.api_url,
                        data={"plaka_no": plaka, "kamera_id": self.kamera_id,
                              "yon": self.yon, "guven_skoru": round(t["guven"], 3)},
                        files={"gorsel": f},
                        timeout=5,
                    )
                gonderilenler.append(plaka)
            except Exception as e:
                print(f"API'ye gönderilemedi: {e}")
            finally:
                try:
                    os.remove(gecici)
                except OSError:
                    pass

        return gonderilenler

    def _dongu(self) -> None:
        os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "quiet")

        def _cap_ac():
            cap = cv2.VideoCapture(self.video_kaynagi, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return cap

        cap = _cap_ac()
        okuyucu = threading.Thread(target=self._kare_okuyucu, args=(cap,), daemon=True,
                                   name=f"pts-okuyucu-{self.kamera_id}")
        okuyucu.start()

        yeniden_baglanma = 0
        while self.calisiyor:
            # Taze kare gelene kadar bekle (max 3 sn)
            guncellendi = self._kare_guncellendi.wait(timeout=3.0)
            if not guncellendi:
                # 3 sn kare gelmedi → yeniden bağlan
                yeniden_baglanma += 1
                print(f"[{self.kamera_id}] Kare gelmedi, yeniden bağlanıyor ({yeniden_baglanma})…")
                cap.release()
                time.sleep(min(2 * yeniden_baglanma, 15))
                cap = _cap_ac()
                okuyucu = threading.Thread(target=self._kare_okuyucu, args=(cap,), daemon=True,
                                           name=f"pts-okuyucu-{self.kamera_id}")
                okuyucu.start()
                continue

            self._kare_guncellendi.clear()
            with self._kare_kilit:
                kare = self._son_kare

            if kare is not None:
                yeniden_baglanma = 0
                try:
                    self._kareyi_isle(kare)
                except Exception as exc:
                    print(f"[{self.kamera_id}] Kare işleme hatası: {exc}")

            # Tam akış → sadece ANPR frekansını sınırla, görüntü okuyucu thread'i yavaşlamıyor
            time.sleep(0.25)

        cap.release()


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
    gonderilenler = pipeline._kareyi_isle(frame)
    if gonderilenler:
        print(f"Tespit edilip gönderilen plakalar: {gonderilenler}")
    else:
        print("Görselde geçerli formatta bir plaka tespit edilemedi.")
    return gonderilenler

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
"""
import os
import re
import tempfile
import time
import threading

try:
    from backend.anpr_engine import ANPREngine  # proje kökünden çalıştırılınca
except ImportError:
    from anpr_engine import ANPREngine  # backend/ içinden doğrudan çalıştırılınca

try:
    import cv2
    import requests
    KUTUPHANELER_MEVCUT = True
except ImportError:
    KUTUPHANELER_MEVCUT = False


PLAKA_REGEX = re.compile(r'^(\d{2})([A-PR-VYZ]{1,3})(\d{2,4})$')


def plaka_dogrula(text: str):
    """OCR çıktısını Türk plaka formatına göre doğrular/temizler. Geçersizse None döner."""
    temiz = text.upper().replace(" ", "")
    eslesme = PLAKA_REGEX.match(temiz)
    if eslesme:
        il_kodu = int(eslesme.group(1))
        if 1 <= il_kodu <= 81:
            return f"{eslesme.group(1)} {eslesme.group(2)} {eslesme.group(3)}"
    return None


class KameraPipeline:
    def __init__(self, video_kaynagi, api_url="http://localhost:8000/kayitlar/otomatik",
                 kamera_id="KAMERA-1", tekrar_gecikme_sn=30, yon="giris"):
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
        self.motor = ANPREngine()
        self.calisiyor = False
        self.son_plaka_zamani = {}

    def baslat(self):
        self.calisiyor = True
        threading.Thread(target=self._dongu, daemon=True).start()
        print(f"Kamera pipeline başlatıldı: {self.kamera_id}")

    def durdur(self):
        self.calisiyor = False

    def _kareyi_isle(self, frame) -> list:
        """Bir kareyi işler, geçerli plakaları API'ye gönderir; gönderilen plaka listesini döndürür."""
        gonderilenler = []
        for sonuc in self.motor.tahmin_et(frame):
            plaka = plaka_dogrula(sonuc.plaka_no)
            if not plaka:
                continue

            simdi = time.time()
            if (plaka in self.son_plaka_zamani and
                    simdi - self.son_plaka_zamani[plaka] < self.tekrar_gecikme_sn):
                continue
            self.son_plaka_zamani[plaka] = simdi

            gecici_gorsel = os.path.join(tempfile.gettempdir(), f"{plaka.replace(' ', '')}_{int(simdi)}.jpg")
            cv2.imwrite(gecici_gorsel, frame)

            try:
                with open(gecici_gorsel, "rb") as f:
                    requests.post(
                        self.api_url,
                        data={
                            "plaka_no": plaka,
                            "kamera_id": self.kamera_id,
                            "yon": self.yon,
                            "guven_skoru": round(sonuc.guven_skoru, 3),
                        },
                        files={"gorsel": f},
                        timeout=5,
                    )
                gonderilenler.append(plaka)
            except Exception as e:
                print(f"API'ye gönderilemedi: {e}")
            finally:
                try:
                    os.remove(gecici_gorsel)
                except OSError:
                    pass
        return gonderilenler

    def _dongu(self):
        import os as _os
        # ffmpeg RTP uyarılarını bastır (bad cseq, PTx gibi zararsız log'lar)
        _os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "quiet")
        cap = cv2.VideoCapture(self.video_kaynagi, cv2.CAP_FFMPEG)
        hatali_kare = 0
        while self.calisiyor:
            ret, frame = cap.read()
            if not ret:
                hatali_kare += 1
                if hatali_kare >= 3:
                    cap.release()
                    time.sleep(2)
                    cap = cv2.VideoCapture(self.video_kaynagi, cv2.CAP_FFMPEG)
                    hatali_kare = 0
                else:
                    time.sleep(0.5)
                continue
            hatali_kare = 0
            self._kareyi_isle(frame)
            time.sleep(0.3)
        cap.release()


def tek_gorsel_test(gorsel_yolu: str, api_url="http://localhost:8000/kayitlar/otomatik",
                     kamera_id="TEST-KAMERA", yon="giris"):
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
    gonderilenler = pipeline._kareyi_isle(frame)
    if gonderilenler:
        print(f"Tespit edilip gönderilen plakalar: {gonderilenler}")
    else:
        print("Görselde geçerli formatta bir plaka tespit edilemedi.")
    return gonderilenler
