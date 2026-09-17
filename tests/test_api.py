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
from backend import main as pts_main
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


def _rol_ile_kullanici_olustur_ve_giris_yap(client, yetkili_header, kullanici_adi: str, rol: str) -> dict:
    """Verilen role sahip yeni bir kullanıcı oluşturur (yönetici gerektirir),
    onunla giriş yapar ve Authorization header'ını döner. RBAC testlerinde
    kullanılır."""
    r = client.post("/kullanicilar", json={
        "kullanici_adi": kullanici_adi, "parola": "GucluParola123!", "rol": rol,
    }, headers=yetkili_header)
    assert r.status_code == 200, r.text
    r2 = client.post("/auth/giris", json={"kullanici_adi": kullanici_adi, "parola": "GucluParola123!"})
    assert r2.status_code == 200, r2.text
    return {"Authorization": f"Bearer {r2.json()['token']}"}


@pytest.fixture(scope="module")
def izleyici_header(client, admin_token):
    # NOT: module-scope bir fixture, fonksiyon-scope'lu `yetkili_header`'a değil
    # doğrudan module-scope `admin_token`'a bağımlı olmalı (aksi halde pytest
    # "ScopeMismatch" hatası verir — daha dar scope'lu bir fixture'a bağımlı
    # olamaz).
    return _rol_ile_kullanici_olustur_ve_giris_yap(
        client, {"Authorization": f"Bearer {admin_token}"}, "rbac-izleyici", "izleyici"
    )


@pytest.fixture(scope="module")
def operator_header(client, admin_token):
    return _rol_ile_kullanici_olustur_ve_giris_yap(
        client, {"Authorization": f"Bearer {admin_token}"}, "rbac-operator", "operatör"
    )


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


# ------------------------------------------------------------------
# Rol bazlı yetkilendirme (RBAC)
# ------------------------------------------------------------------
# Daha önce sadece kullanıcı yönetimi / sistem ayarları / DB yedeği / görüntü
# temizleme rol kontrolü yapıyordu; kamera/kişi/kara liste/bariyer açma/webhook
# gibi geri kalan HER YAZMA işlemi sadece giriş yapmış olmayı yeterli
# sayıyordu — yani "izleyici" (salt okunur) rolündeki bir kullanıcı bile
# bariyer açabiliyor, kamera silebiliyor, lisans aktive edebiliyordu. Bu
# testler _rol_dogrula() ile eklenen kısıtlamaları uçtan uca doğrular.

def test_izleyici_hicbir_yazma_islemi_yapamaz(client, izleyici_header):
    """İzleyici (salt okunur) rolü GERÇEKTEN salt okunur olmalı."""
    denemeler = [
        ("post", "/kisiler", {"ad_soyad": "X", "plaka_no": "34 RBC 001", "tip": "abone"}),
        ("post", "/kameralar", {"ad": "X", "rtsp_url": "rtsp://127.0.0.1/x", "yon": "giris"}),
        ("post", "/kara-listesi", {"plaka_no": "34 RBC 002", "sebep": "test"}),
        ("post", "/bariyer/ayarlar", {"ad": "X", "mod": "simulate"}),
        ("post", "/lisans/aktive-et", {"anahtar": "PTS1.x.y"}),
        ("post", "/bildirim/ayarlar", {"ad": "X", "hedef": "https://example.com"}),
        ("put", "/sistem/ayarlar", {"supheli_esik": 5}),
        ("post", "/kullanicilar", {"kullanici_adi": "baska", "parola": "GucluParola123!", "rol": "izleyici"}),
        ("post", "/siteler", {"ad": "X"}),
    ]
    for metot, yol, govde in denemeler:
        r = getattr(client, metot)(yol, json=govde, headers=izleyici_header)
        assert r.status_code == 403, f"{metot.upper()} {yol}: izleyici 403 almalıydı, {r.status_code} aldı ({r.text})"


def test_izleyici_okuma_uc_noktalarina_erisebilir(client, izleyici_header):
    """Kısıtlama SADECE yazma işlemlerinde olmalı; izleyici okuyabilmeli."""
    for yol in ("/kisiler", "/kameralar", "/kara-listesi", "/kayitlar", "/bariyer/ayarlar"):
        r = client.get(yol, headers=izleyici_header)
        assert r.status_code == 200, f"GET {yol}: izleyici erişemedi ({r.status_code})"


