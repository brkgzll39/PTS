# PTS Mobil (Yönetim/Raporlama Uygulaması)

Bu klasör, TPAO PTS sisteminin **yönetim/raporlama amaçlı, salt-okunur** resmi
mobil uygulamasının (React Native / Expo, TypeScript) kaynak kodunu içerir.
Panelin PWA (tarayıcıdan "Ana Ekrana Ekle") sürümünden farklı olarak bu, gerçek
bir uygulama mağazası deneyimine daha yakın, kendi ikonu/splash ekranı ve
**push bildirimi** desteği olan bağımsız bir uygulamadır.

## ÖNEMLİ UYARI — bu kod bu ortamda derlenip çalıştırılamadı

Bu kodu yazdığım sanal ortamda (sandbox) npm paket kayıt sunucusuna (registry)
erişim tamamen engelli (`npm install` her paket için 403 Forbidden döndürüyor).
Bu yüzden:

- `npm install` / `npx expo install` **hiç çalıştırılamadı**,
- `npx expo start` ile uygulama **hiç açılıp denenemedi**,
- `tsc --noEmit` ile TypeScript tip kontrolü **hiç yapılamadı**.

Kod, mevcut web panelinin (`frontend/`) mantığı ve Expo SDK 57'nin (Eylül 2026
itibarıyla güncel kararlı sürüm) resmi dokümantasyonu referans alınarak
elle, dikkatlice yazıldı ve gözden geçirildi — ama **gerçek ilk derleme/çalıştırma
sizin kendi bilgisayarınızda olacak**. Aşağıdaki adımları uyguladıktan sonra
çıkan HERHANGİ bir hatayı (kırmızı ekran, kırmızı terminal çıktısı, "Unable to
resolve module" vb.) bana birebir kopyalayıp gönderirseniz, bir sonraki
yama (patch) ile hemen düzeltirim. Bu, projenin baştan beri sürdürdüğü
"sessiz hata olmasın" ilkesinin bir parçası — bu adımı gizlemek yerine
açıkça söylüyorum.

## Gereksinimler

- Node.js 22.13 veya üzeri (bilgisayarınızda kurulu olmalı)
- Bir Expo hesabı (ücretsiz) — sadece gerçek APK/IPA derlemesi (EAS Build)
  için gerekli; hızlı test için (Expo Go) gerekmez
- Telefonunuzda **Expo Go** uygulaması (hızlı test için) veya gerçek APK
  kurulumu (kalıcı kullanım için)
- PTS backend sunucusunun telefonla aynı ağda (veya telefondan erişilebilir
  bir adreste) çalışıyor olması

## 1) İlk kurulum

```bash
cd mobil
npm install
npx expo install --fix
```

`expo install --fix`, `package.json`'daki paket sürümlerini benim burada
tahmin ederek yazdığım sürümlerden, Expo SDK 57 ile **gerçekten uyumlu** olan
kesin sürümlere otomatik düzeltir. Bu komutu atlamayın — sürüm uyuşmazlığı
en sık karşılaşılan hatadır.

## 2) Hızlı test (kurulum/imzalama gerektirmez)

```bash
npx expo start
```

Terminalde bir QR kod çıkar. Telefonunuza (App Store / Play Store'dan) **Expo
Go** uygulamasını kurup QR kodu okutun — uygulama telefonunuzda anında açılır.
Bu, kod üzerinde hızlıca deneme/iterasyon yapmak için en pratik yoldur; ama
Expo Go üzerinden push bildirimleri Android'de sınırlı çalışabilir (bkz.
aşağıdaki not) — push bildirimini tam test etmek için gerçek APK kurulumu
gerekir.

İlk açılışta uygulama sizden **PTS sunucu adresini** ister (ör.
`http://192.168.1.23:8000`) — panelin tarayıcıdan eriştiğiniz adresle aynısı.
Ardından normal PTS kullanıcı adı/şifrenizle giriş yaparsınız (sadece
"sakin" rolündeki hesaplar mobil uygulamaya giremez — bu bilinçli bir
kısıtlama, çünkü uygulama yönetim/raporlama amaçlıdır).

## 3) Gerçek, kalıcı Android uygulaması (APK) — EAS Build

Bir gün geçerli, ücretsiz [expo.dev](https://expo.dev) hesabı oluşturduktan
sonra:

```bash
cd mobil
npx eas login
npx eas build -p android --profile preview
```

Bu komut, APK dosyasını Expo'nun bulut sunucularında derler (birkaç dakika
sürer) ve size indirme linki verir. İndirdiğiniz `.apk` dosyasını Android
telefona kurmak için telefonda "bilinmeyen kaynaklardan yükleme" izni
gerekebilir (Android sürümüne göre değişir).

`app.json` içindeki `extra.eas.projectId` alanı şu an bir **yer tutucu**
(`BURAYA-KENDI-EAS-PROJECT-ID-NIZ-GELECEK`) — ilk `eas build` komutunu
çalıştırdığınızda Expo CLI bunu otomatik olarak kendi proje kimliğinizle
değiştirmeyi teklif eder, kabul edin.

## 4) iOS hakkında önemli not

iOS tarafı için kod tamamen yazıldı (aynı kaynak kod her iki platformda da
çalışır), ancak **gerçek bir iPhone'a kurulabilir bir build almak için
ücretli bir Apple Developer hesabı (yıllık ~99 USD) gereklidir** — ne bu
oturumda ne de şu an elimde böyle bir hesap var. Yani iOS desteği şu an
"kod hazır, derlenip imzalanması bekliyor" durumunda. Böyle bir hesabınız
olursa:

```bash
npx eas build -p ios --profile preview
```

komutu iOS için de aynı şekilde çalışır (Apple hesap bilgilerinizi ilk
seferinde ister).

## 5) Push bildirimleri nasıl çalışır

- Uygulama girişten hemen sonra, arka planda, telefonun bildirim izni ister
  ve bir "Expo push token" alıp backend'e (`POST /push/kaydet`) kaydeder.
  Bu adım **sessizce başarısız olabilir** (izin verilmezse, gerçek cihaz
  değilse — emülatörde push çalışmaz — vb.); kullanıcıya "Ayarlar" sekmesinde
  push durumu gösterilir ve gerekirse "Tekrar Dene" butonu sunulur.
- Panelde (web) **Bildirim Ayarları** sekmesinden yeni bir bildirim kuralı
  eklerken "Tip" olarak **Push Bildirim (Mobil Uygulama)** seçilebilir; "Hedef"
  alanına `hepsi` ya da bir rol adı (`yonetici`, `operatör`, `güvenlik`,
  `izleyici`) yazılır — bildirim, o rolde ve o an cihazında push token'ı kayıtlı
  olan herkese gider.
- Aynı fiziksel telefon farklı bir PTS kullanıcısıyla tekrar giriş yaparsa
  (vardiya değişimi gibi), o cihazın push kaydı otomatik olarak yeni
  kullanıcıya devreder — eski kullanıcıya artık bildirim gitmez.
- Çıkış yapıldığında uygulama backend'den o cihazın push kaydını siler
  (`POST /push/kaydi-sil`).

## Uygulamanın kapsamı (bilinçli olarak sınırlı)

Bu ilk sürüm, sizin seçiminize göre **yönetim/raporlama** odaklıdır ve
**salt okunur**dur:

- **Kontrol Merkezi**: özet istatistikler + son açık alarmlardan ilk 5'i
- **Alarmlar**: tüm alarm listesi, okundu işaretleme (tek tek veya toplu)
- **Geçiş Kayıtları**: arama (plakaya göre, 400ms gecikmeli)
- **Ayarlar**: kullanıcı bilgisi, push bildirim durumu, sunucu değiştirme,
  çıkış yapma

Kayıt düzenleme, kişi/araç ekleme, kara liste yönetimi gibi **yazma**
işlemleri bu ilk sürümde bilinçli olarak yok — bunlar için panel (web/PWA)
kullanılmaya devam edilir. İleride istenirse bir sonraki sürümde eklenebilir.

## Sorun mu çıktı?

`npx expo start` veya `eas build` sırasında çıkan hata metnini (özellikle
kırmızı yazan kısmı) olduğu gibi kopyalayıp gönderin — bir sonraki yamada
düzeltirim. Bu tür başlangıç hataları (paket sürüm uyuşmazlığı, eksik
native modül bağlantısı vb.) elle yazılmış, hiç çalıştırılmamış bir React
Native projesinde beklenen bir durumdur ve genelde tek satırlık düzeltmelerle
çözülür.
