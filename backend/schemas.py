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

    model_config = ConfigDict(from_attributes=True)


class KullaniciOlustur(BaseModel):
    kullanici_adi: str = Field(min_length=3, max_length=80)
    parola: str = Field(min_length=8)
    rol: str = "izleyici"
    # rol="sakin" iken ZORUNLU: bu hesabın hangi Kişi kaydına bağlanacağı
    # (bkz. main.py::kullanici_ekle). Diğer roller için yok sayılır.
    kisi_id: Optional[int] = None

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
    plaka_no: str
    kamera_id: str = "KAMERA-1"
    yon: str = "giris"
    guven_skoru: Optional[float] = None
    # Görevlinin bir aracı elle içeri/dışarı aldığında düşebileceği tek
    # seferlik not (ör. "teslimat aracı, güvenlik onayıyla alındı").
    not_metni: Optional[str] = None


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
    dogrulama_kare_sayisi: Optional[int] = None
    farkli_okuma_sayisi: Optional[int] = None
    not_metni: Optional[str] = None
    manuel_giris: bool = False
    duzenleyen: Optional[str] = None
    duzenleme_tarihi: Optional[datetime] = None

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
    değil -- bu yüzden ayrı bir bayrak gerekiyor)."""
    plaka_no: Optional[str] = None
    yon: Optional[str] = None
    yetki_durumu: Optional[str] = None
    kisi_id: Optional[int] = None
    kisi_id_temizle: bool = False
    not_metni: Optional[str] = None


class KameraYonGuncelle(BaseModel):
    """Var olan bir kameranın yönünü (giriş/çıkış) DEĞİŞTİRİR -- RTSP adresine/
    parolasına dokunmadan (bkz. main.py::kamera_yon_degistir)."""
    yon: str


class KameraRoiGuncelle(BaseModel):
    """Bir kameranın tespit alanını (ROI -- region of interest) kare
    genişliğinin/yüksekliğinin YÜZDESİ (0-100, çözünürlükten bağımsız olsun
    diye piksel değil yüzde) olarak sınırlar. Örn. giriş ve çıkış
    kameralarının açıları birbirinin şeridini de görüyorsa, her kamera için
    SADECE kendi şeridine denk gelen bölge tanımlanır; bu bölgenin dışındaki
    tespitler oy birikimine hiç girmez (bkz.
    camera_reader.py::_kutu_roi_icinde_mi, main.py::kamera_roi_guncelle).
    `temizle=True` gönderilirse x1/y1/x2/y2 yok sayılır ve sınır tamamen
    kaldırılır (kare tamamı tekrar geçerli olur)."""
    x1: Optional[float] = None
    y1: Optional[float] = None
    x2: Optional[float] = None
    y2: Optional[float] = None
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


class DogrulukTestiIstegi(BaseModel):
    """/sistem/dogruluk-testi isteği — bkz. camera_reader.py::toplu_dogruluk_testi.
    Yalnızca sunucudaki (kamerayı çalıştıran bilgisayardaki) bir klasör yoluna
    işaret eder; dosya YÜKLEMESİ değildir (fotoğraflar zaten Dahua NVR'dan
    dışa aktarılıp bir klasöre konmuş olmalı)."""
    klasor: str
    min_guven_skoru: Optional[float] = None
    kontrast_iyilestir: bool = False
