import React from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { renkler } from "../theme";

export default function LoadingView({ mesaj = "Yükleniyor..." }: { mesaj?: string }) {
  return (
    <View style={styles.kapsayici}>
      <ActivityIndicator size="large" color={renkler.vurgu} />
      <Text style={styles.mesaj}>{mesaj}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  kapsayici: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: renkler.zeminAcik, gap: 12 },
  mesaj: { color: renkler.yaziSoluk },
});
