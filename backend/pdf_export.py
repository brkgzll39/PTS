"""Kayıtları PDF formatında dışa aktarma. Tekil kayıt PDF'i araç görselini de içerir."""
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
)
from reportlab.lib.styles import getSampleStyleSheet


def kayitlar_pdf_olustur(kayitlar: list, dosya_yolu: str, baslik: str = "PTS Kayıt Raporu") -> str:
    doc = SimpleDocTemplate(
        dosya_yolu, pagesize=landscape(A4), topMargin=1.5 * cm, bottomMargin=1.5 * cm
    )
    stiller = getSampleStyleSheet()
    elemanlar = []

    elemanlar.append(Paragraph(baslik, stiller["Title"]))
    elemanlar.append(
        Paragraph(f"Oluşturulma Tarihi: {datetime.now().strftime('%d.%m.%Y %H:%M')}", stiller["Normal"])
    )
    elemanlar.append(Paragraph(f"Toplam Kayıt: {len(kayitlar)}", stiller["Normal"]))
    elemanlar.append(Spacer(1, 0.5 * cm))

    veri = [["ID", "Plaka", "Tarih/Saat", "Kamera", "Yön", "Yetki Durumu", "Kişi/Tip"]]
    for k in kayitlar:
        veri.append([
            str(k.id), k.plaka_no, k.tarih_saat.strftime("%d.%m.%Y %H:%M:%S"),
            k.kamera_id, k.yon, k.yetki_durumu, k.kisi_tip_anlik or "-",
        ])

    tablo = Table(veri, repeatRows=1)
    tablo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    elemanlar.append(tablo)
    doc.build(elemanlar)
    return dosya_yolu


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
