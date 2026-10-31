"""Günlük yönetici raporu PDF'i (2026-10-31). Veri main.py::_gunluk_rapor_verisi'nde
hazırlanır; burada yalnızca sayfaya dökülür (Türkçe yazı tipi: pdf_export)."""
from datetime import datetime

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend import pdf_export

_KOYU = colors.HexColor("#1F2937")
_ACIK = colors.HexColor("#F1F4F9")
_KIRMIZI = colors.HexColor("#FDE2E1")


def _tablo(veri: list, genislikler: list, vurgulu_satirlar: tuple = ()) -> Table:
    t = Table(veri, colWidths=[g * cm for g in genislikler], repeatRows=1)
    stil = [
        ("FONTNAME", (0, 0), (-1, -1), pdf_export.FONT_NORMAL),
        ("FONTNAME", (0, 0), (-1, 0), pdf_export.FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), _KOYU),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D5DCE3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ACIK]),
    ]
    stil += [("BACKGROUND", (0, i), (-1, i), _KIRMIZI) for i in vurgulu_satirlar]
    t.setStyle(TableStyle(stil))
    return t


def _ozet_kutulari(ozet: list) -> Table:
    hucreler = [[f"{deger}" for _, deger in ozet], [ad for ad, _ in ozet]]
    t = Table(hucreler, colWidths=[18.0 / max(len(ozet), 1) * cm] * len(ozet))
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), pdf_export.FONT_BOLD),
        ("FONTNAME", (0, 1), (-1, 1), pdf_export.FONT_NORMAL),
        ("FONTSIZE", (0, 0), (-1, 0), 16), ("FONTSIZE", (0, 1), (-1, 1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#D5DCE3")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E3E7EE")),
        ("BACKGROUND", (0, 0), (-1, -1), _ACIK),
        ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
    ]))
    return t


def _saatlik_grafik(saatlik: list) -> Drawing:
    d = Drawing(18 * cm, 4.2 * cm)
    g = VerticalBarChart()
    g.x, g.y, g.width, g.height = 1.0 * cm, 0.6 * cm, 16.5 * cm, 3.3 * cm
    g.data = [list(saatlik)]
    g.categoryAxis.categoryNames = [f"{s:02d}" for s in range(24)]
    g.categoryAxis.labels.fontName = pdf_export.FONT_NORMAL
    g.categoryAxis.labels.fontSize = 6.5
    g.valueAxis.labels.fontName = pdf_export.FONT_NORMAL
    g.valueAxis.labels.fontSize = 6.5
    g.valueAxis.valueMin = 0
    g.bars[0].fillColor = colors.HexColor("#2F6FED")
    g.bars[0].strokeColor = None
    d.add(g)
    return d


def rapor_olustur(veri: dict, dosya_yolu: str) -> str:
    doc = SimpleDocTemplate(dosya_yolu, pagesize=A4, topMargin=1.3 * cm, bottomMargin=1.3 * cm,
                            leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            title=f"Günlük Rapor {veri['tarih']}")
    st = pdf_export._turkce_destekli_stiller()
    bolum = st["Heading3"].clone("bolum")
    bolum.spaceBefore, bolum.spaceAfter = 10, 4
    kucuk = st["Normal"].clone("kucuk")
    kucuk.fontSize, kucuk.leading = 8, 10
    kucuk.textColor = colors.HexColor("#5B6576")
    e = []
    e.append(Paragraph(f"GÜNLÜK YÖNETİCİ RAPORU — {veri['tarih']}", st["Title"]))
    if veri.get("kurum"):
        e.append(Paragraph(pdf_export._pdf_metin(veri["kurum"]), st["Normal"]))
    e.append(Paragraph(f"Oluşturulma: {datetime.now():%d.%m.%Y %H:%M}", kucuk))
    e.append(Spacer(1, 0.3 * cm))
    e.append(_ozet_kutulari(veri["ozet"]))

    e.append(Paragraph("Saatlik geçiş yoğunluğu", bolum))
    e.append(_saatlik_grafik(veri["saatlik"]))

    e.append(Paragraph("Araç türlerine göre geçişler", bolum))
    e.append(_tablo([["Tür", "Geçiş"]] + [[a, str(n)] for a, n in veri["turler"]], [12, 4]))

    if veri["alarmlar"]:
        e.append(Paragraph("Alarmlar", bolum))
        e.append(_tablo([["Alarm", "Adet"]] + [[a, str(n)] for a, n in veri["alarmlar"]], [12, 4]))

    if veri["kara_liste"]:
        e.append(Paragraph("Kara listedeki araç geçişleri", bolum))
        e.append(_tablo([["Saat", "Plaka", "Nokta"]] + [list(r) for r in veri["kara_liste"]], [3, 4, 9],
                        vurgulu_satirlar=tuple(range(1, len(veri["kara_liste"]) + 1))))

    if veri["onaysiz"]:
        e.append(Paragraph("Onaylanmadan giren ziyaretçiler", bolum))
        e.append(_tablo([["Saat", "Plaka", "Nokta", "Not"]] + [list(r) for r in veri["onaysiz"]], [2.2, 3, 5, 7.8]))
        if veri.get("onaysiz_fazla"):
            e.append(Paragraph(f"… ve {veri['onaysiz_fazla']} kayıt daha (Geçiş Kayıtları'nda).", kucuk))

    if veri.get("resmi"):
        r = veri["resmi"]
        e.append(Paragraph("Resmi araçlar", bolum))
        e.append(_tablo(
            [["Çıkış", "Görevli", "Görevsiz", "Geç dönüş"], [str(r["cikis"]), str(r["gorevli"]), str(r["gorevsiz"]), str(r["gec"])]],
            [4, 4, 4, 4], vurgulu_satirlar=(1,) if r["gorevsiz"] or r["gec"] else ()))
        if r["gorevsiz_liste"]:
            e.append(Spacer(1, 0.2 * cm))
            e.append(_tablo([["Saat", "Plaka", "Araç"]] + [list(x) for x in r["gorevsiz_liste"]], [3, 4, 9]))

    if veri["mutabakat"]:
        e.append(Paragraph("Kamera mutabakatı (kameranın kendi okumasıyla karşılaştırma)", bolum))
        e.append(_tablo([["Kamera", "Kamera okudu", "PTS yakaladı", "Oran", "Sonradan eklenen"]]
                        + [list(x) for x in veri["mutabakat"]], [5.5, 2.8, 2.8, 2.2, 2.7]))

    if veri["kesintiler"] or veri["sessiz"]:
        e.append(Paragraph("Sistem olayları", bolum))
        satirlar = [["Saat", "Olay"]] + [[a, b] for a, b in veri["kesintiler"] + veri["sessiz"]]
        e.append(_tablo(satirlar, [3, 13], vurgulu_satirlar=tuple(range(1, len(satirlar)))))

    e.append(Spacer(1, 0.5 * cm))
    e.append(Paragraph("Bu rapor PTS tarafından kendiliğinden oluşturuldu.", kucuk))
    doc.build(e)
    return dosya_yolu
