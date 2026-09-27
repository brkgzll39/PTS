import React, { useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { useAuth } from "../context/AuthContext";
import { renkler, yaziBoyutlari } from "../theme";

export default function GirisScreen() {
  const { girisYap, sunucuDegistir, sunucuAdresi, sonHata } = useAuth();
  const [kullaniciAdi, setKullaniciAdi] = useState("");
  const [parola, setParola] = useState("");
  const [hata, setHata] = useState<string | null>(sonHata);
  const [gonderiliyor, setGonderiliyor] = useState(false);

  async function gonder() {
    setHata(null);
    if (!kullaniciAdi.trim() || !parola) {
      setHata("Kullanıcı adı ve parola gerekli");
      return;
    }
    setGonderiliyor(true);
    try {
      await girisYap(kullaniciAdi.trim(), parola);
    } catch (e) {
      setHata((e as Error).message || "Giriş başarısız");
    } finally {
      setGonderiliyor(false);
    }
  }

  return (
    <KeyboardAvoidingView style={styles.kapsayici} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.icerik} keyboardShouldPersistTaps="handled">
        <Text style={styles.baslik}>TPAO PTS</Text>
        <Text style={styles.altBaslik}>Yönetim / Raporlama Girişi</Text>
        <Text style={styles.sunucu}>{sunucuAdresi}</Text>

        <TextInput
          style={styles.girdi}
          value={kullaniciAdi}
          onChangeText={setKullaniciAdi}
          placeholder="Kullanıcı adı"
          autoCapitalize="none"
          autoCorrect={false}
        />
        <TextInput
          style={styles.girdi}
          value={parola}
          onChangeText={setParola}
          placeholder="Parola"
          secureTextEntry
        />
        {hata && <Text style={styles.hata}>{hata}</Text>}
        <Pressable style={[styles.buton, gonderiliyor && { opacity: 0.6 }]} onPress={gonder} disabled={gonderiliyor}>
          <Text style={styles.butonYazi}>{gonderiliyor ? "Giriş yapılıyor..." : "Giriş Yap"}</Text>
        </Pressable>
        <Pressable onPress={sunucuDegistir}>
          <Text style={styles.linkYazi}>Sunucu adresini değiştir</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  kapsayici: { flex: 1, backgroundColor: renkler.zeminAcik },
  icerik: { flexGrow: 1, justifyContent: "center", padding: 24, gap: 12 },
  baslik: { fontSize: 28, fontWeight: "800", color: renkler.lacivert, textAlign: "center" },
  altBaslik: { fontSize: yaziBoyutlari.govde, color: renkler.yaziSoluk, textAlign: "center", marginBottom: 4 },
  sunucu: { fontSize: 11, color: renkler.yaziSoluk, textAlign: "center", marginBottom: 16 },
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
  linkYazi: { color: renkler.vurgu, textAlign: "center", marginTop: 16, fontSize: yaziBoyutlari.kucuk },
});
