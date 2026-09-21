"""Kayıtları PDF formatında dışa aktarma. Tekil kayıt PDF'i araç görselini de içerir."""
import io
import logging
import os
from datetime import datetime
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
)
from reportlab.lib.styles import getSampleStyleSheet

logger = logging.getLogger("pts.pdf_export")


# 2026-09-21: kullanıcı, `_pdf_metin`'in ilk (kaçışlama) düzeltmesinden SONRA
# BİLE PDF dışa aktarmanın gerçek üretim verisiyle (2408 kayıt) hâlâ genel
# 500'e düştüğünü bildirdi. Kök neden bu sefer FARKLIYDI: reportlab'ın
# `Table`'ı, bir hücrenin sarılmış metni TEK SAYFAYA sığmayacak kadar
# uzun/boşluksuz olursa (örn. programatik olarak birleştirilmiş, çakışan
# çok sayıda vardiya oturumunun "; " ile ayrılmış listesi -- bkz.
# main.py::_vardiya_etiketleri_haritasi -- unutulmuş/kapanmamış eski
# oturumlar birikince bu liste anormal uzayabilir) yakalanmamış bir
# `reportlab.platypus.doc.LayoutError` fırlatır. En dar sütun (1.1cm,
# "Blok"/"Otopark" -- bunlar pratikte hep boş ama savunma amaçlı en KÖTÜ
# durum baz alındı) tek bir hücrede ~220 karakterden sonra bu limiti
# aşıyor (yerel olarak ikili aramayla doğrulandı). Çözüm: her hücre
# metnini, bu sınırın ALTINDA sabit bir uzunlukta kırpmak -- normal/geçerli
# hiçbir isim/site/departman/nokta adı bu uzunluğa asla yaklaşmaz, bu
# yalnızca anormal/runaway veriye karşı bir güvenlik ağıdır.
_PDF_HUCRE_MAKS_UZUNLUK = 200


def _pdf_metin(deger) -> str:
    """`Paragraph`e verilecek HER metni güvenli hale getirir.

    KÖK NEDEN 1 (2026-09-21, kullanıcı ekran görüntüsüyle bildirdi -- toplu
    "GEÇİŞ RAPORU" PDF'i, kimliği doğrulanmış geçerli bir istekte bile genel
    "Sunucuda beklenmeyen bir hata oluştu" 500'üne düşüyordu): reportlab'ın
    `Paragraph` flowable'ı, kendisine verilen metni DÜZ METİN olarak DEĞİL,
    sınırlı bir HTML/XML biçimlendirme dili (`<b>`, `<i>`, `<font .../>` vb.
    etiketleri tanıyan bir mini ayrıştırıcı) olarak işler. Bu satırlardaki
    hücrelerin çoğu (kişi adı/soyadı, site adı, daire/departman, erişim
    noktası adı, vardiya kullanıcı adı) yönetici panelinden serbest metin
    olarak girilir -- hiçbiri bu amaçla doğrulanmış/kısıtlanmış DEĞİLDİR.
    Biri bu alanlardan birine kazara (veya bilerek) eşleşmeyen/kapatılmamış
    bir etiketle karışabilecek bir metin girerse (örn. "<b>önemli" gibi
    kapatılmamış kalın etiketi), reportlab'ın ayrıştırıcısı yakalanmamış bir
    `ValueError` fırlatırdı. Çözüm: HER hücre metnini standart XML kaçış
    kurallarıyla (`&`->`&amp;`, `<`->`&lt;`, `>`->`&gt;`) kaçışlamak.

    KÖK NEDEN 2 (aynı gün, İKİNCİ bir kullanıcı bildirimiyle bulundu --
    yukarıdaki düzeltmeden SONRA bile aynı 500 devam ediyordu): aşırı uzun/
    boşluksuz bir hücre metni, `_PDF_HUCRE_MAKS_UZUNLUK` docstring'indeki
    notta anlatılan `LayoutError`'a yol açıyordu. Çözüm: kaçışlamadan ÖNCE
    metni bu sınıra kırpmak (kırpıldığını belli etmek için "…" eklenir)."""
    metin = str(deger)
    if len(metin) > _PDF_HUCRE_MAKS_UZUNLUK:
        metin = metin[:_PDF_HUCRE_MAKS_UZUNLUK] + "…"
    return _xml_escape(metin)

