"""Dahua ANPR kameralarının KENDİ plaka okumalarını PTS'e aktaran bağlantı.

2026-09-25 (kullanıcı: "Dahua ITC413 ... PTS'e aktaran bir bağlantı ekler
misin, deneyelim"): ITC413-PW4D gibi Dahua giriş-çıkış ANPR kameraları
plakayı kendi içlerinde de okur (üretici: tanıma oranı ≥%98). PTS ise aynı
kameranın RTSP görüntüsünü alıp plakayı KENDİ modeliyle okur. Bu modül
kameranın okumasını da alır ve PTS'in çok kareli oylamasına GÜÇLÜ bir oy
olarak ekler (bkz. camera_reader.py::KameraPipeline.harici_okuma_ekle):

  * İki okuma aynıysa kayıt daha güvenilir olur.
  * PTS'in modeli bir kareyi okuyamasa bile (gece, parlama) kameranın
    okuması tek başına kaydı oluşturabilir.
  * Çelişkide kameranın okuması ağır basar (tek oyu birkaç iyi kareye
    denktir), ama PTS'in çok sayıda tutarlı okuması yine de sonucu
    değiştirebilir.

Bağlantı yöntemi -- Dahua HTTP API, "snapManager.cgi attachFileProc":

    GET http://<kamera>/cgi-bin/snapManager.cgi?action=attachFileProc
        &Flags[0]=Event&Events=[TrafficJunction]&heartbeat=5

Kamera bağlantıyı açık tutar ve her plaka olayında `multipart/x-mixed-replace`
biçiminde önce bir `text/plain` parça (ör. `Events[0].TrafficCar.PlateNumber=
34ABC123` satırları), ardından olayın fotoğraf(lar)ını `image/jpeg` parça
olarak gönderir; olay yokken her `heartbeat` saniyede bir "Heartbeat" metni
yollar. Kimlik doğrulama Digest'tir. Kullanıcı adı/parola ve kamera adresi,
kameranın PTS'te zaten kayıtlı RTSP adresinden alınır -- ayrıca girilmez.

BİLİNEN BELİRSİZLİK: Dahua'nın farklı yazılım sürümleri olay metnini
farklı biçimlerde (anahtar=değer satırları ya da JSON) ve farklı olay
adlarıyla (TrafficJunction, TrafficParkingSpace...) gönderebiliyor. Bu
yüzden plaka hem `...PlateNumber=` satırlarından hem JSON'daki
`"PlateNumber"` alanından okunur; olay adı kamera başına ayarlanabilir ve
paneldeki "Bağlantıyı Test Et" düğmesi, kameradan gelen HAM mesajları
göstererek sahadaki gerçek biçimin görülmesini sağlar.
"""
import logging
import re
import threading
import time
from collections import deque
from typing import Callable, Optional
from urllib.parse import quote, unquote, urlsplit

logger = logging.getLogger("pts.dahua")

VARSAYILAN_OLAYLAR = "TrafficJunction"
VARSAYILAN_HTTP_PORT = 80
KALP_ATISI_SN = 5
# Kalp atışı 5 sn'de bir gelmeli; bu kadar süre HİÇ veri gelmezse bağlantı
# ölü sayılıp yeniden kurulur (bkz. canlı ekranlardaki "zombi SSE" dersi).
OKUMA_ZAMAN_ASIMI_SN = 30
_TAMPON_UST_SINIR = 20 * 1024 * 1024
_HAM_ORNEK_SAYISI = 15
_HAM_ORNEK_UZUNLUK = 2000

_OLAY_ADI_DESENI = re.compile(r"^[A-Za-z0-9_]+(,[A-Za-z0-9_]+)*$")

_PLAKA_DESENLERI = (
    re.compile(r"PlateNumber\s*=\s*([^\r\n]*)"),
    re.compile(r'"PlateNumber"\s*:\s*"([^"]*)"'),
    re.compile(r"Object\.Text\s*=\s*([^\r\n]*)"),
)
_PLAKASIZ_DEGERLER = {"", "UNKNOWN", "UNLICENSED", "NOPLATE", "NONE", "NULL", "-"}


