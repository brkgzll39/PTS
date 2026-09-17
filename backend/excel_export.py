"""Kayıtları ve kişileri .xlsx (Excel) formatında dışa aktarma."""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

BASLIK_DOLGU = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
BASLIK_YAZI = Font(color="FFFFFF", bold=True)


def _guvenli_hucre(deger):
    """Excel/CSV formül enjeksiyonunu engeller: kullanıcı girdisi '=','+','-','@' ile başlıyorsa kaçış karakteri eklenir."""
    if isinstance(deger, str) and deger[:1] in ("=", "+", "-", "@"):
        return "'" + deger
    return deger


def _baslik_satiri_bicimlendir(ws, sutun_sayisi):
    for col_no in range(1, sutun_sayisi + 1):
        hucre = ws.cell(row=1, column=col_no)
        hucre.fill = BASLIK_DOLGU
        hucre.font = BASLIK_YAZI
        hucre.alignment = Alignment(horizontal="center")


def kayitlar_excel_olustur(satirlar: list, dosya_yolu: str) -> str:
    """`satirlar`: main.py::_kayitlari_rapor_satirlari'nin ürettiği, her biri
    bir geçiş kaydını temsil eden düz (plain) sözlüklerden oluşan liste.

    Sütun düzeni (2026-09-18), kullanıcının paylaştığı bir referans ürünün
    "GEÇİŞ RAPORU" Excel çıktısıyla BİREBİR eşleşecek şekilde tasarlandı:
    Plaka/Adı/Soyadı/Site/Blok/Daire/Otopark/Nokta/Geçiş Tipi/Araç Tipi/
    Tarih/Notlar. "ID" en başa, bizim sistemimize özgü ekstra bir sütun
    olarak eklendi (kayda geri dönüp bakabilmek için faydalı, referansta
    yok). "Blok" ve "Otopark" bu sistemde MODELLENMEDİĞİ için her zaman
    boştur -- var olmayan bir veri asla uydurulmaz (bkz. main.py'deki not)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Geçiş Raporu"

    basliklar = [
        "ID", "Plaka", "Adı", "Soyadı", "Site", "Blok", "Daire", "Otopark",
        "Nokta", "Geçiş Tipi", "Araç Tipi", "Tarih", "Notlar",
    ]
    ws.append(basliklar)
    _baslik_satiri_bicimlendir(ws, len(basliklar))

    for s in satirlar:
        ws.append([
            s["id"],
            _guvenli_hucre(s["plaka_no"]),
            _guvenli_hucre(s["ad"]),
            _guvenli_hucre(s["soyad"]),
            _guvenli_hucre(s["site"]),
            _guvenli_hucre(s["blok"]),
            _guvenli_hucre(s["daire"]),
            _guvenli_hucre(s["otopark"]),
            _guvenli_hucre(s["nokta"]),
            s["gecis_tipi"],
            _guvenli_hucre(s["arac_tipi"]),
            s["tarih_saat"].strftime("%d.%m.%Y %H:%M:%S"),
            _guvenli_hucre(s["notlar"]),
        ])

    for i, baslik in enumerate(basliklar, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(10, len(baslik) + 4)
    ws.column_dimensions[get_column_letter(basliklar.index("Notlar") + 1)].width = 35

    ws.freeze_panes = "A2"
    wb.save(dosya_yolu)
    return dosya_yolu


def kisiler_excel_olustur(kisiler: list, dosya_yolu: str) -> str:
    wb = Workbook()
    ws = wb.active
    ws.title = "Kişiler"

    basliklar = [
        "ID", "Ad Soyad", "Plaka No", "Tip", "Telefon",
        "Daire/Departman", "Aktif", "Başlangıç", "Bitiş",
    ]
    ws.append(basliklar)
    _baslik_satiri_bicimlendir(ws, len(basliklar))

    for k in kisiler:
        ws.append([
            k.id,
            _guvenli_hucre(k.ad_soyad),
            _guvenli_hucre(k.plaka_no),
            k.tip,
            _guvenli_hucre(k.telefon or ""),
            _guvenli_hucre(k.daire_departman or ""),
            "Evet" if k.aktif else "Hayır",
            k.baslangic_tarihi.strftime("%d.%m.%Y") if k.baslangic_tarihi else "",
            k.bitis_tarihi.strftime("%d.%m.%Y") if k.bitis_tarihi else "",
        ])

    for i, baslik in enumerate(basliklar, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(14, len(baslik) + 4)

    ws.freeze_panes = "A2"
    wb.save(dosya_yolu)
    return dosya_yolu


# Bu başlıklar, main.py::toplu_kisi_import'un normalize ettikten sonra
# BEKLEDİĞİ sütun adlarıyla (ad_soyad, plaka_no, tip, telefon,
# daire_departman) BİREBİR eşleşecek şekilde seçildi -- normalizasyon
# yalnızca küçük harfe çevirip BOŞLUKLARI alt çizgiyle değiştiriyor (bkz.
# toplu_kisi_import), bu yüzden başlıkta "/" gibi başka bir ayraç
# KULLANILAMAZ (örn. "Daire/Departman" "daire/departman" olur, beklenen
# "daire_departman" ile eşleşmez -- bu yüzden burada "Daire Departman").
_ICE_AKTARMA_SABLONU_BASLIKLARI = ["Ad Soyad", "Plaka No", "Tip", "Telefon", "Daire Departman"]
_ICE_AKTARMA_GECERLI_TIPLER = ("abone", "personel", "ziyaretci")


def kisi_ice_aktarma_sablonu_olustur(dosya_yolu: str) -> str:
    """Kullanıcı talebi (2026-09-18): personel (ve genel olarak abone/
    ziyaretçi) kaydını toplu eklemek için doldurulup `POST
    /kisiler/toplu-import`'a geri yüklenecek, doğru başlıklarla hazır bir
    Excel şablonu. İki sayfa içerir: doldurulacak "Kişiler" sayfası (örnek
    satırlarla ve "Tip" sütununda açılır liste doğrulamasıyla) ve her
    sütunu açıklayan salt-okunur bir "Açıklama" sayfası."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Kişiler"
    ws.append(_ICE_AKTARMA_SABLONU_BASLIKLARI)
    _baslik_satiri_bicimlendir(ws, len(_ICE_AKTARMA_SABLONU_BASLIKLARI))

    # Görevlinin doldururken referans alabileceği, AÇIKÇA örnek olduğu
    # belirtilen iki satır -- silinip üzerine gerçek veriler yazılabilir.
    ornek_satirlar = [
        ["ÖRNEK — SİLİP ÜZERİNE YAZINIZ", "34 ABC 123", "personel", "05XX XXX XX XX", "GÜVENLİK ŞEFLİĞİ"],
        ["ÖRNEK — SİLİP ÜZERİNE YAZINIZ", "34 DEF 456", "abone", "05XX XXX XX XX", "A Blok 12"],
    ]
    for satir in ornek_satirlar:
        ws.append(satir)

    # "Tip" sütunu için açılır liste doğrulaması -- yalnızca 3 geçerli
    # değerden birini yazmayı kolaylaştırır; toplu_kisi_import GEÇERSİZ bir
    # değeri sessizce "abone"ya çeviriyor (bkz. o fonksiyonun kendi notu),
    # bu yüzden burada yanlış yazımı BAŞTAN önlemek özellikle değerlidir.
    tip_dogrulama = DataValidation(
        type="list",
        formula1=f'"{",".join(_ICE_AKTARMA_GECERLI_TIPLER)}"',
        allow_blank=False,
        showDropDown=False,  # openpyxl/Excel XML tersten çalışır: False = açılır oku GÖSTER
        showErrorMessage=True,
    )
    tip_dogrulama.error = "Tip yalnızca 'abone', 'personel' veya 'ziyaretci' olabilir."
    tip_dogrulama.errorTitle = "Geçersiz Tip"
    ws.add_data_validation(tip_dogrulama)
    tip_sutun_harfi = get_column_letter(_ICE_AKTARMA_SABLONU_BASLIKLARI.index("Tip") + 1)
    tip_dogrulama.add(f"{tip_sutun_harfi}2:{tip_sutun_harfi}500")

    for i, baslik in enumerate(_ICE_AKTARMA_SABLONU_BASLIKLARI, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(16, len(baslik) + 4)
    ws.column_dimensions["A"].width = 32
    ws.freeze_panes = "A2"

    aciklama = wb.create_sheet("Açıklama")
    aciklama.append(["Sütun", "Zorunlu mu?", "Açıklama"])
    _baslik_satiri_bicimlendir(aciklama, 3)
    aciklama_satirlari = [
        ("Ad Soyad", "Evet", "Kişinin (personel/abone/ziyaretçi) tam adı."),
        ("Plaka No", "Evet", "Örn. '34 ABC 123'. Aynı kişinin birden fazla aracı varsa, kaydı ekledikten sonra panelden Kişiler sekmesinden ek plaka eklenebilir."),
        ("Tip", "Evet", "'abone' (site sakini), 'personel' veya 'ziyaretci' olmalı — açılır listeden seçin. Geçersiz/boş bir değer sessizce 'abone' olarak kaydedilir, bu yüzden dikkatli seçin."),
        ("Telefon", "Hayır", "Boş bırakılabilir."),
        ("Daire Departman", "Hayır", "Abone için daire/blok bilgisi (örn. 'A Blok 12'), personel için departman adı (örn. 'ÜRETİM MÜDÜRLÜĞÜ'). Boş bırakılabilir."),
    ]
    for satir in aciklama_satirlari:
        aciklama.append(list(satir))
    aciklama.append([])
    aciklama.append(["Not: İlk satır (başlık) SİLİNMEMELİ. Örnek olarak işaretlenmiş satırlar üzerine yazılabilir ya da silinebilir."])
    for i, genislik in enumerate((22, 14, 90), 1):
        aciklama.column_dimensions[get_column_letter(i)].width = genislik

    wb.save(dosya_yolu)
    return dosya_yolu
