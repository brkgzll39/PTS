"""backend/excel_export.py için testler.

Bu modül (main.py'nin aksine) fastapi/sqlalchemy'ye bağımlı DEĞİL --
yalnızca openpyxl kullanıyor. Bu yüzden (depodaki diğer birçok testin aksine)
bu dosya GERÇEKTEN çalıştırılıp doğrulanabildi (bkz. README'deki
"Kalıcı Test Altyapısı" bölümündeki, sandbox'ta fastapi/sqlalchemy'nin
kurulu olmadığına dair not -- bu iki modül o kısıtlamanın DIŞINDA kalıyor).
"""
from datetime import datetime

import openpyxl
import pytest

from backend import excel_export


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
# "GEÇİŞ RAPORU" Excel çıktısı (2026-09-18) -- kullanıcının paylaştığı
# referans ürünün rapor biçimine yaklaştırma kararı.
# ------------------------------------------------------------------

def test_kayitlar_excel_basliklari_referans_rapor_ile_eslesir(tmp_path):
    """Kullanıcının paylaştığı referans "GEÇİŞ RAPORU" Excel çıktısının
    başlık satırı: Plaka, Adı, Soyadı, Site, Blok, Daire, Otopark, Nokta,
    Geçiş Tipi, Araç Tipi, Tarih, Notlar. Bizim raporumuz bunu birebir
    içerir; başa yalnızca kendi sistemimize özgü "ID" sütunu eklenir."""
    dosya = tmp_path / "kayitlar.xlsx"
    excel_export.kayitlar_excel_olustur([_ornek_satir()], str(dosya))

    wb = openpyxl.load_workbook(str(dosya))
    ws = wb.active
    basliklar = [h.value for h in ws[1]]
    assert basliklar == [
        "ID", "Plaka", "Adı", "Soyadı", "Site", "Blok", "Daire", "Otopark",
        "Nokta", "Geçiş Tipi", "Araç Tipi", "Tarih", "Notlar",
    ]
    assert ws.title == "Geçiş Raporu"


def test_kayitlar_excel_veri_satiri_dogru_yazilir(tmp_path):
    dosya = tmp_path / "kayitlar.xlsx"
    excel_export.kayitlar_excel_olustur([_ornek_satir()], str(dosya))

    wb = openpyxl.load_workbook(str(dosya))
    ws = wb.active
    satir = [h.value for h in ws[2]]
    assert satir == [
        1, "34 ABC 123", "Ahmet", "Yılmaz", "LOJMAN", None, "PERSONEL", None,
        "LOJMAN GİRİŞ", "Giriş", "GÜVENLİK ŞEFLİĞİ", "17.09.2026 08:04:07", "test notu",
    ]


def test_kayitlar_excel_formul_enjeksiyonu_engellenir(tmp_path):
    """Kamera/OCR ya da kişi kaydından gelen bir metin '=', '+', '-' veya '@'
    ile başlıyorsa Excel'de formül olarak YORUMLANMAMALI (bkz.
    excel_export._guvenli_hucre)."""
    dosya = tmp_path / "kayitlar.xlsx"
    excel_export.kayitlar_excel_olustur(
        [_ornek_satir(ad="=CMD('zararli')", notlar="+1+1")], str(dosya)
    )
    wb = openpyxl.load_workbook(str(dosya))
    ws = wb.active
    satir = [h.value for h in ws[2]]
    assert satir[2] == "'=CMD('zararli')"
    assert satir[-1] == "'+1+1"


def test_kayitlar_excel_bos_liste_ile_de_calisir(tmp_path):
    """Filtreye uyan hiçbir kayıt yoksa da rapor (yalnızca başlık satırıyla)
    hatasız üretilmeli -- boş bir sonuç, dışa aktarma özelliğini bozmamalı."""
    dosya = tmp_path / "kayitlar.xlsx"
    excel_export.kayitlar_excel_olustur([], str(dosya))
    wb = openpyxl.load_workbook(str(dosya))
    ws = wb.active
    assert ws.max_row == 1


# ------------------------------------------------------------------
# Personel/abone/ziyaretçi toplu içe aktarma ŞABLONU (2026-09-18)
# ------------------------------------------------------------------