def olaylari_dogrula(olaylar: Optional[str]) -> str:
    """Virgülle ayrılmış olay adları (yalnızca harf/rakam/_) -- URL'e
    gömüleceği için sıkı doğrulanır."""
    temiz = (olaylar or VARSAYILAN_OLAYLAR).replace(" ", "")
    if not _OLAY_ADI_DESENI.match(temiz) or len(temiz) > 200:
        raise ValueError(f"Geçersiz olay adı: {olaylar!r} (ör. TrafficJunction veya TrafficJunction,TrafficParkingSpace)")
    return temiz


def rtsp_adresinden_baglanti(rtsp_url: str, http_port: Optional[int] = None) -> dict:
    """Kameranın RTSP adresinden (rtsp://kullanici:parola@ip:554/...) HTTP
    olay bağlantısı için gereken adres ve kimlik bilgilerini çıkarır."""
    parcalar = urlsplit(rtsp_url or "")
    if not parcalar.hostname:
        raise ValueError("Kameranın RTSP adresinden IP/ana bilgisayar adı çıkarılamadı.")
    if not parcalar.username:
        raise ValueError(
            "Kameranın RTSP adresinde kullanıcı adı/parola yok (rtsp://kullanici:parola@ip/...). "
            "Kameranın kendi plaka okumasını alabilmek için adrese eklenmeli."
        )
    return {
        "host": parcalar.hostname,
        "port": int(http_port or VARSAYILAN_HTTP_PORT),
        "kullanici": unquote(parcalar.username),
        "parola": unquote(parcalar.password or ""),
    }


def olay_adresi(host: str, port: int, olaylar: str, kalp_atisi: int = KALP_ATISI_SN) -> str:
    host_kismi = f"[{host}]" if ":" in host else host
    port_kismi = "" if port == 80 else f":{port}"
    # Köşeli parantezler Dahua'nın beklediği biçim; `quote` ile yalnızca
    # güvenli olmayan karakterler kodlanır.
    return (
        f"http://{host_kismi}{port_kismi}/cgi-bin/snapManager.cgi?action=attachFileProc"
        f"&Flags[0]=Event&Events=[{quote(olaylar, safe=',_')}]&heartbeat={int(kalp_atisi)}"
    )


def olay_metninden_plaka(metin: str) -> Optional[str]:
    """Olay metninden plakayı çıkarır; plakasız araç/boş değer için None."""
    for desen in _PLAKA_DESENLERI:
        eslesme = desen.search(metin or "")
        if eslesme:
            deger = eslesme.group(1).strip().strip('"').strip()
            sade = re.sub(r"[^A-Za-z0-9]", "", deger).upper()
            if sade in _PLAKASIZ_DEGERLER:
                return None
            return sade or None
    return None


def olay_kodunu_al(metin: str) -> Optional[str]:
    eslesme = re.search(r"(?:^|\.)Code\s*=\s*([A-Za-z0-9_]+)", metin or "", re.M) or \
        re.search(r'"Code"\s*:\s*"([A-Za-z0-9_]+)"', metin or "")
    return eslesme.group(1) if eslesme else None


class MultipartAyristirici:
    """`multipart/x-mixed-replace` akışını parça parça ayrıştırır. Parçalar
    `Content-Length` ile ya da (başlık yoksa) bir sonraki sınıra kadar
    okunur. `besle()` tamamlanan (içerik_türü, gövde) çiftlerini döner."""

    def __init__(self, sinir: str):
        sinir = (sinir or "myboundary").strip().strip('"')
        self._sinir = (sinir if sinir.startswith("--") else "--" + sinir).encode("latin-1")
        self._tampon = b""

    def besle(self, veri: bytes) -> list:
        self._tampon += veri
        if len(self._tampon) > _TAMPON_UST_SINIR:
            # Bozuk bir akışta tampon sınırsız büyümesin.
            logger.warning("Dahua olay akışı tamponu sınırı aştı, temizleniyor")
            self._tampon = b""
            return []
        parcalar = []
        while True:
            bas = self._tampon.find(self._sinir)
            if bas < 0:
                # Sınır henüz gelmedi; sınırın bir kısmı sonda olabilir, onu tut.
                if len(self._tampon) > len(self._sinir):
                    self._tampon = self._tampon[-len(self._sinir):]
                return parcalar
            baslik_bas = bas + len(self._sinir)
            baslik_son = self._tampon.find(b"\r\n\r\n", baslik_bas)
            if baslik_son < 0:
                self._tampon = self._tampon[bas:]
                return parcalar
            basliklar = self._tampon[baslik_bas:baslik_son].decode("latin-1", "replace")
            govde_bas = baslik_son + 4
            tur_es = re.search(r"Content-Type:\s*([^\r\n;]+)", basliklar, re.I)
            uzunluk_es = re.search(r"Content-Length:\s*(\d+)", basliklar, re.I)
            icerik_turu = tur_es.group(1).strip().lower() if tur_es else "text/plain"
            if uzunluk_es:
                uzunluk = int(uzunluk_es.group(1))
                if len(self._tampon) < govde_bas + uzunluk:
                    self._tampon = self._tampon[bas:]
                    return parcalar
                govde = self._tampon[govde_bas:govde_bas + uzunluk]
                self._tampon = self._tampon[govde_bas + uzunluk:]
            else:
                sonraki = self._tampon.find(self._sinir, govde_bas)
                if sonraki < 0:
                    self._tampon = self._tampon[bas:]
                    return parcalar
                govde = self._tampon[govde_bas:sonraki].rstrip(b"\r\n")
                self._tampon = self._tampon[sonraki:]
            parcalar.append((icerik_turu, govde))


