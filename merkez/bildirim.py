"""Merkezin satıcıya bildirim göndermesi: Telegram ve/veya e-posta.

Ortam değişkenleri:
  MERKEZ_TELEGRAM_TOKEN   BotFather'dan alınan bot anahtarı
  MERKEZ_TELEGRAM_SOHBET  bildirimin gideceği sohbet kimliği (virgülle birden çok)
  MERKEZ_SMTP_SUNUCU, MERKEZ_SMTP_PORT (587), MERKEZ_SMTP_KULLANICI, MERKEZ_SMTP_PAROLA,
  MERKEZ_SMTP_GONDEREN, MERKEZ_SMTP_ALICI (virgülle birden çok)
"""
import json
import logging
import os
import smtplib
import urllib.request
from email.message import EmailMessage

logger = logging.getLogger("merkez.bildirim")


def kanallar() -> list:
    k = []
    if os.getenv("MERKEZ_TELEGRAM_TOKEN") and os.getenv("MERKEZ_TELEGRAM_SOHBET"):
        k.append("telegram")
    if os.getenv("MERKEZ_SMTP_SUNUCU") and os.getenv("MERKEZ_SMTP_ALICI"):
        k.append("eposta")
    return k


def _telegram(metin: str) -> None:
    token = os.environ["MERKEZ_TELEGRAM_TOKEN"].strip()
    for sohbet in [s.strip() for s in os.environ["MERKEZ_TELEGRAM_SOHBET"].split(",") if s.strip()]:
        govde = json.dumps({"chat_id": sohbet, "text": metin[:4000]}, ensure_ascii=False).encode()
        istek = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=govde,
                                       headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(istek, timeout=15):
            pass


def _eposta(konu: str, metin: str) -> None:
    mesaj = EmailMessage()
    mesaj["Subject"] = konu
    mesaj["From"] = os.getenv("MERKEZ_SMTP_GONDEREN") or os.getenv("MERKEZ_SMTP_KULLANICI") or "pts-merkez@localhost"
    mesaj["To"] = os.environ["MERKEZ_SMTP_ALICI"]
    mesaj.set_content(metin)
    port = int(os.getenv("MERKEZ_SMTP_PORT") or 587)
    sunucu = os.environ["MERKEZ_SMTP_SUNUCU"]
    baglanti = smtplib.SMTP_SSL(sunucu, port, timeout=20) if port == 465 else smtplib.SMTP(sunucu, port, timeout=20)
    with baglanti as s:
        if port != 465:
            s.starttls()
        if os.getenv("MERKEZ_SMTP_KULLANICI"):
            s.login(os.environ["MERKEZ_SMTP_KULLANICI"], os.getenv("MERKEZ_SMTP_PAROLA", ""))
        s.send_message(mesaj)


def gonder(konu: str, metin: str) -> list:
    """Ayarlı tüm kanallara gönderir; hata verenlerin listesini döner (hata yutulur, loglanır)."""
    hatalar = []
    for kanal in kanallar():
        try:
            _telegram(f"{konu}\n\n{metin}") if kanal == "telegram" else _eposta(konu, metin)
        except Exception as exc:  # noqa: BLE001 - bir kanalın hatası diğerini engellemesin
            logger.warning("Bildirim gönderilemedi (%s): %s", kanal, exc)
            hatalar.append(f"{kanal}: {exc}")
    return hatalar