# TÜRKÇE KARAKTER DÜZELTMESİ (2026-09-18, kullanıcı ekran görüntüsüyle
# bildirdi): reportlab'ın gömülü 14 temel fontu (Helvetica/Helvetica-Bold
# vb.) yalnızca WinAnsiEncoding'i destekler -- bu, Türkçeye özgü "ı, İ, ş,
# Ş, ğ, Ğ" karakterlerini İÇERMEZ. Sonuç: "GEÇİŞ RAPORU" -> "GEÇ██ RAPORU",
# "Tanımsız Araç" -> "Tan█ms█z Araç" gibi, bu harflerin yerine boş kare
# (.notdef glifi) basılıyordu. Çözüm: tüm Türkçe karakterleri içeren,
# serbestçe gömülebilir bir Unicode TrueType fontu (DejaVu Sans, bkz.
# backend/fonts/LISANS-DejaVu.txt) kaydedip TÜM stil/tablo font
# referanslarını buna yönlendirmek.
_FONT_DIZINI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FONT_NORMAL = "PTSSans"
FONT_BOLD = "PTSSans-Bold"
_turkce_fontlari_kayitli = False


def _turkce_fontlari_kaydet() -> None:
    """DejaVu Sans'ı reportlab'a kaydeder -- modül başına yalnızca bir kez
    (gereksiz disk I/O'sundan kaçınmak için); `registerFont`'un kendisi de
    tekrar çağrılmaya karşı zararsızdır ama bu bayrak dosyayı her PDF
    üretiminde yeniden OKUMAMIZI önler.

    2026-09-21: bu iki `registerFont` çağrısı önceden HİÇBİR try/except ile
    korunmuyordu -- kurulum klasörü kopyalanırken/taşınırken (ör. zip
    olarak paylaşılırken) `backend/fonts/*.ttf` dosyaları eksik kalır ya da
    bozulursa (sıfır bayt, kesik indirme vb.), bu satır yakalanmamış bir
    istisna fırlatıp TÜM PDF dışa aktarmayı (Türkçe karakter sorunuyla
    hiçbir ilgisi olmayan tek bir kayıt indirme isteğini bile) genel 500'e
    düşürürdü. Artık font dosyaları okunamazsa reportlab'ın gömülü
    Helvetica fontlarına düşülüyor (ı/İ/ş/Ş/ğ/Ğ o durumda hatalı
    görünebilir ama rapor en azından ÜRETİLİR) ve durum loglanıyor ki
    sorun sessizce geçiştirilmesin."""
    global _turkce_fontlari_kayitli, FONT_NORMAL, FONT_BOLD
    if _turkce_fontlari_kayitli:
        return
    try:
        pdfmetrics.registerFont(TTFont(FONT_NORMAL, os.path.join(_FONT_DIZINI, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, os.path.join(_FONT_DIZINI, "DejaVuSans-Bold.ttf")))
    except Exception:
        logger.exception(
            "Türkçe karakter destekli font (%s) yüklenemedi -- Helvetica'ya "
            "düşülüyor (ı/İ/ş/Ş/ğ/Ğ karakterleri PDF'lerde hatalı görünebilir). "
            "backend/fonts/ klasörünün eksiksiz kopyalandığını kontrol edin.",
            _FONT_DIZINI,
        )
        FONT_NORMAL = "Helvetica"
        FONT_BOLD = "Helvetica-Bold"
    _turkce_fontlari_kayitli = True


def _turkce_destekli_stiller():
    """`getSampleStyleSheet()`in döndürdüğü varsayılan stil sözlüğünü alır ve
    metin içeren TÜM stillerin `fontName`ini Türkçe karakterleri destekleyen
    fonta çevirir (bkz. modül başındaki 2026-09-18 notu). Başlık/alt başlık
    stilleri kalın, diğerleri normal fontu kullanır."""
    _turkce_fontlari_kaydet()
    stiller = getSampleStyleSheet()
    for ad in stiller.byName:
        st = stiller[ad]
        if not hasattr(st, "fontName"):
            continue
        st.fontName = FONT_BOLD if ad.startswith(("Heading", "Title")) else FONT_NORMAL
    return stiller


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
    notlar, PDF'de görsel). "Vardiya" (2026-09-20, bkz. excel_export.py'deki
    aynı başlıklı not) burada da en sona, referansta olmayan sistemimize özgü
    bir sütun olarak eklendi."""
    doc = SimpleDocTemplate(
        dosya_yolu, pagesize=landscape(A4), topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        leftMargin=1 * cm, rightMargin=1 * cm,
    )
    stiller = _turkce_destekli_stiller()
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
                 "Nokta", "Geçiş Tipi", "Araç Tipi", "Tarih", "Resim", "Vardiya"]
    # Sütun genişlikleri elle belirlendi (reportlab'ın otomatik dağıtımı,
    # her zaman boş kalan Blok/Otopark'a da diğerleriyle eşit yer ayırıp
    # başlıkların kelime ortasından bölünmesine yol açardı).
    genislikler_cm = [0.9, 2.1, 2.0, 2.0, 1.8, 1.1, 1.6, 1.1, 2.3, 1.6, 2.6, 2.7, 2.9, 2.6]
    veri = [basliklar]
    for s in satirlar:
        veri.append([
            Paragraph(_pdf_metin(s["id"]), hucre_stili),
            Paragraph(_pdf_metin(s["plaka_no"]), hucre_stili),
            Paragraph(_pdf_metin(s["ad"]) if s["ad"] else "-", hucre_stili),
            Paragraph(_pdf_metin(s["soyad"]) if s["soyad"] else "-", hucre_stili),
            Paragraph(_pdf_metin(s["site"]) if s["site"] else "-", hucre_stili),
            Paragraph(_pdf_metin(s["blok"]) if s["blok"] else "-", hucre_stili),
            Paragraph(_pdf_metin(s["daire"]) if s["daire"] else "-", hucre_stili),
            Paragraph(_pdf_metin(s["otopark"]) if s["otopark"] else "-", hucre_stili),
            Paragraph(_pdf_metin(s["nokta"]) if s["nokta"] else "-", hucre_stili),
            Paragraph(_pdf_metin(s["gecis_tipi"]), hucre_stili),
            Paragraph(_pdf_metin(s["arac_tipi"]), hucre_stili),
            # Tarih, sunucu tarafında strftime ile üretilir (kullanıcı girdisi
            # DEĞİLDİR) -- kaçışlamak zararsız olsa da gereksiz; yine de "\n"
            # içerdiği için Paragraph yerine kaçışsız bırakmak render'ı bozmaz.
            Paragraph(s["tarih_saat"].strftime("%d.%m.%Y\n%H:%M:%S"), hucre_stili),
            _pdf_gorsel_hucresi(s.get("goruntu_yolu"), hucre_stili),
            Paragraph(_pdf_metin(s["vardiya"]) if s.get("vardiya") else "-", hucre_stili),
        ])

    tablo = Table(veri, repeatRows=1, colWidths=[g * cm for g in genislikler_cm])
    tablo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        # Başlık satırı Table'a düz string olarak veriliyor (Paragraph değil),
        # bu yüzden kendi fontunu hucre_stili'nden DEVRALMAZ -- Türkçe
        # karakterler ("Adı", "Soyadı", "Geçiş Tipi") için burada da AYRICA
        # FONT_BOLD belirtilmesi gerekiyor (bkz. modül başındaki 2026-09-18 notu).
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
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
    stiller = _turkce_destekli_stiller()
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
        # Bu tablonun hücreleri de (yukarıdaki toplu rapordaki başlık satırı
        # gibi) düz string -- "Kişi/Tip:" gibi Türkçe karakter içeren
        # etiketlerin doğru görünmesi için font burada AYRICA belirtilmeli.
        ("FONTNAME", (0, 0), (-1, -1), FONT_NORMAL),
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
