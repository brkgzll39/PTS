import React, { useEffect, useState } from "react";
import { Alert, Pressable, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import Constants from "expo-constants";
import * as Notifications from "expo-notifications";
import { useAuth } from "../context/AuthContext";
import { pushBildirimKaydiniYap } from "../push/registerPushToken";
import { renkler, yaziBoyutlari } from "../theme";

const ROL_ETIKETLERI: Record<string, string> = {
  yonetici: "Yönetici",
  "operatör": "Operatör",
  "güvenlik": "Güvenlik Personeli",
  izleyici: "İzleyici (Salt Okunur)",
};

export default function AyarlarScreen() {
  const { kullanici, sunucuAdresi, cikisYap, sunucuDegistir } = useAuth();
  const [bildirimDurumu, setBildirimDurumu] = useState<string>("kontrol ediliyor...");
  const [bildirimKontrolEdiliyor, setBildirimKontrolEdiliyor] = useState(false);

  async function bildirimDurumunuGuncelle() {
    const izin = await Notifications.getPermissionsAsync();
    setBildirimDurumu(izin.status === "granted" ? "Açık" : izin.status === "denied" ? "Reddedildi" : "Belirsiz");
  }

  useEffect(() => {
    bildirimDurumunuGuncelle();
  }, []);

  async function bildirimYenidenDene() {
    setBildirimKontrolEdiliyor(true);
    const sonuc = await pushBildirimKaydiniYap();
    setBildirimKontrolEdiliyor(false);
    await bildirimDurumunuGuncelle();
    if (!sonuc.basarili) {
      Alert.alert("Push Bildirim", sonuc.neden || "Bilinmeyen bir sorun oluştu");
    } else {
      Alert.alert("Push Bildirim", "Bu cihaz bildirim almak üzere kaydedildi.");
    }
  }

  function cikisOnayi() {
    Alert.alert("Çıkış Yap", "Oturumu kapatmak istediğinize emin misiniz?", [
      { text: "Vazgeç", style: "cancel" },
      { text: "Çıkış Yap", style: "destructive", onPress: () => cikisYap() },
    ]);
  }

  return (
    <View style={styles.kapsayici}>
      <StatusBar style="dark" />
      <View style={styles.kart}>
        <Text style={styles.satirEtiket}>Kullanıcı</Text>
        <Text style={styles.satirDeger}>{kullanici?.kullanici_adi}</Text>
        <Text style={styles.satirEtiket}>Rol</Text>
        <Text style={styles.satirDeger}>{kullanici ? ROL_ETIKETLERI[kullanici.rol] || kullanici.rol : "-"}</Text>
        <Text style={styles.satirEtiket}>Sunucu Adresi</Text>
        <Text style={styles.satirDeger}>{sunucuAdresi}</Text>
      </View>

      <View style={styles.kart}>
        <Text style={styles.satirEtiket}>Push Bildirim Durumu</Text>
        <Text style={styles.satirDeger}>{bildirimDurumu}</Text>
        <Pressable
          style={[styles.ikincilButon, bildirimKontrolEdiliyor && { opacity: 0.6 }]}
          onPress={bildirimYenidenDene}
          disabled={bildirimKontrolEdiliyor}
        >
          <Text style={styles.ikincilButonYazi}>
            {bildirimKontrolEdiliyor ? "Kontrol ediliyor..." : "Yeniden Dene / İzin İste"}
          </Text>
        </Pressable>
      </View>

      <Pressable style={styles.ikincilButon} onPress={sunucuDegistir}>
        <Text style={styles.ikincilButonYazi}>Sunucu Adresini Değiştir</Text>
      </Pressable>

      <Pressable style={styles.tehlikeliButon} onPress={cikisOnayi}>
        <Text style={styles.tehlikeliButonYazi}>Çıkış Yap</Text>
      </Pressable>

      <Text style={styles.versiyon}>TPAO PTS Mobil · v{Constants.expoConfig?.version || "1.0.0"}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  kapsayici: { flex: 1, backgroundColor: renkler.zeminAcik, padding: 16, gap: 14 },
  kart: {
    backgroundColor: renkler.yuzeyBeyaz,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: renkler.kenarlik,
    padding: 16,
    gap: 2,
  },
  satirEtiket: { fontSize: 11, color: renkler.yaziSoluk, marginTop: 8, textTransform: "uppercase", letterSpacing: 0.5 },
  satirDeger: { fontSize: yaziBoyutlari.govde, color: renkler.yaziKoyu, fontWeight: "600" },
  ikincilButon: {
    marginTop: 10,
    backgroundColor: renkler.zeminAcik,
    borderWidth: 1,
    borderColor: renkler.kenarlik,
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: "center",
  },
  ikincilButonYazi: { color: renkler.vurgu, fontWeight: "600", fontSize: yaziBoyutlari.kucuk },
  tehlikeliButon: { backgroundColor: renkler.tehlikeZemin, borderRadius: 10, paddingVertical: 14, alignItems: "center" },
  tehlikeliButonYazi: { color: renkler.tehlike, fontWeight: "700", fontSize: yaziBoyutlari.govde },
  versiyon: { textAlign: "center", color: renkler.yaziSoluk, fontSize: 11, marginTop: "auto" },
});