class OlayBirlestirici:
    """Metin parçasındaki plakayı, hemen ardından gelen İLK fotoğrafla
    eşleştirip tek bir olay olarak döner (sonraki fotoğraflar -- ör. plaka
    kırpıntısı -- aynı olaya aittir, yok sayılır)."""

    def __init__(self):
        self._bekleyen: Optional[dict] = None
        self.kalp_atisi_sayisi = 0

    def parca(self, icerik_turu: str, govde: bytes) -> list:
        cikan = []
        if icerik_turu.startswith("image/"):
            if self._bekleyen is not None and self._bekleyen.get("jpeg") is None:
                self._bekleyen["jpeg"] = govde
                cikan.append(self._bekleyen)
                self._bekleyen = None
            return cikan
        metin = govde.decode("utf-8", "replace")
        if self._bekleyen is not None:
            cikan.append(self._bekleyen)
            self._bekleyen = None
        if metin.strip().lower() == "heartbeat":
            self.kalp_atisi_sayisi += 1
            return cikan
        plaka = olay_metninden_plaka(metin)
        if plaka:
            self._bekleyen = {"plaka": plaka, "kod": olay_kodunu_al(metin), "jpeg": None, "metin": metin}
        return cikan


def _hata_mesaji(durum_kodu: int) -> str:
    if durum_kodu == 401:
        return "Kimlik doğrulama başarısız (401): RTSP adresindeki kullanıcı adı/parola kamerada HTTP için geçerli değil."
    if durum_kodu in (400, 404, 501):
        return (f"Kamera olay aboneliğini kabul etmedi ({durum_kodu}): olay adı yanlış olabilir "
                "(ör. TrafficJunction yerine TrafficParkingSpace) ya da bu yazılım sürümü desteklemiyor.")
    return f"Kamera beklenmeyen bir yanıt verdi (HTTP {durum_kodu})."


def _yanit_ac(adres: str, kullanici: str, parola: str, okuma_zaman_asimi: float = OKUMA_ZAMAN_ASIMI_SN):
    import requests
    from requests.auth import HTTPDigestAuth

    return requests.get(adres, auth=HTTPDigestAuth(kullanici, parola), stream=True,
                        timeout=(5, okuma_zaman_asimi))


def _gelen_veriyi_oku(yanit):
    """Akışı GELDİĞİ KADARIYLA okur. `iter_content(8192)` bu iş için uygun
    değil: parça boyutu dolana (8 KB) ya da bağlantı kapanana kadar bekler --
    kalp atışları ve olay metinleri küçük olduğu için olaylar saniyelerce
    gecikir ya da hiç işlenmez. `read1` o an elde olanı hemen döndürür
    (chunked aktarımı da çözer)."""
    ham = yanit.raw
    oku = getattr(ham, "read1", None)
    if oku is None:  # eski urllib3: alttaki http.client yanıtına in
        oku = getattr(getattr(ham, "_fp", None), "read1", None)
    if oku is None:
        yield from yanit.iter_content(chunk_size=1024)
        return
    while True:
        veri = oku(8192)
        if not veri:
            return
        yield veri


def _sinir_al(content_type: str) -> str:
    eslesme = re.search(r"boundary\s*=\s*\"?([^\";]+)\"?", content_type or "", re.I)
    return eslesme.group(1) if eslesme else "myboundary"


