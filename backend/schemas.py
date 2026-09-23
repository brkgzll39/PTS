import json
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime
from typing import Optional, List

GECERLI_TIPLER = ("abone", "personel", "ziyaretci")
# "sakin": bir Kişi kaydına bağlı, yalnızca kendi araç/geçmiş bilgisine
# erişebilen öz-hizmet giriş hesabı (bkz. main.py::_personel_girisi_gerekli
# ve /sakin/... uç noktaları, 2026-09-17 notu).
# "güvenlik": güvenlik personeli hesabı (bkz. 2026-09-18 "Güvenlik Personeli
# Vardiya Filtresi" notu, README) -- yetki/görünürlük açısından "operatör"
# ile BİREBİR AYNI (bkz. main.py::_rol_dogrula ve frontend/app.js::ROL_SEVIYE),
# TEK farkı kayıtlar listesinin/raporların kendi vardiya saatleriyle
# filtrelenmesidir (bkz. main.py::_guvenlik_kayit_filtresi_uygula).
GECERLI_ROLLER = ("yonetici", "operatör", "güvenlik", "izleyici", "sakin")


def plaka_normalize(v: str) -> str:
    """Girdi plaka numarasını normalize eder: baş/son boşluk temizlenir, büyük
    harfe çevrilir ve Türk plaka formatında ASLA yer almayan karakterler
    (harf/rakam/boşluk dışında her şey) atılır.

    ÖNEMLİ — bu, main.py'deki otomatik-kayıt yolunda (POST /kayitlar/otomatik
    ve toplu içe aktarma) zaten uygulanan `re.sub(r"[^A-Za-z0-9 ]", "", ...)`
    ile BİREBİR AYNI kuraldır. Önceden bu şemadaki `plaka_no` alanları yalnızca
    `.upper().strip()` yapıyordu — karakter kısıtlaması YOKTU. Bu hem iki farklı
    giriş yolu arasında tutarsız bir normalizasyona (aynı plaka farklı şekilde
    saklanabilir) hem de daha ciddisi bir stored-XSS açığına yol açıyordu:
    kara listeye/kişiye `plaka_no="x');alert(1)//"` gibi bir değer eklenip,
    frontend'de bu değer `onclick="...('${escapeHtml(plaka)}')"` biçiminde bir
    HTML attribute'u içine gömüldüğünde (attribute HTML-decode edildikten
    SONRA JS olarak yorumlanır) çalıştırılabiliyordu. Artık tüm giriş
    noktalarında AYNI (tek doğru kaynak) kural zorunlu kılınıyor.
    """
    temiz = re.sub(r"[^A-Za-z0-9 ]", "", v).strip().upper()
    if not temiz:
        raise ValueError("plaka_no geçerli karakter içermiyor (yalnızca harf, rakam ve boşluk kabul edilir)")
    return temiz


class SiteOlustur(BaseModel):
    ad: str
    aciklama: Optional[str] = None


class SiteCevap(BaseModel):
    id: int
    ad: str
    aciklama: Optional[str] = None
    aktif: bool
    olusturma_tarihi: datetime

    model_config = ConfigDict(from_attributes=True)


class NoktaOlustur(BaseModel):
    site_id: int
    ad: str
    yon: str = "giris"
    kamera_id: Optional[str] = None
    bariyer_id: Optional[int] = None
    aciklama: Optional[str] = None


