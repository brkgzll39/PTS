# PTS Kapı Kutusu

Nizamiyeye konan küçük kontrol kutusu. Kart: **KinCony KC868-A8**
(ESP32, kablolu ağ, 8 röle, 8 optokuplörlü giriş).

Kutunun görevleri:

- **Araç geçti sinyali.** Yerdeki döngü dedektörü araç görünce kutu bunu anında
  PTS'ye bildirir. Kamera o aracı okumadıysa PTS bir **okunamayan geçiş** açar.
  Bu geçiş İçerideki Araçlar ekranında ve Kapı Modunda görevliye görünür, görevli
  plakayı fotoğraftan yazar.
- **Bariyeri açar.** PTS'nin "aç" komutuyla bariyer rölesini kısa süre çeker
  (kuru kontak).
- **Görevli düğmesi.** Kutuya bağlanan düğmeye basılınca bariyer yerelde açılır.
  Bu, PTS kapalı olsa da çalışır.
- **Ağ yoksa biriktirir.** Ağ yokken en çok 300 olayı biriktirir, bağlantı gelince
  gönderir.
- **Ağdan güncellenir.** Yeni yazılım kutunun kendi web sayfasından yüklenir; USB
  yalnızca ilk kurulumda gerekir.

> Bu sürümde kutu plakayı **kendisi tanımaz**. Plakayı PTS tanır. PTS kapalıyken
> tanıdık araca bariyeri kendiliğinden açmak için kameranın kendi plaka tanıması
> (Dahua ANPR) gerekir. Bu sonraki sürümün işi.

## 1. Parça listesi (bir şerit)

| Parça | Not |
|---|---|
| KinCony **KC868-A8** (ESP32 + Ethernet). A8v3 ya da A8M değil | Kutunun beyni |
| **Loop (manyetik araç) dedektörü, 12V**, röle çıkışlı, "varlık (presence)" modlu | 12/24V AC/DC yazanlar da olur |
| Loop kablosu (1,5 mm² tek damarlı, özel loop kablosu) | Bir döngü + bağlantı için ~20-30 m |
| **12V DC DIN ray güç kaynağı**, en az 2 A (ör. Mean Well HDR-30-12) | Kart 12V ister: **24V vermeyin** |
| IP65 dış mekân pano kutusu, DIN ray, klemensler | |
| Cat6 Ethernet kablosu (dış mekân), gerekirse ağ anahtarı portu | |
| Görevli düğmesi (isteğe bağlı, NO kontaklı buton) | |
| Bariyer kullanılacaksa: 24V DC motorlu, kuru kontak "aç" girişli, fotoselli bariyer | Bariyer kendi adaptörüyle beslenir |

Gereken aletler: dizüstü bilgisayar ve kartın USB kablosu, multimetre, tornavida
takımı, kablo soyucu. Asfalt kesimi için bariyerci ya da elektrikçi.

> 220V bağlantısını (güç kaynağının girişi, sigorta) bir elektrikçi yapmalıdır.

## 2. Bağlantı

```
[Döngü (asfalt)] -> [Loop dedektörü 12V] --röle (NO)--> [KC868 giriş 1 + GND]
[Görevli düğmesi (isteğe bağlı)]         -------------> [KC868 giriş 8 + GND]
[KC868 röle 1: COM + NO] --kuru kontak--> [Bariyer kartı "AÇ/START" girişi]
[Fotosel]                ------------->   [Bariyer kartı güvenlik girişi]  (kutudan bağımsız)
[KC868 Ethernet]         ------------->   [Ağ anahtarı / PTS sunucusu]
[12V DC güç kaynağı]     ------------->   [KC868 12V girişi + loop dedektörü]
```

- KC868 girişleri **GND'ye kısa devre** edilince aktif olur. Loop dedektörünün
  röle çıkışını (NO ve COM) girişe ve GND'ye bağlayın.
- Bariyerin elektriğine **dokunmayın**. Kutu, bariyer kartının "aç" butonu
  girişine yalnızca bir kontak verir (röle COM + NO).
- **Fotosel kutuya değil bariyere bağlanır.** Kolun araca inmesini bariyer kendisi
  engeller.
- Loop dedektörünü **varlık (presence)** moduna alın: araç döngünün üstündeyken
  röle çekili kalsın. "Darbe (pulse)" modunda da çalışır, ama varlık modu daha
  güvenilirdir.

### Döngünün döşenmesi (genel kurallar: dedektörün kılavuzu önceliklidir)

