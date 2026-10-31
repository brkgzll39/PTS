"""Dahua ANPR kamerasının KENDİ HAFIZASINDAKİ (SD kart) plaka kayıtlarını sonradan okuma.

2026-10-30 (kullanıcı: "sunucu bilgisayarı yetkisiz kişilerce kapatıldı. ANPR
kamerası geçişleri kaydedip sunucu tekrar açıldığında sisteme geçişleri
yansıtsın"): Dahua ITC kameraları her plaka okumasını (ve fotoğrafını) kendi
kartına yazar; sunucu kapalıyken de bunu yapmaya devam eder. Sunucu açılınca
PTS, kapalı kaldığı aralığın kayıtlarını kameradan ister ve eksik geçişleri
ekler (bkz. main.py "SUNUCU KESİNTİSİ").

BİLİNEN BELİRSİZLİK (dahua_olay.py'deki gibi): Dahua'nın yazılım sürümleri
kayıt sorgusunu farklı uçlarla ve farklı alan adlarıyla yanıtlıyor. Bu yüzden
sırayla üç yöntem denenir ve aralığı doğru okuyan ilk yöntem kullanılır:

  1. recordFinder.cgi?action=find&name=TrafficSnapEventInfo + zaman süzgeci; birkaç
     yazım denenir, dönen kayıtların gerçekten aralıkta olduğu doğrulanır.
  2. Süzgeç yok sayılıyorsa: recordFinder doSeekFind (offset/count) ile kayıt
     sırasında ikili arama (bkz. _record_finder_arama).
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


_EPOK = datetime(1970, 1, 1)


def yerel_saat_farki(an: Optional[datetime] = None) -> timedelta:
    """Sunucunun UTC'ye göre saat farkı (Türkiye: +3 sa)."""
    an = an or datetime.now()
    t = an.timestamp()
    return datetime.fromtimestamp(t) - datetime.utcfromtimestamp(t)


def zaman_coz(deger: Optional[str], kayma: Optional[timedelta] = None) -> Optional[datetime]:
    """Unix saniyesi ya da 'YYYY-MM-DD HH:MM:SS' (kameranın yerel saati).

    Unix saniyesine eklenen `kayma`: None -> gerçek UTC kabul edilir (sunucunun saat
    farkı eklenir); timedelta(0) -> kamera YEREL saati saniyeye çevirmiş (SAHADA
    GÖRÜLDÜ 2026-10-31, TPAO Nizamiye: kayıtlar 3 saat ileri görünüyordu). Hangisinin
    doğru olduğu main.py::_dahua_saat_kaymasi ile kameradan kameraya bulunur."""
    if not deger:
        return None
    deger = deger.strip().strip('"')
    if re.fullmatch(r"\d{9,11}", deger):
        try:
            naif = _EPOK + timedelta(seconds=int(deger))
        except (OverflowError, ValueError):
            return None
        return naif + (yerel_saat_farki(naif) if kayma is None else kayma)
    for bicim in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(deger[:19], bicim)
        except ValueError:
            continue
    return None


def kamera_unix(an: datetime, kayma: Optional[timedelta] = None) -> int:
    """`zaman_coz`un tersi: sunucu saatindeki `an`ı kameranın kullandığı unix saniyesine çevirir.
    Sorgu aralığı da kayıtlarla AYNI yorumla gönderilmeli: kamera yerel saat yazıyorsa
    gerçek UTC saniyesi göndermek aralığı 3 saat kaydırır (sahada görüldü, 2026-10-31)."""
    naif = an - (yerel_saat_farki(an) if kayma is None else kayma)
    return int((naif - _EPOK).total_seconds())


def kayit_ayikla(kayit: dict, kayma: Optional[timedelta] = None) -> Optional[dict]:
    plaka = _alan(kayit, _PLAKA_ALANLARI)
    if not plaka:
        return None
    plaka = re.sub(r"[^A-Za-z0-9 ]", "", plaka).strip().upper()
    if plaka.replace(" ", "") in _PLAKASIZ_DEGERLER or len(plaka.replace(" ", "")) < 4:
        return None
    zaman = zaman_coz(_alan(kayit, _ZAMAN_ALANLARI), kayma)
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
    def __init__(self, rtsp_url: str, http_port: Optional[int], kayma: Optional[timedelta] = None):
        import requests
        from requests.auth import HTTPDigestAuth

        b = rtsp_adresinden_baglanti(rtsp_url, http_port)
        host = f"[{b['host']}]" if ":" in b["host"] else b["host"]
        self.kok = f"http://{host}" + (f":{b['port']}" if b["port"] != 80 else "")
        self.adres = f"{b['host']}:{b['port']}"
        self.kayma = kayma  # unix saniyelerinin yorumu (bkz. zaman_coz)
        self.oturum = requests.Session()
        self.oturum.auth = HTTPDigestAuth(b["kullanici"], b["parola"])

    def getir(self, yol: str):
        return self.oturum.get(self.kok + yol, timeout=ZAMAN_ASIMI_SN)