class NoktaCevap(BaseModel):
    id: int
    site_id: int
    ad: str
    yon: str
    kamera_id: Optional[str] = None
    bariyer_id: Optional[int] = None
    aciklama: Optional[str] = None
    aktif: bool
    olusturma_tarihi: datetime
    # ORM sütunu DEĞİLDİR -- main.py::noktalari_listele tarafından, "id vs ad"
    # hata sınıfını (bkz. _kullanicinin_izinli_kamera_adlari'nin docstring'i)
    # istemci tarafına da taşımadan önlemek için doldurulur. `kamera_id` bu
    # noktaya bağlı kameranın "id"si iken, gerçek geçiş kayıtları (Kayit.
    # kamera_id) kameranın "ad" alanıyla damgalanır -- frontend bir olayın
    # hangi Nokta'ya ait olduğunu bulurken (bkz. app.js::olayDetayAc) "id"yi
    # DEĞİL, bu alanı `kayit.kamera_id` ile karşılaştırmalıdır.
    kamera_adi: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class IlkYoneticiOlustur(BaseModel):
    kullanici_adi: str
    parola: str


class GirisIstegi(BaseModel):
    kullanici_adi: str
    parola: str


class LisansAktivasyonIstegi(BaseModel):
    anahtar: str


class KullaniciCevap(BaseModel):
    id: int
    kullanici_adi: str
    rol: str
    aktif: bool
    son_giris: Optional[datetime] = None
    olusturma_tarihi: Optional[datetime] = None
    # Yalnızca rol="sakin" hesaplarında dolu (bkz. models.Kullanici.kisi_id).
    kisi_id: Optional[int] = None
    # "Nizamiye Bazlı Kamera Erişimi" (2026-09-21): None = kısıtlama yok (tüm
    # kameraları görebilir); DB'de JSON dizi (string) olarak saklanıyor (bkz.
    # main.py::_kullanicinin_izinli_kameralari) -- aşağıdaki validator ham
    # string'i response'ta gerçek bir liste olarak döndürmek için çözer.
    kamera_erisim_listesi: Optional[List[str]] = None
    # "Vardiya Grupları" (2026-09-21): None = bu hesap adlandırılmış bir
    # vardiya grubuna atanmamış (bkz. main.py::_kullanicinin_vardiya_pencereleri
    # ve models.Kullanici.vardiya_adi). Dolu ise (ör. "A"), AYNI değeri
    # taşıyan tüm hesapların vardiya oturumları görünürlük açısından
    # BİRLEŞİK sayılır.
    vardiya_adi: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("kamera_erisim_listesi", mode="before")
    @classmethod
    def _kamera_erisim_listesini_coz(cls, v):
        if v is None or isinstance(v, list):
            return v
        try:
            cozulen = json.loads(v)
        except (ValueError, TypeError):
            return None
        return cozulen if isinstance(cozulen, list) else None


class KullaniciOlustur(BaseModel):
    kullanici_adi: str = Field(min_length=3, max_length=80)
    parola: str = Field(min_length=8)
    rol: str = "izleyici"
    # rol="sakin" iken ZORUNLU: bu hesabın hangi Kişi kaydına bağlanacağı
    # (bkz. main.py::kullanici_ekle). Diğer roller için yok sayılır.
    kisi_id: Optional[int] = None
    # None = kısıtlama yok (varsayılan, geriye dönük uyumlu); dolu bir liste
    # (BOŞ liste dahil) verilirse hesap SADECE o kamera id'lerini görebilir
    # (bkz. main.py::_kamera_id_listesini_dogrula -- geçersiz id'ler 400 ile
    # reddedilir).
    kamera_erisim_listesi: Optional[List[str]] = None
    # "Vardiya Grupları" (2026-09-21): boş/None = adlandırılmış bir vardiya
    # grubuna atanmaz (bkz. main.py::kullanici_ekle -- baş/son boşluk
    # temizlenir, büyük harfe çevrilir; arayüz A/B/C/D önerir ama serbest
    # metindir).
    vardiya_adi: Optional[str] = Field(None, max_length=20)

    @field_validator("rol")
    @classmethod
    def rol_kontrol(cls, v):
        if v not in GECERLI_ROLLER:
            raise ValueError(f"Geçerli roller: {GECERLI_ROLLER}")
        return v


