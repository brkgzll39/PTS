import React, { useCallback, useEffect, useState } from "react";
import { FlatList, StyleSheet, Text, TextInput, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { sonKayitlariGetir } from "../api/pts";
import type { Kayit } from "../api/types";
import KayitRow from "../components/KayitRow";
import LoadingView from "../components/LoadingView";
import ErrorBanner from "../components/ErrorBanner";
import { renkler, yaziBoyutlari } from "../theme";

// Web panelin arama kutusundaki İLKE aynen korunuyor (bkz. app.js): kullanıcı
// yazarken her tuş vuruşunda sunucuya gitmek yerine kısa bir gecikme
// (debounce) ile istek atılır -- hem sunucuyu gereksiz yormaz hem de yavaş
// bir mobil ağda daha akıcı hisseder.
function useDebounce<T>(deger: T, gecikmeMs: number): T {
  const [debounceliDeger, setDebounceliDeger] = useState(deger);
  useEffect(() => {
    const zamanlayici = setTimeout(() => setDebounceliDeger(deger), gecikmeMs);
    return () => clearTimeout(zamanlayici);
  }, [deger, gecikmeMs]);
  return debounceliDeger;
}

export default function KayitlarScreen() {
  const [arama, setArama] = useState("");
  const debounceliArama = useDebounce(arama, 400);
  const [kayitlar, setKayitlar] = useState<Kayit[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [yenileniyor, setYenileniyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);

  const veriyiYukle = useCallback(async (plaka: string) => {
    setHata(null);
    try {
      const liste = await sonKayitlariGetir(50, plaka || undefined);
      setKayitlar(liste);
    } catch (e) {
      setHata((e as Error).message || "Kayıtlar yüklenemedi");
    } finally {
      setYukleniyor(false);
      setYenileniyor(false);
    }
  }, []);

  useEffect(() => {
    setYukleniyor(true);
    veriyiYukle(debounceliArama);
  }, [debounceliArama, veriyiYukle]);

  return (
    <View style={styles.kapsayici}>
      <StatusBar style="dark" />
      <View style={styles.aramaKutusu}>
        <TextInput
          style={styles.aramaGirdi}
          value={arama}
          onChangeText={setArama}
          placeholder="Plaka ara..."
          autoCapitalize="characters"
          autoCorrect={false}
        />
      </View>
      {hata && <ErrorBanner mesaj={hata} yenidenDeneOnPress={() => veriyiYukle(debounceliArama)} />}
      {yukleniyor ? (
        <LoadingView mesaj="Kayıtlar yükleniyor..." />
      ) : (
        <FlatList
          data={kayitlar}
          keyExtractor={(k) => String(k.id)}
          renderItem={({ item }) => <KayitRow kayit={item} />}
          refreshing={yenileniyor}
          onRefresh={() => {
            setYenileniyor(true);
            veriyiYukle(debounceliArama);
          }}
          ListEmptyComponent={<Text style={styles.bosDurum}>Kayıt bulunamadı</Text>}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  kapsayici: { flex: 1, backgroundColor: renkler.zeminAcik },
  aramaKutusu: { padding: 12, backgroundColor: renkler.yuzeyBeyaz, borderBottomWidth: 1, borderBottomColor: renkler.kenarlik },
  aramaGirdi: {
    borderWidth: 1,
    borderColor: renkler.kenarlik,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: yaziBoyutlari.govde,
  },
  bosDurum: { padding: 32, textAlign: "center", color: renkler.yaziSoluk },
});
