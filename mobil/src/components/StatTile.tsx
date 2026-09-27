import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { renkler, yaziBoyutlari } from "../theme";

interface Props {
  etiket: string;
  deger: number | string;
  vurgu?: "notr" | "tehlike" | "basarili" | "uyari";
}

const ZEMIN: Record<NonNullable<Props["vurgu"]>, string> = {
  notr: renkler.zeminAcik,
  tehlike: renkler.tehlikeZemin,
  basarili: renkler.basariliZemin,
  uyari: renkler.uyariZemin,
};

const YAZI: Record<NonNullable<Props["vurgu"]>, string> = {
  notr: renkler.yaziKoyu,
  tehlike: renkler.tehlike,
  basarili: renkler.basarili,
  uyari: renkler.uyari,
};

export default function StatTile({ etiket, deger, vurgu = "notr" }: Props) {
  return (
    <View style={[styles.kutu, { backgroundColor: ZEMIN[vurgu] }]}>
      <Text style={[styles.deger, { color: YAZI[vurgu] }]}>{deger}</Text>
      <Text style={styles.etiket}>{etiket}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  kutu: {
    flexBasis: "48%",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: renkler.kenarlik,
    paddingVertical: 14,
    paddingHorizontal: 12,
    marginBottom: 12,
  },
  deger: { fontSize: yaziBoyutlari.baslik, fontWeight: "700" },
  etiket: { fontSize: yaziBoyutlari.kucuk, color: renkler.yaziSoluk, marginTop: 4 },
});