def _basliklari_normalize_et(basliklar):
    # main.py::toplu_kisi_import'un YAPTIĞI normalizasyonun birebir aynısı --
    # şablonun bu ayrı, bağımsız kopyayla hâlâ eşleştiğini doğrulamak için.
    return [str(b).strip().lower().replace(" ", "_") if b else "" for b in basliklar]


def test_ice_aktarma_sablonu_basliklari_toplu_import_ile_eslesir(tmp_path):
    """Şablonun ürettiği başlıklar, main.py::toplu_kisi_import'un normalize
    ettikten sonra BEKLEDİĞİ 'ad_soyad', 'plaka_no', 'tip', 'telefon',
    'daire_departman' sütunlarıyla birebir eşleşmeli -- aksi halde kullanıcı
    şablonu hiç değiştirmeden geri yüklese bile içe aktarma başarısız olurdu."""
    dosya = tmp_path / "sablon.xlsx"
    excel_export.kisi_ice_aktarma_sablonu_olustur(str(dosya))

    wb = openpyxl.load_workbook(str(dosya))
    ws = wb["Kişiler"]
    basliklar_ham = [h.value for h in ws[1]]
    basliklar = _basliklari_normalize_et(basliklar_ham)
    for zorunlu in ("ad_soyad", "plaka_no", "tip"):
        assert zorunlu in basliklar, f"'{zorunlu}' şablonda eksik -- içe aktarma her zaman başarısız olurdu"
    assert "telefon" in basliklar
    assert "daire_departman" in basliklar


def test_ice_aktarma_sablonu_ornek_satirlari_gecerli_tip_kullanir(tmp_path):
    """Şablondaki örnek satırların 'tip' değeri, toplu_kisi_import'un kabul
    ettiği GEÇERLİ değerlerden biri olmalı -- kullanıcı örneği hiç
    değiştirmeden yanlışlıkla yüklerse bile sessizce 'abone'ya
    düşürülmemeli (bkz. toplu_kisi_import'un aynı davranışı)."""
    dosya = tmp_path / "sablon.xlsx"
    excel_export.kisi_ice_aktarma_sablonu_olustur(str(dosya))
    wb = openpyxl.load_workbook(str(dosya))
    ws = wb["Kişiler"]
    basliklar = [h.value for h in ws[1]]
    tip_idx = basliklar.index("Tip")
    for satir in ws.iter_rows(min_row=2, values_only=True):
        assert satir[tip_idx] in ("abone", "personel", "ziyaretci")


def test_ice_aktarma_sablonu_aciklama_sayfasi_var(tmp_path):
    dosya = tmp_path / "sablon.xlsx"
    excel_export.kisi_ice_aktarma_sablonu_olustur(str(dosya))
    wb = openpyxl.load_workbook(str(dosya))
    assert "Açıklama" in wb.sheetnames
    aciklama = wb["Açıklama"]
    metin = "\n".join(str(c.value) for row in aciklama.iter_rows() for c in row if c.value)
    assert "ad_soyad" not in metin.lower() or "Ad Soyad" in metin  # başlıklar okunabilir Türkçe biçimde açıklanır
    assert "abone" in metin and "personel" in metin and "ziyaretci" in metin


def test_ice_aktarma_sablonu_tip_sutununda_veri_dogrulamasi_var(tmp_path):
    """'Tip' sütununa açılır liste (data validation) eklenmiş olmalı --
    aksi halde kullanıcı serbest metin yazıp typo yapabilir ve bu, sessizce
    'abone'ya düşer (bkz. toplu_kisi_import)."""
    dosya = tmp_path / "sablon.xlsx"
    excel_export.kisi_ice_aktarma_sablonu_olustur(str(dosya))
    wb = openpyxl.load_workbook(str(dosya))
    ws = wb["Kişiler"]
    assert len(ws.data_validations.dataValidation) >= 1
    dogrulama = ws.data_validations.dataValidation[0]
    assert dogrulama.type == "list"
    for tip in ("abone", "personel", "ziyaretci"):
        assert tip in dogrulama.formula1
