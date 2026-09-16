# PTS - Plaka Tanıma Sistemi

Localhost üzerinde çalışan, tarayıcıdan erişilen tam bir Plaka Tanıma Sistemi (PTS) paneli.

## Özellikler

- **Plaka kayıtları takibi**: Her geçişi tarih/saat, kamera, yön ve yetki durumuyla kaydeder.
- **Abone / Personel / Ziyaretçi yönetimi**: Ekleme, düzenleme, aktif/pasif yapma, silme. Ziyaretçiler için otomatik süre kontrolü (süresi dolan ziyaretçi plakası "süresi dolmuş" olarak işaretlenir).
- **Otomatik yetki kontrolü**: Gelen her plaka, kişi listesiyle karşılaştırılır; yetkili/yetkisiz/süresi dolmuş durumu otomatik belirlenir.
- **LED panel entegrasyonu**: Simülasyon, Seri Port (RS232/USB) veya TCP/IP üzerinden mesaj gönderimi. Panel arayüzünden ayarlanabilir ve test edilebilir.
- **Geçmişe dönük kayıt görüntüleme**: Plaka, tarih aralığı ve yetki durumuna göre filtreleme.
- **Excel dışa aktarma**: Kayıtlar ve kişi listesi `.xlsx` olarak indirilebilir.
- **PDF dışa aktarma**: Filtrelenmiş kayıt listesi PDF olarak, tekil kayıtlar ise araç görseliyle birlikte PDF olarak indirilebilir.
- **Web paneli**: `http://localhost:8000` adresinden tarayıcıyla erişilir, kurulum gerektirmez (sadece tarayıcı yeterli).
- **Opsiyonel gerçek kamera entegrasyonu**: RTSP + YOLO + EasyOCR ile gerçek ANPR pipeline'ı hazır (isteğe bağlı, ağır bağımlılıklar gerektirir).

## Klasör Yapısı

```
pts_sistemi/
├── backend/
│   ├── main.py              # FastAPI uygulaması ve tüm API uç noktaları
│   ├── database.py          # SQLite bağlantısı
│   ├── models.py            # Veritabanı tabloları
│   ├── schemas.py           # API veri doğrulama şemaları
│   ├── excel_export.py      # Excel (.xlsx) üretimi
│   ├── pdf_export.py        # PDF üretimi (görsel dahil)
│   ├── led_panel.py         # LED panel gönderim modülü
│   ├── camera_reader.py     # Opsiyonel gerçek ANPR/RTSP pipeline
│   ├── ornek_veri.py        # Demo verisi ekleme scripti
│   ├── requirements.txt
│   └── config.json          # (otomatik oluşur) LED ayarları burada saklanır
├── frontend/
│   ├── index.html           # Panel arayüzü
│   ├── app.js                # Tüm API bağlantıları / arayüz mantığı
│   └── style.css
├── goruntuler/               # Araç görselleri buraya kaydedilir
├── disa_aktarilanlar/        # Üretilen Excel/PDF dosyaları buraya kaydedilir
├── veritabani/                # (otomatik oluşur) pts.db SQLite dosyası
├── calistir.bat              # Windows için başlatma scripti
└── calistir.sh                # Linux/Mac için başlatma scripti
```

## Kurulum ve Çalıştırma

### Profesyonel Windows Kurulumu

