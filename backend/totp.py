"""İki adımlı doğrulama için zaman tabanlı tek kullanımlık kod (TOTP, RFC 6238).

2026-10-23 (kullanıcı onayı): panel artık Tailscale üzerinden telefondan da
açılıyor; yönetici parolası ele geçirilse bile telefondaki doğrulama
uygulamasının (Google/Microsoft Authenticator vb.) 6 haneli kodu olmadan
girilemesin. Harici paket gerekmez (yalnız standart kütüphane): 30 sn'lik
adım, 6 hane, HMAC-SHA1 -- tüm yaygın uygulamaların varsayılanı.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import Optional
from urllib.parse import quote

ADIM_SN = 30
HANE = 6


def gizli_uret() -> str:
    """160 bit rastgele anahtar, base32 (uygulamaya elle de yazılabilir)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def kod(gizli: str, zaman: Optional[float] = None) -> str:
    anahtar = base64.b32decode(gizli.upper() + "=" * (-len(gizli) % 8))
    sayac = int((time.time() if zaman is None else zaman) // ADIM_SN)
    ozet = hmac.new(anahtar, struct.pack(">Q", sayac), hashlib.sha1).digest()
    kaydir = ozet[-1] & 0x0F
    deger = struct.unpack(">I", ozet[kaydir:kaydir + 4])[0] & 0x7FFFFFFF
    return str(deger % 10 ** HANE).zfill(HANE)


def dogrula(gizli: str, girilen: str, zaman: Optional[float] = None, pencere: int = 1) -> bool:
    """Telefon saatinin ±`pencere` adım (30 sn) kaymasını tolere eder."""
    girilen = "".join(ch for ch in (girilen or "") if ch.isdigit())
    if len(girilen) != HANE or not gizli:
        return False
    simdi = time.time() if zaman is None else zaman
    return any(hmac.compare_digest(kod(gizli, simdi + k * ADIM_SN), girilen) for k in range(-pencere, pencere + 1))


def otpauth_uri(gizli: str, hesap: str, yayinci: str = "PTS") -> str:
    """Doğrulama uygulamasının QR kodundan okuyacağı adres."""
    etiket = quote(f"{yayinci}:{hesap}", safe=":")
    return f"otpauth://totp/{etiket}?secret={gizli}&issuer={quote(yayinci)}&digits={HANE}&period={ADIM_SN}"
