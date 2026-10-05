"""2026-10-05: Kişiler toplu işlemleri, Excel içe aktarma modları ve eski
geçiş kayıtlarını yeniden bağlama aracı.

Bu testler paylaşımlı test veritabanına DOKUNMAZ: işlev katmanı, her test için
sıfırdan kurulan BELLEKTEKİ bir SQLite veritabanıyla (izole `db`) çağrılır;
yalnızca yetki/doğrulama davranışı HTTP üzerinden (ve yan etkisiz) denenir.
NOT: fastapi + sqlalchemy gerektirir (bkz. tests/test_api.py'nin başlığı)."""
import io
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from backend import models, schemas
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


def _kullanici(rol="yonetici", ad="test-yonetici"):
    return models.Kullanici(kullanici_adi=ad, rol=rol)


def _kisi(db, ad, plaka, tip="personel", aktif=True, ek=()):
    k = models.Kisi(ad_soyad=ad, plaka_no=plaka, tip=tip, aktif=aktif)
    db.add(k)
    db.flush()
    for e in ek:
        db.add(models.KisiPlaka(kisi_id=k.id, plaka_no=e))
    db.commit()
    return k


def _kayit(db, plaka, durum, kisi_id=None, tip_anlik=None, dakika_once=60):
    kayit = models.Kayit(
        plaka_no=plaka, kamera_id="TEST", yon="giris", yetki_durumu=durum,
        kisi_id=kisi_id, kisi_tip_anlik=tip_anlik,
        tarih_saat=datetime.now() - timedelta(minutes=dakika_once),
    )
    db.add(kayit)
    db.commit()
    return kayit


# ------------------------------------------------------------------
# Toplu işlem
# ------------------------------------------------------------------

def test_toplu_pasif_ve_aktif_yapar(db):
    a, b, c = _kisi(db, "A", "34 AAA 001"), _kisi(db, "B", "34 BBB 002"), _kisi(db, "C", "34 CCC 003")
    sonuc = pts_main.kisiler_toplu_islem(schemas.KisiTopluIslem(ids=[a.id, b.id], islem="pasif"), db, _kullanici("operatör"))
    assert sonuc == {"islem": "pasif", "islenen": 2, "bulunamayan": 0}
    db.expire_all()
    assert [db.get(models.Kisi, i).aktif for i in (a.id, b.id, c.id)] == [False, False, True]
    pts_main.kisiler_toplu_islem(schemas.KisiTopluIslem(ids=[a.id], islem="aktif"), db, _kullanici())
    db.expire_all()
    assert db.get(models.Kisi, a.id).aktif is True and db.get(models.Kisi, b.id).aktif is False


def test_toplu_tip_degistirir_ve_gecersiz_tipi_reddeder(db):
    a = _kisi(db, "A", "34 AAA 001", tip="abone")
    pts_main.kisiler_toplu_islem(schemas.KisiTopluIslem(ids=[a.id], islem="tip", tip="personel"), db, _kullanici())
    db.expire_all()
    assert db.get(models.Kisi, a.id).tip == "personel"
    for kotu in (None, "", "yonetici"):
        with pytest.raises(HTTPException) as e:
            pts_main.kisiler_toplu_islem(schemas.KisiTopluIslem(ids=[a.id], islem="tip", tip=kotu), db, _kullanici())
        assert e.value.status_code == 400


def test_toplu_sil_kayitlari_korur_baglantiyi_koparir_ek_plakalari_siler(db):
    a = _kisi(db, "A", "34 AAA 001", ek=("34 AAA 002",))
    b = _kisi(db, "B", "34 BBB 001")
    kayit = _kayit(db, "34 AAA 001", "yetkili", kisi_id=a.id)
    sakin = models.Kullanici(kullanici_adi="sakin-a", rol="sakin", kisi_id=a.id, parola_hash="x")
    db.add(sakin)
    db.commit()

    sonuc = pts_main.kisiler_toplu_islem(schemas.KisiTopluIslem(ids=[a.id, 99999], islem="sil"), db, _kullanici())
    assert sonuc == {"islem": "sil", "islenen": 1, "bulunamayan": 1}
    db.expire_all()
    assert db.get(models.Kisi, a.id) is None
    assert db.get(models.Kisi, b.id) is not None
    assert db.query(models.KisiPlaka).count() == 0
    assert db.get(models.Kayit, kayit.id).kisi_id is None  # geçiş kaydı SİLİNMEZ
    assert db.query(models.Kullanici).filter_by(kullanici_adi="sakin-a").one().kisi_id is None
    assert db.query(models.DenetimKaydi).filter_by(eylem="kisi_toplu_islem").count() == 1


