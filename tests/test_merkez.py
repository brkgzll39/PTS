"""Merkezi izleme sunucusu (merkez/) ve PTS tarafındaki istemci (backend/merkez_istemci.py)."""
import base64
import json
import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend import merkez_istemci
from merkez import uygulama
from merkez.sorunlar import genel_durum, sorunlari_hesapla

PAROLA = "merkez-test-parolasi-123"


def _basic(kullanici="yonetici", parola=PAROLA):
    return {"Authorization": "Basic " + base64.b64encode(f"{kullanici}:{parola}".encode()).decode()}


@pytest.fixture
def merkez(tmp_path, monkeypatch):
    monkeypatch.setenv("MERKEZ_VERITABANI", str(tmp_path / "merkez.db"))
    monkeypatch.setenv("MERKEZ_YONETICI_PAROLA", PAROLA)
    monkeypatch.setenv("MERKEZ_BILDIRIM_DONGUSU", "0")
    for ad in ("MERKEZ_TELEGRAM_TOKEN", "MERKEZ_SMTP_SUNUCU"):
        monkeypatch.delenv(ad, raising=False)
    uygulama._hatali_giris.clear()
    with TestClient(uygulama.app) as c:
        yield c


def _ozet(**degisen):
    ozet = {
        "zaman": datetime.now().isoformat(timespec="seconds"), "kurum": "Test AŞ", "surum": "2.0",
        "veritabani": "tamam", "son_kayit_dk": 3,
        "kameralar": [{"ad": "Giriş", "aktif": True, "goruntu": "calisiyor", "dahua_bagli": True, "son_okuma_dk": 3,
                       "bugun_okuma": 120, "mutabakat": {"gun": "2026-10-30", "kamera_gecis": 200, "oran": 98.0,
                                                         "eklenen": 4, "hata": False}}],
        "disk": {"en_dolu_yuzde": 40.0, "yollar": [{"ad": "Veritabanı", "yuzde": 40.0}]},
        "yedek": {"otomatik_acik": True, "yas_saat": 5},
        "lisans": {"aktif": True, "kalan_gun": 200}, "sertifika_kalan_gun": None,
        "alarmlar_24s": {"kara_liste": 1}, "okunmamis_alarm": 2, "kesintiler_7g": [],
    }
    ozet.update(degisen)
    return ozet


# ------------------------------------------------------------------ sorun hesaplama
def test_saglikli_kurulumda_sorun_yok():
    simdi = time.time()
    s = sorunlari_hesapla(_ozet(), simdi - 60, simdi)
    assert s == [] and genel_durum(s) == "iyi"


def test_sessiz_kurulum_cevrimdisi_sayilir():
    simdi = time.time()
    s = sorunlari_hesapla(_ozet(), simdi - 20 * 60, simdi)
    assert s[0]["kod"] == "cevrimdisi" and s[0]["seviye"] == "kritik"
    assert genel_durum(s) == "cevrimdisi"
    # 10 dakika sessizlik henüz çevrimdışı değil
    assert not sorunlari_hesapla(_ozet(), simdi - 10 * 60, simdi)


def test_sorunlar_kritik_once_ve_dogru_esiklerle():
    simdi = time.time()
    ozet = _ozet(
        kameralar=[{"ad": "Giriş", "aktif": True, "goruntu": "donmus", "dahua_bagli": False, "bugun_okuma": 0,
                    "mutabakat": {"gun": "2026-10-30", "kamera_gecis": 100, "oran": 70.0, "hata": False}},
                   {"ad": "Kapalı kamera", "aktif": False, "goruntu": "durdu"}],
        disk={"en_dolu_yuzde": 96, "yollar": [{"ad": "Veritabanı", "yuzde": 96.0}, {"ad": "Yedekler", "yuzde": 86.0}]},
        yedek={"otomatik_acik": True, "yas_saat": 40},
        lisans={"aktif": True, "kalan_gun": 5},
        alarmlar_24s={"sessiz_kamera": 1, "bildirim_hatasi": 3},
    )
    s = sorunlari_hesapla(ozet, simdi - 60, simdi)
    kodlar = {x["kod"]: x["seviye"] for x in s}
    assert kodlar["kamera_goruntu:Giriş"] == "kritik"
    assert "kamera_goruntu:Kapalı kamera" not in kodlar          # kapalı kamera sayılmaz
    assert kodlar["kamera_okuma:Giriş"] == "uyari"
    assert kodlar["mutabakat:Giriş"] == "uyari"
    assert kodlar["disk:Veritabanı"] == "kritik" and kodlar["disk:Yedekler"] == "uyari"
    assert kodlar["yedek"] == "uyari"
    assert kodlar["lisans"] == "kritik"
    assert "sessiz_kamera" in kodlar and "bildirim_hatasi" in kodlar
    assert [x["seviye"] for x in s] == sorted((x["seviye"] for x in s), key=lambda v: v != "kritik")
    assert genel_durum(s) == "kritik"


