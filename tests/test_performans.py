"""Performans bekçisi (2026-11-09, backend/performans.py)."""
import time

from backend import performans as pf


def _normal(**ek):
    o = {"zaman": "t", "veritabani_ms": 40, "havuz_kullanim": 0.1, "havuz_dolu": 1, "havuz_kapasite": 15,
         "dongu_ms": 5, "istek_p95_ms": 150, "akis_sayisi": 18, "islemci_sistem": 54, "bellek_mb": 540, "kayit_hatasi": 0}
    o.update(ek)
    return o


def test_sayaclar_p95_akis_ve_kayit_hatasi():
    s = pf.Sayaclar()
    for i in range(100):
        s.istek_bitti(i / 1000)          # 0..99 ms
    s.akis_acildi("mjpeg"); s.akis_acildi("mjpeg"); s.akis_acildi("sse"); s.akis_kapandi("mjpeg")
    s.kayit_gonderim_hatasi(); s.kayit_gonderim_hatasi()
    b = s.bosalt()
    assert b["istek_sayisi"] == 100 and 93 <= b["istek_p95_ms"] <= 95 and b["istek_en_uzun_ms"] == 99
    assert b["akis_sayisi"] == 2 and b["akislar"] == {"mjpeg": 1, "sse": 1} and b["kayit_hatasi"] == 2
    b2 = s.bosalt()                      # boşaltıldı: istekler ve hatalar sıfır, akışlar sürer
    assert b2["istek_sayisi"] == 0 and b2["kayit_hatasi"] == 0 and b2["akis_sayisi"] == 2
    s.akis_kapandi("sse"); s.akis_kapandi("sse")      # fazladan kapanma eksiye düşürmez
    assert s.akislar()["sse"] == 0


def test_tek_yavas_dakika_alarm_degil_ust_uste_uc_dakika_alarm():
    """2026-11-09 sahadaki değerler: /saglik 60 sn, havuz dolu."""
    ornekler = [_normal() for _ in range(5)] + [_normal(veritabani_ms=30000, havuz_kullanim=1.0, havuz_dolu=15)]
    assert pf.degerlendir(ornekler) == []
    ornekler += [_normal(veritabani_ms=30000, havuz_kullanim=1.0, havuz_dolu=15)] * 2
    kodlar = {s["kod"]: s for s in pf.degerlendir(ornekler)}
    assert set(kodlar) == {"veritabani_ms", "havuz_kullanim"}
    assert "30,0 sn" in kodlar["veritabani_ms"]["mesaj"] and "%100" in kodlar["havuz_kullanim"]["mesaj"]
    assert "(15/15)" in kodlar["havuz_kullanim"]["mesaj"]


def test_kayit_hatasi_bes_dakikada_uc():
    ornekler = [_normal(kayit_hatasi=1), _normal(), _normal(kayit_hatasi=1)]
    assert pf.degerlendir(ornekler) == []
    ornekler.append(_normal(kayit_hatasi=1))
    s = pf.degerlendir(ornekler)
    assert [x["kod"] for x in s] == ["kayit_hatasi"] and "3 kez" in s[0]["mesaj"]


def test_hayalet_akis_birikimi_on_dakika():
    ornekler = [_normal(akis_sayisi=100) for _ in range(9)]
    assert pf.degerlendir(ornekler) == []
    ornekler.append(_normal(akis_sayisi=100))
    assert [x["kod"] for x in pf.degerlendir(ornekler)] == ["akis_sayisi"]


def test_eksik_olcum_sorun_sayilmaz():
    assert pf.degerlendir([_normal(islemci_sistem=None) for _ in range(12)]) == []


def test_bekci_yeni_duzelen_ve_saatte_bir_bildirim():
    saat = [1000.0]
    b = pf.Bekci(saat=lambda: saat[0])
    for _ in range(2):
        assert b.ekle(_normal(veritabani_ms=9000))[0] == []
    yeni, duzelen, _ = b.ekle(_normal(veritabani_ms=9000))
    assert [s["kod"] for s in yeni] == ["veritabani_ms"] and duzelen == []
    yeni, _, sorunlar = b.ekle(_normal(veritabani_ms=9000))
    assert yeni == [] and len(sorunlar) == 1                     # süren sorun yeniden bildirilmez
    yeni, duzelen, _ = b.ekle(_normal())
    assert [s["kod"] for s in duzelen] == ["veritabani_ms"]
    # Yarım saat sonra yeniden başlarsa bildirilmez (saatte bir), bir saat sonra bildirilir.
    saat[0] += 1800
    for _ in range(3):
        yeni, _, _ = b.ekle(_normal(veritabani_ms=9000))
    assert yeni == []
    b.ekle(_normal())
    saat[0] += 3600
    for _ in range(3):
        yeni, _, _ = b.ekle(_normal(veritabani_ms=9000))
    assert [s["kod"] for s in yeni] == ["veritabani_ms"]


def test_ozet_bes_dakikalik_en_kotu_deger():
    b = pf.Bekci()
    for i in range(10):
        b.ekle(_normal(zaman=f"t{i}", istek_p95_ms=100 + i))
    o = b.ozet()
    assert len(o) == 2 and o[0]["istek_p95_ms"] == 104 and o[1]["istek_p95_ms"] == 109 and o[1]["zaman"] == "t9"


def test_islemci_ve_bellek_olculur():
    olcer = pf.IslemciOlcer()
    bas = time.process_time()
    while time.process_time() - bas < 0.2:
        pass
    sistem, pts = olcer.olc()
    assert pts > 0 and (sistem is None or 0 <= sistem <= 100)
    assert pf.bellek_mb() is None or pf.bellek_mb() > 10