def test_toplu_sil_operator_yapamaz_hicbir_sey_silinmez(db):
    a = _kisi(db, "A", "34 AAA 001")
    with pytest.raises(HTTPException) as e:
        pts_main.kisiler_toplu_islem(schemas.KisiTopluIslem(ids=[a.id], islem="sil"), db, _kullanici("operatör"))
    assert e.value.status_code == 403
    assert db.get(models.Kisi, a.id) is not None


def test_toplu_izleyici_hicbir_islem_yapamaz(db):
    a = _kisi(db, "A", "34 AAA 001")
    with pytest.raises(HTTPException) as e:
        pts_main.kisiler_toplu_islem(schemas.KisiTopluIslem(ids=[a.id], islem="pasif"), db, _kullanici("izleyici"))
    assert e.value.status_code == 403


def test_toplu_hic_kisi_bulunamazsa_404(db):
    with pytest.raises(HTTPException) as e:
        pts_main.kisiler_toplu_islem(schemas.KisiTopluIslem(ids=[1, 2, 3], islem="pasif"), db, _kullanici())
    assert e.value.status_code == 404


def test_toplu_islem_semasi_gecersiz_girdileri_reddeder():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        schemas.KisiTopluIslem(ids=[], islem="pasif")
    with pytest.raises(ValidationError):
        schemas.KisiTopluIslem(ids=[1], islem="yoket")
    assert schemas.KisiTopluIslem(ids=[1], islem=" SİL".replace("İ", "i")).islem == "sil"


def test_toplu_islem_cok_kisiyi_parcalara_bolerek_isler(db, monkeypatch):
    monkeypatch.setattr(pts_main, "_IN_PARCA_BOYUTU", 2)
    kisiler = [_kisi(db, f"K{i}", f"34 KKK {i:03d}") for i in range(7)]
    sonuc = pts_main.kisiler_toplu_islem(
        schemas.KisiTopluIslem(ids=[k.id for k in kisiler], islem="pasif"), db, _kullanici())
    assert sonuc["islenen"] == 7
    db.expire_all()
    assert all(db.get(models.Kisi, k.id).aktif is False for k in kisiler)


# ------------------------------------------------------------------
# Geçmiş kayıtları yeniden bağlama
# ------------------------------------------------------------------

def _yeniden_bagla_senaryosu(db):
    a = _kisi(db, "Ayşe", "34 AAA 111", tip="personel")
    b = _kisi(db, "Burak", "34 BBB 222", tip="abone", ek=("34 BBB 223",))
    return {
        "a": a, "b": b,
        "a_yetkili": _kayit(db, "34AAA111", "yetkili"),                      # boşluksuz yazım da eşleşir
        "b_ek_yetkili": _kayit(db, "34 BBB 223", "yetkili", tip_anlik="abone"),  # dolu tip korunur
        "b_dolu_onayli": _kayit(db, "34 BBB 222", "ziyaretci_onayli"),
        "yabanci": _kayit(db, "06 ZZZ 999", "yetkili"),                      # sistemde kişisi yok
        "a_yetkisiz": _kayit(db, "34 AAA 111", "yetkisiz"),
        "a_kara": _kayit(db, "34 AAA 111", "kara_liste"),
        "baskasina_bagli": _kayit(db, "34 AAA 111", "yetkili", kisi_id=b.id),
    }


