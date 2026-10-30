from sqlalchemy import BigInteger, Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, UniqueConstraint, Date
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
    rol = Column(String(30), nullable=False, default="izleyici")  # yonetici | operatör | güvenlik | izleyici | sakin
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
    # KAMERA/NOKTA ERİŞİM KISITLAMASI (2026-09-21): NULL/boş = kısıtlama YOK,
    # hesap TÜM kameraları görebilir -- geriye dönük uyumluluk için varsayılan
    # budur (mevcut tüm hesaplar bu haldeydi). Dolu olduğunda, `cameras.json`
    # id'lerinin bir JSON dizisi ("[\"uuid-1\", \"uuid-2\"]") olarak saklanır;
    # bu hesap yalnızca listedeki kameraları canlı izleyebilir VE genel
    # "Kayıtlar" akışında yalnızca bu kameralardan gelen geçişleri görür (bkz.
    # main.py::_kullanicinin_izinli_kameralari, _guvenlik_kayit_filtresi_uygula).
    # KASITLI İSTİSNA: "Plaka Analizi" (bkz. main.py::plaka_analiz) belirli bir
    # aracı hedefleyen bir arama olduğu için bu kısıtlamadan MUAFTIR -- bir
    # vardiyanın/noktanın, başka bir vardiyada/noktada geçen belirli bir aracı
    # tespit edebilmesi gerekir (bkz. README'deki 2026-09-21 notu, kullanıcı
    # talebi). Ham ALTER TABLE ile eklendiği için (bkz. _veritabani_migrasyon,
    # kisi_id ile AYNI desen) burada da DB seviyesinde bir kısıtlama/FK yok;
    # geçerlilik main.py::_kamera_id_listesini_dogrula ile UYGULAMA seviyesinde
    # sağlanıyor.
    kamera_erisim_listesi = Column(Text, nullable=True)
    # VARDİYA GRUBU ADI (2026-09-21): NULL = bu hesap adlandırılmış bir
    # vardiya grubuna atanmamış -- güvenlik oturumu görünürlüğü (bkz.
    # main.py::_kullanicinin_vardiya_pencereleri) yalnızca KENDİ oturumlarıyla
    # sınırlı kalır (eski/varsayılan davranış). Dolu olduğunda (ör. "A"),
    # AYNI değeri taşıyan TÜM hesapların vardiya oturumları BİRLEŞİK olarak
    # görünür hale gelir -- kullanıcı talebi (2026-09-21): "LOJMAN A Vardiyası
    # Bülent ile aynı zaman aralığında çalışacağı için ... Ana nizamiyeden
    # bülent kontrol ettiğinde Lojman A geçişlerini de görebilecek" -- yani
    # FARKLI fiziksel noktalardaki (Ana Nizamiye/Lojman Nizamiye) hesaplar aynı
    # vardiya adını paylaşarak birbirinin kayıt görünürlüğünü PAYLAŞABİLİR.
    # Panelde serbest metin olarak saklanır (main.py::kullanici_ekle/
    # kullanici_guncelle normalize eder: baş/son boşluk temizlenir, büyük harfe
    # çevrilir) ama arayüz A/B/C/D önerir. Kayıtlar ekranındaki "Vardiya"
    # sütununu/filtresini de besler (bkz. main.py::
    # _kayitlarin_vardiya_adlarini_ekle). Ham ALTER TABLE ile eklendiği için
    # (bkz. _veritabani_migrasyon, kisi_id ile AYNI desen) DB seviyesinde bir
    # kısıtlama yok.
    vardiya_adi = Column(String(20), nullable=True)
    # İKİ ADIMLI DOĞRULAMA (2026-10-23) -- bkz. backend/totp.py. totp_gizli
    # kurulum başlayınca yazılır; totp_aktif ancak uygulamadan okunan ilk kod
    # doğrulanınca True olur. Aktifken girişte parolaya ek 6 haneli kod istenir.
    totp_gizli = Column(String(64), nullable=True)
    totp_aktif = Column(Boolean, default=False)
    # EKRAN KISITLAMASI (2026-10-23): NULL = rolün gördüğü tüm ekranlar.
    # Dolu ise JSON dizi (ör. ["canli","kontrol","panel","iceride","kayitlar"]):
    # arayüz yalnız bu sekmeleri gösterir. Yetki rolden gelir; bu yalnız
    # görünürlüktür (bkz. schemas.EKRANLAR).
    ekran_listesi = Column(Text, nullable=True)
    olusturma_tarihi = Column(DateTime, default=datetime.now)