class KullaniciGuncelle(BaseModel):
    rol: Optional[str] = None
    aktif: Optional[bool] = None
    parola: Optional[str] = Field(None, min_length=8)
    # Yalnızca rol="sakin"ya geçilirken/geçiliyken anlamlı; bkz.
    # main.py::kullanici_guncelle. None = "değiştirme" (diğer alanlarla aynı
    # kural), bağlantıyı kaldırmak için bu uç nokta kullanılmaz.
    kisi_id: Optional[int] = None
    # None = değiştirme (diğer alanlarla aynı kural). Bir liste (BOŞ liste
    # DAHİL) gönderilirse kısıtlama TAM OLARAK o listeye ayarlanır. Kısıtlamayı
    # tamamen KALDIRIP hesabı yeniden "tüm kameralar" durumuna getirmek için
    # `kamera_erisimi_temizle=true` gönderilir (bkz. main.py::
    # kamera_roi_guncelle'deki aynı "temizle" deseniyle tutarlı).
    kamera_erisim_listesi: Optional[List[str]] = None
    kamera_erisimi_temizle: bool = False
    # "Vardiya Grupları" (2026-09-21): None = değiştirme (diğer alanlarla
    # aynı kural). Boş string (baş/son boşluk temizlendikten sonra) gönderilirse
    # atama TAMAMEN KALDIRILIR (NULL'a döner) -- kamera_erisim_listesi'ndeki
    # gibi ayrı bir "temizle" bayrağına GEREK YOK, çünkü boş bir vardiya adı
    # zaten geçerli bir değer DEĞİLDİR (bkz. main.py::kullanici_guncelle).
    vardiya_adi: Optional[str] = Field(None, max_length=20)

    @field_validator("rol")
    @classmethod
    def rol_kontrol(cls, v):
        if v is not None and v not in GECERLI_ROLLER:
            raise ValueError(f"Geçerli roller: {GECERLI_ROLLER}")
        return v


class VardiyaOturumuCevap(BaseModel):
    """Bir güvenlik personelinin ÖZ-HİZMET vardiya oturumu (bkz.
    models.VardiyaOturumu, main.py::/vardiya-oturumlari). Elle oluşturma
    şeması YOK -- oturumlar yalnızca giriş/çıkış (bkz. main.py::giris_yap,
    ::cikis_yap) ile otomatik açılıp kapanır; yönetici yalnızca LİSTELEYEBİLİR
    ve açık kalmış bir oturumu SONLANDIRABİLİR (bkz. /vardiya-oturumlari/{id}/sonlandir)."""
    id: int
    kullanici_id: int
    giris_zamani: datetime
    cikis_zamani: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class KisiPlakaOlustur(BaseModel):
    plaka_no: str = Field(min_length=1, max_length=15)
    aciklama: Optional[str] = Field(None, max_length=100)

    @field_validator("plaka_no")
    @classmethod
    def plaka_buyuk_harf(cls, v):
        return plaka_normalize(v)


class KisiPlakaCevap(BaseModel):
    id: int
    kisi_id: int
    plaka_no: str
    aciklama: Optional[str] = None
    aktif: bool
    olusturma_tarihi: datetime

    model_config = ConfigDict(from_attributes=True)


class KisiOlustur(BaseModel):
    ad_soyad: str = Field(min_length=1, max_length=100)
    plaka_no: str = Field(min_length=1, max_length=15)
    tip: str
    telefon: Optional[str] = Field(None, max_length=20)
    daire_departman: Optional[str] = Field(None, max_length=50)
    aciklama: Optional[str] = None
    bitis_tarihi: Optional[datetime] = None
    giris_saati_baslangic: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    giris_saati_bitis: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    izin_verilen_gunler: Optional[str] = Field(None, max_length=20)  # "0,1,2,3,4"

    @field_validator("plaka_no")
    @classmethod
    def plaka_buyuk_harf(cls, v):
        return plaka_normalize(v)

    @field_validator("tip")
    @classmethod
    def tip_kontrol(cls, v):
        if v not in GECERLI_TIPLER:
            raise ValueError(f"tip şunlardan biri olmalı: {GECERLI_TIPLER}")
        return v