- **Yer:** kameranın plakayı okuduğu noktanın altı. Kutu "araç var" dediği anda
  kamera da o aracı görüyor olmalı.
- **Boyut:** şerit genişliğinden her iki yanda ~30-50 cm içeride, yol yönünde
  ~1,5-2 m uzunlukta bir dikdörtgen.
- **Sarım:** çevre 6-10 m ise 3 tur. Daha küçükse 4 tur, daha büyükse 2 tur.
- **Kanal:** 3-5 cm derinlik. Köşeler 45° kesilir ki kablo keskin bükülmesin.
  Kablo yerleştirilip kanal bitüm ya da epoksi dolguyla kapatılır.
- **Bağlantı kablosu:** döngüden dedektöre giden iki uç metre başına en az 20 kez
  birbirine burulur ve olabildiğince kısa tutulur.
- **Uzaklık:** başka bir döngüden ve büyük metal parçalardan (ızgara, bariyer
  gövdesi) en az 1 m uzakta olmalı. İki döngü yan yanaysa dedektörlerin frekansı
  farklı ayarlanır.

## 3. Yazılımın karta yüklenmesi

Derlenmiş yazılım GitHub → Actions → **Kapi Kutusu yazilimi** → son çalışma →
**kapi-kutusu** artifact'inde bulunur.

- **`pts-kapi-kutusu-tam.bin`**: ilk yükleme. Tek dosyadır, **0x0** adresine yazılır.
- `firmware.bin`: güncelleme. Kutunun web sayfasından yüklenir (aşağıda).

Windows'ta en kolay yol:

1. Espressif'in **Flash Download Tool** programını indirin. ChipType: ESP32, WorkMode: Develop.
2. Kartı USB ile bilgisayara bağlayın. Kart üzerindeki USB, CH340 sürücüsü ister.
3. `pts-kapi-kutusu-tam.bin` dosyasını **0x0** adresine yazdırın, **START** düğmesine basın.

Kaynak koddan derlemek isterseniz (PlatformIO kurulu bilgisayarda):

```
cd kapi_kutusu
pio run -t upload
pio device monitor     # seri ekran: DURUM, SIFIRLA komutları
```

### Ağdan güncelleme

1. GitHub'dan yeni **kapi-kutusu** dosyasını indirip açın.
2. Kutunun sayfasında (`http://<kutu-ip>/`) en alttaki **Yazılım güncelleme**
   bölümünde **firmware.bin** dosyasını seçin ve **Güncellemeyi yükle**'ye basın.
3. Yükleme ~1 dk sürer. Bitince kutu yeniden başlar ve sayfa kendiliğinden yenilenir.
   Sayfanın başlığında yeni sürüm numarası görünür.

- Ayarlar (PTS adresi, anahtar, parola) korunur.
- Yanlış dosya (ör. `tam.bin`, zip ya da başka bir kartın yazılımı) yüklenirse
  kutu daha flash'a yazmadan reddeder ve eski yazılımla çalışmaya devam eder.
  Yükleme yarıda kesilirse de eski yazılım çalışmaya devam eder.
- Güncelleme sırasında kutunun elektriğini kesmeyin.
- Yeni yazılım hiç açılmazsa (çok olası değil), kutu USB ile `tam.bin` yazılarak
  kurtarılır. Bu durumda ayarlar yeniden yapılır.

> **1.0.0'dan geçiş:** 1.1.0 ile kartın bölüm tablosu değişti. 1.0.0 yüklü bir karta
> 1.1.0 bir kez **USB ile `tam.bin`** olarak yazılmalıdır. Sonrası ağdan yapılır.

## 4. Ayarlar

1. Kutuyu ağa bağlayın. Kutu adresini DHCP'den alır.
   - Adres modemin/anahtarın listesinde **pts-kapi-kutusu** adıyla görünür.
   - Ya da seri ekranda `DURUM` yazarak öğrenebilirsiniz.
2. PTS'de **Bariyer → Kapı Kutuları → Yeni kutu** ile kutuyu ekleyin.
   - Giriş 1'i şeridin kamerasıyla eşleyin, ör. "Ana Kapı Çıkış", Çıkış şeridi.
   - Kaydedince **PTS adresi** ve **kutu anahtarı** görünür.
3. Tarayıcıda `http://<kutu-ip>/` adresini açın. İlk açılışta sayfa parolasızdır.
   - Bir **yönetici parolası** belirleyin (kullanıcı adı: `admin`).
   - PTS adresini ve kutu anahtarını yazın.
   - Gerekirse sabit IP girin.
   - **Kaydet**'e basın. Kutu yeniden başlar.