class VardiyaAtamasi(Base):
    """KULLANIMDAN KALDIRILDI (2026-09-20) -- bkz. VardiyaOturumu ve README'deki
    "Öz-Hizmet Vardiya Oturumları" notu. Bu sınıf ve `vardiya_atamalari`
    tablosu, yönetici panelinden ELLE, GÜN BAZLI vardiya ataması yapılan ESKİ
    sistemden kalma; kullanıcı geri bildirimi ("her gün ben giremem, personel
    kendi vardiyasını kendi başlatıp bitirsin") üzerine tamamen
    VardiyaOturumu (giriş/çıkışa bağlı, ÖZ-HİZMET) sistemiyle DEĞİŞTİRİLDİ.
    Sınıf, üretimdeki mevcut tabloyu/geçmiş verileri BOZMAMAK için burada
    bırakıldı (SQLAlchemy `create_all` var olan bir tabloyu SİLMEZ), ama
    main.py'de ARTIK HİÇBİR YERDE okunmuyor/yazılmıyor -- yalnızca geçiş
    öncesi oluşturulmuş eski atamaların veritabanında durmaya devam etmesi
    içindir. Yeni kod bu sınıfı KULLANMAMALI."""
    __tablename__ = "vardiya_atamalari"

    id = Column(Integer, primary_key=True, index=True)
    kullanici_id = Column(Integer, ForeignKey("kullanicilar.id"), nullable=False, index=True)
    tarih = Column(DateTime, nullable=False, index=True)
    baslangic_saat = Column(String(5), nullable=False)  # "HH:MM"
    bitis_saat = Column(String(5), nullable=False)  # "HH:MM"
    olusturan = Column(String(80), nullable=True)
    olusturma_tarihi = Column(DateTime, default=datetime.now)