def test_sistem_loglarina_izleyici_erisemez_operator_erisebilir(client, izleyici_header, operator_header):
    """Güvenlik regresyonu: /sistem/loglar kamera bağlantı adresleri (RTSP
    kimlik bilgileri dahil, maskelenmiş olsa da) ve dahili hata detayları
    içerir — salt-okunur 'izleyici' rolüne açık kalmamalı. En az operatör
    olmalı."""
    r = client.get("/sistem/loglar", headers=izleyici_header)
    assert r.status_code == 403, f"izleyici loglara erişebildi ({r.status_code})"
    r2 = client.get("/sistem/loglar", headers=operator_header)
    assert r2.status_code == 200, f"operatör loglara erişemedi ({r2.text})"


# ------------------------------------------------------------------
# /goruntuler — araç/sürücü görselleri (KVKK kapsamında kişisel veri)
# ------------------------------------------------------------------
# Güvenlik regresyonu: bu yol önceden kimliksiz bir StaticFiles mount'uydu.
# Artık giriş yapmamış hiç kimse (rol farketmeksizin) bu görsellere
# erişememeli, ve dosya adı yalnızca DÜZ bir ad olmalı (yol geçişi/"../"
# denemeleri reddedilmeli).

def test_goruntu_girissiz_erisilemez(client):
    r = client.get("/goruntuler/herhangi_bir_dosya.jpg")
    assert r.status_code in (401, 403), f"Girişsiz istek engellenmedi ({r.status_code})"


def test_goruntu_yol_gecisi_denemesi_reddedilir(client, izleyici_header):
    """NOT: Starlette'in varsayılan `{dosya_adi}` yol dönüştürücüsü zaten TEK
    bir segment içinde eşleşir (ham bir '/' içeren istekler bu uç noktaya HİÇ
    ulaşmaz, 404 döner) — bu yüzden burada özellikle TEK segment içinde
    kalan ama yine de ".." içeren bir değeri test ediyoruz: gorsel_getir'in
    kendi ".." kontrolünün (yalnızca yönlendirme katmanına güvenmeden)
    gerçekten çalıştığını doğrudan doğrular."""
    r = client.get("/goruntuler/..gizli_dosya.jpg", headers=izleyici_header)
    assert r.status_code == 400, f"'..' içeren dosya adı reddedilmedi ({r.status_code})"


def test_goruntu_girisli_kullanici_gercek_dosyayi_alabilir(client, izleyici_header, tmp_path_factory):
    from backend.main import GORUNTU_KLASORU

    dosya_adi = "pytest_gecici_test_gorseli.jpg"
    tam_yol = os.path.join(GORUNTU_KLASORU, dosya_adi)
    with open(tam_yol, "wb") as f:
        f.write(b"\xff\xd8\xff\xe0sahte-jpeg-icerigi")
    try:
        r = client.get(f"/goruntuler/{dosya_adi}", headers=izleyici_header)
        assert r.status_code == 200, r.text
        assert r.content.startswith(b"\xff\xd8\xff")
    finally:
        os.remove(tam_yol)


def test_operator_gunluk_islemleri_yapabilir_ama_yonetim_islemlerini_yapamaz(client, operator_header):
    """Operatör günlük operasyonu (kişi/kamera/kara liste/bariyer açma) yapabilmeli,
    ama yönetici'ye özel işlemleri (kullanıcı yönetimi, sistem ayarları, webhook
    yapılandırması, lisans) YAPAMAMALI."""
    r = client.post("/kisiler", json={
        "ad_soyad": "Operator Testi", "plaka_no": "34 RBC 003", "tip": "abone",
    }, headers=operator_header)
    assert r.status_code == 200, f"Operatör kişi ekleyemedi: {r.text}"

    r2 = client.post("/kara-listesi", json={"plaka_no": "34 RBC 004", "sebep": "test"}, headers=operator_header)
    assert r2.status_code == 200, f"Operatör kara listeye ekleyemedi: {r2.text}"

    yonetim_denemeleri = [
        ("post", "/kullanicilar", {"kullanici_adi": "baska2", "parola": "GucluParola123!", "rol": "izleyici"}),
        ("put", "/sistem/ayarlar", {"supheli_esik": 5}),
        ("post", "/bildirim/ayarlar", {"ad": "X", "hedef": "https://example.com"}),
        ("post", "/lisans/aktive-et", {"anahtar": "PTS1.x.y"}),
        # Site/Nokta yönetimi de sadece yönetici'ye açık — operatör günlük
        # operasyon yapar ama yerleşke topolojisini değiştiremez.
        ("post", "/siteler", {"ad": "Operatör Sitesi"}),
        ("post", "/noktalar", {"site_id": 1, "ad": "X"}),
    ]
    for metot, yol, govde in yonetim_denemeleri:
        r3 = getattr(client, metot)(yol, json=govde, headers=operator_header)
        assert r3.status_code == 403, f"{metot.upper()} {yol}: operatör 403 almalıydı, {r3.status_code} aldı"