# recordFinder zaman süzgeci yazımları. SAHADA GÖRÜLDÜ (2026-10-31, TPAO Lojman,
# Dahua ITC): "condition.StartTime=<unix>" ve "StartTime=<unix>" ile kamera HTTP 200
# döndü ama süzgeci YOK SAYDI -- en eski kayıttan (RecNo=1) başlayıp en fazla 1024
# kayıt gönderdi. Bu yüzden her yazımın sonucu doğrulanır (dönen kayıtlar istenen
# aralıkta mı); hiçbiri uymazsa doSeekFind ile kayıt sırasında ikili arama yapılır.
_SAYFA_UST = 1024  # kameranın bir yanıtta verdiği en fazla kayıt


def _rf_varyantlari(bas: datetime, bit: datetime, kayma: Optional[timedelta] = None) -> list:
    u1, u2 = str(kamera_unix(bas, kayma)), str(kamera_unix(bit, kayma))
    t1, t2 = bas.strftime("%Y-%m-%d %H:%M:%S"), bit.strftime("%Y-%m-%d %H:%M:%S")
    return [
        ("condition.StartTime (unix)", {"condition.StartTime": u1, "condition.EndTime": u2}),
        ("condition.StartTime (tarih)", {"condition.StartTime": t1, "condition.EndTime": t2}),
        ("StartTime (unix)", {"StartTime": u1, "EndTime": u2}),
        ("StartTime (tarih)", {"StartTime": t1, "EndTime": t2}),
        ("condition.Time (unix)", {"condition.Time[0]": u1, "condition.Time[1]": u2}),
    ]


def _rf_get(bag: "_Baglanti", eylem: str, parametreler: dict):
    from urllib.parse import urlencode
    sorgu = urlencode({"action": eylem, "name": "TrafficSnapEventInfo", **parametreler}, safe="[].:")
    return bag.getir("/cgi-bin/recordFinder.cgi?" + sorgu)


def _rf_satirlari(metin: str, kayma: Optional[timedelta] = None) -> list:
    """Her kayıt için (zaman, ayıklanmış kayıt ya da None) -- plakasız kayıtların zamanı da arama için gerekir."""
    return [(zaman_coz(_alan(k, _ZAMAN_ALANLARI), kayma), kayit_ayikla(k, kayma)) for k in kayitlari_grupla(metin)]


def _rf_ozet(satirlar: list) -> str:
    zamanlar = [z for z, _ in satirlar if z]
    if not zamanlar:
        return f"{len(satirlar)} kayıt"
    return f"{len(satirlar)} kayıt, {min(zamanlar):%d.%m.%Y %H:%M} – {max(zamanlar):%d.%m.%Y %H:%M}"


# Süzgeç "uygulandı" sayılması için dönen kayıtların istenen aralığa en fazla bu kadar
# uzak olmasına izin verilir: aralık kameraya yerel saat / UTC farkıyla birkaç saat kaymış
# gitse de doğru sorgu reddedilmesin (sahada 2026-10-31: ±1 saat kuralı doğru sorguyu
# eledi, ölçüm 1 kayıtla kaldı). Süzgeci yok sayan kamera en eski kayıtlarını (aylar
# öncesi) döndürür; onlar yine elenir. Kesin aralık kayitlari_getir'de süzülür.
_SUZGEC_TOLERANS = timedelta(hours=6)


def _record_finder_suzgecli(bag: "_Baglanti", bas: datetime, bit: datetime, ham: list,
                            bos_yanit: Optional[list] = None) -> Optional[list]:
    """Süzgeci uygulayan yazımlar arasından aralıkta EN ÇOK kayıt döndürenin kayıtları
    (tümü denenir: bir yazımın 1, ötekinin 240 kayıt döndürdüğü görüldü); yoksa None.
    Hiç kayıt döndürmeyen yazım kesin sayılmaz (kamera yazımı anlamamış olabilir):
    `bos_yanit` listesine işaretlenir, sıra araması denenir."""
    en_iyi = None  # (aralıktaki kayıt sayısı, parametreler, satırlar)
    for etiket, parametreler in _rf_varyantlari(bas, bit, bag.kayma):
        y = _rf_get(bag, "find", {**parametreler, "count": _SAYFA_UST})
        satirlar = _rf_satirlari(y.text, bag.kayma) if y.status_code == 200 else []
        ham.append({"yontem": f"recordFinder · {etiket}", "http": y.status_code,
                    "ornek": (_rf_ozet(satirlar) + "\n" if y.status_code == 200 else "") + y.text[:600]})
        if y.status_code != 200 or "Error" in y.text[:50]:
            continue
        zamanlar = [z for z, _ in satirlar if z]
        if not zamanlar:
            if bos_yanit is not None:
                bos_yanit.append(etiket)
            continue
        if not all(bas - _SUZGEC_TOLERANS <= z <= bit + _SUZGEC_TOLERANS for z in zamanlar):
            continue  # kamera bu yazımı yok saydı (çok eski / alakasız kayıtlar döndü)
        aralikta = sum(1 for z in zamanlar if bas <= z <= bit)
        if en_iyi is None or aralikta > en_iyi[0]:
            en_iyi = (aralikta, parametreler, satirlar)
    if en_iyi is None:
        return None
    _, parametreler, satirlar = en_iyi
    kayitlar = [a for _, a in satirlar if a]
    offset = len(satirlar)
    while len(satirlar) >= _SAYFA_UST and offset < EN_FAZLA_KAYIT:  # aralıkta 1024'ten fazla kayıt
        y = _rf_get(bag, "doSeekFind", {**parametreler, "offset": offset, "count": _SAYFA_UST})
        satirlar = _rf_satirlari(y.text, bag.kayma) if y.status_code == 200 else []
        kayitlar += [a for _, a in satirlar if a]
        offset += len(satirlar)
    return kayitlar


