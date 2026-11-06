"""Kamera parolalarının diskte şifreli saklanması (2026-11-06, backend/gizli.py)."""
import json
import os

import pytest

from fastapi.testclient import TestClient

from backend import gizli


@pytest.fixture(scope="module")
def client():
    from backend.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def yetkili_header(client):
    from backend import main
    main._hiz_sinir_giris.sifirla()
    client.post("/auth/ilk-yonetici", json={"kullanici_adi": "admin", "parola": "GucluParola123!"})
    r = client.post("/auth/giris", json={"kullanici_adi": "admin", "parola": "GucluParola123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def ayri_anahtar(tmp_path, monkeypatch):
    monkeypatch.setenv("PTS_GIZLI_ANAHTAR_DOSYASI", str(tmp_path / "anahtar.key"))
    monkeypatch.delenv("PTS_GIZLI_ANAHTAR", raising=False)
    gizli._sifirla_test_icin()
    yield tmp_path
    gizli._sifirla_test_icin()


def test_sifrele_coz_ve_anahtar_dosyasi(ayri_anahtar):
    s = gizli.sifrele("Gizli:P@ss")
    assert s.startswith("enc1:") and "Gizli" not in s
    assert gizli.coz(s) == "Gizli:P@ss"
    assert gizli.coz("acik") == "acik"            # şifresiz değer olduğu gibi
    assert (ayri_anahtar / "anahtar.key").read_text().startswith(("duz:", "dpapi:"))


def test_rtsp_ayir_ekle():
    url = "rtsp://admin:Ab%40c12@192.168.1.71:554/cam/realmonitor?channel=1"
    temiz, parola = gizli.rtsp_parolasini_ayir(url)
    assert temiz == "rtsp://admin@192.168.1.71:554/cam/realmonitor?channel=1"
    assert parola == "Ab%40c12"
    assert gizli.rtsp_parolasini_ekle(temiz, parola) == url
    assert gizli.rtsp_parolasini_ayir("rtsp://192.168.1.5/x") == ("rtsp://192.168.1.5/x", None)


def test_anahtar_kaybolursa_kamera_isaretlenir_parola_korunur(ayri_anahtar):
    disk = gizli.kamera_diske({"ad": "K", "rtsp_url": "rtsp://admin:abc@1.2.3.4/x"})
    (ayri_anahtar / "anahtar.key").unlink()
    gizli._sifirla_test_icin()                    # yeni anahtar -> eski şifre çözülemez
    bellek = gizli.kamera_diskten(disk)
    assert bellek["parola_cozulemedi"] is True
    assert bellek["rtsp_url"] == "rtsp://admin@1.2.3.4/x"
    # Başka bir alan değişip yeniden yazılırsa eski şifreli parola kaybolmaz.
    tekrar = gizli.kamera_diske(bellek)
    assert tekrar["rtsp_parola"] == disk["rtsp_parola"] and "parola_cozulemedi" not in tekrar


def test_cameras_json_eski_acik_metin_tasinir_ve_diskte_parola_kalmaz(client, yetkili_header):
    from backend import main
    with open(main.KAMERA_DOSYASI, "w", encoding="utf-8") as f:
        json.dump([{"id": "k-gizli", "ad": "Gizli Test", "rtsp_url": "rtsp://admin:CokGizli1@10.0.0.9:554/s",
                    "yon": "giris", "aktif": False}], f)
    assert main._kamera_parolalarini_sifrele() == 1
    ham = open(main.KAMERA_DOSYASI, encoding="utf-8").read()
    assert "CokGizli1" not in ham and "enc1:" in ham
    assert main._kamera_parolalarini_sifrele() == 0   # ikinci kez bir şey yapmaz
    # Bellekte eskisi gibi parolalı adres kullanılır.
    k = [k for k in main._kameralari_oku() if k["id"] == "k-gizli"][0]
    assert k["rtsp_url"] == "rtsp://admin:CokGizli1@10.0.0.9:554/s"
    # API parolayı (şifreli hali dahil) göndermez.
    r = client.get("/kameralar", headers=yetkili_header)
    govde = json.dumps(r.json())
    assert "CokGizli1" not in govde and "enc1:" not in govde
    os.remove(main.KAMERA_DOSYASI)


def test_kamera_yazilinca_parola_diskte_sifreli():
    """Kamera ekleme/düzenleme uçlarının hepsi _kameralari_yaz'dan geçer."""
    from backend import main
    main._kameralari_yaz([{"id": "k-yeni", "ad": "Yeni Gizli",
                           "rtsp_url": "rtsp://admin:YeniParola9@10.0.0.10:554/s", "yon": "giris", "aktif": False}])
    ham = open(main.KAMERA_DOSYASI, encoding="utf-8").read()
    assert "YeniParola9" not in ham and "enc1:" in ham
    assert main._kameralari_oku()[0]["rtsp_url"] == "rtsp://admin:YeniParola9@10.0.0.10:554/s"
    os.remove(main.KAMERA_DOSYASI)