# ------------------------------------------------------------------
# Site / Erişim Noktası (kamera ↔ bariyer bağlantısı)
# ------------------------------------------------------------------
# Nokta, kameralar (cameras.json'da tutulan) ile bariyerler (SQL tablosu)
# arasındaki TEK bağlantıdır — bu yüzden her iki foreign key de (var
# olduklarında) gerçekten var olan kayıtları göstermeli, aksi halde panel
# sessizce geçersiz bir bağlantı gösterir (bkz. main.py::nokta_ekle).

def test_site_olusturulur_ve_listelenir(client, yetkili_header):
    r = client.post("/siteler", json={"ad": "Test Yerleşkesi", "aciklama": "RBAC testi için"}, headers=yetkili_header)
    assert r.status_code == 200, r.text
    site_id = r.json()["id"]

    r2 = client.get("/siteler", headers=yetkili_header)
    assert r2.status_code == 200
    assert any(s["id"] == site_id for s in r2.json())


def test_nokta_olmayan_bariyer_id_ile_reddedilir(client, yetkili_header):
    site = client.post("/siteler", json={"ad": "Nokta Test Sitesi 1"}, headers=yetkili_header).json()
    r = client.post("/noktalar", json={
        "site_id": site["id"], "ad": "Nizamiye", "bariyer_id": 999999,
    }, headers=yetkili_header)
    assert r.status_code == 404


def test_nokta_olmayan_kamera_id_ile_reddedilir(client, yetkili_header):
    site = client.post("/siteler", json={"ad": "Nokta Test Sitesi 2"}, headers=yetkili_header).json()
    r = client.post("/noktalar", json={
        "site_id": site["id"], "ad": "Nizamiye", "kamera_id": "olmayan-kamera-uuid",
    }, headers=yetkili_header)
    assert r.status_code == 404


def test_nokta_gecerli_bariyerle_olusturulur_ve_bariyer_acmaya_baglanir(client, yetkili_header):
    site = client.post("/siteler", json={"ad": "Nokta Test Sitesi 3"}, headers=yetkili_header).json()
    bariyer = client.post("/bariyer/ayarlar", json={"ad": "Nizamiye Bariyeri", "mod": "simulate"}, headers=yetkili_header).json()

    r = client.post("/noktalar", json={
        "site_id": site["id"], "ad": "Nizamiye Giriş", "yon": "giris", "bariyer_id": bariyer["id"],
    }, headers=yetkili_header)
    assert r.status_code == 200, r.text
    nokta = r.json()
    assert nokta["bariyer_id"] == bariyer["id"]

    # Panelin "Bariyer Aç" akışının dayandığı gerçek zincir: nokta -> bariyer_id -> /bariyer/{id}/ac
    r2 = client.post(f"/bariyer/{nokta['bariyer_id']}/ac", headers=yetkili_header)
    assert r2.status_code == 200, r2.text


def test_site_silinince_bagli_nokta_da_silinir(client, yetkili_header):
    site = client.post("/siteler", json={"ad": "Silinecek Site"}, headers=yetkili_header).json()
    nokta = client.post("/noktalar", json={"site_id": site["id"], "ad": "Silinecek Nokta"}, headers=yetkili_header).json()

    r = client.delete(f"/siteler/{site['id']}", headers=yetkili_header)
    assert r.status_code == 200, r.text

    kalanlar = client.get("/noktalar", headers=yetkili_header).json()
    assert not any(n["id"] == nokta["id"] for n in kalanlar), "Site silindiğinde bağlı nokta da silinmeliydi (cascade)"


