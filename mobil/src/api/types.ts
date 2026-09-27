// backend/schemas.py'deki gerçek yanıt şekilleriyle BİREBİR eşleşir (bkz.
// KullaniciCevap, KayitCevap, AlarmCevap) -- burada yalnızca mobil
// uygulamanın gerçekten kullandığı alanlar tutuldu, backend'in döndürdüğü
// ekstra alanlar TypeScript'te sorun çıkarmaz (fazlalık alan hatası değil).

export type Rol = "yonetici" | "operatör" | "güvenlik" | "izleyici" | "sakin";

export interface Kullanici {
  id: number;
  kullanici_adi: string;
  rol: Rol;
  aktif: boolean;
}

export interface GirisYaniti {
  token: string;
  kullanici: Kullanici;
}

export interface Istatistik {
  toplam_kayit: number;
  bugunku_kayit: number;
  yetkisiz_giris_denemesi: number;
  aktif_kisi_sayisi: number;
  kara_liste_gecis?: number;
  kara_liste_kayit_sayisi?: number;
}

export interface IceridDurumu {
  iceride_sayisi: number;
}

export interface Kayit {
  id: number;
  plaka_no: string;
  tarih_saat: string;
  kamera_id: string;
  yon: string; // "giris" | "cikis"
  yetki_durumu: string; // "yetkili" | "yetkisiz" | "kara_liste" | "suresi_dolmus" | ...
  kisi_adi?: string | null;
  not_metni?: string | null;
  misafir_adi?: string | null;
}

export interface Alarm {
  id: number;
  kayit_id: number | null;
  plaka_no: string;
  alarm_tipi: string;
  mesaj: string;
  okundu: boolean;
  tarih_saat: string;
}

export class ApiHatasi extends Error {
  status?: number;
  agHatasi?: boolean;
  constructor(mesaj: string, status?: number, agHatasi?: boolean) {
    super(mesaj);
    this.status = status;
    this.agHatasi = agHatasi;
  }
}
