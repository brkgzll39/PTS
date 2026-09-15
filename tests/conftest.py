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

_TEST_DB_DIZINI = tempfile.mkdtemp(prefix="pts-test-db-")
os.environ.setdefault("PTS_DATABASE_URL", f"sqlite:///{os.path.join(_TEST_DB_DIZINI, 'test_pts.db')}")
os.environ.setdefault("PTS_LICENSE_SECRET", "test-suiti-icin-sabit-lisans-secret")
os.environ.setdefault("PTS_AUTH_SECRET", "test-suiti-icin-sabit-auth-secret-0123456789")
# Gerçek bir kurulumun license.json/cameras.json/sistem_ayarlari.json dosyalarının
# testler tarafından ezilmemesi için bunları da geçici dizine yönlendiriyoruz.
os.environ.setdefault("PTS_LICENSE_FILE", os.path.join(_TEST_DB_DIZINI, "license.json"))
os.environ.setdefault("PTS_CAMERAS_FILE", os.path.join(_TEST_DB_DIZINI, "cameras.json"))
os.environ.setdefault("PTS_SISTEM_AYARLARI_FILE", os.path.join(_TEST_DB_DIZINI, "sistem_ayarlari.json"))
