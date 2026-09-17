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


def _rol_ile_kullanici_olustur_ve_giris_yap(client, yetkili_header, kullanici_adi: str, rol: str, kisi_id: int = None) -> dict:
    """Verilen role sahip yeni bir kullanıcı oluşturur (yönetici gerektirir),
    onunla giriş yapar ve Authorization header'ını döner. RBAC testlerinde
    kullanılır. `kisi_id`, yalnızca rol="sakin" iken anlamlıdır (bkz.
    main.py::_sakin_kisi_id_dogrula)."""
    govde = {"kullanici_adi": kullanici_adi, "parola": "GucluParola123!", "rol": rol}
    if kisi_id is not None:
        govde["kisi_id"] = kisi_id
    r = client.post("/kullanicilar", json=govde, headers=yetkili_header)
    assert r.status_code == 200, r.text
    r2 = client.post("/auth/giris", json={"kullanici_adi": kullanici_adi, "parola": "GucluParola123!"})
    assert r2.status_code == 200, r2.text
    return {"Authorization": f"Bearer {r2.json()['token']}"}


@pytest.fixture(scope="module")
def sakin_kisi_id(client, yetkili_header):
    """'sakin' (site sakini öz-hizmet portalı) RBAC/işlevsellik testlerinde
    kullanılacak, sakin hesabına bağlanacak Kişi kaydı."""
    r = client.post("/kisiler", json={
        "ad_soyad": "Sakin Test Kişi", "plaka_no": "34 SKN 01", "tip": "abone",
        "daire_departman": "A Blok Daire 5",
    }, headers=yetkili_header)
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture(scope="module")
def sakin_header(client, admin_token, sakin_kisi_id):
    return _rol_ile_kullanici_olustur_ve_giris_yap(
        client, {"Authorization": f"Bearer {admin_token}"}, "rbac-sakin", "sakin", kisi_id=sakin_kisi_id
    )


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


def test_manuel_giris_null_olan_eski_kayit_500_patlamiyor(client, operator_header):
    """REGRESYON (2026-09-17, gerçek kullanıcı ortamında bulundu): SQL
    Server'da ALTER TABLE ... ADD manuel_giris BIT DEFAULT 0, "WITH VALUES"
    açıkça verilmedikçe TABLODA HALİHAZIRDA VAR OLAN satırları NULL bırakıyor
    (SQLite'ın aksine). `manuel_giris` alanı `bool` (Optional değil) olduğu
    için bu, GET /kayitlar gibi uçlarda ResponseValidationError ile 500'e yol
    açtı. Burada bunu, ORM'i atlayıp doğrudan SQL ile manuel_giris'i NULL
    bırakan bir kayıt ekleyerek simüle ediyoruz -- normal POST /kayitlar akışı
    Python tarafında zaten default=False uyguladığı için bunu üretemez, gerçek
    hata yalnızca ham SQL/ALTER TABLE seviyesinde ortaya çıkıyor."""
    from backend.database import engine
    from sqlalchemy import text as sqltext
    with engine.connect() as conn:
        conn.execute(sqltext(
            "INSERT INTO plaka_kayitlari (plaka_no, kamera_id, yon, yetki_durumu, manuel_giris) "
            "VALUES ('34 NULLTEST 09', 'TEST', 'giris', 'bilinmiyor', NULL)"
        ))
        conn.commit()

    r = client.get("/kayitlar", params={"plaka": "NULLTEST"}, headers=operator_header)
    assert r.status_code == 200, r.text
    kayitlar = r.json()
    assert len(kayitlar) == 1
    assert kayitlar[0]["manuel_giris"] is False


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


# ------------------------------------------------------------------
# Kamera yön değiştirme + tespit alanı (ROI) sınırlama
# ------------------------------------------------------------------
# Kök neden (2026-09-17, gerçek kullanıcı ortamında bulundu): giriş ve çıkış
# kameralarının açıları birbirinin şeridini de görecek şekilde örtüşünce,
# giriş yapan bir araç çıkış kamerasına da yansıyıp aynı anda hem "giriş" hem
# "çıkış" olarak iki ayrı kayıt oluşturuyordu. Bunu çözmek için: (1) bir
# kameranın yönünü RTSP adresini/parolasını yeniden girmeye gerek kalmadan
# yerinde değiştirebilen PATCH /kameralar/{id}/yon ve (2) her kameraya
# yüzde tabanlı bir tespit alanı (ROI) tanımlayıp bu alanın dışındaki
# tespitleri oy birikimine hiç sokmayan PATCH /kameralar/{id}/roi eklendi.

