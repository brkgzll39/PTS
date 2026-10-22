# PTS'i başka kurumlara kurmak (ürünleştirme rehberi)

2026-10-23. Bu belge PTS'in TPAO dışındaki kurumlara **kod değiştirmeden** nasıl
kurulacağını anlatır. Buradaki altyapının hepsi hazırdır ama **varsayılan olarak
kapalıdır**: `marka.json` dosyası olmayan ve modül listesi içermeyen bir lisansla
çalışan kurulum (bugünkü TPAO sistemi) hiçbir fark görmez.

## 1. Satıştan önce: hukuki kontrol listesi

Bunlar netleşmeden ürün satılmamalı.

- [ ] **Yazılımın sahipliği.** PTS, TPAO'da çalışırken ve kurum için geliştirildiyse
  Fikir ve Sanat Eserleri Kanunu md. 18 uyarınca haklar, aksi kararlaştırılmadıkça
  işverene ait sayılabilir. Bir avukata danışın; gerekirse kurumla yazılı anlaşma yapın.
- [ ] **Plaka bulma modeli lisansı.** Dedektör modelleri (open-image-models,
  `yolo-v9-*`) YOLOv9 tabanlıdır; YOLOv9'un orijinal kodu GPL-3.0 lisanslıdır.
  Ağırlıkların kapalı, ücretli bir üründe kullanım koşulunu netleştirin. Gerekirse
  kendi Türk plaka verinizle kendi modelinizi eğitin.
- [ ] **Diğer kütüphaneler** (FastAPI, SQLAlchemy, ReportLab, openpyxl, Bootstrap,
  Chart.js, qrcode-generator, IBM Plex): MIT/BSD/OFL, ticari kullanıma uygun.
  Lisans metinleri `frontend/vendor/*/LICENSE` altında; pakette kalmalı.
- [ ] **Marka.** TPAO adı/logosu müşteri paketine girmez (derleme bunu denetler,
  bkz. §3). Satışta TPAO'yu referans olarak anmak için kurumdan yazılı izin gerekir.
- [ ] **KVKK.** Müşteri veri sorumlusu, siz veri işleyensiniz. Veri işleme
  sözleşmesi ve aydınlatma metni şablonu hazırlayın. PTS tarafı hazır: görüntü
  saklama süresi, geçiş kayıtlarını anonimleştirme (`kayit_anonimlestirme_gun`),
  denetim kaydı, iki adımlı doğrulama, buluta veri göndermeyen kurulum.
- [ ] Şirket / fatura altyapısı; kamu ihaleleri için Yerli Malı Belgesi araştırması.

## 2. Ne hazır?

| Parça | Nerede | Varsayılan (bugünkü sistem) |
|---|---|---|
| Kurum adı, logo, iletişim, uygulama adı | `marka.json` → `backend/marka.py`, `GET /marka` | Dosya yok → TPAO |
| "VIP" kişi tipinin adı (panel/Excel/LED) | `marka.json`: `vip_adi`, `vip_etiketi` | Bölge Müdürü |
| LED bekleme yazısı | `marka.json`: `led_bekleme_yazisi(_2)` | T.P.A.O. / TRAKYA |
| Hazır vardiya çizelgesi | `marka.json`: `varsayilan_vardiya_cizelgesi` | Ekim 2026 (TPAO) |
| Kamera sayısı sınırı | lisans: `--kamera` | (zaten vardı) |
| Lisansla açılan modüller | lisans: `--modul` | Liste yok → hepsi açık |
| Müşteri paketinden TPAO izlerinin silinmesi | `installer/derle_windows.py` | Yalnız müşteri paketinde |
| Uzaktan güncelleme | `guncelle.ps1` | Hazır |
| Uzaktan izleme | `GET /saglik` | Hazır |

`marka.json` **varsa** eksik alanlar TPAO'dan değil kurumsuz değerlerden
(`marka.GENEL`) gelir: başka bir kurumda TPAO adı, telefonu ya da LED yazısı
hiçbir durumda görünmez. Bozuk bir `marka.json` da kurumsuz değerlere düşer.

### Modüller (`backend/lisans.py::MODULLER`)

