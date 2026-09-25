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


# ============================================================================
# tahmin_et() -- KÖK NEDEN REGRESYON TESTLERİ (2026-09-17)
# ============================================================================
# Sahada aylarca süren "hiçbir model/eşik/kontrast/kare boyutu ile TEK bir
# plaka bile tespit edilemiyor" şikayetinin gerçek nedeni burada bulundu:
# fast_alpr.ALPR.predict() İÇ İÇE bir nesne dönüyor (ALPRResult(detection=
# DetectionResult(confidence=.., bounding_box=BoundingBox(x1=.., ..)),
# ocr=OcrResult(text=.., confidence=[karakter başına LİSTE]))) ama tahmin_et()
# DÜZ (sonuc.plate/sonuc.text, sonuc.score/sonuc.confidence) alanlar
# bekliyordu -- bunlar hiç var olmadığından HER aday sessizce atılıyordu.
# Kullanıcının kendi makinesinde fast_alpr'ı BU sarmalayıcıyı hiç kullanmadan
# doğrudan çağırdığı canlı bir teşhis testinde plaka ("34MRU796") yüksek
# güvenle (0.847 dedektör, ~0.999 OCR karakterleri) bulundu; aşağıdaki sahte
# nesneler o gerçek çıktının YAPISINI birebir taklit eder -- eski
# `_SahteALPR.predict()` (her zaman []) bu ayrıştırma mantığını hiç
# çalıştırmadığı için hata aylarca fark edilmemişti.

class _SahteKutuIcIce:
    def __init__(self, x1, y1, x2, y2):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2


class _SahteTespitIcIce:
    def __init__(self, confidence, bounding_box):
        self.label = "License Plate"
        self.confidence = confidence
        self.bounding_box = bounding_box


class _SahteOcrIcIce:
    def __init__(self, text, confidence, region="Turkey"):
        self.text = text
        self.confidence = confidence
        self.region = region


class _SahteSonucIcIce:
    """Kurulu fast_alpr sürümünün GERÇEKTE döndürdüğü iç içe yapı."""

    def __init__(self, detection, ocr):
        self.detection = detection
        self.ocr = ocr


class _SahteSonucDuz:
    """Olası eski/farklı bir sürümün düz (nested olmayan) yapısı --
    geriye dönük uyumluluk için hâlâ desteklenmeli."""

    def __init__(self, plate, score, box):
        self.plate = plate
        self.score = score
        self.box = box


def _motor_olustur(monkeypatch, sahte_fast_alpr, tahminler):
    """predict() çağrıldığında `tahminler`i döndüren bir motor kurar."""
    monkeypatch.delenv("PTS_ANPR_DETECTOR_ESIGI", raising=False)
    monkeypatch.delenv("PTS_ANPR_DETECTOR_MODEL", raising=False)
    motor = anpr_engine.ANPREngine()
    motor._alpr.predict = lambda frame: tahminler
    return motor


def test_tahmin_et_ic_ice_gercek_kutuphane_yapisini_dogru_ayristirir(monkeypatch, sahte_fast_alpr):
    """Kullanıcının gerçek teşhis çıktısıyla birebir aynı yapı (bkz. modül
    başındaki not) artık doğru şekilde bir PlakaSonucu'na dönüşmeli --
    ÖNCEKİ kod bunu sessizce atıyordu, bu yüzden bu test önceki halde
    BAŞARISIZ olurdu (boş liste dönerdi)."""
    ocr_guvenleri = [0.9998, 0.9999, 0.9996, 0.9997, 0.9998, 0.9997, 0.9993, 0.9985]
    ic_ice = _SahteSonucIcIce(
        detection=_SahteTespitIcIce(
            confidence=0.8470978706741433,
            bounding_box=_SahteKutuIcIce(x1=2218, y1=992, x2=2423, y2=1076),
        ),
        ocr=_SahteOcrIcIce(text="34MRU796", confidence=ocr_guvenleri),
    )
    motor = _motor_olustur(monkeypatch, sahte_fast_alpr, [ic_ice])

    sonuclar = motor.tahmin_et("sahte-kare")

    assert len(sonuclar) == 1
    assert sonuclar[0].plaka_no == "34MRU796"
    assert sonuclar[0].guven_skoru == pytest.approx(sum(ocr_guvenleri) / len(ocr_guvenleri))
    assert sonuclar[0].kutu == (2218, 992, 2423, 1076)


def test_tahmin_et_duz_eski_yapiyi_da_geriye_donuk_destekler(monkeypatch, sahte_fast_alpr):
    """Olası eski/farklı bir fast_alpr sürümünün düz yapısı da kırılmamalı."""
    duz = _SahteSonucDuz(plate="34MRU796", score=0.91, box={"xmin": 10, "ymin": 20, "xmax": 110, "ymax": 60})
    motor = _motor_olustur(monkeypatch, sahte_fast_alpr, [duz])

    sonuclar = motor.tahmin_et("sahte-kare")

    assert len(sonuclar) == 1
    assert sonuclar[0].plaka_no == "34MRU796"
    assert sonuclar[0].guven_skoru == pytest.approx(0.91)
    assert sonuclar[0].kutu == (10, 20, 110, 60)