class VardiyaOturumu(Base):
    """rol="güvenlik" (Güvenlik Personeli) hesapları için ÖZ-HİZMET
    (self-service) vardiya oturumu (bkz. 2026-09-20 "Öz-Hizmet Vardiya
    Oturumları" notu, README; önceki elle/gün-bazlı `VardiyaAtamasi`
    sisteminin YERİNE geçer). Kullanıcı talebi: yöneticinin her personelin
    vardiya saatlerini önceden elle girmesi yerine, PERSONEL KENDİSİ giriş
    yapınca vardiyası başlasın, çıkış yapana kadar sürsün istedi.

    Bir satır = TEK BİR oturum: `giris_zamani`, kullanıcının `/auth/giris`
    çağrısının (bkz. main.py::giris_yap, ::_guvenlik_oturum_baslat) sunucu
    zaman damgasıdır; `cikis_zamani`, `/auth/cikis` çağrısının (bkz.
    main.py::cikis_yap) zaman damgasıdır ve oturum kapanana kadar NULL kalır.

    `cikis_zamani` NULL olduğu sürece oturum AÇIK sayılır ve filtre mantığı
    (bkz. main.py::_kullanicinin_vardiya_pencereleri) bu pencereyi ÜST SINIRI
    OLMADAN yorumlar -- yani `giris_zamani`'ndan bu yana (ve oturum kapanana
    kadar) gerçekleşen TÜM yeni/canlı geçişler o kullanıcıya görünür kalır.

    "Unutulan çıkış" (tarayıcı/bilgisayar `/auth/cikis` hiç çağrılmadan
    kapatılması) durumunda oturum süresiz AÇIK kalabilir -- ama bu
    ZARARSIZDIR: aynı kullanıcı bir dahaki sefer TEKRAR giriş yaptığında, o
    andaki zaman damgasıyla eski açık oturum OTOMATİK kapatılır ve yeni bir
    oturum açılır (bkz. _guvenlik_oturum_baslat) -- bu sayede unutulan bir
    çıkış, bir SONRAKİ gerçek vardiyanın kayıtlarına asla karışmaz. Yönetici
    de "Vardiya Oturumları" panelinden açık kalmış bir oturumu elle
    sonlandırabilir (bkz. /vardiya-oturumlari/{id}/sonlandir).

    Aynı anda birden fazla güvenlik personelinin oturumu açıksa (ör. devir
    teslim saatinde), bir kayıt HER İKİSİNİN de listesinde ayrı ayrı görünür
    -- `VardiyaAtamasi`'ndaki ile AYNI, bilinçli tasarım kararı (bkz. README)."""
    __tablename__ = "vardiya_oturumlari"

    id = Column(Integer, primary_key=True, index=True)
    kullanici_id = Column(Integer, ForeignKey("kullanicilar.id"), nullable=False, index=True)
    giris_zamani = Column(DateTime, nullable=False, default=datetime.now, index=True)
    cikis_zamani = Column(DateTime, nullable=True, index=True)


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
    tip = Column(String(20), nullable=False)  # abone | personel | ziyaretci | vip | alt_isveren
    telefon = Column(String(20))
    daire_departman = Column(String(50))
    aciklama = Column(Text)
    # 2026-10-22: bu kişinin aracı geçtiğinde kaydın notu boşsa otomatik yazılan
    # not (ör. "TPIC", "Servis") -- görevli her geçişte elle yazmasın.
    otomatik_not = Column(String(100), nullable=True)
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
    # DAHUA ANPR KATKISI (2026-09-25 kullanıcı isteği: "Bu akşamki geçişleri
    # takip etmek için yeni yaptığım dahua eklemesiyle hangisi daha verimli
    # çalışmış tespit edebilmem için bir grafik"). Bu geçiş oturumunda
    # KAMERANIN KENDİ Dahua ANPR okuması (bkz. camera_reader.py::
    # KameraPipeline.harici_okuma_ekle, HARICI_OKUMA_OY_AGIRLIGI) kazanan
    # plaka metnine oy verdiyse True; PTS'in kendi OCR'ı tek başına
    # kesinleştirdiyse False; kamera pipeline'ından GELMEYEN kayıtlarda
    # (manuel giriş, eski kayıtlar, dahua_anpr hiç açılmamış kameralar)
    # None kalır -- "Dahua'nın hiç katkısı olmadı" ile "bu bilgi bu kayıt
    # için hiç hesaplanmadı" birbirinden ayırt edilebilsin diye BİLİNÇLİ
    # olarak False değil None kullanılır. Kamera bazında karşılaştırma:
    # main.py::kamera_dahua_karsilastirma.
    harici_katkili = Column(Boolean, nullable=True)
    # KAMERA OKUMASI UYUŞMAZLIĞI (2026-10-12): kameranın KENDİ ANPR'ı (Dahua)
    # bu geçişte kaydedilen plakadan FARKLI bir metin okuduysa o metin
    # ("16 AC 9302"); aynıysa ya da kamera okuması yoksa None. Doluysa kayıt
    # panelde "Kontrol gerekli" diye işaretlenir -- iki okumadan biri yanlıştır.
    kamera_okumasi = Column(String(20), nullable=True)
    # Tek seferlik, bu kayda özel not (örn. "görevli tarafından elle içeri
    # alındı, sebep: teslimat"). Kişinin KENDİ profilindeki kalıcı notlar
    # (bkz. Kisi.aciklama) ile KARIŞTIRILMAMALI -- bu SADECE bu tekil geçişe
    # aittir.
    not_metni = Column(Text, nullable=True)
    # Kişiye (Kisi tablosu, kisi_id) bağlı OLMAYAN bir "misafir" geçişinde,
    # aracı kullanan kişinin ad soyadını serbest metin olarak kaydetmek
    # içindir (2026-09-22 kullanıcı isteği: "gelen tüm araçların bu ekranda
    # misafirse de isim soyisimlerini kaydetmek için bir sütun'a daha
    # ihtiyacım var"). `not_metni` (herhangi bir amaçla kullanılabilen
    # serbest not) ile KARIŞTIRILMAMALI -- bu alan SADECE kişinin adı
    # içindir. kisi_id doluysa kişinin gerçek adı zaten Kisi.ad_soyad'dan
    # gelir (bkz. main.py::kayitlari_listele'nin kisi join'i); bu alan o
    # durumda genelde boş bırakılır, yalnızca HİÇBİR Kişi kaydına
    # bağlanmamış (kisi_id IS NULL) bir "misafir" geçişi için doldurulur.
    misafir_adi = Column(String(100), nullable=True)
    # ARVENTO ENTEGRASYONU (2026-09-23 kullanıcı isteği): "Arvento Sisteminde
    # kimlik kartı ile aracın çalıştıran personelin ... bilgisi pts sistemine
    # entegre edilmesini istiyorum ... o araç plaka tanıma sisteminden geçiş
    # yaptığında direkt olarak aracı kullanan personel ismi ona göre
    # güncellenecek." Arvento'nun harici webhook'undan (bkz.
    # main.py::arvento_webhook) gelen "bu plakayı şu an kim kullanıyor"
    # bilgisinin, bu kayıt OLUŞTURULDUĞU ANDA bilinen en güncel halidir (bkz.
    # main.py::_arvento_surucu_bul, _kayit_olustur_ve_bildir içinde
    # çağrılıyor). BİLİNÇLİ OLARAK misafir_adi'DAN AYRI bir alandır:
    # misafir_adi kişi tarafından/görevli tarafından ELLE girilen, kisi_id'ye
    # BAĞLI OLMAYAN bir misafir adıdır; surucu_adi ise OTOMATİK, Arvento
    # kaynaklı ve kisi_id'den TAMAMEN BAĞIMSIZDIR (araç örn. bir abonenin
    # üzerine kayıtlı olabilir ama o gün başka bir personel kullanıyor
    # olabilir — ikisi çelişmez, ikisi de aynı anda dolu olabilir). Kullanıcı
    # açıkça "sadece isim olarak gösterilsin, PTS Kişi kayıtlarıyla
    # eşleştirme yapılmasın" dediği için PTS'teki Kisi tablosuyla HİÇBİR
    # otomatik bağ kurulmaz — bu yalnızca serbest metin bir görüntüleme
    # alanıdır. Sistem tarafından otomatik dolduğundan panelden ELLE
    # düzenlenebilir bir alan OLARAK SUNULMAZ (bkz. schemas.KayitDuzenle'nin
    # bu alanı içermemesi) — yanlış eşleşen bir kaydı düzeltmenin yolu,
    # Arvento'dan doğru olayın tekrar gelmesini beklemek ya da (ileride
    # istenirse) ayrı bir düzeltme uç noktası eklemektir.
    surucu_adi = Column(String(100), nullable=True)
    # Bu kayıt panelden elle mi oluşturuldu (görevlinin "Manuel Kayıt Ekle"
    # ile birini elle içeri alması) yoksa kamera pipeline'ından mı geldi.
    manuel_giris = Column(Boolean, default=False)
    # Denetlenebilirlik: bu kayıt sonradan bir operatör tarafından
    # düzenlendiyse (plaka/yön/durum/kişi/not) kim ve ne zaman değiştirdi.
    duzenleyen = Column(String(80), nullable=True)
    duzenleme_tarihi = Column(DateTime, nullable=True)
    # "İçeriden çıkar" (2026-10-26): çıkışı kameraya okunmayan aracın GİRİŞ
    # kaydına görevlinin "çıktı" işareti. Sahte bir çıkış kaydı üretilmez;
    # araç İçerideki Araçlar listesinden düşer, geçiş kayıtları değişmez.
    elle_cikis_zamani = Column(DateTime, nullable=True)
    elle_cikis_yapan = Column(String(80), nullable=True)
    olusturma_tarihi = Column(DateTime, default=datetime.now)

    kisi = relationship("Kisi", back_populates="kayitlar")


