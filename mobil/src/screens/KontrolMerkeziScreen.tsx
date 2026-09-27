import React, { useCallback, useEffect, useState } from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { alarmlariGetir, iceridDurumuGetir, istatistikGetir } from "../api/pts";
import type { Alarm, IceridDurumu, Istatistik } from "../api/types";
import StatTile from "../components/StatTile";
import AlarmRow from "../components/AlarmRow";
import LoadingView from "../components/LoadingView";
import ErrorBanner from "../components/ErrorBanner";
import { renkler, yaziBoyutlari } from "../theme";

export default function KontrolMerkeziScreen() {
  const [istatistik, setIstatistik] = useState<Istatistik | null>(null);
  const [iceride, setIceride] = useState<IceridDurumu | null>(null);
  const [sonAlarmlar, setSonAlarmlar] = useState<Alarm[]>([]);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [yenileniyor, setYenileniyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);

  const veriyiYukle = useCallback(async () => {
    setHata(null);
    try {
      const [ist, ic, alarmlar] = await Promise.all([
        istatistikGetir(),
        // Bu uç nokta arıza/bakım gibi durumlarda 500 dönebilir (ör.
        // kamera tarafı henüz hiç veri üretmemiş) -- bir hata TÜM ekranı
        // düşürmesin diye ayrı yakalanıyor, web panelin AYNI ilkesi
        // (bkz. app.js::panelYenile'deki .catch(() => {})).
        iceridDurumuGetir().catch(() => null),
        alarmlariGetir(true, 5),
      ]);
      setIstatistik(ist);
      setIceride(ic);
      setSonAlarmlar(alarmlar);
    } catch (e) {
      setHata((e as Error).message || "Veriler yüklenemedi");
    } finally {
      setYukleniyor(false);
      setYenileniyor(false);
    }
  }, []);

  useEffect(() => {
    veriyiYukle();
  }, [veriyiYukle]);

  if (yukleniyor) return <LoadingView mesaj="Kontrol Merkezi yükleniyor..." />;

  return (
    <View style={styles.kapsayici}>
      <StatusBar style="dark" />
      {hata && <ErrorBanner mesaj={hata} yenidenDeneOnPress={veriyiYukle} />}
      <ScrollView
        contentContainerStyle={styles.icerik}
        refreshControl={
          <RefreshControl
            refreshing={yenileniyor}
            onRefresh={() => {
              setYenileniyor(true);
              veriyiYukle();
            }}
            colors={[renkler.vurgu]}
          />
        }
      >
        <Text style={styles.bolumBaslik}>Genel İstatistikler</Text>
        <View style={styles.izgara}>
          <StatTile etiket="Bugünkü Geçiş" deger={istatistik?.bugunku_kayit ?? "-"} />
          <StatTile etiket="Toplam Kayıt" deger={istatistik?.toplam_kayit ?? "-"} />
          <StatTile etiket="Yetkisiz Deneme" deger={istatistik?.yetkisiz_giris_denemesi ?? "-"} vurgu="tehlike" />
          <StatTile etiket="Kara Liste Geçişi" deger={istatistik?.kara_liste_gecis ?? 0} vurgu="tehlike" />
          <StatTile etiket="Aktif Kişi" deger={istatistik?.aktif_kisi_sayisi ?? "-"} vurgu="basarili" />
          <StatTile etiket="İçeride Araç" deger={iceride?.iceride_sayisi ?? "-"} vurgu="basarili" />
        </View>

        <Text style={styles.bolumBaslik}>Açık Alarmlar</Text>
        <View style={styles.kart}>
          {sonAlarmlar.length === 0 ? (
            <Text style={styles.bosDurum}>Açık alarm yok</Text>
          ) : (
            sonAlarmlar.map((a) => <AlarmRow key={a.id} alarm={a} />)
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  kapsayici: { flex: 1, backgroundColor: renkler.zeminAcik },
  icerik: { padding: 16, paddingBottom: 32 },
  bolumBaslik: {
    fontSize: yaziBoyutlari.kucuk,
    fontWeight: "700",
    color: renkler.yaziSoluk,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginBottom: 10,
    marginTop: 8,
  },
  izgara: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" },
  kart: {
    backgroundColor: renkler.yuzeyBeyaz,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: renkler.kenarlik,
    overflow: "hidden",
  },
  bosDurum: { padding: 16, color: renkler.yaziSoluk, textAlign: "center" },
});