@pytest.fixture(scope="module")
def roi_test_kamera_id(client, yetkili_header):
    """Bu modüldeki lisans limiti daha önceki testlerde (bkz.
    test_lisans_aktivasyonu_ve_kamera_limiti) 1 olarak aktifleştirilip o tek
    hak da kullanılmış durumda -- bu yüzden burada limiti yükselten YENİ bir
    lisans aktive edip kendi test kameramızı ekliyoruz."""
    anahtar = lisans.uret("ROI Test Site", kamera_limiti=10, gun=30)
    r = client.post("/lisans/aktive-et", json={"anahtar": anahtar}, headers=yetkili_header)
    assert r.status_code == 200, r.text

    r2 = client.post("/kameralar", json={
        "ad": "ROI Test Kamerası", "rtsp_url": "rtsp://127.0.0.1/roitest", "yon": "giris",
    }, headers=yetkili_header)
    assert r2.status_code == 200, r2.text
    return r2.json()["id"]


def test_kamera_yon_degistir_operator_calistirabilir_ve_yon_gunceller(client, operator_header, roi_test_kamera_id):
    r = client.patch(f"/kameralar/{roi_test_kamera_id}/yon", json={"yon": "cikis"}, headers=operator_header)
    assert r.status_code == 200, r.text
    assert r.json()["yon"] == "cikis"

    # Panel/başka testler karışmasın diye eski haline geri alıyoruz.
    r2 = client.patch(f"/kameralar/{roi_test_kamera_id}/yon", json={"yon": "giris"}, headers=operator_header)
    assert r2.status_code == 200
    assert r2.json()["yon"] == "giris"


def test_kamera_yon_degistir_gecersiz_deger_400_doner(client, operator_header, roi_test_kamera_id):
    r = client.patch(f"/kameralar/{roi_test_kamera_id}/yon", json={"yon": "yukari"}, headers=operator_header)
    assert r.status_code == 400


def test_kamera_yon_degistir_bulunamayan_kamera_404_doner(client, operator_header):
    r = client.patch("/kameralar/YOK-BOYLE-BIR-KAMERA/yon", json={"yon": "giris"}, headers=operator_header)
    assert r.status_code == 404


def test_kamera_yon_degistir_izleyici_yetkisiz_403_doner(client, izleyici_header, roi_test_kamera_id):
    r = client.patch(f"/kameralar/{roi_test_kamera_id}/yon", json={"yon": "cikis"}, headers=izleyici_header)
    assert r.status_code == 403


def test_kamera_roi_guncelle_operator_calistirabilir_ve_alani_kaydeder(client, operator_header, roi_test_kamera_id):
    r = client.patch(f"/kameralar/{roi_test_kamera_id}/roi",
                      json={"x1": 10, "y1": 5, "x2": 90, "y2": 95}, headers=operator_header)
    assert r.status_code == 200, r.text
    kamera = r.json()
    assert kamera["roi"] == {"x1": 10.0, "y1": 5.0, "x2": 90.0, "y2": 95.0}

    # Kalıcı mı diye /kameralar listesinden de doğrula.
    r2 = client.get("/kameralar", headers=operator_header)
    kaydedilen = next(k for k in r2.json() if k["id"] == roi_test_kamera_id)
    assert kaydedilen["roi"] == {"x1": 10.0, "y1": 5.0, "x2": 90.0, "y2": 95.0}


def test_kamera_roi_guncelle_temizle_alani_kaldirir(client, operator_header, roi_test_kamera_id):
    # Önce bir alan tanımlı olduğundan emin ol.
    r0 = client.patch(f"/kameralar/{roi_test_kamera_id}/roi",
                       json={"x1": 0, "y1": 0, "x2": 50, "y2": 50}, headers=operator_header)
    assert r0.status_code == 200 and r0.json()["roi"] is not None

    r = client.patch(f"/kameralar/{roi_test_kamera_id}/roi", json={"temizle": True}, headers=operator_header)
    assert r.status_code == 200, r.text
    # NOT: temizlenince "roi" anahtarı sözlükten tamamen kaldırılıyor
    # (kamera.pop("roi", None)) -- yanıt JSON'unda hiç bulunmaz, None değil.
    assert r.json().get("roi") is None