def test_tahmin_et_bos_liste_donerse_bos_liste_doner(monkeypatch, sahte_fast_alpr):
    motor = _motor_olustur(monkeypatch, sahte_fast_alpr, [])
    assert motor.tahmin_et("sahte-kare") == []


def test_tahmin_et_metin_cikarilamayan_aday_atlanir(monkeypatch, sahte_fast_alpr):
    """Ne düz ne iç içe yapıda plaka metni bulunamıyorsa (örn. kütüphane
    hiç tanımadığımız bir üçüncü şekil dönerse) aday sessizce atlanmalı --
    hata fırlatmamalı."""
    tanimsiz = types.SimpleNamespace(garip_alan=123)
    motor = _motor_olustur(monkeypatch, sahte_fast_alpr, [tanimsiz])
    assert motor.tahmin_et("sahte-kare") == []


@pytest.mark.parametrize(
    "deger, beklenen",
    [
        (None, None),
        (0.95, pytest.approx(0.95)),
        ([0.9, 1.0], pytest.approx(0.95)),
        ([], None),
        (["gecersiz"], None),
    ],
)
def test_ocr_guveni_hesapla_tek_sayi_ve_liste_bicimlerini_destekler(deger, beklenen):
    assert anpr_engine._ocr_guveni_hesapla(deger) == beklenen


def test_kutuya_cevir_x1y1x2y2_ve_xminyminxmaxymax_destekler():
    assert anpr_engine._kutuya_cevir(_SahteKutuIcIce(x1=1, y1=2, x2=3, y2=4)) == (1, 2, 3, 4)
    assert anpr_engine._kutuya_cevir({"xmin": 5, "ymin": 6, "xmax": 7, "ymax": 8}) == (5, 6, 7, 8)
    assert anpr_engine._kutuya_cevir(None) is None


# ------------------------------------------------------------------
# OCR MODELİ SEÇİMİ + GÜVENLİ GERİ DÖNÜŞ (2026-09-25)
# ------------------------------------------------------------------

def test_ocr_modeli_varsayilan_ve_ortam_degiskeniyle_secilebilir(monkeypatch, sahte_fast_alpr):
    monkeypatch.delenv("PTS_ANPR_DETECTOR_MODEL", raising=False)
    monkeypatch.delenv("PTS_ANPR_OCR_MODEL", raising=False)
    motor = anpr_engine.ANPREngine()
    assert motor.ocr_modeli_etkin == anpr_engine.OCR_MODELI_VARSAYILAN
    assert motor._alpr.kwargs["ocr_model"] == anpr_engine.OCR_MODELI_VARSAYILAN

    monkeypatch.setenv("PTS_ANPR_OCR_MODEL", "cct-s-v2-global-model")
    motor = anpr_engine.ANPREngine()
    assert motor.ocr_modeli_etkin == "cct-s-v2-global-model"
    assert motor._alpr.kwargs["ocr_model"] == "cct-s-v2-global-model"
    assert "PTS_ANPR_OCR_MODEL" in motor.ocr_modeli_kaynagi


def test_yuklenemeyen_model_canli_sistemi_durdurmaz_varsayilana_doner(monkeypatch, sahte_fast_alpr, caplog):
    class _SeciciALPR(_SahteALPR):
        def __init__(self, **kwargs):
            if kwargs.get("ocr_model") == "olmayan-model":
                raise ValueError("model bulunamadı")
            super().__init__(**kwargs)

    monkeypatch.setattr(sahte_fast_alpr, "ALPR", _SeciciALPR)
    monkeypatch.delenv("PTS_ANPR_DETECTOR_MODEL", raising=False)
    monkeypatch.setenv("PTS_ANPR_OCR_MODEL", "olmayan-model")
    with caplog.at_level("ERROR"):
        motor = anpr_engine.ANPREngine()
    assert motor.ocr_modeli_etkin == anpr_engine.OCR_MODELI_VARSAYILAN
    assert motor._alpr.kwargs["ocr_model"] == anpr_engine.OCR_MODELI_VARSAYILAN
    assert "VARSAYILAN modellere" in caplog.text


def test_test_motoru_ortam_degiskenlerini_yok_sayar_cpu_kullanir_ve_hatayi_iletir(monkeypatch, sahte_fast_alpr):
    monkeypatch.setenv("PTS_ANPR_DETECTOR_MODEL", "yolo-v9-t-384-license-plate-end2end")
    monkeypatch.setenv("PTS_ANPR_OCR_MODEL", "cct-s-v2-global-model")
    motor = anpr_engine.ANPREngine(
        detector_model="yolo-v9-t-640-license-plate-end2end", ocr_model="cct-xs-v2-global-model",
        modelleri_ortamdan_al=False, sadece_cpu=True,
    )
    assert motor._alpr.kwargs["detector_model"] == "yolo-v9-t-640-license-plate-end2end"
    assert motor._alpr.kwargs["ocr_model"] == "cct-xs-v2-global-model"
    assert motor._alpr.kwargs["detector_providers"] == ["CPUExecutionProvider"]

    class _HataALPR(_SahteALPR):
        def __init__(self, **kwargs):
            raise ValueError("model bulunamadı")

    monkeypatch.setattr(sahte_fast_alpr, "ALPR", _HataALPR)
    with pytest.raises(ValueError):
        anpr_engine.ANPREngine(ocr_model="olmayan-model", modelleri_ortamdan_al=False, sadece_cpu=True)