| Modül | Kapalıyken |
|---|---|
| `led` | LED'e hiçbir şey gönderilmez; LED ayarı/testi 403 |
| `bildirim` | Telegram/webhook gönderilmez; bildirim ayarı/testi 403 |
| `mobil` | Mobil uygulama bildirim kaydı 403 |
| `arvento` | Arvento webhook'u 403 |
| `vardiya_cizelgesi` | Çizelge etiketlemesi yok (vardiya oturumları kullanılır); çizelge girişi 403 |
| `dahua_anpr` | Kameranın kendi ANPR okuması birleştirilmez |

Modül listesi imzalı lisans anahtarının içinden okunur; `license.json` elle
değiştirilerek modül açılamaz. Lisansta liste yoksa (eski lisanslar, kendi
sisteminiz) tüm modüller açıktır.

## 3. Yeni müşteri: adım adım

1. **Marka klasörü.** Depoda `musteriler/<musteri>/` oluşturun:
   `installer/marka-ornek.json`'u `marka.json` adıyla kopyalayıp doldurun, logoyu
   (PNG/SVG, yaklaşık 360x110) aynı klasöre koyun.
2. **Derleme.** GitHub → Actions → "Derlenmis Windows paketi" → *Run workflow* →
   `marka` alanına `musteriler/<musteri>`. (Elle: `python installer/derle_windows.py
   --cikti derlenmis --marka musteriler/<musteri>`.) Paket TPAO izi taşırsa derleme
   durur. `marka` boş bırakılırsa kurumsuz ("PTS") paket çıkar.
3. **Kurulum.** `PTS-Kurulum.exe` müşteri bilgisayarına kurulur. İlk açılışta ilk
   yönetici hesabı oluşturulur; panel "Lisans" ekranında **cihaz kodu** görünür.
4. **Lisans.** Kendi bilgisayarınızda:
   ```
   python araclar/lisans_araci.py uret --musteri "ACME A.Ş." --kamera 4 --gun 365 --cihaz <CIHAZ_KODU> --modul led --modul bildirim
   ```
   `--modul` hiç verilmezse tüm modüller açılır. Anahtarı panelden etkinleştirin.
5. **HTTPS ve güvenlik.** `python backend\sertifika_olustur.py --ip <tailscale/ek IP>`,
   `.env`'e `PTS_HTTPS=1`, `guvenlik_duvari.ps1 -EkIpler "..."`. Bilgisayarlar
   sertifikayı `https://<sunucu>:8000/pts-ca.crt`'den kurar.
6. **İzleme.** Dış izleme aracına `https://<sunucu>:8000/saglik` ekleyin,
   `"saglikli":true` aransın.

## 4. Sektör paketleri (önerilen modül setleri)

| Paket | Modüller | Durum |
|---|---|---|
| Kurumsal kampüs / fabrika / OSB | led, bildirim, vardiya_cizelgesi, arvento, dahua_anpr | Hazır (yalnız ayar) |
| Site / rezidans | bildirim, mobil, (led) | Hazır; daire başına araç kotası eklenebilir |
| Kamu / kritik tesis | led, bildirim, dahua_anpr | Hazır; Yerli Malı Belgesi |
| Ücretli otopark | — | Yeni modül gerekir: tarife, kasa, fiş |
| Lojistik / depo | — | Yeni modül gerekir: randevu, kantar |

Son iki paket, gerçek bir talep görülmeden yapılmamalı.

## 5. Fiyatlandırma ve satış (öneri)

- Giriş noktası / kamera başına kalıcı lisans + yıllık bakım-destek (lisansın
  %15-20'si) ya da yıllık abonelik. 30 günlük deneme lisansı (`--gun 30`).
- Satış kanalı: güvenlik kamerası / bariyer kuran sistem entegratörleri (bayilik).
- Sürekli gelir: `/saglik` ile uzaktan izleme ve `guncelle.ps1` ile bakım hizmeti.
- Konumlandırma: kendi sunucusunda çalışan, buluta veri göndermeyen, KVKK'ya
  uygun, Türk plakasına özel, mevcut kameralarla çalışan ve kameranın kendi
  okumasını birleştiren sistem.

## 6. Henüz yapılmayanlar

- İlk açılış sihirbazı (kurum adı/logo/kamera panelden). Şimdilik `marka.json`.
- Kapalı modüllerin sekmelerinin arayüzde gizlenmesi (şimdilik işlem 403 ile reddedilir).
- Temiz bir Windows'ta uçtan uca kurulum testi.
- Kurulum / kullanım videoları ve demo ortamı.
