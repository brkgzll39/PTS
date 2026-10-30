"""Kayıtları ve kişileri .xlsx (Excel) formatında dışa aktarma."""
import re

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

BASLIK_DOLGU = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
BASLIK_YAZI = Font(color="FFFFFF", bold=True)


def _guvenli_hucre(deger):
    """Excel/CSV formül enjeksiyonunu engeller: kullanıcı girdisi '=','+','-','@' ile başlıyorsa kaçış karakteri eklenir.

    KÖK NEDEN (2026-09-21, kullanıcı bildirdi -- toplu "GEÇİŞ RAPORU"
    Excel'i, kimliği doğrulanmış geçerli bir istekte bile genel "Sunucuda
    beklenmeyen bir hata oluştu" 500'üne düşüyordu): OOXML (.xlsx) biçimi,
    XML 1.0 spesifikasyonu gereği belirli KONTROL KARAKTERLERİNİ (örn.
    NUL, backspace -- sekme/satır sonu/satır başı HARİÇ) hücre metninde
    HİÇ barındıramaz. `not_metni` (serbest metin not alanı) gibi bir alana
    -- kopyala/yapıştır yoluyla ya da bozuk bir OCR/harici kaynaktan --
    böyle bir karakter karışırsa, openpyxl `wb.save()` sırasında
    yakalanmamış bir `IllegalCharacterError` (ValueError alt sınıfı)
    fırlatırdı -- istek kendisi tamamen geçerli olsa bile TÜM rapor
    çökerdi. Çözüm: openpyxl'in kendi `ILLEGAL_CHARACTERS_RE` deseniyle bu
    karakterleri hücreye yazmadan ÖNCE temizlemek (bkz. aynı kök nedenle
    ilgili backend/pdf_export.py::_pdf_metin'deki kaçışlama notu -- PDF
    tarafında reportlab bu karakterlere karşı DAHA toleranslı olduğu için
    orada AYRI bir sorun (LayoutError) olarak ortaya çıktı, bkz. o
    dosyadaki not)."""
    if isinstance(deger, str):
        deger = ILLEGAL_CHARACTERS_RE.sub("", deger)
    if isinstance(deger, str) and deger[:1] in ("=", "+", "-", "@"):
        return "'" + deger
    return deger


def _baslik_satiri_bicimlendir(ws, sutun_sayisi):
    for col_no in range(1, sutun_sayisi + 1):
        hucre = ws.cell(row=1, column=col_no)
        hucre.fill = BASLIK_DOLGU
        hucre.font = BASLIK_YAZI
        hucre.alignment = Alignment(horizontal="center")


_KAYIT_BASLIKLARI = [
    "ID", "Plaka", "Adı", "Soyadı", "Site", "Blok", "Daire", "Otopark",
    "Nokta", "Geçiş Tipi", "Araç Tipi", "Tarih", "Notlar", "Vardiya",
]


def _nokta_kok_adi(nokta: str) -> str:
    """Sondaki numara ve giriş/çıkış ekleri atılmış nokta adı ("Lojman1" -> "Lojman")."""
    temiz = (nokta or "").strip()
    temiz = re.sub(r"(?i)[\s_-]*(giri[sş]|[cç][iı]k[iı][sş])$", "", temiz)
    return re.sub(r"[\s_\-\d]+$", "", temiz).strip()


def nizamiye_grubu(nokta: str) -> str:
    """Bir kamera/nokta adının ait olduğu nizamiyenin KARŞILAŞTIRMA anahtarı:
    sondaki numara ve giriş/çıkış ekleri atılır, büyük/küçük harf ve Türkçe
    "ı"/"i" farkı yok sayılır -- sahadaki "Lojman" + "Lojman1" aynı,
    "Nizamiye" + "Nizamıye" aynı nizamiyedir."""
    kok = _nokta_kok_adi(nokta)
    if not kok:
        return ""
    return kok.replace("I", "ı").replace("İ", "i").lower().replace("ı", "i")


def nizamiye_gorunen_adi(anahtar: str, noktalar: list) -> str:
    """Sayfa adı: gruptaki adlardan "i" ile yazılmış olanı (Nizamiye), yoksa
    en sık geçeni (Nizamıye)."""
    if not anahtar:
        return "Diğer"
    koklar = [_nokta_kok_adi(n) for n in noktalar]

    def oncelik(k):
        # 1) "i" ile yazılmış, 2) yalnız baş harfi büyük ("Lojman", "LOJMAN" değil), 3) en sık geçen
        return (k.lower() == anahtar, k[1:] == k[1:].lower(), koklar.count(k))
    return max(set(koklar), key=oncelik)


