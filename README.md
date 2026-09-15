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
