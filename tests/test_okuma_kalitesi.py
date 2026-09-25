"""backend/okuma_kalitesi.py testleri (GERÇEKTEN çalıştırıldı)."""
from backend.okuma_kalitesi import kalite_degerlendir


def test_kayit_yoksa_kayit_yok_ve_oneri():
    s = kalite_degerlendir(0, 0, 0, 0, 0, None, None)
    assert s["durum"] == "kayit_yok"
    assert s["tek_kare_orani"] is None
    assert s["oneriler"]


def test_az_kayitla_yetersiz_veri():
    s = kalite_degerlendir(5, 5, 5, 5, 5, 1.0, 0.9)
    assert s["durum"] == "yetersiz_veri"


def test_saglikli_kamera_iyi():
    s = kalite_degerlendir(200, 200, 6, 10, 4, 12.4, 0.981)
    assert s["durum"] == "iyi"
    assert s["oneriler"] == []
    assert s["tek_kare_orani"] == 0.03
    assert s["ortalama_kare"] == 12.4


def test_tek_kare_orani_esikleri():
    assert kalite_degerlendir(100, 100, 12, 0, 0, 4, 0.95)["durum"] == "dikkat"
    zayif = kalite_degerlendir(100, 100, 30, 0, 0, 2, 0.95)
    assert zayif["durum"] == "zayif"
    assert "TEK karede" in zayif["oneriler"][0]


def test_en_kotu_olcut_genel_durumu_belirler_ve_tum_oneriler_listelenir():
    s = kalite_degerlendir(100, 100, 12, 35, 11, 5, 0.9)
    assert s["durum"] == "zayif"  # kararsız okuma %35
    assert len(s["oneriler"]) == 3


def test_dogrulama_bilgisi_eksik_eski_kayitlar_orana_katilmaz():
    # 100 kayıttan yalnızca 20'sinde kare sayısı biliniyor (eski kayıtlar).
    s = kalite_degerlendir(100, 20, 2, 0, 0, 6, 0.95)
    assert s["tek_kare_orani"] == 0.1
