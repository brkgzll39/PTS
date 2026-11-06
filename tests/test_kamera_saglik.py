"""Kamera sağlık bekçisi / ayar denetimi (2026-11-06, backend/kamera_saglik.py)."""
import json
import os
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend import kamera_saglik as ks

KURAL_TEK = """table.VideoAnalyseRule[0][0].Config.Direction[0]=Obverse
table.VideoAnalyseRule[0][0].Config.Direction[1]=
table.VideoAnalyseRule[0][0].Enable=true
table.VideoAnalyseRule[0][0].Type=TrafficTollGate"""
KURAL_IKI = KURAL_TEK.replace("Direction[1]=", "Direction[1]=Reverse")


def test_yonleri_ayikla():
    assert ks.yonleri_ayikla(KURAL_TEK) == ["Obverse"]
    assert ks.yonleri_ayikla(KURAL_IKI) == ["Obverse", "Reverse"]
    assert ks.yonleri_ayikla(KURAL_TEK.replace("Enable=true", "Enable=false")) is None
    assert ks.yonleri_ayikla("Error\nBad Request!") is None


def _kodlar(bilgi, mut=None):
    return [s["kod"] for s in ks.sorunlari_bul(bilgi, mut)]


def test_sorun_kurallari():
    iyi = {"ulasildi": True, "saat_farki_sn": -3, "ntp_acik": True, "yonler": ["Obverse", "Reverse"]}
    assert _kodlar(iyi) == []
    assert _kodlar({**iyi, "saat_farki_sn": 95}) == ["saat"]
    assert _kodlar({**iyi, "ntp_acik": False}) == ["ntp"]
    assert _kodlar({**iyi, "yonler": ["Obverse"]}) == ["yon"]
    assert _kodlar({**iyi, "yonler": None}) == []                      # bilinmiyorsa sorun sayılmaz
    assert _kodlar({"ulasildi": False, "hata": "x"}) == ["ulasilamadi"]
    assert _kodlar(None, {"kamera_gecis": 200, "eklenen": 30, "hata": None}) == ["kacirma"]
    assert _kodlar(None, {"kamera_gecis": 200, "eklenen": 5, "hata": None}) == []
    assert _kodlar(None, {"kamera_gecis": 10, "eklenen": 5, "hata": None}) == []   # az geçiş
    assert "dk ileride" in ks.sorunlari_bul({**iyi, "saat_farki_sn": 600}, None)[0]["mesaj"]


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


def test_denetim_yeni_sorunda_bir_kez_alarm_verir(client, yetkili_header, monkeypatch, tmp_path):
    from backend import main, models
    from backend.database import SessionLocal
    monkeypatch.setattr(main, "_KAMERA_DENETIM_DOSYASI", str(tmp_path / "denetim.json"))
    kam = {"id": "ks-1", "ad": "Denetim Kamera", "rtsp_url": "rtsp://admin:p@10.9.9.9:554/s", "yon": "giris",
           "aktif": True, "dahua_anpr": {"aktif": True, "http_port": 80}}
    monkeypatch.setattr(main, "_kameralari_oku", lambda: [kam])
    monkeypatch.setattr(main, "_dahua_kayitli_kameralar", lambda: [kam])
    cevap = {"ulasildi": True, "saat_farki_sn": 2, "ntp_acik": False, "yonler": ["Obverse"], "hata": None}
    monkeypatch.setattr(ks, "kameraya_sor", lambda *a, **k: dict(cevap))
    bildirimler = []
    monkeypatch.setattr(main, "_bildirim_tetikle", lambda db, t, v: bildirimler.append((t, v)))

    db = SessionLocal()
    try:
        db.add(models.KameraMutabakati(gun=date.today() - timedelta(days=1), kamera_ad="Denetim Kamera",
                                       kamera_gecis=100, pts_yakalanan=80, eklenen=20))
        db.commit()
        onceki = db.query(models.Alarm).filter(models.Alarm.alarm_tipi == "kamera_ayari").count()
    finally:
        db.close()

    r = client.post("/kamera-ayar-denetimi/calistir", headers=yetkili_header)
    assert r.status_code == 200, r.text
    k = r.json()["kameralar"][0]
    assert {s["kod"] for s in k["sorunlar"]} == {"ntp", "yon", "kacirma"}
    assert len(bildirimler) == 1 and bildirimler[0][0] == "kamera_ayari"
    assert "Denetim Kamera" in bildirimler[0][1]["mesaj"]

    # Aynı sorunlar ikinci kez alarm üretmez; yeni bir sorun (saat) üretir.
    client.post("/kamera-ayar-denetimi/calistir", headers=yetkili_header)
    assert len(bildirimler) == 1
    cevap["saat_farki_sn"] = 300
    client.post("/kamera-ayar-denetimi/calistir", headers=yetkili_header)
    assert len(bildirimler) == 2 and "saat" in bildirimler[1][1]["mesaj"].lower()

    db = SessionLocal()
    try:
        assert db.query(models.Alarm).filter(models.Alarm.alarm_tipi == "kamera_ayari").count() == onceki + 2
    finally:
        db.close()
    g = client.get("/kamera-ayar-denetimi", headers=yetkili_header).json()
    assert g["zaman"] and g["kameralar"][0]["ad"] == "Denetim Kamera"
    assert "10.9.9.9" not in json.dumps(g) or ":p@" not in json.dumps(g)   # parola sızmaz