# ------------------------------------------------------------------
# /sistem/saglik — SQL Server yedeğinin GERÇEKTEN alınıp alınmadığının izlenmesi
# ------------------------------------------------------------------
# Önceden sistem, SQL Server Agent bakım planının çalışıp çalışmadığını hiçbir
# şekilde izlemiyordu — plan hiç kurulmasa bile sessizce fark edilmezdi.

def test_yedek_izleme_ayarlanmamissa_hicbir_davranis_degismez(client, izleyici_header, monkeypatch):
    monkeypatch.delenv("PTS_SQL_YEDEK_KLASORU", raising=False)
    r = client.get("/sistem/saglik", headers=izleyici_header)
    assert r.status_code == 200, r.text
    assert r.json()["yedek"] == {"izleniyor": False, "son_yedek_zamani": None, "yedek_gecikmis": None}


def test_yedek_izleme_ayarliysa_en_yeni_dosyanin_yasini_raporlar(client, izleyici_header, monkeypatch, tmp_path):
    eski = tmp_path / "eski_yedek.bak"
    eski.write_bytes(b"eski")
    yeni = tmp_path / "yeni_yedek.bak"
    yeni.write_bytes(b"yeni")
    gecmis_zaman = (datetime.now() - timedelta(days=10)).timestamp()
    os.utime(eski, (gecmis_zaman, gecmis_zaman))
    # yeni dosya için mtime'ı elle ayarlamıyoruz — az önce yazıldığı için zaten güncel.

    monkeypatch.setenv("PTS_SQL_YEDEK_KLASORU", str(tmp_path))
    r = client.get("/sistem/saglik", headers=izleyici_header)
    assert r.status_code == 200, r.text
    yedek = r.json()["yedek"]
    assert yedek["izleniyor"] is True
    assert yedek["yedek_gecikmis"] is False  # en yeni dosya (yeni_yedek.bak) az önce yazıldı
    assert yedek["son_yedek_zamani"] is not None


def test_yedek_izleme_klasor_bossa_gecikmis_sayilir(client, izleyici_header, monkeypatch, tmp_path):
    monkeypatch.setenv("PTS_SQL_YEDEK_KLASORU", str(tmp_path))  # var ama boş bir klasör
    r = client.get("/sistem/saglik", headers=izleyici_header)
    yedek = r.json()["yedek"]
    assert yedek["izleniyor"] is True
    assert yedek["yedek_gecikmis"] is True
    assert yedek["son_yedek_zamani"] is None


def test_gecersiz_istek_govdesi_tutarli_422_doner(client, yetkili_header):
    """RequestValidationError (422) için küresel hata yakalayıcı, diğer tüm
    hatalarla aynı `{"detail": ...}` gövde biçimini kullanmalı ve ek olarak
    ham pydantic hata listesini de (`hatalar`) içermeli."""
    r = client.post(
        "/kara-listesi",
        json={"plaka_no": "';--", "sebep": "test"},  # yalnızca geçersiz karakter -> plaka_normalize ValueError fırlatır
        headers=yetkili_header,
    )
    assert r.status_code == 422, r.text
    govde = r.json()
    assert "detail" in govde
    assert "hatalar" in govde
    assert isinstance(govde["hatalar"], list)


def test_beklenmeyen_hata_loglanir_ve_tutarli_500_doner(client, caplog):
    """Bilerek fırlatılmamış (HTTPException olmayan) bir hata; istemciye
    traceback sızdırmadan tutarlı bir JSON gövdesiyle dönmeli VE sunucu
    tarafında tam iz düşümüyle loglanmalı (bkz. main.py::_beklenmeyen_hata_yakalayici) —
    aksi halde bu sınıftaki hatalar `/sistem/loglar` üzerinden hiç görülemez."""

    def _patlayan_fonksiyon():
        raise RuntimeError("kaçınılmaz test hatası")

    with caplog.at_level("ERROR", logger="pts"):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(pts_main, "_son_yedek_bilgisini_al", _patlayan_fonksiyon)
            r = client.get("/sistem/saglik")

    assert r.status_code == 500, r.text
    govde = r.json()
    assert govde == {
        "detail": "Sunucuda beklenmeyen bir hata oluştu. Lütfen tekrar deneyin veya sistem yöneticisine bildirin."
    }
    assert "kaçınılmaz test hatası" not in r.text  # istemciye traceback sızmamalı
    assert "Beklenmeyen hata" in caplog.text  # ama sunucu logunda İZİ olmalı
    assert "kaçınılmaz test hatası" in caplog.text  # traceback sunucu logunda GÖRÜNÜR olmalı


