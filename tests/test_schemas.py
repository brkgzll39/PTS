"""backend/schemas.py için regresyon testleri.

2026-09'da bulunan gerçek bir hata: bu dosyada birçok Pydantic şeması (ör.
KisiOlustur, KisiGuncelle, KisiCevap, KullaniciCevap) yanlışlıkla İKİ KEZ
tanımlanmıştı. Python, aynı isimle ikinci `class` tanımını sessizce öncekinin
üzerine yazar — hata fırlatmaz. Sonuç: dosyanın en altındaki (eksik) ikinci
tanımlar kazanıyordu ve "saat/gün bazlı ziyaretçi/personel erişimi" özelliği
(giris_saati_baslangic, giris_saati_bitis, izin_verilen_gunler) API katmanında
tamamen çalışmaz durumdaydı — veritabanı modelinde, iş mantığında
(_plaka_yetki_kontrol) ve arayüzde (index.html + app.js) tam destekleniyor
olmasına rağmen, çünkü API bu alanları ne kabul ediyor ne de geri
döndürüyordu. Bu test dosyası, bu sınıfın bir hatasının bir daha sessizce
geri dönmemesi için şemalardaki alanları doğrudan kontrol eder.

Bağımlılık: yalnızca pydantic (fastapi/sqlalchemy gerekmez).
"""
from backend import schemas


def test_kisi_olustur_saat_gun_alanlarini_icerir():
    alanlar = set(schemas.KisiOlustur.model_fields.keys())
    assert {"giris_saati_baslangic", "giris_saati_bitis", "izin_verilen_gunler"} <= alanlar


def test_kisi_guncelle_saat_gun_alanlarini_icerir():
    alanlar = set(schemas.KisiGuncelle.model_fields.keys())
    assert {"giris_saati_baslangic", "giris_saati_bitis", "izin_verilen_gunler"} <= alanlar


def test_kisi_cevap_saat_gun_alanlarini_ve_ek_plakalari_icerir():
    alanlar = set(schemas.KisiCevap.model_fields.keys())
    assert {"giris_saati_baslangic", "giris_saati_bitis", "izin_verilen_gunler", "ek_plakalar"} <= alanlar


def test_kullanici_cevap_olusturma_tarihini_icerir():
    assert "olusturma_tarihi" in schemas.KullaniciCevap.model_fields


def test_kisi_olustur_ornek_veriyle_calisir():
    """Frontend'in gönderdiği gerçek şekle yakın bir örnek: saat/gün kısıtlı ziyaretçi."""
    kisi = schemas.KisiOlustur(
        ad_soyad="Ahmet Yılmaz",
        plaka_no="  34 abc 123  ",
        tip="ziyaretci",
        giris_saati_baslangic="08:00",
        giris_saati_bitis="18:00",
        izin_verilen_gunler="0,1,2,3,4",
    )
    assert kisi.plaka_no == "34 ABC 123"  # büyük harf + baştaki/sondaki boşluk temizlenir
    assert kisi.giris_saati_baslangic == "08:00"
    assert kisi.izin_verilen_gunler == "0,1,2,3,4"


def test_schemas_dosyasinda_tekrarlanan_sinif_tanimi_yok():
    """Aynı sınıf adının dosyada birden fazla kez tanımlanmadığını doğrudan
    kaynak koddan kontrol eder — bu, bulunan asıl hatanın kendisiydi."""
    import ast
    import inspect

    kaynak = inspect.getsource(schemas)
    agac = ast.parse(kaynak)
    isimler = [d.name for d in agac.body if isinstance(d, ast.ClassDef)]
    tekrarlananlar = {isim for isim in isimler if isimler.count(isim) > 1}
    assert not tekrarlananlar, f"schemas.py içinde tekrar tanımlanmış sınıflar: {tekrarlananlar}"
