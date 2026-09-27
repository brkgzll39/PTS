import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import type { Alarm } from "../api/types";
import { renkler, yaziBoyutlari } from "../theme";

const ALARM_ETIKETLERI: Record<string, string> = {
  yetkisiz: "Yetkisiz araç",
  kara_liste: "Kara liste",
  suresi_dolmus: "Süresi dolmuş",
  supheli_arac: "Şüpheli araç",
  bariyer_hatasi: "Bariyer hatası",
  kamera_arizasi: "Kamera arızası",
  disk_hatasi: "Disk hatası",
  disk_doluyor: "Disk doluluk uyarısı",
  yedek_bozuk: "Otomatik yedek bozuk",
};

function zamanFormatla(isoTarih: string): string {
  try {
    return new Date(isoTarih).toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch {
    return isoTarih;
  }
}

interface Props {
  alarm: Alarm;
  onOkunduIsaretle?: (alarmId: number) => void;
}

export default function AlarmRow({ alarm, onOkunduIsaretle }: Props) {
  return (
    <View style={[styles.satir, alarm.okundu && styles.okunmus]}>
      <View style={{ flex: 1 }}>
        <Text style={styles.tip}>{ALARM_ETIKETLERI[alarm.alarm_tipi] || alarm.alarm_tipi}</Text>
        <Text style={styles.mesaj} numberOfLines={2}>
          {alarm.plaka_no ? `${alarm.plaka_no} — ` : ""}
          {alarm.mesaj}
        </Text>
        <Text style={styles.zaman}>{zamanFormatla(alarm.tarih_saat)}</Text>
      </View>
      {!alarm.okundu && onOkunduIsaretle && (
        <Pressable style={styles.buton} onPress={() => onOkunduIsaretle(alarm.id)} hitSlop={8}>
          <Text style={styles.butonYazi}>Okundu</Text>
        </Pressable>
      )}
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
    borderLeftWidth: 4,
    borderLeftColor: renkler.tehlike,
    gap: 10,
  },
  okunmus: { borderLeftColor: renkler.kenarlik, opacity: 0.6 },
  tip: { fontSize: yaziBoyutlari.govde, fontWeight: "700", color: renkler.yaziKoyu },
  mesaj: { fontSize: yaziBoyutlari.kucuk, color: renkler.yaziSoluk, marginTop: 2 },
  zaman: { fontSize: 11, color: renkler.yaziSoluk, marginTop: 4 },
  buton: {
    backgroundColor: renkler.vurgu,
    borderRadius: 8,
    paddingVertical: 6,
    paddingHorizontal: 10,
  },
  butonYazi: { color: "#fff", fontSize: 11, fontWeight: "600" },
});
