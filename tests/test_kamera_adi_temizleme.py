"""2026-10-05: kayıtlara damgalanan kamera adı artık Türkçe harfleri KORUR.

Eskiden `Kayit.kamera_id` yalnızca ASCII'ye indirgeniyordu ("Giriş Kamerası" ->
"Giri Kameras"); bu yüzden kamera adı değişince eski kayıtlar bulunamıyor ve
kamera bazlı erişim kısıtlaması o kameranın kayıtlarını sessizce gizliyordu.
NOT: fastapi + sqlalchemy gerektirir (bkz. tests/test_api.py'nin başlığı)."""
import pytest

from backend import models
from backend import main as pts_main


def test_kamera_adi_turkce_harfleri_ve_parantezi_korur():
    t = pts_main._kamera_adini_kayit_icin_temizle
    assert t("Giriş Kamerası") == "Giriş Kamerası"
    assert t("ROI Test Kamerası (Yeni)") == "ROI Test Kamerası (Yeni)"
    assert t("Çıkış-2_Öğrenci.Yolu") == "Çıkış-2_Öğrenci.Yolu"


def test_kamera_adi_tehlikeli_karakterleri_siler_ve_bos_ise_varsayilana_duser():
    t = pts_main._kamera_adini_kayit_icin_temizle
    assert t("<b>Giriş</b>;--") == "bGirişb--"
    assert t("  <>  ") == "KAMERA-1"
    assert len(t("Ş" * 80)) == 50


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


def _kayit(db, kamera_id):
    k = models.Kayit(plaka_no="34 TST 001", kamera_id=kamera_id, yon="giris", yetki_durumu="yetkili")
    db.add(k)
    db.commit()
    return k


def test_eski_ascii_kamera_adlari_onarilir_ve_islem_tekrarlanabilir(db):
    k1 = _kayit(db, "Giri Kameras")
    k2 = _kayit(db, "Cikis")           # zaten doğru/ASCII: dokunulmaz
    kameralar = [{"ad": "Giriş Kamerası"}, {"ad": "Cikis"}]
    assert pts_main._kayit_kamera_adlarini_onar(db, kameralar) == 1
    db.expire_all()
    assert db.get(models.Kayit, k1.id).kamera_id == "Giriş Kamerası"
    assert db.get(models.Kayit, k2.id).kamera_id == "Cikis"
    assert pts_main._kayit_kamera_adlarini_onar(db, kameralar) == 0


def test_onarim_belirsiz_eslesmelerde_hicbir_seyi_degistirmez(db):
    # İki farklı kamera aynı eski biçime ("Gie") indirgeniyor -> hangisi olduğu bilinemez.
    k = _kayit(db, "Gie")
    assert pts_main._kayit_kamera_adlarini_onar(db, [{"ad": "Gişe"}, {"ad": "Giçe"}]) == 0
    db.expire_all()
    assert db.get(models.Kayit, k.id).kamera_id == "Gie"
    # Eski biçim, başka bir kameranın GERÇEK adıysa da dokunulmaz.
    assert pts_main._kayit_kamera_adlarini_onar(db, [{"ad": "Giriş Kamerası"}, {"ad": "Giri Kameras"}]) == 0
