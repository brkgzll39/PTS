"""E-posta bildirimi (2026-10-31, günlük yönetici raporu için; bkz. main.py
"GÜNLÜK YÖNETİCİ RAPORU"). Bildirim ayarlarında tip="email", hedef=<adres>.

SMTP sunucusu ve hesabı, Telegram bot token'ı gibi ortam değişkenlerinden okunur
(panelde/veritabanında parola dolaşmaz):

    PTS_SMTP_SUNUCU     ör. smtp.kurum.gov.tr
    PTS_SMTP_PORT       varsayılan 587
    PTS_SMTP_GUVENLIK   starttls (varsayılan) | ssl | yok
    PTS_SMTP_KULLANICI  boşsa kimlik doğrulamasız gönderilir (iç ağ röle sunucusu)
    PTS_SMTP_PAROLA
    PTS_SMTP_GONDEREN   ör. pts@kurum.gov.tr (boşsa kullanıcı adı)
"""
import logging
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

logger = logging.getLogger("pts")

ADRES_DESENI = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _ayar(ad: str, varsayilan: str = "") -> str:
    return (os.getenv(ad) or varsayilan).strip()


def eposta_ayarli_mi() -> bool:
    return bool(_ayar("PTS_SMTP_SUNUCU"))


def eposta_gonder_sync(alici: str, konu: str, metin: str, ek_yolu: Optional[str] = None) -> "tuple[bool, Optional[str]]":
    sunucu = _ayar("PTS_SMTP_SUNUCU")
    if not sunucu:
        return False, "PTS_SMTP_SUNUCU ortam değişkeni ayarlanmamış (e-posta sunucusu)"
    if not ADRES_DESENI.match(alici or ""):
        return False, f"Geçersiz e-posta adresi: {alici!r}"
    guvenlik = _ayar("PTS_SMTP_GUVENLIK", "starttls").lower()
    try:
        port = int(_ayar("PTS_SMTP_PORT", "465" if guvenlik == "ssl" else "587"))
    except ValueError:
        return False, "PTS_SMTP_PORT sayı olmalı"
    kullanici, parola = _ayar("PTS_SMTP_KULLANICI"), _ayar("PTS_SMTP_PAROLA")
    ileti = EmailMessage()
    ileti["Subject"] = konu
    ileti["From"] = _ayar("PTS_SMTP_GONDEREN") or kullanici or f"pts@{sunucu}"
    ileti["To"] = alici
    ileti.set_content(metin)
    if ek_yolu:
        with open(ek_yolu, "rb") as f:
            ileti.add_attachment(f.read(), maintype="application", subtype="pdf", filename=os.path.basename(ek_yolu))
    try:
        if guvenlik == "ssl":
            baglanti = smtplib.SMTP_SSL(sunucu, port, timeout=20, context=ssl.create_default_context())
        else:
            baglanti = smtplib.SMTP(sunucu, port, timeout=20)
        with baglanti:
            if guvenlik == "starttls":
                baglanti.starttls(context=ssl.create_default_context())
            if kullanici:
                baglanti.login(kullanici, parola)
            baglanti.send_message(ileti)
        return True, None
    except smtplib.SMTPAuthenticationError:
        return False, "E-posta sunucusu kullanıcı adı/parolayı kabul etmedi"
    except Exception as exc:
        logger.warning("E-posta gönderilemedi (%s): %s", alici, exc)
        return False, f"E-posta gönderilemedi: {exc}"
