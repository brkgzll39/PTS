"""Vardiya çizelgesi (2026-10-12, kullanıcı isteği): Lojman nizamiyesinde A/B/C/D
vardiyaları giriş yapılmadan, Bölge Müdürlüğü'nün aylık çizelgesine göre
belirlenir. Bu modül veritabanından/fastapi'den bağımsız saf hesaplamaları
içerir (main.py veritabanı tarafını yapar).

Çizelge biçimi (kağıttaki tabloyla aynı): her gün için üç dilim --
07:00-15:00 (sabah), 15:00-23:00 (akşam), 23:00-07:00 (gece; o gün 23:00'te
başlar, ERTESİ GÜN 07:00'de biter) -- ve o gün dilim almayan vardiya
"hafta tatili"dir.

Listesi girilmemiş günler, girilen son listenin son 20 gününün tekrarıyla
hesaplanır (Ekim 2026 çizelgesi 20 günde bir tekrar ediyor: 1-11 Ekim =
21-31 Ekim). İlk listeden önceki gün de (ilk günün 00:00-07:00'ını kapsayan
gece dilimi için) aynı döngüyle geriye doğru hesaplanır.
"""
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

VARDIYALAR = ("A", "B", "C", "D")
DONGU_GUN = 20

# (dilim kodu, etiket, başlangıç saati, süre saat)
DILIMLER = (
    ("sabah", "07:00-15:00", time(7, 0), 8),
    ("aksam", "15:00-23:00", time(15, 0), 8),
    ("gece", "23:00-07:00", time(23, 0), 8),
)
DILIM_ETIKETI = {kod: etiket for kod, etiket, _, _ in DILIMLER}

GunVardiyalari = Tuple[str, str, str]  # (sabah, akşam, gece)

# Bölge Müdürlüğü Ekim 2026 çizelgesi (kullanıcının gönderdiği tablo, 2026-10-12
# kullanıcı tarafından doğrulandı). Satırlar: 07-15, 15-23, 23-07.
EKIM_2026 = (
    "DDDAAAAACCCCCBBBBBDDDDDAAAAACCC",
    "ACCCCCBBBBBDDDDDAAAAACCCCCBBBBB",
    "BBBBDDDDDAAAAACCCCCBBBBBDDDDDAA",
)


class CizelgeHatasi(ValueError):
    pass


def dilim_araliklari(gun: date) -> List[Tuple[str, datetime, datetime]]:
    """O günün üç dilimi: (kod, başlangıç, bitiş). Gece dilimi ertesi güne taşar."""
    sonuc = []
    for kod, _, baslangic_saati, sure in DILIMLER:
        baslangic = datetime.combine(gun, baslangic_saati)
        sonuc.append((kod, baslangic, baslangic + timedelta(hours=sure)))
    return sonuc


def tatil_vardiyasi(v: GunVardiyalari) -> Optional[str]:
    kalan = [x for x in VARDIYALAR if x not in v]
    return kalan[0] if len(kalan) == 1 else None


def ay_listesini_coz(yil: int, ay: int, sabah: str, aksam: str, gece: str) -> Dict[date, GunVardiyalari]:
    """Kağıttaki üç satırı (her biri ayın gün sayısı kadar A/B/C/D harfi;
    boşluklar yok sayılır) günlere çevirir. Her günde üç farklı vardiya olmalı."""
    gun_sayisi = monthrange(yil, ay)[1]
    satirlar = []
    for ad, satir in (("07:00-15:00", sabah), ("15:00-23:00", aksam), ("23:00-07:00", gece)):
        temiz = "".join((satir or "").split()).upper()
        if len(temiz) != gun_sayisi:
            raise CizelgeHatasi(f"{ad} satırında {gun_sayisi} harf olmalı, {len(temiz)} harf var")
        hatali = sorted(set(temiz) - set(VARDIYALAR))
        if hatali:
            raise CizelgeHatasi(f"{ad} satırında geçersiz harf: {', '.join(hatali)} (yalnızca A, B, C, D)")
        satirlar.append(temiz)
    sonuc = {}
    for i in range(gun_sayisi):
        v = (satirlar[0][i], satirlar[1][i], satirlar[2][i])
        if len(set(v)) != 3:
            raise CizelgeHatasi(f"{i + 1}. gün: aynı vardiya birden fazla dilimde ({'/'.join(v)})")
        sonuc[date(yil, ay, i + 1)] = v
    return sonuc


def donguden_hesapla(liste: Dict[date, GunVardiyalari], gun: date) -> Optional[GunVardiyalari]:
    """Listesi girilmemiş `gun` için 20 günlük döngüden hesaplar: kendisinden
    ÖNCEKİ en son listeli günün son 20 gününün tekrarı (iki liste arasındaki
    boşluk da önceki listeden devam eder). İlk listeden önceki günler ilk 20
    günün geriye doğru tekrarıdır. Döngü için ardışık 20 günlük liste yoksa None."""
    if gun in liste:
        return liste[gun]
    if not liste:
        return None
    onceki = [g for g in liste if g < gun]
    if onceki:
        pencere_basi = max(onceki) - timedelta(days=DONGU_GUN - 1)
    else:
        pencere_basi = min(liste)
    pencere = [pencere_basi + timedelta(days=i) for i in range(DONGU_GUN)]
    if any(g not in liste for g in pencere):
        return None
    return liste[pencere[(gun - pencere_basi).days % DONGU_GUN]]


def ekim_2026() -> Dict[date, GunVardiyalari]:
    return ay_listesini_coz(2026, 10, *EKIM_2026)


def ay_satirlari(gunler: Sequence[Tuple[date, GunVardiyalari]]) -> Tuple[str, str, str]:
    """ay_listesini_coz'un tersi: günlerden üç satır metni üretir."""
    return tuple("".join(v[i] for _, v in gunler) for i in range(3))