class KisiGuncelle(BaseModel):
    ad_soyad: Optional[str] = Field(None, min_length=1, max_length=100)
    plaka_no: Optional[str] = Field(None, min_length=1, max_length=15)
    tip: Optional[str] = None
    telefon: Optional[str] = Field(None, max_length=20)
    daire_departman: Optional[str] = Field(None, max_length=50)
    aciklama: Optional[str] = None
    aktif: Optional[bool] = None
    bitis_tarihi: Optional[datetime] = None
    giris_saati_baslangic: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    giris_saati_bitis: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    izin_verilen_gunler: Optional[str] = Field(None, max_length=20)

    @field_validator("plaka_no")
    @classmethod
    def plaka_buyuk_harf(cls, v):
        return plaka_normalize(v) if v is not None else v

    @field_validator("tip")
    @classmethod
    def tip_kontrol(cls, v):
        if v is not None and v not in GECERLI_TIPLER:
            raise ValueError(f"tip şunlardan biri olmalı: {GECERLI_TIPLER}")
        return v


class KisiCevap(BaseModel):
    id: int
    ad_soyad: str
    plaka_no: str
    tip: str
    telefon: Optional[str] = None
    daire_departman: Optional[str] = None
    aciklama: Optional[str] = None
    aktif: bool
    baslangic_tarihi: Optional[datetime] = None
    bitis_tarihi: Optional[datetime] = None
    giris_saati_baslangic: Optional[str] = None
    giris_saati_bitis: Optional[str] = None
    izin_verilen_gunler: Optional[str] = None
    olusturma_tarihi: datetime
    ek_plakalar: List[KisiPlakaCevap] = []
    # 2026-09-22 kullanıcı isteği: "Kişiler" ekranındaki listeye aracın geçiş
    # geçmişinden özet bilgi eklendi -- bunlar Kisi tablosunda GERÇEK bir
    # sütun DEĞİL, main.py::_kisilerin_gecis_ozetini_ekle tarafından bu
    # kişinin TÜM plakalarıyla (ana + ek_plakalar) eşleşen Kayit satırlarından
    # (Kayit.kisi_id üzerinden) hesaplanıp yanıt döndürülmeden hemen önce
    # ORM nesnesine geçici olarak eklenen alanlardır (from_attributes=True
    # sayesinde burada otomatik okunur). Bu kişiye ait hiç geçiş kaydı yoksa
    # hepsi None kalır.
    ilk_gecis: Optional[datetime] = None
    son_gecis: Optional[datetime] = None
    son_yetki_durumu: Optional[str] = None
    son_not_metni: Optional[str] = None
    son_not_ekleyen: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class KaraListesiOlustur(BaseModel):
    plaka_no: str = Field(min_length=1, max_length=15)
    sebep: Optional[str] = Field(None, max_length=255)

    @field_validator("plaka_no")
    @classmethod
    def plaka_buyuk_harf(cls, v):
        return plaka_normalize(v)


class KaraListesiCevap(BaseModel):
    id: int
    plaka_no: str
    sebep: Optional[str] = None
    ekleyen: Optional[str] = None
    aktif: bool
    olusturma_tarihi: datetime

    model_config = ConfigDict(from_attributes=True)


