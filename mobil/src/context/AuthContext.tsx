import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { cikisYap as apiCikisYap, girisYap as apiGirisYap, mevcutKullanici } from "../api/pts";
import { sunucuAdresiniKaydet, sunucuAdresiniOku, tokenKaydet, tokenOku, tokenSil } from "../api/client";
import { ApiHatasi, Kullanici } from "../api/types";
import { pushBildirimKaydiniYap } from "../push/registerPushToken";

// Bu mobil uygulama BİLİNÇLİ OLARAK yalnızca "yönetim/raporlama" (salt
// okunur izleme) senaryosu için var (2026-09-27 kullanıcı isteği) -- "sakin"
// öz-hizmet hesapları burada desteklenmiyor (backend zaten
// _personel_girisi_gerekli ile bu hesapları /kayitlar, /alarmlar gibi
// uçlardan reddediyor; burada da erkenden, anlaşılır bir mesajla engellenir).
type Durum = "yukleniyor" | "sunucuGerekli" | "girisGerekli" | "girisYapildi";

interface AuthBaglami {
  durum: Durum;
  kullanici: Kullanici | null;
  sunucuAdresi: string | null;
  sonHata: string | null;
  sunucuAdresiniAyarla: (adres: string) => Promise<void>;
  girisYap: (kullaniciAdi: string, parola: string) => Promise<void>;
  cikisYap: () => Promise<void>;
  sunucuDegistir: () => void;
}

const Baglam = createContext<AuthBaglami | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [durum, setDurum] = useState<Durum>("yukleniyor");
  const [kullanici, setKullanici] = useState<Kullanici | null>(null);
  const [sunucuAdresi, setSunucuAdresi] = useState<string | null>(null);
  const [sonHata, setSonHata] = useState<string | null>(null);

  const baslangicKontrolu = useCallback(async () => {
    const adres = await sunucuAdresiniOku();
    setSunucuAdresi(adres);
    if (!adres) {
      setDurum("sunucuGerekli");
      return;
    }
    const token = await tokenOku();
    if (!token) {
      setDurum("girisGerekli");
      return;
    }
    try {
      const k = await mevcutKullanici();
      if (k.rol === "sakin") {
        // bkz. üstteki not -- bu hesap türü bu uygulamada desteklenmiyor.
        await tokenSil();
        setSonHata("Bu uygulama sakin (öz-hizmet) hesapları için değildir. Lütfen personel hesabıyla giriş yapın.");
        setDurum("girisGerekli");
        return;
      }
      setKullanici(k);
      setDurum("girisYapildi");
    } catch {
      // Token süresi dolmuş/geçersiz -- 8 saatlik ömür (bkz. backend
      // main.py::_token_uret) dolduğunda sessizce giriş ekranına düşer,
      // web panelin _oturumSuresiDoldu'suyla AYNI davranış.
      await tokenSil();
      setDurum("girisGerekli");
    }
  }, []);

  useEffect(() => {
    baslangicKontrolu();
  }, [baslangicKontrolu]);

  const sunucuAdresiniAyarla = useCallback(async (adres: string) => {
    await sunucuAdresiniKaydet(adres);
    setSunucuAdresi(adres.trim().replace(/\/+$/, ""));
    setDurum("girisGerekli");
  }, []);

  const girisYap = useCallback(async (kullaniciAdi: string, parola: string) => {
    setSonHata(null);
    const yanit = await apiGirisYap(kullaniciAdi, parola);
    if (yanit.kullanici.rol === "sakin") {
      throw new ApiHatasi("Bu uygulama sakin (öz-hizmet) hesapları için değildir. Lütfen personel hesabıyla giriş yapın.");
    }
    await tokenKaydet(yanit.token);
    setKullanici(yanit.kullanici);
    setDurum("girisYapildi");
    // Push kaydı LOGIN AKIŞINI BLOKLAMAZ -- bildirim izni reddedilse ya da
    // backend'e kayıt anlık başarısız olsa bile kullanıcı uygulamayı
    // kullanmaya devam edebilmeli (bkz. registerPushToken.ts'in gerekçesi).
    pushBildirimKaydiniYap().catch(() => {});
  }, []);

  const cikisYap = useCallback(async () => {
    try {
      await apiCikisYap();
    } catch {
      // Web panelin oturumKapat'ıyla AYNI ilke: sunucuya ulaşılamasa bile
      // (ağ hatası vb.) yerel çıkış ASLA engellenmez.
    }
    await tokenSil();
    setKullanici(null);
    setDurum("girisGerekli");
  }, []);

  const sunucuDegistir = useCallback(() => {
    // Ayarlar ekranından "Sunucu adresini değiştir" -- mevcut oturumu da
    // sonlandırır çünkü yeni sunucuda aynı token'ın anlamı olmayabilir.
    tokenSil().catch(() => {});
    setKullanici(null);
    setDurum("sunucuGerekli");
  }, []);

  const deger = useMemo<AuthBaglami>(
    () => ({ durum, kullanici, sunucuAdresi, sonHata, sunucuAdresiniAyarla, girisYap, cikisYap, sunucuDegistir }),
    [durum, kullanici, sunucuAdresi, sonHata, sunucuAdresiniAyarla, girisYap, cikisYap, sunucuDegistir]
  );

  return <Baglam.Provider value={deger}>{children}</Baglam.Provider>;
}

export function useAuth(): AuthBaglami {
  const deger = useContext(Baglam);
  if (!deger) throw new Error("useAuth, AuthProvider dışında çağrıldı");
  return deger;
}
