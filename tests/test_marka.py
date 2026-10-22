"""2026-10-23: kuruma özel görünüm marka.json'dan (bkz. backend/marka.py)."""
import json

import pytest
from fastapi.testclient import TestClient

from backend import marka
from backend import main as pts_main
from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_marka_dosyasi_yoksa_bugunku_tpao_degerleri(client, monkeypatch, tmp_path):
    monkeypatch.setenv("PTS_MARKA_FILE", str(tmp_path / "yok.json"))
    assert marka.oku() == marka.VARSAYILAN
    j = client.get("/marka").json()
    assert j["kurum_adi"] == "TÜRKİYE PETROLLERİ ANONİM ORTAKLIĞI"
    assert j["iletisim"]["eposta"] == "bguzelel@tpao.gov.tr" and j["logo_url"] is None
    manifest = client.get("/manifest.webmanifest").json()
    with open(f"{pts_main.FRONTEND_KLASORU}/manifest.json", encoding="utf-8") as f:
        assert manifest == json.load(f)   # çalışan sistemde manifest birebir aynı
    assert client.get("/marka/logo").headers["content-type"] == "image/png"


def test_marka_dosyasi_varsa_eksik_alanlar_kurumsuz_gelir(client, monkeypatch, tmp_path):
    yol = tmp_path / "marka.json"
    yol.write_text(json.dumps({"kurum_adi": "ACME A.Ş.", "kisa_ad": "ACME PTS", "iletisim": {"eposta": "it@acme.tr"},
                               "bilinmeyen_alan": 1}), encoding="utf-8")
    monkeypatch.setenv("PTS_MARKA_FILE", str(yol))
    j = client.get("/marka").json()
    assert j["kurum_adi"] == "ACME A.Ş." and j["iletisim"] == {"telefon": "", "telefon_uri": "", "dahili": "", "eposta": "it@acme.tr"}
    metin = json.dumps(client.get("/marka").json(), ensure_ascii=False) + json.dumps(marka.oku(), ensure_ascii=False)
    for tpao in ("TPAO", "T.P.A.O", "TRAKYA", "PETROLLERİ", "tpao.gov.tr", "Bölge Müdürü", "0537"):
        assert tpao not in metin
    assert marka.oku()["varsayilan_vardiya_cizelgesi"] is None
    assert client.get("/manifest.webmanifest").json()["short_name"] == "ACME PTS"
    assert j["logo_url"] == "/marka/logo"
    assert client.get("/marka/logo").headers["content-type"].startswith("image/svg")   # kurumsuz logo

    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\nkurum")
    yol.write_text(json.dumps({"kurum_adi": "ACME A.Ş.", "logo_dosyasi": "logo.png"}), encoding="utf-8")
    import os
    os.utime(yol, (1, 1))   # aynı saniyede yazılsa da önbellek yenilensin
    assert client.get("/marka/logo").content.endswith(b"kurum")


def test_bozuk_marka_dosyasinda_tpao_gorunmez(monkeypatch, tmp_path):
    yol = tmp_path / "marka.json"
    yol.write_text("{bozuk", encoding="utf-8")
    monkeypatch.setenv("PTS_MARKA_FILE", str(yol))
    assert marka.oku() == marka.GENEL


def test_ornek_marka_dosyasi_gecerli(monkeypatch):
    import os
    ornek = os.path.join(os.path.dirname(pts_main.FRONTEND_KLASORU), "installer", "marka-ornek.json")
    with open(ornek, encoding="utf-8") as f:
        assert set(json.load(f)) == set(marka.VARSAYILAN)   # tüm alanlar örnekte var


def test_cizelgesiz_kurumda_hazir_cizelge_yuklenmez(monkeypatch, tmp_path):
    yol = tmp_path / "marka.json"
    yol.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("PTS_MARKA_FILE", str(yol))
    monkeypatch.setattr(pts_main, "_cizelge_tamamlanan_gun", None)
    monkeypatch.setattr(pts_main, "_cizelge_listesi", lambda db: {})
    monkeypatch.setattr(pts_main.vardiya_cizelgesi, "ekim_2026", lambda: pytest.fail("TPAO çizelgesi yüklenmemeli"))
    db = pts_main.SessionLocal()
    try:
        pts_main._cizelge_tamamla(db)
    finally:
        db.close()