class KayitManuel(BaseModel):
    # GÜVENLİK/KARARLILIK DÜZELTMESİ (2026-09-22 kod incelemesi): bu alan
    # önceki gibi çıplak `str` bırakılmıştı -- diğer TÜM plaka_no alanlarının
    # (KisiOlustur, KisiGuncelle, KisiPlakaOlustur, KaraListesiOlustur) aksine
    # ne bir uzunluk sınırı ne de plaka_normalize() doğrulayıcısı vardı.
    # main.py'deki manuel `re.sub(...).strip().upper()` temizliği geçersiz
    # karakterleri atıyor ama ASLA KISALTMIYOR -- gerçek üretim ortamı olan
    # SQL Server'da (bkz. README, models.py::plaka_no = Column(String(15)))
    # 15 karakterden uzun bir NVARCHAR(15) INSERT'i, burada YAKALANMAYAN bir
    # veritabanı hatasıyla 500'e düşer: sıradan bir yapıştırma/yazım hatası,
    # "kayıt eklenemedi" gibi temiz bir 400 yerine opak bir sunucu hatasına
    # dönüşürdü. Artık diğer tüm şemalarla AYNI kural uygulanıyor.
    plaka_no: str = Field(min_length=1, max_length=15)
    kamera_id: str = "KAMERA-1"
    yon: str = "giris"
    guven_skoru: Optional[float] = None
    # Görevlinin bir aracı elle içeri/dışarı aldığında düşebileceği tek
    # seferlik not (ör. "teslimat aracı, güvenlik onayıyla alındı").
    not_metni: Optional[str] = None
    # Kişiye (Kisi) bağlı olmayan bir misafirin ad soyadı -- bkz.
    # models.Kayit.misafir_adi'nin docstring'i.
    misafir_adi: Optional[str] = Field(None, max_length=100)

    @field_validator("plaka_no")
    @classmethod
    def plaka_buyuk_harf(cls, v):
        return plaka_normalize(v)

    @field_validator("yon")
    @classmethod
    def yon_kontrol(cls, v):
        # 2026-09-22 kod incelemesi: kayit_duzenle (PATCH) zaten "giris"/
        # "cikis" dışını reddediyordu (main.py) ama kayıt OLUŞTURMA yolu
        # (bu şema) hiç doğrulamıyordu -- geçersiz bir yön ("IN" gibi) hatasız
        # kaydedilip vardiya/rapor/otomatik-bariyer-açma mantığının sessizce
        # yanlış davranmasına yol açabiliyordu.
        if v not in ("giris", "cikis"):
            raise ValueError("yon 'giris' veya 'cikis' olmalı")
        return v


class KayitCevap(BaseModel):
    id: int
    plaka_no: str
    tarih_saat: datetime
    kamera_id: str
    yon: str
    goruntu_yolu: Optional[str] = None
    guven_skoru: Optional[float] = None
    ham_plaka_metni: Optional[str] = None
    yetki_durumu: str
    kisi_id: Optional[int] = None
    kisi_tip_anlik: Optional[str] = None
    # 2026-09-22 kullanıcı geri bildirimi: "kişi eşleştirmesi ... Hasan ÇETİN
    # seçtim fakat herhangi bir yerde gözükmüyor" -- bu bir ORM sütunu
    # DEĞİLDİR, bkz. main.py::_kayitlara_kisi_adini_ekle'nin docstring'i.
    kisi_adi: Optional[str] = None
    dogrulama_kare_sayisi: Optional[int] = None
    farkli_okuma_sayisi: Optional[int] = None
    not_metni: Optional[str] = None
    misafir_adi: Optional[str] = None
    # Arvento entegrasyonu (2026-09-23) -- bkz. models.Kayit.surucu_adi'nin
    # docstring'i. Bu ALAN, misafir_adi/kisi_adi'nin aksine, panelden ELLE
    # DEĞİL yalnızca Arvento webhook'undan otomatik doldurulur; bu yüzden
    # KayitManuel/KayitDuzenle şemalarında YOKTUR (kasıtlı).
    surucu_adi: Optional[str] = None
    manuel_giris: bool = False
    duzenleyen: Optional[str] = None
    duzenleme_tarihi: Optional[datetime] = None
    # "Vardiya Grupları" (2026-09-21): bu bir ORM sütunu DEĞİLDİR -- bkz.
    # main.py::_kayitlarin_vardiya_adlarini_ekle (bellek-içi olarak hesaplanıp
    # yalnızca ilgili uçlarda atanır; atanmadığı uçlarda `from_attributes`
    # sorunsuzca bu varsayılan `None`a düşer). Bu kaydın gerçekleştiği anda
    # AÇIK olan adlandırılmış vardiya oturumlarının (ör. "A", birden fazlaysa
    # "A/B") adı -- Kayıtlar ekranındaki "Vardiya" sütunu/filtresi ve Plaka
    # Analizi için.
    vardiya_adi: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("manuel_giris", mode="before")
    @classmethod
    def manuel_giris_none_ise_false_say(cls, v):
        """SAVUNMA KATMANI (2026-09-17): bu sütun sonradan ALTER TABLE ile
        eklendiği için -- ve SQL Server'da (SQLite'ın aksine) bir DEFAULT'lu
        ALTER TABLE, "WITH VALUES" açıkça verilmedikçe TABLODA HALİHAZIRDA VAR
        OLAN satırları NULL bırakıyor -- canlı bir veritabanında bu alan hâlâ
        NULL olan eski kayıtlarla karşılaşılabilir (bkz. main.py::
        _veritabani_migrasyon'daki UPDATE ... WHERE manuel_giris IS NULL,
        kök nedeni orada düzeltiyor). `bool` alanı Optional olmadığından
        Pydantic bunu doğrulayamayıp tüm /kayitlar isteğini 500'e düşürüyordu;
        burada None açıkça False'a çevrilerek bu uç noktalar migrasyon
        adımından bağımsız olarak da kırılmaz hale getiriliyor."""
        return False if v is None else v


