"""Kayıtları PDF formatında dışa aktarma. Tekil kayıt PDF'i araç görselini de içerir."""
import io
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
)
from reportlab.lib.styles import getSampleStyleSheet

# Toplu "GEÇİŞ RAPORU" PDF'indeki küçük resimler için hedef boyut/kalite.
# ÖNEMLİ (2026-09-18): kamera görselleri diskte tam çözünürlükte (birkaç
# yüz KB) saklanır -- reportlab'ın Image flowable'ı bir dosya yoluyla
# çağrılırsa görseli KÜÇÜK GÖSTERSE BİLE orijinal baytları olduğu gibi PDF'e
# gömer (yalnızca GÖRÜNTÜLEME boyutunu ölçekler, dosya boyutunu değil). Yüzlerce
# kayıt içeren bir raporda bu, PDF'i yüzlerce MB'a şişirip pratikte
# açılamaz/gönderilemez hale getirirdi. Bu yüzden her görsel, gömülmeden önce
# Pillow ile küçültülüp yeniden JPEG'e kodlanır (bellekte, diske yazılmadan).
_KUCUK_GORSEL_MAKS_BOYUT = (240, 160)
_KUCUK_GORSEL_JPEG_KALITE = 60


def _kucuk_gorsel_akisi(goruntu_yolu):
    """Bir kayıt görselini küçültüp bellekte bir JPEG akışı (BytesIO) olarak
    döner; dosya yoksa/okunamıyorsa/bozuksa None döner (rapor o durumda bu
    satır için görsel yerine bir yer tutucu metin gösterir -- tek bir bozuk
    görsel yüzünden TÜM rapor oluşturma işlemi asla çökmemeli)."""
    if not goruntu_yolu or not os.path.isfile(goruntu_yolu):
        return None
    try:
        from PIL import Image as PILImage
        with PILImage.open(goruntu_yolu) as img:
            img = img.convert("RGB")
            img.thumbnail(_KUCUK_GORSEL_MAKS_BOYUT)
            akis = io.BytesIO()
            img.save(akis, format="JPEG", quality=_KUCUK_GORSEL_JPEG_KALITE)
            akis.seek(0)
            return akis
    except Exception:
        return None


def kayitlar_pdf_olustur(satirlar: list, dosya_yolu: str, tarih_araligi_metni: str = "", baslik: str = "GEÇİŞ RAPORU") -> str:
    """`satirlar`: main.py::_kayitlari_rapor_satirlari'nin ürettiği düz
    sözlük listesi (bkz. excel_export.kayitlar_excel_olustur'un aynı
    parametresi). Sütun düzeni (2026-09-18), kullanıcının paylaştığı bir
    referans ürünün "GEÇİŞ RAPORU" PDF çıktısıyla eşleşecek şekilde
    tasarlandı -- tek fark, Excel'deki "Notlar" yerine burada "Resim"
    sütununun bulunması (referansın kendisi de aynı ayrımı yapıyor: Excel'de
    notlar, PDF'de görsel)."""
    doc = SimpleDocTemplate(
        dosya_yolu, pagesize=landscape(A4), topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        leftMargin=1 * cm, rightMargin=1 * cm,
    )
    stiller = getSampleStyleSheet()
    hucre_stili = stiller["Normal"].clone("hucre")
    hucre_stili.fontSize = 7
    hucre_stili.leading = 8.5
    elemanlar = []

    elemanlar.append(Paragraph(baslik, stiller["Title"]))
    if tarih_araligi_metni:
        elemanlar.append(Paragraph(tarih_araligi_metni, stiller["Normal"]))
    elemanlar.append(
        Paragraph(f"Oluşturulma Tarihi: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}", stiller["Normal"])
    )
    elemanlar.append(Paragraph(f"Toplam Kayıt: {len(satirlar)}", stiller["Normal"]))
    elemanlar.append(Spacer(1, 0.4 * cm))

    basliklar = ["ID", "Plaka", "Adı", "Soyadı", "Site", "Blok", "Daire", "Otopark",
                 "Nokta", "Geçiş Tipi", "Araç Tipi", "Tarih", "Resim"]
    # Sütun genişlikleri elle belirlendi (reportlab'ın otomatik dağıtımı,
    # her zaman boş kalan Blok/Otopark'a da diğerleriyle eşit yer ayırıp
    # başlıkların kelime ortasından bölünmesine yol açardı).
    genislikler_cm = [0.9, 2.1, 2.0, 2.0, 1.8, 1.1, 1.6, 1.1, 2.3, 1.6, 2.6, 2.7, 2.9]
    veri = [basliklar]
    for s in satirlar:
        veri.append([
            Paragraph(str(s["id"]), hucre_stili),
            Paragraph(s["plaka_no"], hucre_stili),
            Paragraph(s["ad"] or "-", hucre_stili),
            Paragraph(s["soyad"] or "-", hucre_stili),
            Paragraph(s["site"] or "-", hucre_stili),
            Paragraph(s["blok"] or "-", hucre_stili),
            Paragraph(s["daire"] or "-", hucre_stili),
            Paragraph(s["otopark"] or "-", hucre_stili),
            Paragraph(s["nokta"] or "-", hucre_stili),
            Paragraph(s["gecis_tipi"], hucre_stili),
            Paragraph(s["arac_tipi"], hucre_stili),
            Paragraph(s["tarih_saat"].strftime("%d.%m.%Y\n%H:%M:%S"), hucre_stili),
            _pdf_gorsel_hucresi(s.get("goruntu_yolu"), hucre_stili),
        ])

    tablo = Table(veri, repeatRows=1, colWidths=[g * cm for g in genislikler_cm])
    tablo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
    ]))
    elemanlar.append(tablo)
    doc.build(elemanlar)
    return dosya_yolu


