"""Diskte saklanan gizli bilgilerin (kamera parolaları) şifrelenmesi.

2026-11-06 kullanıcı isteği ("kamera parolaları"): RTSP parolaları cameras.json'da
AÇIK METİN duruyordu; sunucu klasörüne erişen ya da dosyanın bir kopyasını
(yedek, e-posta, USB) gören herkes kameraların yönetici parolasını okuyabiliyordu.

Şimdi parola Fernet (AES-128-CBC + HMAC-SHA256, `cryptography` kütüphanesi) ile
şifrelenip "enc1:..." olarak saklanır. Anahtar:
  * PTS_GIZLI_ANAHTAR ortam değişkeni (Fernet anahtarı) verilmişse o,
  * yoksa veritabani/gizli_anahtar.key dosyası (ilk kullanımda üretilir).
    Windows'ta bu dosyadaki anahtar ayrıca DPAPI (CryptProtectData, makine
    kapsamı) ile korunur: dosya başka bir bilgisayara kopyalansa da çözülemez.

Anahtar kaybolursa (ör. Windows yeniden kurulduysa) parolalar çözülemez; kamera
bağlanamaz ve loga yazılır -- kamerayı silip parolasıyla yeniden eklemek yeter.
"""
import base64
import logging
import os
import sys
import threading

logger = logging.getLogger("pts.gizli")

ONEK = "enc1:"
_kilit = threading.Lock()
_fernet = None
_uyarildi = False


def _anahtar_dosyasi() -> str:
    yol = os.getenv("PTS_GIZLI_ANAHTAR_DOSYASI")
    if yol:
        return yol
    from backend.database import DB_KLASORU
    return os.path.join(DB_KLASORU, "gizli_anahtar.key")


