"""backend/pdf_export.py için testler.

excel_export.py gibi bu modül de fastapi/sqlalchemy'ye bağımlı DEĞİL --
yalnızca reportlab ve Pillow kullanıyor, bu yüzden bu dosya da (depodaki
diğer birçok testin aksine) GERÇEKTEN çalıştırılıp doğrulanabildi.
"""
import os
from datetime import datetime

import pytest
from PIL import Image as PILImage

from backend import pdf_export


def _ornek_satir(**gecersizler):
    satir = {
        "id": 1,
        "plaka_no": "34 ABC 123",
        "ad": "Ahmet",
        "soyad": "Yılmaz",
        "site": "LOJMAN",
        "blok": "",
        "daire": "PERSONEL",
        "otopark": "",
        "nokta": "LOJMAN GİRİŞ",
        "gecis_tipi": "Giriş",
        "arac_tipi": "GÜVENLİK ŞEFLİĞİ",
        "tarih_saat": datetime(2026, 9, 17, 8, 4, 7),
        "notlar": "test notu",
        "goruntu_yolu": None,
    }
    satir.update(gecersizler)
    return satir


# ------------------------------------------------------------------
# Görsel küçültme/sıkıştırma (2026-09-18) -- toplu PDF raporunun dosya
# boyutunun binlerce tam çözünürlüklü görsel yüzünden şişmesini önler.
# ------------------------------------------------------------------

def test_kucuk_gorsel_akisi_dosya_yoksa_none_doner():
    assert pdf_export._kucuk_gorsel_akisi(None) is None
    assert pdf_export._kucuk_gorsel_akisi("/olmayan/bir/yol.jpg") is None


def test_kucuk_gorsel_akisi_bozuk_dosyada_cokmez(tmp_path):
    """Bozuk/eksik bir görsel dosyası TÜM rapor oluşturmayı çökertmemeli --
    yalnızca o satır için None dönüp yer tutucuya düşmeli."""
    bozuk = tmp_path / "bozuk.jpg"
    bozuk.write_bytes(b"bu bir JPEG degil")
    assert pdf_export._kucuk_gorsel_akisi(str(bozuk)) is None