class ArventoSuruculuOlay(Base):
    """Arvento'nun harici webhook'undan alınan her "bu plakayı şu an kim
    kullanıyor" olayının HAM KAYDI (2026-09-23 kullanıcı isteği, bkz.
    main.py::arvento_webhook). BİLİNÇLİ OLARAK "son atama" alanını doğrudan
    Kisi/Kayit üzerinde TUTMAK yerine (tek satırlık, üzerine yazılan bir
    durum) her olay AYRI bir satır olarak eklenir (append-only günlük):

    1) Denetlenebilirlik/hata ayıklama: Arvento'nun gerçek webhook gövde
       biçimi bu entegrasyon yazılırken KESİN olarak bilinmiyordu (kullanıcı
       "bu konuyu arvento ile konuşmam gerekiyor" dedi) -- alan adları
       tahminle eşleştiriliyor (bkz. main.py::_ARVENTO_PLAKA_ALANLARI vb.).
       Gerçek üretimde bir eşleşme sorunu çıkarsa `ham_veri`daki tam JSON
       gövdesi olmadan kök nedeni bulmak imkansız olurdu.
    2) `alinma_zamani` (sunucunun olayı ALDIĞI an, HER ZAMAN dolu) ile
       `olay_zamani` (Arvento'nun gövdede bildirdiği zaman, opsiyonel/
       ayrıştırılamazsa None) kasıtlı olarak AYRI tutulur -- eşleştirme
       (bkz. main.py::_arvento_surucu_bul) `alinma_zamani`ya göre sıralar,
       çünkü bu değer HER ZAMAN doğru ve monoton artandır; Arvento'nun kendi
       saatine güvenmek (saat senkronizasyon sorunu / farklı biçim/dilim
       ihtimali) sessiz bir sıralama hatasına yol açabilirdi.
    """
    __tablename__ = "arvento_surucu_olaylari"

    id = Column(Integer, primary_key=True, index=True)
    plaka_no = Column(String(15), nullable=False, index=True)
    surucu_adi = Column(String(100), nullable=False)
    # Arvento'nun kimlik kartı/sicil no bilgisi -- yalnızca referans/hata
    # ayıklama amaçlı saklanır, kullanıcının açık isteği doğrultusunda
    # ("sadece isim olarak gösterilsin") PTS Kişi kayıtlarıyla eşleştirmede
    # KULLANILMAZ.
    kart_no = Column(String(50), nullable=True)
    olay_zamani = Column(DateTime, nullable=True)
    alinma_zamani = Column(DateTime, default=datetime.now, index=True)
    # Ham JSON gövdesi (hata ayıklama/denetim amaçlı, bkz. sınıf docstring'i).
    ham_veri = Column(Text, nullable=True)


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
    """Webhook veya Telegram bildirim kuralları -- alarm/kayıt olaylarını
    panelin DIŞINA (nöbetçinin telefonuna vb.) da anlık iletmek için (bkz.
    main.py::_bildirim_tetikle, backend/telegram_bildirim.py).

    NOT (2026-09-26): `tip` daha önce "webhook | email" olarak
    belgeleniyordu ama "email" hiçbir zaman gerçekten UYGULANMADI -- bir
    kullanıcı panelden/API'den `tip="email"` ile bir ayar oluştursaydı,
    ayar sessizce hiçbir zaman çalışmayacaktı (bkz. main.py::
    _bildirim_gonder_sync'in kök neden notu). Artık yalnızca gerçekten
    desteklenen değerler kabul ediliyor: webhook | telegram."""
    __tablename__ = "bildirim_ayarlari"

    id = Column(Integer, primary_key=True, index=True)
    ad = Column(String(80), nullable=False)
    tip = Column(String(20), default="webhook")  # webhook | telegram
    hedef = Column(String(255), nullable=False)  # webhook: hedef URL -- telegram: chat_id
    tetikleyici = Column(String(30), default="hepsi")  # hepsi | yetkisiz | kara_liste | suresi_dolmus | supheli_arac | bariyer_hatasi | disk_hatasi | kamera_arizasi | yedek_bozuk | disk_doluyor | sertifika_bitiyor
    http_metot = Column(String(10), default="POST")  # yalnızca tip="webhook" için anlamlıdır
    aktif = Column(Boolean, default=True)
    olusturma_tarihi = Column(DateTime, default=datetime.now)


