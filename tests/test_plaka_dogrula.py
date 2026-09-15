"""backend/camera_reader.py::plaka_dogrula için birim testleri.

Bu fonksiyon, kameradan/OCR'dan gelen ham metni Türk plaka formatına göre
doğrular ve normalize eder. Yanlış il kodu, hatalı harf/rakam sayısı gibi
durumların doğru şekilde reddedildiğinden emin olunur.
"""
import pytest

from backend.camera_reader import plaka_dogrula


@pytest.mark.parametrize("girdi, beklenen", [
    ("34ABC123", "34 ABC 123"),
    ("34 ABC 123", "34 ABC 123"),
    ("34abc123", "34 ABC 123"),        # küçük harf normalize edilmeli
    ("06A1234", "06 A 1234"),           # tek harf, 4 haneli
    ("01A12", "01 A 12"),                # tek harf, 2 haneli (izin verilen minimum)
    ("81ABC99", "81 ABC 99"),           # en yüksek geçerli il kodu (81)
])
def test_gecerli_plakalar_kabul_edilir(girdi, beklenen):
    assert plaka_dogrula(girdi) == beklenen


@pytest.mark.parametrize("girdi", [
    "00ABC123",   # il kodu 0 -> geçersiz
    "82ABC123",   # il kodu 81'i aşıyor -> geçersiz
    "99ABC123",   # il kodu geçersiz
    "ABC1234",    # il kodu (rakam) yok
    "34ABCD123",  # 4 harf -> Türk plaka formatında en fazla 3 harf olur
    "",           # boş girdi
    "sadece metin",
])
def test_gecersiz_plakalar_reddedilir(girdi):
    assert plaka_dogrula(girdi) is None


def test_bosluklar_yok_sayilarak_karsilastirilir():
    """README'de belirtilen kural: '34ABC123' ile '34 ABC 123' aynı kabul edilmeli."""
    assert plaka_dogrula("34ABC123") == plaka_dogrula("34 ABC 123")