class KayitDuzenle(BaseModel):
    """Panelden mevcut bir geçiş kaydının tam düzenlenmesi (bkz.
    main.py::kayit_duzenle). Tüm alanlar opsiyoneldir -- sadece gönderilenler
    değiştirilir. `kisi_id_temizle=True` kişi eşleştirmesini kaldırır (aksi
    halde `kisi_id=None` göndermek "değiştirme" anlamına gelir, kaldırma
    değil -- bu yüzden ayrı bir bayrak gerekiyor).

    2026-09-22 kod incelemesi: plaka_no artık diğer tüm plaka_no alanlarıyla
    (KisiOlustur/KisiGuncelle/KisiPlakaOlustur/KayitManuel) TUTARLI şekilde
    Field(max_length=15) + plaka_normalize() ile doğrulanıyor -- bkz.
    KayitManuel'in aynı düzeltmeyi açıklayan yorumu. main.py::kayit_duzenle
    zaten yon/yetki_durumu için kendi doğrulamasını yapıyor, o kısım
    değiştirilmedi."""
    plaka_no: Optional[str] = Field(None, min_length=1, max_length=15)
    yon: Optional[str] = None
    yetki_durumu: Optional[str] = None
    kisi_id: Optional[int] = None
    kisi_id_temizle: bool = False
    not_metni: Optional[str] = None
    misafir_adi: Optional[str] = Field(None, max_length=100)

    @field_validator("plaka_no")
    @classmethod
    def plaka_buyuk_harf(cls, v):
        return plaka_normalize(v) if v is not None else v


class KameraYonGuncelle(BaseModel):
    """Var olan bir kameranın yönünü (giriş/çıkış) DEĞİŞTİRİR -- RTSP adresine/
    parolasına dokunmadan (bkz. main.py::kamera_yon_degistir)."""
    yon: str


class KameraRoiNoktasi(BaseModel):
    """Serbest çizim (polygon) ROI'nin tek bir köşe noktası -- kare
    genişliğinin/yüksekliğinin YÜZDESİ (0-100) cinsinden."""
    x: float
    y: float