def test_az_gecisli_gunde_mutabakat_uyarisi_yok_ve_kesinti_24_saat():
    simdi = time.time()
    zaman = datetime.now()
    ozet = _ozet(kameralar=[{"ad": "Arka", "aktif": True, "goruntu": "calisiyor",
                             "mutabakat": {"gun": "2026-10-30", "kamera_gecis": 5, "oran": 40.0}}],
                 kesintiler_7g=[{"baslangic": (zaman - timedelta(hours=2)).isoformat(), "bitis": (zaman - timedelta(hours=1)).isoformat(),
                                 "sure_dk": 60, "durum": "tamamlandi"},
                                {"baslangic": (zaman - timedelta(days=3)).isoformat(), "bitis": (zaman - timedelta(days=3)).isoformat(),
                                 "sure_dk": 10, "durum": "tamamlandi"}])
    s = sorunlari_hesapla(ozet, simdi - 60, simdi)
    assert not any(x["kod"].startswith("mutabakat") for x in s)
    kesintiler = [x for x in s if x["kod"].startswith("kesinti:")]
    assert len(kesintiler) == 1 and "1 saat" in kesintiler[0]["mesaj"]


def test_bakim_sozlesmesi_uyarisi():
    simdi = time.time()
    yakin = (datetime.now() + timedelta(days=10)).date().isoformat()
    s = sorunlari_hesapla(_ozet(), simdi - 60, simdi, bakim_bitis=yakin)
    assert [x["kod"] for x in s] == ["bakim_bitiyor"]


# ------------------------------------------------------------------ merkez API
def test_yonetici_girisi_gerekli_ve_hatali_parola_kilitlenir(merkez):
    assert merkez.get("/api/kurulumlar").status_code == 401
    assert merkez.get("/").status_code == 401
    for _ in range(10):
        assert merkez.get("/api/kurulumlar", headers=_basic(parola="yanlis")).status_code == 401
    assert merkez.get("/api/kurulumlar", headers=_basic()).status_code == 429
    uygulama._hatali_giris.clear()
    assert merkez.get("/api/kurulumlar", headers=_basic()).status_code == 200
    assert "PTS Merkezi" in merkez.get("/", headers=_basic()).text


def test_parola_ayarlanmadiysa_pano_kapali(merkez, monkeypatch):
    monkeypatch.delenv("MERKEZ_YONETICI_PAROLA")
    assert merkez.get("/api/kurulumlar", headers=_basic()).status_code == 503


def test_kurulum_ekle_nabiz_ve_listele(merkez):
    r = merkez.post("/api/kurulumlar", json={"ad": "TPAO Batman", "bakim_bitis": "2027-10-31"}, headers=_basic())
    assert r.status_code == 200
    anahtar, kid = r.json()["anahtar"], r.json()["id"]

    assert merkez.post("/api/nabiz", json=_ozet()).status_code == 401
    assert merkez.post("/api/nabiz", json=_ozet(), headers={"X-Kurulum-Anahtari": "yanlis"}).status_code == 401
    ozet = _ozet()
    ozet["kameralar"][0]["plaka"] = "34ABC123"     # olmaması gereken alan: kaydedilmez
    assert merkez.post("/api/nabiz", json=ozet, headers={"X-Kurulum-Anahtari": anahtar}).status_code == 200

    liste = merkez.get("/api/kurulumlar", headers=_basic()).json()
    k = liste["kurulumlar"][0]
    assert k["ad"] == "TPAO Batman" and k["durum"] == "iyi" and k["kamera_calisan"] == 1 and k["bugun_okuma"] == 120
    assert k["erisim_7g"] == 100.0
    assert liste["sayac"]["iyi"] == 1
    ayrinti = merkez.get(f"/api/kurulumlar/{kid}", headers=_basic()).json()
    assert "plaka" not in json.dumps(ayrinti["ozet"])

    # Devre dışı kurulum gönderemez; anahtar yenilenince eskisi geçmez.
    assert merkez.patch(f"/api/kurulumlar/{kid}", json={"etkin": False}, headers=_basic()).status_code == 200
    assert merkez.post("/api/nabiz", json=_ozet(), headers={"X-Kurulum-Anahtari": anahtar}).status_code == 403
    merkez.patch(f"/api/kurulumlar/{kid}", json={"etkin": True}, headers=_basic())
    yeni = merkez.post(f"/api/kurulumlar/{kid}/anahtar-yenile", headers=_basic()).json()["anahtar"]
    assert merkez.post("/api/nabiz", json=_ozet(), headers={"X-Kurulum-Anahtari": anahtar}).status_code == 401
    assert merkez.post("/api/nabiz", json=_ozet(), headers={"X-Kurulum-Anahtari": yeni}).status_code == 200
    assert merkez.patch(f"/api/kurulumlar/{kid}", json={"bakim_bitis": "31.10.2027"}, headers=_basic()).status_code == 400
    assert merkez.delete(f"/api/kurulumlar/{kid}", headers=_basic()).status_code == 200
    assert merkez.get("/api/kurulumlar", headers=_basic()).json()["kurulumlar"] == []


