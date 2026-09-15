"""FastAPI uç noktaları için entegrasyon testleri (TestClient + geçici SQLite).

NOT: Bu dosya fastapi + sqlalchemy gerektirir. Bu depo bu testleri yazan
oturumun kum havuzunda (dış paket erişimi organizasyon politikasıyla kapalı
olduğu için) çalıştırılamadı — kullanıcının kendi ortamında ya da CI'da
(bkz. .github/workflows/tests.yml) çalışır. Testler, `tests/conftest.py`
içinde ayarlanan geçici bir SQLite veritabanı ve sabit test secret'larıyla
tamamen izole çalışacak şekilde tasarlandı.
"""
import os
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend import lisans
from backend.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    """İlk yönetici hesabını bir kez oluşturur ve token döner (modül genelinde paylaşılır)."""
    r = client.post("/auth/ilk-yonetici", json={"kullanici_adi": "admin", "parola": "GucluParola123!"})
    assert r.status_code == 200, r.text
    r2 = client.post("/auth/giris", json={"kullanici_adi": "admin", "parola": "GucluParola123!"})
    assert r2.status_code == 200, r2.text
    return r2.json()["token"]


@pytest.fixture
def yetkili_header(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ------------------------------------------------------------------
# Sağlık / temel
# ------------------------------------------------------------------

def test_saglik_kontrolu(client):
    r = client.get("/saglik")
    assert r.status_code == 200


# ------------------------------------------------------------------
# Kimlik doğrulama
# ------------------------------------------------------------------

def test_ilk_yonetici_ve_giris_akisi(client, admin_token):
    assert admin_token  # fixture zaten başarılı giriş yaptı

    # İkinci kez ilk yönetici oluşturmaya çalışmak reddedilmeli
    r = client.post("/auth/ilk-yonetici", json={"kullanici_adi": "baska", "parola": "GucluParola123!"})
    assert r.status_code == 409


def test_yanlis_parola_ile_giris_reddedilir(client):
    r = client.post("/auth/giris", json={"kullanici_adi": "admin", "parola": "yanlis-parola"})
    assert r.status_code == 401


def test_tokensiz_korumali_uc_noktaya_erisim_reddedilir(client):
    r = client.get("/kisiler")
    assert r.status_code == 401


def test_giris_deneme_kilitlemesi(client):
    """Var olmayan bir kullanıcı adıyla 5 başarısız denemeden sonra kilitlenmeli (429)."""
    kullanici_adi = "hic-var-olmayan-kullanici"
    for _ in range(5):
        r = client.post("/auth/giris", json={"kullanici_adi": kullanici_adi, "parola": "yanlis"})
        assert r.status_code == 401
    r = client.post("/auth/giris", json={"kullanici_adi": kullanici_adi, "parola": "yanlis"})
    assert r.status_code == 429


# ------------------------------------------------------------------
# Plaka yetki kontrolü (yetkili / yetkisiz / kara liste / süresi dolmuş / saat kısıtlaması)
# ------------------------------------------------------------------

def test_taninmayan_plaka_yetkisiz_gelir(client, yetkili_header):
    r = client.post("/kayitlar", json={"plaka_no": "06 ZZZ 999", "kamera_id": "TEST", "yon": "giris"},
                     headers=yetkili_header)
    assert r.status_code == 200, r.text
    assert r.json()["yetki_durumu"] == "yetkisiz"


def test_kayitli_abone_yetkili_gelir(client, yetkili_header):
    r = client.post("/kisiler", json={
        "ad_soyad": "Test Abone",
        "plaka_no": "34 TEST 01",
        "tip": "abone",
    }, headers=yetkili_header)
    assert r.status_code == 200, r.text

    r2 = client.post("/kayitlar", json={"plaka_no": "34 TEST 01", "kamera_id": "TEST", "yon": "giris"},
                      headers=yetkili_header)
    assert r2.status_code == 200, r2.text
    assert r2.json()["yetki_durumu"] == "yetkili"


def test_kara_listedeki_plaka_engellenir(client, yetkili_header):
    r = client.post("/kara-listesi", json={"plaka_no": "34 KARA 02", "sebep": "test"}, headers=yetkili_header)
    assert r.status_code == 200, r.text

    r2 = client.post("/kayitlar", json={"plaka_no": "34 KARA 02", "kamera_id": "TEST", "yon": "giris"},
                      headers=yetkili_header)
    assert r2.status_code == 200, r2.text
    assert r2.json()["yetki_durumu"] == "kara_liste"


def test_suresi_dolmus_ziyaretci_dogru_isaretlenir(client, yetkili_header):
    gecmis_tarih = (datetime.now() - timedelta(days=1)).isoformat()
    r = client.post("/kisiler", json={
        "ad_soyad": "Eski Ziyaretci",
        "plaka_no": "34 ESKI 03",
        "tip": "ziyaretci",
        "bitis_tarihi": gecmis_tarih,
    }, headers=yetkili_header)
    assert r.status_code == 200, r.text

    r2 = client.post("/kayitlar", json={"plaka_no": "34 ESKI 03", "kamera_id": "TEST", "yon": "giris"},
                      headers=yetkili_header)
    assert r2.status_code == 200, r2.text
    assert r2.json()["yetki_durumu"] == "suresi_dolmus"


def test_saat_disi_erisim_yetkisiz_sayilir(client, yetkili_header):
    """Bu regresyon testi özellikle önemli: schemas.py'deki tekrar tanımlanmış
    (duplicate) sınıflar yüzünden bu alanlar API'den API'ye hiç ulaşmıyordu.
    Burada saat penceresinin GERÇEKTEN uygulandığını uçtan uca doğruluyoruz."""
    simdi = datetime.now()
    # Şu andan 2 saat önce başlayıp 1 saat önce biten bir pencere: garanti olarak "şu an" dışında.
    baslangic = (simdi - timedelta(hours=2)).strftime("%H:%M")
    bitis = (simdi - timedelta(hours=1)).strftime("%H:%M")

    r = client.post("/kisiler", json={
        "ad_soyad": "Saat Kisitli Personel",
        "plaka_no": "34 SAAT 04",
        "tip": "personel",
        "giris_saati_baslangic": baslangic,
        "giris_saati_bitis": bitis,
    }, headers=yetkili_header)
    assert r.status_code == 200, r.text
    olusturulan = r.json()
    # Alan gerçekten kaydedilmiş mi? (Sadece istek kabul edildi diye yetmez, geri de dönmeli.)
    assert olusturulan["giris_saati_baslangic"] == baslangic
    assert olusturulan["giris_saati_bitis"] == bitis

    r2 = client.post("/kayitlar", json={"plaka_no": "34 SAAT 04", "kamera_id": "TEST", "yon": "giris"},
                      headers=yetkili_header)
    assert r2.status_code == 200, r2.text
    assert r2.json()["yetki_durumu"] == "yetkisiz", (
        "Saat penceresi dışında olmasına rağmen 'yetkili' döndü — "
        "muhtemelen schemas.py'deki alanlar API'ye ulaşmıyor"
    )


# ------------------------------------------------------------------
# Kamera: giriş doğrulama + lisans/limit kontrolü
# ------------------------------------------------------------------

def test_kamera_gecersiz_adres_semasi_reddedilir(client, yetkili_header):
    r = client.post("/kameralar", json={"ad": "Test Kamera", "rtsp_url": "file:///etc/passwd", "yon": "giris"},
                     headers=yetkili_header)
    assert r.status_code == 400


def test_kamera_gecersiz_yon_reddedilir(client, yetkili_header):
    r = client.post("/kameralar", json={"ad": "Test Kamera", "rtsp_url": "rtsp://127.0.0.1/test", "yon": "yukari"},
                     headers=yetkili_header)
    assert r.status_code == 400


def test_lisanssiz_kamera_eklenemez(client, yetkili_header):
    r = client.get("/lisans", headers=yetkili_header)
    assert r.status_code == 200
    if r.json().get("aktif"):
        pytest.skip("Bu test sırasında lisans zaten aktifleştirilmiş (test sırası bağımlılığı)")
    r2 = client.post("/kameralar", json={"ad": "Kamera 1", "rtsp_url": "rtsp://127.0.0.1/test", "yon": "giris"},
                      headers=yetkili_header)
    assert r2.status_code == 403


def test_lisans_aktivasyonu_ve_kamera_limiti(client, yetkili_header):
    # kamera_limiti=1 olan, cihaza kilitli olmayan bir lisans üret ve aktive et.
    anahtar = lisans.uret("Test Site", kamera_limiti=1, gun=30)
    r = client.post("/lisans/aktive-et", json={"anahtar": anahtar}, headers=yetkili_header)
    assert r.status_code == 200, r.text
    assert r.json()["aktif"] is True
    assert r.json()["kamera_limiti"] == 1

    r2 = client.post("/kameralar", json={"ad": "Kamera 1", "rtsp_url": "rtsp://127.0.0.1/kanal1", "yon": "giris"},
                      headers=yetkili_header)
    assert r2.status_code == 200, r2.text

    # Limit 1: ikinci kamera reddedilmeli
    r3 = client.post("/kameralar", json={"ad": "Kamera 2", "rtsp_url": "rtsp://127.0.0.1/kanal2", "yon": "cikis"},
                      headers=yetkili_header)
    assert r3.status_code == 403


def test_gecersiz_imzali_lisans_reddedilir(client, yetkili_header):
    sahte = "PTS1.eW9rLWJvenVsbXVzLXZlcmk.eW9rLWltemE"
    r = client.post("/lisans/aktive-et", json={"anahtar": sahte}, headers=yetkili_header)
    assert r.status_code == 400


# ------------------------------------------------------------------
# Görüntü saklama / otomatik temizlik
# ------------------------------------------------------------------
# NOT: Bu testler `_goruntu_temizle_calistir` fonksiyonunu (hem manuel
# /sistem/goruntu-temizle uç noktası hem de arka planda periyodik çalışan
# otomatik saklama görevi tarafından paylaşılan mantık) uçtan uca doğrular.
# Amaç: disk sürekli dolup sistemi "donmuş" gibi göstermesin diye eklenen bu
# otomasyonun, YANLIŞLIKLA yeni/güncel kayıtların görüntülerini silmediğini
# ve gerçekten SADECE eski kayıtları temizlediğini garanti altına almak.

def _test_goruntu_dosyasi_olustur(client, dosya_adi: str) -> str:
    from backend.main import GORUNTU_KLASORU
    os.makedirs(GORUNTU_KLASORU, exist_ok=True)
    tam_yol = os.path.join(GORUNTU_KLASORU, dosya_adi)
    with open(tam_yol, "wb") as f:
        f.write(b"sahte-goruntu-verisi")
    return tam_yol


def test_eski_goruntulu_kayit_temizlenir_yeni_olan_korunur(client, yetkili_header):
    from backend.database import SessionLocal
    from backend import models

    eski_dosya_adi = "test-eski-goruntu.jpg"
    yeni_dosya_adi = "test-yeni-goruntu.jpg"
    eski_tam_yol = _test_goruntu_dosyasi_olustur(client, eski_dosya_adi)
    yeni_tam_yol = _test_goruntu_dosyasi_olustur(client, yeni_dosya_adi)

    db = SessionLocal()
    try:
        eski_kayit = models.Kayit(
            plaka_no="34 ESK 99", kamera_id="TEST",
            tarih_saat=datetime.now() - timedelta(days=45),
            goruntu_yolu=eski_tam_yol,
        )
        yeni_kayit = models.Kayit(
            plaka_no="34 YEN 99", kamera_id="TEST",
            tarih_saat=datetime.now() - timedelta(hours=1),
            goruntu_yolu=yeni_tam_yol,
        )
        db.add_all([eski_kayit, yeni_kayit])
        db.commit()
    finally:
        db.close()

    try:
        r = client.post("/sistem/goruntu-temizle", params={"gun": 30}, headers=yetkili_header)
        assert r.status_code == 200, r.text
        assert r.json()["silinen_goruntu"] >= 1

        assert not os.path.exists(eski_tam_yol), "30 günden eski görüntü silinmeliydi"
        assert os.path.exists(yeni_tam_yol), (
            "1 saat önceki kayıt YANLIŞLIKLA silindi — tarih filtresinde bir "
            "regresyon olabilir (otomatik saklama görevi de aynı fonksiyonu kullanıyor)"
        )
    finally:
        for yol in (eski_tam_yol, yeni_tam_yol):
            if os.path.exists(yol):
                os.remove(yol)


# ------------------------------------------------------------------
# Bilinen plakaya göre OCR düzeltmesi (veritabanı çapraz kontrolü)
# ------------------------------------------------------------------
# Bu, doğruluğu artırmak için eklenen bir tekniktir: OCR tek bir karakteri
# yanlış okusa bile (düşük güvenle), sahada kayıtlı bilinen bir plakayla tek
# karakter farkı varsa ve başka hiçbir aday bu kadar yakın değilse, o bilinen
# plakaya düzeltilir. GÜVENLİK AÇISINDAN KRİTİK: bu SADECE erişim vermek için
# çalışmalı, kara listeye asla uygulanmamalı (aksi halde alakasız bir araç
# yanlışlıkla engellenebilir).

def test_dusuk_guvenli_tek_karakter_hatasi_bilinen_plakaya_duzeltilir(client, yetkili_header):
    r = client.post("/kisiler", json={
        "ad_soyad": "Duzeltme Testi", "plaka_no": "34 DZT 123", "tip": "abone",
    }, headers=yetkili_header)
    assert r.status_code == 200, r.text

    # OCR "3" yerine "8" okumuş (tek karakter hatası), düşük güvenle.
    r2 = client.post("/kayitlar", json={
        "plaka_no": "34 DZT 128", "kamera_id": "TEST", "yon": "giris", "guven_skoru": 0.55,
    }, headers=yetkili_header)
    assert r2.status_code == 200, r2.text
    sonuc = r2.json()
    assert sonuc["plaka_no"] == "34 DZT 123", "Bilinen plakaya düzeltilmedi"
    assert sonuc["ham_plaka_metni"] == "34 DZT 128", "Ham OCR okuması denetim için saklanmalıydı"
    assert sonuc["yetki_durumu"] == "yetkili", (
        "Düzeltme uygulandığı halde 'yetkisiz' döndü — düzeltme yetki kontrolünden ÖNCE uygulanmalı"
    )


def test_yuksek_guvenli_okuma_duzeltilmez(client, yetkili_header):
    """Zaten yüksek güvenli (>= eşik) bir okuma, bilinen bir plakaya yakın olsa
    bile OLDUĞU GİBİ bırakılmalı — aksi halde doğru bir okuma yanlışlıkla
    'düzeltilerek' bozulabilir."""
    r = client.post("/kisiler", json={
        "ad_soyad": "Yuksek Guven Testi", "plaka_no": "34 YKG 123", "tip": "abone",
    }, headers=yetkili_header)
    assert r.status_code == 200, r.text

    r2 = client.post("/kayitlar", json={
        "plaka_no": "34 YKG 128", "kamera_id": "TEST", "yon": "giris", "guven_skoru": 0.97,
    }, headers=yetkili_header)
    assert r2.status_code == 200, r2.text
    sonuc = r2.json()
    assert sonuc["plaka_no"] == "34 YKG 128", "Yüksek güvenli okuma yanlışlıkla değiştirildi"
    assert sonuc["ham_plaka_metni"] is None
    assert sonuc["yetki_durumu"] == "yetkisiz"


def test_kara_listeye_yakinlik_duzeltmesi_uygulanmaz(client, yetkili_header):
    """Güvenlik regresyon testi: kara listedeki bir plakaya YAKIN ama farklı
    (ve bilinmeyen) bir plaka, düzeltme mekanizması yüzünden YANLIŞLIKLA
    engellenmemeli. Düzeltme sadece bilinen (abone/personel) plakalara karşı
    çalışır, kara listeye karşı hiç çalışmaz."""
    r = client.post("/kara-listesi", json={"plaka_no": "34 KRY 123", "sebep": "test"}, headers=yetkili_header)
    assert r.status_code == 200, r.text

    r2 = client.post("/kayitlar", json={
        "plaka_no": "34 KRY 128", "kamera_id": "TEST", "yon": "giris", "guven_skoru": 0.55,
    }, headers=yetkili_header)
    assert r2.status_code == 200, r2.text
    sonuc = r2.json()
    assert sonuc["yetki_durumu"] != "kara_liste", (
        "Kara listedeki bir plakaya yakın farklı bir araç yanlışlıkla kara listeye düzeltildi/engellendi"
    )
