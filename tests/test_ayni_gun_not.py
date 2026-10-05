"""2026-10-05: aynı plakanın aynı gün içindeki geçişlerine notun otomatik
taşınması (main.py::_ayni_gun_onceki_not). İzole bellek veritabanı kullanır.
NOT: fastapi + sqlalchemy gerektirir (bkz. tests/test_api.py'nin başlığı)."""
from datetime import datetime, timedelta

import pytest

from backend import models
from backend import main as pts_main


@pytest.fixture
def db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    motor = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(motor)
    oturum = sessionmaker(bind=motor)()
    try:
        yield oturum
    finally:
        oturum.close()
        motor.dispose()


SIMDI = datetime(2026, 10, 5, 12, 0, 0)


def _kayit(db, plaka, saat, not_metni=None, gun=0):
    db.add(models.Kayit(
        plaka_no=plaka, kamera_id="K", yon="giris", yetki_durumu="yetkili", not_metni=not_metni,
        tarih_saat=SIMDI.replace(hour=saat) - timedelta(days=gun),
    ))
    db.commit()


def test_bugunku_son_gecisin_notu_tasinir(db):
    _kayit(db, "34 ABC 123", 9, "HAMITABAT")
    assert pts_main._ayni_gun_onceki_not(db, "34 ABC 123", SIMDI) == "HAMITABAT"


def test_plaka_bosluk_ve_harf_farki_onemsiz(db):
    _kayit(db, "34 ABC 123", 9, "HAMITABAT")
    assert pts_main._ayni_gun_onceki_not(db, "34abc123", SIMDI) == "HAMITABAT"


def test_baska_plakanin_notu_tasinmaz(db):
    _kayit(db, "34 ABC 123", 9, "HAMITABAT")
    assert pts_main._ayni_gun_onceki_not(db, "06 XYZ 999", SIMDI) is None


def test_dunun_notu_bugune_tasinmaz(db):
    _kayit(db, "34 ABC 123", 9, "DÜNKÜ NOT", gun=1)
    assert pts_main._ayni_gun_onceki_not(db, "34 ABC 123", SIMDI) is None


def test_en_son_gecis_belirleyici_degisen_not_kazanir(db):
    _kayit(db, "34 ABC 123", 8, "ESKİ")
    _kayit(db, "34 ABC 123", 10, "YENİ")
    assert pts_main._ayni_gun_onceki_not(db, "34 ABC 123", SIMDI) == "YENİ"


def test_en_son_gecisteki_not_silindiyse_tasima_durur(db):
    _kayit(db, "34 ABC 123", 8, "ESKİ")
    _kayit(db, "34 ABC 123", 10, None)  # görevli sonraki geçişte notu bilerek sildi
    assert pts_main._ayni_gun_onceki_not(db, "34 ABC 123", SIMDI) is None


def test_bos_veya_bosluk_not_none_sayilir(db):
    _kayit(db, "34 ABC 123", 9, "   ")
    assert pts_main._ayni_gun_onceki_not(db, "34 ABC 123", SIMDI) is None


def test_hic_kayit_yoksa_none(db):
    assert pts_main._ayni_gun_onceki_not(db, "34 ABC 123", SIMDI) is None