class DenetimKaydi(Base):
    """Hassas yönetici işlemlerinin kalıcı denetim (audit) izi.

    KÖK NEDEN (2026-09-20): kullanıcı rolü/aktiflik değiştirme, hesap silme,
    kamera silme, lisans aktivasyonu, sistem ayarları değiştirme gibi
    işlemler önceden yalnızca (döngüsel olarak silinen/sıkıştırılan)
    `loglar/pts.log` metin dosyasına yazılıyordu -- ne filtrelenebiliyordu
    ne de panelde görülebiliyordu, yalnızca sunucuya dosya erişimi olan biri
    okuyabilirdi. Bu tablo AYNI olayları (bkz. main.py::_denetim_kaydet)
    kalıcı, sorgulanabilir ve panelde ("Denetim Kayıtları" sekmesi, yalnızca
    yönetici) görüntülenebilir hâle getiriyor. Log dosyasına yazma DEVAM
    EDİYOR (iki bağımsız kayıt yeri -- biri bozulursa/silinirse diğeri
    hâlâ durur); bu tablo bunun YERİNE değil, YANINDA eklendi."""
    __tablename__ = "denetim_kayitlari"

    id = Column(Integer, primary_key=True, index=True)
    zaman = Column(DateTime, default=datetime.now, index=True)
    kullanici_adi = Column(String(80), nullable=False, index=True)  # işlemi YAPAN kullanıcı
    eylem = Column(String(50), nullable=False, index=True)  # ör. "kullanici_sil", "kamera_sil"
    aciklama = Column(Text, nullable=False)  # insan-okunur detay (ör. "rol: izleyici -> operatör")


