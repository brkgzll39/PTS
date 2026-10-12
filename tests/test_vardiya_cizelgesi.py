"""backend/vardiya_cizelgesi.py -- Bölge Müdürlüğü vardiya çizelgesi hesapları."""
from datetime import date, datetime

import pytest

from backend import vardiya_cizelgesi as vc


def test_ekim_2026_kullanicinin_tablosuyla_ayni():
    e = vc.ekim_2026()
    assert len(e) == 31
    # Kağıttaki "HAFTA TATİLİ" satırı üç satırdan bağımsız doğrulama sağlar.
    assert "".join(vc.tatil_vardiyasi(e[date(2026, 10, g)]) for g in range(1, 32)) == "CAADBBCCADDBBCAADDBCCAADBBCCADD"
    assert e[date(2026, 10, 12)] == ("C", "D", "A")


def test_gece_dilimi_ertesi_gune_tasar():
    dilimler = vc.dilim_araliklari(date(2026, 10, 1))
    assert [(k, b.isoformat(), s.isoformat()) for k, b, s in dilimler] == [
        ("sabah", "2026-10-01T07:00:00", "2026-10-01T15:00:00"),
        ("aksam", "2026-10-01T15:00:00", "2026-10-01T23:00:00"),
        ("gece", "2026-10-01T23:00:00", "2026-10-02T07:00:00"),
    ]


def test_20_gunluk_dongu_ileri_ve_geri():
    e = vc.ekim_2026()
    assert vc.donguden_hesapla(e, date(2026, 11, 1)) == e[date(2026, 10, 12)]
    assert vc.donguden_hesapla(e, date(2026, 11, 20)) == e[date(2026, 10, 31)]
    assert vc.donguden_hesapla(e, date(2026, 11, 21)) == e[date(2026, 10, 12)]
    assert vc.donguden_hesapla(e, date(2026, 9, 30)) == e[date(2026, 10, 20)]  # 1 Ekim 00-07 için
    assert vc.donguden_hesapla({}, date(2026, 11, 1)) is None


def test_listeler_arasindaki_bosluk_onceki_listeden_devam_eder():
    """Aralık girilip Kasım girilmezse Kasım, Ekim'in döngüsünden hesaplanır
    (önceden boş kalıyor, Kasım geçişleri vardiyasız kalıyordu)."""
    ekim = vc.ekim_2026()
    liste = dict(ekim)
    liste.update(vc.ay_listesini_coz(2026, 12, *(("ABCD" * 8)[:31], ("BCDA" * 8)[:31], ("CDAB" * 8)[:31])))
    assert vc.donguden_hesapla(liste, date(2026, 11, 15)) == vc.donguden_hesapla(ekim, date(2026, 11, 15))
    assert vc.donguden_hesapla(liste, date(2027, 1, 1)) == liste[date(2026, 12, 12)]


@pytest.mark.parametrize("sabah, aksam, gece, hata", [
    ("D" * 30, "A" * 31, "B" * 31, "31 harf"),
    ("X" + "D" * 30, "A" * 31, "B" * 31, "geçersiz harf"),
    ("D" * 31, "D" + "A" * 30, "B" * 31, "1. gün"),
])
def test_ay_listesi_dogrulanir(sabah, aksam, gece, hata):
    with pytest.raises(vc.CizelgeHatasi, match=hata):
        vc.ay_listesini_coz(2026, 10, sabah, aksam, gece)


def test_ay_listesi_bosluklari_ve_kucuk_harfi_kabul_eder():
    s, a, g = vc.EKIM_2026
    bosluklu = [" ".join(x.lower()) for x in (s, a, g)]
    assert vc.ay_listesini_coz(2026, 10, *bosluklu) == vc.ekim_2026()
    assert vc.ay_satirlari(sorted(vc.ekim_2026().items())) == vc.EKIM_2026