# ---------------------------------------------------------------- Windows DPAPI
def _dpapi(veri: bytes, koru: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    tampon = ctypes.create_string_buffer(veri, len(veri))
    giris = BLOB(len(veri), ctypes.cast(tampon, ctypes.POINTER(ctypes.c_char)))
    cikis = BLOB()
    crypt32 = ctypes.windll.crypt32
    CRYPTPROTECT_UI_FORBIDDEN, CRYPTPROTECT_LOCAL_MACHINE = 0x1, 0x4
    bayrak = CRYPTPROTECT_UI_FORBIDDEN | CRYPTPROTECT_LOCAL_MACHINE
    if koru:
        ok = crypt32.CryptProtectData(ctypes.byref(giris), "PTS", None, None, None, bayrak, ctypes.byref(cikis))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(giris), None, None, None, None, bayrak, ctypes.byref(cikis))
    if not ok:
        raise OSError(f"DPAPI hatası: {ctypes.GetLastError()}")
    try:
        return ctypes.string_at(cikis.pbData, cikis.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(cikis.pbData)


def _anahtari_yukle() -> bytes:
    ortam = os.getenv("PTS_GIZLI_ANAHTAR")
    if ortam:
        return ortam.strip().encode()
    yol = _anahtar_dosyasi()
    if os.path.isfile(yol):
        with open(yol, "r", encoding="ascii") as f:
            icerik = f.read().strip()
        tur, _, deger = icerik.partition(":")
        if tur == "dpapi":
            return _dpapi(base64.b64decode(deger), koru=False)
        if tur == "duz":
            return deger.encode()
        raise ValueError(f"Tanınmayan anahtar dosyası biçimi: {yol}")
    from cryptography.fernet import Fernet
    anahtar = Fernet.generate_key()
    icerik = f"duz:{anahtar.decode()}"
    if sys.platform == "win32":
        try:
            icerik = "dpapi:" + base64.b64encode(_dpapi(anahtar, koru=True)).decode()
        except Exception as exc:  # DPAPI yoksa düz dosya (yine de cameras.json'dan ayrı)
            logger.warning("DPAPI kullanılamadı, anahtar korumasız saklanıyor: %s", exc)
    os.makedirs(os.path.dirname(os.path.abspath(yol)) or ".", exist_ok=True)
    tanitici = os.open(yol, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(tanitici, "w", encoding="ascii") as f:
        f.write(icerik)
    logger.info("Yeni şifreleme anahtarı oluşturuldu: %s", yol)
    return anahtar


def _fernet_al():
    global _fernet
    with _kilit:
        if _fernet is None:
            from cryptography.fernet import Fernet
            _fernet = Fernet(_anahtari_yukle())
        return _fernet


def kullanilabilir_mi() -> bool:
    global _uyarildi
    try:
        import cryptography.fernet  # noqa: F401
        return True
    except ImportError:
        if not _uyarildi:
            logger.warning("'cryptography' kurulu değil; kamera parolaları şifrelenmeden saklanıyor.")
            _uyarildi = True
        return False


def sifreli_mi(deger) -> bool:
    return isinstance(deger, str) and deger.startswith(ONEK)


def sifrele(metin: str) -> str:
    if not metin or sifreli_mi(metin) or not kullanilabilir_mi():
        return metin
    return ONEK + _fernet_al().encrypt(metin.encode("utf-8")).decode("ascii")


def coz(deger: str) -> str:
    """Şifreli değeri çözer; şifresiz değeri olduğu gibi döner. Çözülemezse ValueError."""
    if not sifreli_mi(deger):
        return deger
    try:
        return _fernet_al().decrypt(deger[len(ONEK):].encode("ascii")).decode("utf-8")
    except Exception as exc:
        raise ValueError("Şifreli değer çözülemedi (anahtar değişmiş ya da kayıp)") from exc


def _sifirla_test_icin():
    global _fernet
    with _kilit:
        _fernet = None


# ------------------------------------------------------------- RTSP adresleri
def _ayir(url: str):
    """'rtsp://kul:parola@host:554/yol' -> (önek 'rtsp://', 'kul', 'parola', 'host:554/yol')."""
    sema, ayrac, kalan = url.partition("://")
    if not ayrac:
        return None
    netloc, egik, yol = kalan.partition("/")
    if "@" not in netloc:
        return None
    kimlik, _, host = netloc.rpartition("@")
    kul, iki_nokta, parola = kimlik.partition(":")
    return sema + "://", kul, parola if iki_nokta else None, host + egik + yol


def rtsp_parolasini_ayir(url: str):
    """Adresten parolayı çıkarır: (parolasız_adres, parola veya None)."""
    parca = _ayir(str(url or ""))
    if not parca or parca[2] is None:
        return url, None
    onek, kul, parola, geri = parca
    return f"{onek}{kul}@{geri}", parola


def rtsp_parolasini_ekle(url: str, parola: str) -> str:
    parca = _ayir(str(url or ""))
    if not parca:
        return url
    onek, kul, _, geri = parca
    return f"{onek}{kul}:{parola}@{geri}"


def kamera_diske(kamera: dict) -> dict:
    """Diske yazılacak kopya: parola adresten çıkarılıp şifreli 'rtsp_parola' alanına konur."""
    k = dict(kamera)
    k.pop("parola_cozulemedi", None)
    eski_sifreli = k.pop("_rtsp_parola_sifreli", None)
    if not kullanilabilir_mi():
        return k
    temiz, parola = rtsp_parolasini_ayir(k.get("rtsp_url", ""))
    if parola:
        k["rtsp_url"] = temiz
        k["rtsp_parola"] = sifrele(parola)
    elif eski_sifreli:
        k["rtsp_parola"] = eski_sifreli
    return k


def kamera_diskten(kamera: dict) -> dict:
    """Okunan kaydı bellekte kullanılacak hale getirir (parola adrese geri eklenir)."""
    if "rtsp_parola" not in kamera:
        return kamera
    k = dict(kamera)
    sifreli = k.pop("rtsp_parola")
    try:
        k["rtsp_url"] = rtsp_parolasini_ekle(k.get("rtsp_url", ""), coz(sifreli))
    except ValueError as exc:
        logger.error("Kamera '%s' parolası çözülemedi: %s -- kamerayı parolasıyla yeniden ekleyin.",
                     k.get("ad"), exc)
        k["parola_cozulemedi"] = True
        k["_rtsp_parola_sifreli"] = sifreli   # yeniden yazılırsa kaybolmasın
    return k
