from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from backend.database import Base


class Site(Base):
    """PTS'nin yönettiği yerleşke veya tesis."""
    __tablename__ = "siteler"

    id = Column(Integer, primary_key=True, index=True)
    ad = Column(String(120), nullable=False, unique=True)
    aciklama = Column(Text)
    aktif = Column(Boolean, default=True)
    olusturma_tarihi = Column(DateTime, default=datetime.now)

    noktalar = relationship("Nokta", back_populates="site", cascade="all, delete-orphan")


class Kullanici(Base):
    """Panel kullanıcısı ve yetki rolü."""
    __tablename__ = "kullanicilar"

    id = Column(Integer, primary_key=True, index=True)
    kullanici_adi = Column(String(80), nullable=False, unique=True, index=True)
    parola_hash = Column(String(255), nullable=False)
    rol = Column(String(30), nullable=False, default="izleyici")  # yonetici | operatör | izleyici | sakin
    aktif = Column(Boolean, default=True)
    son_giris = Column(DateTime, nullable=True)
    # Yalnızca rol="sakin" hesaplarında dolu: bu giriş hesabının hangi Kişi
    # (site sakini) kaydına ait olduğunu belirtir -- "sakin" bu bağlantı
    # üzerinden SADECE kendi araç/geçmiş bilgisine erişebilir (bkz.
    # main.py::_sakin_girisi_gerekli ve /sakin/... uç noktaları). Diğer üç
    # rol için her zaman NULL'dır. Ham ALTER TABLE ile eklendiği için burada
    # FK kısıtlaması DB seviyesinde uygulanmıyor (bkz. _veritabani_migrasyon
    # -- noktalar.bariyer_id ile aynı desen); kisi silinirse main.py::kisi_sil
    # bu alanı NULL'a çeker.
    kisi_id = Column(Integer, ForeignKey("kisiler.id"), nullable=True)
    olusturma_tarihi = Column(DateTime, default=datetime.now)


class Nokta(Base):
    """Giriş/çıkış gibi kamera ve bariyerlerin bağlı olduğu erişim noktası."""
    __tablename__ = "noktalar"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("siteler.id"), nullable=False, index=True)
    ad = Column(String(120), nullable=False)
    yon = Column(String(10), default="giris")
    # cameras.json'daki kamera "id"si (UUID string) — SQL FK değil, çünkü
    # kameralar veritabanında değil ayrı bir JSON dosyasında tutuluyor.
    kamera_id = Column(String(64), nullable=True)
    bariyer_id = Column(Integer, ForeignKey("bariyer_ayarlari.id"), nullable=True)
    aciklama = Column(Text)
    aktif = Column(Boolean, default=True)
    olusturma_tarihi = Column(DateTime, default=datetime.now)

    site = relationship("Site", back_populates="noktalar")


class Kisi(Base):
    """Abone (site sakini), personel veya ziyaretçi kaydı."""
    __tablename__ = "kisiler"

    id = Column(Integer, primary_key=True, index=True)
    ad_soyad = Column(String(100), nullable=False)
    plaka_no = Column(String(15), nullable=False, index=True)
    tip = Column(String(20), nullable=False)  # abone | personel | ziyaretci
    telefon = Column(String(20))
    daire_departman = Column(String(50))
    aciklama = Column(Text)
    aktif = Column(Boolean, default=True)
    baslangic_tarihi = Column(DateTime, default=datetime.now)
    bitis_tarihi = Column(DateTime, nullable=True)
    # Saat/gün bazlı erişim: "08:00", "18:00", "0,1,2,3,4" (Pazartesi=0 … Pazar=6)
    giris_saati_baslangic = Column(String(5), nullable=True)
    giris_saati_bitis = Column(String(5), nullable=True)
    izin_verilen_gunler = Column(String(20), nullable=True)
    olusturma_tarihi = Column(DateTime, default=datetime.now)

    kayitlar = relationship("Kayit", back_populates="kisi")
    ek_plakalar = relationship("KisiPlaka", back_populates="kisi", cascade="all, delete-orphan")


class KisiPlaka(Base):
    """Bir kişiye bağlı ek araç plakaları (çoklu araç desteği)."""
    __tablename__ = "kisi_plakalar"

    id = Column(Integer, primary_key=True, index=True)
    kisi_id = Column(Integer, ForeignKey("kisiler.id"), nullable=False, index=True)
    plaka_no = Column(String(15), nullable=False, index=True)
    aciklama = Column(String(100))
    aktif = Column(Boolean, default=True)
    olusturma_tarihi = Column(DateTime, default=datetime.now)

    kisi = relationship("Kisi", back_populates="ek_plakalar")


