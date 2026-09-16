"""backend/lisans.py için birim testleri (üretim, doğrulama, kurcalama tespiti).

Bu modül lisans_uretici.py (CLI) ve main.py (API) tarafından ortak kullanılır;
imzalama mantığındaki en ufak bir bozulma tüm lisansları geçersiz kılabileceği
için burada ayrıntılı test edilir.
"""
import hashlib
import hmac
import json

import pytest

from backend import lisans


@pytest.fixture(autouse=True)
def _sabit_secret(monkeypatch):
    """Her testte aynı, bilinen bir PTS_LICENSE_SECRET kullanılmasını sağlar."""
    monkeypatch.setenv("PTS_LICENSE_SECRET", "test-icin-sabit-secret")


def test_uretilen_lisans_dogrulanir():
    anahtar = lisans.uret("Test Site", kamera_limiti=4, gun=30)
    payload = lisans.coz(anahtar)
    assert payload["musteri"] == "Test Site"
    assert payload["kamera_limiti"] == 4
    assert payload["cihaz_kodu"] is None


def test_gecersiz_parametreler_reddedilir():
    with pytest.raises(ValueError):
        lisans.uret("Site", kamera_limiti=0, gun=30)
    with pytest.raises(ValueError):
        lisans.uret("Site", kamera_limiti=2, gun=0)


def test_yanlis_secret_ile_dogrulama_reddedilir(monkeypatch):
    anahtar = lisans.uret("Test Site", kamera_limiti=2, gun=30)
    monkeypatch.setenv("PTS_LICENSE_SECRET", "baska-bir-secret")
    with pytest.raises(lisans.LisansGecersiz):
        lisans.coz(anahtar)


def test_kurcalanmis_govde_reddedilir():
    """Payload'ı değiştirip imzayı olduğu gibi bırakmak (kamera limitini
    yükseltmeye çalışmak gibi) tespit edilmeli."""
    anahtar = lisans.uret("Test Site", kamera_limiti=2, gun=30)
    versiyon, govde, imza = anahtar.split(".", 2)
    payload = json.loads(lisans._b64_coz(govde))
    payload["kamera_limiti"] = 999  # kötü niyetli değişiklik
    govde_degistirilmis = lisans._b64(json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))
    sahte_anahtar = f"{versiyon}.{govde_degistirilmis}.{imza}"  # imza eski, govde yeni
    with pytest.raises(lisans.LisansGecersiz):
        lisans.coz(sahte_anahtar)


def test_bozuk_format_reddedilir():
    for kotu in ["", "sadece-bir-parca", "PTS1.sadece-iki-parca", "PTS2.govde.imza"]:
        with pytest.raises(lisans.LisansGecersiz):
            lisans.coz(kotu)


def test_suresi_dolmus_lisans_reddedilir():
    anahtar = lisans.uret("Eski Site", kamera_limiti=2, gun=1)
    versiyon, govde, _imza = anahtar.split(".", 2)
    payload = json.loads(lisans._b64_coz(govde))
    payload["bitis_tarihi"] = "2000-01-01"
    govde2 = lisans._b64(json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))
    imza2 = lisans._b64(hmac.new(lisans.secret_al().encode("utf-8"), govde2.encode("ascii"), hashlib.sha256).digest())
    suresi_dolmus_anahtar = f"{versiyon}.{govde2}.{imza2}"
    with pytest.raises(lisans.LisansGecersiz, match="süresi dolmuş"):
        lisans.coz(suresi_dolmus_anahtar)


def test_cihaza_kilitli_lisans_farkli_cihazda_reddedilir():
    anahtar = lisans.uret("Kilitli Site", kamera_limiti=2, gun=30, cihaz_kodu_deger="AAAABBBBCCCCDDDD")
    with pytest.raises(lisans.LisansGecersiz):
        lisans.coz(anahtar, beklenen_cihaz_kodu="BASKA-CIHAZ-KODU")
    # doğru cihaz koduyla sorunsuz geçmeli
    payload = lisans.coz(anahtar, beklenen_cihaz_kodu="AAAABBBBCCCCDDDD")
    assert payload["cihaz_kodu"] == "AAAABBBBCCCCDDDD"


def test_cihaz_koduna_kilitli_olmayan_lisans_her_cihazda_gecer():
    anahtar = lisans.uret("Serbest Site", kamera_limiti=2, gun=30)
    payload = lisans.coz(anahtar, beklenen_cihaz_kodu="HERHANGI-BIR-CIHAZ")
    assert payload["musteri"] == "Serbest Site"


def test_cihaz_kodu_tekrarlanabilir():
    """Aynı bilgisayarda art arda çağrılınca aynı kodu üretmeli (kalıcı kimlik)."""
    assert lisans.cihaz_kodu() == lisans.cihaz_kodu()
    assert len(lisans.cihaz_kodu()) == 16


def test_secret_ayarlanmamissa_varsayilana_duser_ve_bir_kez_uyarir(monkeypatch, caplog):
    """Güvenlik regresyonu: PTS_LICENSE_SECRET ayarlanmamışsa (kaynak kodda
    herkese açık, sabit) bir geliştirme secret'ına sessizce düşülmemeli —
    en azından çalışma zamanında (CORS '*' / AUTH_SECRET için yapıldığı gibi)
    bir uyarı loglanmalı. Log spam olmasın diye süreç başına yalnızca BİR
    kez uyarılmalı."""
    monkeypatch.delenv("PTS_LICENSE_SECRET", raising=False)
    monkeypatch.setattr(lisans, "_varsayilan_secret_uyarisi_yapildi", False)
    with caplog.at_level("WARNING", logger="pts.lisans"):
        assert lisans.secret_al() == lisans.VARSAYILAN_GELISTIRME_SECRET
        assert any("PTS_LICENSE_SECRET" in kayit.message for kayit in caplog.records)
        onceki_kayit_sayisi = len(caplog.records)

        lisans.secret_al()  # ikinci çağrı: aynı süreçte tekrar uyarmamalı
        assert len(caplog.records) == onceki_kayit_sayisi


def test_secret_ayarliysa_hic_uyarmaz(monkeypatch, caplog):
    monkeypatch.setattr(lisans, "_varsayilan_secret_uyarisi_yapildi", False)
    with caplog.at_level("WARNING", logger="pts.lisans"):
        assert lisans.secret_al() == "test-icin-sabit-secret"  # autouse fixture'dan
        assert caplog.records == []
