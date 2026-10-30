"""Dahua ANPR kamerasının KENDİ HAFIZASINDAKİ (SD kart) plaka kayıtlarını sonradan okuma.

2026-10-30 (kullanıcı: "sunucu bilgisayarı yetkisiz kişilerce kapatıldı. ANPR
kamerası geçişleri kaydedip sunucu tekrar açıldığında sisteme geçişleri
yansıtsın"): Dahua ITC kameraları her plaka okumasını (ve fotoğrafını) kendi
kartına yazar; sunucu kapalıyken de bunu yapmaya devam eder. Sunucu açılınca
PTS, kapalı kaldığı aralığın kayıtlarını kameradan ister ve eksik geçişleri
ekler (bkz. main.py "SUNUCU KESİNTİSİ").

BİLİNEN BELİRSİZLİK (dahua_olay.py'deki gibi): Dahua'nın yazılım sürümleri
kayıt sorgusunu farklı uçlarla ve farklı alan adlarıyla yanıtlıyor. Bu yüzden
sırayla üç sorgu denenir ve ilk sonuç veren kullanılır:

  1. recordFinder.cgi?action=find&name=TrafficSnapEventInfo&condition.StartTime=<unix>&...
  2. Aynısı, "condition." öneki olmadan (eski sürümler).
  3. mediaFileFind.cgi (factory.create -> findFile -> findNextFile -> close):
     kart üzerindeki olay fotoğraflarını listeler; plaka olay özetinden okunur,
     fotoğraf RPC_Loadfile ile indirilir.

Yanıtlar `records[0].PlateNumber=34ABC123` gibi anahtar=değer satırlarıdır;
plaka, zaman ve dosya yolu alan ADININ SONUNA göre tanınır (TrafficCar.PlateNumber,
PlateNumber, Summary...PlateNumber hepsi plaka sayılır). Panelde "Önizle"
kameranın HAM yanıtını da gösterir: sahadaki gerçek biçim ilk denemede görülür.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

from backend.dahua_olay import _PLAKASIZ_DEGERLER, rtsp_adresinden_baglanti

logger = logging.getLogger("pts.dahua")

ZAMAN_ASIMI_SN = 15
EN_FAZLA_KAYIT = 5000
_SAYFA = 100
_HAM_ORNEK_UZUNLUK = 1500

_PLAKA_ALANLARI = ("platenumber", "plate", "platetext")
_ZAMAN_ALANLARI = ("utc", "createtime", "snaptime", "time", "starttime", "recordbeginutc", "eventtime", "begintime")
_DOSYA_ALANLARI = ("filepath", "picpath", "picturepath", "path")
_KAYIT_DESENI = re.compile(r"^(records|items|found\.items|list)\[(\d+)\]\.(.+)$", re.I)


def kv_ayristir(metin: str) -> list:
    """'a.b[0].c=d' satırlarını (anahtar, değer) listesine çevirir (sıra korunur)."""
    satirlar = []
    for satir in (metin or "").splitlines():
        if "=" not in satir:
            continue
        anahtar, deger = satir.split("=", 1)
        satirlar.append((anahtar.strip(), deger.strip()))
    return satirlar


def kayitlari_grupla(metin: str) -> list:
    """records[N].* / items[N].* satırlarını kayıt başına sözlüklere toplar."""
    gruplar = {}
    for anahtar, deger in kv_ayristir(metin):
        m = _KAYIT_DESENI.match(anahtar)
        if m:
            gruplar.setdefault((m.group(1).lower(), int(m.group(2))), {})[m.group(3)] = deger
    return [gruplar[k] for k in sorted(gruplar)]


def _alan(kayit: dict, sonlar: tuple) -> Optional[str]:
    """Anahtarının son parçası (nokta/köşeli parantez sonrası) `sonlar`dan biri olan ilk dolu değer."""
    for sonek in sonlar:
        for anahtar, deger in kayit.items():
            son = re.split(r"[.\]]", anahtar)[-1].lower()
            if son == sonek and deger.strip():
                return deger.strip()
    return None


def zaman_coz(deger: Optional[str]) -> Optional[datetime]:
    """Unix saniyesi (UTC) ya da 'YYYY-MM-DD HH:MM:SS' (kameranın yerel saati)."""
    if not deger:
        return None
    deger = deger.strip().strip('"')
    if re.fullmatch(r"\d{9,11}", deger):
        try:
            return datetime.fromtimestamp(int(deger))
        except (OverflowError, OSError, ValueError):
            return None
    for bicim in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(deger[:19], bicim)
        except ValueError:
            continue
    return None


def kayit_ayikla(kayit: dict) -> Optional[dict]:
    plaka = _alan(kayit, _PLAKA_ALANLARI)
    if not plaka:
        return None
    plaka = re.sub(r"[^A-Za-z0-9 ]", "", plaka).strip().upper()
    if plaka.replace(" ", "") in _PLAKASIZ_DEGERLER or len(plaka.replace(" ", "")) < 4:
        return None
    zaman = zaman_coz(_alan(kayit, _ZAMAN_ALANLARI))
    if zaman is None:
        return None
    return {"plaka": plaka, "zaman": zaman, "dosya": _alan(kayit, _DOSYA_ALANLARI)}


def _tekillestir(kayitlar: list) -> list:
    """Aynı plaka 30 sn içinde birden çok kez (her fotoğraf ayrı satır) gelirse bir kez sayılır."""
    sonuc = []
    for k in sorted(kayitlar, key=lambda x: x["zaman"]):
        if any(o["plaka"].replace(" ", "") == k["plaka"].replace(" ", "")
               and abs((o["zaman"] - k["zaman"]).total_seconds()) <= 30 for o in sonuc[-20:]):
            onceki = next(o for o in reversed(sonuc) if o["plaka"].replace(" ", "") == k["plaka"].replace(" ", ""))
            onceki["dosya"] = onceki["dosya"] or k["dosya"]
            continue
        sonuc.append(dict(k))
    return sonuc


class _Baglanti:
    def __init__(self, rtsp_url: str, http_port: Optional[int]):
        import requests
        from requests.auth import HTTPDigestAuth

        b = rtsp_adresinden_baglanti(rtsp_url, http_port)
        host = f"[{b['host']}]" if ":" in b["host"] else b["host"]
        self.kok = f"http://{host}" + (f":{b['port']}" if b["port"] != 80 else "")
        self.adres = f"{b['host']}:{b['port']}"
        self.oturum = requests.Session()
        self.oturum.auth = HTTPDigestAuth(b["kullanici"], b["parola"])

    def getir(self, yol: str):
        return self.oturum.get(self.kok + yol, timeout=ZAMAN_ASIMI_SN)


def _record_finder(bag: _Baglanti, bas: datetime, bit: datetime, onekli: bool, ham: list) -> Optional[list]:
    onek = "condition." if onekli else ""
    yol = (f"/cgi-bin/recordFinder.cgi?action=find&name=TrafficSnapEventInfo"
           f"&{onek}StartTime={int(bas.timestamp())}&{onek}EndTime={int(bit.timestamp())}&count={EN_FAZLA_KAYIT}")
    y = bag.getir(yol)
    ham.append({"yontem": f"recordFinder{'' if onekli else ' (öneksiz)'}", "http": y.status_code,
                "ornek": y.text[:_HAM_ORNEK_UZUNLUK]})
    if y.status_code != 200 or "Error" in y.text[:50]:
        return None
    return [a for a in (kayit_ayikla(k) for k in kayitlari_grupla(y.text)) if a]


def _media_file_find(bag: _Baglanti, bas: datetime, bit: datetime, olay: str, ham: list) -> Optional[list]:
    y = bag.getir("/cgi-bin/mediaFileFind.cgi?action=factory.create")
    ham.append({"yontem": "mediaFileFind (create)", "http": y.status_code, "ornek": y.text[:300]})
    m = re.search(r"result\s*=\s*(\d+)", y.text)
    if y.status_code != 200 or not m:
        return None
    nesne = m.group(1)
    try:
        bicim = "%Y-%m-%d %H:%M:%S"
        y = bag.getir(f"/cgi-bin/mediaFileFind.cgi?action=findFile&object={nesne}&condition.Channel=1"
                      f"&condition.StartTime={quote(bas.strftime(bicim))}&condition.EndTime={quote(bit.strftime(bicim))}"
                      f"&condition.Types[0]=jpg&condition.Flags[0]=Event&condition.Events[0]={quote(olay)}")
        ham.append({"yontem": "mediaFileFind (findFile)", "http": y.status_code, "ornek": y.text[:300]})
        if y.status_code != 200 or "OK" not in y.text:
            return None
        kayitlar = []
        for _ in range(EN_FAZLA_KAYIT // _SAYFA):
            y = bag.getir(f"/cgi-bin/mediaFileFind.cgi?action=findNextFile&object={nesne}&count={_SAYFA}")
            if len(ham) < 6:
                ham.append({"yontem": "mediaFileFind (findNextFile)", "http": y.status_code, "ornek": y.text[:_HAM_ORNEK_UZUNLUK]})
            if y.status_code != 200:
                break
            sayfa = kayitlari_grupla(y.text)
            kayitlar += [a for a in (kayit_ayikla(k) for k in sayfa) if a]
            if len(sayfa) < _SAYFA:
                break
        return kayitlar
    finally:
        for eylem in ("close", "destroy"):
            try:
                bag.getir(f"/cgi-bin/mediaFileFind.cgi?action={eylem}&object={nesne}")
            except Exception:
                pass


def kayitlari_getir(rtsp_url: str, bas: datetime, bit: datetime, http_port: Optional[int] = None,
                    olaylar: Optional[str] = None) -> dict:
    """Kameranın `bas`–`bit` arasındaki plaka kayıtları. Hiçbir şey kaydetmez.

    Dönüş: {"basarili", "yontem", "kayitlar": [{plaka, zaman, dosya}], "ham": [...], "hata", "adres"}"""
    sonuc = {"basarili": False, "yontem": None, "kayitlar": [], "ham": [], "hata": None, "adres": None}
    try:
        bag = _Baglanti(rtsp_url, http_port)
    except ValueError as exc:
        sonuc["hata"] = str(exc)
        return sonuc
    sonuc["adres"] = bag.adres
    olay = (olaylar or "TrafficJunction").split(",")[0].strip() or "TrafficJunction"
    denemeler = (
        ("recordFinder", lambda: _record_finder(bag, bas, bit, True, sonuc["ham"])),
        ("recordFinder (öneksiz)", lambda: _record_finder(bag, bas, bit, False, sonuc["ham"])),
        ("mediaFileFind", lambda: _media_file_find(bag, bas, bit, olay, sonuc["ham"])),
    )
    for ad, dene in denemeler:
        try:
            bulunan = dene()
        except Exception as exc:
            sonuc["ham"].append({"yontem": ad, "http": None, "ornek": f"Bağlantı hatası: {exc}"})
            if ad == "recordFinder" and "401" not in str(exc):
                # Kameraya hiç ulaşılamıyorsa diğer yöntemleri denemenin anlamı yok.
                if isinstance(exc, OSError) or exc.__class__.__name__ in ("ConnectionError", "ConnectTimeout"):
                    sonuc["hata"] = f"Kameraya bağlanılamadı ({bag.adres}): {exc}"
                    return sonuc
            continue
        if bulunan is None:
            continue
        sonuc.update(basarili=True, yontem=ad, kayitlar=_tekillestir(
            [k for k in bulunan if bas - timedelta(minutes=1) <= k["zaman"] <= bit + timedelta(minutes=1)]))
        if sonuc["kayitlar"] or ad == denemeler[-1][0]:
            break
    if not sonuc["basarili"]:
        sonuc["hata"] = ("Kamera kayıt sorgusunu kabul etmedi. Kameranın kartında ANPR kayıtlarının tutulduğunu "
                         "(Depolama ayarları) ve kullanıcının yetkisini kontrol edin; ham yanıtlar aşağıda.")
    return sonuc


def goruntu_indir(rtsp_url: str, dosya_yolu: str, http_port: Optional[int] = None) -> Optional[bytes]:
    """Kameranın kartındaki fotoğraf (mediaFileFind'ın FilePath'i). Alınamazsa None."""
    if not dosya_yolu or not dosya_yolu.startswith("/"):
        return None
    try:
        bag = _Baglanti(rtsp_url, http_port)
        y = bag.getir("/cgi-bin/RPC_Loadfile" + quote(dosya_yolu))
    except Exception as exc:
        logger.info("Kamera fotoğrafı indirilemedi (%s): %s", dosya_yolu, exc)
        return None
    veri = y.content if y.status_code == 200 else b""
    bas = veri.find(b"\xff\xd8")  # Dahua bazen JPEG'in önüne başlık ekliyor
    return veri[bas:] if bas >= 0 and len(veri) - bas > 1000 else None
