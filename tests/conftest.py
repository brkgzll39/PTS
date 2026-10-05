"""Tüm testler için ortak ayarlar.

ÖNEMLİ: main.py import edildiği anda (modül seviyesinde) veritabanı motorunu
kurar, dizinleri oluşturur ve log dosyasını açar. Bu yüzden test veritabanı
gibi ortam değişkenlerinin, `backend.main` (veya `backend.database`) herhangi
bir test dosyası tarafından import edilmeden ÖNCE ayarlanmış olması gerekir.
conftest.py, pytest tarafından test modülleri toplanmadan/import edilmeden
önce yüklendiği için bu ayarı burada, modül seviyesinde (fixture içinde değil)
yapıyoruz.
"""
import os
import tempfile

# HERMETİK ORTAM (2026-10-05): testler HİÇBİR ZAMAN gerçek kurulumun ayarlarını
# (ortam değişkenleri ya da proje kökündeki .env) kullanmamalı. Özellikle:
# - PTS_KAMERA_ANAHTARI .env'de doluysa /kayitlar/otomatik'e giden TÜM test
#   istekleri 401 alırdı (kullanıcının ilk tam koşusunda ~35 test böyle düştü);
# - PTS_DATABASE_URL gerçek bir SQL Server'ı gösteriyorsa testler ÜRETİM
#   veritabanına yazardı (önceden `setdefault` kullanıldığı için gerçek değer
#   kazanırdı).
# Bu yüzden önce TÜM PTS_* değişkenleri temizlenir, .env yüklemesi kapatılır ve
# test değerleri DOĞRUDAN atanır (setdefault DEĞİL).
for _anahtar in [k for k in os.environ if k.startswith("PTS_")]:
    del os.environ[_anahtar]
os.environ["PTS_ENV_DOSYASINI_ATLA"] = "1"

_TEST_DB_DIZINI = tempfile.mkdtemp(prefix="pts-test-db-")
os.environ["PTS_DATABASE_URL"] = f"sqlite:///{os.path.join(_TEST_DB_DIZINI, 'test_pts.db')}"
os.environ["PTS_LICENSE_SECRET"] = "test-suiti-icin-sabit-lisans-secret"
os.environ["PTS_AUTH_SECRET"] = "test-suiti-icin-sabit-auth-secret-0123456789"
# Gerçek bir kurulumun license.json/cameras.json/sistem_ayarlari.json dosyalarının
# testler tarafından ezilmemesi için bunları da geçici dizine yönlendiriyoruz.
os.environ["PTS_LICENSE_FILE"] = os.path.join(_TEST_DB_DIZINI, "license.json")
os.environ["PTS_CAMERAS_FILE"] = os.path.join(_TEST_DB_DIZINI, "cameras.json")
os.environ["PTS_SISTEM_AYARLARI_FILE"] = os.path.join(_TEST_DB_DIZINI, "sistem_ayarlari.json")


def pytest_collection_modifyitems(config, items):
    """Kamera okuyucu testlerini (gerçek thread/video/zamanlama kullanırlar)
    test_api.py'den ÖNCE çalıştırır.

    Tam koşuda bu testler, test_api.py'nin başlattığı uygulama (kamera
    pipeline'ları, arka plan döngüleri, model yüklemesi) CPU'yu/GIL'i
    kullanırken çalışıyor ve hazırlık adımları 200-300 sn sürüp zaman
    aşımına düşüyordu; tek başına 13 sn'de geçiyorlardı (2026-10-05).
    Temiz bir süreçte çalışmaları bu yarışı ortadan kaldırır. Sıralama kararlıdır:
    diğer testlerin göreli sırası değişmez."""
    items.sort(key=lambda item: 0 if item.path.name == "test_camera_reader.py" else 1)
