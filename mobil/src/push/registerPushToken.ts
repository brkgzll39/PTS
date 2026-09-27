import * as Notifications from "expo-notifications";
import * as Device from "expo-device";
import { Platform } from "react-native";
import { pushTokenKaydet } from "../api/pts";

// Uygulama ön plandayken de bildirim GÖRÜNSÜN (varsayılan davranış arka
// planda/kilit ekranında gösterir ama uygulama açıkken sessizce yutar) --
// bir güvenlik/yönetim uygulamasında "uygulama açıkken alarm geldiğini
// göstermemek" kabul edilebilir değil.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

/**
 * Bildirim izni ister, Expo push token'ını alır ve backend'e kaydeder.
 * Fiziksel bir cihaz DEĞİLSE (simülatör/emülatör) push token üretilemez --
 * bu durumda sessizce (hata fırlatmadan) `null` döner, uygulamanın geri
 * kalanının çalışmasını ETKİLEMEZ (bkz. web panelin PWA service worker
 * kaydındaki AYNI "başarısız olursa normal çalışmayı bozma" ilkesi).
 */
export async function pushBildirimKaydiniYap(): Promise<{ basarili: boolean; neden?: string }> {
  if (!Device.isDevice) {
    return { basarili: false, neden: "Fiziksel bir cihazda değilsiniz (simülatör push bildirim alamaz)" };
  }

  const mevcutIzin = await Notifications.getPermissionsAsync();
  let nihaiIzin = mevcutIzin;
  if (mevcutIzin.status !== "granted") {
    nihaiIzin = await Notifications.requestPermissionsAsync();
  }
  if (nihaiIzin.status !== "granted") {
    return { basarili: false, neden: "Bildirim izni verilmedi" };
  }

  if (Platform.OS === "android") {
    // Android 8+'da bir "kanal" olmadan bildirim hiç görünmeyebilir/varsayılan
    // ayarlarla (ses/titreşim yok) gösterilir -- burada güvenlik alarmına
    // uygun (yüksek öncelik) bir kanal tanımlıyoruz.
    await Notifications.setNotificationChannelAsync("pts-alarmlar", {
      name: "PTS Alarmları",
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: "#2F6FED",
    });
  }

  let expoPushToken: string;
  try {
    const sonuc = await Notifications.getExpoPushTokenAsync();
    expoPushToken = sonuc.data;
  } catch (hata) {
    return { basarili: false, neden: `Push token alınamadı: ${String(hata)}` };
  }

  try {
    await pushTokenKaydet(expoPushToken, Platform.OS);
  } catch (hata) {
    // Backend'e kaydetme başarısız olsa bile (ör. o an sunucuya ulaşılamadı)
    // bu, UYGULAMANIN GERİ KALANINI durdurmamalı -- kullanıcı bir sonraki
    // girişte veya Ayarlar ekranındaki "yeniden dene" ile tekrar deneyebilir.
    return { basarili: false, neden: `Sunucuya kaydedilemedi: ${String((hata as Error).message || hata)}` };
  }

  return { basarili: true };
}
