"""backend/anpr_engine.py::ANPREngine için ortam değişkeni davranış testleri.

fast_alpr kütüphanesi bu test ortamında kurulu olmayabilir (üretimde GPU/ONNX
bağımlılıkları ve gerçek model ağırlıklarının indirilmesini gerektirir); bu
yüzden gerçek `fast_alpr.ALPR` sınıfı yerine `sys.modules`'a enjekte edilen
sahte bir modül kullanılır. Bu, ANPREngine.__init__ içindeki
PTS_ANPR_DETECTOR_ESIGI / PTS_ANPR_DETECTOR_MODEL ortam değişkeni okuma ve
geçersiz kılma mantığını, hiçbir ağır bağımlılık gerektirmeden doğrular --
bu dosyadan önce anpr_engine.py için hiç test yoktu.
"""
import sys
import types

import pytest

from backend import anpr_engine


class _SahteALPR:
    """Gerçek fast_alpr.ALPR yerine geçen, kendisine verilen kwargs'ı
    kaydeden sahte sınıf -- ağır model indirme/yükleme hiç yapılmaz."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def predict(self, frame):
        return []


@pytest.fixture
def sahte_fast_alpr(monkeypatch):
    sahte_modul = types.ModuleType("fast_alpr")
    sahte_modul.ALPR = _SahteALPR
    monkeypatch.setitem(sys.modules, "fast_alpr", sahte_modul)
    return sahte_modul


def test_ortam_degiskenleri_yoksa_kutuphane_varsayilanlari_kullanilir(monkeypatch, sahte_fast_alpr):
    monkeypatch.delenv("PTS_ANPR_DETECTOR_ESIGI", raising=False)
    monkeypatch.delenv("PTS_ANPR_DETECTOR_MODEL", raising=False)

    motor = anpr_engine.ANPREngine()

    assert motor.detektor_esigi_etkin == anpr_engine.DEDEKTOR_ESIGI_KUTUPHANE_VARSAYILANI
    # Ayarlanmadığında detector_conf_thresh HİÇ geçirilmemeli -- kütüphanenin
    # kendi dahili varsayılanı (0.4) uygulanır, davranış hiç değişmez.
    assert "detector_conf_thresh" not in motor._alpr.kwargs
    assert motor.dedektor_modeli_etkin == anpr_engine.DEDEKTOR_MODELI_VARSAYILAN
    assert motor._alpr.kwargs["detector_model"] == anpr_engine.DEDEKTOR_MODELI_VARSAYILAN


def test_ortam_degiskenleri_esigi_ve_modeli_gecersiz_kilar(monkeypatch, sahte_fast_alpr):
    """PTS_ANPR_DETECTOR_ESIGI ve PTS_ANPR_DETECTOR_MODEL ayarlıysa, panelin
    hiçbir ayarından etkilenmeden doğrudan fast_alpr.ALPR()'a geçirilmeli."""
    monkeypatch.setenv("PTS_ANPR_DETECTOR_ESIGI", "0.25")
    monkeypatch.setenv("PTS_ANPR_DETECTOR_MODEL", "yolo-v9-s-608-license-plate-end2end")

    motor = anpr_engine.ANPREngine()

    assert motor.detektor_esigi_etkin == pytest.approx(0.25)
    assert motor._alpr.kwargs["detector_conf_thresh"] == pytest.approx(0.25)
    assert "PTS_ANPR_DETECTOR_ESIGI" in motor.detektor_esigi_kaynagi
    assert motor.dedektor_modeli_etkin == "yolo-v9-s-608-license-plate-end2end"
    assert motor._alpr.kwargs["detector_model"] == "yolo-v9-s-608-license-plate-end2end"
    assert "PTS_ANPR_DETECTOR_MODEL" in motor.dedektor_modeli_kaynagi


def test_virgullu_ondalik_esik_degeri_kabul_edilir(monkeypatch, sahte_fast_alpr):
    """Türkçe klavyede ondalık ayracı virgül olabilir (panelin kendi 'Min.
    plaka tanıma güveni' alanında olduğu gibi); PTS_ANPR_DETECTOR_ESIGI için
    de aynı tolerans gösterilir, kullanıcı '0,25' yazarsa da çalışmalı."""
    monkeypatch.setenv("PTS_ANPR_DETECTOR_ESIGI", "0,25")
    monkeypatch.delenv("PTS_ANPR_DETECTOR_MODEL", raising=False)

    motor = anpr_engine.ANPREngine()

    assert motor.detektor_esigi_etkin == pytest.approx(0.25)


def test_gecersiz_esik_degeri_sessizce_yutulmaz_uyari_loglanip_varsayilana_duser(monkeypatch, sahte_fast_alpr, caplog):
    monkeypatch.setenv("PTS_ANPR_DETECTOR_ESIGI", "abc-gecersiz")
    monkeypatch.delenv("PTS_ANPR_DETECTOR_MODEL", raising=False)

    with caplog.at_level("WARNING"):
        motor = anpr_engine.ANPREngine()

    assert motor.detektor_esigi_etkin == anpr_engine.DEDEKTOR_ESIGI_KUTUPHANE_VARSAYILANI
    assert "detector_conf_thresh" not in motor._alpr.kwargs
    assert "sayıya çevrilemedi" in caplog.text


def test_bilinmeyen_model_ismi_uyariyla_birlikte_yine_de_kullanilir(monkeypatch, sahte_fast_alpr, caplog):
    """Kütüphane ileride yeni bir model eklerse (burada henüz listelenmemiş
    olsa bile) kullanıcı onu PTS_ANPR_DETECTOR_MODEL ile seçebilsin diye
    bilinmeyen isimler REDDEDİLMEZ, sadece uyarı loglanır."""
    monkeypatch.delenv("PTS_ANPR_DETECTOR_ESIGI", raising=False)
    monkeypatch.setenv("PTS_ANPR_DETECTOR_MODEL", "bilinmeyen-model-xyz")

    with caplog.at_level("WARNING"):
        motor = anpr_engine.ANPREngine()

    assert motor.dedektor_modeli_etkin == "bilinmeyen-model-xyz"
    assert motor._alpr.kwargs["detector_model"] == "bilinmeyen-model-xyz"
    assert "bilinen model listesinde yok" in caplog.text


def test_dedektor_modeli_bilgileri_tum_modeller_icin_boyut_ve_recall_icerir():
    """Panelin/logun raporladığı model bilgisi tablosunun tutarlılığı: her
    girişte boyut ve recall alanları bulunmalı (bkz. anpr_engine.py'deki
    açıklayıcı yorum -- kaynak: github.com/ankandrew/open-image-models)."""
    for model_adi, bilgi in anpr_engine.DEDEKTOR_MODELI_BILGILERI.items():
        assert "boyut" in bilgi and bilgi["boyut"] > 0
        assert "recall" in bilgi and 0 <= bilgi["recall"] <= 1
    assert anpr_engine.DEDEKTOR_MODELI_VARSAYILAN in anpr_engine.DEDEKTOR_MODELI_BILGILERI
