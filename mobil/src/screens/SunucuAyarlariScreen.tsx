import React, { useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { useAuth } from "../context/AuthContext";
import { renkler, yaziBoyutlari } from "../theme";

export default function SunucuAyarlariScreen() {
  const { sunucuAdresiniAyarla, sunucuAdresi } = useAuth();
  const [adres, setAdres] = useState(sunucuAdresi || "http://");
  const [hata, setHata] = useState<string | null>(null);
  const [kaydediliyor, setKaydediliyor] = useState(false);

  async function kaydet() {
    setHata(null);
    const temiz = adres.trim();
    if (!/^https?:\/\/.+/.test(temiz)) {
      setHata('Adres "http://" veya "https://" ile başlamalı, örn. http://192.168.1.23:8000');
      return;
    }
    setKaydediliyor(true);
    try {
      await sunucuAdresiniAyarla(temiz);
    } finally {
      setKaydediliyor(false);
    }
  }

  return (
    <KeyboardAvoidingView style={styles.kapsayici} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.icerik} keyboardShouldPersistTaps="handled">
        <Text style={styles.baslik}>PTS Sunucu Adresi</Text>
        <Text style={styles.aciklama}>
          Panelin çalıştığı bilgisayarın yerel ağ adresini girin (aynı Wi-Fi'da olmalısınız). Bilgisayarda "ipconfig"
          ile bulabilirsiniz -- README'deki "Mobil Uygulama" bölümüne bakın.
        </Text>
        <TextInput
          style={styles.girdi}
          value={adres}
          onChangeText={setAdres}
          placeholder="http://192.168.1.23:8000"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
        />
        {hata && <Text style={styles.hata}>{hata}</Text>}
        <Pressable style={[styles.buton, kaydediliyor && { opacity: 0.6 }]} onPress={kaydet} disabled={kaydediliyor}>
          <Text style={styles.butonYazi}>{kaydediliyor ? "Kontrol ediliyor..." : "Devam Et"}</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  kapsayici: { flex: 1, backgroundColor: renkler.zeminAcik },
  icerik: { flexGrow: 1, justifyContent: "center", padding: 24, gap: 14 },
  baslik: { fontSize: yaziBoyutlari.baslik, fontWeight: "700", color: renkler.yaziKoyu, textAlign: "center" },
  aciklama: { fontSize: yaziBoyutlari.kucuk, color: renkler.yaziSoluk, textAlign: "center", marginBottom: 10 },
  girdi: {
    borderWidth: 1,
    borderColor: renkler.kenarlik,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: yaziBoyutlari.govde,
    backgroundColor: renkler.yuzeyBeyaz,
  },
  hata: { color: renkler.tehlike, fontSize: yaziBoyutlari.kucuk },
  buton: { backgroundColor: renkler.vurgu, borderRadius: 10, paddingVertical: 14, alignItems: "center", marginTop: 8 },
  butonYazi: { color: "#fff", fontWeight: "700", fontSize: yaziBoyutlari.govde },
});