def test_yeniden_bagla_onizleme_hicbir_sey_yazmaz(db):
    s = _yeniden_bagla_senaryosu(db)
    sonuc = pts_main._gecmis_kayitlari_yeniden_bagla(db, False, "t")
    assert sonuc == {
        "uygulandi": False, "baglanan_kayit": 3, "etkilenen_kisi": 2,
        "yetkisiz_aday": 1, "yetkisiz_duzeltilen": 0, "eslesmeyen_yetkili": 1,
    }
    db.expire_all()
    assert db.get(models.Kayit, s["a_yetkili"].id).kisi_id is None
    assert db.get(models.Kayit, s["a_yetkisiz"].id).yetki_durumu == "yetkisiz"
    assert db.query(models.DenetimKaydi).count() == 0


def test_yeniden_bagla_uygula_etiketi_korur_kisiyi_baglar(db):
    s = _yeniden_bagla_senaryosu(db)
    sonuc = pts_main._gecmis_kayitlari_yeniden_bagla(db, True, "t")
    assert sonuc["uygulandi"] is True and sonuc["baglanan_kayit"] == 3
    assert sonuc["yetkisiz_duzeltilen"] == 1
    db.expire_all()
    a_yetkili = db.get(models.Kayit, s["a_yetkili"].id)
    assert (a_yetkili.kisi_id, a_yetkili.yetki_durumu, a_yetkili.kisi_tip_anlik) == (s["a"].id, "yetkili", "personel")
    ek = db.get(models.Kayit, s["b_ek_yetkili"].id)
    assert (ek.kisi_id, ek.kisi_tip_anlik) == (s["b"].id, "abone")  # ek plaka -> sahibi; dolu tip korunur
    onayli = db.get(models.Kayit, s["b_dolu_onayli"].id)
    assert (onayli.kisi_id, onayli.yetki_durumu) == (s["b"].id, "ziyaretci_onayli")
    assert db.get(models.Kayit, s["yabanci"].id).kisi_id is None
    # Yetkisiz satır yeniden değerlendirilir; kara liste ve başkasına bağlı satır dokunulmaz.
    yetkisiz = db.get(models.Kayit, s["a_yetkisiz"].id)
    assert (yetkisiz.kisi_id, yetkisiz.yetki_durumu) == (s["a"].id, "yetkili")
    assert db.get(models.Kayit, s["a_kara"].id).kisi_id is None
    assert db.get(models.Kayit, s["baskasina_bagli"].id).kisi_id == s["b"].id
    assert db.query(models.DenetimKaydi).filter_by(eylem="gecmis_yeniden_bagla").count() == 1


def test_yeniden_bagla_ikinci_calistirma_bir_sey_degistirmez(db):
    _yeniden_bagla_senaryosu(db)
    pts_main._gecmis_kayitlari_yeniden_bagla(db, True, "t")
    ikinci = pts_main._gecmis_kayitlari_yeniden_bagla(db, True, "t")
    assert ikinci["baglanan_kayit"] == 0 and ikinci["yetkisiz_aday"] == 0


def test_yeniden_bagla_pasif_kisiye_de_baglar_ama_yetkisizi_yetkili_yapmaz(db):
    k = _kisi(db, "Pasif", "34 PSF 001", aktif=False)
    yetkili = _kayit(db, "34 PSF 001", "yetkili")
    yetkisiz = _kayit(db, "34 PSF 001", "yetkisiz")
    pts_main._gecmis_kayitlari_yeniden_bagla(db, True, "t")
    db.expire_all()
    assert db.get(models.Kayit, yetkili.id).kisi_id == k.id
    assert db.get(models.Kayit, yetkisiz.id).yetki_durumu == "yetkisiz"  # pasif kişi yetki vermez


def test_yeniden_bagla_yalnizca_yonetici(db):
    with pytest.raises(HTTPException) as e:
        pts_main.gecmis_kayitlari_yeniden_bagla(uygula=True, db=db, kullanici=_kullanici("operatör"))
    assert e.value.status_code == 403


# ------------------------------------------------------------------
# Excel içe aktarma: mevcut plakalar
# ------------------------------------------------------------------

class _SahteDosya:
    def __init__(self, icerik: bytes, ad="kisiler.xlsx"):
        self.filename = ad
        self._icerik = icerik

    async def read(self):
        return self._icerik


def _excel(satirlar) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ad_soyad", "plaka_no", "tip", "telefon", "daire_departman"])
    for s in satirlar:
        ws.append(list(s))
    cikti = io.BytesIO()
    wb.save(cikti)
    return cikti.getvalue()