def test_denetim_sabah_bir_kez_calisir(monkeypatch):
    from datetime import datetime
    from backend import main
    calisti = []
    monkeypatch.setattr(main, "_kamera_denetimi_calistir", lambda *a, **k: calisti.append(1))
    monkeypatch.setattr(main, "_kameralari_oku", lambda: [{"id": "x"}])
    monkeypatch.setattr(main, "_son_kamera_denetim_gunu", None)
    assert main._kamera_denetimi_bir_kontrol(datetime(2026, 11, 6, 6, 0)) is False
    assert main._kamera_denetimi_bir_kontrol(datetime(2026, 11, 6, 6, 31)) is True
    assert main._kamera_denetimi_bir_kontrol(datetime(2026, 11, 6, 9, 0)) is False
    assert calisti == [1]


def test_kameraya_sor_yanitlari_ayristirir(monkeypatch):
    from datetime import datetime
    from backend import dahua_kayit

    class Yanit:
        def __init__(self, metin, kod=200):
            self.text, self.status_code, self.ok = metin, kod, kod < 400

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)

    yanitlar = {"getCurrentTime": Yanit("result=2026-11-06 10:00:40\r\n"),
                "name=NTP": Yanit("table.NTP.Address=pool.ntp.org\r\ntable.NTP.Enable=false\r\n"),
                "name=VideoAnalyseRule": Yanit(KURAL_TEK)}

    class SahteBaglanti:
        def __init__(self, *a, **k):
            pass

        def getir(self, yol):
            return next(v for k, v in yanitlar.items() if k in yol)

    monkeypatch.setattr(dahua_kayit, "_Baglanti", SahteBaglanti)
    b = ks.kameraya_sor("rtsp://a:b@1.2.3.4/x", simdi=datetime(2026, 11, 6, 10, 0, 0))
    assert b == {"ulasildi": True, "saat_farki_sn": 40, "ntp_acik": False, "yonler": ["Obverse"], "hata": None}
    yanitlar["getCurrentTime"] = Yanit("", 401)
    assert "parola" in ks.kameraya_sor("rtsp://a:b@1.2.3.4/x")["hata"]


@pytest.mark.parametrize("dml_kurulu, saglayicilar, cpu_zorla, sorun_var", [
    (False, None, False, False),                                              # GPU paketi yok: CPU normal
    (True, ["DmlExecutionProvider", "CPUExecutionProvider"], False, False),  # sağlıklı
    (True, ["CPUExecutionProvider"], False, True),                           # 2026-11-06 sahadaki bozulma
    (True, ["CPUExecutionProvider"], True, False),                           # bilerek CPU'ya zorlanmış
])
def test_anpr_motoru_ekran_kartini_kaybettiyse_sorun(monkeypatch, dml_kurulu, saglayicilar, cpu_zorla, sorun_var):
    import sys
    import types
    from importlib import metadata
    from backend import main

    def surum(ad):
        if ad == "onnxruntime-directml" and dml_kurulu:
            return "1.24.4"
        raise metadata.PackageNotFoundError(ad)

    monkeypatch.setattr(metadata, "version", surum)
    sahte = types.SimpleNamespace(get_available_providers=lambda: list(saglayicilar or []))
    monkeypatch.setitem(sys.modules, "onnxruntime", sahte)
    if cpu_zorla:
        monkeypatch.setenv("PTS_ANPR_PROVIDERS", "cpu")
    else:
        monkeypatch.delenv("PTS_ANPR_PROVIDERS", raising=False)
    durum = main._anpr_motor_durumu()
    assert bool(durum["sorun"]) is sorun_var
    if sorun_var:
        assert "onnxruntime-directml==1.24.4" in durum["sorun"]


def test_anpr_motoru_alarmi_gunde_bir_kez(monkeypatch):
    from backend import main, models
    from backend.database import SessionLocal
    monkeypatch.setattr(main, "_anpr_motor_durumu", lambda: {"sorun": "Plaka motoru ekran kartını kullanamıyor (test)"})
    gonderilen = []
    monkeypatch.setattr(main, "_bildirim_tetikle", lambda db, t, v: gonderilen.append(t))
    db = SessionLocal()
    try:
        db.query(models.Alarm).filter(models.Alarm.alarm_tipi == "anpr_motoru").delete()
        db.commit()
    finally:
        db.close()
    assert main._anpr_motor_kontrol_ve_alarm()
    assert main._anpr_motor_kontrol_ve_alarm()
    assert gonderilen == ["anpr_motoru"]
