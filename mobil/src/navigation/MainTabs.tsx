import React from "react";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { Ionicons } from "@expo/vector-icons";
import KontrolMerkeziScreen from "../screens/KontrolMerkeziScreen";
import AlarmlarScreen from "../screens/AlarmlarScreen";
import KayitlarScreen from "../screens/KayitlarScreen";
import AyarlarScreen from "../screens/AyarlarScreen";
import { renkler } from "../theme";

export type SekmeParametreleri = {
  KontrolMerkezi: undefined;
  Alarmlar: undefined;
  Kayitlar: undefined;
  Ayarlar: undefined;
};

const Tab = createBottomTabNavigator<SekmeParametreleri>();

export default function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerStyle: { backgroundColor: renkler.lacivert },
        headerTintColor: "#fff",
        headerTitleStyle: { fontWeight: "700" },
        tabBarActiveTintColor: renkler.vurgu,
        tabBarInactiveTintColor: renkler.yaziSoluk,
        tabBarStyle: { backgroundColor: renkler.yuzeyBeyaz, borderTopColor: renkler.kenarlik },
        tabBarIcon: ({ color, size }) => {
          const simgeler: Record<keyof SekmeParametreleri, keyof typeof Ionicons.glyphMap> = {
            KontrolMerkezi: "speedometer-outline",
            Alarmlar: "warning-outline",
            Kayitlar: "list-outline",
            Ayarlar: "settings-outline",
          };
          const ad = route.name as keyof SekmeParametreleri;
          return <Ionicons name={simgeler[ad]} size={size} color={color} />;
        },
      })}
    >
      <Tab.Screen name="KontrolMerkezi" component={KontrolMerkeziScreen} options={{ title: "Kontrol Merkezi" }} />
      <Tab.Screen name="Alarmlar" component={AlarmlarScreen} options={{ title: "Alarmlar" }} />
      <Tab.Screen name="Kayitlar" component={KayitlarScreen} options={{ title: "Geçiş Kayıtları" }} />
      <Tab.Screen name="Ayarlar" component={AyarlarScreen} options={{ title: "Ayarlar" }} />
    </Tab.Navigator>
  );
}
