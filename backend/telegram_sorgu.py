"""Telegram'dan soru sorma (2026-10-31, kullanıcı isteği): yetkili kişi bota yazar,
PTS cevap verir. Yalnız Bildirim ayarlarında tip="telegram" olarak kayıtlı sohbetlere
(chat_id) cevap verilir; diğerlerine yalnızca "yetkili değil" denir. Cevaplar
main.py::_telegram_sorgu_cevabi'nda veritabanından hazırlanır; burada yalnız mesaj
yorumlanır. Mesajlar uzun yoklamayla (getUpdates) alınır: botta webhook tanımlıysa
ya da aynı bot başka bir programda da dinleniyorsa Telegram ikisine birden vermez.
"""
import re

YARDIM = (
    "PTS sorgu botu. Yazabilecekleriniz:\n"
    "• Plaka (ör. 34ABC123 ya da 34 ABC 123): araç içeride mi, kimin, son geçişleri\n"
    "• Plakanın bir kısmı (ör. ABC12): benzer plakalar\n"
    "• içeride: içerideki araç ve ziyaretçi sayısı\n"
    "• özet: bugünün geçiş özeti\n"
    "• alarmlar: okunmamış son alarmlar\n"
    "• yardım: bu mesaj"
)

_TR_KUCUK = str.maketrans("İIŞĞÜÖÇ", "iışğüöç")


def _kucuk(metin: str) -> str:
    return metin.translate(_TR_KUCUK).lower()


def komut_coz(metin: str) -> tuple:
    """Mesajı (komut, argüman) çiftine çevirir: yardim | iceride | ozet | alarmlar | plaka | bilinmiyor."""
    ham = (metin or "").strip()
    sade = _kucuk(ham).lstrip("/").split("@")[0].strip()
    if sade in ("start", "yardım", "yardim", "help", "?", ""):
        return "yardim", None
    if sade.startswith(("içeride", "iceride", "içerdekiler", "içeridekiler", "iceridekiler")):
        return "iceride", None
    if sade in ("özet", "ozet", "rapor", "bugün", "bugun"):
        return "ozet", None
    if sade.startswith(("alarm", "uyarı", "uyari")):
        return "alarmlar", None
    plaka = re.sub(r"[^A-Za-z0-9]", "", ham).upper()
    if 3 <= len(plaka) <= 10 and re.search(r"\d", plaka) and len(ham) <= 14:
        return "plaka", plaka
    return "bilinmiyor", ham