def test_gorsel_izleme_ayarlanmamissa_pasif_raporlanir(client, izleyici_header):
    """PTS_GORSEL_IZLEME_DIZINI test ortamında ayarlı değil, dolayısıyla
    _klasor_izleyici hiç başlatılmamış olmalı (bkz. main.py::
    _klasor_izlemeyi_baslat_gerekirse) — varsayılan/eski davranış korunur."""
    r = client.get("/sistem/saglik", headers=izleyici_header)
    assert r.status_code == 200, r.text
    assert r.json()["gorsel_izleme"] == {"aktif": False, "klasor": None}


def test_gorsel_izleme_aktifken_klasoruyle_birlikte_raporlanir(client, izleyici_header, monkeypatch):
    """Klasör izleyici çalışıyorken /sistem/saglik bunu ve hangi klasörü
    izlediğini bildirmeli (panelin Sistem sekmesindeki satır buna dayanır)."""

    class _SahteKlasorIzleyici:
        calisiyor = True
        kok_klasor = "/tmp/ornek-izleme-klasoru"

    monkeypatch.setattr(pts_main, "_klasor_izleyici", _SahteKlasorIzleyici())
    r = client.get("/sistem/saglik", headers=izleyici_header)
    assert r.status_code == 200, r.text
    assert r.json()["gorsel_izleme"] == {"aktif": True, "klasor": "/tmp/ornek-izleme-klasoru"}


def test_anpr_dedektor_esigi_kutuphane_yoksa_none_doner(client, izleyici_header, monkeypatch):
    """Kamera kütüphaneleri (cv2/fast-alpr bağımlılıkları) kurulu değilse
    dedektör eşiği bilgisi hiç sorulmaz, sade None raporlanır."""
    monkeypatch.setattr(pts_main, "_CAM_LIBS", False)
    r = client.get("/sistem/saglik", headers=izleyici_header)
    assert r.status_code == 200, r.text
    assert r.json()["anpr_dedektor_esigi"] is None


def test_anpr_dedektor_esigi_motor_olusunca_fiili_deger_raporlanir(client, izleyici_header, monkeypatch):
    """PTS_ANPR_DETECTOR_ESIGI ortam değişkeninin panelden ayarlanan
    'Min. plaka tanıma güveni' ile karıştırılması geçmişte kullanıcı
    karışıklığına yol açmıştı: bu test, motor bir kez oluşturulduktan sonra
    /sistem/saglik'in FİİLEN uygulanan eşiği ve kaynağını (ortam değişkeni mi,
    kütüphane varsayılanı mı) doğru yansıttığını doğrular (bkz.
    camera_reader.py::dedektor_esigi_bilgisi, anpr_engine.py)."""
    from backend import camera_reader as cr

    monkeypatch.setattr(pts_main, "_CAM_LIBS", True)
    monkeypatch.setattr(
        cr, "dedektor_esigi_bilgisi",
        lambda: {
            "esik": 0.25, "kaynak": "PTS_ANPR_DETECTOR_ESIGI ortam değişkeni ('0.25')",
            "model": "yolo-v9-s-608-license-plate-end2end",
            "model_kaynagi": "PTS_ANPR_DETECTOR_MODEL ortam değişkeni",
        },
    )
    r = client.get("/sistem/saglik", headers=izleyici_header)
    assert r.status_code == 200, r.text
    assert r.json()["anpr_dedektor_esigi"] == {
        "esik": 0.25, "kaynak": "PTS_ANPR_DETECTOR_ESIGI ortam değişkeni ('0.25')",
        "model": "yolo-v9-s-608-license-plate-end2end",
        "model_kaynagi": "PTS_ANPR_DETECTOR_MODEL ortam değişkeni",
    }


def test_dogruluk_testi_izleyici_erisemez(client, izleyici_header):
    """Sunucudaki dosya sistemini okuyan bir işlem olduğu için izleyici
    rolüne açık değil -- bkz. main.py::dogruluk_testi_calistir."""
    r = client.post("/sistem/dogruluk-testi", json={"klasor": "/tmp/herhangi"}, headers=izleyici_header)
    assert r.status_code == 403


def test_dogruluk_testi_kutuphane_yoksa_400_doner(client, operator_header, monkeypatch):
    monkeypatch.setattr(pts_main, "_CAM_LIBS", False)
    r = client.post("/sistem/dogruluk-testi", json={"klasor": "/tmp/herhangi"}, headers=operator_header)
    assert r.status_code == 400