class DahuaOlayDinleyici:
    """Bir kameranın olay akışını arka planda sürekli dinler; her plaka
    olayında `geri_cagri(plaka, jpeg)` çağırır. Bağlantı koparsa artan
    beklemeyle (en fazla 60 sn) yeniden bağlanır."""

    def __init__(self, rtsp_url: str, kamera_ad: str, geri_cagri: Callable[[str, Optional[bytes]], None],
                 olaylar: Optional[str] = None, http_port: Optional[int] = None):
        self.kamera_ad = kamera_ad
        self._geri_cagri = geri_cagri
        self._olaylar = olaylari_dogrula(olaylar)
        self._baglanti = rtsp_adresinden_baglanti(rtsp_url, http_port)
        self._adres = olay_adresi(self._baglanti["host"], self._baglanti["port"], self._olaylar)
        self._calisiyor = False
        self._thread: Optional[threading.Thread] = None
        self._yanit = None
        self._kilit = threading.Lock()
        self._durum = {
            "bagli": False, "son_hata": None, "son_baglanti": None, "son_veri": None,
            "son_olay": None, "son_plaka": None, "olay_sayisi": 0, "kalp_atisi_sayisi": 0,
        }
        self._ham_ornekler: deque = deque(maxlen=_HAM_ORNEK_SAYISI)

    def baslat(self) -> None:
        self._calisiyor = True
        self._thread = threading.Thread(target=self._dongu, daemon=True, name=f"pts-dahua-{self.kamera_ad}")
        self._thread.start()
        logger.info("[%s] Dahua plaka olayları dinleniyor (%s:%s, olaylar=%s)",
                    self.kamera_ad, self._baglanti["host"], self._baglanti["port"], self._olaylar)

    def durdur(self) -> None:
        self._calisiyor = False
        yanit = self._yanit
        if yanit is not None:
            try:
                yanit.close()  # bloklanmış okumayı sonlandırır
            except Exception:
                pass

    def durum(self) -> dict:
        with self._kilit:
            d = dict(self._durum)
            d["ham_ornekler"] = list(self._ham_ornekler)
        d["olaylar"] = self._olaylar
        d["adres"] = f"{self._baglanti['host']}:{self._baglanti['port']}"
        return d

    def _guncelle(self, **alanlar) -> None:
        with self._kilit:
            self._durum.update(alanlar)

    def _dongu(self) -> None:
        deneme = 0
        while self._calisiyor:
            try:
                self._bir_baglanti()
                deneme = 0
            except Exception as exc:
                if not self._calisiyor:
                    break  # durdur() bağlantıyı kapattı -- hata değil
                deneme += 1
                self._guncelle(bagli=False, son_hata=str(exc))
                if deneme in (1, 5) or deneme % 30 == 0:
                    logger.warning("[%s] Dahua olay bağlantısı hatası (deneme %d): %s", self.kamera_ad, deneme, exc)
            finally:
                self._guncelle(bagli=False)
                self._yanit = None
            if self._calisiyor:
                time.sleep(min(60, 2 ** min(deneme, 6)))

    def _bir_baglanti(self) -> None:
        yanit = _yanit_ac(self._adres, self._baglanti["kullanici"], self._baglanti["parola"])
        self._yanit = yanit
        try:
            if yanit.status_code != 200:
                raise RuntimeError(_hata_mesaji(yanit.status_code))
            ayristirici = MultipartAyristirici(_sinir_al(yanit.headers.get("Content-Type", "")))
            birlestirici = OlayBirlestirici()
            self._guncelle(bagli=True, son_hata=None, son_baglanti=time.time())
            logger.info("[%s] Dahua olay akışına bağlanıldı", self.kamera_ad)
            for parca in _gelen_veriyi_oku(yanit):
                if not self._calisiyor:
                    return
                if not parca:
                    continue
                self._guncelle(son_veri=time.time())
                for icerik_turu, govde in ayristirici.besle(parca):
                    if not icerik_turu.startswith("image/"):
                        metin = govde[:_HAM_ORNEK_UZUNLUK].decode("utf-8", "replace")
                        if metin.strip().lower() != "heartbeat":
                            with self._kilit:
                                self._ham_ornekler.append({"zaman": time.time(), "metin": metin})
                    for olay in birlestirici.parca(icerik_turu, govde):
                        self._olayi_isle(olay)
                self._guncelle(kalp_atisi_sayisi=birlestirici.kalp_atisi_sayisi)
            raise RuntimeError("Kamera olay bağlantısını kapattı")
        finally:
            try:
                yanit.close()
            except Exception:
                pass

    def _olayi_isle(self, olay: dict) -> None:
        with self._kilit:
            self._durum["olay_sayisi"] += 1
            self._durum["son_olay"] = time.time()
            self._durum["son_plaka"] = olay["plaka"]
        logger.info("[%s] Kamera kendi plaka okumasını gönderdi: %s (olay=%s, fotoğraf=%s)",
                    self.kamera_ad, olay["plaka"], olay.get("kod"), "var" if olay.get("jpeg") else "yok")
        try:
            self._geri_cagri(olay["plaka"], olay.get("jpeg"))
        except Exception:
            logger.exception("[%s] Kamera plaka olayı işlenemedi", self.kamera_ad)


