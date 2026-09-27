import * as SecureStore from "expo-secure-store";
import { ApiHatasi } from "./types";

const SUNUCU_ADRESI_ANAHTARI = "pts_sunucu_adresi";
const TOKEN_ANAHTARI = "pts_token";

// SecureStore anahtarları yalnızca [A-Za-z0-9._-] kabul eder -- burada
// sabit, güvenli anahtarlar kullanıldığı için bir sorun yok, ama ileride
// değiştirilirse bu kısıtlama akılda tutulmalı.

export async function sunucuAdresiniOku(): Promise<string | null> {
  return SecureStore.getItemAsync(SUNUCU_ADRESI_ANAHTARI);
}

export async function sunucuAdresiniKaydet(adres: string): Promise<void> {
  // Kullanıcı "http://192.168.1.23:8000" ya da sonunda "/" ile de
  // yazabilir -- ikisini de normalize ediyoruz ki apiCagir'daki
  // birleştirme (`${taban}${yol}`) yanlışlıkla "//kayitlar" üretmesin.
  const temiz = adres.trim().replace(/\/+$/, "");
  await SecureStore.setItemAsync(SUNUCU_ADRESI_ANAHTARI, temiz);
}

export async function tokenOku(): Promise<string | null> {
  return SecureStore.getItemAsync(TOKEN_ANAHTARI);
}

export async function tokenKaydet(token: string): Promise<void> {
  await SecureStore.setItemAsync(TOKEN_ANAHTARI, token);
}

export async function tokenSil(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_ANAHTARI);
}

interface CagriSecenekleri {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  // 401 alındığında oturumu sonlandırma davranışını çağıran taraf (AuthContext)
  // yönetir -- bu dosya kasıtlı olarak React state'ine dokunmuyor.
  tokenGerekmez?: boolean;
}

// frontend/app.js::apiCagir ile AYNI davranış felsefesi: ağ hatası ile
// sunucunun döndürdüğü hata (4xx/5xx) birbirinden AYRI ele alınır, ikisi de
// çağırana anlaşılır bir `ApiHatasi` olarak ulaşır -- ekranlarda "bir şeyler
// ters gitti" gibi belirsiz bir mesaj yerine gerçek nedeni gösterebilmek için.
export async function apiCagir<T>(yol: string, secenekler: CagriSecenekleri = {}): Promise<T> {
  const taban = await sunucuAdresiniOku();
  if (!taban) {
    throw new ApiHatasi("Sunucu adresi ayarlanmamış. Lütfen Ayarlar'dan sunucu adresini girin.");
  }
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (!secenekler.tokenGerekmez) {
    const token = await tokenOku();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let cevap: Response;
  try {
    cevap = await fetch(`${taban}${yol}`, {
      method: secenekler.method || "GET",
      headers,
      body: secenekler.body !== undefined ? JSON.stringify(secenekler.body) : undefined,
    });
  } catch {
    // Sunucuya HİÇ ulaşılamadı -- yanlış IP, sunucu kapalı, telefon farklı
    // bir Wi-Fi ağında, vb. `agHatasi` bayrağı ekranların "sunucuya
    // ulaşılamıyor, adresi/ağı kontrol edin" gibi somut bir mesaj
    // gösterebilmesi için ayrı tutuluyor (bkz. web panelin AYNI deseni).
    throw new ApiHatasi("Sunucuya ulaşılamıyor. Sunucu adresini ve aynı ağda olduğunuzu kontrol edin.", undefined, true);
  }

  if (!cevap.ok) {
    let detay = "İstek başarısız";
    try {
      const govde = await cevap.json();
      if (govde?.detail) detay = String(govde.detail);
    } catch {
      // Gövde JSON değilse (ör. bir ters vekil sunucunun ürettiği HTML hata
      // sayfası) varsayılan mesaj kalır -- kullanıcıya hâlâ bir HTTP durum
      // koduyla anlamlı bir şey söylenebilir.
    }
    throw new ApiHatasi(detay, cevap.status);
  }

  // 204 No Content gibi gövdesiz başarılı yanıtlar da olabilir.
  const metin = await cevap.text();
  return (metin ? JSON.parse(metin) : undefined) as T;
}