def test_kucuk_gorsel_akisi_buyuk_gorseli_gercekten_kucultur(tmp_path):
    """KÖK SORUN: reportlab'ın Image flowable'ı bir dosya yoluyla
    çağrılırsa görseli küçük GÖSTERSE bile orijinal baytları PDF'e olduğu
    gibi gömer. Binlerce kayıt içeren bir raporda bu, dosyayı yüzlerce MB'a
    şişirirdi. Bu test, küçültmenin gerçekten dosya boyutunu (yalnızca
    görüntülenen boyutu değil) düşürdüğünü doğrular."""
    buyuk = tmp_path / "buyuk.jpg"
    # Sıkıştırmaya en dirençli durumu simüle etmek için rastgele gürültü
    # (düz renkli bir görsel gerçekçi olmayacak kadar kolay sıkışır).
    import random
    rastgele_veri = bytes(random.getrandbits(8) for _ in range(1920 * 1080 * 3 // 50))
    img = PILImage.frombytes("L", (1920 // 5, 1080 // 5), rastgele_veri[: (1920 // 5) * (1080 // 5)])
    img = img.convert("RGB").resize((1920, 1080))
    img.save(str(buyuk), format="JPEG", quality=95)

    kaynak_boyut = buyuk.stat().st_size
    akis = pdf_export._kucuk_gorsel_akisi(str(buyuk))
    assert akis is not None
    kucultulmus_boyut = len(akis.getvalue())
    assert kucultulmus_boyut < kaynak_boyut, "küçültme dosya boyutunu gerçekten düşürmeli"
    assert kucultulmus_boyut < 50 * 1024, "küçültülmüş bir görsel 50KB'ı aşmamalı (aksi halde binlerce kayıtlık bir raporda dosya yine şişer)"

    # Döndürülen akış GERÇEKTEN geçerli bir JPEG olmalı (yalnızca bayt sayısı değil).
    akis.seek(0)
    with PILImage.open(akis) as dogrulama:
        dogrulama.verify()


# ------------------------------------------------------------------
# "GEÇİŞ RAPORU" PDF çıktısı
# ------------------------------------------------------------------

def test_kayitlar_pdf_olustur_gecerli_pdf_uretir(tmp_path):
    dosya = tmp_path / "rapor.pdf"
    pdf_export.kayitlar_pdf_olustur(
        [_ornek_satir()], str(dosya),
        tarih_araligi_metni="Bu raporda 17.09.2026 - 18.09.2026 tarihleri arasındaki geçiş kayıtları listelenmektedir.",
    )
    assert dosya.exists()
    with open(dosya, "rb") as f:
        assert f.read(5) == b"%PDF-", "Gecerli bir PDF dosyasi baslik imzasiyla baslamali"


def test_kayitlar_pdf_olustur_gorselsiz_satirda_cokmez(tmp_path):
    """goruntu_yolu=None olan (görsel eklenmemiş bir kamera tespiti ya da
    manuel kayıt) bir satır, rapor oluşturmayı ÇÖKERTMEMELİ -- yerine bir
    yer tutucu ('Görsel yok') konmalı."""
    dosya = tmp_path / "rapor.pdf"
    pdf_export.kayitlar_pdf_olustur([_ornek_satir(goruntu_yolu=None)], str(dosya))
    assert dosya.exists()


def test_kayitlar_pdf_olustur_gorselli_ve_gorselsiz_karisik_satirlar(tmp_path):
    gorsel_yolu = tmp_path / "arac.jpg"
    PILImage.new("RGB", (640, 480), color=(80, 120, 160)).save(str(gorsel_yolu), format="JPEG")

    satirlar = [
        _ornek_satir(id=1, goruntu_yolu=str(gorsel_yolu)),
        _ornek_satir(id=2, goruntu_yolu=None),
        _ornek_satir(id=3, goruntu_yolu="/olmayan/yol.jpg"),
    ]
    dosya = tmp_path / "rapor.pdf"
    pdf_export.kayitlar_pdf_olustur(satirlar, str(dosya))
    assert dosya.exists()
    assert dosya.stat().st_size > 0


def test_kayitlar_pdf_olustur_bos_liste_ile_de_calisir(tmp_path):
    dosya = tmp_path / "rapor.pdf"
    pdf_export.kayitlar_pdf_olustur([], str(dosya), tarih_araligi_metni="Bu kriterlere uyan hiçbir geçiş kaydı bulunamadı.")
    assert dosya.exists()


def test_kayitlar_pdf_olustur_coklu_kayitla_dosya_boyutu_makul_kalir(tmp_path):
    """Kök risk: yüzlerce/binlerce kayıt + her biri bir görsel = küçültme
    olmasaydı devasa bir PDF. 50 kayıt (her biri kendi görseliyle) için
    dosyanın makul kalması (birkaç MB'ı geçmemesi) gerektiğini doğrular."""
    gorsel_yolu = tmp_path / "arac.jpg"
    import random
    rastgele_veri = bytes(random.getrandbits(8) for _ in range(640 * 480 * 3 // 10))
    img = PILImage.frombytes("L", (640 // 3, 480 // 3), rastgele_veri[: (640 // 3) * (480 // 3)])
    img = img.convert("RGB").resize((640, 480))
    img.save(str(gorsel_yolu), format="JPEG", quality=95)

    satirlar = [_ornek_satir(id=i, goruntu_yolu=str(gorsel_yolu)) for i in range(50)]
    dosya = tmp_path / "rapor.pdf"
    pdf_export.kayitlar_pdf_olustur(satirlar, str(dosya))
    boyut_mb = dosya.stat().st_size / (1024 * 1024)
    assert boyut_mb < 5, f"50 kayıtlık rapor {boyut_mb:.2f}MB -- küçültme çalışmıyor olabilir"


# ------------------------------------------------------------------
# Türkçe karakter desteği (2026-09-18) -- kullanıcı ekran görüntüsüyle
# bildirdi: reportlab'ın varsayılan Helvetica/Helvetica-Bold fontu (base14)
# yalnızca WinAnsiEncoding'i destekler; Türkçeye özgü "ı, İ, ş, Ş, ğ, Ğ"
# karakterleri bu kodlamada YOK. Sonuç, üretilen PDF'lerde "GEÇİŞ RAPORU"
# -> "GEÇ██ RAPORU", "Tanımsız Araç" -> "Tan█ms█z Araç" gibi bu harflerin
# yerine boş kare (.notdef glifi) basılmasıydı. Aşağıdaki testler, yalnızca
# "PDF üretildi mi"yi değil, PDF'i pdfplumber ile GERİ OKUYUP içindeki
# Türkçe metnin GERÇEKTEN doğru çıktığını doğruluyor.
# ------------------------------------------------------------------

def test_turkce_fontlari_kaydet_dosyalar_depoya_gomulu():
    """Font dosyaları depoda bulunmalı -- kullanıcının kendi Windows
    kurulumunda internet bağlantısı ya da ekstra font kurulumu
    GEREKTİRMEMELİ (bkz. backend/fonts/LISANS-DejaVu.txt)."""
    pdf_export._turkce_fontlari_kaydet()
    assert os.path.isfile(os.path.join(pdf_export._FONT_DIZINI, "DejaVuSans.ttf"))
    assert os.path.isfile(os.path.join(pdf_export._FONT_DIZINI, "DejaVuSans-Bold.ttf"))


def test_turkce_destekli_stiller_tum_stillerin_fontunu_degistirir():
    stiller = pdf_export._turkce_destekli_stiller()
    assert stiller["Normal"].fontName == pdf_export.FONT_NORMAL
    assert stiller["Title"].fontName == pdf_export.FONT_BOLD
    assert stiller["Heading2"].fontName == pdf_export.FONT_BOLD


def test_kayitlar_pdf_turkce_karakterler_dogru_render_edilir(tmp_path):
    """Kök neden regresyon testi: kullanıcının bildirdiği ekran görüntüsündeki
    TAM senaryoyu (başlık + sütun başlıkları + hücre değerleri, hepsi Türkçeye
    özgü karakterler içeriyor) yeniden üretip PDF'i geri okuyarak doğrular."""
    import pdfplumber

    satirlar = [_ornek_satir(
        ad="İhsan", soyad="Güçlü", site="RAPTEST SİTESİ", daire="PERSONEL",
        nokta="Nizamiye Kapısı", gecis_tipi="Giriş", arac_tipi="GÜVENLİK ŞEFLİĞİ",
    )]
    dosya = tmp_path / "turkce.pdf"
    pdf_export.kayitlar_pdf_olustur(satirlar, str(dosya), baslik="GEÇİŞ RAPORU")

    with pdfplumber.open(str(dosya)) as pdf:
        tam_metin = "\n".join(sayfa.extract_text() or "" for sayfa in pdf.pages)

    # NOT: "Nizamiye Kapısı" tek bir string olarak DEĞİL "Nizamiye" ve
    # "Kapısı" ayrı ayrı aranıyor -- dar "Nokta" sütunu bu metni iki satıra
    # sarıyor (Paragraph word-wrap), bu yüzden pdfplumber'ın satır bazlı
    # metin çıkarımı ikisini yan yana DEĞİL, diğer hücrelerin ilk satırlarının
    # arasına serpiştirilmiş olarak döner -- bu, Türkçe font düzeltmesinden
    # bağımsız, saf bir sütun genişliği/kelime kaydırma davranışı.
    for beklenen in (
        "GEÇİŞ RAPORU", "Adı", "Soyadı", "Geçiş Tipi", "Araç Tipi",
        "İhsan", "Güçlü", "Nizamiye", "Kapısı", "Giriş", "GÜVENLİK", "ŞEFLİĞİ",
    ):
        assert beklenen in tam_metin, (
            f"'{beklenen}' üretilen PDF'in metninde bulunamadı -- Türkçe karakter "
            "render sorunu (kök neden regresyonu) olabilir"
        )


def test_kayit_detay_pdf_turkce_karakterler_dogru_render_edilir(tmp_path):
    import pdfplumber
    from types import SimpleNamespace

    kayit = SimpleNamespace(
        plaka_no="34 ABC 123", tarih_saat=datetime(2026, 9, 17, 8, 4, 7),
        kamera_id="KAM-1", yon="giris", yetki_durumu="yetkili",
        guven_skoru=0.98, kisi_tip_anlik="personel", goruntu_yolu=None,
    )
    dosya = tmp_path / "detay.pdf"
    pdf_export.kayit_detay_pdf_olustur(kayit, str(dosya))

    with pdfplumber.open(str(dosya)) as pdf:
        tam_metin = "\n".join(sayfa.extract_text() or "" for sayfa in pdf.pages)

    for beklenen in ("Plaka Tanıma Kayıt Detayı", "Kişi/Tip:", "Yön:", "Bu kayıt için görsel bulunmuyor."):
        assert beklenen in tam_metin, f"'{beklenen}' üretilen PDF'in metninde bulunamadı"