Kurulum paketi üretmek için önce [Inno Setup 6](https://jrsoftware.org/isdl.php)
kurun, ardından `installer\build_setup.bat` dosyasını çalıştırın. Oluşan
`installer\output\SPY-PTS-Setup.exe` paketi program klasörünü, masaüstü ve başlat
menüsü kısayollarını oluşturur. Hedef bilgisayarda kurulum sonrası Python ortamı
ve bağımlılıklar otomatik hazırlanır.

### SQL Server

Tek bilgisayar/demo kullanımı için SQLite fallback olarak kalır. Çok kameralı veya
çok kullanıcılı kurulumda SQL Server Express önerilir. SQL Server ODBC Driver 18
kurulu olmalıdır. Kurulumdan sonra şu komutla bağlantıyı ayarlayın:
```bash
cd backend
python veritabani_ayarla.py --sunucu "localhost\\SQLEXPRESS" --veritabani PTS --kullanici pts_app
```
Parola komut satırında görünmez ve bağlantı bilgisi `database_config.json` içinde
yerel olarak saklanır. Üretim ortamında bu dosyaya erişim kısıtlanmalıdır.

### Windows
1. Python 3.12 kurulu olduğundan emin olun ([python.org](https://python.org)).
2. `uv` kurun: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
3. Proje klasörünü hedef bilgisayara kopyalayın.
4. `kurulum.bat` dosyasına çift tıklayın.
5. Kurulumdan sonra `calistir.bat` dosyasına çift tıklayın.
6. Tarayıcıdan **http://localhost:8000** adresini açın.

`calistir.bat`, bağımlılıkları proje içindeki `.venv` sanal ortamına kurar. Python
3.12 kullanılması, sabitlenmiş FastAPI/Pydantic paketlerinin Windows üzerinde
uyumlu hazır paketlerle kurulmasını sağlar.

Başka bilgisayara taşırken `backend`, `frontend`, `goruntuler`, `disa_aktarilanlar`,
`veritabani`, `calistir.bat`, `kurulum.bat` ve `README.md` birlikte kopyalanmalıdır.
`.venv` klasörünü kopyalamak gerekmez; `kurulum.bat` hedef bilgisayarda yeniden oluşturur.
İlk açılışta yönetici hesabı oluşturulur, ardından Lisans sekmesinden o bilgisayara
özel üretilmiş lisans anahtarı aktive edilir.

### Linux / macOS
```bash
cd pts_sistemi
./calistir.sh
```
Ardından tarayıcıdan **http://localhost:8000** adresine gidin.

### Manuel Kurulum (her iki platform)
```bash
cd pts_sistemi/backend
pip install -r requirements.txt
uvicorn main:app --reload
```

### Örnek/Demo Veri Eklemek (opsiyonel)
Sistemi hemen denemek isterseniz birkaç örnek abone/personel/ziyaretçi eklemek için:
```bash
cd pts_sistemi/backend
python ornek_veri.py
```
Bu, `34 ABC 123` gibi örnek plakalar ekler. Ardından panelde **Test Kaydı Ekle**
sekmesinden bu plakayı girip "yetkili" olarak tanındığını görebilirsiniz.

## Panel Sekmeleri

| Sekme | Ne işe yarar |
|---|---|
| **Panel** | Genel istatistikler (toplam/bugünkü kayıt, yetkisiz deneme sayısı, aktif kişi sayısı) ve son kayıtlar |
| **Kayıtlar** | Tüm geçiş kayıtlarını plaka/tarih/durum bazında filtreleme, Excel/PDF indirme |
| **Kişiler** | Abone, personel, ziyaretçi ekleme/düzenleme/silme |
| **LED Panel** | Bağlantı modu (Simülasyon/Seri/TCP) ayarı ve test mesajı gönderme |
| **Test Kaydı Ekle** | Gerçek kamera olmadan manuel plaka kaydı oluşturup sistemi test etme |
| **Site / Erişim Noktası** *(sadece yönetici)* | Yerleşke (site) tanımlama ve her erişim noktasını (nokta) bir kameraya ve bir bariyere bağlama — olay detayındaki "Bariyer Aç" butonu bu bağlantıyı kullanır |

## Rol Bazlı Yetkilendirme (RBAC)

Sistemde üç rol var, hem backend (her yazma uç noktasında `_rol_dogrula()`) hem
de panel arayüzünde (`data-rol-min` özniteliği + `rolYeterli()` — bkz.
`frontend/app.js`) aynı politikayı uygular:

| Rol | Yetkisi |
|---|---|
| **izleyici** | Sadece okuma: kayıtları, kameraları, kişileri, kara listeyi görüntüleyebilir. Hiçbir yazma/silme/bariyer açma işlemi yapamaz. |
| **operatör** | Günlük operasyon: kişi/kara liste/kamera/bariyer/LED kaydı ekleyip düzenleyebilir, bariyer açabilir, test kaydı oluşturabilir. Kullanıcı yönetimi, sistem ayarları, lisans, webhook ve site/nokta topolojisi gibi yönetimsel işlemlere erişemez. |
| **yonetici** | Tam yetki: yukarıdakilerin hepsi + kullanıcı yönetimi, sistem ayarları, lisans aktivasyonu, webhook yapılandırması, veritabanı yedeği, site/nokta yönetimi. |

Panel tarafında yetkisiz bir aksiyon için buton/form tamamen gizlenir ya da
devre dışı bırakılır (backend zaten aynı isteği 403 ile reddeder — arayüz
kısıtlaması sadece kullanıcı deneyimi içindir, gerçek güvenlik sınırı
backend'deki `_rol_dogrula()` kontrolüdür).

## Gerçek ANPR Kamera Bağlama

İki seçenek var:

**1) Kameranın kendi ANPR motorunu kullanmak (önerilen, daha az kaynak tüketir):**
Çoğu ticari ANPR kamerası (Hikvision, Dahua vb.) plakayı kendi içinde okuyup event olarak
gönderebilir. Kameranızın ayarlarından tespit sonucunu şu adrese POST edecek şekilde
yapılandırın:
```
http://<bu-bilgisayarın-yerel-ip'si>:8000/kayitlar/otomatik
```
Form alanları: `plaka_no`, `kamera_id`, `yon`, `guven_skoru` (opsiyonel), `gorsel` (opsiyonel, dosya).

**2) Kendi Python pipeline'ınızı çalıştırmak:**
`backend/camera_reader.py` dosyasında RTSP video akışını FastALPR motoruyla
(`backend/anpr_engine.py`) tespit edip okuyan hazır bir iskelet var. Kullanmak için:
```bash
pip install "fast-alpr[onnx]" opencv-python requests
```
Ardından dosyanın en üstündeki örneğe göre `KameraPipeline` sınıfını başlatın.
Türk plaka formatına göre doğrulama (`plaka_dogrula` fonksiyonu) ve tekrar filtreleme
(aynı plakayı 30 saniye içinde tekrar bildirmeme) dahildir.

Kamera bağlamadan önce tek bir araç/plaka fotoğrafıyla pipeline'ı uçtan uca test
edebilirsiniz:
```bash
cd backend
python -c "from camera_reader import tek_gorsel_test; tek_gorsel_test('arac_fotografi.jpg')"
```
Bu, FastAPI sunucusu çalışıyorken tespit edilen plakayı gerçekten `/kayitlar/otomatik`
uç noktasına gönderir ve panelde görünmesini sağlar.

### Canlı Görüntü: Gerçek Zamanlı Akış (2026-09-16)

Panel eskiden canlı kamera karesini 3 saniyede bir ayrı bir HTTP isteğiyle
"anlık görüntü" (snapshot) olarak çekiyordu — bu, doğası gereği kesikli/adım
adım görünüyordu. Artık `GET /kameralar/{id}/akis` uç noktası üzerinden TEK bir
bağlantı üzerinden gerçek zamanlı MJPEG akışı (`multipart/x-mixed-replace`)
sağlanıyor: pipeline'ın ürettiği HER yeni kare (tipik olarak ~4 FPS'e kadar,
ANPR motorunun işleme hızına bağlı) sunucu tarafında üretildiği an istemciye
iletiliyor; istemci de kareyi anında ekrana yansıtıyor. Tarayıcının `<img>`
etiketi özel başlık (Authorization) taşıyamadığı için akış, `/olaylar/sse` ile
aynı yöntemle (token'lı `fetch()` + elle ayrıştırma) tüketiliyor
(`frontend/app.js`: `_kameraAkisiBaslat`). Kare sınırları her zaman
`Content-Length` başlığıyla belirlendiği için (ikili veri içinde sınır dizisi
aranmıyor), bir JPEG'in içinde tesadüfen sınıra benzeyen baytlar olsa bile akış
bozulmuyor.

### Birden Fazla Kamera ve GPU Kararlılığı

`fast-alpr[onnx-directml]` (Windows'ta GPU hızlandırması) kuruluysa, plaka
tespiti/OCR modelleri GPU üzerinde (DirectML) çalışır. **Tüm kameralar TEK bir
ANPR motorunu (dolayısıyla tek bir GPU oturumunu) paylaşır ve her çıkarım
çağrısı serileştirilir** — böylece kaç kamera bağlı olursa olsun GPU'ya aynı
anda yalnızca tek bir istek gider. Bu, ikinci bir kamera eklendiğinde
gözlemlenen bir GPU sürücüsü çökmesi/sıfırlanması sorununu (onnxruntime
`DXGI_ERROR_DEVICE_HUNG` hatası, ardından bozuk veri hataları ve bazı
donanımlarda tüm sistemin donup kendini yeniden başlatması) önlemek için
eklendi — kök neden, her kameranın kendi bağımsız GPU oturumunu açıp aynı
anda GPU'ya iş göndermesiydi.

GPU sürücünüz/donanımınız hâlâ kararsızsa (ör. eski sürücü, düşük VRAM),
çıkarımı tamamen CPU'ya zorlayabilirsiniz:
```bash
set PTS_ANPR_PROVIDERS=cpu   # Windows (cmd)
$env:PTS_ANPR_PROVIDERS="cpu"  # Windows (PowerShell)
```
Birkaç kamera için CPU'da çalıştırmak tipik olarak yeterince hızlıdır (canlı
görüntü zaten periyodik JPEG anlık görüntüsü olarak akıyor, gerçek zamanlı
video işleme değil). Ayrıca GPU sürücünüzü güncel tutmanız önerilir —
DirectML tabanlı çoklu-model iş yükleri eski sürücülerde daha sık kararsızlık
gösterir.

## Tanıma Doğruluğu: Ticari ANPR Seviyesine Yaklaşma

Piyasadaki ticari ANPR sistemleri gerçek koşullarda genelde **%90-98**,
kontrollü/optimum koşullarda ise **%99'a yaklaşan veya aşan** doğruluk
bildiriyor ([Carmen Cloud](https://carmencloud.com/anpr-accuracy-unveiled-how-reliable-is-automatic-number-plate-recognition/)).
Bunu belirleyen faktörlerin başında —yazılımdan önce— **kamera donanımı ve
kurulumu** geliyor: plaka görüntüde en az 50-75 piksel genişliğinde olmalı,
kamera-araç mesafesi mümkünse 40 metrenin altında tutulmalı, yatay/dikey açı
45 derecenin altında olmalı ve gece/gündüz için yeterli (tercihen IR)
aydınlatma bulunmalı ([Controlware, "ANPR: %65'ten %99.5'e"](https://www.controlware.com.au/blog-news/apnr-and-how-to-go-from-65-to-995-accuracy)).
**Bu koşullar yazılımla telafi edilemez** — kamerayı yeniden bağladığınızda
konum/açı/aydınlatmayı bu ölçütlere göre ayarlamanız, PTS'nin ulaşacağı
doğruluk tavanını doğrudan belirleyecektir.

Yazılım tarafında, kamera hazır olana kadar da devreye girecek şekilde,
doğruluğu artıran iki teknik eklendi:

**1) Çok kareli oy birleştirme ("frame consolidation")** — `backend/camera_reader.py`
içindeki `PlakaOturumTakipcisi`. Bir araç kamerada birkaç kare boyunca
görünür; tek bir kötü karenin OCR hatasına güvenmek yerine, aynı aracın (veya
birbirine çok yakın okumaların) TÜM okumaları bir "geçiş oturumunda" toplanır
ve ağırlıklı çoğunluk oyu kazanır. Düşük güvenli tek kareler (`min_tanima_guveni`
ayarının altındakiler, varsayılan 0.4) oylamaya hiç girmez. Bu, ticari ANPR
sistemlerinin tek kareye göre çok daha yüksek doğruluk elde etmesinin başlıca
tekniklerinden biridir.

**2) Bilinen plakaya göre OCR düzeltmesi (veritabanı çapraz kontrolü)** —
`backend/metin_araclari.py` + `backend/main.py::_bilinen_plakaya_yakinlik_duzelt`.
Site girişi gibi KAPALI bir plaka evreninde, "veritabanı çapraz kontrolü"
(database cross-referencing) doğruluğu artıran bilinen bir tekniktir (bkz.
yukarıdaki Carmen Cloud kaynağı). OCR düşük güvenle tek bir karakteri yanlış
okusa bile (örn. "34 ABC 128"), sahada kayıtlı bilinen bir plakayla ("34 ABC 123")
tek karakter farkı varsa ve başka hiçbir aday bu kadar yakın değilse, o
plakaya düzeltilir. **Güvenlik sınırları:** düzeltme SADECE erişim vermek
için çalışır, kara listeye asla uygulanmaz; zaten yüksek güvenli (≥%90)
okumalara hiç dokunulmaz; birden fazla bilinen plaka eşit derecede yakınsa
(belirsiz durum) düzeltme yapılmaz. Bir düzeltme uygulandığında hem ham OCR
metni hem düzeltilmiş plaka kayıtta ayrı ayrı saklanır (denetlenebilirlik
için) ve panelde olay detayında "OCR DÜZELTMESİ" satırında görünür. Sistem
Ayarları'ndan `bilinen_plaka_duzeltme_aktif` ile kapatılabilir.

Her ikisi de Sistem Ayarları panelinden ayarlanabilir (`min_tanima_guveni`,
`bilinen_plaka_duzeltme_aktif`); ayrıca `tests/test_metin_araclari.py` ve
`tests/test_camera_reader.py` içinde, gerçek kamera olmadan da doğrulanabilen
kapsamlı testleri var (eşleşen/eşleşmeyen okumalar, belirsizlik durumu,
eşik altı okumaların elenmesi, vb.).

## Kamera Bağlantı Güvenilirliği

Bu bölüm, kamera bağlantılarının/araç geçişi görüntülerinin donmaması için yapılan
sağlamlaştırma çalışmasını özetler.

**Bulunan ve düzeltilen kritik hata:** `backend/camera_reader.py` dosyası bozuk bir
kopyalama nedeniyle içeriğini iki kez barındırıyordu ve bu yüzden **Python
tarafından import edilemiyordu** (`SyntaxError`). `main.py` bu import hatasını sessizce
yutup `_CAM_LIBS = False` yapan bir `try/except` içinde çalıştığı için sistem hiçbir
zaman gerçek bir kamera pipeline'ı başlatamıyordu — opencv/fast-alpr kurulu olsa bile.
Muhtemelen yaşanan "kamera bağlanmıyor / görüntü hiç gelmiyor" sorunlarının kök nedeni
budur. Dosya temizlenip yeniden yazıldı; artık hatasız import ediliyor.

**Ayrıca eklenen sağlamlaştırmalar:**
- **Thread sızıntısı düzeltmesi**: Eskiden her yeniden bağlanmada eski kare-okuyucu
  thread hiç durdurulmuyor, kapatılmış bağlantı üzerinde sonsuza kadar dönmeye devam
  ediyordu. Artık her bağlantının bir "nesli" var; eski nesil thread'ler yeni bağlantı
  açılınca kendiliğinden ve temiz şekilde sonlanıyor.
- **Görüntü donması (frozen image) tespiti**: `pipeline_calisiyor=true` artık tek başına
  yeterli sayılmıyor — pipeline son karenin üzerinden ne kadar süre geçtiğini
  (`son_kare_yasi_sn`) izliyor ve gerçekten donmuş mu (`donmus`) diye ayrı raporluyor.
  Eskiden TCP bağlantısı açık kalıp görüntü aslında donmuş olsa bile arayüzde hâlâ
  "Canlı" yazabiliyordu.
- **Otomatik kendi kendini iyileştirme (watchdog)**: `main.py` içine her 20 saniyede bir
  çalışan bir kamera bekçisi eklendi. Pipeline thread'i beklenmedik şekilde çökerse
  (örn. yakalanmamış bir istisna) veya kamera uzun süre (90 sn+) donuk kalırsa, bekçi
  bunu tespit edip otomatik olarak yeniden başlatır ve gerekirse Alarmlar listesine
  "Kamera arızası" kaydı düşer — operatörün fark etmesi beklenmeden.
- **Log entegrasyonu**: Kamera modülündeki tüm çalışma zamanı olayları artık
  `print()` yerine uygulamanın kendi logger'ı üzerinden `loglar/pts.log` dosyasına
  yazılıyor (sorun giderme için tek yer).
- **Bellek hijyeni**: Tekrar-filtreleme için tutulan "son görülen plaka" sözlüğü
  artık periyodik olarak budanıyor; çok uzun süre (günler/haftalar) kesintisiz
  çalışan kurulumlarda yavaş bellek büyümesini önler.

**Yeni API alanları** (`/kameralar`, `/kameralar/{id}/saglik`, `/kameralar/saglik/tumu`):
`son_kare_yasi_sn` (son karenin saniye cinsinden yaşı), `donmus` (bool),
`yeniden_baglanma_sayisi`, `calisma_suresi_sn`, ve özet `durum` alanı
(`canli` | `donmus` | `bagli_degil` | `kapali`). Panel arayüzü (Kamera Yönetimi
tablosu ve Canlı İzleme kamera duvarı) bu alanları kullanarak "Görüntü Donmuş"
uyarısını turuncu bir rozet/banner ile gösterir.

**Kamera olmadan doğrulama:** Fiziksel kamera bağlı değilken bu değişiklikler kısa bir
sentetik video dosyasını "kamera" gibi kullanan bağımsız bir test betiğiyle uçtan uca
doğrulandı: video bilerek EOF'a düşürülüp kesinti/donma simüle edildi, pipeline'ın
otomatik yeniden bağlandığı, hiçbir thread'in sızmadığı (eşzamanlı okuyucu thread
sayısı hep 1'de kaldı) ve tespit edilen plakanın gerçek bir HTTP sunucusuna başarıyla
POST edildiği doğrulandı. Gerçek kamerayı taktığınızda aynı davranışı
`/kameralar/{id}/saglik` ve panel üzerinden gözlemleyebilirsiniz.

## Bu Sürümde Bulunan ve Düzeltilen Diğer Hatalar

Kamera modülündeki kritik hatayı ararken aynı sınıftan iki hata daha bulundu —
üçü de "bir dosyanın/bloğun yanlışlıkla iki kez yazılıp ikinci kopyanın ilkini
sessizce ezmesi" örüntüsüne sahip. Şeffaflık için burada listeleniyor:

- **`backend/schemas.py` — saat/gün bazlı erişim özelliği tamamen çalışmıyordu.**
  `KisiOlustur`, `KisiGuncelle`, `KisiCevap` ve `KullaniciCevap` şemaları dosyada
  yanlışlıkla iki kez tanımlanmıştı. Python bir sınıfın ikinci tanımını hatasız
  şekilde birincinin üzerine yazar; dosyanın sonundaki (eksik) ikinci tanımlar
  kazanıyordu. Sonuç: veritabanı modeli, `_plaka_yetki_kontrol` iş mantığı ve
  arayüz (Kişi ekleme formundaki saat/gün seçimi) bu özelliği tam destekliyor
  olmasına rağmen, API katmanı `giris_saati_baslangic`, `giris_saati_bitis` ve
  `izin_verilen_gunler` alanlarını ne kabul ediyor ne de geri döndürüyordu —
  yani "sadece 08:00–18:00 arası" veya "sadece hafta içi" gibi bir kısıtlama
  panelden hiçbir zaman gerçek olarak kaydedilemiyordu. Şemalar temizlendi;
  bu özelliğin gerçekten çalıştığı `tests/test_api.py::test_saat_disi_erisim_yetkisiz_sayilir`
  ile doğrulandı.
- **`GET /auth/me` iki kez tanımlanmıştı** (`mevcut_kullanici` ve `beni_getir`).
  Davranışı etkilemiyordu (FastAPI ilk kaydı kullanıyordu) ama ikinci tanım
  kod tabanında kafa karıştırıcı, asla çalışmayan ölü koddu; kaldırıldı.
- **`README.md` dosyasının sonunda bozuk, UTF-16 kodlamalı bir bayt dizisi vardı**
  (muhtemelen bir düzenleme aracının kodlama hatası). Dosya bu yüzden bazı
  araçlarda metin yerine "ikili (binary) dosya" olarak algılanabiliyordu.
  Temizlendi.

Bu üçü de derlemeyi/çalışmayı engellemiyordu (schemas.py ve README.md için
Python/Markdown hata vermeden "çalışıyormuş gibi" görünüyordu) — bu yüzden fark
edilmeleri zordu. `tests/test_schemas.py::test_schemas_dosyasinda_tekrarlanan_sinif_tanimi_yok`
artık bu spesifik hata sınıfının (aynı isimde tekrar sınıf tanımı) schemas.py'de
bir daha sessizce geri dönmemesini garanti eder.

## Panel Denetiminde Bulunan ve Düzeltilen Sorunlar (2026-09-15)

Kamera fiziksel olarak bağlanana kadar panelin profesyonel kullanıma hazır
olup olmadığı denetlendi. Bulunan ve düzeltilen sorunlar:

- **RBAC (rol bazlı yetkilendirme) fiilen yoktu.** Arayüz "izleyici / operatör
  / yönetici" rollerini belgeliyordu ama backend'de kullanıcı yönetimi, sistem
  ayarları, DB yedeği ve görüntü temizleme dışındaki HİÇBİR yazma uç noktası
  rol kontrolü yapmıyordu — giriş yapmış olmak yetiyordu. Somut sonucu:
  "izleyici" (salt okunur) rolündeki bir kullanıcı bile bariyer açabiliyor,
  kamera silebiliyor, lisans aktive edebiliyordu. `_rol_dogrula()` yardımcı
  fonksiyonu eklenip ~20 uç noktaya uygulandı; panel tarafında da aynı
  politika `data-rol-min` özniteliği ve `rolYeterli()` ile birebir uygulandı
  (bkz. yukarıdaki "Rol Bazlı Yetkilendirme" bölümü). `tests/test_api.py`'de
  üç uçtan uca RBAC testiyle doğrulandı.
- **"Bariyer Aç" butonu sahte bir `alert()` idi.** Olay detayı penceresindeki
  buton hiçbir gerçek bariyeri açmıyor, sadece "gönderildi" diye bir mesaj
  kutusu gösteriyordu — çünkü kameralar (JSON dosyası) ile bariyerler (SQL
  tablosu) arasında hiçbir veri bağlantısı yoktu. `Nokta` modeli `kamera_id`
  ve `bariyer_id` alanlarıyla genişletildi, yeni "Site / Erişim Noktası"
  sekmesi bu bağlantıyı kurmayı sağlıyor, buton artık gerçekten
  `POST /bariyer/{id}/ac` çağırıyor (bağlı bariyer yoksa açıkça "bağlı bariyer
  yok" diyor, sahte başarı mesajı göstermiyor).
- **Ölü/sahte arayüz alanları kaldırıldı.** Olay detayında hiçbir zaman
  doldurulmayan MARKA/MODEL/RENK alanları (sistemde araç görsel tanıma yok,
  sadece plaka OCR var) ve hardcoded "OTOPARK: Genel" / tekrarlanan
  "SİTE: Genel tesis" metinleri kaldırıldı; SİTE alanı artık kameranın bağlı
  olduğu gerçek `Nokta`/`Site` kaydından geliyor.
- **Sürüm numarası tutarsızlığı düzeltildi.** Kenar çubuğu "v1.0" gösteriyordu,
  backend (`FastAPI(version=...)`) "2.0" döndürüyordu; ikisi eşitlendi.
- **Yan menüde aynı sekmeye giden 3 ayrı bağlantı vardı** ("Geçiş Kayıtları",
  "Geçiş Raporu", "Veri Aktarımı" — üçü de `#kayitlar-sekme`). Gereksiz
  tekrar kaldırıldı, tek bağlantı kaldı.

## Fiziksel Kamera Bağlantısı Sonrası Bulunan ve Düzeltilen Sorunlar (2026-09-16)

- **Konsolda tekrarlayan sahte 401 hatası.** `sseBaslat()` içinde kullanılmayan,
  hiçbir zaman çalışmayan bir `new EventSource('/olaylar/sse', {})` çağrısı
  vardı. Tarayıcının `EventSource` API'si özel başlık (Authorization) taşıyamaz,
  bu yüzden bu istek her zaman 401 ile reddediliyor ve konsolu kirletiyordu.
  Gerçek SSE mekanizması zaten token'lı `fetch()` ile ayrı bir yolla
  (`_sseBaslatFetch`) çalışıyordu; ölü kod kaldırıldı.
- **Tam ekranda kamera görüntüsü kırpılıyordu.** Canlı kamera karesi
  `object-fit: cover` ile gösteriliyordu; bu tam ekranda görüntünün kenarlarını
  kırpıyordu. Tam ekran modunda (`:fullscreen`) `object-fit: contain` uygulanacak
  şekilde CSS düzeltildi, artık tüm kare siyah kenarlıklarla görülüyor.
- **H.264 kameralarda geçişlerde takılma → RTSP'yi TCP'ye zorlama denendi,
  sahada bazı kameralarda BAŞKA bir soruna yol açtı (2026-09-16 güncellemesi).**
  OpenCV'nin FFmpeg RTSP istemcisi varsayılan olarak UDP kullanıyor; H.264'te
  tek bir kayıp UDP paketi tüm GOP'u bozabiliyor. İlk düzeltmede
  `OPENCV_FFMPEG_CAPTURE_OPTIONS` ile RTSP her zaman TCP'ye zorlanmıştı; ancak
  bazı kamera/ağ/NAT kombinasyonlarında RTSP-üzerinden-TCP hiç desteklenmiyor
  veya kararsız çalışıyor — bu da "İlk bağlantı açılamadı" / sık yeniden
  bağlanma döngüsüne, hatta bir geçişin hiç yakalanamamasına yol açabiliyordu.
  Bu yüzden transport zorlama artık **varsayılan değil**; yalnızca
  `PTS_RTSP_TRANSPORT=tcp` (veya `udp`) ortam değişkeniyle açıkça istenirse
  etkinleşir, aksi halde FFmpeg'in kendi (genelde UDP) varsayılanı kullanılır.
  Soket zaman aşımı (`stimeout`) ve azami gecikme (`max_delay`) ayarları —
  transport'tan bağımsız, güvenli faydalar — her koşulda uygulanmaya devam
  ediyor. Kameranız TCP'yi sorunsuz destekliyorsa ve asıl amaç olan
  takılma/donmayı azaltmak istiyorsanız bu değişkeni açıkça ayarlayabilirsiniz;
  ama varsayılan olarak zorlanmıyor çünkü bağlantıyı İYİLEŞTİRECEĞİNE
  KÖTÜLEŞTİRDİĞİ görüldü.
- **"DB Yedek" butonu "Bearer token gerekli" hatası veriyordu.** `veritabaniIndir()`
  fonksiyonu `window.open("/sistem/yedek", "_blank")` kullanıyordu; bu yeni bir
  sekme/üst düzey gezinme başlattığı için `apiCagir()`'ın normalde
  `sessionStorage`'daki token'dan eklediği `Authorization: Bearer ...` başlığını
  TAŞIMIYORDU, backend de haklı olarak reddediyordu. Düzeltme: dosya artık
  token başlığıyla `fetch()` edilip blob olarak indiriliyor (gerçek bir dosya
  indirme butonu gibi çalışıyor, sekme açıp hata göstermiyor). Not: bu özellik
  yalnızca SQLite için çalışır; SQL Server kullanan kurulumlarda backend zaten
  açık bir "SQL Server için veritabanı yönetim araçlarını kullanın" hatası
  döner — bu beklenen bir davranıştır, hata değildir.

## "Araç net görünüyor ama hiç kayda düşmüyor" — Tanı Kabiliyeti (2026-09-16)

Sahada, plakası tamamen okunaklı görünen araçların hiçbir iz bırakmadan
(ne hata, ne kayıt) kaybolduğu vakalar bildirildi. Sorun şu ki, tespit
zincirinde birkaç nokta TAMAMEN SESSİZCE atlıyordu — hiçbir log satırı
bırakmadan:

- OCR bir metin okudu ama Türk plaka formatına uymadı (`plaka_dogrula` None
  döndü) → artık `logger.info` ile loglanıyor (okunan ham metin + güven skoruyla).
- Format olarak geçerli bir plaka okundu ama güven skoru `min_tanima_guveni`
  eşiğinin altında kaldı → artık loglanıyor.
- Pipeline, tespit edilen plakayı `/kayitlar/otomatik`'e POST etti, istek
  sunucuya ULAŞTI (bağlantı hatası yok) ama sunucu HTTP 4xx/5xx ile reddetti
  → önceden bu durum hiç kontrol edilmiyor, sessizce "gönderildi" sayılıyordu;
  artık HTTP durum kodu kontrol ediliyor ve reddedilirse loglanıyor.

Bu üçü sayesinde bir sonraki "araç göründü ama kayda düşmedi" vakasında
Sistem/Log ekranı kaybın nerede olduğunu (OCR yanlış okudu mu, güven düşük mü,
yoksa API mi reddetti) gösterir — AMA bu üçü de yalnızca dedektörün BULDUĞU
adaylar üzerinde çalışır (bkz. bir sonraki madde).

**~~Olası bağımsız neden — kamera açısı/çözünürlüğü~~ (2026-09-16: bu teşhis
YANLIŞ ÇIKTI, düzeltiliyor):** Önceki bir sürümde burada, giriş/çıkış
kameralarının geniş açılı kadrajının plakayı dedektör için "çok küçük"
kıldığı ve bunun kamera konumlandırma/zoom değişikliği gerektirdiği
belirtilmişti. Sahadan gelen kanıt bu teşhisi çürüttü: AYNI kameralardan AYNI
video akışını işleyen bağımsız bir başka yazılım (üçüncü taraf bir PTS
istemcisi), tam olarak sorun yaşadığımız plakaları (ör. "06 FVV 494") dahil
olmak üzere sorunsuz okuyabiliyor — hem giriş hem çıkış kamerasında. Bu,
kameranın fiziksel görüş açısının/çözünürlüğünün YETERLİ olduğunu, sorunun
kamerada değil YAZILIM tarafında (bizim dedektör/eşik yapılandırmamızda)
olması gerektiğini kanıtlıyor. Kamerada zoom/konum değişikliği YAPILAMAYACAĞI
(ve zaten gerekmediği) için bu öneri tamamen geri çekilmiştir.

**Gerçek neden adayı — dedektörün kendi (gizli) güven eşiği:** `_kareyi_isle`
içindeki üç log noktası da yalnızca FastALPR'ın `ALPR.predict()` metodunun
DÖNDÜRDÜĞÜ sonuçlar üzerinde çalışır. Ancak FastALPR'ın kendi YOLO tabanlı
plaka DEDEKTÖRÜ, kendi dahili `detector_conf_thresh` eşiğinin (kütüphane
varsayılanı: **0.4**) altında kalan aday kutuları OCR'a hiç göndermeden
tamamen eler — bu durumda `predict()` o kare için doğrudan BOŞ liste döner ve
yukarıdaki üç log noktasının HİÇBİRİ tetiklenmez (loglayacak hiçbir "sonuç"
yoktur). Önceki kod tabanında bu eşik hiç açığa çıkarılmıyordu (sabit/örtülü
0.4). Bu, "kamera görüntü akıyor, araç net görünüyor, hiçbir hata/log yok,
yine de kayda düşmüyor" şikayetinin en olası açıklamasıdır: bizim özel kamera
açı/mesafe/aydınlatma koşullarımızda dedektörün ürettiği ham güven skoru
0.4'ün altında kalıyor olabilir (üçüncü taraf yazılımın kendi dedektörü farklı
bir model/eşik kullandığı için aynı karede başarılı olabiliyor).

Bunu doğrulamak/ayarlamak için iki araç eklendi:

1. **`PTS_ANPR_DETECTOR_ESIGI` ortam değişkeni** (bkz. `backend/anpr_engine.py`):
   dedektörün `detector_conf_thresh` değerini geçersiz kılar. Örn.
   `PTS_ANPR_DETECTOR_ESIGI=0.15` ile sunucuyu yeniden başlatıp aynı araçların
   geçişini tekrar deneyin. Not: bu, `min_tanima_guveni` (Sistem Ayarları'ndaki
   OCR-sonrası eşik) ile KARIŞTIRILMAMALI — ikisi tamamen farklı, art arda
   çalışan iki filtredir; bu yenisi daha ÖNCE (dedektör aşamasında) devreye
   girer. Motor tüm kameralar arasında PAYLAŞILDIĞI için bu değer yalnızca
   sunucu (yeniden) başlarken okunur, çalışırken değiştirilemez.
2. **"Boş tespit" özet logu** (bkz. `camera_reader.py::BOS_TESPIT_LOG_ARALIK_SN`):
   dedektör art arda hiçbir aday bulamazsa en fazla 2 dakikada bir Sistem/Log
   ekranında özet bir satır görünür. Bu her zaman normaldir (trafiksiz an);
   ama net görünen bir aracın geçtiği ANDA bu log satırı sürekli görünüyorsa,
   dedektörün gerçekten hiçbir şey bulamadığının (yukarıdaki hipotezin)
   doğrulanmış kanıtıdır — bu durumda `PTS_ANPR_DETECTOR_ESIGI`'yi düşürmek
   doğru adımdır.

**2026-09-16 sahadan doğrulama:** Bu iki araç sahada devreye alındıktan hemen
sonra, çıkış kamerasının önünde ~30 saniye bekleyen ve plakası ekran
görüntüsünde net okunan bir araç ("34 MSJ 048") yine kayda düşmedi. Sistem/Log
ekranı, o aracın kamerada bulunduğu TÜM 2 dakikalık pencerede ("Son 120 sn
içinde dedektör 384 karede hiçbir plaka adayı bulamadı") dedektörün gerçekten
SIFIR aday bulduğunu doğruladı — yani sorun OCR'da/güven eşiğinde/API'de değil,
tam olarak yukarıda öngörülen dedektör aşamasında. Bu, "boş tespit" logunun
kendisinin artık teşhis için yeterli olduğunu ve bir sonraki adımın
`PTS_ANPR_DETECTOR_ESIGI` ile eşiği kademeli düşürüp denemek olduğunu
gösteriyor.

**Ham kare teşhis kaydı (eşik düşürmek yetmezse):** `PTS_ANPR_DETECTOR_ESIGI`
düşürmek sorunu çözmezse, sorun eşikte değil başka bir yerde olabilir (plaka
bölgesi kareye hiç girmiyor, çözünürlük çok düşük, kameranın kendi görüntü
işleme ayarları görüntüyü aşırı bozuyor vb.). Bunu KÖR bir şekilde eşik
deneyerek değil, dedektöre GERÇEKTEN giden ham kareyi gözle görerek anlamak
için `PTS_HAM_KARE_KAYIT_DIZINI` ortam değişkenini bir dizin yoluna ayarlayın
(örn. `PTS_HAM_KARE_KAYIT_DIZINI=C:\pts_ham_kareler`). Ayarlıysa, dedektörün
hiçbir aday bulamadığı kareler (yani "boş tespit" logunu tetikleyen TAM OLARAK
aynı kareler) o dizine kamera başına en fazla 5 saniyede bir JPEG olarak
kaydedilir (disk şişmesin diye kamera başına en fazla 300 dosya tutulur,
eskiler otomatik silinir). Varsayılan olarak KAPALIDIR; yalnızca teşhis
sırasında açılması, sorun netleşince kapatılması önerilir.

## Kalıcı Test Altyapısı

`tests/` klasöründe pytest tabanlı bir test paketi var:

- `test_plaka_dogrula.py`, `test_lisans.py`, `test_schemas.py`, `test_camera_reader.py`:
  bağımlılığı hafif (fastapi/sqlalchemy gerektirmez), yalnızca pydantic/opencv/requests
  yeterlidir.
- `test_api.py`: FastAPI `TestClient` + geçici bir SQLite veritabanı kullanarak
  kimlik doğrulama, plaka yetki kontrolü (yetkili/yetkisiz/kara liste/süresi
  dolmuş/saat kısıtlaması), lisans aktivasyonu ve kamera limiti gibi uçtan uca
  akışları test eder. Gerçek bir kurulumun `license.json`/`cameras.json`
  dosyalarını ezmemesi için bu dosyaların yolu `PTS_LICENSE_FILE` /
  `PTS_CAMERAS_FILE` / `PTS_SISTEM_AYARLARI_FILE` ortam değişkenleriyle test
  sırasında geçici bir dizine yönlendirilir (bkz. `tests/conftest.py`).

Çalıştırmak için:
```bash
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
pytest
```

`.github/workflows/tests.yml` bu paketi her `push`/pull request'te otomatik
çalıştırır — camera_reader.py'nin import edilemez hale geldiği veya
schemas.py'de bir sınıfın yanlışlıkla tekrar tanımlandığı türden bir regresyon
artık sessizce main dalına giremez.

## Üretim Güvenliği Sertleştirmeleri

- **CORS**: Varsayılan olarak artık hiçbir çapraz kaynağa (cross-origin) izin
  verilmiyor (panel zaten aynı sunucudan servis edildiği için buna ihtiyaç
  yok). Panele başka bir origin'den erişilmesi gerekiyorsa `PTS_CORS_ORIGINS`
  ortam değişkenine virgülle ayrılmış origin listesi yazın.
- **Hız sınırlama (rate limiting)**: `/auth/giris` (kullanıcı adı bazlı
  kilitlemeye ek olarak IP başına dakikada 20 deneme) ve `/kayitlar/otomatik`
  (kimlik doğrulaması olmayan, kameraların doğrudan POST ettiği tek uç nokta;
  IP başına dakikada 120 istek) artık bellek-içi bir sınırlayıcıdan geçiyor.
  `/kayitlar/otomatik` için ayrıca `PTS_KAMERA_ANAHTARI` ortam değişkeniyle
  paylaşılan bir anahtar da zorunlu tutulabilir (zaten mevcut bir özellikti).
- **Kamera adresi doğrulama**: `/kameralar` artık yalnızca `rtsp://`, `rtsps://`,
  `http://`, `https://` şemalarını ve `giris`/`cikis` yönünü kabul ediyor.
- **HTTPS hatırlatması**: Uygulama açılışta, ters vekil (reverse proxy) arkasında
  TLS sonlandırması yapılandırılmadıysa bunu `loglar/pts.log`'a bir kez
  hatırlatma olarak yazar (zaten yapılandırdıysanız `PTS_ARKASINDA_TERS_VEKIL=1`
  ile susturabilirsiniz).
- **Kamera arızası bildirimi**: Kamera bekçisinin (watchdog) tespit ettiği uzun
  süreli arızalar artık mevcut webhook bildirim sistemine bağlı — Bildirimler
  sekmesinden "kamera_arizasi" tetikleyicili bir webhook (N8N/Slack/Teams/kendi
  API'niz) ekleyerek anlık haber alabilirsiniz.

**2026-09-16 profesyonellik/güvenlik denetimi — bu turda düzeltilenler:**

- **Stored XSS (kara liste/kişi plaka alanı):** `plaka_no` alanına eskiden yalnızca
  `.upper().strip()` uygulanıyordu; harf/rakam/boşluk dışındaki karakterler (`'`, `<`,
  `(`, `;` vb.) kabul ediliyordu. Frontend bu değeri bir zamanlar `onclick="fonksiyon('${...}')"`
  biçiminde bir HTML attribute'u içine JS string'i olarak gömdüğü için, kara listeye
  `"x');alert(1)//"` gibi bir "plaka" eklenip o satırı görüntüleyen bir yöneticinin
  oturumunda kod çalıştırılabiliyordu. Artık `schemas.py::plaka_normalize` TÜM giriş
  noktalarında (kişi/kara liste/otomatik kayıt) aynı karakter kısıtlamasını
  zorunlu kılıyor, VE frontend artık plaka değerini hiçbir yerde bir HTML attribute'u
  içine JS kodu olarak gömmüyor (`data-*` attribute + olay delegasyonu kullanılıyor).
- **`/goruntuler` artık kimlik doğrulaması gerektiriyor:** Araç/sürücü görselleri
  (plaka + fotoğraf — KVKK kapsamında kişisel veri) önceden tamamen kimliksiz bir
  `StaticFiles` mount'uyla servis ediliyordu; dosya adı kalıbı tahmin edilebilir
  olduğu için (`PLAKA_unixzaman.jpg`) ağdaki herkes giriş yapmadan indirebiliyordu.
  Artık `GET /goruntuler/{dosya_adi}` giriş yapmış kullanıcı gerektiren normal bir
  uç nokta (ayrıca yol geçişi/`..` denemelerine karşı da korumalı); `<img>` etiketi
  Authorization header taşıyamadığı için frontend bu görselleri `fetch()` + Bearer
  token ile alıp blob URL'ine çeviriyor.
- **RTSP kamera parolaları artık loglanmıyor + `/sistem/loglar` rol kısıtlı:**
  Kamera pipeline'ı başlarken `video_kaynagi` (kullanıcı adı/parola dahil RTSP
  adresi) olduğu gibi loglanıyordu; bu, aynı dosyadaki bilinçli parola maskeleme
  çabasını (panel/API'de) tamamen boşa çıkarıyordu. Artık log satırında da
  maskeleniyor, VE `/sistem/loglar` en az **operatör** rolü gerektiriyor (önceden
  salt-okunur "izleyici" bile okuyabiliyordu) — servis ederken de (diskte zaten
  duran eski log satırları için) ikinci bir maskeleme katmanı uygulanıyor.
- **SQL Server bağlantısı artık şifreli kuruluyor:** `veritabani_ayarla.py`
  önceden `Encrypt=no` kullanıyordu; backend ile SQL Server farklı makinelerdeyse
  kimlik bilgileri ve plaka/kişi verisi ağda düz metin taşınıyordu. Artık
  `Encrypt=yes` (+ kendinden imzalı sertifikalarla da çalışsın diye
  `TrustServerCertificate=yes`) kullanılıyor. **NOT:** bu yalnızca betiği YENİDEN
  çalıştırdığınızda etkilidir — mevcut bir kurulumu geriye dönük değiştirmez;
  zaten yapılandırılmış bir kurulumda `database_config.json`'ı elle güncelleyin
  ya da betiği tekrar çalıştırın.
- **Repo temizliği:** Referanssız, kaynağı belirsiz bir `backend.rar` arşivi
  (ilk commit'ten beri duruyordu, hiçbir yerden kullanılmıyordu) kaldırıldı;
  `.gitignore`'a `*.rar`/`*.zip` eklendi.

**2026-09-16 (devam) — "en kararlı ve düzgün" hale getirme turu:**

- **SQL Server bağlantı havuzu artık "sessizce ölmüş bağlantı" sınıfına karşı
  korumalı:** SQLAlchemy'nin varsayılan bağlantı havuzu, havuzdan aldığı bir
  bağlantının hâlâ canlı olduğunu doğrulamadan doğrudan kullanır. Kurumsal
  güvenlik duvarları/NAT'lar boşta kalan TCP bağlantılarını genelde uygulamaya
  hiçbir hata döndürmeden sessizce düşürür — sahada bunun tipik belirtisi
  "sistem bir süre sorunsuz çalışıyor, sonra rastgele hata vermeye başlıyor,
  yeniden başlatınca düzeliyor" şeklindedir. SQL Server URL'siyle çalışan
  kurulumlarda artık `pool_pre_ping=True` (bağlantı ödünç alınırken ucuz bir
  "SELECT 1" ile canlılık doğrulaması, ölüyse sessizce yenisiyle değiştirir) ve
  `pool_recycle=1800` (30 dakikadan uzun süredir havuzda bekleyen bağlantıları
  proaktif tazeler) etkin. SQLite kurulumlarını etkilemez.
- **Beklenmeyen hatalar artık görünür:** Daha önce, bizim bilerek fırlatmadığımız
  (yani bir `HTTPException` olmayan) bir hata FastAPI tarafından istemciye
  sızdırılmıyordu (bu zaten güvenliydi) ama sunucu tarafında da HİÇBİR YERE
  loglanmıyordu — yani "panel hata verdi" şikayeti geldiğinde `/sistem/loglar`
  ekranında bu hatanın hiçbir izi bulunamıyordu. Artık küresel bir hata
  yakalayıcı her beklenmeyen hatayı tam iz düşümüyle (traceback) uygulama
  logumuza yazıyor (`/sistem/loglar` üzerinden görülebilir) ve istemciye diğer
  tüm hatalarla tutarlı, bilgi sızdırmayan tek bir JSON gövdesi
  (`{"detail": "..."}`) dönüyor. İstek gövdesi doğrulama hataları (422) da aynı
  tutarlı biçimde dönüyor.
- **Pydantic V2 uyumluluğu:** `schemas.py`'deki tüm `class Config: from_attributes
  = True` blokları (9 adet), gelecekteki bir Pydantic sürümünde kaldırılacak olan
  eski (V1) sözdiziminden `model_config = ConfigDict(from_attributes=True)`'a
  taşındı — davranışta hiçbir değişiklik yok, sadece CI'da biriken 9 adet
  "deprecated" uyarısı ortadan kalktı.
- **Panel erişilebilirlik (a11y) düzeltmeleri:** Tüm modal kapatma butonlarına
  (`.btn-close`) `aria-label="Kapat"` eklendi (Bootstrap'in kendi belgelerinin
  önerdiği ama bu panelde eksik olan bir ayrıntı); ne görünür metni ne de bir
  `title`/`aria-label`'ı olan birkaç ikon-yalnızca buton (ör. "Son Geçişler"
  kartındaki yenile butonu, Siteler/Erişim Noktaları/Kara Liste/Kullanıcılar/
  Bildirimler listelerindeki yenile butonları, PDF indir butonu) artık erişilebilir
  bir isme sahip. Geçiş kayıtlarındaki küçük resim (thumbnail) önizlemeleri
  yalnızca fare tıklamasıyla büyütülebiliyordu (bir `<img>` öntanımlı olarak
  klavyeyle odaklanamaz/tetiklenemez); artık `role="button" tabindex="0"` ve bir
  klavye (Enter/Boşluk) olay dinleyicisiyle klavye/ekran okuyucu kullanıcıları
  için de erişilebilir.

## Otomatik Görüntü/Kayıt Saklama

Daha önce eski geçiş görüntülerini temizlemenin tek yolu `/sistem/goruntu-temizle`
uç noktasını manuel olarak çağırmaktı — bir operatör bunu unutursa disk sessizce
dolabilir, bu da (görüntü yazma hataları yüzünden) tıpkı bir kamera donması gibi
görünen bir "sistem takılması" belirtisine yol açabilirdi.

Artık uygulama açılışında arka planda sürekli çalışan bir görev, Sistem
Ayarları'ndaki **"Görüntü saklama süresi (gün)"** ayarını (varsayılan: 30 gün)
her 6 saatte bir kontrol edip bu süreden eski, görüntüsü olan kayıtların
dosyalarını otomatik olarak siler (kaydın kendisi veritabanında kalır, sadece
görüntü dosyası ve `goruntu_yolu` alanı temizlenir). Ayarı `0` yaparsanız
otomatik temizlik devre dışı kalır; manuel uç nokta yine de çalışmaya devam eder.
Bu işi hem manuel uç nokta hem de otomatik görev aynı paylaşılan fonksiyonu
(`_goruntu_temizle_calistir`) kullanarak yapar, böylece iki ayrı yerde
birbirinden farklı davranan iki kopya mantık oluşmaz.

## LED Panel Bağlama

`backend/led_panel.py` üç mod destekler:
- **simulate**: Donanım yok, mesajlar konsola/veritabanına yazılır (varsayılan, test için).
- **serial**: RS232/USB seri port. `pip install pyserial` gerektirir. Panelin COM portu ve baud rate bilgisini panel arayüzünden (LED Panel sekmesi) girin.
- **tcp**: Ethernet/WiFi üzerinden IP ile konuşan panel. IP adresi ve port bilgisini girin.

Kullandığınız LED panelin kendine özgü bir metin protokolü varsa (örn. başına/sonuna
özel komut baytları eklemek gerekiyorsa), `led_mesaj_gonder()` fonksiyonunu panelinizin
kullanım kılavuzuna göre uyarlamanız gerekebilir — iskelet hazır, sadece gönderim
formatını değiştirmeniz yeterli.

## Veri Formatı Notları

- Plakalar veritabanında büyük harfle saklanır; karşılaştırma yapılırken boşluklar
  yok sayılır, yani "34ABC123" ile "34 ABC 123" aynı kabul edilir.
- Ziyaretçi kayıtlarına bir **bitiş tarihi/saati** girilirse, bu süre geçtikten sonra
  o plaka otomatik olarak "süresi dolmuş" durumuna düşer (kişi kaydı silinmez,
  sadece geçiş anında bu durum tespit edilir).

## Lisans ve Canlı İzleme

Canlı İzleme sekmesi giriş ve çıkış kameralarını, son geçişleri ve sistem durumunu
tek ekranda gösterir. Lisans sekmesindeki cihaz kodu bu bilgisayara özgüdür.
Geliştirme/demo kurulumu için aşağıdaki anahtar kullanılabilir (4 kamera limitli,
herhangi bir cihazda çalışır, yalnızca varsayılan `PTS_LICENSE_SECRET` ile üretilmiştir):
```
PTS1.eyJsaXNhbnNfaWQiOiJERUYyNkJDRUIwMzBDNjczIiwibXVzdGVyaSI6IlBUUyBEZW1vIiwiY2loYXpfa29kdSI6bnVsbCwia2FtZXJhX2xpbWl0aSI6NCwiYmFzbGFuZ2ljX3RhcmloaSI6IjIwMjYtMDgtMzEiLCJiaXRpc190YXJpaGkiOiIyMDM2LTA4LTI4In0.9TjZviZsKE3ZHz0i5ivUQT4ZpAP1l6EnPn4kXsL_nL4
```
Bu anahtar yalnızca demo amaçlıdır ve varsayılan gizli anahtarla üretildiği için
üretimde güvenli sayılmaz. Gerçek kullanımda `PTS_LICENSE_SECRET` ortam değişkenini
kendi güçlü değerinizle değiştirin ve müşteriye özel anahtarları yalnızca o zaman üretin.

### Lisans Üretme

İmzalı müşteri lisansı üretmek için backend klasöründe şu komutu çalıştırın:
```bash
python lisans_uretici.py --musteri "ABC Site" --kamera 8 --gun 365
```
Üretilen anahtarı uygulamanın **Lisans** sekmesine girin. Belirli bir bilgisayara
bağlamak için `--cihaz` parametresine uygulamanın cihaz kodunu verebilirsiniz.
Gerçek dağıtımda `PTS_LICENSE_SECRET` ortam değişkenini lisans üretici ve doğrulama
sunucusunda aynı güçlü gizli değerle ayarlayın; varsayılan değer yalnızca geliştirme
içindir.

### ⚠️ 2026-09-16: Lisans Uygulaması Gerçekten Sıkılaştırıldı — Kurulumunuzu Kontrol Edin

Bu turda iki gerçek boşluk kapatıldı; ikisi de mevcut (zaten çalışan) kurulumların
davranışını DEĞİŞTİREBİLİR, o yüzden dikkatlice okuyun:

1. **`PTS_LICENSE_SECRET` ayarlanmamışsa artık çalışma zamanında UYARI loglanıyor**
   (`loglar/pts.log`, süreç başına bir kez) — önceden bu durumda sessizce
   kaynak kodda sabit/herkese açık bir geliştirme anahtarına düşülüyordu ve
   HİÇBİR uyarı yoktu. Eğer bu değişkeni hiç ayarlamadıysanız, üretimde
   MUTLAKA kendi güçlü değerinizi ayarlayın — aksi halde kaynağa erişimi olan
   biri geçerli imzalı bir lisans üretebilir.
2. **Lisans artık HER kontrolde yeniden doğrulanıyor, sadece aktivasyon anında
   değil.** Önceden `_lisans_aktif_mi()` yalnızca `license.json`'daki statik
   `"aktif": true` bayrağına ve ayrı bir `"bitis_tarihi"` kopyasına bakıyordu —
   bunlar aktivasyon SONRASI bir daha asla imzayla karşılaştırılmıyordu. Artık
   saklı `anahtar` alanının imzası (+ süre + cihaz kilidi) HER seferinde yeniden
   doğrulanıyor.
3. **Kamera bekçisi (watchdog) artık lisansı da periyodik kontrol ediyor.**
   Önceden lisans SADECE yeni bir kamera eklerken kontrol ediliyordu — mevcut
   kameralar bir lisans süresi dolduktan/geçersiz hale geldikten SONRA da
   sınırsız çalışmaya devam edebiliyordu. Artık her ~20 saniyede bir lisans
   geçerliliği kontrol ediliyor; geçersizse **TÜM kamera pipeline'ları otomatik
   durdurulur** ve bir arıza alarmı (webhook'a bağlıysa bildirim de) oluşturulur.
   **Bu, mevcut kurulumunuz için önemli:** lisansınızın bitiş tarihini şimdiden
   kontrol edin (Lisans sekmesi) — daha önce süre dolsa bile kameralar sessizce
   çalışmaya devam ediyordu, artık devam ETMEYECEK. Süresi yakında dolacaksa
   önceden yeni bir anahtar üretip aktive edin.

## ⚠️ KVKK Uyarısı

Plaka + görüntü kaydı Türkiye'de KVKK kapsamında **kişisel veri** sayılır. Bu sistemi
gerçek bir ortamda (site, işyeri vb.) kullanacaksanız:
- Görünür yerde aydınlatma metni/bilgilendirme tabelası bulundurun.
- Kayıt saklama süresini makul bir aralıkla sınırlayın ve net tanımlayın.
- Verilere erişimi sınırlı tutun ve erişim loglarını takip edin.

Bu konuda kesin uyumluluk için bir hukuk danışmanına başvurmanızı öneririz;
bu doküman yalnızca genel bilgilendirme amaçlıdır.

## Üretim Ortamı (Gerçek Kullanım) Notları

- **Günlükler**: Uygulama olayları (giriş denemeleri, sağlık kontrolü hataları vb.)
  `loglar/pts.log` dosyasına yazılır (5 MB'ta döner, son 5 dosya saklanır). Sorun
  giderme için önce bu dosyaya bakın.
- **Sağlık kontrolü**: `GET /saglik` uç noktası uygulamanın ve veritabanı bağlantısının
  çalıştığını doğrular; izleme araçlarında (uptime kontrolü vb.) kullanılabilir.
- **Giriş kilitleme**: Aynı kullanıcı adına 5 başarısız giriş denemesinden sonra
  15 dakika giriş kilitlenir (kaba kuvvet saldırılarına karşı).
- **Çökme sonrası otomatik yeniden başlatma**: `calistir.bat`, sunucu beklenmedik
  şekilde kapanırsa 5 saniye sonra otomatik olarak yeniden başlatır.
- **Bilgisayar açılışında otomatik başlatma**: Görev Zamanlayıcı'da "Oturum açıldığında"
  tetikleyicisiyle `calistir.bat` dosyasını çalıştıracak bir görev oluşturmanız önerilir;
  böylece bilgisayar yeniden başladığında PTS insan müdahalesi olmadan ayağa kalkar.
  **Daha sağlam bir alternatif (önerilir, 2026-09-16):** Görev Zamanlayıcı + açık
  konsol penceresi modelinin sınırları vardır — RDP oturumu kapanırsa veya konsol
  penceresi yanlışlıkla kapatılırsa süreç düşebilir, ve durumu `services.msc`'den
  görünmez. [NSSM](https://nssm.cc/) ile PTS'i gerçek bir Windows Servisi olarak
  kaydedebilirsiniz (yönetici olarak):
  ```bat
  nssm install PTS "C:\PTS\.venv\Scripts\python.exe" "-m uvicorn backend.main:app --host 0.0.0.0 --port 8000"
  nssm set PTS AppDirectory "C:\PTS"
  nssm set PTS Start SERVICE_AUTO_START
  nssm start PTS
  ```
  Bu şekilde PTS oturum açılmasa bile arka planda çalışır, çöktüğünde Windows
  Hizmet Yöneticisi otomatik yeniden başlatır ve durumu `services.msc`'den
  izlenebilir olur.
- **Görsel/kayıt saklama süresi (2026-09-16 düzeltmesi):** Bu bölüm önceden "Sistem
  `goruntuler/` klasöründeki araç görsellerini otomatik silmez" diyordu — bu artık
  DOĞRU DEĞİL ve koddan sapmıştı: sistem, Sistem Ayarları'ndaki `goruntu_saklama_gun`
  ayarına göre (varsayılan: **30 gün**) her 6 saatte bir eski görselleri/kayıtları
  OTOMATİK olarak siler (bkz. `main.py::_goruntu_temizlik_dongu`). Bu, varsayılan bir
  kurulumda operatör hiçbir ayar değiştirmeden görsellerin ~30 gün sonra sessizce
  silinebileceği anlamına gelir — bazı sahalarda kanıt/soruşturma amacıyla daha uzun
  saklama gerekebileceğinden, kurulumdan hemen sonra Sistem Ayarları'ndan bu süreyi
  ihtiyacınıza göre (veya tamamen kapatmak için 0'a) ayarlayın. Otomatik temizliğe ek
  olarak (veya onun yerine) manuel bir uç nokta da vardır (`/sistem/goruntu-temizle`).
- **HTTPS**: PTS varsayılan olarak düz HTTP ile yerel ağda çalışır. İnternete açık veya
  güvenilmeyen bir ağda çalıştıracaksanız IIS/nginx gibi bir ters vekil (reverse proxy)
  arkasında TLS sonlandırması yapılandırın; kimlik bilgileri ve oturum anahtarları
  şifresiz ağda taşınmamalıdır.
- **Yedekleme**: SQL Server kullanıyorsanız düzenli veritabanı yedeği (SQL Server Agent
  bakım planı) kurun. SQLite kullanıyorsanız `veritabani/pts.db` dosyasını düzenli
  olarak yedekleyin.
  **2026-09-16:** önceden sistem bu bakım planının GERÇEKTEN çalışıp çalışmadığını
  hiçbir şekilde izlemiyordu — plan hiç kurulmasa ya da sessizce başarısız olmaya
  başlasa bile PTS bunu asla fark etmiyordu. `PTS_SQL_YEDEK_KLASORU` ortam
  değişkenini bakım planının `.bak` dosyalarını yazdığı klasöre ayarlarsanız,
  Sistem sekmesi en son yedeğin ne zaman alındığını gösterir ve 2 günden eskiyse
  kırmızı bir uyarı işareti çıkarır (`GET /sistem/saglik` içindeki `yedek` alanı).
  Ayarlamazsanız davranış değişmez, bu satır panelde hiç görünmez.

## Sorun Giderme

- **"ModuleNotFoundError" hatası**: `pip install -r requirements.txt` komutunu
  `backend` klasörü içindeyken çalıştırdığınızdan emin olun.
- **Port zaten kullanımda hatası**: `uvicorn main:app --port 8001` ile farklı bir
  port deneyin, ardından `http://localhost:8001` adresine gidin.
- **Veritabanını sıfırlamak isterseniz**: `veritabani/pts.db` dosyasını silin,
  sunucuyu yeniden başlattığınızda boş bir veritabanı otomatik oluşturulur.
- **Bir düzeltme uyguladım ama hiçbir şey değişmemiş gibi görünüyor**: Bir
  yamayı (`git am ...`) uyguladıktan sonra iki ayrı adım daha gerekir, aksi
  halde eski davranış devam eder: (1) **Python sunucusunu (uvicorn) yeniden
  başlatın** — dosyadaki değişiklik diskte olsa bile, çalışan süreç hâlâ eski
  kodu bellekte tutar; `--reload` ile çalıştırmıyorsanız süreci tamamen durdurup
  tekrar başlatmanız gerekir. (2) **Tarayıcıda sayfayı SERT yenileyin**
  (Ctrl+Shift+R / Ctrl+F5), özellikle `app.js`/`style.css` değişen bir düzeltme
  için — 2026-09-16'dan itibaren statik dosyalar `Cache-Control: no-cache` ile
  sunuluyor (normal bir yenileme artık her zaman güncel sürümü getirmeli), ama
  bu tarihten önceki bir sürümü çalıştırıyorsanız veya tarayıcınız yine de eski
  bir kopyayı bellekte tutuyorsa sert yenileme kesin çözümdür. Aynı sekmeyi
  günlerdir hiç yenilemeden açık tutmak da (özellikle canlı kamera/DB yedek gibi
  JS tabanlı düzeltmeler için) aynı yanıltıcı "düzeltme çalışmıyor" görünümüne
  yol açar.