class OturumTokeni(Base):
    """Başarılı bir /auth/giris ile açılmış TEK BİR aktif oturumun kaydı --
    "Hesap Güvenliği: Aktif Oturumları Görme ve Uzaktan Kapatma" (2026-09-26,
    kullanıcı isteği).

    KÖK NEDEN: kimlik doğrulama önceden TAMAMEN DURUMSUZDU (stateless) --
    `main.py::_token_uret` yalnızca `kullanici_id` ve bir bitiş zaman
    damgasını HMAC ile imzalıyordu, sunucu tarafında bu token'a dair HİÇBİR
    kayıt tutulmuyordu. Bu şu iki soruyu YANITSIZ bırakıyordu: (1) "şu an bu
    hesapla hangi cihazlar/tarayıcılardan oturum açılmış?" ve (2) parola
    değiştirmeden, yalnızca "şu belirli oturumu" uzaktan kapatmak -- imzası
    hâlâ matematiksel olarak geçerli bir token'ı, süresi (8 saat) dolmadan
    iptal etmenin HİÇBİR yolu yoktu (bir hesabı `aktif=False` yapmak TÜM
    oturumlarını keser ama hesabı da tamamen kullanılamaz hale getirir --
    "yalnızca şüpheli BİR oturumu kapat, hesabı KİLİTLEME" isteğini
    karşılamaz).

    Artık her başarılı girişte burada rastgele/tahmin edilemez bir `jti`
    (JWT terminolojisindeki "JWT ID" karşılığı, ama burada JWT değil kendi
    imzalı biçimimiz kullanılıyor) ile bir satır açılıyor VE bu jti token'ın
    imzalı GÖVDESİNE de ekleniyor (bkz. main.py::_token_uret/_token_coz).
    `_giris_gerekli` (ve token'ı doğrudan çözen /kamera-akis, /olaylar/sse
    uç noktaları) artık imza+süre kontrolüne EK olarak bu satırın hâlâ var
    olmasını da zorunlu kılıyor -- satır silinirse (yönetici panelden
    "Kapat" derse, ya da parola sıfırlanınca/hesap pasife alınınca ilgili
    kullanıcının TÜM satırları toplu silinince, bkz. main.py::
    kullanici_guncelle/kullanici_sil) imza hâlâ geçerli olsa bile bir
    SONRAKİ istekte 401 döner. Süresi geçmiş satırlar `main.py::
    _oturum_temizlik_dongu` tarafından periyodik olarak temizlenir (yoksa
    tablo sınırsız büyür -- bkz. Patch #113'ün "disk doluyor" kök neden
    notuyla AYNI türde bir sorun olurdu)."""
    __tablename__ = "oturum_tokenleri"

    id = Column(Integer, primary_key=True, index=True)
    kullanici_id = Column(Integer, ForeignKey("kullanicilar.id"), nullable=False, index=True)
    jti = Column(String(32), nullable=False, unique=True, index=True)
    # İstemcinin IP adresi (bkz. main.py::giris_yap -- request.client.host).
    # Yalnızca bilgilendirici amaçlıdır, hiçbir yetkilendirme kararı buna
    # dayanmaz (ör. bir NAT/proxy arkasında birden çok kullanıcı aynı IP'yi
    # paylaşabilir).
    ip_adresi = Column(String(64), nullable=True)
    olusturma_tarihi = Column(DateTime, default=datetime.now)
    # _giris_gerekli tarafından THROTTLE edilerek güncellenir (bkz. main.py::
    # _OTURUM_GUNCELLEME_ARALIK_SN) -- her istekte yazmak gereksiz DB
    # yüküne yol açardı; panelde "son görülme" olarak gösterilir.
    son_kullanim_tarihi = Column(DateTime, default=datetime.now)
    # Token'ın imzalı gövdesindeki bitiş zaman damgasıyla AYNI değer --
    # süresi geçmiş satırların temizlik döngüsünce bulunabilmesi için burada
    # da (sorgulanabilir bir DateTime olarak) tutulur.
    bitis_tarihi = Column(DateTime, nullable=False)


class PushToken(Base):
    """Mobil uygulamanın (React Native/Expo) anlık bildirim alabilmesi için
    kaydettiği Expo push token'ı (2026-09-27, kullanıcı isteği: "daha
    profesyonel mobil uygulama" -- push bildirim istendi).

    Mimari not: OturumTokeni (yukarısı) YETKİLENDİRME için, bu ise SADECE
    BİLDİRİM HEDEFİ için -- ikisi bilinçli olarak ayrı tablolar. Bir push
    token, kullanıcı çıkış yapıp token'ı (OturumTokeni) süresi dolsa bile
    o CİHAZA bildirim gönderilebilmesi için ayrıca yaşamaya devam edebilir
    (gerçek uygulamalarda normal davranış budur) -- bu yüzden OturumTokeni
    silinince/süresi dolunca CASCADE ile silinmiyor.

    `expo_push_token` TEKİL (unique): aynı fiziksel cihaz farklı bir
    kullanıcıyla tekrar giriş yaparsa (ör. vardiya değişimi) aynı satır
    GÜNCELLENİR (bkz. main.py::/push/kaydet'teki upsert) -- aksi halde eski
    kullanıcı hesabına bağlı satır o cihaza bildirim göndermeye devam eder,
    hesabı artık kullanmayan biri başkasının bildirimini görürdü."""
    __tablename__ = "push_tokenlari"

    id = Column(Integer, primary_key=True, index=True)
    kullanici_id = Column(Integer, ForeignKey("kullanicilar.id"), nullable=False, index=True)
    expo_push_token = Column(String(200), nullable=False, unique=True, index=True)
    platform = Column(String(20), default="bilinmiyor")  # ios | android
    olusturma_tarihi = Column(DateTime, default=datetime.now)
    son_kullanim_tarihi = Column(DateTime, default=datetime.now)