def test_dogruluk_testi_operator_calistirabilir_ve_sonucu_doner(client, operator_header, monkeypatch):
    """toplu_dogruluk_testi() gerçekten çağrılıyor mu, verilen parametreler
    (klasor/min_guven_skoru/kontrast_iyilestir) doğru iletiliyor mu ve
    dönen sonuç istemciye olduğu gibi ulaşıyor mu -- bunu doğrular."""
    monkeypatch.setattr(pts_main, "_CAM_LIBS", True)

    cagrilar = []

    def _sahte_test(klasor, min_guven_skoru, kontrast_iyilestir):
        cagrilar.append((klasor, min_guven_skoru, kontrast_iyilestir))
        return {
            "toplam": 2, "dogru": 1, "yanlis": 0, "esik_altinda": 0,
            "tespit_edilemedi": 1, "etiketlenemedi": 0, "dogruluk_orani": 0.5,
            "detaylar": [],
        }

    from backend import camera_reader as cr
    monkeypatch.setattr(cr, "toplu_dogruluk_testi", _sahte_test)

    r = client.post(
        "/sistem/dogruluk-testi",
        json={"klasor": "/tmp/etiketli-fotograflar", "min_guven_skoru": 0.25, "kontrast_iyilestir": True},
        headers=operator_header,
    )
    assert r.status_code == 200, r.text
    assert r.json()["dogruluk_orani"] == 0.5
    assert cagrilar == [("/tmp/etiketli-fotograflar", 0.25, True)]


def test_dogruluk_testi_klasor_bulunamazsa_400_doner(client, operator_header, monkeypatch):
    monkeypatch.setattr(pts_main, "_CAM_LIBS", True)

    def _hata_firlat(klasor, min_guven_skoru, kontrast_iyilestir):
        raise ValueError(f"Klasör bulunamadı: {klasor}")

    from backend import camera_reader as cr
    monkeypatch.setattr(cr, "toplu_dogruluk_testi", _hata_firlat)

    r = client.post("/sistem/dogruluk-testi", json={"klasor": "/olmayan"}, headers=operator_header)
    assert r.status_code == 400


# ------------------------------------------------------------------
# Geçiş kaydı tam düzenleme + manuel kayıt notu (bkz. main.py::kayit_duzenle,
# kayit_ekle_manuel; "Plaka Analizi" ekranındaki manuel kayıt/düzenleme
# özellikleri bu uç noktaları kullanır)
# ------------------------------------------------------------------

def test_kayit_manuel_not_metni_ve_manuel_giris_bayragi_kaydedilir(client, operator_header):
    """'Plaka Analizi' ekranındaki 'Manuel Kayıt Ekle' formu bu uca not_metni
    ile POST atıyor -- kayıt hem manuel_giris=True hem de girilen notla
    dönmeli (görsel/güven skoru olmadan)."""
    r = client.post("/kayitlar", json={
        "plaka_no": "34 MNL 01", "kamera_id": "PANEL-MANUEL", "yon": "giris",
        "not_metni": "teslimat aracı, güvenlik onayıyla alındı",
    }, headers=operator_header)
    assert r.status_code == 200, r.text
    veri = r.json()
    assert veri["manuel_giris"] is True
    assert veri["not_metni"] == "teslimat aracı, güvenlik onayıyla alındı"
    assert veri["duzenleyen"] is None  # manuel eklemek "düzenleme" sayılmaz


def test_kayit_duzenle_plaka_durum_ve_not_guncellenir_ve_denetim_izi_tutulur(client, operator_header):
    r = client.post("/kayitlar", json={"plaka_no": "34 DZL 02", "kamera_id": "TEST", "yon": "giris"},
                     headers=operator_header)
    assert r.status_code == 200, r.text
    kayit_id = r.json()["id"]
    assert r.json()["duzenleyen"] is None

    r2 = client.patch(f"/kayitlar/{kayit_id}", json={
        "plaka_no": "34 dzl 02",  # küçük harf + boşluksuz -- normalize edilmeli
        "yetki_durumu": "yetkili",
        "not_metni": "operatör tarafından manuel olarak yetkilendirildi",
    }, headers=operator_header)
    assert r2.status_code == 200, r2.text
    veri = r2.json()
    assert veri["plaka_no"] == "34 DZL 02"
    assert veri["yetki_durumu"] == "yetkili"
    assert veri["not_metni"] == "operatör tarafından manuel olarak yetkilendirildi"
    assert veri["duzenleyen"] == "rbac-operator"
    assert veri["duzenleme_tarihi"] is not None