def test_buyuk_ya_da_bozuk_ozet_reddedilir(merkez):
    anahtar = merkez.post("/api/kurulumlar", json={"ad": "X"}, headers=_basic()).json()["anahtar"]
    h = {"X-Kurulum-Anahtari": anahtar, "Content-Type": "application/json"}
    assert merkez.post("/api/nabiz", content=b"[1,2]", headers=h).status_code == 400
    assert merkez.post("/api/nabiz", content=b"{bozuk", headers=h).status_code == 400
    assert merkez.post("/api/nabiz", content=b"{\"a\":\"" + b"x" * 300_000 + b"\"}", headers=h).status_code == 413


def test_bildirim_turu_bekler_bildirir_ve_duzeldi_der(merkez, monkeypatch):
    gonderilen = []
    monkeypatch.setattr(uygulama.bildirim, "gonder", lambda konu, metin: gonderilen.append((konu, metin)) or [])
    anahtar = merkez.post("/api/kurulumlar", json={"ad": "Lojman"}, headers=_basic()).json()["anahtar"]
    bozuk = _ozet(disk={"en_dolu_yuzde": 97, "yollar": [{"ad": "Veritabanı", "yuzde": 97.0}]})
    merkez.post("/api/nabiz", json=bozuk, headers={"X-Kurulum-Anahtari": anahtar})
    simdi = time.time()

    assert uygulama.bildirim_turu(simdi) == []                       # ilk görülüş: beklenir
    assert uygulama.bildirim_turu(simdi + 300) == []
    giden = uygulama.bildirim_turu(simdi + uygulama.BEKLEME_SN + 1)
    assert len(giden) == 1 and "Lojman" in giden[0][0] and "Disk %97" in giden[0][1]
    assert uygulama.bildirim_turu(simdi + uygulama.BEKLEME_SN + 60) == []   # tekrar etmez

    merkez.post("/api/nabiz", json=_ozet(), headers={"X-Kurulum-Anahtari": anahtar})
    giden = uygulama.bildirim_turu(time.time() + 5)
    assert len(giden) == 1 and "Düzeldi" in giden[0][1]
    assert len(gonderilen) == 2

    # Çevrimdışı beklemeden bildirilir (eşik zaten 15 dk).
    giden = uygulama.bildirim_turu(time.time() + 20 * 60)
    assert len(giden) == 1 and "haber yok" in giden[0][1]
    kid = merkez.get("/api/kurulumlar", headers=_basic()).json()["kurulumlar"][0]["id"]
    olaylar = merkez.get(f"/api/kurulumlar/{kid}", headers=_basic()).json()["olaylar"]
    assert [o["tur"] for o in olaylar].count("duzeldi") == 1


# ------------------------------------------------------------------ PTS istemcisi
def test_istemci_kisisel_veri_iceren_ozeti_gondermez():
    assert merkez_istemci.yasakli_alan_var_mi({"kameralar": [{"ad": "x", "plaka_no": "1"}]}) == "kameralar[0].plaka_no"
    with pytest.raises(RuntimeError, match="kişisel veri"):
        merkez_istemci.gonder("https://ornek.invalid", "a", {"kisi_adi": "Ali"})


def test_istemci_url_dogrulama():
    assert merkez_istemci.url_dogrula("https://izleme.firma.com/") == "https://izleme.firma.com"
    assert merkez_istemci.url_dogrula("http://192.168.1.5:8100") == "http://192.168.1.5:8100"
    for kotu in ("izleme.firma.com", "ftp://x", "http://izleme.firma.com"):
        with pytest.raises(ValueError):
            merkez_istemci.url_dogrula(kotu)
    assert merkez_istemci.anahtari_maskele("abcdefghijklmnop") == "abcd…mnop"
