import React, { useCallback, useEffect, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { alarmOkunduIsaretle, alarmlariGetir, tumAlarmlariOkunduIsaretle } from "../api/pts";
import type { Alarm } from "../api/types";
import AlarmRow from "../components/AlarmRow";
import LoadingView from "../components/LoadingView";
import ErrorBanner from "../components/ErrorBanner";
import { renkler, yaziBoyutlari } from "../theme";

export default function AlarmlarScreen() {
  const [alarmlar, setAlarmlar] = useState<Alarm[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [yenileniyor, setYenileniyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);

  const veriyiYukle = useCallback(async () => {
    setHata(null);
    try {
      const liste = await alarmlariGetir(true, 50);
      setAlarmlar(liste);
    } catch (e) {
      setHata((e as Error).message || "Alarmlar yüklenemedi");
    } finally {
      setYukleniyor(false);
      setYenileniyor(false);
    }
  }, []);

  useEffect(() => {
    veriyiYukle();
  }, [veriyiYukle]);

  async function isaretleveYenile(alarmId: number) {
    // İYİMSER GÜNCELLEME (optimistic update): sunucudan yanıt beklemeden
    // satırı hemen "okundu" görünümüne çevir -- ağ gecikmesi kadar
    // beklemek bir dokunuşun etkisiz görünmesine yol açardı. Sunucu
    // isteği başarısız olursa listeyi TEKRAR sunucudan çekip gerçek
    // duruma döneriz (sessizce yanlış bir "okundu" durumu göstermeyiz).
    setAlarmlar((onceki) => onceki.map((a) => (a.id === alarmId ? { ...a, okundu: true } : a)));
    try {
      await alarmOkunduIsaretle(alarmId);
    } catch {
      veriyiYukle();
    }
  }

  async function tumunuIsaretle() {
    setAlarmlar((onceki) => onceki.map((a) => ({ ...a, okundu: true })));
    try {
      await tumAlarmlariOkunduIsaretle();
    } catch {
      veriyiYukle();
    }
  }

  if (yukleniyor) return <LoadingView mesaj="Alarmlar yükleniyor..." />;

  const acikSayisi = alarmlar.filter((a) => !a.okundu).length;

  return (
    <View style={styles.kapsayici}>
      <StatusBar style="dark" />
      {hata && <ErrorBanner mesaj={hata} yenidenDeneOnPress={veriyiYukle} />}
      <View style={styles.ustCubuk}>
        <Text style={styles.ustCubukYazi}>{acikSayisi} açık alarm</Text>
        {acikSayisi > 0 && (
          <Pressable onPress={tumunuIsaretle}>
            <Text style={styles.linkYazi}>Tümünü okundu işaretle</Text>
          </Pressable>
        )}
      </View>
      <FlatList
        data={alarmlar}
        keyExtractor={(a) => String(a.id)}
        renderItem={({ item }) => <AlarmRow alarm={item} onOkunduIsaretle={isaretleveYenile} />}
        refreshing={yenileniyor}
        onRefresh={() => {
          setYenileniyor(true);
          veriyiYukle();
        }}
        ListEmptyComponent={<Text style={styles.bosDurum}>Alarm bulunmuyor</Text>}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  kapsayici: { flex: 1, backgroundColor: renkler.zeminAcik },
  ustCubuk: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: renkler.yuzeyBeyaz,
    borderBottomWidth: 1,
    borderBottomColor: renkler.kenarlik,
  },
  ustCubukYazi: { color: renkler.yaziSoluk, fontSize: yaziBoyutlari.kucuk, fontWeight: "600" },
  linkYazi: { color: renkler.vurgu, fontSize: yaziBoyutlari.kucuk, fontWeight: "600" },
  bosDurum: { padding: 32, textAlign: "center", color: renkler.yaziSoluk },
});