class NobetNotu(Base):
    """Vardiya devir-teslim defteri (2026-10-12, kullanıcı isteği): bir vardiyanın
    sonrakilere bıraktığı not (ör. "34 ABC 123 yarın 09:00'da gelecek", "Lojman
    bariyeri takılıyor"). Notlar silinmez/düzenlenmez (denetim izi); "kapatılana
    kadar" açık kalır ve her vardiyaya gösterilir. Yazan/kapatan kullanıcının adı
    kopyalanarak saklanır (FK değil): kullanıcı sonradan silinse de not okunur kalır."""
    __tablename__ = "nobet_notlari"

    id = Column(Integer, primary_key=True, index=True)
    metin = Column(Text, nullable=False)
    kapi = Column(String(80), nullable=False, default="Genel")
    olusturan_id = Column(Integer, nullable=True)
    olusturan_adi = Column(String(80), nullable=False)
    vardiya_adi = Column(String(30), nullable=True)
    olusturma_zamani = Column(DateTime, default=datetime.now, index=True)
    kapali = Column(Boolean, default=False, index=True)
    kapatan_adi = Column(String(80), nullable=True)
    kapanma_zamani = Column(DateTime, nullable=True)
    kapanis_notu = Column(Text, nullable=True)

    okumalar = relationship("NobetNotuOkuma", back_populates="nobet_notu", order_by="NobetNotuOkuma.okuma_zamani")


class BeklenenZiyaretci(Base):
    """Ön kayıtlı (beklenen) ziyaretçi (2026-10-26, kullanıcı isteği). Nöbet
    Defteri'ne "34 ABC 123 yarın 09:00'da gelecek" yazmak yerine plaka, misafir
    ve ev sahibi girilir; araç geçerlilik aralığında kameraya okununca kayıt
    kendiliğinden "onaylı ziyaretçi" sayılır, misafir adı ve not dolar (bkz.
    main.py::_beklenen_ziyaretci_bul). Otomatik bariyer açtırmaz: o yalnızca
    tanımlı (yetkili) araçlar içindir. Kayıtlar silinmez; iptal edilir."""
    __tablename__ = "beklenen_ziyaretciler"

    id = Column(Integer, primary_key=True, index=True)
    plaka_no = Column(String(15), nullable=False, index=True)
    misafir_adi = Column(String(100), nullable=True)
    ev_sahibi = Column(String(120), nullable=True)   # kimin misafiri / departman
    aciklama = Column(String(300), nullable=True)
    beklenen_saat = Column(String(5), nullable=True)  # "09:00" -- bilgi amaçlı
    baslangic = Column(DateTime, nullable=False, index=True)
    bitis = Column(DateTime, nullable=False, index=True)
    olusturan_adi = Column(String(80), nullable=False)
    olusturma_zamani = Column(DateTime, default=datetime.now)
    ilk_gelis_zamani = Column(DateTime, nullable=True)
    ilk_gelis_kayit_id = Column(Integer, nullable=True)
    ilk_gelis_kamera = Column(String(64), nullable=True)
    iptal = Column(Boolean, default=False)
    iptal_eden = Column(String(80), nullable=True)
    # Misafir daveti (2026-10-30): öz-hizmet hesabının kendi oluşturduğu kayıt.
    davet_eden_kullanici_id = Column(Integer, nullable=True, index=True)