def _ice_aktar(db, satirlar, mod="atla"):
    import asyncio
    return asyncio.run(pts_main.toplu_kisi_import(
        dosya=_SahteDosya(_excel(satirlar)), mod=mod, db=db, kullanici=_kullanici("operatör")))


def test_import_ayni_dosyayi_iki_kez_yuklemek_kisileri_ikiye_katlamaz(db):
    satirlar = [("Ali", "34 ALI 001", "abone", "5551112233", "A1"), ("Veli", "34 VEL 002, 34 VEL 003", "personel", "", "")]
    ilk = _ice_aktar(db, satirlar)
    assert ilk["eklendi"] == 2 and ilk["eklenen_ek_plaka"] == 1
    ikinci = _ice_aktar(db, satirlar)
    assert ikinci["eklendi"] == 0 and ikinci["atlandi"] == 2
    assert "zaten kayıtlı" in ikinci["atlanan"][0]
    assert db.query(models.Kisi).count() == 2 and db.query(models.KisiPlaka).count() == 1


def test_import_ayni_dosyada_tekrar_eden_plaka_ikinci_kez_eklenmez(db):
    sonuc = _ice_aktar(db, [("Ali", "34 ALI 001", "abone", "", ""), ("Ali Kopya", "34 ali 001", "abone", "", "")])
    assert sonuc["eklendi"] == 1 and sonuc["atlandi"] == 1


def test_import_guncelle_modu_yalnizca_dolu_alanlari_gunceller_ve_ek_plaka_ekler(db):
    ali = _kisi(db, "Ali", "34 ALI 001", tip="abone")
    ali.telefon, ali.daire_departman = "111", "A1"
    db.commit()
    sonuc = _ice_aktar(db, [("Ali Yılmaz", "34 ALI 001; 34 ALI 009", "personel", "", "B2")], mod="guncelle")
    assert (sonuc["eklendi"], sonuc["guncellendi"], sonuc["eklenen_ek_plaka"]) == (0, 1, 1)
    db.expire_all()
    ali = db.get(models.Kisi, ali.id)
    assert (ali.ad_soyad, ali.tip, ali.telefon, ali.daire_departman) == ("Ali Yılmaz", "personel", "111", "B2")  # boş telefon silmez
    assert [e.plaka_no for e in ali.ek_plakalar] == ["34 ALI 009"]
    assert db.query(models.Kisi).count() == 1


def test_import_guncelle_modu_degisiklik_yoksa_degismeyen_sayar(db):
    _kisi(db, "Ali", "34 ALI 001", tip="abone")
    sonuc = _ice_aktar(db, [("Ali", "34 ALI 001", "abone", "", "")], mod="guncelle")
    assert (sonuc["guncellendi"], sonuc["degismeyen"]) == (0, 1)


def test_import_guncelle_modu_farkli_kisilere_ait_plakalari_atlar_ve_bildirir(db):
    _kisi(db, "Ali", "34 ALI 001")
    _kisi(db, "Veli", "34 VEL 002")
    sonuc = _ice_aktar(db, [("Karışık", "34 ALI 001, 34 VEL 002", "abone", "", "")], mod="guncelle")
    assert sonuc["guncellendi"] == 0 and "farklı kişilere" in sonuc["hatalar"][0]
    assert db.query(models.KisiPlaka).count() == 0


def test_import_gecersiz_mod_400(db):
    import asyncio
    with pytest.raises(HTTPException) as e:
        asyncio.run(pts_main.toplu_kisi_import(
            dosya=_SahteDosya(_excel([("Ali", "34 ALI 001", "abone", "", "")])), mod="sil", db=db, kullanici=_kullanici()))
    assert e.value.status_code == 400


def test_import_yeni_kisi_gecmis_yetkisiz_kayitlarini_duzeltir(db):
    eski = _kayit(db, "34 YNI 001", "yetkisiz")
    sonuc = _ice_aktar(db, [("Yeni", "34 YNI 001", "personel", "", "")])
    assert sonuc["guncellenen_gecmis_kayit"] == 1
    db.expire_all()
    assert db.get(models.Kayit, eski.id).yetki_durumu == "yetkili"
