import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { renkler, yaziBoyutlari } from "../theme";

interface Props {
  mesaj: string;
  yenidenDeneOnPress?: () => void;
}

export default function ErrorBanner({ mesaj, yenidenDeneOnPress }: Props) {
  return (
    <View style={styles.kapsayici}>
      <Text style={styles.mesaj}>{mesaj}</Text>
      {yenidenDeneOnPress && (
        <Pressable style={styles.buton} onPress={yenidenDeneOnPress}>
          <Text style={styles.butonYazi}>Yeniden Dene</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  kapsayici: {
    backgroundColor: renkler.tehlikeZemin,
    borderRadius: 12,
    padding: 14,
    margin: 14,
    gap: 8,
  },
  mesaj: { color: renkler.tehlike, fontSize: yaziBoyutlari.govde },
  buton: { alignSelf: "flex-start", backgroundColor: renkler.tehlike, borderRadius: 8, paddingVertical: 6, paddingHorizontal: 12 },
  butonYazi: { color: "#fff", fontWeight: "600", fontSize: yaziBoyutlari.kucuk },
});