@pytest.mark.parametrize("govde", [
    {"x1": 50, "y1": 0, "x2": 40, "y2": 100},   # x1 >= x2
    {"x1": 0, "y1": 80, "x2": 100, "y2": 20},   # y1 >= y2
    {"x1": -5, "y1": 0, "x2": 100, "y2": 100},  # 0-100 dışı
    {"x1": 0, "y1": 0, "x2": 100, "y2": 150},   # 0-100 dışı
    {"x1": 0, "y1": 0, "x2": 100},              # eksik alan (y2 yok), temizle=false
])
def test_kamera_roi_guncelle_gecersiz_degerler_400_doner(client, operator_header, roi_test_kamera_id, govde):
    r = client.patch(f"/kameralar/{roi_test_kamera_id}/roi", json=govde, headers=operator_header)
    assert r.status_code == 400, r.text


def test_kamera_roi_guncelle_bulunamayan_kamera_404_doner(client, operator_header):
    r = client.patch("/kameralar/YOK-BOYLE-BIR-KAMERA/roi",
                      json={"x1": 0, "y1": 0, "x2": 100, "y2": 100}, headers=operator_header)
    assert r.status_code == 404


def test_kamera_roi_guncelle_izleyici_yetkisiz_403_doner(client, izleyici_header, roi_test_kamera_id):
    r = client.patch(f"/kameralar/{roi_test_kamera_id}/roi",
                      json={"x1": 0, "y1": 0, "x2": 100, "y2": 100}, headers=izleyici_header)
    assert r.status_code == 403


# ------------------------------------------------------------------
# "sakin" (site sakini öz-hizmet portalı) rolü — 2026-09-17
# ------------------------------------------------------------------
# Kök neden: kullanıcı, ekran görüntüleriyle bir referans ürünün "Abone
# Düzenle" ekranını göstererek site sakinlerinin kendi kullanıcı adı/
# şifresiyle giriş yapıp kendi araç/geçmiş bilgisini yönetebildiği bir
# öz-hizmet hesabı istedi. Bu, panelin önceki üç rolünden (yönetici/
# operatör/izleyici — hepsi "güvenilir iç personel") temelde farklı: bir
# "sakin" DIŞARIDAN bir hesap olduğu için, yalnızca kendi verisine
# erişebilmesi ve tüm dahili/genel amaçlı uçlara (kişi listesi, tüm
# kayıtlar, kameralar, sistem logları vb.) KESİNLİKLE erişememesi gerekir
# (bkz. main.py::_personel_girisi_gerekli ve _sakin_girisi_gerekli).

def test_sakin_olusturma_kisi_id_zorunlu_400_doner(client, yetkili_header):
    r = client.post("/kullanicilar", json={
        "kullanici_adi": "sakin-kisisiz", "parola": "GucluParola123!", "rol": "sakin",
    }, headers=yetkili_header)
    assert r.status_code == 400, r.text


def test_sakin_olusturma_olmayan_kisi_404_doner(client, yetkili_header):
    r = client.post("/kullanicilar", json={
        "kullanici_adi": "sakin-yokkisi", "parola": "GucluParola123!", "rol": "sakin", "kisi_id": 999999,
    }, headers=yetkili_header)
    assert r.status_code == 404, r.text


def test_sakin_olusturma_gecerli_kisiyle_basarili(client, yetkili_header, sakin_kisi_id):
    r = client.post("/kullanicilar", json={
        "kullanici_adi": "sakin-basarili", "parola": "GucluParola123!", "rol": "sakin", "kisi_id": sakin_kisi_id,
    }, headers=yetkili_header)
    assert r.status_code == 200, r.text
    assert r.json()["kisi_id"] == sakin_kisi_id
    assert r.json()["rol"] == "sakin"


def test_sakin_olmayan_rolde_kisi_id_yok_sayilir(client, yetkili_header, sakin_kisi_id):
    """rol != 'sakin' iken kisi_id gönderilse bile anlamsızdır ve kayda
    geçmemeli (bkz. main.py::_sakin_kisi_id_dogrula)."""
    r = client.post("/kullanicilar", json={
        "kullanici_adi": "izleyici-kisili", "parola": "GucluParola123!", "rol": "izleyici", "kisi_id": sakin_kisi_id,
    }, headers=yetkili_header)
    assert r.status_code == 200, r.text
    assert r.json()["kisi_id"] is None


def test_kullanici_guncelle_sakine_terfi_kisi_id_gerektirir(client, yetkili_header):
    r = client.post("/kullanicilar", json={
        "kullanici_adi": "terfi-oncesi", "parola": "GucluParola123!", "rol": "izleyici",
    }, headers=yetkili_header)
    kid = r.json()["id"]
    r2 = client.put(f"/kullanicilar/{kid}", json={"rol": "sakin"}, headers=yetkili_header)
    assert r2.status_code == 400, r2.text