4. Kutu sayfasında "PTS: bağlı" yazmalı. PTS'de kutu **Çevrimiçi** görünmeli.
5. **Bariyer** için PTS'de Bariyer → Yeni Bariyer Ekle → **HTTP Webhook** seçin.
   - URL: PTS'nin gösterdiği bariyer adresi (`http://<kutu-ip>/ac?anahtar=...`).
   - Metot: POST.
   - "Yetkili araç girişinde otomatik aç" kutusunu işaretleyin.

### HTTPS hakkında

PTS HTTPS ile çalışıyorsa PTS adresini `https://...` yazın. Bu durumda bağlantı
şifrelidir.

- **Sertifika alanını doldurursanız** kutu, sunucunun kimliğini de doğrular. Alana
  PTS'nin `/pts-ca.crt` dosyasının içeriği yapıştırılır.
- **IP adresiyle bağlanıyorsanız** sertifika alanını boş bırakın. ESP32'nin TLS
  kütüphanesi sertifikayı IP adresine göre doğrulayamaz. Bağlantı yine şifreli
  kalır, sayfa bunun için bir uyarı gösterir.

## 5. Masa başı deneme (sahaya çıkmadan)

1. Karta yazılımı yükleyin (bölüm 3), 12V verin, Ethernet'i takın.
2. Kutu sayfasını açın ve ayarları yapın (bölüm 4).
3. **Giriş denemesi:** IN1 ile GND arasına bir kabloyla kısa süre dokunun.
   - Sayfada "Girişler 1" yeşil yanmalı.
   - ~30 sn sonra PTS'de bir "okunamayan geçiş" görünmeli. O an kamera araç okumadığı için bu beklenen sonuçtur.
   - Denemeden sonra "Araç değil" deyip kapatın.
4. **Röle denemesi:** sayfada **Bariyeri şimdi aç**'a basın. Röle tık sesi çıkarır.
   COM-NO arası multimetrede kısa süre kısa devre görünür.
5. Hepsi çalışıyorsa kutuyu sahaya kurun. Önce yalnız döngü ve dedektör bağlanır,
   birkaç gün "okunamayan geçiş" sayısı izlenir. Bariyer sonra eklenir.

## 6. Sorun giderme

| Belirti | Bakılacak yer |
|---|---|
| Kutu sayfası açılmıyor | Ethernet ışığı, IP adresi (seri ekranda `DURUM`) |
| "PTS anahtarı reddetti" | Kutudaki anahtar PTS'deki ile aynı mı, kutu PTS'de Aktif mi |
| "PTS'ye bağlanılamadı" | PTS adresi ve port, güvenlik duvarı (8000), http/https doğru mu |
| Giriş ışığı yanmıyor | Loop dedektörü röle çıkışı, GND bağlantısı, dedektör ayarı |
| Her araçta "okunamayan geçiş" | PTS'deki giriş-kamera eşlemesi, kamera saati, kamera gerçekten okuyor mu |
| Bariyer açılmıyor | Kutu sayfasında "Bariyeri şimdi aç" ile röle denemesi, bariyer kartının START girişi |

Ayarları silmek için kutu sayfasındaki **Fabrika ayarlarına dön** düğmesini
kullanın ya da seri ekrana `SIFIRLA` yazın.

## 7. Donanım olmadan deneme

```
python kapi_kutusu/araclar/sahte_kutu.py --pts https://127.0.0.1:8000 --anahtar <ANAHTAR>
```

Enter'a her basışta "araç geçti" gönderir. Bariyer adresi olarak
`http://127.0.0.1:8090/ac?anahtar=<ANAHTAR>` verilirse PTS'nin açma komutu
ekrana düşer.

## Geliştirici notları

- `src/mantik.*`: karar veren bütün mantık burada. Standart C++ ile yazıldı,
  bilgisayarda test edilir:
  `g++ -std=c++17 -Wall -Wextra -Werror -I src test/test_mantik.cpp src/mantik.cpp -o t && ./t`
- `src/main.cpp`: donanım katmanı (I2C, Ethernet, web sayfası, gönderim görevi).
- `src/kart.h`: pinler. KC868-A8M'de SDA/SCL yer değiştirir. A8v3 farklı bir karttır.
- PTS tarafı: `backend/main.py` içindeki "KAPI KUTUSU" bölümü.
