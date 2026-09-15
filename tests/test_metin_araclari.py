"""backend/metin_araclari.py için birim testleri.

Bu modül kasıtlı olarak bağımlılıksızdır (cv2/fastapi/sqlalchemy gerektirmez),
bu yüzden hem çok kareli oy birleştirmede (camera_reader.py) hem de bilinen
plaka veritabanına karşı OCR düzeltmesinde (main.py) kullanılan ortak mesafe/
eşleştirme mantığı burada, DB veya kamera olmadan tam olarak doğrulanabilir.
"""
from backend.metin_araclari import levenshtein_mesafesi, en_yakin_bilinen_plakayi_bul


def test_levenshtein_ayni_dizgeler_sifir_doner():
    assert levenshtein_mesafesi("34ABC123", "34ABC123") == 0


def test_levenshtein_tek_karakter_farki():
    assert levenshtein_mesafesi("34ABC123", "34ABC128") == 1


def test_levenshtein_bos_dizge():
    assert levenshtein_mesafesi("", "ABC") == 3
    assert levenshtein_mesafesi("ABC", "") == 3
    assert levenshtein_mesafesi("", "") == 0


def test_levenshtein_ekleme_silme_degistirme_karisik():
    # "kitten" -> "sitting": klasik örnek, mesafe 3
    assert levenshtein_mesafesi("kitten", "sitting") == 3


def test_en_yakin_bilinen_plaka_tam_eslesme_varsa_none_doner():
    """Zaten tam eşleşen bir plaka için 'düzeltme' önerilmemeli (gerek yok)."""
    assert en_yakin_bilinen_plakayi_bul("34ABC123", {"34ABC123", "06XYZ999"}) is None


def test_en_yakin_bilinen_plaka_tek_karakter_hatasini_bulur():
    sonuc = en_yakin_bilinen_plakayi_bul("34ABC128", {"34ABC123", "06XYZ999"})
    assert sonuc == "34ABC123"


def test_en_yakin_bilinen_plaka_esik_uzeri_mesafeyi_reddeder():
    """İki karakter farkı (varsayılan eşik=1'in üzerinde) düzeltilmemeli —
    yanlışlıkla tamamen farklı bir araca erişim verme riski çok yüksek olurdu."""
    sonuc = en_yakin_bilinen_plakayi_bul("34ABC199", {"34ABC123"})  # 2 karakter farklı
    assert sonuc is None


def test_en_yakin_bilinen_plaka_belirsizlikte_duzeltmez():
    """İki farklı bilinen plaka aynı mesafede eşit derecede yakınsa (belirsiz),
    güvenlik gereği HİÇBİRİNE düzeltilmemeli."""
    # "34ABC120" hem "34ABC123" hem "34ABC121"'e tam olarak 1 mesafede.
    sonuc = en_yakin_bilinen_plakayi_bul("34ABC120", {"34ABC123", "34ABC121"})
    assert sonuc is None


def test_en_yakin_bilinen_plaka_aday_yoksa_none_doner():
    assert en_yakin_bilinen_plakayi_bul("34ABC128", set()) is None
    assert en_yakin_bilinen_plakayi_bul("34ABC128", {"06ZZZ999"}) is None
