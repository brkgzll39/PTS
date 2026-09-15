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
- **Görsel/kayıt saklama süresi**: Sistem `goruntuler/` klasöründeki araç görsellerini
  otomatik silmez. KVKK uyumluluğu için belirlediğiniz saklama süresine göre eski
  görselleri ve kayıtları düzenli temizleyen bir bakım rutini oluşturmanız önerilir.
- **HTTPS**: PTS varsayılan olarak düz HTTP ile yerel ağda çalışır. İnternete açık veya
  güvenilmeyen bir ağda çalıştıracaksanız IIS/nginx gibi bir ters vekil (reverse proxy)
  arkasında TLS sonlandırması yapılandırın; kimlik bilgileri ve oturum anahtarları
  şifresiz ağda taşınmamalıdır.
- **Yedekleme**: SQL Server kullanıyorsanız düzenli veritabanı yedeği (SQL Server Agent
  bakım planı) kurun. SQLite kullanıyorsanız `veritabani/pts.db` dosyasını düzenli
  olarak yedekleyin.

## Sorun Giderme

- **"ModuleNotFoundError" hatası**: `pip install -r requirements.txt` komutunu
  `backend` klasörü içindeyken çalıştırdığınızdan emin olun.
- **Port zaten kullanımda hatası**: `uvicorn main:app --port 8001` ile farklı bir
  port deneyin, ardından `http://localhost:8001` adresine gidin.
- **Veritabanını sıfırlamak isterseniz**: `veritabani/pts.db` dosyasını silin,
  sunucuyu yeniden başlattığınızda boş bir veritabanı otomatik oluşturulur.
