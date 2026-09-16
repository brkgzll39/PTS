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
import pytest
from pydantic import ValidationError

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


# ------------------------------------------------------------------
# plaka_normalize — stored-XSS/tutarsız-sanitizasyon regresyon testleri.
#
# 2026-09'da bulunan gerçek bir güvenlik açığı: KisiOlustur/KisiGuncelle/
# KaraListesiOlustur/KisiPlakaOlustur şemalarındaki plaka_no alanları
# yalnızca `.upper().strip()` yapıyordu — main.py'deki otomatik-kayıt yolunun
# (POST /kayitlar/otomatik) uyguladığı `re.sub(r"[^A-Za-z0-9 ]", ...)`
# karakter kısıtlaması burada YOKTU. Bu, kara listeye/kişiye
# `plaka_no="x');alert(1)//"` gibi bir değer eklenip frontend'de bu değerin
# bir HTML attribute'u içine JS string literali olarak gömüldüğü yerlerde
# (onclick="...('...')") çalıştırılabilmesine yol açıyordu. plaka_normalize
# artık TEK doğru kaynak olarak tüm şemalarda zorunlu kılınıyor.
# ------------------------------------------------------------------

@pytest.mark.parametrize("SemaSinifi, ekstra_alanlar", [
    (schemas.KisiPlakaOlustur, {}),
    (schemas.KaraListesiOlustur, {}),
    (schemas.KisiOlustur, {"ad_soyad": "Test Kişi", "tip": "personel"}),
])
def test_plaka_no_zararli_karakterleri_kabul_etmez(SemaSinifi, ekstra_alanlar):
    """Kara liste/kişi şemalarına HTML/JS özel karakterleri (', <, >, ;, ( vb.)
    içeren bir 'plaka' verilirse, bu karakterler main.py'deki otomatik-kayıt
    yoluyla AYNI kuralla (yalnızca harf/rakam/boşluk) atılmalı — sessizce
    kabul edilip veritabanına öylece yazılmamalı."""
    ornek = SemaSinifi(plaka_no="x');alert(1);//", **ekstra_alanlar)
    assert ornek.plaka_no == "XALERT1"
    assert "'" not in ornek.plaka_no
    assert "(" not in ornek.plaka_no
    assert ";" not in ornek.plaka_no


def test_plaka_no_sadece_zararli_karakterlerden_olusuyorsa_reddedilir():
    """Temizlik sonrası hiçbir geçerli karakter kalmıyorsa (ör. yalnızca
    noktalama/özel karakterlerden oluşan bir 'plaka'), sessizce boş bir
    plaka_no kaydetmek yerine doğrulama hatası verilmeli."""
    with pytest.raises(ValidationError):
        schemas.KaraListesiOlustur(plaka_no="';--")


def test_plaka_no_main_py_ile_ayni_kurala_gore_normalize_edilir():
    """schemas.py::plaka_normalize, main.py'nin otomatik-kayıt yolunda
    kullandığı `re.sub(r"[^A-Za-z0-9 ]", "", ...)` ile BİREBİR aynı kuralı
    uygulamalı — iki farklı giriş yolu (API'den elle ekleme vs. kameradan
    otomatik kayıt) aynı plakayı farklı normalize edip veritabanında iki
    farklı temsil olarak bitmemeli."""
    import re
    ham = "34 pep-347!"
    beklenen = re.sub(r"[^A-Za-z0-9 ]", "", ham).strip().upper()
    assert schemas.plaka_normalize(ham) == beklenen == "34 PEP347"


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