class KameraRoiGuncelle(BaseModel):
    """Bir kameranın tespit alanını (ROI -- region of interest) kare
    genişliğinin/yüksekliğinin YÜZDESİ (0-100, çözünürlükten bağımsız olsun
    diye piksel değil yüzde) olarak sınırlar. Örn. giriş ve çıkış
    kameralarının açıları birbirinin şeridini de görüyorsa, her kamera için
    SADECE kendi şeridine denk gelen bölge tanımlanır; bu bölgenin dışındaki
    tespitler oy birikimine hiç girmez (bkz.
    camera_reader.py::_kutu_roi_icinde_mi, main.py::kamera_roi_guncelle).

    İKİ biçimden biri gönderilir:
    - Dikdörtgen (eski/varsayılan): x1/y1/x2/y2 (x1<x2, y1<y2).
    - Serbest çizim / polygon (2026-09-20): `polygon` alanında en az 3
      {"x","y"} noktası -- kullanıcı geri bildirimi ("kare seçimde bazen
      farklı yönden geçen araçları da tespit ediyor") üzerine, şeridin gerçek
      hattını takip eden keyfi bir çokgen çizilebilsin diye eklendi (bkz.
      camera_reader.py::_kutu_polygon_icinde_mi).

    `temizle=True` gönderilirse diğer tüm alanlar yok sayılır ve sınır
    tamamen kaldırılır (kare tamamı tekrar geçerli olur)."""
    x1: Optional[float] = None
    y1: Optional[float] = None
    x2: Optional[float] = None
    y2: Optional[float] = None
    polygon: Optional[List[KameraRoiNoktasi]] = None
    temizle: bool = False


class AlarmCevap(BaseModel):
    id: int
    kayit_id: Optional[int] = None
    plaka_no: str
    alarm_tipi: str
    mesaj: str
    okundu: bool
    tarih_saat: datetime

    model_config = ConfigDict(from_attributes=True)


class BariyerAyarlariCevap(BaseModel):
    id: int
    ad: str
    mod: str
    http_url: Optional[str] = None
    http_metot: str
    http_govde: Optional[str] = None
    gpio_pin: Optional[int] = None
    aktif: bool

    model_config = ConfigDict(from_attributes=True)


class BariyerAyarlariGuncelle(BaseModel):
    ad: Optional[str] = None
    mod: Optional[str] = None
    http_url: Optional[str] = None
    http_metot: Optional[str] = None
    http_govde: Optional[str] = None
    gpio_pin: Optional[int] = None
    aktif: Optional[bool] = None


class DenetimKaydiCevap(BaseModel):
    """GET /denetim-kayitlari yanıtı — bkz. models.DenetimKaydi,
    main.py::_denetim_kaydet. Yalnızca yönetici görebilir (hassas
    yönetici işlemlerinin izini taşır)."""
    id: int
    zaman: datetime
    kullanici_adi: str
    eylem: str
    aciklama: str

    model_config = ConfigDict(from_attributes=True)


class ArventoWebhookCevap(BaseModel):
    """POST /entegrasyonlar/arvento/webhook başarılı yanıtı — bkz.
    main.py::arvento_webhook. İstek gövdesi Arvento'nun tam biçimi henüz
    kesinleşmediği için (bkz. main.py'deki ilgili not) sabit bir Pydantic
    şemasıyla DOĞRULANMIYOR; bunun yerine main.py esnek anahtar eşleştirmesi
    yapıp bu şemayla yanıt döner."""
    durum: str
    plaka_no: str
    surucu_adi: str

    model_config = ConfigDict(from_attributes=True)


class DogrulukTestiIstegi(BaseModel):
    """/sistem/dogruluk-testi isteği — bkz. camera_reader.py::toplu_dogruluk_testi.
    Yalnızca sunucudaki (kamerayı çalıştıran bilgisayardaki) bir klasör yoluna
    işaret eder; dosya YÜKLEMESİ değildir (fotoğraflar zaten Dahua NVR'dan
    dışa aktarılıp bir klasöre konmuş olmalı)."""
    klasor: str
    min_guven_skoru: Optional[float] = None
    kontrast_iyilestir: bool = False
