import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { useAuth } from "../context/AuthContext";
import SunucuAyarlariScreen from "../screens/SunucuAyarlariScreen";
import GirisScreen from "../screens/GirisScreen";
import MainTabs from "./MainTabs";
import LoadingView from "../components/LoadingView";

// Kasıtlı olarak bir "stack" navigator DEĞİL -- bu üç durum (sunucu adresi
// gerekli / giriş gerekli / giriş yapıldı) birbirine geri dönüşü olmayan,
// SIRALI bir akış (bkz. AuthContext.tsx'teki `Durum` tipi); kullanıcının
// "geri" tuşuyla giriş ekranından sunucu ekranına ya da tam tersine dönmesi
// anlamlı değil, bu yüzden basit bir koşullu render yeterli ve daha az
// kod/hata yüzeyi demek.
export default function RootNavigator() {
  const { durum } = useAuth();

  return (
    <NavigationContainer>
      {durum === "yukleniyor" && <LoadingView mesaj="PTS başlatılıyor..." />}
      {durum === "sunucuGerekli" && <SunucuAyarlariScreen />}
      {durum === "girisGerekli" && <GirisScreen />}
      {durum === "girisYapildi" && <MainTabs />}
    </NavigationContainer>
  );
}