def test_kullanici_guncelle_sakinden_baska_role_kisi_id_temizlenir(client, yetkili_header, sakin_kisi_id):
    r = client.post("/kullanicilar", json={
        "kullanici_adi": "sakin-sonra-operator", "parola": "GucluParola123!", "rol": "sakin", "kisi_id": sakin_kisi_id,
    }, headers=yetkili_header)
    kid = r.json()["id"]
    r2 = client.put(f"/kullanicilar/{kid}", json={"rol": "operatör"}, headers=yetkili_header)
    assert r2.status_code == 200, r2.text
    assert r2.json()["kisi_id"] is None


def test_kisi_silinince_bagli_sakin_hesabinin_kisi_id_temizlenir(client, yetkili_header):
    rk = client.post("/kisiler", json={
        "ad_soyad": "Silinecek Sakin Kişisi", "plaka_no": "34 SLN 02", "tip": "abone",
    }, headers=yetkili_header)
    kisi_id = rk.json()["id"]
    ru = client.post("/kullanicilar", json={
        "kullanici_adi": "sakin-yetim-olacak", "parola": "GucluParola123!", "rol": "sakin", "kisi_id": kisi_id,
    }, headers=yetkili_header)
    kullanici_id = ru.json()["id"]

    rs = client.delete(f"/kisiler/{kisi_id}", headers=yetkili_header)
    assert rs.status_code == 200, rs.text

    rl = client.get("/kullanicilar", headers=yetkili_header)
    hedef = next(k for k in rl.json() if k["id"] == kullanici_id)
    assert hedef["kisi_id"] is None


@pytest.mark.parametrize("yol", ["/kisiler", "/kayitlar", "/kameralar", "/kara-listesi", "/bariyer/ayarlar", "/siteler"])
def test_sakin_genel_amacli_uclara_erisemez_403_doner(client, sakin_header, yol):
    """KÖK NEDEN testi: _personel_girisi_gerekli eklenmeden önce bu uçlar
    yalnızca _giris_gerekli ile korunuyordu -- yani giriş yapmış HERHANGİ
    bir hesap (sakin dahil) tüm kişileri/kayıtları/kameraları görebilirdi."""
    r = client.get(yol, headers=sakin_header)
    assert r.status_code == 403, f"GET {yol}: sakin 403 almalıydı, {r.status_code} aldı ({r.text})"


def test_sakin_auth_me_cagirabilir(client, sakin_header):
    """Bu tek istisna: frontend'in doğru arayüze (öz-hizmet paneli) karar
    verebilmesi için sakin de /auth/me'yi çağırabilmeli."""
    r = client.get("/auth/me", headers=sakin_header)
    assert r.status_code == 200, r.text
    assert r.json()["rol"] == "sakin"


def test_sakin_olmayan_roller_sakin_uclarina_erisemez_403_doner(client, izleyici_header, operator_header, yetkili_header):
    for header in (izleyici_header, operator_header, yetkili_header):
        r = client.get("/sakin/profilim", headers=header)
        assert r.status_code == 403, r.text


def test_sakin_profilim_kendi_kisi_kaydini_doner(client, sakin_header, sakin_kisi_id):
    r = client.get("/sakin/profilim", headers=sakin_header)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == sakin_kisi_id
    assert r.json()["ad_soyad"] == "Sakin Test Kişi"
    assert r.json()["ek_plakalar"] == []


def test_sakin_arac_ekle_ve_sil(client, sakin_header):
    r = client.post("/sakin/arac-ekle", json={"plaka_no": "34 SKN 02", "aciklama": "ikinci aracım"}, headers=sakin_header)
    assert r.status_code == 200, r.text
    plaka_id = r.json()["id"]

    r2 = client.get("/sakin/profilim", headers=sakin_header)
    assert any(p["id"] == plaka_id for p in r2.json()["ek_plakalar"])

    r3 = client.delete(f"/sakin/arac/{plaka_id}", headers=sakin_header)
    assert r3.status_code == 200, r3.text

    r4 = client.get("/sakin/profilim", headers=sakin_header)
    assert not any(p["id"] == plaka_id for p in r4.json()["ek_plakalar"])


