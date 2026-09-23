"""backend/metin_araclari.py için birim testleri.

Bu modül kasıtlı olarak bağımlılıksızdır (cv2/fastapi/sqlalchemy gerektirmez),
bu yüzden hem çok kareli oy birleştirmede (camera_reader.py) hem de bilinen
plaka veritabanına karşı OCR düzeltmesinde (main.py) kullanılan ortak mesafe/
eşleştirme mantığı burada, DB veya kamera olmadan tam olarak doğrulanabilir.
"""
from backend.metin_araclari import (
    levenshtein_mesafesi, en_yakin_bilinen_plakayi_bul, sondan_bir_karakter_eksik_mi,
    plaka_hucresini_ayir,
)


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


# ------------------------------------------------------------------
# sondan_bir_karakter_eksik_mi (2026-09-18) -- fast_alpr'ın dedektör kutusunu
# kenar boşluksuz kırpması yüzünden OCR'ın son karakteri hiç görmeden bir
# okuma üretmesi (kullanıcının bildirdiği "02 AFP 552" -> "02 AFP 55" vakası).
# ------------------------------------------------------------------

def test_sondan_bir_karakter_eksik_gercek_vaka():
    assert sondan_bir_karakter_eksik_mi("02 AFP 55", "02 AFP 552") is True


def test_sondan_bir_karakter_eksik_ters_sirada_calismaz():
    """Fonksiyon (kisa, uzun) sırasıyla çağrılmalı -- (uzun, kisa) verilirse
    (parametreler ters), uzun.startswith(kisa) testi anlamsızlaşır ve False
    dönmelidir (çağıran kod bunu ele almalı, bkz. camera_reader.py::kazanan)."""
    assert sondan_bir_karakter_eksik_mi("02 AFP 552", "02 AFP 55") is False


def test_sondan_bir_karakter_eksik_ayni_dizgede_false():
    assert sondan_bir_karakter_eksik_mi("34 ABC 123", "34 ABC 123") is False


def test_sondan_bir_karakter_eksik_ortadan_farkliysa_false():
    """Fark SONDA değil ORTADA (harf grubuna bir harf eklenmiş) ise bu farklı
    bir hata sınıfıdır -- burada YAKALANMAMALI (yanlış pozitif riski)."""
    assert sondan_bir_karakter_eksik_mi("34 A 1234", "34 AB 1234") is False


def test_sondan_bir_karakter_eksik_iki_karakter_farkinda_false():
    """Yalnızca TAM OLARAK bir karakterlik uzunluk farkını hedefler."""
    assert sondan_bir_karakter_eksik_mi("34 AB 1", "34 AB 123") is False


# ------------------------------------------------------------------
# plaka_hucresini_ayir (2026-09-23) -- kullanıcı isteği "çoklu plaka tekrar
# eden isimler olarak düzenle": toplu içe aktarma şablonunun 'Plaka No'
# hücresine virgül/noktalı virgülle ayrılmış birden fazla plaka yazılabilmesi
# (aynı kişinin/birimin birden fazla aracı tek satırda, KisiPlaka olarak).
# ------------------------------------------------------------------

def test_plaka_hucresi_tek_plaka():
    assert plaka_hucresini_ayir("34 ABC 123") == ["34 ABC 123"]


def test_plaka_hucresi_virgulle_ayrilmis_iki_plaka():
    assert plaka_hucresini_ayir("34 ABC 123, 34 DEF 456") == ["34 ABC 123", "34 DEF 456"]


def test_plaka_hucresi_noktali_virgulle_ayrilmis():
    assert plaka_hucresini_ayir("34 ABC 123; 34 DEF 456") == ["34 ABC 123", "34 DEF 456"]


def test_plaka_hucresi_karisik_ayirici_ve_fazla_bosluk():
    assert plaka_hucresini_ayir("  34ABC123 ,, 34DEF456 ; ;06XYZ999  ") == ["34ABC123", "34DEF456", "06XYZ999"]


def test_plaka_hucresi_kucuk_harf_buyutulur():
    assert plaka_hucresini_ayir("34 abc 123") == ["34 ABC 123"]


def test_plaka_hucresi_gecersiz_karakterler_atilir():
    """Excel formül enjeksiyonu / özel karakterler (main.py'nin daha önce
    yaptığı re.sub(r"[^A-Za-z0-9 ]", ...) ile AYNI kural) sessizce atılır."""
    assert plaka_hucresini_ayir("34-ABC/123") == ["34ABC123"]


def test_plaka_hucresi_tekrar_eden_plaka_tekillesir():
    """Kopyala-yapıştır hatasıyla aynı plaka iki kez yazılırsa, aynı kişiye
    aynı ek plakadan iki kez eklenmemesi için tekilleştirilir."""
    assert plaka_hucresini_ayir("34 ABC 123, 34 ABC 123") == ["34 ABC 123"]


def test_plaka_hucresi_bos_veya_none_bos_liste_doner():
    assert plaka_hucresini_ayir("") == []
    assert plaka_hucresini_ayir(None) == []
    assert plaka_hucresini_ayir("   ") == []


def test_plaka_hucresi_sadece_gecersiz_parca_atlanir_digerleri_kalir():
    assert plaka_hucresini_ayir("34 ABC 123, ,,, 34 DEF 456") == ["34 ABC 123", "34 DEF 456"]