def _sayfa_adi(ad: str) -> str:
    # Excel sayfa adı: en fazla 31 karakter, []:*?/\ yasak.
    return re.sub(r"[\[\]:*?/\\]", "", ad)[:31] or "Sayfa"


def _kayit_sayfasi_yaz(ws, satirlar: list) -> None:
    basliklar = _KAYIT_BASLIKLARI
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
            _guvenli_hucre(s.get("vardiya", "")),
        ])

    for i, baslik in enumerate(basliklar, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(10, len(baslik) + 4)
    ws.column_dimensions[get_column_letter(basliklar.index("Notlar") + 1)].width = 35
    ws.column_dimensions[get_column_letter(basliklar.index("Vardiya") + 1)].width = 32
    ws.freeze_panes = "A2"


def kayitlar_excel_olustur(satirlar: list, dosya_yolu: str, nizamiyeler: list = None) -> str:
    """`satirlar`: main.py::_kayitlari_rapor_satirlari'nin ürettiği, her biri
    bir geçiş kaydını temsil eden düz (plain) sözlüklerden oluşan liste.

    Sütun düzeni (2026-09-18), kullanıcının paylaştığı bir referans ürünün
    "GEÇİŞ RAPORU" Excel çıktısıyla BİREBİR eşleşecek şekilde tasarlandı:
    Plaka/Adı/Soyadı/Site/Blok/Daire/Otopark/Nokta/Geçiş Tipi/Araç Tipi/
    Tarih/Notlar. "ID" en başa, bizim sistemimize özgü ekstra bir sütun
    olarak eklendi (kayda geri dönüp bakabilmek için faydalı, referansta
    yok). "Blok" ve "Otopark" bu sistemde MODELLENMEDİĞİ için her zaman
    boştur -- var olmayan bir veri asla uydurulmaz (bkz. main.py'deki not).
    "Vardiya" (2026-09-20 kullanıcı talebi, bkz. README) da AYNI şekilde,
    referansta olmayan ama bizim sistemimize özgü bir sütun olarak en SONA
    eklendi -- o kaydın gerçekleştiği anda hangi güvenlik personelinin
    vardiyasının açık olduğunu (varsa) gösterir.

    2026-10-14 (kullanıcı: "excel kayıt alırken lojman ve nizamiye giriş
    çıkışlarını ayrı ayrı almak istiyorum, bir listede gelmesin"): kayıtlar
    birden fazla nizamiyeye aitse (bkz. `nizamiye_grubu`) her nizamiye AYRI
    bir sayfaya yazılır ("Lojman", "Nizamiye"); tek nizamiyelik raporda tek
    sayfa ("Geçiş Raporu") kalır."""
    gruplar: dict = {}
    for s in satirlar:
        nokta = s.get("nokta", "")
        if nizamiyeler is None:
            anahtar = nizamiye_grubu(nokta)
        else:
            # Tanımlı nizamiyelerden birine ait olmayan (eski/test) adlar "Diğer"e düşer.
            anahtar = nizamiye_grubu(nokta)
            if anahtar not in nizamiyeler:
                anahtar = ""
        gruplar.setdefault(anahtar, []).append(s)

    wb = Workbook()
    if len(gruplar) <= 1:
        ws = wb.active
        ws.title = "Geçiş Raporu"
        _kayit_sayfasi_yaz(ws, satirlar)
    else:
        wb.remove(wb.active)
        kullanilan = set()
        for anahtar in sorted(gruplar, key=lambda a: (a == "", a)):
            ad = _sayfa_adi(nizamiye_gorunen_adi(anahtar, [s.get("nokta", "") for s in gruplar[anahtar]]))
            while ad.lower() in kullanilan:
                ad = _sayfa_adi(ad[:28] + "_" + str(len(kullanilan)))
            kullanilan.add(ad.lower())
            _kayit_sayfasi_yaz(wb.create_sheet(ad), gruplar[anahtar])
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
_ICE_AKTARMA_GECERLI_TIPLER = ("abone", "personel", "ziyaretci", "vip", "alt_isveren")


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
        # 2026-09-23 kullanıcı isteği: "çoklu plaka tekrar eden isimler olarak
        # düzenle" -- birden fazla aracı olan bir kişi/birim artık TEK satırda,
        # bu şekilde virgülle ayrılmış birden fazla plakayla içe aktarılabilir
        # (bkz. metin_araclari.py::plaka_hucresini_ayir, main.py::toplu_kisi_import).
        ["ÖRNEK — SİLİP ÜZERİNE YAZINIZ (BİRDEN FAZLA ARACI OLAN KİŞİ)", "34 GHI 789, 34 JKL 012", "personel", "05XX XXX XX XX", "ÜRETİM MD."],
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
    tip_dogrulama.error = "Tip yalnızca 'abone', 'personel', 'ziyaretci', 'vip' veya 'alt_isveren' olabilir."
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
        ("Plaka No", "Evet", "Örn. '34 ABC 123'. Aynı kişinin/birimin birden fazla aracı varsa, bu hücreye plakaları virgülle (,) ayırarak da yazabilirsiniz -- örn. '34 ABC 123, 34 DEF 456'. İlk yazılan plaka ana plaka olur, diğerleri ek araç olarak kaydedilir; içe aktardıktan sonra panelden Kişiler sekmesinden de ek plaka eklenip çıkarılabilir."),
        ("Tip", "Evet", "'abone' (site sakini), 'personel', 'ziyaretci', 'vip' (Bölge Müdürü) veya 'alt_isveren' (TPIC, servis) olmalı — açılır listeden seçin. Geçersiz/boş bir değer sessizce 'abone' olarak kaydedilir, bu yüzden dikkatli seçin."),
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


def resmi_arac_raporu_olustur(rapor: dict, dosya_yolu: str) -> str:
    """Resmi araç ay sonu raporu (bkz. main.py::_resmi_arac_raporu): özet + döküm."""
    from datetime import datetime

    def _saat(deger):
        return datetime.fromisoformat(deger).strftime("%d.%m.%Y %H:%M") if deger else ""

    def _sure(dk):
        return "" if dk is None else f"{dk // 60} sa {dk % 60} dk"

    wb = Workbook()
    ws = wb.active
    ws.title = "Özet"
    basliklar = ["Plaka", "Araç", "Birim", "Çıkış", "Görevli", "Görevsiz", "Mesai Dışı", "Geç Dönüş", "Dışarıda (toplam)"]
    ws.append(basliklar)
    _baslik_satiri_bicimlendir(ws, len(basliklar))
    for o in rapor["ozet"]:
        ws.append([_guvenli_hucre(o["plaka_no"]), _guvenli_hucre(o["ad"]), _guvenli_hucre(o["birim"] or ""),
                   o["cikis"], o["gorevli"], o["gorevsiz"], o["mesai_disi"], o["gec_donus"], _sure(o["disarida_dk"])])
    ws.append([])
    ws.append([f"Dönem: {rapor['ay']} · Mesai: {rapor['mesai']} · Görev payı: {rapor['tolerans_dk']} dk"])
    for i, baslik in enumerate(basliklar, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(12, len(baslik) + 4)
    ws.freeze_panes = "A2"

    ws2 = wb.create_sheet("Döküm")
    basliklar = ["Plaka", "Araç", "Gün", "Çıkış", "Dönüş", "Süre", "Görev Emri", "Görevli", "Güzergah", "Durum", "Kamera"]
    ws2.append(basliklar)
    _baslik_satiri_bicimlendir(ws2, len(basliklar))
    uyari = PatternFill(start_color="FDE2E1", end_color="FDE2E1", fill_type="solid")
    for s in rapor["satirlar"]:
        durumlar = []
        if not s["gorev_emri_id"]:
            durumlar.append("GÖREVSİZ")
        if s["mesai_disi"]:
            durumlar.append("Mesai dışı")
        if s["gec_donus"]:
            durumlar.append("Geç dönüş")
        if not s["donus"]:
            durumlar.append("Dönüş kaydı yok")
        ws2.append([_guvenli_hucre(s["plaka_no"]), _guvenli_hucre(s["ad"]), s["gun"], _saat(s["cikis"]), _saat(s["donus"]),
                    _sure(s["sure_dk"]), f"#{s['gorev_emri_id']}" if s["gorev_emri_id"] else "",
                    _guvenli_hucre(s["gorevli"] or ""), _guvenli_hucre(s["guzergah"] or ""),
                    ", ".join(durumlar) or "Görevli", _guvenli_hucre(s["kamera"] or "")])
        if not s["gorev_emri_id"] or s["gec_donus"]:
            for hucre in ws2[ws2.max_row]:
                hucre.fill = uyari
    for i, genislik in enumerate([12, 22, 11, 17, 17, 11, 11, 20, 24, 28, 18], 1):
        ws2.column_dimensions[get_column_letter(i)].width = genislik
    ws2.freeze_panes = "A2"
    wb.save(dosya_yolu)
    return dosya_yolu
