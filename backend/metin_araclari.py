"""Küçük, bağımlılıksız metin yardımcıları.

Bu modül kasıtlı olarak cv2/fastapi/sqlalchemy gibi hiçbir ağır bağımlılığa
ihtiyaç duymaz; hem camera_reader.py (kare bazlı oy birikimi için plaka
benzerliği) hem main.py (bilinen plaka veritabanına karşı OCR hatası
düzeltmesi için) tarafından ortak kullanılır. Amaç: aynı mesafe hesaplama
mantığının iki yerde birbirinden bağımsız, zamanla birbirinden sapabilecek
iki kopyası olarak var olmaması (bu depoda daha önce başka dosyalarda görülen
"sessiz tekrar" hata sınıfının bir başka biçimi).
"""


from typing import Optional


def levenshtein_mesafesi(a: str, b: str) -> int:
    """İki dizge arasındaki düzenleme (Levenshtein) mesafesini hesaplar.

    Küçük plaka dizgeleri (7-8 karakter) için yazıldığından basit O(len(a)*len(b))
    dinamik programlama yeterlidir; harici bir kütüphaneye gerek yoktur.
    """
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la

    onceki = list(range(lb + 1))
    for i, ca in enumerate(a, start=1):
        simdi = [i] + [0] * lb
        for j, cb in enumerate(b, start=1):
            maliyet = 0 if ca == cb else 1
            simdi[j] = min(
                onceki[j] + 1,       # silme
                simdi[j - 1] + 1,    # ekleme
                onceki[j - 1] + maliyet,  # değiştirme (veya eşleşme)
            )
        onceki = simdi
    return onceki[lb]


# Sadece TEK karakterlik OCR hatalarını düzelt — bkz.
# main.py::_bilinen_plakaya_yakinlik_duzelt için kullanım bağlamı.
BILINEN_PLAKA_DUZELTME_MAX_MESAFE = 1


def en_yakin_bilinen_plakayi_bul(hedef: str, bilinen_plakalar) -> Optional[str]:
    """Saf eşleştirme mantığı (DB'den bağımsız, kolay birim testi için).

    `hedef` zaten `bilinen_plakalar` içindeyse, ya da tek bir en-yakın aday
    yoksa (aday yok ya da birden fazla aday eşit derecede yakın — yani
    belirsiz), None döner. Yalnızca TEK, KESİN bir en-yakın aday varsa o
    adayı döner.
    """
    if hedef in bilinen_plakalar:
        return None  # zaten tam eşleşiyor, düzeltmeye gerek yok

    en_yakin = None
    en_yakin_mesafe = None
    belirsiz = False
    for aday in bilinen_plakalar:
        if not aday:
            continue
        mesafe = levenshtein_mesafesi(hedef, aday)
        if mesafe > BILINEN_PLAKA_DUZELTME_MAX_MESAFE:
            continue
        if en_yakin_mesafe is None or mesafe < en_yakin_mesafe:
            en_yakin, en_yakin_mesafe = aday, mesafe
            belirsiz = False
        elif mesafe == en_yakin_mesafe:
            belirsiz = True  # birden fazla bilinen plaka eşit derecede yakın — riskli, düzeltme

    return en_yakin if (en_yakin is not None and not belirsiz) else None