def baglanti_testi(rtsp_url: str, olaylar: Optional[str] = None, http_port: Optional[int] = None,
                   sure_sn: float = 8.0) -> dict:
    """Kameraya bir kez bağlanıp `sure_sn` boyunca dinler; panelde "Bağlantıyı
    Test Et" için. Hiçbir kayıt oluşturmaz. Kamera önünden bu sürede bir araç
    geçmezse plaka olayı gelmemesi normaldir -- bağlantının kurulup kalp
    atışlarının gelmesi yeterli kanıttır."""
    sonuc = {"basarili": False, "http_durum": None, "icerik_turu": None, "kalp_atisi_sayisi": 0,
             "olaylar": [], "ham_ornekler": [], "hata": None}
    try:
        olaylar_d = olaylari_dogrula(olaylar)
        b = rtsp_adresinden_baglanti(rtsp_url, http_port)
        adres = olay_adresi(b["host"], b["port"], olaylar_d)
        sonuc["adres"] = f"{b['host']}:{b['port']}"
        sonuc["olay_adlari"] = olaylar_d
    except ValueError as exc:
        sonuc["hata"] = str(exc)
        return sonuc
    try:
        yanit = _yanit_ac(adres, b["kullanici"], b["parola"], okuma_zaman_asimi=min(10.0, sure_sn + 4))
    except Exception as exc:
        sonuc["hata"] = f"Kameraya bağlanılamadı ({b['host']}:{b['port']}): {exc}"
        return sonuc
    try:
        sonuc["http_durum"] = yanit.status_code
        sonuc["icerik_turu"] = yanit.headers.get("Content-Type")
        if yanit.status_code != 200:
            sonuc["hata"] = _hata_mesaji(yanit.status_code)
            return sonuc
        ayristirici = MultipartAyristirici(_sinir_al(sonuc["icerik_turu"] or ""))
        birlestirici = OlayBirlestirici()
        bitis = time.monotonic() + sure_sn
        try:
            for parca in _gelen_veriyi_oku(yanit):
                for icerik_turu, govde in ayristirici.besle(parca or b""):
                    if not icerik_turu.startswith("image/"):
                        metin = govde[:_HAM_ORNEK_UZUNLUK].decode("utf-8", "replace")
                        if metin.strip().lower() != "heartbeat" and len(sonuc["ham_ornekler"]) < 5:
                            sonuc["ham_ornekler"].append(metin)
                    for olay in birlestirici.parca(icerik_turu, govde):
                        sonuc["olaylar"].append({"plaka": olay["plaka"], "kod": olay.get("kod"),
                                                 "fotograf": olay.get("jpeg") is not None})
                if time.monotonic() >= bitis:
                    break
        except Exception as exc:  # okuma zaman aşımı vb. -- o ana kadar toplanan yeterli
            if not birlestirici.kalp_atisi_sayisi:
                sonuc["hata"] = f"Bağlantı kuruldu ama veri okunamadı: {exc}"
        sonuc["kalp_atisi_sayisi"] = birlestirici.kalp_atisi_sayisi
        sonuc["basarili"] = sonuc["hata"] is None and (birlestirici.kalp_atisi_sayisi > 0 or bool(sonuc["olaylar"]))
        if not sonuc["basarili"] and sonuc["hata"] is None:
            sonuc["hata"] = ("Bağlantı kuruldu ama kameradan kalp atışı/olay gelmedi. Olay adını ya da kameranın "
                             "ANPR özelliğinin açık olduğunu kontrol edin.")
        return sonuc
    finally:
        try:
            yanit.close()
        except Exception:
            pass
