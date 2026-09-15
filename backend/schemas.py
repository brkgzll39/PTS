from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List

GECERLI_TIPLER = ("abone", "personel", "ziyaretci")
GECERLI_ROLLER = ("yonetici", "operatör", "izleyici")


class SiteOlustur(BaseModel):
    ad: str
    aciklama: Optional[str] = None


class SiteCevap(BaseModel):
    id: int
    ad: str
    aciklama: Optional[str] = None
    aktif: bool
    olusturma_tarihi: datetime

    class Config:
        from_attributes = True


class NoktaOlustur(BaseModel):
    site_id: int
    ad: str
    yon: str = "giris"
    aciklama: Optional[str] = None


class NoktaCevap(BaseModel):
    id: int
    site_id: int
    ad: str
    yon: str
    aciklama: Optional[str] = None
    aktif: bool
    olusturma_tarihi: datetime

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


class KullaniciOlustur(BaseModel):
    kullanici_adi: str = Field(min_length=3, max_length=80)
    parola: str = Field(min_length=8)
    rol: str = "izleyici"

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

    @field_validator("rol")
    @classmethod
    def rol_kontrol(cls, v):
        if v is not None and v not in GECERLI_ROLLER:
            raise ValueError(f"Geçerli roller: {GECERLI_ROLLER}")
        return v


class KisiPlakaOlustur(BaseModel):
    plaka_no: str = Field(min_length=1, max_length=15)
    aciklama: Optional[str] = Field(None, max_length=100)

    @field_validator("plaka_no")
    @classmethod
    def plaka_buyuk_harf(cls, v):
        return v.upper().strip()


class KisiPlakaCevap(BaseModel):
    id: int
    kisi_id: int
    plaka_no: str
    aciklama: Optional[str] = None
    aktif: bool
    olusturma_tarihi: datetime

    class Config:
        from_attributes = True


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
        return v.upper().strip()

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
        return v.upper().strip() if v is not None else v

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

    class Config:
        from_attributes = True


class KaraListesiOlustur(BaseModel):
    plaka_no: str = Field(min_length=1, max_length=15)
    sebep: Optional[str] = Field(None, max_length=255)

    @field_validator("plaka_no")
    @classmethod
    def plaka_buyuk_harf(cls, v):
        return v.upper().strip()


class KaraListesiCevap(BaseModel):
    id: int
    plaka_no: str
    sebep: Optional[str] = None
    ekleyen: Optional[str] = None
    aktif: bool
    olusturma_tarihi: datetime

    class Config:
        from_attributes = True


class KayitManuel(BaseModel):
    plaka_no: str
    kamera_id: str = "KAMERA-1"
    yon: str = "giris"
    guven_skoru: Optional[float] = None


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

    class Config:
        from_attributes = True


class AlarmCevap(BaseModel):
    id: int
    kayit_id: Optional[int] = None
    plaka_no: str
    alarm_tipi: str
    mesaj: str
    okundu: bool
    tarih_saat: datetime

    class Config:
        from_attributes = True


class BariyerAyarlariCevap(BaseModel):
    id: int
    ad: str
    mod: str
    http_url: Optional[str] = None
    http_metot: str
    http_govde: Optional[str] = None
    gpio_pin: Optional[int] = None
    aktif: bool

    class Config:
        from_attributes = True


class BariyerAyarlariGuncelle(BaseModel):
    ad: Optional[str] = None
    mod: Optional[str] = None
    http_url: Optional[str] = None
    http_metot: Optional[str] = None
    http_govde: Optional[str] = None
    gpio_pin: Optional[int] = None
    aktif: Optional[bool] = None