class KapiKutusu(Base):
    """Nizamiyedeki "PTS Kapı Kutusu" (2026-10-28, kapi_kutusu/ yazılımı, KC868-A8).
    Kutu, yerdeki döngü dedektörünün "araç var" sinyalini POST /kapi-kutusu/olay
    ile bildirir; PTS bunu kamera okumasıyla eşleştirir, eşleşmezse "okunamayan
    geçiş" açar (bkz. main.py "KAPI KUTUSU"). Bariyer açma, mevcut Bariyer
    ayarlarının HTTP moduyla kutunun /ac adresine yapılır.

    `girisler`: JSON dizi [{"giris": 1, "kamera": "Ana Kapı Çıkış", "yon": "cikis"}];
    yalnız burada eşlenen girişler geçiş sayılır (diğerleri yok sayılır)."""
    __tablename__ = "kapi_kutulari"

    id = Column(Integer, primary_key=True, index=True)
    ad = Column(String(60), nullable=False, unique=True)
    anahtar = Column(String(64), nullable=False)
    girisler = Column(Text, nullable=True)
    aktif = Column(Boolean, default=True)
    son_gorulme = Column(DateTime, nullable=True)
    son_ip = Column(String(45), nullable=True)
    surum = Column(String(20), nullable=True)
    giris_durumu = Column(Integer, nullable=True)   # son bildirilen giriş bit maskesi
    son_acilis = Column(BigInteger, nullable=True)  # kutunun açılış kimliği (yeniden başlayınca değişir)
    son_sira = Column(Integer, default=0)           # bu açılışta işlenen son olay numarası
    olusturma_tarihi = Column(DateTime, default=datetime.now)


class KutuOlayi(Base):
    """Kapı kutusunun bildirdiği bir araç geçişi ve kamera okumasıyla eşleşmesi.
    durum: bekliyor (eşleşme zamanı gelmedi) | eslesti | okunamadi | cozuldu |
    yok_sayildi. Okunamayan geçişin anlık kamera görüntüsü `goruntu_yolu`da."""
    __tablename__ = "kutu_olaylari"

    id = Column(Integer, primary_key=True, index=True)
    kutu_id = Column(Integer, ForeignKey("kapi_kutulari.id"), nullable=False, index=True)
    giris_no = Column(Integer, nullable=False)
    kamera_id = Column(String(64), nullable=False)
    yon = Column(String(10), nullable=False)
    zaman = Column(DateTime, nullable=False, index=True)
    durum = Column(String(15), nullable=False, default="bekliyor", index=True)
    eslesen_kayit_id = Column(Integer, nullable=True, index=True)
    goruntu_yolu = Column(String(255), nullable=True)
    cozen = Column(String(80), nullable=True)
    cozum_zamani = Column(DateTime, nullable=True)
    cozum_kayit_id = Column(Integer, nullable=True)


class NobetNotuOkuma(Base):
    """Bir nöbet notunun kim tarafından, ne zaman "Okudum" denerek okunduğu
    (devir-teslimin kanıtı). Not başına kullanıcı başına en fazla bir satır."""
    __tablename__ = "nobet_notu_okumalari"
    __table_args__ = (UniqueConstraint("not_id", "kullanici_id", name="uq_nobet_notu_okuma"),)

    id = Column(Integer, primary_key=True, index=True)
    not_id = Column(Integer, ForeignKey("nobet_notlari.id"), nullable=False, index=True)
    kullanici_id = Column(Integer, nullable=False, index=True)
    kullanici_adi = Column(String(80), nullable=False)
    okuma_zamani = Column(DateTime, default=datetime.now)

    nobet_notu = relationship("NobetNotu", back_populates="okumalar")


class VardiyaCizelgeDilimi(Base):
    """Vardiya çizelgesi (2026-10-12, kullanıcı isteği; bkz. backend/vardiya_cizelgesi.py):
    bir günün bir dilimi (07-15 sabah, 15-23 akşam, 23-07 gece) ve o dilimde
    nöbette olan vardiya (A/B/C/D). Çizelge kameralarından (Lojman) gelen
    geçişlerin vardiya etiketi giriş/oturum yerine buradan gelir. Gün başına 3
    satır; kaynak "liste" (girilen aylık çizelge) ya da "otomatik" (20 günlük
    döngüden hesaplanan). Kayıtlarla veritabanında EXISTS ile eşleştirilir."""
    __tablename__ = "vardiya_cizelge_dilimleri"
    __table_args__ = (UniqueConstraint("gun", "dilim", name="uq_vardiya_cizelge_dilimi"),)

    id = Column(Integer, primary_key=True, index=True)
    gun = Column(Date, nullable=False, index=True)
    dilim = Column(String(10), nullable=False)
    baslangic = Column(DateTime, nullable=False, index=True)
    bitis = Column(DateTime, nullable=False, index=True)
    vardiya_adi = Column(String(10), nullable=False)
    kaynak = Column(String(10), nullable=False, default="liste")
