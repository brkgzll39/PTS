"""Kayıtları ve kişileri .xlsx (Excel) formatında dışa aktarma."""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

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


def kayitlar_excel_olustur(kayitlar: list, dosya_yolu: str) -> str:
    wb = Workbook()
    ws = wb.active
    ws.title = "PTS Kayıtları"

    basliklar = [
        "ID", "Plaka No", "Tarih", "Saat", "Kamera", "Yön",
        "Yetki Durumu", "Güven Skoru (%)", "Kişi/Tip", "Görsel Yolu",
    ]
    ws.append(basliklar)
    _baslik_satiri_bicimlendir(ws, len(basliklar))

    for k in kayitlar:
        ws.append([
            k.id,
            _guvenli_hucre(k.plaka_no),
            k.tarih_saat.strftime("%d.%m.%Y"),
            k.tarih_saat.strftime("%H:%M:%S"),
            _guvenli_hucre(k.kamera_id),
            k.yon,
            k.yetki_durumu,
            round(k.guven_skoru * 100, 1) if k.guven_skoru else "",
            _guvenli_hucre(k.kisi_tip_anlik or ""),
            _guvenli_hucre(k.goruntu_yolu or ""),
        ])

    for i, baslik in enumerate(basliklar, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(14, len(baslik) + 4)

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
