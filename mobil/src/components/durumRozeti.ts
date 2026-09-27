import { renkler } from "../theme";

// frontend/app.js::durumRozeti ile AYNI renk dili (bkz. o dosyadaki "Yeni
// bir renk dili İCAT EDİLMEDİ" ilkesi) -- mobil tarafta da tekrarlanıyor.
const ETIKETLER: Record<string, string> = {
  yetkili: "Yetkili",
  yetkisiz: "Yetkisiz",
  kara_liste: "Kara Liste",
  suresi_dolmus: "Süresi Dolmuş",
};

const RENKLER: Record<string, { zemin: string; yazi: string }> = {
  yetkili: { zemin: renkler.basariliZemin, yazi: renkler.basarili },
  yetkisiz: { zemin: renkler.tehlikeZemin, yazi: renkler.tehlike },
  kara_liste: { zemin: renkler.tehlikeZemin, yazi: renkler.tehlike },
  suresi_dolmus: { zemin: renkler.uyariZemin, yazi: renkler.uyari },
};

export function durumEtiketiAl(durum: string): string {
  return ETIKETLER[durum] || durum;
}

export function durumRengiAl(durum: string): { zemin: string; yazi: string } {
  return RENKLER[durum] || { zemin: renkler.notrZemin, yazi: renkler.notr };
}
