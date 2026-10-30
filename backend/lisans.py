"""Paylaşılan PTS lisans üretme/doğrulama mantığı.

Hem `lisans_uretici.py` (CLI aracı) hem de `main.py` (API, lisans aktivasyon
uç noktası) aynı imzalama/doğrulama algoritmasını kullanır. Mantık daha önce
iki dosyada ayrı ayrı yazılmıştı; bu, biri güncellenip diğerinin unutulması
durumunda üretilen lisansların doğrulanamaz hale gelmesi gibi sinsi bir hataya
açık kapı bırakıyordu. Artık tek doğru kaynak (single source of truth) burası.

Bağımlılık: yalnızca standart kütüphane. FastAPI/SQLAlchemy'ye ihtiyaç duymaz,
bu sayede bu modül tek başına da (birim testleriyle) doğrulanabilir.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import platform
import secrets
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from backend import ed25519

VARSAYILAN_GELISTIRME_SECRET = "gelistirme-lisans-anahtari-degistir"
LISANS_VERSIYONU = "PTS1"          # eski: HMAC (doğrulayan anahtar = üreten anahtar)
IMZALI_LISANS_VERSIYONU = "PTS2"   # 2026-10-20: Ed25519 açık anahtarlı imza

# Lisans verenin Ed25519 AÇIK anahtarı (64 hex). Yalnızca doğrulama yapar;
# bununla lisans ÜRETİLEMEZ. Özel anahtar lisans verenin bilgisayarında kalır
# (bkz. araclar/lisans_araci.py). Boşsa PTS2 lisanslar kabul edilmez.
ACIK_ANAHTAR_HEX = "738500b7f97c53fc8dcfc0756e5136647dbe915368e9b24ea487aba92845f57b"

# Eski (PTS1/HMAC) lisanslar kabul edilsin mi? Kaynak koddan çalışan kurulumda
# (lisans verenin kendi sistemi) şimdilik True. Müşteriye giden DERLENMİŞ
# kurulumda derleme betiği bunu False yapar (bkz. installer/derle_windows.py):
# müşteri .env'e kendi PTS_LICENSE_SECRET'ını yazıp PTS1 lisans üretemesin.
ESKI_LISANS_KABUL = True

logger = logging.getLogger("pts.lisans")
_varsayilan_secret_uyarisi_yapildi = False


class LisansGecersiz(Exception):
    """Lisans anahtarı imzası geçersiz, formatı bozuk, süresi dolmuş ya da
    başka bir cihaza kilitli. Mesajı kullanıcıya doğrudan gösterilebilir."""


def secret_al() -> str:
    """PTS_LICENSE_SECRET ortam değişkeni yoksa geliştirme anahtarına düşer
    (üretimde mutlaka değiştirilmeli — bkz. README Lisans bölümü).

    GÜVENLİK: Bu geliştirme/varsayılan secret KAYNAK KODDA açıkça görünür ve
    HER kurulumda aynıdır. `PTS_CORS_ORIGINS='*'` veya otomatik üretilen
    `AUTH_SECRET` için yapıldığı gibi, bu varsayılana sessizce düşüldüğünde
    hiçbir çalışma-zamanı uyarısı YOKTU — bu env değişkenini ayarlamayı
    unutan (ya da bilmeyen) herhangi bir kurulumda, kaynağa erişimi olan
    HERKES `lisans_uretici.py`yi bu bilinen secret ile çalıştırıp geçerli
    imzalı, istediği kamera limiti/süreye sahip bir lisans üretebilirdi. Artık
    süreç başına bir kez (log spam olmasın diye) uyarı basılıyor.

    .strip(): GERÇEK ÜRETİMDE BULUNAN HATA (2026-09-21, bkz. main.py::
    _kamera_anahtari_degeri'nin AYNI kök neden notu -- PTS_KAMERA_ANAHTARI'nda
    bulunan bu sınıf hata, PTS_LICENSE_SECRET için de aynı şekilde mümkündür):
    ortam değişkeni Windows'ta ayarlanırken sona görünmez bir satır sonu (\n)
    karışabilir. Bu fonksiyon HEM `uret()` (imzalama, lisans_uretici.py CLI)
    HEM DE `coz()` (doğrulama, sunucu) tarafından çağrıldığı için, tek bir
    yerde .strip() uygulamak iki tarafın da HER ZAMAN aynı (temizlenmiş)
    değeri kullanmasını garanti eder -- bu patch'ten SONRA üretilen/aktive
    edilen bir lisans için sorun yaşanmaz; ama değişkenin GERÇEKTEN sonunda
    bir \n varsa, bu patch'ten önce (eski, ham değerle) üretilmiş MEVCUT bir
    lisans, patch sonrası bir kez daha üretilip aktive edilmelidir (eski imza,
    artık temizlenmiş secret ile uyuşmayabilir)."""
    global _varsayilan_secret_uyarisi_yapildi
    deger = (os.getenv("PTS_LICENSE_SECRET") or "").strip()
    if deger:
        return deger
    if not _varsayilan_secret_uyarisi_yapildi:
        _varsayilan_secret_uyarisi_yapildi = True
        logger.warning(
            "PTS_LICENSE_SECRET ayarlanmamış — HERKESE AÇIK, kaynak kodda sabit bir geliştirme "
            "anahtarı kullanılıyor. Üretimde MUTLAKA benzersiz bir PTS_LICENSE_SECRET ortam "
            "değişkeni tanımlayın; aksi halde kaynağa erişimi olan biri geçerli imzalı lisans üretebilir."
        )
    return VARSAYILAN_GELISTIRME_SECRET


def _b64(veri: bytes) -> str:
    return base64.urlsafe_b64encode(veri).decode("ascii").rstrip("=")


def _b64_coz(veri: str) -> bytes:
    return base64.urlsafe_b64decode(veri + "=" * (-len(veri) % 4))


def cihaz_kodu() -> str:
    """Bu bilgisayara özgü, tekrarlanabilir bir tanımlayıcı üretir."""
    kaynak = f"{platform.node()}-{uuid.getnode()}-{platform.system()}"
    return hashlib.sha256(kaynak.encode("utf-8")).hexdigest()[:16].upper()


# ÜRÜNLEŞTİRME (2026-10-23): lisansla açılıp kapanan modüller. Lisansta
# "moduller" alanı YOKSA hepsi açıktır -- bu alandan önce üretilmiş tüm
# lisanslar (kendi sistem dahil) aynen çalışmaya devam eder. Alan varsa
# yalnızca listedekiler açılır (bkz. main.py::_modul_acik_mi).
MODULLER = {
    "led": "LED tabela (Huidu/seri port)",
    "bildirim": "Telegram / webhook bildirimleri",
    "mobil": "Mobil uygulama bildirimleri",
    "arvento": "Arvento filo / sürücü entegrasyonu",
    "vardiya_cizelgesi": "Vardiya çizelgesi (girişsiz vardiya)",
    "dahua_anpr": "Kamera ANPR okumasını birleştirme (Dahua)",
    "misafir_daveti": "Öz-hizmet hesabının kendi misafirini davet etmesi",
}

# Lisansta modül listesi YOKKEN de kapalı kalan modüller (2026-10-30): yalnız
# dış kurulumlar için yapılmış, mevcut sistemlerde (TPAO) hiç görünmemesi
# gereken özellikler. Açmak için lisans --modul ile açıkça listelemelidir.
VARSAYILAN_KAPALI = frozenset({"misafir_daveti"})


def modul_acik(ad: str, moduller: Optional[list]) -> bool:
    if moduller is None:
        return ad not in VARSAYILAN_KAPALI
    return ad in moduller


def modulleri_dogrula(moduller: Optional[list]) -> Optional[list]:
    if moduller is None:
        return None
    bilinmeyen = sorted(set(moduller) - set(MODULLER))
    if bilinmeyen:
        raise ValueError(f"Bilinmeyen modül: {', '.join(bilinmeyen)} (geçerli: {', '.join(MODULLER)})")
    return sorted(set(moduller))


def uret(musteri: str, kamera_limiti: int, gun: int, cihaz_kodu_deger: Optional[str] = None,
         moduller: Optional[list] = None) -> str:
    """İmzalı bir lisans anahtarı üretir (`PTS1.<govde>.<imza>` formatında)."""
    govde = _payload_olustur(musteri, kamera_limiti, gun, cihaz_kodu_deger, moduller)
    imza = _b64(hmac.new(secret_al().encode("utf-8"), govde.encode("ascii"), hashlib.sha256).digest())
    return f"{LISANS_VERSIYONU}.{govde}.{imza}"


def _payload_olustur(musteri: str, kamera_limiti: int, gun: int, cihaz_kodu_deger: Optional[str],
                     moduller: Optional[list] = None) -> str:
    if kamera_limiti < 1 or gun < 1:
        raise ValueError("Kamera limiti ve gün sayısı 1 veya daha büyük olmalıdır")
    payload = {
        "lisans_id": secrets.token_hex(8).upper(),
        "musteri": musteri.strip(),
        "cihaz_kodu": cihaz_kodu_deger.strip().upper() if cihaz_kodu_deger else None,
        "kamera_limiti": kamera_limiti,
        "baslangic_tarihi": date.today().isoformat(),
        "bitis_tarihi": (date.today() + timedelta(days=gun)).isoformat(),
    }
    moduller = modulleri_dogrula(moduller)
    if moduller is not None:
        payload["moduller"] = moduller
    return _b64(json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))


def imzali_uret(ozel_anahtar: bytes, musteri: str, kamera_limiti: int, gun: int,
                cihaz_kodu_deger: Optional[str] = None, moduller: Optional[list] = None) -> str:
    """Ed25519 ile imzalı lisans (`PTS2.<govde>.<imza>`). Yalnızca lisans
    verenin bilgisayarında, özel anahtarla çalışır (bkz. araclar/lisans_araci.py)."""
    govde = _payload_olustur(musteri, kamera_limiti, gun, cihaz_kodu_deger, moduller)
    imza = ed25519.imzala(ozel_anahtar, f"{IMZALI_LISANS_VERSIYONU}.{govde}".encode("ascii"))
    return f"{IMZALI_LISANS_VERSIYONU}.{govde}.{_b64(imza)}"


def _imzali_dogrula(govde: str, imza: str) -> None:
    if not ACIK_ANAHTAR_HEX:
        raise LisansGecersiz("Bu PTS sürümünde lisans doğrulama anahtarı tanımlı değil")
    try:
        imza_baytlari = _b64_coz(imza)
        acik = bytes.fromhex(ACIK_ANAHTAR_HEX)
    except ValueError:
        raise LisansGecersiz("Lisans anahtarı formatı geçersiz")
    if not ed25519.dogrula(acik, f"{IMZALI_LISANS_VERSIYONU}.{govde}".encode("ascii"), imza_baytlari):
        raise LisansGecersiz("Lisans imzası doğrulanamadı (anahtar değiştirilmiş veya başka bir lisans verene ait)")


def coz(anahtar: str, beklenen_cihaz_kodu: Optional[str] = None) -> dict:
    """Lisans anahtarını doğrular ve payload'ı döner. Geçersizse LisansGecersiz fırlatır.

    `beklenen_cihaz_kodu` verilirse ve lisans belirli bir cihaza kilitliyse
    (payload'da cihaz_kodu doluysa), o cihaz koduyla eşleşmiyorsa reddedilir."""
    try:
        versiyon, govde, imza = anahtar.strip().split(".", 2)
    except (ValueError, AttributeError):
        raise LisansGecersiz("Lisans anahtarı formatı geçersiz")
    if versiyon == IMZALI_LISANS_VERSIYONU:
        _imzali_dogrula(govde, imza)
    elif versiyon == LISANS_VERSIYONU:
        if not ESKI_LISANS_KABUL:
            raise LisansGecersiz("Eski tip (PTS1) lisans bu sürümde geçersiz; yeni lisans anahtarı isteyin")
        beklenen_imza = _b64(hmac.new(secret_al().encode("utf-8"), govde.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(imza, beklenen_imza):
            raise LisansGecersiz("Lisans imzası doğrulanamadı (anahtar değiştirilmiş veya yanlış secret ile üretilmiş)")
    else:
        raise LisansGecersiz(f"Bilinmeyen lisans sürümü: {versiyon}")

    try:
        payload = json.loads(_b64_coz(govde))
    except (ValueError, json.JSONDecodeError) as exc:
        raise LisansGecersiz("Lisans içeriği çözümlenemedi") from exc

    if beklenen_cihaz_kodu and payload.get("cihaz_kodu") and payload["cihaz_kodu"] != beklenen_cihaz_kodu:
        raise LisansGecersiz("Bu lisans başka bir cihaza kilitli")

    try:
        bitis = datetime.fromisoformat(payload["bitis_tarihi"]).date()
    except (KeyError, ValueError) as exc:
        raise LisansGecersiz("Lisans bitiş tarihi okunamadı") from exc
    if bitis < datetime.now().date():
        raise LisansGecersiz("Lisans süresi dolmuş")

    return payload
