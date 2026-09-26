"""backend/telegram_bildirim.py için saf birim testleri.

fastapi/veritabanına ihtiyaç duymaz -- yalnızca `urllib.request.urlopen`
monkeypatch'lenir (tıpkı tests/test_api.py'deki webhook/bariyer testlerinin
yaptığı gibi, bkz. o dosyadaki test_bariyer_ac_http_basarili).
"""
import json
import urllib.error
import urllib.request

import pytest

from backend import telegram_bildirim as tb


@pytest.fixture(autouse=True)
def _token_ayarli(monkeypatch):
    """Aksi belirtilmedikçe her testte bot token ayarlı sayılır."""
    monkeypatch.setenv("PTS_TELEGRAM_BOT_TOKEN", "123456:ABCDEF-test-token")
    yield


def test_bot_token_al_bosluk_ve_satir_sonu_temizler(monkeypatch):
    monkeypatch.setenv("PTS_TELEGRAM_BOT_TOKEN", "  gizli-token\n")
    assert tb.bot_token_al() == "gizli-token"


def test_bot_token_yoksa_ayarli_degil(monkeypatch):
    monkeypatch.delenv("PTS_TELEGRAM_BOT_TOKEN", raising=False)
    assert tb.telegram_ayarli_mi() is False
    basarili, hata = tb.telegram_gonder_sync("123", {"mesaj": "test"})
    assert basarili is False
    assert "PTS_TELEGRAM_BOT_TOKEN" in hata


def test_chat_id_bos_ise_gonderilmez(monkeypatch):
    basarili, hata = tb.telegram_gonder_sync("   ", {"mesaj": "test"})
    assert basarili is False
    assert "chat_id" in hata


def test_mesaj_metni_olay_ve_alanlari_iceriyor():
    metin = tb._mesaj_metni_olustur({
        "olay": "kamera_arizasi", "mesaj": "Kamera donuk", "kamera_ad": "Nizamiye Giriş",
    })
    assert "kamera_arizasi" in metin
    assert "Kamera donuk" in metin
    assert "Nizamiye Giriş" in metin


def test_mesaj_metni_bilinmeyen_alani_sessizce_atlar():
    metin = tb._mesaj_metni_olustur({"mesaj": "test", "bilinmeyen_alan": "her ne ise"})
    assert "bilinmeyen_alan" not in metin
    assert "her ne ise" not in metin


def test_telegram_gonder_basarili(monkeypatch):
    gonderilen = {}

    class _SahteCevap:
        def read(self):
            return b'{"ok": true}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _sahte_urlopen(req, timeout=None):
        gonderilen["url"] = req.full_url
        gonderilen["govde"] = json.loads(req.data.decode("utf-8"))
        return _SahteCevap()

    monkeypatch.setattr(urllib.request, "urlopen", _sahte_urlopen)
    basarili, hata = tb.telegram_gonder_sync("987654321", {"mesaj": "Test bildirimi", "plaka_no": "34 ABC 123"})
    assert basarili is True
    assert hata is None
    assert gonderilen["url"] == f"{tb.TELEGRAM_API_KOKU}/bot123456:ABCDEF-test-token/sendMessage"
    assert gonderilen["govde"]["chat_id"] == "987654321"
    assert "Test bildirimi" in gonderilen["govde"]["text"]
    assert "34 ABC 123" in gonderilen["govde"]["text"]


def test_telegram_gonder_yanlis_chat_id_aciklamasi_donuyor(monkeypatch):
    """Telegram API'sinin GERÇEK hata biçimini (JSON gövdeli 400) taklit
    eder -- panelde/`/bildirim/test` yanıtında "ağ hatası" gibi belirsiz bir
    mesaj yerine Telegram'ın kendi "chat not found" açıklaması görünmeli."""
    def _hata_veren_urlopen(req, timeout=None):
        import io
        govde = json.dumps({"ok": False, "description": "Bad Request: chat not found"}).encode()
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(govde))

    monkeypatch.setattr(urllib.request, "urlopen", _hata_veren_urlopen)
    basarili, hata = tb.telegram_gonder_sync("yanlis-id", {"mesaj": "test"})
    assert basarili is False
    assert "chat not found" in hata


def test_telegram_gonder_ag_hatasi(monkeypatch):
    def _hata_veren_urlopen(req, timeout=None):
        raise OSError("bağlantı reddedildi")

    monkeypatch.setattr(urllib.request, "urlopen", _hata_veren_urlopen)
    basarili, hata = tb.telegram_gonder_sync("123", {"mesaj": "test"})
    assert basarili is False
    assert "bağlantı reddedildi" in hata
