"""Küçük, bağımlılıksız metin yardımcıları.

Bu modül kasıtlı olarak cv2/fastapi/sqlalchemy gibi hiçbir ağır bağımlılığa
ihtiyaç duymaz; hem camera_reader.py (kare bazlı oy birikimi için plaka
benzerliği) hem main.py (bilinen plaka veritabanına karşı OCR hatası
düzeltmesi için) tarafından ortak kullanılır. Amaç: aynı mesafe hesaplama
mantığının iki yerde birbirinden bağımsız, zamanla birbirinden sapabilecek
iki kopyası olarak var olmaması (bu depoda daha önce başka dosyalarda görülen
"sessiz tekrar" hata sınıfının bir başka biçimi).
"""


import re
from typing import List, Optional


def levenshtein_mesafesi(a: str, b: str) -> int:
    """İki dizge arasındaki düzenleme (Levenshtein) mesafesini hesaplar.

    Küçük plaka dizgeleri (7-8 karakter) için yazıldığından basit O(len(a)*len(b))
    dinamik programlama yeterlidir; harici bir kütüphaneye gerek yoktur.
    """
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la

    onceki = list(range(lb + 1))
    for i, ca in enumerate(a, start=1):
        simdi = [i] + [0] * lb
        for j, cb in enumerate(b, start=1):
            maliyet = 0 if ca == cb else 1
            simdi[j] = min(
                onceki[j] + 1,       # silme
                simdi[j - 1] + 1,    # ekleme
                onceki[j - 1] + maliyet,  # değiştirme (veya eşleşme)
            )
        onceki = simdi
    return onceki[lb]


# Sadece TEK karakterlik OCR hatalarını düzelt — bkz.
# main.py::_bilinen_plakaya_yakinlik_duzelt için kullanım bağlamı.
BILINEN_PLAKA_DUZELTME_MAX_MESAFE = 1


def en_yakin_bilinen_plakayi_bul(hedef: str, bilinen_plakalar) -> Optional[str]:
    """Saf eşleştirme mantığı (DB'den bağımsız, kolay birim testi için).

    `hedef` zaten `bilinen_plakalar` içindeyse, ya da tek bir en-yakın aday
    yoksa (aday yok ya da birden fazla aday eşit derecede yakın — yani
    belirsiz), None döner. Yalnızca TEK, KESİN bir en-yakın aday varsa o
    adayı döner.
    """
    if hedef in bilinen_plakalar:
        return None  # zaten tam eşleşiyor, düzeltmeye gerek yok

    en_yakin = None
    en_yakin_mesafe = None
    belirsiz = False
    for aday in bilinen_plakalar:
        if not aday:
            continue
        mesafe = levenshtein_mesafesi(hedef, aday)
        if mesafe > BILINEN_PLAKA_DUZELTME_MAX_MESAFE:
            continue
        if en_yakin_mesafe is None or mesafe < en_yakin_mesafe:
            en_yakin, en_yakin_mesafe = aday, mesafe
            belirsiz = False
        elif mesafe == en_yakin_mesafe:
            belirsiz = True  # birden fazla bilinen plaka eşit derecede yakın — riskli, düzeltme

    return en_yakin if (en_yakin is not None and not belirsiz) else None


def sondan_bir_karakter_eksik_mi(kisa: str, uzun: str) -> bool:
    """`uzun`, `kisa`'nın SONUNA tam olarak bir karakter eklenmiş hali mi?

    Kullanım bağlamı (bkz. camera_reader.py::PlakaOyBirikimi.kazanan): fast_alpr
    kütüphanesi (ve genel olarak çoğu ANPR dedektörü) tespit kutusunu HİÇBİR
    kenar boşluğu (padding) bırakmadan tam sınırlarından kırpıyor -- kutunun
    sağ kenarı son karaktere birkaç piksel yakın kalırsa o karakter OCR'a hiç
    ulaşmadan kırpılabiliyor. Bu, OCR'ın SONDAN bir karakter EKSİK ama yine de
    yüksek güvenle okuduğu bir sonuç üretmesine yol açar (gördüğü karakterlerin
    hepsi gerçekten doğrudur, sadece biri hiç görülmemiştir) -- düşük güven
    eşiği bunu YAKALAYAMAZ.

    Yalnızca SONDAN (dizginin en sağından) bir karakterin eksik/fazla olduğu
    durumu hedefler -- ortadan bir karakter eksikse (örn. bir harf grubundan
    bir harf düşmüşse) bu farklı bir hata sınıfıdır ve burada ele alınmaz
    (dizge uzunluğu aynı kalmadığı için `_sondan_bir_karakter_farkli_mi` gibi
    kullanan çağıran kodun kendisi zaten ayrı bir kontrolle bunu eler)."""
    return len(uzun) == len(kisa) + 1 and uzun.startswith(kisa)


def plaka_hucresini_ayir(hucre: Optional[str]) -> List[str]:
    """Toplu kişi içe aktarma Excel şablonunun 'Plaka No' hücresini, virgül
    (,) veya noktalı virgülle (;) ayrılmış BİRDEN FAZLA plakaya böler ve her
    parçayı normalize eder (baş/son boşluk temizlenir, büyük harfe çevrilir,
    harf/rakam/boşluk DIŞINDAKİ karakterler atılır).

    Bu normalizasyon kuralı schemas.py::plaka_normalize ile BİREBİR AYNIDIR
    (bkz. o fonksiyonun docstring'i) -- ama bu modül kasıtlı olarak
    fastapi/sqlalchemy/pydantic'e ihtiyaç duymadığından (bkz. dosya başındaki
    not) burada bağımsız bir kopyası tutuluyor; ikisini birden değiştirmeden
    yalnızca birini değiştirmek, iki farklı giriş yolunun (tekil kişi ekleme
    vs. toplu içe aktarma) aynı plakayı farklı şekilde saklamasına yol açar.

    Kullanıcı isteği (2026-09-23): "çoklu plaka tekrar eden isimler olarak
    düzenle" -- aynı kişinin (ör. bir departmanın havuz araçları, ya da
    birden fazla aracı olan bir personelin) artık AYRI satırlar yerine TEK
    satırda, bu hücreye virgülle ayrılmış birden fazla plaka yazılarak içe
    aktarılabilmesi için (ör. '34 ABC 123, 34 DEF 456'). Dönen listenin İLK
    elemanı kişinin ana plaka_no'su, kalanlar main.py::toplu_kisi_import
    tarafından KisiPlaka (ek_plakalar) olarak eklenir -- panelden Kişiler
    ekranında "+ Plaka Ekle" ile tek tek eklemekle birebir aynı veri modeli.

    Boş/geçersiz (temizlendikten sonra hiç karakter kalmayan) parçalar
    sessizce atlanır; aynı hücrede yanlışlıkla tekrarlanan bir plaka
    (kopyala-yapıştır hatası) tekilleştirilir, ilk görülme sırası korunur.
    Girdi None/boş ise boş liste döner."""
    if not hucre:
        return []
    sonuc: List[str] = []
    for parca in re.split(r"[,;]+", hucre):
        temiz = re.sub(r"[^A-Za-z0-9 ]", "", parca).strip().upper()
        if temiz and temiz not in sonuc:
            sonuc.append(temiz)
    return sonuc
