import { apiCagir } from "./client";
import type { Alarm, GirisYaniti, IceridDurumu, Istatistik, Kayit, Kullanici } from "./types";

export function girisYap(kullaniciAdi: string, parola: string): Promise<GirisYaniti> {
  return apiCagir<GirisYaniti>("/auth/giris", {
    method: "POST",
    body: { kullanici_adi: kullaniciAdi, parola },
    tokenGerekmez: true,
  });
}

export function cikisYap(): Promise<{ mesaj: string }> {
  return apiCagir("/auth/cikis", { method: "POST" });
}

export function mevcutKullanici(): Promise<Kullanici> {
  return apiCagir<Kullanici>("/auth/me");
}

export function istatistikGetir(): Promise<Istatistik> {
  return apiCagir<Istatistik>("/kayitlar/istatistik");
}

export function iceridDurumuGetir(): Promise<IceridDurumu> {
  return apiCagir<IceridDurumu>("/araclar/iceridedurum");
}

export function sonKayitlariGetir(limit = 20, plaka?: string): Promise<Kayit[]> {
  const parametreler = new URLSearchParams({ limit: String(limit) });
  if (plaka) parametreler.set("plaka", plaka);
  return apiCagir<Kayit[]>(`/kayitlar?${parametreler.toString()}`);
}

export function alarmlariGetir(sadeceAcik = true, limit = 30): Promise<Alarm[]> {
  const parametreler = new URLSearchParams({
    sadece_acik: String(sadeceAcik),
    limit: String(limit),
  });
  return apiCagir<Alarm[]>(`/alarmlar?${parametreler.toString()}`);
}

export function alarmOkunduIsaretle(alarmId: number): Promise<Alarm> {
  return apiCagir<Alarm>(`/alarmlar/${alarmId}/okundu`, { method: "PATCH" });
}

export function tumAlarmlariOkunduIsaretle(): Promise<unknown> {
  return apiCagir("/alarmlar/tumu-okundu", { method: "POST" });
}

export function pushTokenKaydet(expoPushToken: string, platform: string): Promise<unknown> {
  return apiCagir("/push/kaydet", {
    method: "POST",
    body: { expo_push_token: expoPushToken, platform },
  });
}

export function pushTokenSil(expoPushToken: string): Promise<unknown> {
  return apiCagir("/push/kaydi-sil", {
    method: "POST",
    body: { expo_push_token: expoPushToken },
  });
}
