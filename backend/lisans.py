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

VARSAYILAN_GELISTIRME_SECRET = "gelistirme-lisans-anahtari-degistir"
LISANS_VERSIYONU = "PTS1"

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
    süreç başına bir kez (log spam olmasın diye) uyarı basılıyor."""
    global _varsayilan_secret_uyarisi_yapildi
    deger = os.getenv("PTS_LICENSE_SECRET")
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


def uret(musteri: str, kamera_limiti: int, gun: int, cihaz_kodu_deger: Optional[str] = None) -> str:
    """İmzalı bir lisans anahtarı üretir (`PTS1.<govde>.<imza>` formatında)."""
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
    govde = _b64(json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))
    imza = _b64(hmac.new(secret_al().encode("utf-8"), govde.encode("ascii"), hashlib.sha256).digest())
    return f"{LISANS_VERSIYONU}.{govde}.{imza}"


def coz(anahtar: str, beklenen_cihaz_kodu: Optional[str] = None) -> dict:
    """Lisans anahtarını doğrular ve payload'ı döner. Geçersizse LisansGecersiz fırlatır.

    `beklenen_cihaz_kodu` verilirse ve lisans belirli bir cihaza kilitliyse
    (payload'da cihaz_kodu doluysa), o cihaz koduyla eşleşmiyorsa reddedilir."""
    try:
        versiyon, govde, imza = anahtar.strip().split(".", 2)
    except (ValueError, AttributeError):
        raise LisansGecersiz("Lisans anahtarı formatı geçersiz")
    if versiyon != LISANS_VERSIYONU:
        raise LisansGecersiz(f"Bilinmeyen lisans sürümü: {versiyon}")

    beklenen_imza = _b64(hmac.new(secret_al().encode("utf-8"), govde.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(imza, beklenen_imza):
        raise LisansGecersiz("Lisans imzası doğrulanamadı (anahtar değiştirilmiş veya yanlış secret ile üretilmiş)")

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
