// Web panelinin Board4 tema diliyle (bkz. frontend/style.css, 2026-09-26/27
// "Tüm panel (17 sekme)" reskin patch'i) TUTARLI renk paleti -- mobil
// uygulama ayrı bir görsel dil icat etmiyor, aynı marka/renklerle devam
// ediyor. Anlamsal/durum renkleri (rozetler vb.) de web panelle AYNI
// mantıkla ayrı tutuldu: yeşil=yetkili/aktif, kırmızı=yetkisiz/kara liste,
// amber=süresi dolmuş/dikkat.

export const renkler = {
  zeminAcik: "#F4F6F9",
  yuzeyBeyaz: "#FFFFFF",
  yaziKoyu: "#1B2431",
  yaziSoluk: "#5A6472",
  kenarlik: "#E2E6ED",

  lacivert: "#16233A", // sidebar/tab bar
  lacivertAcik: "#24406A", // aktif durum
  vurgu: "#2F6FED", // ana aksan (web panelin yeni #2F6FED'i ile aynı)
  vurguAcik: "#7EA6FF",

  basarili: "#167343",
  basariliZemin: "#E3F5E9",
  tehlike: "#A02B2B",
  tehlikeZemin: "#FBE3E1",
  uyari: "#976B00",
  uyariZemin: "#FFF4D6",
  notr: "#5D7482",
  notrZemin: "#EDF0F2",
} as const;

export const bosluklar = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;

export const yaziBoyutlari = {
  baslik: 22,
  altBaslik: 16,
  govde: 14,
  kucuk: 12,
} as const;