class Kayit(Base):
    """Kameradan / manuel girişten gelen her plaka geçiş kaydı."""
    __tablename__ = "plaka_kayitlari"

    id = Column(Integer, primary_key=True, index=True)
    plaka_no = Column(String(15), nullable=False, index=True)
    tarih_saat = Column(DateTime, default=datetime.now, index=True)
    kamera_id = Column(String(50), default="KAMERA-1")
    yon = Column(String(10), default="giris")
    goruntu_yolu = Column(String(255), nullable=True)
    guven_skoru = Column(Float, nullable=True)
    # OCR'dan ham gelen metin, sadece bilinen bir plakaya göre DÜZELTİLDİYSE
    # doldurulur (bkz. main.py::_bilinen_plakaya_yakinlik_duzelt); düzeltme
    # yapılmadıysa None kalır — plaka_no zaten ham okumanın ta kendisidir.
    # Denetlenebilirlik için: bir düzeltme uygulandığında hem orijinal hem
    # düzeltilmiş halin ikisi de kayıtta kalır.
    ham_plaka_metni = Column(String(20), nullable=True)
    yetki_durumu = Column(String(20), default="bilinmiyor")  # yetkili | yetkisiz | suresi_dolmus | kara_liste
    kisi_id = Column(Integer, ForeignKey("kisiler.id"), nullable=True)
    kisi_tip_anlik = Column(String(20), nullable=True)
    # Bu okumanın kaç FARKLI KAREDE tekrarlanıp oy aldığı (bkz.
    # camera_reader.py::PlakaOyBirikimi.toplam_kare_sayisi) -- kamera
    # pipeline'ından gelmeyen kayıtlarda (manuel giriş, eski kayıtlar) None
    # kalır. 1 ise bu okuma başka HİÇBİR karede doğrulanmadan tek başına
    # kesinleşmiş demektir (yanlış okuma riski daha yüksek); panelde bu
    # kayıtlar ayrıca işaretlenir (bkz. README.md'deki 2026-09-17 notu).
    dogrulama_kare_sayisi = Column(Integer, nullable=True)
    # Bu oturumda (bkz. camera_reader.py::PlakaOyBirikimi) OCR'ın kaç FARKLI
    # METİN VARYANTI önerdiği (2026-09-18). 1 ise tüm kareler AYNI metinde
    # birleşti (gerçek oydaşma); 1'den büyükse kazanan, azınlıkta kalan en az
    # bir farklı okumaya rağmen seçildi demektir -- örn. dedektörün kutuyu
    # kenar boşluksuz kırpması yüzünden bazı karelerde son karakter hiç
    # görülmeyip erken bitmiş bir metin üretilmiş olabilir (bkz. README.md'deki
    # ilgili not). Kamera pipeline'ından gelmeyen kayıtlarda (manuel giriş,
    # eski kayıtlar) None kalır.
    farkli_okuma_sayisi = Column(Integer, nullable=True)
    # Tek seferlik, bu kayda özel not (örn. "görevli tarafından elle içeri
    # alındı, sebep: teslimat"). Kişinin KENDİ profilindeki kalıcı notlar
    # (bkz. Kisi.aciklama) ile KARIŞTIRILMAMALI -- bu SADECE bu tekil geçişe
    # aittir.
    not_metni = Column(Text, nullable=True)
    # Bu kayıt panelden elle mi oluşturuldu (görevlinin "Manuel Kayıt Ekle"
    # ile birini elle içeri alması) yoksa kamera pipeline'ından mı geldi.
    manuel_giris = Column(Boolean, default=False)
    # Denetlenebilirlik: bu kayıt sonradan bir operatör tarafından
    # düzenlendiyse (plaka/yön/durum/kişi/not) kim ve ne zaman değiştirdi.
    duzenleyen = Column(String(80), nullable=True)
    duzenleme_tarihi = Column(DateTime, nullable=True)
    olusturma_tarihi = Column(DateTime, default=datetime.now)

    kisi = relationship("Kisi", back_populates="kayitlar")


class KaraListesi(Base):
    """Engellenen veya şüpheli araç listesi."""
    __tablename__ = "kara_listesi"

    id = Column(Integer, primary_key=True, index=True)
    plaka_no = Column(String(15), nullable=False, unique=True, index=True)
    sebep = Column(String(255))
    ekleyen = Column(String(80))
    aktif = Column(Boolean, default=True)
    olusturma_tarihi = Column(DateTime, default=datetime.now)


class LedMesaj(Base):
    """LED panele gönderilen mesajların günlüğü."""
    __tablename__ = "led_mesajlari"

    id = Column(Integer, primary_key=True, index=True)
    mesaj = Column(String(255))
    tarih_saat = Column(DateTime, default=datetime.now)
    basarili = Column(Boolean, default=True)


class Alarm(Base):
    """Yetkisiz veya süresi dolmuş geçişler için alarm günlüğü."""
    __tablename__ = "alarmlar"

    id = Column(Integer, primary_key=True, index=True)
    kayit_id = Column(Integer, ForeignKey("plaka_kayitlari.id"), nullable=True, index=True)
    plaka_no = Column(String(15), nullable=False, index=True)
    alarm_tipi = Column(String(30), nullable=False, index=True)
    mesaj = Column(String(255), nullable=False)
    okundu = Column(Boolean, default=False, index=True)
    tarih_saat = Column(DateTime, default=datetime.now, index=True)


class BariyerAyarlari(Base):
    """Bariyer açma webhook/GPIO ayarları."""
    __tablename__ = "bariyer_ayarlari"

    id = Column(Integer, primary_key=True, index=True)
    ad = Column(String(80), nullable=False)
    mod = Column(String(20), default="simulate")  # simulate | http | gpio
    http_url = Column(String(255))
    http_metot = Column(String(10), default="GET")
    http_govde = Column(Text)
    gpio_pin = Column(Integer)
    auto_ac = Column(Boolean, default=False)  # yetkili araç girişinde otomatik aç
    aktif = Column(Boolean, default=True)
    olusturma_tarihi = Column(DateTime, default=datetime.now)


class BildirimAyarlari(Base):
    """Webhook veya e-posta bildirim kuralları."""
    __tablename__ = "bildirim_ayarlari"

    id = Column(Integer, primary_key=True, index=True)
    ad = Column(String(80), nullable=False)
    tip = Column(String(20), default="webhook")  # webhook | email
    hedef = Column(String(255), nullable=False)  # URL veya e-posta adresi
    tetikleyici = Column(String(30), default="hepsi")  # hepsi | yetkisiz | kara_liste | suresi_dolmus
    http_metot = Column(String(10), default="POST")
    aktif = Column(Boolean, default=True)
    olusturma_tarihi = Column(DateTime, default=datetime.now)
