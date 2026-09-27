import React from "react";
import { StyleSheet, Text, View } from "react-native";
import type { Kayit } from "../api/types";
import { renkler, yaziBoyutlari } from "../theme";
import { durumEtiketiAl, durumRengiAl } from "./durumRozeti";

function saatFormatla(isoTarih: string): string {
  try {
    return new Date(isoTarih).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return isoTarih;
  }
}

export default function KayitRow({ kayit }: { kayit: Kayit }) {
  const renk = durumRengiAl(kayit.yetki_durumu);
  return (
    <View style={styles.satir}>
      <View style={{ flex: 1 }}>
        <Text style={styles.plaka}>{kayit.plaka_no}</Text>
        <Text style={styles.altBilgi}>
          {kayit.kamera_id} · {kayit.yon === "giris" ? "Giriş" : "Çıkış"}
          {kayit.kisi_adi ? ` · ${kayit.kisi_adi}` : ""}
          {kayit.misafir_adi ? ` · ${kayit.misafir_adi}` : ""}
        </Text>
      </View>
      <View style={[styles.rozet, { backgroundColor: renk.zemin }]}>
        <Text style={[styles.rozetYazi, { color: renk.yazi }]}>{durumEtiketiAl(kayit.yetki_durumu)}</Text>
      </View>
      <Text style={styles.saat}>{saatFormatla(kayit.tarih_saat)}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  satir: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderBottomWidth: 1,
    borderBottomColor: renkler.kenarlik,
    gap: 10,
  },
  plaka: { fontSize: yaziBoyutlari.govde, fontWeight: "700", color: renkler.yaziKoyu },
  altBilgi: { fontSize: yaziBoyutlari.kucuk, color: renkler.yaziSoluk, marginTop: 2 },
  rozet: { borderRadius: 999, paddingVertical: 3, paddingHorizontal: 8 },
  rozetYazi: { fontSize: 11, fontWeight: "600" },
  saat: { fontSize: yaziBoyutlari.kucuk, color: renkler.yaziSoluk, width: 44, textAlign: "right" },
});