def test_kayit_duzenle_gecersiz_yetki_durumu_400_doner(client, operator_header):
    r = client.post("/kayitlar", json={"plaka_no": "34 DZL 03", "kamera_id": "TEST", "yon": "giris"},
                     headers=operator_header)
    kayit_id = r.json()["id"]
    r2 = client.patch(f"/kayitlar/{kayit_id}", json={"yetki_durumu": "gecersiz-deger"}, headers=operator_header)
    assert r2.status_code == 400


def test_kayit_duzenle_kisi_eslestirme_atanir_ve_temizlenir(client, operator_header):
    rk = client.post("/kisiler", json={
        "ad_soyad": "Düzenleme Testi Kişi", "plaka_no": "34 DZL 04", "tip": "personel",
    }, headers=operator_header)
    assert rk.status_code == 200, rk.text
    kisi_id = rk.json()["id"]

    r = client.post("/kayitlar", json={"plaka_no": "06 BSK 05", "kamera_id": "TEST", "yon": "giris"},
                     headers=operator_header)
    kayit_id = r.json()["id"]

    r2 = client.patch(f"/kayitlar/{kayit_id}", json={"kisi_id": kisi_id}, headers=operator_header)
    assert r2.status_code == 200, r2.text
    assert r2.json()["kisi_id"] == kisi_id
    assert r2.json()["kisi_tip_anlik"] == "personel"

    r3 = client.patch(f"/kayitlar/{kayit_id}", json={"kisi_id_temizle": True}, headers=operator_header)
    assert r3.status_code == 200, r3.text
    assert r3.json()["kisi_id"] is None


def test_kayit_duzenle_izleyici_yetkisiz_403_doner(client, operator_header, izleyici_header):
    r = client.post("/kayitlar", json={"plaka_no": "34 DZL 06", "kamera_id": "TEST", "yon": "giris"},
                     headers=operator_header)
    kayit_id = r.json()["id"]
    r2 = client.patch(f"/kayitlar/{kayit_id}", json={"not_metni": "izleyici bunu yapamamalı"},
                       headers=izleyici_header)
    assert r2.status_code == 403


def test_kayit_sil_yalnizca_yonetici_operator_403_doner(client, operator_header):
    r = client.post("/kayitlar", json={"plaka_no": "34 DZL 07", "kamera_id": "TEST", "yon": "giris"},
                     headers=operator_header)
    kayit_id = r.json()["id"]
    r2 = client.delete(f"/kayitlar/{kayit_id}", headers=operator_header)
    assert r2.status_code == 403


def test_kayit_duzenle_bulunamayan_kayit_404_doner(client, operator_header):
    r = client.patch("/kayitlar/999999", json={"not_metni": "yok"}, headers=operator_header)
    assert r.status_code == 404


def test_plaka_analiz_yeni_alanlari_dondurur(client, operator_header):
    """Plaka Analizi ekranının görsel/doğrulama/not/manuel-giriş/düzenleme
    denetim bilgilerini gösterebilmesi için bu alanların analiz uç
    noktasından da gelmesi gerekiyor (bkz. main.py::plaka_analiz)."""
    r = client.post("/kayitlar", json={
        "plaka_no": "34 ANLZ 08", "kamera_id": "PANEL-MANUEL", "yon": "giris",
        "not_metni": "analiz ekranı testi",
    }, headers=operator_header)
    assert r.status_code == 200, r.text

    r2 = client.get("/kayitlar/analiz/34 ANLZ 08", headers=operator_header)
    assert r2.status_code == 200, r2.text
    kayit = r2.json()["son_kayitlar"][0]
    for alan in ("id", "plaka_no", "goruntu_yolu", "guven_skoru", "dogrulama_kare_sayisi",
                 "not_metni", "manuel_giris", "kisi_id", "duzenleyen", "duzenleme_tarihi"):
        assert alan in kayit, f"'{alan}' alanı /kayitlar/analiz yanıtında eksik"
    assert kayit["not_metni"] == "analiz ekranı testi"
    assert kayit["manuel_giris"] is True