def test_sakin_baska_kisinin_plakasini_silemez_404_doner(client, sakin_header, yetkili_header):
    """IDOR regresyonu: bir sakin, kendi kisi_id'sine ait olmayan bir
    KisiPlaka id'sini tahmin ederek silemesin (bkz. main.py::sakin_arac_sil)."""
    rk = client.post("/kisiler", json={
        "ad_soyad": "Başka Sakin", "plaka_no": "34 BSK 03", "tip": "abone",
    }, headers=yetkili_header)
    baska_kisi_id = rk.json()["id"]
    rp = client.post(f"/kisiler/{baska_kisi_id}/plakalar", json={"plaka_no": "34 BSK 04"}, headers=yetkili_header)
    baska_plaka_id = rp.json()["id"]

    r = client.delete(f"/sakin/arac/{baska_plaka_id}", headers=sakin_header)
    assert r.status_code == 404, r.text


def test_sakin_gecmisim_yalnizca_kendi_kayitlarini_doner(client, sakin_header, operator_header, sakin_kisi_id):
    # Sakinin kendi kişisine bağlı bir kayıt oluştur.
    r1 = client.post("/kayitlar", json={"plaka_no": "34 SKN 01", "kamera_id": "TEST-SAKIN", "yon": "giris"}, headers=operator_header)
    assert r1.status_code == 200, r1.text
    assert r1.json()["kisi_id"] == sakin_kisi_id, "Test öncülü: plaka zaten sakin_kisi_id'ye eşleşmeliydi"

    # Başka bir plakaya ait, sakine bağlı OLMAYAN bir kayıt da oluştur.
    r2 = client.post("/kayitlar", json={"plaka_no": "34 BASKASI 05", "kamera_id": "TEST-SAKIN", "yon": "giris"}, headers=operator_header)
    assert r2.status_code == 200, r2.text

    r3 = client.get("/sakin/gecmisim", headers=sakin_header)
    assert r3.status_code == 200, r3.text
    plakalar = {k["plaka_no"] for k in r3.json()}
    assert "34 SKN 01" in plakalar
    assert "34 BASKASI 05" not in plakalar


def test_sakin_hesabi_yetim_kalinca_400_doner(client, yetkili_header):
    """_sakin_kisisini_al'ın 'hesap henüz bağlanmamış' savunmasını, normal
    API akışında bu duruma ULAŞILABİLECEK tek yoldan (bağlı Kişi silinince
    kisi_id NULL'lanır, bkz. test_kisi_silinince_bagli_sakin... ve
    main.py::kisi_sil) uçtan uca doğrular -- ayrı bir kişi/hesap kullanılır
    ki paylaşılan `sakin_header`/`sakin_kisi_id` fixture'ları başka testler
    için bozulmasın."""
    rk = client.post("/kisiler", json={
        "ad_soyad": "Yetim Kalacak Sakin", "plaka_no": "34 YTM 07", "tip": "abone",
    }, headers=yetkili_header)
    kisi_id = rk.json()["id"]
    ru = client.post("/kullanicilar", json={
        "kullanici_adi": "sakin-yetim-kalan", "parola": "GucluParola123!", "rol": "sakin", "kisi_id": kisi_id,
    }, headers=yetkili_header)
    assert ru.status_code == 200, ru.text
    r2 = client.post("/auth/giris", json={"kullanici_adi": "sakin-yetim-kalan", "parola": "GucluParola123!"})
    yetim_header = {"Authorization": f"Bearer {r2.json()['token']}"}

    rs = client.delete(f"/kisiler/{kisi_id}", headers=yetkili_header)
    assert rs.status_code == 200, rs.text

    r3 = client.get("/sakin/profilim", headers=yetim_header)
    assert r3.status_code == 400, r3.text


def test_ziyaretci_onayli_yetki_durumu_kayit_duzenlede_kabul_edilir(client, operator_header):
    """Yeni "Ziyaretçi Girişi" akışının (bkz. app.js::_ziyaretciGirisiKutusunuAyarla,
    ziyaretciBilgileriKaydet) dayandığı whitelist genişletmesi: kayit_duzenle
    artık yetki_durumu="ziyaretci_onayli" değerini kabul etmeli."""
    r = client.post("/kayitlar", json={"plaka_no": "34 ZYR 06", "kamera_id": "TEST-ZYR", "yon": "giris"}, headers=operator_header)
    kayit_id = r.json()["id"]
    r2 = client.patch(f"/kayitlar/{kayit_id}", json={"yetki_durumu": "ziyaretci_onayli"}, headers=operator_header)
    assert r2.status_code == 200, r2.text
    assert r2.json()["yetki_durumu"] == "ziyaretci_onayli"