def _seek(bag: "_Baglanti", offset: int, adet: int) -> Optional[list]:
    y = _rf_get(bag, "doSeekFind", {"offset": offset, "count": adet})
    if y.status_code != 200 or "Error" in y.text[:50]:
        return None
    return _rf_satirlari(y.text, bag.kayma)


def _record_finder_arama(bag: "_Baglanti", bas: datetime, bit: datetime, ham: list) -> Optional[list]:
    """Süzgeç yoksa: doSeekFind ile kayıt sırası (RecNo) üzerinde ikili arama. Kayıtlar
    zamana göre sıralı kabul edilir; önce toplam kayıt sayısı, sonra `bas`tan sonraki
    ilk kayıt bulunur ve oradan `bit`e kadar sayfa sayfa okunur."""
    def zaman(i):
        r = _seek(bag, i, 1)
        return r[0][0] if r else None

    ilk, ikinci = _seek(bag, 0, 1), _seek(bag, 1, 1)
    if not ilk or not ikinci or ilk == ikinci:
        ham.append({"yontem": "recordFinder · doSeekFind", "http": None,
                    "ornek": "Kamera doSeekFind (sayfalı okuma) desteklemiyor ya da kayıt yok."})
        return None
    # Toplam kayıt sayısı: üstel yoklama + ikili arama (son dolu sıra)
    alt, ust = 0, _SAYFA_UST
    while zaman(ust) is not None and ust < (1 << 24):
        alt, ust = ust, ust * 2
    while ust - alt > 1:
        orta = (alt + ust) // 2
        alt, ust = (orta, ust) if zaman(orta) is not None else (alt, orta)
    toplam = alt + 1
    # `bas`tan sonraki ilk kayıt (zamanı okunamayan kayıt "önce" sayılır)
    sol, sag = 0, toplam
    while sol < sag:
        orta = (sol + sag) // 2
        z = zaman(orta)
        if z is not None and z >= bas:
            sag = orta
        else:
            sol = orta + 1
    kayitlar, offset = [], sol
    while offset < toplam and len(kayitlar) < EN_FAZLA_KAYIT:
        satirlar = _seek(bag, offset, _SAYFA_UST) or []
        if not satirlar:
            break
        kayitlar += [a for z, a in satirlar if a and z and bas <= z <= bit]
        offset += len(satirlar)
        son = [z for z, _ in satirlar if z]
        if son and max(son) > bit:
            break
    ham.append({"yontem": "recordFinder · doSeekFind (sıra araması)", "http": 200,
                "ornek": f"Kamerada toplam {toplam} kayıt; aralığın ilk kaydı {sol}. sırada; {len(kayitlar)} geçiş okundu."})
    return kayitlar


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
                    olaylar: Optional[str] = None, kayma: Optional[timedelta] = None) -> dict:
    """Kameranın `bas`–`bit` arasındaki plaka kayıtları. Hiçbir şey kaydetmez.

    Dönüş: {"basarili", "yontem", "kayitlar": [{plaka, zaman, dosya}], "ham": [...], "hata", "adres"}"""
    sonuc = {"basarili": False, "yontem": None, "kayitlar": [], "ham": [], "hata": None, "adres": None}
    try:
        bag = _Baglanti(rtsp_url, http_port, kayma)
    except ValueError as exc:
        sonuc["hata"] = str(exc)
        return sonuc
    sonuc["adres"] = bag.adres
    olay = (olaylar or "TrafficJunction").split(",")[0].strip() or "TrafficJunction"
    bos_yanit = []
    denemeler = (
        ("recordFinder", lambda: _record_finder_suzgecli(bag, bas, bit, sonuc["ham"], bos_yanit)),
        ("recordFinder (sıra araması)", lambda: _record_finder_arama(bag, bas, bit, sonuc["ham"])),
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
        break  # yöntem aralığı doğru okudu (boş olsa bile: o aralıkta geçiş yok)
    if not sonuc["basarili"] and bos_yanit:
        # Kamera süzgeçli sorguya boş yanıt verdi, sıra araması da yok: aralıkta geçiş yok kabul edilir.
        sonuc.update(basarili=True, yontem=f"recordFinder · {bos_yanit[0]}", kayitlar=[], hata=None)
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