def _pdf_gorsel_hucresi(goruntu_yolu, hucre_stili):
    """"Resim" sütunundaki tek bir hücreyi üretir: küçültülmüş görsel varsa
    onu, yoksa (görsel yok/dosya okunamadı) bir yer tutucu metin döner."""
    akis = _kucuk_gorsel_akisi(goruntu_yolu)
    if akis is None:
        return Paragraph("Görsel yok", hucre_stili)
    try:
        return Image(akis, width=2.6 * cm, height=1.75 * cm, kind="proportional")
    except Exception:
        return Paragraph("Görsel yok", hucre_stili)


def kayit_detay_pdf_olustur(kayit, dosya_yolu: str) -> str:
    doc = SimpleDocTemplate(dosya_yolu, pagesize=A4, topMargin=2 * cm)
    stiller = getSampleStyleSheet()
    elemanlar = []

    elemanlar.append(Paragraph("Plaka Tanıma Kayıt Detayı", stiller["Title"]))
    elemanlar.append(Spacer(1, 0.5 * cm))

    guven_metni = f"%{kayit.guven_skoru * 100:.1f}" if kayit.guven_skoru else "-"
    bilgi = [
        ["Plaka No:", kayit.plaka_no],
        ["Tarih/Saat:", kayit.tarih_saat.strftime("%d.%m.%Y %H:%M:%S")],
        ["Kamera:", kayit.kamera_id],
        ["Yön:", kayit.yon],
        ["Yetki Durumu:", kayit.yetki_durumu],
        ["Güven Skoru:", guven_metni],
        ["Kişi/Tip:", kayit.kisi_tip_anlik or "-"],
    ]
    tablo = Table(bilgi, colWidths=[5 * cm, 10 * cm])
    tablo.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elemanlar.append(tablo)
    elemanlar.append(Spacer(1, 1 * cm))

    if kayit.goruntu_yolu and os.path.exists(kayit.goruntu_yolu):
        elemanlar.append(Paragraph("Araç Görseli:", stiller["Heading2"]))
        elemanlar.append(Spacer(1, 0.3 * cm))
        elemanlar.append(Image(kayit.goruntu_yolu, width=14 * cm, height=9 * cm, kind="proportional"))
    else:
        elemanlar.append(Paragraph("Bu kayıt için görsel bulunmuyor.", stiller["Normal"]))

    doc.build(elemanlar)
    return dosya_yolu
