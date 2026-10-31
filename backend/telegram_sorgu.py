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
    "• Plaka (ör. 34ABC123 ya da \"34 ABC 123 içeride mi\"): araç içeride mi, kimin, son geçişleri\n"
    "• Plakanın bir kısmı (ör. ABC12): benzer plakalar\n"
    "• içeride: içerideki araç ve ziyaretçi sayısı\n"
    "• özet: bugünün geçiş özeti\n"
    "• alarmlar: okunmamış son alarmlar\n"
    "• yardım: bu mesaj"
)

_TR_KUCUK = str.maketrans("İIŞĞÜÖÇ", "iışğüöç")


def _kucuk(metin: str) -> str:
    return metin.translate(_TR_KUCUK).lower()


_TR_BUYUK = str.maketrans("iıüöçşğ", "İIÜÖÇŞĞ")
# Cümlenin içindeki tam Türk plakası: "Plaka 34 MRU 811 içeride mi" -> 34MRU811
_PLAKA_DESENI = re.compile(r"(?<![0-9A-Z])(\d{2})\s*([A-Z]{1,3})\s*(\d{2,5})(?![0-9A-Z])")


def komut_coz(metin: str) -> tuple:
    """Mesajı (komut, argüman) çiftine çevirir: yardim | iceride | ozet | alarmlar | plaka | bilinmiyor.

    Görevli doğal cümle yazar (2026-10-31, sahada: "Plaka 34 MRU 811 içeride mi" anlaşılmadı):
    önce cümlenin içinde tam plaka aranır; yoksa rakam içeren kısa bir kelime plaka parçası
    sayılır; o da yoksa anahtar kelimeler cümlenin herhangi bir yerinde aranır."""
    ham = (metin or "").strip()
    kelimeler = re.findall(r"[0-9a-zçğıöşü]+", _kucuk(ham))
    if not kelimeler or kelimeler[0] in ("start", "yardım", "yardim", "help"):
        return "yardim", None
    buyuk = ham.translate(_TR_BUYUK).upper()
    m = _PLAKA_DESENI.search(buyuk)
    if m:
        return "plaka", "".join(m.groups())
    parca = [w for w in re.findall(r"[0-9A-Z]+", buyuk) if re.search(r"\d", w) and 3 <= len(w) <= 10]
    if parca:
        return "plaka", max(parca, key=len)
    for kelime in kelimeler:
        if kelime.startswith(("içeri", "iceri", "içerd", "icerd")):
            return "iceride", None
        if kelime.startswith(("özet", "ozet", "rapor", "bugün", "bugun")):
            return "ozet", None
        if kelime.startswith(("alarm", "uyarı", "uyari")):
            return "alarmlar", None
        if kelime.startswith(("yardım", "yardim")):
            return "yardim", None
    return "bilinmiyor", ham
