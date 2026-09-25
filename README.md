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

### Kamera Olmadan Test: Bir Klasöre Fotoğraf Bırakarak Otomatik Kayıt (2026-09-16)

`tek_gorsel_test` her fotoğraf için elle bir komut çalıştırmanızı gerektirir. Kamera
bağlı değilken (ya da bağlıyken bile) birden fazla fotoğrafı tek tek komut yazmadan,
sadece bir klasöre SÜRÜKLEYİP BIRAKARAK sisteme "gerçek bir araç geçişi" gibi
kaydettirmek isterseniz, `PTS_GORSEL_IZLEME_DIZINI` ortam değişkenini bir klasöre
ayarlayın:
```bash
set PTS_GORSEL_IZLEME_DIZINI=C:\pts-fotograf-izleme   # Windows (cmd)
$env:PTS_GORSEL_IZLEME_DIZINI="C:\pts-fotograf-izleme"  # Windows (PowerShell)
```
Uygulama açılışında bu klasörü (yoksa) otomatik oluşturur ve her ~5 saniyede bir
tarar:

- Klasörün **doğrudan içine** bıraktığınız fotoğraflar **GİRİŞ** olarak,
- `cikis\` alt klasörüne bıraktıklarınız **ÇIKIŞ** olarak işlenir.
- İşlenen her fotoğraf (başarılı ya da başarısız) `islenenler\` alt klasörüne
  taşınır ki bir daha işlenmesin; tespit **başarısız** olduysa dosya adının başına
  `TESPIT_EDILEMEDI_` eklenir.
- Bir dosya, boyutu İKİ ARDIŞIK taramada aynı görülene kadar işlenmez (yarım
  kopyalanmış/bozuk bir dosyayı okumamak için kasıtlı bir gecikme) — yani bir
  fotoğrafın işlenmesi birkaç saniye sürebilir, bu normaldir.

Bu, gerçek bir kamera pipeline'ının kullandığı AYNI tespit + yetki kontrolü +
veritabanı kaydı + LED panel bildirimi yolunu kullanır — yani panelde tıpkı
gerçek bir kamera geçişiymiş gibi görünür. Ayrıca **"araç net görünüyor ama hiç
kayda düşmüyor"** türü sorunları kamera bağlamadan, elinizdeki gerçek/sorunlu
fotoğraflarla tekrar tekrar deneyerek teşhis etmek için de kullanışlıdır: bir
fotoğraf `TESPIT_EDILEMEDI_` ile işaretlenirse, `PTS_ANPR_DETECTOR_ESIGI`
değişkenini düşürüp aynı fotoğrafı `islenenler\` klasöründen tekrar izleme
klasörüne taşıyarak yeniden deneyebilirsiniz. Sistem sekmesindeki "Sistem Durumu"
paneli, klasör izlemenin aktif olup olmadığını gösterir.

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

**Kayıtlar panelinde "Doğrulama" sütunu (2026-09-17):** Kök neden düzeltmesi
sonrası (bkz. yukarıdaki Toplu Doğruluk Testi bölümündeki not) sistem artık
gerçekten plaka tespit etmeye başlayınca, sahada şu kafa karıştırıcı durum
gözlemlendi: bir araç doğru okunup ("39 SU 877") kaydolduktan hemen sonra,
AYNI aracın bir başka karesinde OCR yanlış okuyup ("04 SD 377", %86 güven)
bunun da AYRI bir kayıt olarak panele düşmesi — çünkü metin farkı oturum
birleştirme eşiğinden (Levenshtein ≤2) büyük olduğu için ayrı bir "oturum"
sayılıyor ve tek bir okumayla (başka hiçbir kare doğrulamadan) doğrudan
kesinleşiyor. Bu YANLIŞ bir tespit değil (dedektör/OCR görevini yapıyor),
ama panelde iki farklı plaka görünmesi operatörün kafasını karıştırıyor.

Kaydı sessizce SİLMEK yerine (bu, nadir de olsa gerçekten TEK bir karede
görünüp geçen bir aracın kaydını da yok edebilir — güvenlik açısından kabul
edilemez), her kayda artık kaç FARKLI karede tekrarlanıp doğrulandığı bilgisi
eklendi: `PlakaOyBirikimi.toplam_kare_sayisi` (kamera pipeline'ından API'ye
`dogrulama_kare_sayisi` alanıyla gönderilir, `plaka_kayitlari` tablosunda
saklanır). Kayıtlar tablosunda yeni bir "Doğrulama" sütunu bunu gösterir:

- **⚠ 1 kare** (turuncu): bu okuma yalnızca TEK bir karede yapıldı, başka
  hiçbir karede doğrulanmadı — yanlış okuma ihtimali daha yüksektir,
  operatör bu kayda dikkatli yaklaşmalı.
- **✓ N kare** (yeşil, N≥2): N farklı karenin oydaşmasıyla kesinleşti — daha
  güvenilir.
- **-**: kamera pipeline'ından gelmeyen kayıt (manuel giriş veya bu özellik
  eklenmeden önceki eski kayıtlar) — uygulanamaz.

Hiçbir kayıt gizlenmez/silinmez; operatör panelde ikisini de görüp kendi
değerlendirmesini yapabilir. `tests/test_camera_reader.py` içinde hem
`toplam_kare_sayisi`in doğru sayıldığını (tek okuma, tekrarlanan okuma, farklı
varyantların oydaşması) hem bu değerin API isteğine gerçekten eklendiğini
doğrulayan regresyon testleri var.

**"Plaka Analizi" ekranında tam düzenleme, notlar ve manuel kayıt (2026-09-17,
devam):** Yukarıdaki "Doğrulama" sütunu sadece BİLGİ veriyordu — bir operatör
"04 SD 377" gibi yanlış okunmuş bir kaydı görünce bunun üzerinde hiçbir şey
yapamıyordu. Artık hem "Kayıtlar" tablosunda hem de bir plakaya tıklanınca
açılan "Plaka Analizi" penceresinde şu işlemler var:

- **Tam düzenleme**: bir geçiş kaydının plakası, yönü, yetki durumu, kişi
  eşleştirmesi ve notu panelden değiştirilebilir (`PATCH /kayitlar/{id}`,
  `operatör`+ yetkisi gerekir). Yanlış OCR okumasıyla oluşmuş bir kayıt artık
  silinmeden DÜZELTİLEBİLİR. Kim, ne zaman değiştirdi her zaman kayıtta tutulur
  (`duzenleyen`/`duzenleme_tarihi`) — bu alanlar panelden asla doğrudan set
  edilemez, yalnızca uç nokta tarafından otomatik doldurulur. Bir kaydın kalıcı
  olarak silinmesi (`DELETE /kayitlar/{id}`) `yönetici` yetkisiyle sınırlı.
- **Geçiş kaydı notu (`not_metni`)**: bu tekil geçişe özel, tek seferlik bir
  not (örn. "teslimat aracı, güvenlik onayıyla alındı"). Kişinin KENDİ
  profilindeki kalıcı notla (`Kisi.aciklama`, personel/abone/ziyaretçi
  formlarında zaten mevcuttu) karıştırılmamalı — biri kişiye, diğeri bu tekil
  geçişe ait.
  Kayıtlar tablosunda artık görsel ve Doğrulama sütunlarının yanına düzenle/sil
  ikonları da eklendi (rol bazlı görünürlük: düzenleme `operatör`+, silme
  yalnızca `yönetici`).
- **"Manuel Kayıt Ekle"**: Plaka Analizi ekranından, bir görevlinin elle içeri
  aldığı (örn. yetkisiz görünen ama güvenlik onayıyla geçirilen) bir aracı
  doğrudan bu plaka için, yön ve not seçerek kaydedebilmesini sağlayan bir
  form. Oluşan kayıt `manuel_giris=True` bayrağıyla ve panelde "Manuel"
  etiketiyle işaretlenir, kamera pipeline'ından gelen kayıtlarla asla
  karıştırılmaz.
- **Görseller Plaka Analizi'nde de görünür**: önceden bu ekran yalnızca metin
  tablosu gösteriyordu; artık her satırda (varsa) araç görseli de aynı
  korumalı (token'lı fetch + blob URL) yöntemle yükleniyor, "Kayıtlar"
  tablosundakiyle birebir aynı bileşen kullanılarak.

Güvenlik tasarımı burada da aynı: hiçbir düzenleme/silme işlemi sessiz veri
kaybına yol açmaz — silme yalnızca en yüksek yetkiyle ve geri alınamaz olduğu
açıkça belirtilerek yapılabilir, düzenlemeler ise her zaman denetim izi
bırakır. `tests/test_api.py` içinde bu uç noktalar için RBAC (operatör/izleyici/
yönetici sınırları), alan doğrulama (geçersiz `yetki_durumu`, olmayan kayıt/
kişi) ve `/kayitlar/analiz/{plaka_no}` yanıtının yeni alanları eksiksiz
döndürdüğünü doğrulayan testler eklendi.

**⚠️ 2026-09-17 (devam) — ACİL DÜZELTME: `manuel_giris` sütunu canlı SQL
Server'da GET /kayitlar'ı 500'e düşürüyordu.** Yukarıdaki özellik teslim
edildikten hemen sonra, kullanıcının gerçek üretim ortamında (SQL Server)
`GET /kayitlar` `ResponseValidationError` ile çöktü: `manuel_giris` alanı 50
kayıtta `null` geldi. Kök neden, SQLite ile SQL Server'ın **aynı** ALTER
TABLE ifadesine (`ADD manuel_giris BIT DEFAULT 0`) FARKLI davranmasıydı:

- **SQLite**'ta bir `DEFAULT`'lu `ADD COLUMN`, tablodaki VAR OLAN satırları da
  otomatik olarak o değerle doldurur.
- **SQL Server**'da ise sütun NULL kabul ediyorsa (NOT NULL verilmediği için
  ediyordu) ve ifadeye açıkça `WITH VALUES` eklenmedikçe, `DEFAULT` yalnızca
  BUNDAN SONRA eklenecek satırlara uygulanır — tabloda hâlihazırda var olan
  TÜM satırlarda bu alan NULL kalır. Test paketi yalnızca SQLite kullandığı
  için bu fark hiçbir testte yakalanamadı; `schemas.KayitCevap.manuel_giris`
  ise `bool` (Optional değil) olduğundan Pydantic bu `null` değerleri
  doğrulayamayıp isteğin TAMAMINI 500'e düşürüyordu (tek bir bozuk kayıt değil,
  aynı sayfadaki TÜM kayıtlar).

İki katmanlı düzeltme yapıldı: (1) `_veritabani_migrasyon()`'daki ALTER TABLE
ifadelerine SQL Server için `WITH VALUES` eklendi (yeni kurulumlar artık
doğru davranacak) VE kullanıcının veritabanındaki gibi HALİHAZIRDA NULL olan
satırları düzelten `UPDATE plaka_kayitlari SET manuel_giris = 0 WHERE
manuel_giris IS NULL` adımı her başlangıçta koşulsuz (idempotent) çalıştırılıyor;
(2) savunma katmanı olarak `schemas.KayitCevap`'a bir `field_validator`
eklendi — `manuel_giris` her ne sebeple NULL gelirse gelsin (bu migrasyon
adımından bağımsız olarak) artık `False`'a çevrilip API asla çökmüyor.
`tests/test_api.py`'ye, ORM'i atlayıp doğrudan SQL ile `manuel_giris=NULL`
olan bir kayıt ekleyen ve `GET /kayitlar`'ın hâlâ 200 döndüğünü doğrulayan bir
regresyon testi eklendi; düzeltme ayrıca gerçek Pydantic modeliyle (fastapi
olmadan, sadece pydantic kullanılarak) bu sandbox'ta da elle doğrulandı.

**⚠️ 2026-09-17 (devam) — Aynı araç aynı dakikada hem "giriş" hem "çıkış"
olarak İKİ kayda düşüyordu: kameraların görüş açıları örtüşüyordu.**
Kullanıcı, panelde "39 AEL 670" plakalı bir aracın aynı dakikada hem giriş
kamerasından "Giriş", hem de nizamiye kapısı kamerasından "Çıkış" olarak iki
ayrı kayda düştüğünü bildirdi. Kameraların fiziksel olarak birbirinden ayrı,
farklı noktalarda olduğu doğrulandıktan sonra kullanıcı gerçek kök nedeni
kendisi tespit etti: **giriş ve çıkış kameralarının ikisinin de açısı,
kendi şeridinin yanı sıra KOMŞU şeridi de görecek şekilde ayarlıydı** —
yani giriş yapan bir araç çıkış kamerasının görüş alanına da giriyor (ve
"çıkış" olarak kaydediliyor), çıkış yapan araç da aynı şekilde giriş
kamerasına yansıyıp "giriş" olarak kaydediliyordu. Bu, kamera açılarının
fiziksel olarak yeniden hizalanmasını gerektirmeden, YAZILIMSAL olarak da
çözülebilecek bir sorun: her kameraya, yalnızca kendi şeridini kapsayan bir
**tespit alanı (ROI — region of interest)** tanımlanarak komşu şeritteki
araçların o kameranın kaydına hiç düşmemesi sağlanabilir.

İki yeni yetenek eklendi:

- **Kamera Yönünü Yerinde Değiştirme (`PATCH /kameralar/{id}/yon`).**
  Önceden yanlış yapılandırılmış bir kameranın yönünü (giriş/çıkış)
  düzeltmenin TEK yolu kamerayı SİLİP RTSP adresini (ve varsa parolasını)
  elle yeniden yazarak baştan eklemekti. Ama panel, güvenlik gereği RTSP
  adresindeki parolayı istemciye asla düz metin göndermiyor (bkz.
  `_kamera_guvenli_gorunum`) — yani operatör parolayı not almadıysa/
  hatırlamıyorsa kamerayı siler silmez o bağlantıyı yeniden kuramaz hale
  gelebilirdi. Bu yeni uç nokta yalnızca `yon` alanını değiştirir; kameranın
  `id`'si, RTSP adresi ve parolası hiç değişmeden kalır. Panelde Kameralar
  sekmesindeki her satırın Yön hücresi artık (operatör/yönetici için) tek
  tıkla değiştirilebilen bir açılır listeye dönüştü.
- **Tespit Alanı Sınırlama / ROI (`PATCH /kameralar/{id}/roi`).** Her
  kameraya, kare boyutunun YÜZDESİ (0-100, çözünürlükten bağımsız) cinsinden
  bir dikdörtgen (`x1,y1,x2,y2`) tanımlanabiliyor. Bir tespitin bu alanın
  içinde sayılıp sayılmayacağına, kutunun TAMAMININ içeride olup olmadığına
  değil, MERKEZ NOKTASININ içeride olup olmadığına bakılarak karar veriliyor
  (bir araç ROI sınırına yakınsa kutusu sınırı kısmen aşabilir; merkez nokta
  testi bu durumda daha isabetli). ROI dışında kalan tespitler, çok-kareli oy
  birikim sistemine (`PlakaOturumTakipcisi`) HİÇ girmiyor — yani API'ye asla
  ulaşmıyor, panelde hiç görünmüyor. Panelde Kameralar sekmesinde yeni bir
  "Alan Sınırı" (makas ikonlu) düğme, kameranın CANLI görüntüsünü gösteren bir
  modal açıyor; operatör bu modalda 4 sayısal alanı (X1/Y1/X2/Y2, yüzde)
  değiştirdikçe görüntü üzerinde sarı bir dikdörtgen önizlemesi anlık olarak
  güncelleniyor — böylece gerçek trafiği izleyerek gözle kalibrasyon
  yapılabiliyor. Kamera pipeline'ının canlı önizleme karesinde de artık ROI
  sınırı (sarı çizgi) ve her tespit, ROI içinde mi dışında mı olduğuna göre
  yeşil/gri (ve "(alan dışı)" etiketiyle) renklendiriliyor. Bir kameranın ROI'si
  `temizle=true` gönderilerek tamamen kaldırılabiliyor.

Her iki uç nokta da yalnızca yönetici/operatör rolüne açık (izleyici 403
alır); değişiklik kamera etkinse pipeline'ı otomatik olarak yeniden başlatıp
uygulamaya alıyor. `tests/test_camera_reader.py`'ye ROI'nin yüzdeden piksele
doğru çevrildiğini, bir tespitin merkez noktasına göre içeri/dışarı
sınıflandırıldığını ve ROI dışındaki bir tespitin pipeline seviyesinde oy
birikimine ve API'ye HİÇ ulaşmadığını (buna karşılık ROI içindeki bir
tespitin normal şekilde ulaştığını) doğrulayan testler eklendi.
`tests/test_api.py`'ye de her iki uç nokta için RBAC (yönetici/operatör
izinli, izleyici 403), alan doğrulama (geçersiz yön değeri; eksik/0-100 dışı/
x1≥x2 veya y1≥y2 olan ROI değerleri; `temizle=true` ile mevcut bir ROI'nin
kaldırılması) ve olmayan kamera id'si için 404 dönüşünü doğrulayan testler
eklendi.

**2026-09-20 (devam) — Tespit alanı artık SERBEST ÇİZİM (polygon) olarak da
tanımlanabiliyor.** Kullanıcı geri bildirimi (birebir): "bir de alan sınırı
eklemiştik bu alan sınırına serbest çizim ekleme şansımız var mı kare
seçimde bazen farklı yönden geçen araçları da tespit ediyor bunu
istemiyorum". Bir şerit kameraya çapraz/eğik açıdan görünüyorsa, dikdörtgen
ROI şeridin bounding-box'ını (en geniş noktasını) kapsamak zorunda kaldığı
için komşu şeridi de içine alabiliyordu — dikdörtgenin köşeleri eksene
paralel olmak zorunda ama gerçek şerit sınırı çoğu zaman değil.

- **Yeni ROI biçimi:** `PATCH /kameralar/{id}/roi` artık `polygon` alanını da
  kabul ediyor — en az 3, en fazla 20 `{"x","y"}` (yüzde, 0-100) köşe
  noktası (bkz. `schemas.KameraRoiGuncelle`, `main.py::
  _roi_polygon_gecerlilestir`). Kaydedilen ROI o zaman
  `{"tip": "polygon", "noktalar": [...]}` biçiminde saklanıyor; eski
  dikdörtgen biçim (`{"x1","y1","x2","y2"}`, "tip" anahtarı YOK) hâlâ
  geçerli ve varsayılan — geriye dönük uyumluluk tamamen korunuyor,
  hâlihazırda kaydedilmiş hiçbir kameranın ROI'si bu değişiklikle bozulmuyor.
- **Ortak filtre/çizim altyapısı:** `camera_reader.py::_roi_ciz_bilgisi_hesapla`,
  ROI'nin tipine bakıp (dikdörtgen/polygon) ortak bir `(tip, şekil)` ikilisi
  üretiyor; hem oy-birikimi filtresi (`_kutu_roi_ciz_bilgisiyle_icinde_mi`)
  hem canlı önizleme çizimi (`_kare_uzerine_ciz`, artık `cv2.polylines` ile
  kapalı bir çokgen de çizebiliyor) AYNI hesaplamayı kullanıyor — eskiden
  olduğu gibi tutarsızlık riski yok. Polygon içeride-mi testi
  (`_kutu_polygon_icinde_mi`), standart "ray casting" (bir noktadan ışın
  gönderip çokgenin kaç kenarını kestiğini sayma) algoritmasıyla, ekstra bir
  geometri kütüphanesi (shapely vb.) GEREKMEDEN yapılıyor; yine tespit
  kutusunun MERKEZ noktasına bakılıyor (dikdörtgen ROI ile aynı ilke).
- **Yeni arayüz:** Tespit Alanı (ROI) modalına "Kare (Dikdörtgen)" / "Serbest
  Çizim" seçimi eklendi (varsayılan: Kare, mevcut davranış hiç değişmedi).
  Serbest Çizim seçilince, kameranın anlık görüntüsü üzerine bindirilen bir
  SVG katmanına (`viewBox="0 0 100 100"`, böylece tıklama koordinatı direkt
  yüzdeye karşılık geliyor) sırayla tıklanarak şeridin köşeleri işaretlenir;
  3. noktadan itibaren şekil sarı, yarı saydam bir çokgen olarak canlı
  önizlenir. "Son Noktayı Sil" ve "Temizle" düğmeleriyle düzeltme yapılabilir.
  Var olan bir polygon ROI'yi düzenlemek için modal açıldığında noktalar
  otomatik yüklenir (sıfırdan yeniden çizmeye gerek yok). Kameralar
  listesindeki "Alan sınırlı" rozeti de iki ROI tipini de doğru etiketliyor.

Testler: `tests/test_camera_reader.py`'ye (gerçekten çalıştırılıp doğrulandı)
piksel dönüşümü, ray-casting testi (basit bir kare için içeride/dışarıda/
geçersiz-şekil durumları), `_roi_ciz_bilgisi_hesapla`'nın "tip" anahtarı
olmayan eski kayıtları hâlâ dikdörtgen sayması, ve — en önemlisi — TAM DA
kullanıcının şikayet ettiği senaryoyu simüle eden iki uçtan-uca test eklendi:
bounding-box'ı komşu şeridi de kapsayacak kadar geniş olan çapraz bir şerit
polygon'u, sabit tespit kutusunu (dikdörtgen olsaydı YANLIŞLIKLA kabul
edilirdi) doğru şekilde REDDEDİYOR; aynı polygon'un tespitin gerçekten
olduğu tarafı kapsayan bir varyasyonu ise normal şekilde KABUL EDİYOR.
`tests/test_api.py`'ye (fastapi gerektirdiği için yalnızca `py_compile` ile
doğrulandı) polygon ile kaydetme/temizleme, 3'ten az veya 20'den fazla nokta
ile 400, 0-100 dışı koordinatla 400, ve izleyici için 403 testleri eklendi.

**2026-09-17 (devam) — Panel ve Kayıtlar sekmeleri artık araç geçişinde
KENDİLİĞİNDEN yenileniyor.** Önceden gerçek zamanlı SSE bağlantısı yalnızca
Panel'deki "canlı olaylar" küçük listesini ve bir toast bildirimini anlık
güncelliyordu; Panel'in sayaçları (toplam/bugünkü/yetkisiz giriş/araç
içeride/kara liste sayısı vb.) ve Kayıtlar sekmesindeki asıl tablo, kullanıcı
elle "yenile"/sayfayı yeniden açana kadar ESKİ kalıyordu. Artık her SSE
"kayit" olayında (`_sseKayitAl` → `_canliBolumleriTazeleDebounce`) hem
`panelYenile()` hem de `kayitlariYukle(false)` arka planda otomatik olarak
çalışıyor — kullanıcı hiçbir şey yapmadan hem Panel hem Kayıtlar güncel
kalıyor. Art arda hızlı gelen olaylar (aynı anda birden fazla araç geçişi)
400ms'lik bir pencerede TEK yenileme turuna toplanıyor (debounce), gereksiz
API isteği yığılması önleniyor. SSE bağlantısı koptuğunda devreye giren 15
saniyelik yedek polling de artık yalnızca Panel'i değil Kayıtlar'ı da
kapsıyor. Kullanıcı o an Kayıtlar sekmesindeki plaka/tarih/durum filtre
kutularından birine yazı yazıyorsa (`_kayitlarFiltresiDuzenleniyorMu`) arama
kutusunun elinin altından değişip yarım kalan aramasının bozulmaması için o
turda yalnızca Kayıtlar tablosu atlanıyor, Panel yine de tazeleniyor.

**2026-09-20 (devam) — Canlı geçiş bildirimine (toast) tıklayınca doğrudan
not/onay ekranı açılıyor.** Kullanıcı geri bildirimi (birebir): "Giriş veya
çıkış olduğunda panel ekranında sağ üstte 34 MRU 800 giriş yaptı gibi bir
bildirim geliyor bu bildirim geldiğinde son geçişler de olduğu gibi direkt
olarak onun üstüne tıklayıp not ve onay ekranının açılmasını istiyorum."
`toastGoster()` artık opsiyonel üçüncü bir `tikla` (callback) parametresi
alıyor; verildiğinde toast'un gövdesi tıklanabilir hale geliyor (imleç
`pointer`, `title="Detayları görmek için tıklayın"`) ve tıklanınca hem
callback çalışıp toast kapanıyor. `_sseKayitAl`, her yeni SSE "kayit"
olayında toast'ı `() => olayDetayAc(kayit.id)` callback'iyle açıyor — yani
"Son Geçişler" panelindeki bir satıra tıklamakla BİREBİR AYNI davranış
(görsel + not/onay/ziyaretçi girişi ekranı) artık toast'un kendisinden de
tetiklenebiliyor. Kapatma (X) butonu ayrı bir olay dinleyicisiyle çalıştığı
için (bkz. Bootstrap'ın `data-bs-dismiss`'i) tıklama olayı kabarcıklanmıyor
(bubbling), yani X'e basmak yanlışlıkla detay ekranını açmıyor.
`tests/test_bildirim_tiklama_ve_roi_polygon.py`'ye (gerçekten çalıştırılıp
doğrulandı) bu davranışı doğrulayan testler eklendi.

**2026-09-17 (devam) — Ziyaretçi girişi ve site sakini öz-hizmet portalı.**
Kullanıcı, rakip bir üründen ekran görüntüleri paylaşarak benzer bir "ziyaretçi
kabulü" ve "sakin/abone paneli" deneyimi istedi. Görsellerdeki kapsam çok
genişti (Site > Blok > Daire hiyerarşisi, daire bazlı araç/kişi kotaları,
otopark/kart yönetimi dahil); kullanıcıyla netleştirme sonrasında YALNIZCA
aşağıdaki üç parça, PTS'nin MEVCUT düz (flat) Kişi veri modeli üzerine
uygulandı — **Site > Blok > Daire yapısı ve daire bazlı limitler bilinçli
olarak KAPSAM DIŞI bırakıldı** ve bu sistemde yoktur:

- **Kayıt detayında tek tuşla "Ziyaretçi Girişi":** Bir tespit "yetkisiz",
  "kara liste" veya "bilinmiyor" olarak işaretlendiğinde, olay detay
  penceresinde (operatör/yönetici için) yeni bir "Ziyaretçi Girişi" kutusu
  çıkar. Görevli isteğe bağlı olarak tespiti bir Kişi/daireye bağlayabilir,
  kısa bir not girebilir (ör. "kargo", "misafir") ve TEK düğmeyle hem kaydı
  `yetki_durumu=ziyaretci_onayli` olarak onaylar hem de (nokta bir bariyere
  bağlıysa) bariyeri açar. Kara listedeki bir plaka için ekstra bir onay
  istemi (`confirm()`) çıkar. Bu akış, yeni bir backend uç noktası
  GEREKTİRMEDİ — var olan `PATCH /kayitlar/{id}` ve `POST /bariyer/{id}/ac`
  uçlarının bir bileşimidir; yalnızca `yetki_durumu` beyaz listesine
  (`_KAYIT_GECERLI_YETKI_DURUMLARI`) yeni bir değer eklendi. Kayıtlar
  filtresine ve durum rozetlerine de bu yeni değer eklendi.
- **Bağımsız "Ziyaretçi Girişi" formu:** Panel (Kontrol Merkezi) sekmesine
  eklenen "+ Ziyaretçi Girişi" düğmesi, herhangi bir kamera tespiti olmadan
  (ör. telefonla önceden haber verilmiş bir ziyaretçi için) elle plaka girip
  hangi bariyer/erişim noktasının açılacağını seçebileceğiniz bağımsız bir
  form açar. Açılacak nokta seçimi ZORUNLUDUR (referans üründeki "hangi
  bariyerin açılacağını seçin" davranışıyla birebir) ve yalnızca gerçekten bir
  bariyere bağlı noktalar listede görünür. Kaydet düğmesi sırasıyla `POST
  /kayitlar` (manuel kayıt oluştur) → `PATCH /kayitlar/{id}`
  (`ziyaretci_onayli` yap, isteğe bağlı kişiye bağla) → `POST
  /bariyer/{id}/ac` (bariyeri fiilen aç) uçlarını zincirler — burada da yeni
  bir backend uç noktası gerekmedi.
- **"sakin" rolü — site sakini öz-hizmet portalı:** Kullanıcılar sekmesinde
  artık yönetici/operatör/izleyicinin yanında dördüncü bir rol olarak
  "Sakin" oluşturulabiliyor. Bu rol, panel PERSONELİNİN (yönetici/operatör/
  izleyici) bir üyesi DEĞİLDİR — dışarıdan, daha az güvenilen bir hesap
  türüdür ve mutlaka var olan bir Kişi kaydına bağlanır
  (`Kullanici.kisi_id`, bkz. `main.py::_sakin_kisi_id_dogrula`; kişi
  silinirse bu bağlantı `kisi_sil` tarafından otomatik temizlenir ve hesap
  "yetim" kalıp `/sakin/...` uçlarından açık bir 400 hatası döner). Bir sakin
  giriş yaptığında normal personel arayüzü (sidebar + sekmeler) hiç
  gösterilmez; bunun yerine yalnızca kendi profilini (ad/soyad, ana plaka,
  daire/departman, aktiflik), kendi ek araçlarını (ekleme/silme) ve kendi
  giriş/çıkış geçmişini gördüğü sadeleştirilmiş, ayrı bir sayfa açılır (`GET
  /sakin/profilim`, `POST /sakin/arac-ekle`, `DELETE /sakin/arac/{id}`, `GET
  /sakin/gecmisim`, `GET /sakin/goruntu/{kayit_id}`). Bu uçların HİÇBİRİ
  istekten kaynak kimliği (kisi_id) almaz — her zaman JWT'den çözülüp DB'de
  doğrulanan oturum sahibinin `kisi_id`'si kullanılır ve sahiplik SQL
  filtrelerinde ikinci kez doğrulanır (IDOR koruması: bir sakin başka bir
  kişinin plaka id'sini veya kayıt id'sini tahmin ederek onun verisini
  göremez/silemez).
  - **Yan etki — önemli güvenlik sıkılaştırması:** "sakin" rolünü eklemek,
    var olan bir varsayımı gün yüzüne çıkardı: dahili/genel amaçlı uçların
    (kişi listesi, kayıtlar, kameralar, kara liste, siteler, sistem logları
    vb. — yaklaşık 70 uç nokta) çoğu yalnızca `_giris_gerekli` (yani "giriş
    yapmış HERHANGİ bir hesap") ile korunuyordu. Yeni, daha az güvenilir
    "sakin" rolü eklenince bu artık kabul edilemezdi. Bu yüzden yeni bir
    bağımlılık olan `_personel_girisi_gerekli` (sakin hariç her rolü kabul
    eder) tüm bu uçlara uygulandı; yalnızca `/auth/me` (sakinin kendi
    rolünü tespit edebilmesi için) eski `_giris_gerekli` davranışını
    korudu. Sonuç: bir sakin hesabı artık başka hiçbir kişiyi, kaydı,
    kamerayı veya sistem bilgisini göremez — yalnızca kendi verisine ve
    `/sakin/...` uçlarına erişebilir.
  - **Otopark ve Kart yönetimi YOK:** Referans üründeki "Otopark Listesi"
    (daire bazlı park yeri ataması) ve "Kart" (fiziksel erişim kartı)
    kavramları bu sistemin veri modelinde karşılığı olmadığı ve kullanıcının
    seçtiği kapsamda yer almadığı için uygulanmadı.

**2026-09-17 (devam) — "Son kullanılan not" önerisi, her gece 23:59'da
sıfırlanır.** Kullanıcının somut örneği: yetkisiz bir kargo aracına
("PTT Kargo") panelden elle bir not eklendiğinde, aynı araç aynı gün
içinde tekrar gelirse (örn. 09:00 giriş, 13:00 çıkış) görevli notu yeniden
yazmak zorunda kalmamalı — ama kullanıcı bu önerinin bir sonraki güne HİÇ
taşınmamasını, her gün saat 23:59'da (gün değişiminde) sıfırlanmasını
açıkça istedi.

- **Önemli ayrım:** Bu, `Kayit.not_metni` gibi KALICI/denetime tabi bir alan
  DEĞİLDİR. Her giriş/çıkış kaydının kendi notu (bkz. yukarıdaki "Plaka
  Analizi ekranında tam düzenleme, notlar ve manuel kayıt" bölümü) zaten o
  kayda özeldir ve sonsuza dek olduğu gibi saklanır — geçmiş kayıtlara
  ASLA dokunulmaz/silinmez. Yeni eklenen şey, yalnızca bir sonraki not
  giriş kutusuna otomatik ÖNERİ olarak sunulan, sunucu belleğinde tutulan
  GEÇİCİ bir önbellektir (`main.py::_SON_NOT_ONBELLEGI`) — sunucu yeniden
  başlatıldığında da zaten kaybolur, ayrıca her gece 23:59'da aktif olarak
  temizlenir (`_son_not_onbellek_temizlik_dongu`, her dakika kontrol eder)
  ve okuma sırasında da pasif olarak süresi dolar (`_son_not_oku`, önbellek
  kaydı bugüne ait değilse anında yok sayar — aktif döngü henüz çalışmamış
  olsa bile doğruluk garantilenir).
- Bir kayda not eklenen/güncellenen HER yer bu önbelleği besler: manuel
  kayıt ekleme (Kayıtlar sekmesi "Test Kaydı Ekle" formu ve Plaka Analizi
  "Manuel Kayıt Ekle" formu — ikisi de `POST /kayitlar`), Kayıt Düzenle ve
  Ziyaretçi Girişi (ikisi de `PATCH /kayitlar/{id}`).
- Yeni uç nokta: `GET /kayitlar/son-not?plaka=...` → `{"not_metni": "..."}`
  (yoksa `null`). Panelde dört ayrı not kutusu bunu tüketir: olay
  detayındaki Ziyaretçi Girişi kutusu, Kayıt Düzenle modalı (yalnızca o
  kaydın KENDİ notu boşsa), bağımsız "Ziyaretçi Girişi" panel formu (plaka
  alanından çıkılınca/blur), ve Plaka Analizi'nin "Manuel Kayıt Ekle"
  formu (bu ekranda plaka zaten sabit olduğundan `plaka_analiz` uç
  noktasının kendi yanıtına eklenen `son_not_onerisi` alanı üzerinden,
  ekstra bir istek atmadan). Öneri HER ZAMAN düzenlenebilir kalır —
  görevli isterse değiştirip kaydedebilir.
- 5 yeni test: kayıtsız bir plaka için boş dönüş, manuel kayıt notunun
  (kullanıcının "PTT Kargo" örneğinin birebir tekrarı) önbelleğe yansıması
  ve aynı gün ikinci bir kayıtla (çıkış) bozulmaması, Kayıt Düzenle/
  Ziyaretçi Girişi üzerinden eklenen notun da yansıması, Plaka Analizi
  yanıtındaki `son_not_onerisi` alanı, ve önbellekteki tarih doğrudan
  "dün"e çekilerek gün değişiminin öneriyi gerçekten sıfırladığının
  doğrulanması.

**2026-09-17 (devam) — Otomatik tespitler için "kayıt güven eşiği" filtresi.**
Kullanıcı, düşük güvenli (hatalı/yanlış okunan) OCR tespitlerinin panele ve
Kayıtlar sekmesine düşüp kayıtları şişirdiğini bildirdi ve yalnızca **%97-%100**
aralığında güvenli olan tespitlerin kayda geçmesini, geri kalanının HİÇ
kaydedilmemesini istedi. Bu, var olan `min_tanima_guveni` ayarından (bkz.
Sistem Ayarları) **BİLİNÇLİ OLARAK FARKLI** yeni bir ayar/mekanizma olarak
eklendi çünkü ikisi farklı aşamalarda çalışır:

- `min_tanima_guveni` (varsayılan 0.4): yalnızca kameranın kendi in-process
  pipeline'ında, TEK TEK OCR karelerinin çok-kareli oy birikimine
  (`camera_reader.py::PlakaOyBirikimi`) girip girmeyeceğine bakar. Bir
  oturumda birden fazla düşük-orta güvenli okuma varsa, oy birleştirme
  sonucu ortaya çıkan NİHAİ güven skoru yine de bu değerin altında/üstünde
  olabilir; ayrıca `/kayitlar/otomatik`'e DOĞRUDAN istek atan (kamera
  pipeline'ından geçmeyen) harici bir ANPR sistemi bu ayardan hiç etkilenmez.
- **Yeni: `otomatik_kayit_min_guven_skoru` (varsayılan 0.97).** Oturum
  kapanıp nihai/tek bir güven skoru belirlendikten SONRA, `POST
  /kayitlar/otomatik` uç noktasında (bkz. `main.py::kayit_ekle_otomatik`)
  uygulanan gerçek-zamanlı bir kapıdır — kaynağı ne olursa olsun (in-process
  pipeline veya harici bir sistem) TÜM otomatik tespitlere eşit şekilde
  uygulanır. `guven_skoru` bu eşiğin altındaysa (üst sınır zaten motor
  tarafından 1.0 ile sınırlı olduğundan ayrıca bir üst eşik gerekmez, yine de
  savunma amaçlı 1.0'ın belirgin şekilde üzerindeki bozuk/anormal değerler de
  aynı şekilde reddedilir): **kayıt hiç oluşturulmaz, gönderilen görsel
  dosyası diskten hemen silinir**, uç nokta yine de HTTP 200 ve
  `{"atlandi": true, "sebep": "dusuk_guven_skoru", ...}` gövdesiyle yanıt
  verir (kamera tarafında bunu bir hata gibi loglayıp gürültü yaratmasın
  diye — bkz. `camera_reader.py`'deki `yanit.status_code >= 400` kontrolü).
  Elle girilen kayıtlar (`kayit_ekle_manuel`, Ziyaretçi Girişi akışları,
  Panel'deki "Test Kaydı Ekle" formu — hepsi `manuel_giris=True`) bu
  filtreden **HİÇ etkilenmez**, çünkü bunlar bir OCR tespiti değil, personelin
  bilinçli kararıdır.
- Sistem Ayarları panelinde iki eşik yan yana, açıklayıcı bir notla birlikte
  gösterilir ve yalnızca yönetici değiştirebilir.
- **Geriye dönük temizlik:** Bu filtre yalnızca BUNDAN SONRAKİ tespitleri
  etkiler; özellik devreye alınmadan önce zaten kaydedilmiş düşük güvenli
  kayıtları temizlemek için Sistem sekmesi → Disk Yönetimi'ne "Düşük Güvenli
  Kayıtları Temizle" düğmesi eklendi (`POST /sistem/dusuk-guven-temizle`,
  yalnızca yönetici). Bu uç nokta, Sistem Ayarları'ndaki eşiğin altında kalan
  ve `guven_skoru` dolu olan (yani gerçek bir OCR tespiti olan) kayıtları —
  ve varsa görsel dosyalarını — kalıcı olarak siler; elle girilmiş
  kayıtlara ve o kayıtlara bağlı alarm günlüğüne (bkz. `kayit_sil`'deki aynı
  FK-güvenliği deseni) dokunmaz. Otomatik, periyodik bir arka plan işi
  OLARAK tasarlanmadı — gerçek-zamanlı filtre zaten gelecekteki birikmeyi
  önlediği için, bu yalnızca geçmiş birikimi bir kerelik temizlemek
  içindir.
- **Bilinen dengeleme notu:** `_bilinen_plakaya_yakinlik_duzelt` (OCR'ın tek
  karakter hatalarını bilinen plakalara göre düzelten mekanizma) %90 güvenin
  ALTINDAKİ okumalarda devreye girer ve düzeltme plaka METNİNİ değiştirir,
  güven SKORUNU değiştirmez. Yani %90 altı bir okuma, doğru bir bilinen
  plakaya düzeltilmiş olsa bile, güven skoru hâlâ %97 eşiğinin altında
  kalacağından kayda düşmez. Bu, kullanıcının talebiyle bilinçli bir
  ödünleşimdir (düşük güvenli her okumayı, doğru çıksa bile eleyerek
  kayıtların şişmesini engellemek); saha testlerinde meşru düşük-güvenli
  geçişlerin sistematik olarak kaybolduğu görülürse eşiğin (Sistem
  Ayarları'ndan) düşürülmesi gerekebilir.

**⚠️ 2026-09-17 (devam) — az yukarıdaki "bilinen dengeleme notu"nda öngörülen
risk gerçekleşti: kullanıcının kendi (sistemde kayıtlı) aracı, girişte %96.6
güvenle okundu ama %97'lik genel eşiğin az altında kaldığı için o geçiş HİÇ
KAYDEDİLMEDİ — aynı araç çıkışta (daha yüksek güvenle) kaydedildiği için
Kayıtlar sekmesinde giriş kaydı olmayan, yalnızca çıkışı olan tutarsız bir
görünüm oluştu.** Basitçe genel eşiği düşürmek yeni bir ödünleşim yaratırdı
(gerçekten hatalı/yabancı okumaların yeniden kayıtlara sızması); bunun yerine
daha hedefli bir çözüm eklendi — **"bilinen araç istisnası"**:

- Yeni ayar: `otomatik_kayit_min_guven_skoru_bilinen_arac` (varsayılan **0.80**,
  Sistem Ayarları panelinde genel eşiğin hemen altında gösterilir).
- Genel eşiğin altında kalan bir otomatik tespit artık hemen atılmıyor;
  önce ham plaka metni, sahadaki bilinen (abone/personel) ana VE ek
  plakalarla (`Kisi.plaka_no` + `KisiPlaka.plaka_no`) TAM eşleşiyor mu ya da
  (`en_yakin_bilinen_plakayi_bul` ile) tek karakter farkla eşleşiyor mu diye
  kontrol edilir (`main.py::_bilinen_plakaya_yakin_mi` — bu kontrol,
  `_bilinen_plakaya_yakinlik_duzelt`'in kullandığı sorgu mantığıyla ortak bir
  yardımcı fonksiyonda, `_bilinen_plakalar_sozlugu`, birleştirildi ki iki
  yerde birbirinden bağımsız kopya olarak var olmasın).
- Eşleşme varsa VE güven skoru daha düşük olan bu ikinci eşiği (varsayılan
  %80) geçiyorsa, tespit yine de kaydedilir. Eşleşme yoksa (bilinmeyen/yabancı
  bir plaka) ya da güven bu ikinci eşiğin de altındaysa, davranış eskisi gibi
  aynen devam eder — kayıt hiç oluşturulmaz.
- Mantık: genel eşik esasen sistemde HİÇ KAYITLI OLMAYAN plakaların (yanlış
  okunmuş, hiçbir gerçek araca karşılık gelmeyen) kayıtları şişirmesini
  önlemek içindir. Sahada zaten kayıtlı bir plakayla tam/çok yakın eşleşen bir
  tespit için düşük bir OCR güven skoru genellikle ışık/açı/kısmi görüş gibi
  görüntü kalitesi sorunlarından kaynaklanır — okunan METNİN kendisi kuvvetle
  muhtemelen yine doğrudur, dolayısıyla bu durumda kaydı atmak (fayda yerine)
  yalnızca zarar verir (kayıp giriş/çıkış kaydı).
- 4 yeni test eklendi: bilinen-araç eşiğinin varsayılanı (0.80), genel eşiğin
  altında ama bilinen-araç eşiğinin üzerindeki TANIMLI bir aracın artık
  kaydedildiği (kullanıcının canlı senaryosunun birebir tekrarı), bilinmeyen
  bir plaka için istisnanın devreye GİRMEDİĞİ, ve bilinen bir araç olsa bile
  bilinen-araç eşiğinin de altında kalan bir tespitin yine atlandığı
  (istisnanın bir güvenlik tabanını atlamadığı).

**2026-09-17 (devam) — Kişiler sekmesinde plaka artık tıklanabilir.**
Kayıtlar ve Kara Liste sekmelerinde bir plakaya tıklamak zaten "Plaka
Analizi" penceresini (geçiş geçmişi + her geçişin görseli) açıyordu, ama
Kişiler sekmesindeki "Plaka" sütunu sıradan, tıklanamayan bir metin olarak
kalmıştı — kullanıcı bunu "hiç işlevi yokmuş gibi" olarak bildirdi. Artık
Kişiler sekmesindeki plaka da aynı `data-plaka-analiz` mekanizmasını
kullanan bir bağlantı: tıklandığında o kişinin/plakanın TÜM geçiş
geçmişini, her geçişin küçük resmini (tıklanınca büyük halinin yeni
sekmede açıldığı) ve kara liste durumunu gösteren aynı "Plaka Analizi"
penceresi açılır. Yeni bir backend uç noktası veya mekanizma GEREKMEDİ —
var olan `plakaAnalizAc()` işlevine tek bir eksik bağlantı eklendi.

**⚠️ 2026-09-17 (devam) — KÖK NEDEN BULUNDU: "Plaka Analizi" HER ZAMAN
"Toplam Geçiş: 0" gösteriyordu VE kara liste engeli fiilen hiç
çalışmıyordu.** Kullanıcı, az önce eklenen tıklanabilir plaka bağlantısını
denedikten sonra bir ekran görüntüsüyle "Toplam Geçiş: 0 / Kayıt yok"
gösteren, gerçekte ise kayıtları listede görünen bir plaka için açılan boş
bir "Plaka Analizi" penceresi bildirdi. Kök neden koddaki iki farklı
normalize fonksiyonunun karıştırılmasıydı:

- `main.py::_plaka_normalize` — boşlukları TAMAMEN KALDIRIR ("34 GA 0835" →
  "34GA0835"). Bilinen-plaka yakınlık düzeltmesinde (Levenshtein) bilerek
  kullanılır, orada doğru.
- `schemas.py::plaka_normalize` — boşlukları KORUR, yalnızca geçersiz
  karakterleri temizler ve büyük harfe çevirir. `Kisiler`, `KisiPlaka`,
  `KaraListesi` ve `Kayit` tablolarının HEPSİ plaka_no'yu bu biçimde (boşluklu)
  saklar.

`plaka_analiz` ve `_plaka_yetki_kontrol` (gerçek zamanlı yetki kontrolü),
`_plaka_normalize` ile ürettikleri BOŞLUKSUZ değeri, DB'de BOŞLUKLU saklanan
sütunlarla `Model.plaka_no == hedef` biçiminde DOĞRUDAN karşılaştırıyordu —
iki taraf da farklı biçimde olduğu için bu sorgular **HİÇBİR ZAMAN**
eşleşmiyordu. Somut etkileri:

- "Plaka Analizi" penceresi her plaka için her zaman "Toplam Geçiş: 0",
  "Kayıt yok" gösteriyordu (kullanıcının bildirdiği belirti).
- **Kara liste (blacklist) engeli, sistemin kurulduğu günden beri, hiçbir
  gerçek kamera tespitinde veya elle girilen kayıtta FİİLEN ÇALIŞMIYORDU** —
  bir plaka kara listeye eklense bile bir sonraki geçişinde yine "yetkisiz"
  ya da (kayıtlıysa) "yetkili" olarak işleniyordu, asla "kara_liste" olarak
  engellenmiyordu.
- Bir kişinin panelden eklenen ek/ikincil plakaları (bkz. `POST
  /kisiler/{id}/plakalar`) gerçek bir geçişte hiçbir zaman "yetkili" olarak
  tanınmıyordu (yalnızca kişinin ANA plakası, Python tarafında doğru
  normalize edilerek karşılaştırıldığı için, çalışıyordu).
- "Plaka Analizi"nden manuel kayıt eklemek veya "Kara Listeye Ekle"ye
  basmak, ekranda görünenin aksine, aslında boşluksuz/hatalı bir plaka
  metniyle kaydediyordu.

**Düzeltme:** yeni bir `_plaka_normalize_sql()` yardımcı fonksiyonu, aynı
boşluksuzlaştırma+büyük-harf normalizasyonunu SQL tarafında
(`REPLACE(UPPER(sütun), ' ', '')`) uygular; `_plaka_yetki_kontrol` ve
`plaka_analiz`'deki BEŞ sorgunun tamamı (kara liste ×2, ek plaka ×2, geçiş
kayıtları ×1) artık bunu kullanıyor — SQLite ve SQL Server'ın ikisinde de
çalışan standart `REPLACE`/`UPPER` fonksiyonlarıyla. "Plaka Analizi"nin
döndürdüğü plaka metni de artık normalize edilmiş (boşluksuz) hali değil,
kayıtlardaki OKUNABİLİR (boşluklu) biçimiyle dönüyor. Bu, kod
incelemesiyle (bu depoda fastapi/sqlalchemy kurulu olmadığı için
`test_api.py` çalıştırılamıyor) bulunup 7 yeni testle (kara liste — aynı ve
farklı boşluk biçimiyle —, ek plaka yetkilendirmesi, Plaka Analizi'nin
doğru geçiş sayısı/kara liste durumu) doğrulandı; ayrıca bu depodaki VAR
OLAN `test_plaka_analiz_yeni_alanlari_dondurur` testinin de bu hata
yüzünden aslında hiç geçemeyeceği (boş bir listeden ilk elemanı almaya
çalışırdı) fark edildi.

**2026-09-17 (devam) — Araç görselleri artık büyük/net görünüyor VE
uygulama içinde yakınlaştırılıp (zoom) plaka yakından incelenebiliyor;
ayrıca küçük resimlere tıklama özelliğinin baştan beri hiç çalışmadığı
ortaya çıkarıldı.** Kullanıcı, çalışan bir "Plaka Analizi" ekran
görüntüsü paylaşarak görsellerin daha net görünmesini ve TÜM araç
görsellerine (Panel, Kayıtlar, Plaka Analizi, olay detayı) yakınlaştırıp
plakayı yakından görebilmeyi istedi. İnceleme sırasında ayrı, öncesinde
fark edilmemiş bir hata bulundu:

- Küçük resimler (`.thumb`) `data-goruntu-yolu` attribute'u taşıyan bir
  seçiciyle (`.thumb[data-goruntu-yolu]`) tıklamaya/büyütmeye açılıyordu.
  Ancak bir tablo render edildikten HEMEN SONRA çağrılan
  `korumaliGorselleriYukle()`, görsel yüklenmeyi (asenkron `fetch`) hiç
  beklemeden bu attribute'u DOM'dan siliyordu
  (`img.removeAttribute("data-goruntu-yolu")`). Yani bir kullanıcı
  fiziksel olarak tıklayabilene kadar geçen sürede bu seçici zaten
  hiçbir şeye eşleşmiyordu — **küçük resimlere tıklayıp büyütme özelliği
  uygulamanın HER YERİNDE (Panel "Son Kayıtlar", Kayıtlar tablosu, Plaka
  Analizi) baştan beri hiç çalışmamıştı**, ayrıca olay detayı
  penceresindeki ana görsel (`#olayModalGorsel`) için bu özellik hiç
  kablolanmamıştı bile.
- Küçük resimler yalnızca 56×40px boyutundaydı — plakayı okumak pratikte
  imkânsızdı.
- Büyütülmüş görsel, `window.open(imgEl.src)` ile blob: URL'ini yeni bir
  sekmede açıyordu; yakınlaştırma imkânı yoktu ve blob URL'leri için bu
  davranış tarayıcıdan tarayıcıya tutarsızdı.

**Düzeltme:**

- `.thumb` küçük resimleri 96×68px'e büyütüldü ve hover'da hafif bir
  büyüme/gölge efekti eklendi (`frontend/style.css`).
- Tıklama/klavye (Enter/Boşluk) olay delegasyonu artık kalıcı olan
  `.thumb`/`.zoomable-img` SINIF adlarına göre eşleşiyor — silinen
  `data-goruntu-yolu` attribute'una değil (`frontend/app.js`). Bu,
  yukarıdaki tıklama hatasını da düzeltir.
- Yeni bir uygulama-içi büyütme (lightbox) penceresi eklendi
  (`#gorselBuyutModal`): fare tekerleğiyle imlecin altındaki noktayı
  sabit tutarak yakınlaştırma, +/- ve "sıfırla" düğmeleri, çift tıkla
  2.5x yakınlaştır/sıfırla, ve (yakınlaştırılmışken) fare/dokunmatik ile
  sürükleyerek kaydırma (pan). Modal kapanınca zoom/pan durumu otomatik
  sıfırlanır. Görsel zaten korumalı bir blob: URL olarak yüklü olduğu
  için (bkz. `korumaliGorselAta`) tekrar sunucudan çekilmiyor, aynı blob
  URL'i lightbox'a aktarılıyor.
- Olay detayı penceresinin ana görseli (`#olayModalGorsel`) artık
  `zoomable-img` sınıfı ve `role="button" tabindex="0"` ile aynı
  lightbox'ı kullanıyor — önceden bu görsel hiç tıklanamıyordu.
- Bu değişiklikler yalnızca `frontend/` içindedir; backend/veritabanı
  davranışı etkilenmedi (test sayısı 95'te sabit kaldı).

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

## Kayıtlar Raporu Biçimi ve Personel Toplu İçe Aktarma (2026-09-18)

Kullanıcının paylaştığı, kullanmakta olduğu başka bir üründen alınmış referans
"GEÇİŞ RAPORU" PDF/Excel çıktısına yaklaştırmak amacıyla Kayıtlar dışa aktarma
raporları (Excel + PDF) yeniden tasarlandı, ve sisteme yeni bir personel/abone/
ziyaretçi toplu içe aktarma Excel şablonu eklendi.

**Rapor sütunları:** Yeni sütun sırası: `Plaka, Adı, Soyadı, Site, Blok, Daire,
Otopark, Nokta, Geçiş Tipi, Araç Tipi, Tarih` + (Excel'de `Notlar`, PDF'de
`Görsel`) — referans üründeki sütunlarla birebir aynı isimlendirme (başa
yalnızca bu sistemin kendi `ID` sütunu eklendi).

- **"Araç Tipi" sütunu**, kaydın eşleştiği Kişi'nin tipine göre değişir:
  personel için kişinin departman adı (`daire_departman`), abone için
  `"Tanımlı"`, hiçbir kişiyle eşleşmeyen bir plaka için `"Tanımsız Araç"`.
  Referans raporda olmayan ama sistemin zaten tuttuğu bir bilgi olan kara
  liste eşleşmesi de `"Tanımsız Araç"` içinde gizlenmek yerine ayrıca
  `"Kara Liste"` olarak gösteriliyor.
- **"Daire" sütunu**, personel tipi için her zaman sabit `"PERSONEL"` metnini,
  abone tipi için kişinin kendi `daire_departman` değerini gösterir.
- **"Blok" ve "Otopark" sütunları her zaman BOŞ bırakılır.** Bu kavramlar bu
  sistemin veri modelinde YOK — "Site > Blok > Daire hiyerarşisi ve otopark
  ataması" 2026-09-17'de "Ziyaretçi Girişi" özelliği eklenirken bilinçli
  olarak kapsam dışı bırakılmıştı. Referans rapor biçimiyle sütun uyumluluğu
  için bu iki sütun yer tutucu olarak eklendi ama var olmayan bir veri
  UYDURULMADI/UYDURULMAYACAK.
- Zenginleştirme mantığı `backend/main.py::_kayitlari_rapor_satirlari`
  içinde tek bir yerde toplanıyor (hem Excel hem PDF aynı fonksiyonu
  kullanıyor) ve N+1 sorgudan kaçınmak için kişiler/noktalar/siteler toplu
  olarak önceden yükleniyor.
- PDF'teki araç görselleri artık gömülmeden önce küçültülüp yeniden
  sıkıştırılıyor (bkz. `backend/pdf_export.py::_kucuk_gorsel_akisi`, Pillow
  ile 240×160'a küçültme + JPEG kalite 60) — aksi halde binlerce tam
  çözünürlüklü görsel içeren bir rapor yüzlerce MB'a şişebilirdi. Bu yeni
  bağımlılık `backend/requirements.txt`'ye eklendi (`Pillow==11.0.0`).

**Personel/Abone/Ziyaretçi toplu içe aktarma şablonu:** Kişiler sekmesinde
"Excel İçe Aktar"ın yanına yeni bir **"Şablon İndir"** düğmesi eklendi
(`GET /kisiler/toplu-import/sablon`). İndirilen `.xlsx` iki sayfa içerir:

- **"Kişiler" sayfası**: mevcut `toplu_kisi_import` uç noktasının beklediği
  `Ad Soyad, Plaka No, Tip, Telefon, Daire Departman` başlıkları (normalize
  edildiğinde birebir eşleşecek şekilde seçildi — örn. "Daire/Departman"
  DEĞİL "Daire Departman" kullanıldı, çünkü "/" normalizasyon tarafından
  temizlenmiyor ve eşleşmeyi bozardı) + 2 örnek satır, ve `Tip` sütununda
  yalnızca `abone/personel/ziyaretci` seçilebilen bir açılır liste (data
  validation) — serbest metin yazıp typo yapılıp sessizce "abone"ya
  düşülmesini önlemek için.
- **"Açıklama" sayfası**: her sütunun ne anlama geldiğini ve geçerli `Tip`
  değerlerini açıklayan bir referans tablosu.

**⚠️ Bu turda ayrıca bulunan ve düzeltilen bir güvenlik açığı:** bkz. aşağıdaki
"Üretim Güvenliği Sertleştirmeleri" bölümündeki 2026-09-18 notu — dışa
aktarma uç noktaları kimlik doğrulaması gerektirmiyordu.

**⚠️ 2026-09-18 (devam) — KÖK NEDEN BULUNDU: PDF raporlarında Türkçe
karakterler ("ı, İ, ş, Ş, ğ, Ğ") boş kare olarak görünüyordu.** Kullanıcının
paylaştığı bir ekran görüntüsü, üretilen "GEÇİŞ RAPORU" PDF'inde başlığın
"GEÇ██ RAPORU" olarak, "Adı"/"Soyadı" sütun başlıklarının "Ad█"/"Soyad█"
olarak, "Tanımsız Araç"/"Giriş"/"Çıkış" gibi hücre değerlerinin de benzer
şekilde bozuk göründüğünü ortaya çıkardı. Kök neden: reportlab'ın gömülü 14
temel fontu (Helvetica/Helvetica-Bold, `pdf_export.py`'nin önceki tüm
sürümlerinde varsayılan olarak kullanılıyordu) yalnızca **WinAnsiEncoding**'i
destekler — bu kodlamada Türkçeye özgü dişsiz "ı" (U+0131), büyük noktalı
"İ" (U+0130), "ş/Ş" (U+015F/U+015E) ve "ğ/Ğ" (U+011F/U+011E) karakterleri
YOK. Bu yüzden bu harfler PDF'e hiç gömülemiyor, yerlerine boş bir
`.notdef` glifi (kare) basılıyordu — Excel çıktısı etkilenmiyordu, çünkü
openpyxl/Excel Unicode'u sorunsuz destekliyor; sorun yalnızca PDF'e özgüydü.

Düzeltme: Türkçenin tamamını (ve çok daha fazlasını) kapsayan, serbestçe
gömülebilir bir Unicode TrueType fontu (**DejaVu Sans**, Bitstream Vera
lisansı — bkz. `backend/fonts/LISANS-DejaVu.txt`) depoya gömüldü
(`backend/fonts/DejaVuSans.ttf` + `DejaVuSans-Bold.ttf`, ~1.4MB) ve
`pdf_export.py`'deki TÜM stil/tablo font referansları (başlık, tablo
başlıkları, hücreler, tekil kayıt detay PDF'i) buna yönlendirildi (bkz.
`_turkce_destekli_stiller`/`_turkce_fontlari_kaydet`). Font dosyaları
depoyla birlikte geldiği için kullanıcının internet bağlantısına ya da
sisteme ek bir font kurmasına gerek YOK. `tests/test_pdf_export.py`'ye,
üretilen PDF'i `pdfplumber` ile geri okuyup Türkçe metnin GERÇEKTEN doğru
çıktığını doğrulayan (yalnızca "PDF üretildi mi" değil) kök neden regresyon
testleri eklendi.

## Geçmiş Kayıtları Yeni Eklenen/Düzenlenen Kişiye Bağlama (2026-09-18)

Kullanıcı bildirimi: bir aracı ("39 AEZ 645") gerçek kamerayla test etti --
araç o an sistemde tanımlı olmadığı için oluşan geçişler "yetkisiz" düştü.
Ardından aracı personel olarak kaydetti. Yeni kamera tespitleri doğru şekilde
"yetkili" gösterilmeye başladı (bu zaten çalışıyordu -- kamera pipeline'ının
"bilinen plaka" önbelleği TUTMADIĞI, her tespitte canlı veritabanı sorgusu
kullandığı ayrıca doğrulandı), ama kayıttan ÖNCEKİ eski tespitler "yetkisiz"
olarak donmuş kaldı. Bu beklenen bir davranıştı (bir Kayıt satırının
yetki_durumu/kisi_id'si oluşturulduğu ANDAKİ bilgiyle sabitlenir) ama
kullanıcı bunların da düzeltilebilmesini istedi.

**Yeni davranış:** bir Kişi eklendiğinde (`POST /kisiler`), düzenlendiğinde
(`PUT /kisiler/{id}`, örn. abone→personel tip değişikliği veya plaka
düzeltmesi) ya da kendisine bir ek plaka bağlandığında (`POST /kisiler/{id}/
plakalar`), o plakaya (+ tüm ek plakalarına) ait, kayıt ANINDA bu kişi henüz
tanımlı olmadığı için `"yetkisiz"` kalmış GEÇMİŞ `Kayit` satırları OTOMATİK
olarak bulunup güncellenir (bkz. `backend/main.py::_gecmis_kayitlari_kisiye_
bagla`). Toplu personel/abone/ziyaretçi içe aktarma (`/kisiler/toplu-import`)
da her içe aktarılan kişi için aynı düzeltmeyi otomatik uygular ve yanıtta
`guncellenen_gecmis_kayit` alanıyla kaç kaydın güncellendiğini bildirir.

Bu özellik eklenmeden ÖNCE kaydedilmiş kişiler için panelin Kişiler
sekmesine, her satırda bir **"Geçmiş Kayıtları Güncelle"** (saat simgeli)
düğmesi eklendi -- bu, aynı düzeltmeyi `POST /kisiler/{id}/gecmis-kayitlari-
guncelle` ile elle tetikler ve kaç kaydın güncellendiğini bir uyarı olarak
gösterir.

**Güvenlik/doğruluk sınırları (kasıtlı ve test edilmiş):**

- Yalnızca şu ANDA `yetki_durumu="yetkisiz"` VE `kisi_id IS NULL` olan
  satırlara dokunulur. Kara liste (`kara_liste`), süresi dolmuş ziyaretçi
  (`suresi_dolmus`) ya da BAŞKA bir kişiye zaten bağlı satırlar ASLA
  sessizce üzerine yazılmaz -- örneğin bir plaka HEM kara listede HEM de
  (çelişkili biçimde) yeni eklenen bir Kişi'ye karşılık geliyorsa, kara
  liste her zaman önceliklidir ve o plakanın geçmiş kayıtları "yetkili"ye
  çevrilmez.
- Her satır, güncelleme ANINDAKİ "şimdi"ye göre DEĞİL, kendi ORİJİNAL
  `tarih_saat`ine göre yeniden değerlendirilir (`_plaka_yetki_kontrol`'e
  eklenen yeni `referans_zaman` parametresi sayesinde) -- aksi halde yalnızca
  08:00-18:00 arası yetkili bir personelin GECE geçmiş eski bir kaydı,
  güncelleme gündüz çalıştırılırsa yanlışlıkla "yetkili" işaretlenebilirdi.
- Güncellenen her satırda denetlenebilirlik için `duzenleyen`/
  `duzenleme_tarihi` de dolduruluyor (bu işlemi kimin/ne zaman tetiklediği
  kişi eklendiyse otomatik olarak, elle tetiklendiyse elle tetikleyen
  kullanıcı olarak kaydediliyor).
- İşlem idempotenttir: zaten bu kişiye bağlanmış bir satır tekrar
  "güncellenen" sayılmaz, bu yüzden "Geçmiş Kayıtları Güncelle" düğmesi
  güvenle istenildiği kadar tekrar tıklanabilir.

## Operatör Panelinden "Yönetim" Görünürlüğünün Kaldırılması (2026-09-18)

Kullanıcı talebi: yönetici'nin panel görünümü ve yönetimi aynen kalsın, ama
"operatör" rolündeki bir kullanıcı panele giriş yaptığında ekranında SADECE
kendisini ilgilendiren şu 5 alanı tam erişimle görsün: **Canlı İzleme, Ana
Sayfa, Geçiş Kayıtları, Aboneler ve Kişiler, Kara Liste**. Bunların dışında
"Yönetim"e dair hiçbir şey (Kameralar, Bariyer Kontrolü, Webhook Bildirimleri,
Lisans Yönetimi, LED Paneller, Site/Erişim Noktası, Kullanıcılar, Sistem/Log,
ve isimsiz "Test" sekmesi) ekranının hiçbir yerinde görünmemeli.

**Neden bu kadar çok yer değiştirdi:** panelde AYNI sekmeye giden ÜÇ ayrı ve
birbirinden bağımsız DOM konumu vardı -- (1) sol kenar çubuğu (görünür ana
gezinme), (2) sekmeler arasında geçiş yaparken asıl tıklamayı fiilen yapan,
görünen ama göze çarpmayan ikinci bir Bootstrap `nav-tabs` çubuğu (kenar
çubuğundaki bir düğmeye tıklamak arka planda bu çubuktaki karşılığını bulup
tıklıyor), ve (3) Ana Sayfa'daki hızlı erişim kutucukları (`.quick-tile`) --
bunlardan ikisi ("Kamera Yönetimi" ve "Lisans" kutucukları) da Yönetim
sekmelerine gidiyordu. Sadece kenar çubuğunu gizlemek yeterli olmuyordu;
sekme gerçekten "görünmez" olsun diye her üç konumun da ayrı ayrı
işaretlenmesi gerekti.

**Uygulama:** panelde zaten var olan `data-rol-min`/`data-rol-davranis="gizle"`
mekanizması (bkz. yukarıdaki "Rol Bazlı Yetkilendirme (RBAC)" bölümü,
`frontend/app.js::rolBazliArayuzuUygula`) kullanıldı -- yeni bir mekanizma
icat edilmedi. Yukarıdaki 9 sekmenin her üç girişteki (kenar çubuğu, ikinci
sekme çubuğu, Ana Sayfa hızlı erişim kutuları) düğmelerine/`<li>`'lerine
`data-rol-min="yonetici" data-rol-davranis="gizle"` eklendi; ayrıca kenar
çubuğundaki "YÖNETİM" bölüm başlığının kendisi de gizlendi (aksi halde
operatör altı boş bir başlık görürdü).

**Bu bir GÖRÜNÜRLÜK değişikliğidir, yetki değişikliği DEĞİLDİR:** operatör
rolünün backend'deki (`/kameralar`, `/bariyer/ayarlar`, `/led/ayarlar`,
`/sistem/loglar` gibi uçlardaki) API yetkileri BİLEREK ve daha önceden test
edilmiş biçimde değiştirilmedi -- bkz. yukarıdaki RBAC tablosu ve
`tests/test_api.py::test_operator_gunluk_islemleri_yapabilir_ama_yonetim_
islemlerini_yapamaz` / `test_sistem_loglarina_izleyici_erisemez_operator_
erisebilir`: operatörün kamera/bariyer/LED/log uçlarına API üzerinden erişimi
projenin MEVCUT ve kasıtlı tasarımının bir parçası ("günlük operasyon"un bir
parçası sayılıyor -- örn. ileride bir mobil istemci ya da doğrudan API
entegrasyonu operatör hesabıyla kamera yeniden başlatabilsin diye). Bu patch
YALNIZCA operatörün panelde bu ekranları GÖRMESİNİ engelliyor; kullanıcı
yönetimi, sistem ayarları, lisans aktivasyonu ve webhook yapılandırması zaten
öncesinden de backend'de sadece yönetici'ye açıktı, bunlar da değişmedi. Eğer
operatörün API'yi doğrudan çağırarak da (panel dışından) kamera/bariyer/LED
yönetim uçlarına erişememesi isteniyorsa, bu ayrı ve bilinçli bir yetki
kısıtlaması kararı olur -- istenirse ayrıca uygulanabilir.

**Doğrulama:** `tests/test_frontend_rbac.py` (yeni, BeautifulSoup ile
`frontend/index.html`'i ham HTML olarak ayrıştırıp üç girişin de doğru
işaretlendiğini gerçekten çalıştırarak doğrular -- fastapi/sqlalchemy'ye
bağımlı değil) -- 5 "çalışma alanı" sekmesinin YANLIŞLIKLA gizlenmediğini ve
9 "yönetim" sekmesinin her üç girişte de gizlendiğini doğrulayan testlerin
yanı sıra, gelecekte kenar çubuğuna/ikinci sekme çubuğuna bu testin bilmediği
YENİ bir sekme eklenirse testin başarısız olup hatırlatacağı iki
"tamlık koruması" (completeness guard) testi de içeriyor.

## "Net Görünen Plaka Yanlış/Eksik Kaydediliyor" -- Sondan Karakter Eksik Düzeltmesi (2026-09-18)

Kullanıcı bildirimi (ekran görüntüsüyle): kamerada gayet net, tam karşıdan
görünen bir plaka ("02 AFP 552"), panelde "02 AFP 55" (SONDAKİ rakam eksik)
olarak, **%100 güvenle** ve **6/6 karenin "oydaşmasıyla"** kaydedildi --
yani panel bu okumayı en yüksek güven rozetiyle "kesinleşmiş" gösteriyordu,
oysa yanlıştı.

**Kök neden araştırması:** fast_alpr kütüphanesinin (PTS'nin kullandığı ANPR
motoru) kaynak koduna bakıldığında, dedektörün önerdiği kutunun HİÇBİR kenar
boşluğu (padding) eklenmeden tam sınırlarından kırpılıp OCR'a öyle verildiği
görüldü (`cropped_plate = img[y1:y2, x1:x2]` -- kütüphane bunun için
yapılandırılabilir bir padding/margin parametresi de sunmuyor). Yani
dedektörün önerdiği kutunun sağ kenarı son karaktere birkaç piksel yakın
kalırsa, o karakter OCR'a HİÇ ULAŞMADAN kırpılabiliyor. Bu durumda OCR
gördüğü (eksik) karakterlerin HEPSİNİ yine de yüksek güvenle okuyor --
düşük güven eşiği bunu YAKALAYAMAZ, çünkü ortada zayıf okunan bir karakter
yok, sadece hiç görülmemiş bir karakter var. Bu, kutu geometrisi aynı
kaldığı için (aynı araç, aynı açı) bir oturumdaki TÜM karelerde tutarlı
biçimde tekrarlanabiliyor -- "6/6 kare oydaştı" bunun için yanıltıcı bir
güvence, çünkü tüm kareler AYNI (eksik) şekilde kırpılmış olabilir.

**Yapılan düzeltmeler (`backend/camera_reader.py::PlakaOyBirikimi`):**

1. **"Sondan karakter eksik" düzeltmesi:** karakter kırpılması (sondan
   eksik okuma), OCR'ın var olmayan bir karakteri UYDURMASINDAN çok daha
   yaygın bir hata sınıfıdır. Artık aynı oturumda hem kısa hem de TAM
   OLARAK sonuna bir karakter eklenmiş uzun bir varyant görüldüyse VE kısa
   varyant EZİCİ bir çoğunlukla kazanmıyorsa (uzun varyant, kısa varyantın
   en az %34'ü kadar oy aldıysa -- bkz. `SONDAN_EKSIK_KARAKTER_TERCIH_ORANI`),
   daha uzun varyant tercih edilir. Kısa varyant ezici çoğunluktaysa (örn.
   10 karede 9 kez kısa, 1 kez uzun) bu YİNE DE geçersiz kılınmaz --
   gerçekten daha kısa bir plaka olma ihtimaline karşı çoğunluk oyu korunur.
   Fark SONDA değilse (örn. harf grubunun ORTASINA bir harf eklenmiş/
   çıkmışsa) bu düzeltme hiç uygulanmaz -- farklı bir hata sınıfı olduğu
   için yanlış pozitif riskini artırmamak adına kasıtlı olarak dışarıda
   bırakıldı (bkz. `backend/metin_araclari.py::sondan_bir_karakter_eksik_mi`
   ve testleri).
2. **Güven artık KAZANAN metne ait:** ÖNCEDEN panelde gösterilen "güven"
   değeri, oturumdaki TÜM varyantlar arasındaki (kazanan metinle hiç ilgisi
   olmayabilecek) global en yüksek değerdi -- azınlıkta kalan, oylamayı
   kaybeden hatalı bir okumanın rastgele yüksek güvenli olması, panelde
   KAZANAN okumanın da o kadar güvenilir olduğu YANLIŞ izlenimini
   veriyordu. Artık her zaman gerçekten kaydedilen metnin kendi okumaları
   arasındaki en yüksek güvendir.
3. **Çelişki artık panelde görünüyor:** oturumda kaç FARKLI metin
   varyantının önerildiği (`farkli_okuma_sayisi`) ÖNCEDEN yalnızca log
   satırına yazılıp atılıyordu -- artık kayıtla birlikte API'ye gönderilir,
   veritabanına kalıcı olarak yazılır (`plaka_kayitlari.farkli_okuma_sayisi`)
   ve panelde "Doğrulama" sütununda görünür: 1'den büyükse "✓ N kare" yeşil
   rozeti yerine **"⚠ N kare (çelişkili)"** turuncu/kırmızı rozeti gösterilir
   (fare ile üzerine gelince kaç farklı okuma olduğu ve son karakteri elle
   kontrol etme uyarısı çıkar). Kamera pipeline'ından gelmeyen kayıtlarda
   (manuel giriş, eski kayıtlar) bu alan `None` kalır.

**Bunun ÇÖZMEDİĞİ durum (dürüstçe belirtilmeli):** eğer bir oturumdaki
TÜM kareler aynı (eksik) şekilde kırpıldıysa -- yani doğru/uzun varyant bir
kez bile OCR'a hiç önerilmediyse -- yukarıdaki oylama düzeltmesi bunu telafi
edemez, çünkü doğru metin ortada hiç yoktur. Bu durumda gerçek çözüm yazılım
tarafında değil, kamera/dedektör tarafındadır: kamera açısını/zoom'unu
plakanın etrafında biraz boşluk kalacak şekilde ayarlamak, veya
`PTS_ANPR_DETECTOR_MODEL`'i daha yüksek çözünürlüklü bir modele
(`yolo-v9-s-608-license-plate-end2end` gibi -- bkz. `anpr_engine.py`)
yükseltmek, kutunun daha isabetli (ve genelde biraz daha toleranslı)
hesaplanmasına yardımcı olabilir. Panelde artık en azından bu tür kayıtlar
"⚠ çelişkili" olarak İŞARETLENDİĞİ için (madde 3), tamamen sessiz kalmıyor.

**Testler:** `tests/test_metin_araclari.py` (5 yeni, `sondan_bir_karakter_
eksik_mi` için) ve `tests/test_camera_reader.py` (5 yeni -- kullanıcının
bildirdiği tam senaryonun regresyon testi dahil, ayrıca "ezici çoğunluk
geçersiz kılınmaz", "ortadan farklıysa uygulanmaz" ve "güven azınlıktan
sızıntı yapmaz" güvenlik/doğruluk sınırlarının her biri ayrı test edildi).

## Çapraz Kamera Kısa Süreli Tekrarı (2026-09-18)

Kullanıcı talebi: "Giriş kamerasına bir araç plakası geldi ve sistem bunu
kayıt etti. Bu araç geçişine devam ederken çıkış kamerasının da açısına
giriyor -- yani ilk görüntü bir kameradan alındıysa diğer kameranın çekmesi
halinde bile 3 dakika içerisindeki görüntü farklı kameradan çıkış veya
giriş olarak gözükmesin." Yani: giriş ve çıkış kameraları fiziksel olarak
aynı geçidi/yolu paylaşıyorsa, bir aracın TEK geçişi her iki kameranın da
görüş alanına girip iki AYRI (ve çelişkili yönde) kayıt oluşturabiliyordu.

**Neden `camera_reader.py`'deki mevcut mekanizma bunu çözmüyordu:**
`KameraPipeline.son_plaka_zamani`/`tekrar_gecikme_sn` (varsayılan 30 sn)
zaten "aynı plakayı kısa sürede tekrar bildirme" diye bir şey yapıyordu --
ama bu, TEK bir `KameraPipeline` NESNESİNİN kendi belleğinde (Python
sözlüğünde) tutuluyor. Farklı kameralar (ayrı `KameraPipeline` nesneleri,
hatta ayrı süreçler/makineler) birbirinin tespitlerinden tamamen habersiz --
giriş kamerasının belleği, çıkış kamerasının 10 saniye önce ne kaydettiğini
asla bilemez. Bu yüzden çözüm, TÜM kameraların ortak gerçek kaynağı olan
**veritabanı** seviyesinde uygulandı (`backend/main.py::
_capraz_kamera_kisa_sureli_tekrar_mi`, `_kayit_olustur_ve_bildir` içinden
çağrılır): yeni bir otomatik kayıt oluşturulmadan hemen önce, aynı
(normalize edilmiş) plakanın, FARKLI bir `kamera_id`'den, yapılandırılmış
pencere içinde (varsayılan **180 sn = 3 dakika**, yeni sistem ayarı
`capraz_kamera_tekrar_penceresi_sn`) zaten kaydedilip kaydedilmediği
kontrol edilir. Varsa, yeni kayıt oluşturulmaz -- önceki (ilk kaydeden)
kameranın kaydı geçerli kalır, yüklenen görsel silinir ve istek
`{"atlandi": true, "sebep": "capraz_kamera_kisa_sureli_tekrar", ...}` ile
yanıtlanır (düşük güven skoru yüzünden atlanan tespitlerle AYNI, zaten var
olan "atlandi" deseni kullanıldı).

**Kapsam/güvenlik sınırları (kasıtlı):**

- Yalnızca OTOMATİK (kamera pipeline'ı / harici ANPR sistemi) tespitlere
  uygulanır. Elle girilen kayıtlar (`POST /kayitlar`, "Manuel Kayıt Ekle")
  bu kontrolden HİÇ geçirilmez -- görevlinin bilinçli girdiği bir kaydın
  sessizce atlanması yanlış olurdu.
- Kontrol yalnızca FARKLI bir `kamera_id` için geçerlidir -- AYNI kameranın
  kendi tekrarını bastırmak hâlâ `camera_reader.py`'nin (in-process,
  `tekrar_gecikme_sn`) işidir; bu yeni kontrol onun YERİNE değil, YANINA
  eklendi.
- Pencere `0` (veya negatif) yapılırsa özellik tamamen KAPANIR -- "Sistem
  Ayarları" panelinden yönetici tarafından değiştirilebilir.
- Yön (`yon`) bilgisine BAKILMAZ, yalnızca `kamera_id` farkına bakılır --
  kullanıcının talebi zaten yönden bağımsızdı ("çıkış veya giriş olarak
  gözükmesin").

**Dürüstçe belirtilmeli (kullanıcının kabul ettiği bir ödünleşim):** eğer
bir araç GERÇEKTEN 3 dakikadan kısa bir sürede girip çıkarsa (örn. çok hızlı
bir teslimat/indirme-bindirme), bu da aynı fiziksel geçiş gibi
değerlendirilip YALNIZCA ilk kayıt tutulur -- ikinci (gerçek) geçiş
kaydedilmez. Kullanıcı bu pencereyi bilinçli olarak 3 dakika istedi; site
ihtiyacına göre panelden daha kısa/uzun bir değere çekilebilir.

**Ayrıca düzeltilen, ilişkili bir hata (bu araştırma sırasında bulundu):**
`tekrar_gecikme_sn` sistem ayarı ÖNCEDEN tanımlıydı ama `_pipeline_baslat`
tarafından hiçbir zaman okunup `KameraPipeline`'a GEÇİRİLMİYORDU -- panelden
değiştirilse bile (üstelik panelde bir form alanı bile YOKTU) hiçbir etkisi
olmuyordu, tamamen sessiz/etkisiz bir ayardı. Artık hem gerçekten
`KameraPipeline`'a geçiriliyor hem de "Sistem Ayarları" panelinde bir form
alanı olarak görünüyor.

**Testler:** `tests/test_api.py`'ye 5 yeni test eklendi (çapraz kamera
tekrarının atlandığını, AYNI kameradan gelenin etkilenmediğini, pencere
dışındaki eski kaydın engellemediğini, pencere 0 iken özelliğin tamamen
kapandığını ve manuel kayıtların HİÇ etkilenmediğini doğrulayan) -- bu dosya
fastapi/sqlalchemy'ye ihtiyaç duyduğu için bu sandbox'ta çalıştırılamadı,
yalnızca `py_compile` ile sözdizimi doğrulandı (bkz. depodaki genel not).

## Bariyerde Bekleyen (Duran) Aracın Tekrar Tekrar Kayıt Oluşturması (2026-09-24)

Kullanıcı talebi: "bu plakayı neden 3 dakika içinde 3 defa çekmiş" -- Kayıtlar
panelinde, aynı plakanın (`39 AAY 008`), aynı kameradan (`Nizamiye Giriş`),
~90 saniye içinde 3 AYRI kayıt olarak göründüğü bir örnek paylaşıldı. Bu,
görevlinin kimlik/izin kontrolü için bariyerde birkaç dakika bekleyen sıradan
bir araçtı -- yani plaka gerçekten sürekli kamera görüş alanındaydı, sahte
bir tespit veya farklı bir araç değildi.

**Kök neden:** `PlakaOturumTakipcisi` (oy biriktirme/oturum mekanizması,
bkz. `camera_reader.py`), bir aracın plakasını art arda gelen karelerde
"aynı geçiş" olarak biriktirip TEK bir kazanan okuma üretmek için, bir
oturumun ne zaman "bittiğini" üç ayrı koşulla belirliyor:

1. `OTURUM_KAPANMA_SN` (1.2 sn) -- plaka bir süre hiç görülmezse (araç
   gerçekten ayrılmıştır),
2. `OTURUM_MAX_SURE_SN` (8.0 sn) -- plaka KESİNTİSİZ görülmeye devam etse
   bile, sürüklenen/yanlış OCR birikimini önlemek için oturum yine de
   zorla kapatılır (bu güvenlik sınırı, oy biriktirme mekanizmasının ilk
   eklendiği `cacf478` işlemesinden beri vardı),
3. `zorla=True` -- pipeline kapanırken bekleyen oturumları temizlemek için.

Sorun şuydu: `bitmis_oturumlari_al()`, bu üç kapanış nedenini birbirinden
AYIRT ETMİYORDU -- hepsi aynı şekilde "kazanan" üretiyordu. Bariyerde 8
saniyeden uzun bekleyen bir araç için oturum `max_sure` nedeniyle zorla
kapanıyor, kazanan API'ye gönderiliyor, HEMEN ARDINDAN yeni bir oturum
açılıyor (plaka hâlâ kamerada), 8 saniye sonra o da `max_sure` ile kapanıp
tekrar gönderiliyordu -- ve `KameraPipeline.tekrar_gecikme_sn` (varsayılan
30 sn) bunu engellemiyordu, çünkü her kapanış arası zaten 30 saniyeden uzun
sürüyordu (30 sn'lik bekleme her seferinde yeniden dolduruluyordu). Sonuç:
bariyerde bekleyen bir araç için görevlinin işlemi ne kadar sürerse sürsün,
~30+ saniyede bir yepyeni bir "geçiş" kaydı oluşuyordu.

**Neden basitçe `tekrar_gecikme_sn`'yi büyütmek çözüm değildi:** bu, sorunu
gizlemek olurdu, çözmek değil -- hem gereksiz yere UZUN bir süre boyunca
GERÇEKTEN farklı bir aracın aynı plakayla (çok nadir ama mümkün, örn. plaka
okuma hatası) tekrar tespitini de bastırırdı, hem de "araç ne kadar süre
beklerse beklesin asla ikinci kayıt oluşmaz" garantisini vermezdi (sadece
eşiği büyütürdü, sorunu ortadan kaldırmazdı).

**Uygulanan çözüm:** `bitmis_oturumlari_al()` artık her kazanana bir
`kapanma_nedeni` alanı ekliyor (`"sessizlik"` / `"max_sure"` / `"zorla"`,
bu sırayla önceliklendirilir). Yeni `KameraPipeline._oturum_gonderilmeli_mi()`
metodu, `kapanma_nedeni == "max_sure"` olan bir kazananı, aynı plaka için
DAHA ÖNCE de bir `max_sure` kapanışı yaşanmışsa (yani araç hâlâ oradaysa)
SESSİZCE atlar -- yeni bir `_suregelen_plakalar` sözlüğü bu "plaka şu an
sürüp gidiyor" durumunu izler. Araç sonunda gerçekten ayrıldığında (oturum
`sessizlik` nedeniyle kapanır), eğer bu akış için zaten bir kayıt
gönderilmişse o SON kapanış da tekrar kayıt üretmez (böylece aracın
bariyerdeki TÜM bekleme süresi için toplamda tam olarak BİR kayıt oluşur),
ama bayrak temizlenir ki aynı plaka GERÇEKTEN daha sonra tekrar gelirse
(normal `tekrar_gecikme_sn` kuralına tabi olarak) yeniden kayıt
oluşturabilsin.

**Kenar durum (kasıtlı olarak ele alındı):** bir araç, `max_sure`
kapanışından hemen sonra -- yeni oturum hiç açılmadan -- aniden ayrılırsa,
`_suregelen_plakalar`'da o plaka için bir bayrak kalır ama onu temizleyecek
bir `sessizlik` kapanışı asla gelmez; bu, plakanın GELECEKTE tekrar
gelişinin sessizce bastırılmasına yol açabilirdi. Bunu önlemek için yeni
`_SUREGELEN_PLAKA_ZAMAN_ASIMI_SN` (= `OTURUM_MAX_SURE_SN * 2.5` = 20 sn)
sabiti ile `_plaka_hafizasini_buda()` içinden çağrılan
`_suregelen_plakalari_buda()`, bu bayrakları zaman aşımıyla güvenlik ağı
olarak temizliyor.

**Kapsam:** yalnızca aynı kameranın KENDİ tespit akışını etkiler --
`_capraz_kamera_kisa_sureli_tekrar_mi` (yukarıdaki bölüm) ile aynı katmanda
DEĞİL, ondan önceki bir aşamada (oturum kapanışı seviyesinde) çalışır ve
onun yerine değil yanına eklendi.

**Testler:** `tests/test_camera_reader.py`'ye 5 yeni test eklendi:
`kapanma_nedeni`'nin üç senaryoda da doğru raporlandığı, bariyerde bekleyen
bir aracın tekrarlanan `max_sure` kapanışlarının ikinci bir kayıt
ÜRETMEDİĞİ (kullanıcının bildirdiği tam senaryonun regresyonu), aracın
sonunda ayrılmasının da ikinci bir kayıt üretmediği ama bayrağı doğru
temizlediği (ve çok sonra gelen GERÇEKTEN yeni bir geçişin yine de
kaydedildiği), normal/hızlı geçen bir aracın davranışının HİÇ
değişmediği (regresyon), ve güvenlik-ağı zaman aşımının stuck bayrağı
doğru şekilde temizlediği. Toplam: 230 test geçiyor (225 önceki + 5 yeni).

## "Son Geçişler" Panelinden Plaka Geçmişine/Manuel Kayda Erişim (2026-09-18)

Kullanıcı talebi: "bu ekranda son geçişlerde gözüken plakalara da
tıklandığında ziyaretçi ekleme aracın resmini görme kayıt etme gibi şeylerin
aynısını görmek istiyorum" -- Canlı İzleme sekmesindeki "Son Geçişler" yan
panelinde listelenen plakalara tıklandığında, Kayıtlar/Kara Liste/Kişiler
sekmelerinde zaten var olan plaka bazlı analiz ekranındaki imkanların
(tam geçiş geçmişi tablosu, kişi/kara liste durumu, "+ Manuel Kayıt Ekle"
formu) aynısı istendi.

Kod incelemesinde, uygulamada zaten İKİ ayrı "detay görüntüleme" akışının bir
arada var olduğu görüldü:

- `olayDetayAc(id)` / `#olayDetayModal`: TEK bir geçiş kaydına özel modal.
  "Son Geçişler" panelindeki satırlar zaten bunu açıyordu -- araç görseli,
  olay tipi, plaka/tarih/saat/site/nokta/yön, bağlı kişi bilgisi, güven
  skoru, OCR düzeltme notu, bariyer açma düğmesi ve (operatör+) "Ziyaretçi
  Girişi" hızlı onay kutusunu (bir tespiti tek adımda bir kişiye/daireye
  bağlayıp aynı anda bariyeri açan akış) gösteriyordu.
- `plakaAnalizAc(plaka)` / `#plakaAnalizModal`: PLAKA bazlı, o plakanın TÜM
  geçmişini gösteren zengin modal (istatistik kartları, kişi/kara liste
  durumu, düzenle/sil destekli tam geçiş geçmişi tablosu, "Kara Listeye
  Ekle" düğmesi, operatör+ için "+ Manuel Kayıt Ekle" formu). Bu ekran
  yalnızca Kayıtlar/Kara Liste tablolarındaki `data-plaka-analiz` etiketli
  plaka bağlantılarından açılabiliyordu -- "Son Geçişler" panelinden HİÇ
  erişilemiyordu.

Bu iki modal, işlevleri örtüşmeyen ve BİRBİRİNİ İKAME ETMEYEN farklı
amaçlara hizmet ettiği için ("Ziyaretçi Girişi" hızlı onayı ve bariyer açma,
o AN yakalanan olaya özel bilgi gerektirir; plaka geçmişi ve manuel kayıt ise
plakanın kendisine özel, olaydan bağımsız bilgidir), biri diğerinin yerine
geçirilmedi -- ikisi de "Son Geçişler" panelinden erişilebilir hale
getirildi:

- `olayDetayModal`'a yeni bir **"Plaka Geçmişi / Manuel Kayıt"** düğmesi
  eklendi (`#olayModalAnalizBtn`, "Bariyer Aç" ile "Kapat" arasında).
- Tıklandığında `olayDetayModal` kapanır ve aynı plaka ile `plakaAnalizAc()`
  açılır -- kullanıcı böylece tek bir tıklamayla plakanın tüm geçmişini
  görüp gerektiğinde manuel kayıt ekleyebilir veya kara listeye alabilir.
- Güvenlik: plaka değeri düğmenin `onclick`/`data-*` attribute'una statik
  olarak GÖMÜLMEDİ (bkz. app.js'teki mevcut XSS-önleme notu) -- her modal
  açılışında `_olayModalAnalizButonunuAyarla(kayit)` çağrılarak düğmenin
  `onclick`'i, `kayit.plaka_no`'yu doğrudan bir JS değişkeni olarak kullanan
  bir kapanışla (closure) yeniden kuruluyor.
- "Son Geçişler" panelindeki satırların kendi tıklama davranışı (hâlâ
  `olayDetayAc(id)`) DEĞİŞMEDİ -- hem ilk yüklemede hem SSE ile canlı
  eklenen satırlarda.

Yeni `tests/test_olay_detay_plaka_analiz.py` dosyası (bağımlılığı hafif,
gerçekten çalıştırılıp doğrulandı) şunları doğrular: düğmenin varlığını ve
plaka değerini attribute'a gömmediğini, `olayDetayAc()`'ın yeni yardımcıyı
çağırdığını, yardımcının doğru iki modalı (kapat/aç) yönettiğini, ve panel
satırlarının hâlâ `olayDetayAc` çağırdığını.

## Güvenlik Personeli Vardiya Filtresi (2026-09-18, 2026-09-20'de öz-hizmete geçirildi)

Kullanıcı talebi (özetle): sistemi kullanacak güvenlik personeli için
"Kullanıcılar" sekmesinden yeni kullanıcı oluşturma ekranı istendi. Bu
personel yalnızca Canlı İzleme/Ana Sayfa/Kayıtlar/Kişiler/Kara Liste
alanlarını görebilmeli (zaten "operatör" rolüyle aynı 5 alan). Asıl fark:
her güvenlik personeli, Kayıtlar listesinde/raporlarda YALNIZCA KENDİ
VARDİYASINDA geçen araçları görmeli; yönetici panelinden ise her zaman TÜM
kayıtlar görünmeye devam etmeli. Ayrıca: aynı anda birden fazla güvenlik
personelinin vardiyası çakışıyorsa bir kayıt dışlayıcı biçimde tek kişiye
değil, o an vardiyası olan HERKESİN listesinde ayrı ayrı görünmeli.

**GÜNCELLEME (2026-09-20, birebir):** "bu sistemi kullanacak güvenlik
personellerimiz olacak ... bunu sürekli ben yapamam vardiyaya gelen personel
kendisi vardiya başlangıcını kendisi yapabilsin ... kullanıcı giriş yapınca
çıkış yapana kadar onun vardiyası devam etsin" -- yöneticinin her personel
için her günü ELLE vardiya olarak girmesi (eski "Vardiya Planlama" ekranı,
`models.VardiyaAtamasi`) yerine, vardiya artık PERSONELİN KENDİ giriş/
çıkışına bağlı: bir güvenlik hesabıyla giriş yapıldığı an vardiyası başlar,
"Çıkış" yapılana (ya da unutulursa bir sonraki girişte otomatik) kadar sürer.

### Tasarım

- **Yeni rol: `güvenlik`** (bkz. `backend/schemas.py::GECERLI_ROLLER`,
  `backend/main.py::ROL_GUVENLIK`). Yetki/görünürlük açısından `operatör`
  ile **BİREBİR AYNI** kademede -- `_rol_dogrula`, çağıranın rolünü kontrol
  etmeden ÖNCE `güvenlik`'i `operatör`'e eşler, böylece dosyadaki onlarca
  mevcut `_rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)` çağrısının
  HİÇBİRİNE dokunmadan güvenlik rolü de aynı işlemlere otomatik izinli olur.
  Frontend'de de aynı eşdeğerlik `ROL_SEVIYE = {..., "operatör": 1,
  "güvenlik": 1, ...}` ile sağlanıyor.
- **Öz-hizmet vardiya oturumu: `models.VardiyaOturumu`** (eski, artık
  KULLANILMAYAN `models.VardiyaAtamasi`'nin yerini alır -- o sınıf/tablo,
  üretimdeki mevcut veriyi bozmamak için kodda bırakıldı ama hiçbir yerde
  okunup yazılmıyor). Bir satır = TEK BİR oturum: `giris_zamani` başarılı bir
  `/auth/giris` çağrısının, `cikis_zamani` de `/auth/cikis` çağrısının zaman
  damgasıdır ve oturum kapanana kadar NULL kalır (bkz. `main.py::
  _guvenlik_oturum_baslat`, `::cikis_yap`). "Unutulan çıkış" (tarayıcı,
  `/auth/cikis` hiç çağrılmadan kapatılırsa) ZARARSIZDIR: aynı kullanıcı bir
  dahaki sefer TEKRAR giriş yaptığında eski açık oturum o anda otomatik
  kapatılır ve yeni bir oturum açılır -- unutulan bir çıkış asla bir sonraki
  vardiyanın kayıtlarına karışmaz. HH:MM string'ler ve gece-yarısı-geçme
  hesaplaması gibi eski karmaşıklık tamamen ORTADAN KALKTI: oturumlar zaten
  gerçek datetime'lar olduğu için pencere ne kadar sürerse o kadar sürer.
- **Filtre mantığı** (`main.py::_guvenlik_kayit_filtresi_uygula`,
  `_pencere_icinde_mi`): bir kayıt, kullanıcının vardiya oturumlarından
  HERHANGİ BİRİNE denk düşüyorsa görünür (`cikis_zamani` NULL olan bir oturum
  için üst sınır YOKTUR -- giriş anından bu yana geçen HER ŞEY dahildir).
  Çakışan oturumlarda birden fazla kullanıcıya AYNI ANDA ait olabilir --
  dışlayıcı bir atama yok. Hiç vardiya oturumu yoksa GÜVENLİ TARAF seçildi:
  varsayılan olarak HER ŞEYİ göstermek yerine HİÇBİR kayıt döndürülmüyor
  (normal akışta bu durum oluşmaz -- her girişte otomatik bir oturum açılır
  -- ama savunma amaçlı korunuyor).
- **Yeni uç noktalar**: `POST /auth/cikis` (herkes çağırabilir, yalnızca
  `güvenlik` rolü için anlamlıdır -- açık oturumu kapatır). Yalnızca
  yönetici: `GET /vardiya-oturumlari` (izleme), `POST /vardiya-oturumlari/
  {id}/sonlandir` (açık kalmış bir oturumu elle sonlandırma -- ELLE
  OLUŞTURMA uç noktası YOK, oturumlar yalnızca giriş/çıkışla açılıp kapanır),
  `GET /vardiya-oturumlari/durumum` (bkz. aşağıdaki "Teşhis Aracı" bölümü).
- **Yeni arayüz**: "Yeni Kullanıcı" formunda "Güvenlik Personeli" rol
  seçeneği (artık vardiyasının ELLE atanmadığını, giriş/çıkışa bağlı
  olduğunu açıklıyor). Kullanıcılar sekmesindeki eski "Vardiya Planlama"
  kartı (Vardiya Ata formu) TAMAMEN KALDIRILDI; yerine salt-okunur "Vardiya
  Oturumları" izleme tablosu geldi (giriş/çıkış zamanı, durum, ve açık bir
  oturum için "Sonlandır" butonu). Kayıtlar sekmesindeki `#guvenlikVardiyaBilgisi`
  banner'ı ("Bu liste yalnızca SİZİN vardiyanıza denk gelen kayıtları
  gösterir") aynen korundu.

### Filtrenin uygulandığı yerler (kapsam)

Bu bir GÖRÜNÜRLÜK filtresidir; aşağıdaki TÜM uç noktalara uygulandı: kayıtlar
listesi (`GET /kayitlar`, `/kayitlar/sayfa-bilgisi`, eski `/olaylar` uç
noktası), plaka analizi geçmişi (`GET /kayitlar/analiz/{plaka}` -- yalnızca
geçmiş listesi ve "Toplam/Son Geçiş" istatistikleri; kişi/kara liste bilgisi
PLAKAYA ait sabit veri olduğu için filtreye TABİ DEĞİL), panel
istatistiklerinin KAYIT bazlı alanları (`bugunku_kayit`,
`yetkisiz_giris_denemesi`, `kara_liste_gecis` -- `toplam_kayit` ve
`aktif_kisi_sayisi`/`kara_liste_kayit_sayisi` birer geçiş KAYDI olmadığı
için bilinçli olarak filtre DIŞI bırakıldı), dashboard grafiği
(`GET /kayitlar/grafik`), dışa aktarma raporları (`/disa-aktar/excel/kayitlar`,
`/disa-aktar/pdf/kayitlar`, ve tekil `/disa-aktar/pdf/kayit/{id}` -- bu
sonuncusu, kayıt vardiya dışındaysa 403 döner), ve canlı SSE akışı
(`/olaylar/sse` -- bağlı istemcinin rolü/kimliği artık kuyrukla birlikte
tutuluyor, bkz. `_sse_yayinla`, ki güvenlik personeli "Son Geçişler"
panelinde kendi vardiyası dışındaki bir plakanın anlık belirmesini
GÖRMESİN -- aksi halde liste filtresiyle tutarsız, sessiz bir bilgi
sızıntısı olurdu).

**Bilinçli sınır** (kaydı DÜZENLEME/SİLME yetkisi vardiya dışı kayıtlar için
AYRICA kısıtlanmadı -- bu da bir GÖRÜNÜRLÜK kısıtlamasıdır, kaydın ID'sini
zaten bilen bir istemciye karşı ekstra bir yetkilendirme katmanı DEĞİLDİR) ve
canlı SSE filtresi entegrasyon testiyle DEĞİL yalnızca kod incelemesiyle
doğrulandı (TestClient ile bir SSE akışını uçtan uca test etmek bu
değişikliğin kapsamı için orantısız bir karmaşıklık getirirdi).

### Testler

`tests/test_guvenlik_vardiya_frontend.py` (gerçekten çalıştırılıp
doğrulandı): "güvenlik" rol seçeneğinin varlığını ve açıklama metnini, eski
Vardiya Ata formunun KALDIRILDIĞINI, yeni "Vardiya Oturumları" izleme
tablosunun varlığını, `ROL_SEVIYE`'de `güvenlik`/`operatör` eşdeğerliğini, ve
`oturumKapat()`'ın token silinmeden ÖNCE `/auth/cikis`'i çağırdığını
doğrular. `tests/test_api.py`ye eklenen testler (fastapi/sqlalchemy
gerektirdiği için bu sandbox'ta çalıştırılamadı, yalnızca `py_compile` ile
doğrulandı): güvenlik kullanıcısının operatör yetkilerine sahip ama yönetici
işlemi yapamadığını; girişin otomatik olarak TAM OLARAK bir açık oturum
açtığını ve bu oturumların yalnızca yönetici tarafından listelenip
sonlandırılabildiğini; oturum açılmadan ÖNCEKİ bir kaydın görünmediğini;
oturum kaydı elle silinmiş gibi bir durumda fail-closed davranışın hâlâ
çalıştığını; girişin AÇTIĞI oturumun o andan itibaren gerçekleşen kayıtları
hemen gösterdiğini (hem listede hem istatistiklerde); `/auth/cikis`
sonrasında vardiyanın kapandığını ve sonraki kayıtların görünmediğini;
çıkış yapılmadan tekrar giriş yapılırsa ÖNCEKİ (unutulmuş) oturumun otomatik
kapatılıp YENİ birinin açıldığını; gece yarısını geçen bir oturumun doğru
filtrelendiğini (mutlak takvim tarihleriyle, testin çalıştığı saatten
BAĞIMSIZ); aynı gün içinde iki ayrı oturumla (bölünmüş vardiya) her iki
pencerenin de doğru filtrelendiğini; çakışan açık oturumlarda aynı kaydın İKİ
güvenlik kullanıcısında da göründüğünü; dışa aktarma uçlarının (`kullanici`
parametresinin FastAPI DI'ı olmadan doğrudan çağrıldığı için AÇIKÇA
geçirilmesi gerektiği) güvenlik kullanıcısıyla çalıştığını; ve raporlardaki
"Vardiya" sütununun (aşağıya bkz.) doğru etiketlendiğini.

## Vardiya Oturumu Teşhis Aracı (2026-09-18, 2026-09-20'de öz-hizmete uyarlandı)

**Neden gerekli:** filtre canlıya alındıktan sonra bir kullanıcı, kendi
vardiyasını atadığı halde o pencere içinde gerçekleşen YENİ/canlı bir
geçişin Kayıtlar sekmesinde (ve Canlı İzleme'de) hâlâ görünmediğini bildirdi.
Filtre tamamen SUNUCU tarafında, `datetime.now()` ile hesaplanan pencerelere
göre çalıştığı için, en olası kök nedenlerden biri sunucunun sistem saatinin
(üretimde bir Windows makinesi) yönetici panelini kullanan kişinin bildiği
saatten FARKLI olmasıdır (saat dilimi/senkronizasyon sorunu) -- bu yüzden kör
tahminle bir "düzeltme" göndermek yerine, sorunu kullanıcının KENDİSİNİN
teşhis edebileceği bir araç eklendi ("sıfır sessiz hata" ilkesi).

**Ne var:**
- `GET /vardiya-oturumlari/durumum`: rol kontrolü yapmaz (yalnızca çağıranın
  KENDİ verisini döner), ama `güvenlik` rolü dışındaki kullanıcılar için de
  zararsız bir yanıt verir (`{"rol_guvenlik_mi": false, "sunucu_simdiki_
  zaman": ...}`). `güvenlik` rolü için ayrıca: o an açık bir oturumu olup
  olmadığını (`su_an_aktif_vardiya_var_mi`), toplam oturum sayısını ve her
  oturumun giriş/çıkış zamanlarıyla `devam_ediyor` durumunu döner.
- Kayıtlar sekmesindeki `#guvenlikVardiyaBilgisi` banner'ının içindeki
  `#guvenlikVardiyaDurumu` alt alanı bu uç noktayı çağırıp SUNUCU saatini
  kullanıcının TARAYICI saatiyle yan yana gösterir, açık/kapalı durumu ve
  son oturumları listeler, ve iki saat birbirinden FARKLIYSA ayrı bir uyarı
  satırı ekler (`guvenlikVardiyaDurumunuGuncelle()`, `frontend/app.js`). Bu
  fonksiyon hem girişten hemen sonra (`rolBazliArayuzuUygula()` içinde) hem
  de periyodik panel yenilemesinde (`panelYenile()` içinde) tetiklenir.

## Raporlarda "Vardiya" Sütunu (2026-09-20)

**Kullanıcı talebi (birebir):** "bu arada her vardiya için kendi geçiş
raporları olsun Eser Akar geçiş raporu alınca geçiş raporunda eser akar'ın
vardiyası diye raporda bir sütun tanımlansın" -- personel aynı gün içinde
birden fazla kez giriş/çıkış yapabildiği (bölünmüş vardiya) için, bir
kaydın HANGİ oturuma ait olduğu raporda ayrıca görünmeli.

**Ne eklendi:** dışa aktarma (Excel/PDF) satırlarını üreten `main.py::
_kayitlari_rapor_satirlari`, her kayıt için `main.py::
_vardiya_etiketleri_haritasi` ile o kaydın gerçekleştiği anda AÇIK olan
TÜM güvenlik oturumlarını (kullanıcı adı + giriş saati, "devam ediyor" ya da
bitiş saati) bulup `"Ad Soyad (HH:MM-HH:MM)"` biçiminde bir metne çevirir
(aynı anda birden fazla personelin oturumu açıksa hepsi noktalı virgülle
listelenir). Bu değer, hem `excel_export.kayitlar_excel_olustur` hem
`pdf_export.kayitlar_pdf_olustur` çıktısına referans rapor biçimine EK
olarak en sona eklenen "Vardiya" sütununa yazılır (tıpkı "ID" gibi, referans
üründe olmayan ama sistemimize özgü bir sütun). N+1 sorgudan kaçınmak için
TÜM güvenlik oturumları tek seferde çekilip bellekte eşleştirilir.

**Testler:** `tests/test_api.py::test_rapor_vardiya_sutunu_acik_oturumdaki_
kaydi_dogru_etiketler` (yalnızca `py_compile` ile doğrulandı), bir güvenlik
kullanıcısının oturumu açılmadan ÖNCEKİ bir kaydın "vardiya" alanının BOŞ,
oturum AÇIKKEN oluşan bir kaydın ise o kullanıcının adıyla etiketlendiğini
doğrular. `tests/test_excel_export.py` ve `tests/test_pdf_export.py`
(gerçekten çalıştırılıp doğrulandı) güncellendi: yeni sütunun başlıkta ve
veri satırında doğru yer aldığını, ve formül enjeksiyonuna karşı AYNI
korumanın (bkz. `excel_export._guvenli_hucre`) bu sütun için de geçerli
olduğunu doğrular.

## Kalıcı Test Altyapısı

`tests/` klasöründe pytest tabanlı bir test paketi var:

- `test_plaka_dogrula.py`, `test_lisans.py`, `test_schemas.py`, `test_camera_reader.py`,
  `test_metin_araclari.py`, `test_pdf_export.py`, `test_excel_export.py`, `test_frontend_rbac.py`,
  `test_olay_detay_plaka_analiz.py`, `test_guvenlik_vardiya_frontend.py`,
  `test_bildirim_tiklama_ve_roi_polygon.py`:
  bağımlılığı hafif (fastapi/sqlalchemy gerektirmez), yalnızca pydantic/opencv/requests/
  reportlab/pdfplumber/openpyxl/BeautifulSoup gibi hedefe özel kütüphaneler yeterlidir.
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
  için de erişilebilir. Ayrıca panelin TÜM formlarındaki `<label>` etiketleri
  (55 adet) artık ilgili giriş alanına `for="..."` ile eşleşiyor — önceden
  yalnızca görsel yakınlıkla ilişkiliydi, ekran okuyucu kullanıcıları için bir
  etikete tıklamak/odaklanmak ilgili alanı seçmiyordu.

**2026-09-16 (devam) — başlatma betikleri (`calistir.bat`/`calistir.sh`) sertleştirmesi:**

Sahada canlı olarak şu belirti gözlemlendi: 8000 portu başka bir işlem
(örn. PTS'in kapatılmamış eski bir kopyası, ya da hem NSSM/Windows Servisi
hem de elle çalıştırılan `calistir.bat`'ın aynı anda çalışması) tarafından
zaten kullanılıyorken `calistir.bat` her 5 saniyede bir "PTS beklenmedik
şekilde durdu, yeniden başlatılıyor" mesajıyla SONSUZA KADAR yeniden
başlatmayı deniyordu — kullanıcıya gerçek nedeni (`WinError 10048`: port
zaten kullanımda) hiçbir zaman anlaşılır biçimde söylemeden. Artık her iki
betik de:

- Başlamadan ÖNCE 8000 portunun zaten kullanımda olup olmadığını kontrol
  ediyor; doluysa hangi PID'nin tuttuğunu ve ne yapılması gerektiğini
  (o süreci doğrulayıp kapatma komutu dahil) açıkça yazıp duruyor —
  garantili başarısız bir başlatma denemesi yapmıyor.
- Uvicorn gerçekten beklenmedik şekilde çökerse otomatik olarak yeniden
  başlatmaya devam ediyor (bu faydalı davranış korundu), AMA art arda 5 kez
  KISA sürede (60 saniyeden az çalışıp) çökerse -- ki bu kalıcı bir
  yapılandırma sorununa işaret eder -- sonsuz döngüye girmeden durup
  `loglar/pts.log`'a bakılmasını öneriyor. En az 60 saniye sorunsuz
  çalıştıktan sonraki bir çökme GEÇİCİ sayılır ve deneme sayacı sıfırlanır
  (yani yıllarca kararlı çalışan bir kurulum, ara sıra yaşanan tek seferlik
  bir ağ kesintisinde bu korumaya takılıp tamamen durmaz).
- `calistir.sh` ayrıca artık proje kökünden (`backend/` alt klasöründen
  değil) çalışıyor ve `uvicorn backend.main:app` modül yolunu kullanıyor —
  bu, zaten `calistir.bat`'ın kullandığı ve testlerin (`tests/test_api.py`)
  varsaydığı tek doğru içe aktarma yoludur. Ayrıca dosyanın Git'teki
  çalıştırılabilir izni eksikti (`chmod +x`) — README'de belgelenen
  `./calistir.sh` komutu bu olmadan "İzin reddedildi" hatası verirdi; artık
  düzeltildi.

**2026-09-16 (devam) — klasöre fotoğraf bırakarak kayıt oluşturma + bir güvenlik başlığı hatası:**

- Yukarıda "Kamera Olmadan Test: Bir Klasöre Fotoğraf Bırakarak Otomatik
  Kayıt" bölümünde belgelenen `PTS_GORSEL_IZLEME_DIZINI` özelliği eklendi
  (bkz. `camera_reader.py::KlasorIzleyici`).
- **Bulunan ve düzeltilen bir hata:** `camera_reader.py`'deki gerçek kamera
  pipeline'ı, tespit ettiği bir plakayı `/kayitlar/otomatik`'e gönderirken
  `X-PTS-Kamera-Anahtari` başlığını HİÇ göndermiyordu — oysa bu uç nokta,
  `PTS_KAMERA_ANAHTARI` ayarlıysa (README'nin kendisinin, backend farklı bir
  ağdaysa önerdiği bir sıkılaştırma) tam olarak bu başlığı zorunlu kılıyor.
  Yani bu öneriyi uygulayan bir kurulumda, Python pipeline'ının tespit ettiği
  HER plaka sessizce 401 ile reddedilir hale gelirdi — "kamera görüntü
  alıyor, plakayı doğru okuyor, ama yine de hiçbir zaman kayda düşmüyor"
  sınıfından, teşhisi zor bir kayıp. Artık pipeline da aynı ortam
  değişkenini okuyup başlığı ekliyor.

**2026-09-17 (devam) — "PTS_ANPR_DETECTOR_ESIGI ayarım kabul edildi mi?"
sorusuna kesin cevap:** Sahada tekrar aynı sınıftan iki araç ("59 ADG 364",
"39 ACJ 043") net görünüp kayda düşmeden geçince ve `PTS_ANPR_DETECTOR_ESIGI`
0.25'e düşürülüp uygulama yeniden başlatıldığında, panelin **"Min. plaka
tanıma güveni"** alanı da 0,25 olarak ayarlanmıştı — fakat bu iki ayar
BİRBİRİNDEN TAMAMEN FARKLIDIR ve bu karışıklık gerçek sorunu gizliyordu:

- **"Min. plaka tanıma güveni"** (panel, Sistem Ayarları): veritabanında
  saklanan `min_guven_skoru` değeridir. Panelden anında değişir, sunucu
  yeniden başlatılmasına gerek duymaz. Ama yalnızca dedektör bir plaka
  ADAYI bulup OCR onu OKUDUKTAN SONRA devreye girer — "okundu ama güven
  düşük, kaydetme" filtresidir.
- **`PTS_ANPR_DETECTOR_ESIGI`**: bir işletim sistemi ortam değişkenidir,
  panelden HİÇ ayarlanamaz. Yalnızca uygulama açılışında, `anpr_engine.py`
  içinde bir kez okunur ve FastALPR'ın YOLO dedektörünün kendi iç eşiğini
  belirler — OCR'a giden aday kutuların üretildiği, min_guven_skoru'ndan
  ÖNCEKİ aşamadır. Bu ikisi arasındaki fark tam olarak "araç net görünüyor
  ama dedektör hiçbir aday bile bulamıyor" (bu README'de yukarıda anlatılan
  sorun) ile "aday bulundu ama OCR güveni düşük" arasındaki farktır.

Daha da kötüsü: `PTS_ANPR_DETECTOR_ESIGI` fiilen doğru okunup uygulansa
bile, eskiden hiçbir log satırı veya panel göstergesi bunu DOĞRULAMIYORDU —
tekrarlayan "boş tespit" özet logu her zaman sabit "varsayılan 0.4" metnini
yazdırıyordu (gerçek değeri değil), bu yüzden kullanıcı ayarının kabul
edilip edilmediğini anlamanın hiçbir yolu yoktu. Artık:

1. Uygulama açılışında `anpr_engine.py`, dedektör eşiğinin FİİLEN hangi
   değerle ve hangi kaynaktan (ortam değişkeninden mi, kütüphane
   varsayılanından mı) çalıştığını açıkça loglar.
2. "Boş tespit" özet logu artık sabit bir metin değil, o an GEÇERLİ olan
   eşiği ve kaynağını yazdırır.
3. `/sistem/saglik` yanıtına ve panelin Sistem sekmesine (Sistem Sağlığı
   kartı, "Dedektör Eşiği" satırı) bu bilgi eklendi — log dosyasına
   inmeden, tek bakışta, ayarınızın kabul edilip edilmediğini görebilirsiniz.

**`PTS_ANPR_DETECTOR_ESIGI`'yi Windows'ta doğru ayarlama (sık yapılan hata):**
`setx PTS_ANPR_DETECTOR_ESIGI 0.25` komutu, çalıştırıldığı anda AÇIK olan
hiçbir pencereyi (o pencerenin kendisi dahil) etkilemez — yalnızca o
komuttan SONRA açılan YENİ pencerelerde başlatılan süreçler bu değeri
görür. Doğru sıra:
1. Herhangi bir cmd penceresinde `setx PTS_ANPR_DETECTOR_ESIGI 0.25` çalıştırın.
2. O pencereyi kapatın (veya en azından `calistir.bat`'ı ORADA çalıştırmayın).
3. Tamamen YENİ bir cmd penceresi açın, `echo %PTS_ANPR_DETECTOR_ESIGI%`
   ile değerin göründüğünü doğrulayın, ardından `calistir.bat`'ı o yeni
   pencereden başlatın.
4. Panelin Sistem sekmesinde "Dedektör Eşiği" satırının `0.25` gösterdiğini
   doğrulayın — hâlâ `0.40` gösteriyorsa, adım 1-3 doğru sırayla
   yapılmamış demektir (aynı sorunu Windows hizmeti/NSSM olarak
   çalıştırıyorsanız `setx`, hizmeti YENİDEN OLUŞTURMADAN görünmez;
   hizmetin ortam değişkenlerini kendi yapılandırmasından ayarlamanız gerekir).

**2026-09-17 (devam) — eşik yetmiyorsa: dedektörün giriş çözünürlüğü
(`PTS_ANPR_DETECTOR_MODEL`):** `PTS_ANPR_DETECTOR_ESIGI` doğru şekilde
uygulandıktan sonra bile, kamerada BÜYÜK/net/tam karşıdan görünen bir plaka
("39 SR 525") sahada yine kayda düşmedi. Bu, sorunun artık "eşik çok katı"
değil, muhtemelen **dedektörün giriş çözünürlüğü** olduğunu gösteriyor:

FastALPR'ın kullandığı dedektör (`open_image_models` projesinden), önüne
verilen KARENİN TAMAMINI kendi sabit giriş boyutuna (model ismindeki sayı,
örn. `-384-`) küçültüp öyle işler. Kamera 1920x1080 gibi geniş bir görüş
alanı çekiyorsa ve o tarihte kullanılan `yolo-v9-t-384-license-plate-end2end`
modeli bu koca sahneyi yalnızca 384x384 piksele sıkıştırıyorsa, plaka insan
gözüne "büyük ve net" görünse bile modelin GERÇEKTEN gördüğü küçültülmüş
karede birkaç piksele düşüp fark edilemez hale gelebilir — bu, eşiği ne
kadar düşürürseniz düşürün değişmeyen bir sınırlamadır (dedektör hiçbir
aday üretmiyorsa, eşik onu zaten aşağı çekemez). **(2026-09-24 güncellemesi:
bu bölümdeki `-384-` artık PTS'nin varsayılanı DEĞİL -- aşağıdaki
"2026-09-24" başlıklı bölüme bakın.)**

`open_image_models` projesi AYNI kütüphanenin (yani `pip install fast-alpr`
ile zaten kurulu olanın) İÇİNDE, farklı çözünürlüklerde birden fazla model
sunuyor — bunlardan birini seçmek için tek yapılması gereken bir ortam
değişkeni ayarlamak; **ayrı bir kurulum, "GitHub'dan entegrasyon" veya kod
değişikliği gerekmiyor.** Kaynak: https://github.com/ankandrew/open-image-models
(2026-09 itibarıyla):

| Model | Giriş boyutu | Recall (kaçırmama oranı) | mAP50 |
|---|---|---|---|
| `yolo-v9-t-256-license-plate-end2end` | 256px | 0.797 | 0.858 |
| `yolo-v9-t-384-license-plate-end2end` (PTS'nin 2026-09-24'e kadar varsayılanı idi) | 384px | 0.863 | 0.920 |
| `yolo-v9-t-416-license-plate-end2end` | 416px | 0.894 | 0.940 |
| `yolo-v9-t-512-license-plate-end2end` | 512px | 0.901 | 0.948 |
| `yolo-v9-t-640-license-plate-end2end` | 640px | 0.896 | 0.958 |
| **`yolo-v9-s-608-license-plate-end2end`** (en iyi recall + mAP50 — **2026-09-24'ten itibaren PTS'nin varsayılanı**) | 608px | **0.917** | **0.966** |

`recall` sütunu tam olarak aradığımız metrik: kaçırma oranının tersi. En
yüksek recall'a sahip `yolo-v9-s-608-license-plate-end2end`, 2026-09-24'ten
itibaren PTS'nin kendi varsayılanı (aşağıdaki `setx` artık gerekli DEĞİL --
yalnızca BUNUN DIŞINDA bir modele geçmek isterseniz kullanılır, bkz. altındaki
"2026-09-24" bölümü). O tarihten önceki bir PTS sürümünü elle denemek için:

```
setx PTS_ANPR_DETECTOR_MODEL yolo-v9-s-608-license-plate-end2end
```
(yine YENİ bir terminal penceresinden `calistir.bat`'ı başlatın — bkz.
yukarıdaki `setx` uyarısı). İlk açılışta bu model henüz indirilmemişse
FastALPR onu otomatik indirir (birkaç MB, İNTERNET bağlantısı gerektirir,
sadece ilk seferde); sonrasında yerel önbellekten çalışır. Panelin Sistem
sekmesindeki yeni "Dedektör Modeli" satırından hangi modelin fiilen
kullanıldığını doğrulayabilirsiniz. Bilinmeyen/yazım hatalı bir isim
verilirse uygulama başlangıçta bunu loglar ama yine de değeri olduğu gibi
dener (kütüphane kendi hata mesajını verir).

**Ödünleşim:** büyük model = daha fazla piksel = daha iyi recall, ama biraz
daha yavaş çıkarım (birkaç kamera için GPU/DirectML ile tipik olarak yeterince
hızlıdır; sorun yaşarsanız `PTS_ANPR_PROVIDERS=cpu` ile karşılaştırın).
Bilinçli bir mühendislik kararı olarak, PTS'ye tanımadığımız çok sayıda farklı
açık kaynak projesini ("her şeyi GitHub'dan toplayıp entegre etmek") elle
karıştırmak yerine, zaten kullanılan VE test edilmiş kütüphanenin kendi
sunduğu, ölçülebilir (recall/mAP tabloları yayınlanmış) alternatifini
seçilebilir hale getirmeyi tercih ettik — bu hem çok daha az risklidir
(yeni bağımlılık, lisans, bakım yükü yok) hem de sorunun kök nedenine
(çözünürlük) doğrudan hitap eder.

**2026-09-17 (devam) — sahadaki gerçek fotoğraflarla doğrulama:** Kullanıcının
paylaştığı, Dahua NVR'ın kendi ANPR'ının BAŞARIYLA okuduğu 7 aracın hem tam kare
(2688x1584px) hem de kırpılmış plaka (ör. 272x112px) görselleri üzerinde ölçüldü:
tam kare `-384-` modele küçültüldüğünde plaka yaklaşık **34-48x14-16px**'e
düşüyor (bazı araçlarda 16x9px kadar küçük) — bir "tiny" YOLO modeli için
gerçekten zorlayıcı bir boyut. Aynı plakalar `-608-` modelde yaklaşık
**54-76x22-25px**'e (yaklaşık %60 daha büyük) çıkıyor. Bu, README'nin
yukarısındaki tavsiyeyi (yolo-v9-s-608'e geçiş) somut verilerle doğruluyor.

**2026-09-24 — `yolo-v9-s-608-license-plate-end2end` artık PTS'nin
kod-içi varsayılanı, opt-in bir öneri olmaktan çıktı:** kullanıcı sorusu:
"yolo-v9-t-384-license-plate-end2end en güvenilir çözüm bu dedektör modeli
mi, şu anda daha güvenilir çözüme nasıl ulaşabiliriz". Yukarıdaki iki
2026-09-17 tarihli bölümde CEVAP zaten somut ölçümle verilmişti (`-608-`
modelde plakalar ~%60 daha büyük kalıyor, recall 0.863→0.917) — ama o
düzeltme yalnızca `PTS_ANPR_DETECTOR_MODEL` ortam değişkenini ELLE
ayarlayana kadar devreye girmeyen bir "öneri" olarak kalmıştı; hiçbir yerde
bu değişkenin fiilen ayarlandığına dair bir onay/iz yoktu. Kullanıcı
doğrudan "en güvenilir çözüm bu mu" diye sorunca, zaten kanıtlanmış bu
iyileştirmeyi bir daha unutulabilecek/elle uygulanması gereken bir öneri
olarak bırakmak yerine `backend/anpr_engine.py::DEDEKTOR_MODELI_VARSAYILAN`
doğrudan `yolo-v9-s-608-license-plate-end2end` yapıldı -- artık PTS_ANPR_
DETECTOR_MODEL ayarlanmasa bile YENİ kurulumlar ve bu patch'i uygulayan
mevcut kurulum otomatik olarak bu modeli kullanır.

**Bilinmesi gerekenler:**
- **İlk açılışta internet gerekir:** `-608-` modeli daha önce hiç
  indirilmediyse (bu makinede ilk kez kullanılıyorsa), FastALPR onu ilk
  açılışta otomatik indirir (birkaç MB). PTS'nin çalıştığı makinenin İLK
  YENİDEN BAŞLATMADA internete çıkabildiğinden emin olun; sonrasında yerel
  önbellekten çalışır, internet gerekmez.
- **Biraz daha yavaş çıkarım:** 608px giriş, 384px'den daha büyük bir kare
  işler -- birkaç kamera için GPU/DirectML ile tipik olarak sorun
  yaratmaz (bkz. yukarıdaki "Ödünleşim" notu); performans sorunu
  gözlemlenirse `PTS_ANPR_PROVIDERS=cpu` ile karşılaştırılabilir.
- **Eski/daha hafif bir modele dönmek isterseniz** artık `PTS_ANPR_
  DETECTOR_MODEL` ortam değişkenini bu YÖNDE (ör. tekrar `yolo-v9-t-384-
  license-plate-end2end`'e) ayarlamanız yeterli -- mekanizma değişmedi,
  sadece hangi yönde "override" olduğu değişti.
- Panelin Sistem sekmesindeki "Dedektör Modeli" satırından, PTS'nin
  gerçekten hangi modeli kullandığı her zaman doğrulanabilir.

**⚠️ 2026-09-18 — dışa aktarma uç noktalarında kimlik doğrulama eksikliği
bulundu ve düzeltildi:** Kayıtlar raporu biçimini kullanıcının paylaştığı
referans ürüne yaklaştırma çalışması sırasında (bkz. yukarıdaki "Kayıtlar
Raporu Biçimi ve Personel Toplu İçe Aktarma" bölümü), `GET /disa-aktar/excel/
kayitlar`, `/disa-aktar/pdf/kayitlar`, `/disa-aktar/pdf/kayit/{id}` ve
`/disa-aktar/excel/kisiler` uç noktalarının HİÇBİRİNİN kimlik doğrulama
gerektirmediği ortaya çıktı — frontend bu indirmeleri `<a>`/fetch yerine
`window.open()` ile açtığı için (bir dosya indirmesini yeni sekmede tetiklemenin
standart yolu budur) Authorization header'ı hiç eklenmemişti, bu yüzden uç
noktalara başlangıçta hiç kimlik doğrulama dependency'si konmamış. Sonuç:
plaka, ad-soyad, daire/departman ve araç görseli gibi KVKK kapsamındaki kişisel
verileri içeren bu raporlar, sunucuya erişebilen HERHANGİ bir istemci
tarafından (giriş yapmadan) indirilebiliyordu. Yeni eklenen personel toplu
içe aktarma şablonu uç noktası (`/kisiler/toplu-import/sablon`) da aynı
`window.open()` deseniyle açıldığından aynı açığı miras alacaktı; dördü de
tek seferde düzeltildi.

Düzeltme: `_giris_gerekli`, Authorization header'ına ek olarak (SADECE header
yokken devreye giren) bir `?token=` sorgu parametresini de kabul edecek şekilde
genişletildi, VE bu dört uç noktaya (+ yeni şablon uç noktasına) eksik olan
`Depends(_personel_girisi_gerekli)` bağımlılığı eklendi. Frontend tarafında
yeni bir `indirmeUrlOlustur()` yardımcı fonksiyonu, her `window.open()`
çağrısından önce oturumun JWT'sini `?token=` olarak indirme URL'ine ekliyor
(bkz. `frontend/app.js`). **Bilinmesi gereken davranış değişikliği:** bu
raporları eskiden elle kopyaladığınız veya bir betikle otomatik indirdiğiniz
bir bağlantı varsa, artık geçerli bir oturum token'ı olmadan çalışmayacaktır —
panel üzerinden yeniden indirin ya da otomasyonunuzu geçerli bir `token`
sorgu parametresi eklemek üzere güncelleyin.

**2026-09-20 — geniş kapsamlı kod denetimi ("eksik gördüğün eklenmesi ve
geliştirilmesi gereken neler varsa yapar mısın") sonrası düzeltilenler:**

- **Negatif `limit`/`offset` ile 500 kaydı üst sınırını atlatma:** `/kayitlar`,
  `/kayitlar/sayfa-bilgisi`, `/olaylar`, `/alarmlar` ve `/sakin/gecmisim` uç
  noktaları, `limit`/`offset` sorgu parametrelerini `min(limit, 500)` ile
  "kırpıyordu" — ama SQLite'ta (ve SQL Server'da) `LIMIT -1` (veya negatif bir
  değer) "sınırsız" anlamına gelir, yani `?limit=-1` göndermek bu kırpmayı
  TAMAMEN atlatıp veritabanındaki TÜM kayıtları (plaka/kişi gibi KVKK
  kapsamındaki verileri) tek istekte döndürüyordu — hem bir veri sızıntısı
  riski hem de büyük tablolarda bir DoS vektörü. Artık bu beş uç noktanın
  tümünde `limit`/`offset` FastAPI'nin `Query(..., ge=..., le=...)` doğrulaması
  ile sınırlanıyor: sınır dışı bir değer artık sessizce kırpılmıyor, açık bir
  422 ile reddediliyor.
- **Geçersiz tarih filtresi artık 500 yerine 400 döndürüyor:** `/kayitlar` ve
  `/kayitlar/sayfa-bilgisi`'ndeki `baslangic`/`bitis` parametreleri
  `datetime.fromisoformat()` ile ayrıştırılıyordu; geçersiz bir değer
  (`?baslangic=abc`) yakalanmamış bir `ValueError` fırlatıp isteği düz bir
  500'e düşürüyordu (istemciye hangi alanın sorunlu olduğunu hiç söylemeden).
  Yeni `_iso_tarih_parametresini_coz()` yardımcı fonksiyonu artık bunu hangi
  alanın ve hangi değerin geçersiz olduğunu açıkça belirten bir 400 ile
  karşılıyor.
- **`/sistem/saglik` artık kimlik doğrulaması gerektiriyor:** Bu uç nokta
  (dedektör eşiği/modeli, SQL Server yedek durumu, disk/CPU/RAM gibi teşhis
  bilgileri döndürür) hiçbir `Depends(...)` olmadan tanımlanmıştı — ağdaki
  HERKES giriş yapmadan bu bilgilere erişebiliyordu. Artık diğer teşhis uç
  noktalarıyla (`/sistem/loglar` vb.) tutarlı şekilde en az personel girişi
  gerektiriyor.
- **"Güvenlik uyarıları" artık panelde de görünür, yalnızca log dosyasında
  değil:** `PTS_LICENSE_SECRET`/`PTS_KAMERA_ANAHTARI` ayarlanmamışsa veya
  `PTS_CORS_ORIGINS='*'` ise sistem gayet normal çalışır, hiçbir hata vermez —
  ama gerçek bir güvenlik açığı sessizce açık kalır; bu üç durum önceden
  yalnızca (kimsenin günlük olarak açıp okumadığı) `loglar/pts.log`'a bir kez
  yazılıyordu. `/sistem/saglik` yanıtına eklenen yeni `guvenlik_uyarilari`
  alanı, bu üç durumdan hangisi etkinse Sistem sekmesinde (yalnızca ortam
  değişkenlerini değiştirebilecek tek rol olan **yönetici** için) sarı bir
  uyarı banner'ı olarak gösteriyor.
- **Frontend'e küresel bir hata yakalayıcı eklendi:** Backend'in "sıfır sessiz
  hata" ilkesi (küresel exception handler'lar, geniş try/except + loglama
  kapsamı) frontend'de karşılıksızdı — yakalanmamış bir JS hatası veya
  promise reddi yalnızca tarayıcı geliştirici konsoluna düşüp güvenlik
  masasındaki kullanıcıya HİÇ görünmeden kayboluyordu (kimse devtools'u açık
  tutmaz). Artık `window.onerror` ve `unhandledrejection` dinleyicileri her
  yakalanmamış hatayı en azından bir toast bildirimiyle kullanıcıya
  bildiriyor (art arda patlayan bir döngüde kullanıcıyı boğmamak için 10
  saniyede bir sınırlanarak); kırık bir `<img>`/`<script>` yüklemesi gibi
  gerçek bir JS hatası olmayan "error" olayları bu bildirimi tetiklemiyor.
- **Test kapsamı genişletildi:** Daha önce hiç test edilmeyen `/sistem/yedek`
  (rol bazlı erişim) ve `/sakin/goruntu/{kayit_id}` (bir sitede oturan
  kişinin yalnızca KENDİ kaydının görüntüsünü görebildiğini, başkasının
  kaydına erişmeye çalışırsa 404 aldığını doğrulayan IDOR testleri) uç
  noktalarına, `/olaylar` ve `/alarmlar`'a temel işlevsel testler eklendi;
  yukarıdaki limit/offset/tarih doğrulamaları için de kapsamlı parametrize
  testler eklendi. Yeni `tests/test_guvenlik_denetimi_iyilestirmeleri.py`
  dosyası (fastapi/sqlalchemy gerektirmediği için gerçekten çalıştırılıp
  doğrulandı) frontend'deki iki iyileştirmeyi (küresel hata yakalayıcı,
  güvenlik uyarıları banner'ı) kapsıyor.

**2026-09-20 (devam) — kullanıcının "başka neler geliştirilebilir?" sorusu
üzerine ikinci bir denetim turunda eklenenler:**

- **Lisans süresi dolmadan önce uyarı:** Lisans kontrolü tamamen İKİLİYDİ
  (aktif/pasif) -- bekçi döngüsü (`_kamera_bekcisi`), lisans süresi dolduğu
  ANDA (önceden hiçbir belirti olmadan) TÜM kamera pipeline'larını durdurup
  bariyer/ANPR'ı komple karartıyordu. Sahada bu, müşteriye önceden haber
  verilmeden aniden "sistem çalışmıyor" şikayetine dönüşecek bir senaryoydu.
  `/lisans` yanıtına eklenen `kalan_gun`/`yakinda_doluyor` alanları (bkz.
  `_lisans_kalan_gun_ekle`), bitişe 14 gün veya daha az kaldığında panelin
  üst çubuğundaki lisans göstergesini VE Lisans Yönetimi kartını turuncu bir
  "N gün içinde dolacak" uyarısına çeviriyor -- lisans üretme/doğrulama
  mekanizmasının kendisine hiç dokunulmadı, yalnızca pasif bir görünürlük
  katmanı eklendi.
- **Standart güvenlik yanıt başlıkları:** Her API yanıtına artık
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`,
  `Referrer-Policy: strict-origin-when-cross-origin` ve
  `Strict-Transport-Security` başlıkları ekleniyor (bkz.
  `_guvenlik_basliklarini_ekle`) -- clickjacking ve MIME-sniffing'e karşı ek
  bir savunma katmanı (defense in depth). Kapsamlı bir Content-Security-
  Policy BİLİNÇLİ OLARAK eklenmedi: panelin envanteri (inline script/style
  kullanımı dahil) çıkarılıp test edilmeden eklenen bir CSP, üretimde paneli
  sessizce bozabilir -- bu, ayrı ve daha dikkatli bir çalışma gerektiriyor.
- **"Kim ne yaptı" denetim (audit) izi eksikliği:** Kullanıcı rolü/aktiflik
  değiştirme, parola sıfırlama, kullanıcı silme, kamera silme, lisans
  aktivasyonu ve sistem ayarları değiştirme gibi HASSAS yönetici işlemleri
  önceden `loglar/pts.log`'a hiçbir iz bırakmıyordu -- bir hesabın kim
  tarafından ne zaman silindiği ya da bir güvenlik eşiğinin kim tarafından
  değiştirildiği sorusu tamamen cevapsızdı. Artık bu altı işlemin tümü,
  ilgili kullanıcı adı ve neyin değiştiği (parolanın KENDİSİ hariç) ile
  loglanıyor; gerçek bir değişiklik yoksa (ör. aynı değerlerle boş bir PUT)
  log spam'i olmasın diye hiçbir şey yazılmıyor. **Güncelleme (aynı gün,
  devam) — bkz. aşağıdaki "Denetim Kayıtları" bölümü:** bu artık yalnızca
  log dosyasına yazan bir metin izi değil, kalıcı bir veritabanı tablosuna
  da yazan ve panelde ayrı bir ekrandan görüntülenip filtrelenebilen tam bir
  audit-trail sistemi.
- Yeni `tests/test_lisans_suresi_uyarisi.py` dosyası (gerçekten çalıştırılıp
  doğrulandı) frontend'deki lisans uyarısı görselleştirmesini kapsıyor;
  `tests/test_api.py`'ye (yalnızca `py_compile` ile doğrulandı) yukarıdaki
  backend değişikliklerinin tümü için testler eklendi.

**Bilinçli olarak ERTELENEN/atlanan bulgular (gerekçesiyle):** Toplu kişi
içe aktarmadaki (`/kisiler/toplu-import`) her kişi için ayrı bir geçmiş-
kayıt-bağlama sorgusu çalıştıran N+1 deseni tespit edildi ama düzeltilmedi
-- pratikte çoğu yeni kişi için eşleşen geçmiş kayıt olmadığından sorgular
genelde ucuzdur, ve bu delikçe hassas yetkilendirme mantığını (`_plaka_
yetki_kontrol`) toplu bir sorguya dönüştürmek, kazanılacak performanstan
daha yüksek bir ince-hata riski taşır. SQLite kurulumlarında (SQL Server
Agent bakım planı olmayan, genelde daha küçük/deneme kurulumları) periyodik
otomatik yedekleme yok, yalnızca manuel `/sistem/yedek` indirmesi var --
SQL Server kurulumlarında zaten Agent bakım planı + gecikme izleme (yukarı
bakınız, "SQL Server Yedeği İzleme") olduğu için bu yalnızca küçük/opsiyonel
bir iyileştirme olarak not edildi.

## Denetim Kayıtları (Audit Trail) (2026-09-20)

Kullanıcının isteği üzerine, yukarıdaki "kim ne yaptı" logunun metin-dosyası
sınırlaması giderildi: artık kalıcı bir `denetim_kayitlari` veritabanı tablosu
(`models.DenetimKaydi`) VE panelde ayrı bir **"Denetim Kayıtları"** sekmesi
(yalnızca yönetici, Sistem sekmesinin yanında yeni bir nav/kenar çubuğu
girişi) var.

- **Kapsanan işlemler** (tek çağrı noktası: `main.py::_denetim_kaydet`, hem
  log dosyasına HEM veritabanına yazar): kullanıcı oluşturma/güncelleme/
  silme (rol değişikliği, aktif/pasif yapma, parola sıfırlama dahil -- parola
  METNİ asla kaydedilmez), kamera silme, lisans aktivasyonu, sistem ayarları
  değiştirme. Gerçek bir değişiklik yoksa (ör. aynı değerlerle boş bir PUT)
  hiçbir kayıt oluşturulmaz.
- **Panel ekranı:** kullanıcı adına (kısmi eşleşme), eyleme (açılır menüden
  seçilir, sunucudaki GERÇEK eylem türlerinden otomatik doldurulur -- ileride
  yeni bir `_denetim_kaydet` çağrı noktası eklenirse filtre listesi elle
  güncellenmesi gerekmeden otomatik güncel kalır) ve tarih aralığına göre
  filtrelenebilir.
- **Dayanıklılık:** denetim kaydının veritabanına YAZILAMAMASI (ör. o an
  veritabanı kilitliyse) asıl işlemi (kullanıcı silme, kamera silme vb.)
  ASLA engellemez/geri almaz -- ayrı bir try/except'e sarılı, ikincil bir
  gözlemlenebilirlik özelliğidir.
- **Güvenlik:** `GET /denetim-kayitlari` ve `/denetim-kayitlari/eylem-listesi`
  yalnızca **yönetici** rolüne açık -- `/sistem/loglar`'ın aksine (genel arıza
  teşhis logu, operatöre de açık), bu bilgi özellikle hesap yönetimiyle
  ilgili hassas ayrıntılar (kimin parolası sıfırlandı, kim hangi role
  yükseltildi) taşıdığı için operatöre bile kapalı tutuldu.
- Bu, LOG DOSYASININ YERİNE geçmiyor -- iki bağımsız kayıt yeri bilinçli
  olarak korundu (biri bozulursa/silinirse diğeri hâlâ durur).
- Yeni `tests/test_denetim_kayitlari_frontend.py` dosyası (gerçekten
  çalıştırılıp doğrulandı) panel ekranını kapsıyor; `tests/test_api.py`'ye
  (yalnızca `py_compile` ile doğrulandı) uç nokta RBAC'ı, filtreleme ve her
  bir çağrı noktasının gerçekten bir denetim kaydı bıraktığını doğrulayan
  testler eklendi.

## "Daha Profesyonel Neler Yapabilirsin?" Denetimi (2026-09-20)

Kullanıcının bu doğrudan sorusu üzerine yapılan ek bir tur:

- **API dokümantasyonu (Swagger UI/ReDoc) artık varsayılan olarak kapalı:**
  FastAPI'nin otomatik oluşturduğu `/docs`, `/redoc` ve `/openapi.json`
  hiçbir kimlik doğrulaması gerektirmeden VARSAYILAN OLARAK açıktı -- tek
  başına bir veri sızıntısı değil ama ağa erişimi olan HERKESE (giriş
  yapmadan) TÜM API uç noktalarının, alan adlarının ve şemalarının tam bir
  haritasını sunuyordu. Ticari/özel bir ürün için gereksiz bir saldırı yüzeyi
  genişletmesiydi. Artık projedeki diğer "varsayılan güvenli, isteyen açar"
  desenleriyle tutarlı: yalnızca `PTS_API_DOKUMANTASYONU_AC=1` ile (geliştirme/
  hata ayıklama amaçlı) açıkça istenirse devreye giriyor.
- **Sürüm numarası tekrarı düzeltildi:** `/sistem/saglik`'in `surum` alanı,
  `app = FastAPI(..., version="2.0")`'daki AYNI değerin bağımsız, elle
  senkronize edilmesi gereken bir kopyasıydı (bu depoda tekrar tekrar
  görülen "aynı gerçeğin birden fazla kopyası" hata sınıfı) -- artık tek
  kaynak `app.version`.
- **Yeni `.env.example` dosyası:** uygulamanın okuduğu TÜM `PTS_*` ortam
  değişkenleri (güvenlik, veritabanı, ANPR/kamera, dosya yolları,
  geliştirme) önceden yalnızca README'ye dağılmış onlarca ayrı yorum/bölüm
  olarak vardı -- artık tek, güncel bir referans dosyasında toplu. `.gitignore`
  de gerçek bir `.env` dosyasının (sırlar içerebileceği için) yanlışlıkla
  commit edilmesine karşı güncellendi (`.env.example` istisna).
- `tests/test_api.py`'ye (yalnızca `py_compile` ile doğrulandı) API
  dokümantasyonunun varsayılan olarak kapalı olduğunu ve sürüm alanının
  `app.version` ile aynı kaynaktan geldiğini doğrulayan testler eklendi.

## PDF Dışa Aktarma Çökme Düzeltmesi ve Saat Aralığı Filtresi (2026-09-21)

Kullanıcının ekran görüntüsüyle bildirdiği "geçerli bir istekte bile
`/disa-aktar/pdf/kayitlar` genel 'Sunucuda beklenmeyen bir hata oluştu'
500'üne düşüyor" sorununun kök nedeni ve aynı oturumdaki bir takip talebi:

- **KÖK NEDEN (PDF çökmesi):** reportlab'ın `Paragraph` flowable'ı,
  kendisine verilen metni düz metin olarak DEĞİL, sınırlı bir HTML/XML
  biçimlendirme dili olarak ayrıştırıyor. Kişi adı/soyadı, site adı,
  daire/departman, erişim noktası adı ve araç tipi (personel için
  `daire_departman`'dan gelir) gibi yönetici panelinden serbest metin
  olarak girilen alanlardan biri, kapatılmamış bir biçimlendirme
  etiketiyle (örn. `<b>metin`) karışabilecek bir değer içerdiğinde, PDF
  üretimi yakalanmamış bir `ValueError` ile çöküyordu -- istek kendisi
  tamamen geçerli olsa bile. Düzeltme: `backend/pdf_export.py`'de yeni bir
  `_pdf_metin()` yardımcı fonksiyonu, `Paragraph`'a giden HER hücre
  metnini standart XML kaçış kurallarıyla (`&`/`<`/`>`) kaçışlıyor --
  kullanıcı verisi artık ASLA bir biçimlendirme komutu olarak
  yorumlanamıyor.
- **İkinci savunma katmanı:** Türkçe karakter desteği için özel
  DejaVu Sans fontlarını kaydeden `_turkce_fontlari_kaydet()` önceden
  hiçbir try/except ile korunmuyordu -- `backend/fonts/*.ttf` dosyaları
  eksik/bozuk kopyalanırsa (Türkçe karakterlerle HİÇ ilgisi olmayan) HER
  PDF dışa aktarma isteği aynı şekilde çökerdi. Artık font dosyaları
  okunamazsa reportlab'ın gömülü Helvetica fontuna düşülüyor (durum
  loglanıyor, Türkçe karakterler o durumda hatalı görünebilir ama rapor
  en azından ÜRETİLİYOR).
- **Yeni özellik (aynı oturumdaki takip talebi): kayıt filtrelemede saat
  aralığı.** Kayıtlar sekmesindeki "Başlangıç/Bitiş Tarihi" filtreleri
  yalnızca GÜN bazında çalışıyordu -- belirli bir gün içinde yalnızca
  belirli saatler arasındaki geçişleri görmek mümkün değildi. Her iki
  filtrenin yanına opsiyonel bir saat seçici (`<input type="time">`)
  eklendi; saat boş bırakılırsa eski davranış (o günün tamamı) aynen
  korunuyor. Backend tarafında `_bitis_tarih_filtresi_sinirini_hesapla()`
  paylaşılan yardımcı fonksiyonu, `bitis` değerinin ham metninde `T`
  ayırıcısı olup olmadığına bakarak (salt tarih mi, tarih+saat mi) doğru
  üst sınırı hesaplıyor -- bu mantık `/kayitlar`, `/kayitlar/sayfa-bilgisi`
  ve dışa aktarma raporlarının "Bu raporda X - Y tarihleri arasında..."
  açıklama metniyle PAYLAŞILIYOR, aksi halde rapor metni ile gerçek sorgu
  sonucu birbirinden sessizce sapabilirdi.
- Testler: `tests/test_pdf_export.py`'ye (gerçekten çalıştırılabilir --
  reportlab/Pillow dışında bağımlılığı yok) hem markup-benzeri metinle
  çökmediğini hem kaçışlamanın metni gizlemediğini hem de font
  bulunamama durumunda Helvetica'ya düştüğünü doğrulayan testler
  eklendi. `tests/test_api.py`'ye (yalnızca `py_compile` ile doğrulandı)
  saat aralığı filtresinin doğru çalıştığını ve saat verilmeden eski
  davranışın (günün tamamı) korunduğunu doğrulayan testler eklendi.

### Devamı: gerçek üretim verisiyle (2408 kayıt) İKİ FARKLI çökme daha bulundu (2026-09-21, aynı gün)

Kullanıcı yukarıdaki düzeltmeyi uyguladıktan SONRA bile hem PDF HEM Excel
dışa aktarmanın (ekran kaydıyla) hâlâ çöktüğünü bildirdi. Gerçek üretim
verisiyle (kaçışlama düzeltmesinin kapsamadığı) tamamen BAĞIMSIZ iki kök
neden daha bulundu:

- **Excel çökmesi -- `IllegalCharacterError`:** OOXML (.xlsx) biçimi, XML
  1.0 spesifikasyonu gereği belirli KONTROL KARAKTERLERİNİ (NUL, backspace
  vb. -- sekme/satır sonu HARİÇ) hücre metninde HİÇ barındıramaz.
  `not_metni` (serbest metin not alanı) gibi bir alana kopyala/yapıştır ya
  da bozuk bir kaynaktan böyle bir karakter karışırsa, `wb.save()`
  sırasında yakalanmamış bir `IllegalCharacterError` fırlatılıyordu. Bu,
  yukarıdaki PDF kaçışlama düzeltmesinin KAPSAMADIĞI, Excel'e ÖZGÜ ayrı bir
  hataydı (reportlab bu karakterlere PDF tarafında farklı davranıyor, bkz.
  aşağıdaki madde). Düzeltme: `backend/excel_export.py::_guvenli_hucre`,
  openpyxl'in kendi `ILLEGAL_CHARACTERS_RE` deseniyle bu karakterleri
  hücreye yazmadan önce temizliyor.
- **PDF çökmesi (ikinci, FARKLI kök neden) -- `LayoutError`:** kaçışlama
  düzeltmesi biçimlendirme-etiketi sorununu kapatmıştı, ama reportlab'ın
  `Table`'ı AYRI bir durumda da çöküyordu: bir hücrenin sarılmış metni TEK
  SAYFAYA sığmayacak kadar uzun/boşluksuz olursa yakalanmamış bir
  `LayoutError` fırlatıyordu. Gerçek dünyada bu, programatik olarak
  birleştirilmiş "Vardiya" alanının (bkz. `_vardiya_etiketleri_haritasi`)
  unutulmuş/kapanmamış çok sayıda eski oturum birikince anormal
  uzamasıyla tetiklenebilir. Düzeltme: `_pdf_metin()` artık her hücre
  metnini (kaçışlamadan ÖNCE) sabit bir `_PDF_HUCRE_MAKS_UZUNLUK` (200
  karakter) sınırına kırpıyor -- yerel olarak ikili aramayla, en dar
  sütunun (1.1cm) bu sınırın ÜZERİNDE (~220 karakterden sonra) çökmeye
  başladığı doğrulandıktan sonra seçilen, güvenli paylı bir değer. Normal
  hiçbir isim/site/departman/nokta adı bu uzunluğa asla yaklaşmaz -- bu
  yalnızca anormal/runaway veriye karşı bir güvenlik ağı.
- Testler: her iki modülün kendi test dosyasına (`test_excel_export.py`,
  `test_pdf_export.py` -- ikisi de gerçekten çalıştırılabilir) doğrudan
  bu iki senaryoyu yeniden üreten regresyon testleri eklendi.

### Devamı: ASIL kök neden bulundu -- `offset` parametresi Query nesnesi olarak sızıyordu (2026-09-21, aynı gün, kullanıcının paylaştığı GERÇEK hata iziyle)

Yukarıdaki iki tur (kaçışlama + kontrol karakteri/uzunluk kırpma) GERÇEK ve
bağımsız hatalardı, ama kullanıcı düzeltmelerden SONRA bile AYNI 500'ün
devam ettiğini bildirince, panelin "Sistem" sekmesinden tam hata izini
istedik. İz, her ikisinden de TAMAMEN FARKLI, çok daha temel bir sorunu
ortaya çıkardı:

```
File "backend\main.py", line 2811, in kayitlari_listele
    kayitlar = sorgu.order_by(...).offset(offset).limit(limit).all()
...
TypeError: int() argument must be a string, a bytes-like object or a real number, not 'Query'
```

**Kök neden:** `kayitlari_excel_indir` ve `kayitlari_pdf_indir`,
`kayitlari_listele()`'yi FastAPI'nin DI (bağımlılık enjeksiyonu)
mekanizması ÜZERİNDEN DEĞİL, doğrudan bir Python fonksiyonu olarak
çağırıyor -- bu, `kullanici` parametresi için zaten bilinen ve
belgelenmiş bir kısıtlamaydı ("kullanici AÇIKÇA geçirilmezse Depends()
varsayılanı hiç ÇÖZÜLMEZ" notu, bkz. yukarıdaki "Güvenlik Personeli
Vardiya Filtresi" bölümü). Ama AYNI kısıtlama `offset` parametresi için
de geçerliydi ve fark edilmemişti: `kayitlari_listele`'nin imzasındaki
`offset: int = Query(0, ge=0)`, yalnızca FastAPI'nin kendi routing
katmanından çağrıldığında gerçek bir tam sayıya çözülür. Fonksiyon
buradaki gibi düz bir Python çağrısıyla (limit AÇIKÇA veriliyordu ama
offset VERİLMİYORDU) çağrılırsa, Python `offset` için doğrudan FastAPI'nin
`Query(...)` çağrısının DÖNDÜRDÜĞÜ NESNEYİ kullanır -- yani `offset`
isim olarak var ama değeri bir tam sayı DEĞİL, `fastapi.params.Query`
sınıfının bir örneğiydi. Bu, `.offset(offset)` satırına kadar sessizce
ilerleyip SQLAlchemy içinde yakalanmamış bir `TypeError` fırlatıyordu --
istek kendisi (kimlik doğrulaması, tarih filtresi, veri, hepsi) tamamen
geçerli olsa bile HER TEK Excel/PDF dışa aktarma isteği bu yüzden
çöküyordu (kayıt sayısından ya da içeriğinden TAMAMEN BAĞIMSIZ -- yukarıdaki
iki "düzeltme" turu gerçek hatalardı ama HİÇBİRİ bu asıl engelleyici
sorunu çözmüyordu).

**Düzeltme:** her iki çağrı sitesine de `offset=0` AÇIKÇA eklendi.

**Neden test paketi bunu yakalamadı:** `tests/test_api.py`'deki
`test_disa_aktar_uc_noktalari_authorization_basligiyla_calisir` testi bu
iki uç noktayı zaten çağırıp 200 bekliyordu -- bu depo bu testi gerçekten
ÇALIŞTIRABİLECEK bir ortamda (fastapi/sqlalchemy kurulu) çalıştırılsaydı bu
regresyon HEMEN yakalanırdı. Bu oturumun kendi kum havuzunda bu paket kurulu
olmadığından (bkz. "Kalıcı Test Altyapısı" bölümü) bu dosya yalnızca
`py_compile` ile doğrulanabildi -- **kullanıcının kendi ortamında (ya da
CI'da) `pytest tests/` çalıştırması, tam olarak bu sınıftaki hataları erken
yakalamanın yoludur.** Kök nedeni netleştiren, mekanizmayı açıkça anlatan
yeni bir regresyon testi (`test_disa_aktar_kayitlar_offset_query_nesnesi_olarak_sizmaz`)
`tests/test_api.py`'ye eklendi.

## Toplu Doğruluk Testi (Canlı Sisteme Dokunmadan Eşik/Model Karşılaştırma)

Farklı `PTS_ANPR_DETECTOR_ESIGI` / `PTS_ANPR_DETECTOR_MODEL` / kontrast
ayarlarının GERÇEK doğruluk üzerindeki etkisini, canlı sisteme hiçbir kayıt
atmadan, sayısal olarak ölçmek için `POST /sistem/dogruluk-testi` uç noktası
eklendi (yönetici/operatör; panelde Sistem sekmesinde "Toplu Doğruluk Testi"
kartı olarak da mevcuttur).

Kullanım: Dahua NVR'ın ANPR olay listesinden (Aramak/ANPR ekranı) geçmiş
geçişleri "ONEK_PLAKA.jpg" adlandırmasıyla dışa aktarıp bir klasöre koyun
(örn. `C:\pts-test-fotograflari\20260917130536_34MRU796.jpg`) — bu, kaçırılan
geçişleri Dahua'nın kendi ANPR'ı zaten doğru okuduğu için mükemmel bir
"etiketli test seti" oluşturur. Klasördeki `..._plate.jpg` (kırpılmış plaka)
görselleri otomatik atlanır (dedektörün asıl işini test etmezler); dosya
adından geçerli bir Türk plaka formatı çıkarılamayan dosyalar (`Unlicensed`
gibi) "etiketlenemedi" sayılır ve doğruluk oranına katılmaz.

```
POST /sistem/dogruluk-testi
{"klasor": "C:\\pts-test-fotograflari", "min_guven_skoru": 0.25, "kontrast_iyilestir": false}
```

Yanıt: `toplam, dogru, yanlis, esik_altinda, tespit_edilemedi, gorsel_okunamadi,
hata, etiketlenemedi, dogruluk_orani, detaylar` (her dosya için gerçek/okunan
plaka, güven skoru, dedektöre giden karenin piksel boyutu ve sonuç
kategorisi). `min_guven_skoru` verilmezse panelin mevcut "Min. plaka tanıma
güveni" ayarı kullanılır. Bu araç `motor.tahmin_et()`'i DOĞRUDAN çağırır
(`_kareyi_isle`'nin API POST/oturum mantığını hiç çalıştırmaz) — yani
`PTS_ANPR_DETECTOR_ESIGI`/`PTS_ANPR_DETECTOR_MODEL` ortam değişkenlerini her
denemede değiştirip uygulamayı yeniden başlatarak, AYNI fotoğraf klasörü
üzerinde doğruluk oranının nasıl değiştiğini karşılaştırabilirsiniz.

**2026-09-17 (devam) — "tespit_edilemedi" ile "görsel hiç okunamadı" ayrımı:**
İlk sürümde, bir dosyanın hiç açılamaması (bozuk/desteklenmeyen format) ile
dedektörün GERÇEKTEN hiçbir aday bulamaması AYNI "tespit_edilemedi"
kategorisinde toplanıyordu. Sahada 7 gerçek fotoğrafla yapılan bir testte
HEM 384 HEM 608 modelde, HEM 0.4 HEM 0.25 eşikte TÜM dosyalar "tespit_edilemedi"
çıktı — modele/eşiğe göre hiç değişmeyen bu %0 sonucu, gerçek bir dedektör
kaçırma sorunundan çok "dosyalar hiç işlenemiyor" ihtimaline işaret ediyordu,
ama eski kategorileme bu ikisini ayırt edemiyordu. Artık üç ayrı kategori var:

- **`tespit_edilemedi`**: dosya başarıyla okundu, dedektöre verildi, dedektör
  gerçekten hiçbir aday üretmedi.
- **`gorsel_okunamadi`**: `cv2.imread()` dosyayı hiç açamadı (`None` döndü) —
  dedektöre hiç ulaşılmadı. Bunu görüyorsanız sorun model/eşik değil, dosyanın
  kendisi (bozuk kopya, desteklenmeyen format, yol/izin sorunu).
- **`hata`**: motor çağrısı sırasında beklenmeyen bir istisna oluştu (ör. bir
  ONNX çalışma zamanı hatası) — `detaylar` içindeki `hata_mesaji` alanında
  ayrıntı bulunur; bu dosya atlanır, kalan dosyaların işlenmesi durmaz.

Her dosyanın sonucu ve (varsa) dedektöre giden karenin piksel boyutu artık
uygulama loguna da (`Sistem/Log` ekranı) INFO seviyesinde yazılır — panelde
görülen özet sayılarla log'daki ayrıntıyı karşılaştırarak sorunu tam olarak
nerede olduğunu (dosya mı, model mi, gerçekten trafiksiz an mı) teşhis
edebilirsiniz.

**2026-09-17 (devam) — KÖK NEDEN BULUNDU: sonuç ayrıştırma hatası, dedektör
sorunu DEĞİL.** Yukarıdaki `tespit_edilemedi`/`gorsel_okunamadi`/`hata` ayrımı
bile bir süre gerçek nedeni açığa çıkaramadı, çünkü sorun hiçbirinde değildi:
sahada HER model (384/608), HER eşik (0.4/0.25/0.2), CLAHE açık/kapalı, HEM tam
sahne HEM plakayı neredeyse tamamen dolduran kırpılmış bir görsel, HEM
DirectML HEM tamamen CPU'ya zorlanmış çalıştırma (`PTS_ANPR_PROVIDERS=cpu`) ile
test edildi — hepsinde sonuç birebir aynıydı: sıfır tespit. Bu kadar tutarlı
bir "her koşulda tam sıfır" sonucu, ayar/eşik/model seçimi değil, motorun
KENDİSİNİN hiç çalışmadığına işaret ediyordu. Kullanıcının `fast_alpr.ALPR`'ı
`anpr_engine.py`'yi hiç kullanmadan DOĞRUDAN çağırdığı bir teşhis testinde
plaka ("34MRU796") %84.7 dedektör güveniyle, karakterlerin tamamı ~%99.9 OCR
güveniyle DOĞRU bulundu — üstelik bu, PTS'nin panelinde "tespit_edilemedi"
dediği AYNI dosyaydı.

Neden: kurulu `fast_alpr` sürümü, her aday için İÇ İÇE bir sonuç nesnesi
döndürüyor — `ALPRResult(detection=DetectionResult(confidence=.., bounding_box=
BoundingBox(x1=.., y1=.., x2=.., y2=..)), ocr=OcrResult(text=.., confidence=
[karakter başına güvenlerin LİSTESİ]))` — yani plaka metni `sonuc.text`'te
DEĞİL `sonuc.ocr.text`'te. `anpr_engine.py::ANPREngine.tahmin_et()` ise DÜZ
(nested olmayan) `sonuc.plate`/`sonuc.text` ve `sonuc.score`/`sonuc.confidence`
alanları bekliyordu; bunlar gerçek nesnede hiç var olmadığından her aday
sessizce atılıyordu (`if not plaka: continue`). Yani dedektör ve OCR arka
planda plakayı HER ZAMAN doğru buluyordu — PTS bunu asla raporlamıyordu. Bu,
bu depodaki `anpr_engine.py` için o zamana kadarki TEK test dosyasının
(`tests/test_anpr_engine.py`) `predict()`'i her zaman `[]` döndüren bir sahte
sınıf kullanması ve bu ayrıştırma mantığını hiç çalıştırmamasıyla da
örtüşüyor — hata aylarca hiçbir testte yakalanamamıştı.

Düzeltme: `tahmin_et()` artık önce İÇ İÇE (kurulu sürümün gerçek) yapıyı
dener, bulamazsa DÜZ yapıya düşer (olası eski/farklı bir sürüm kırılmasın
diye); OCR güveni tek bir sayı ya da karakter başına güvenlerin listesi
olarak gelebildiği için yeni bir `_ocr_guveni_hesapla()` yardımcı fonksiyonu
(liste ise ortalamasını alır) eklendi; kutu koordinatları hem
`xmin/ymin/xmax/ymax` hem `x1/y1/x2/y2` adlandırmasını destekler hale
getirildi. `tests/test_anpr_engine.py`'ye, kullanıcının gerçek teşhis
çıktısının YAPISINI birebir taklit eden yeni sahte sınıflarla regresyon
testleri eklendi (bu testler DÜZELTME ÖNCESİ kodda başarısız olurdu).

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
  olarak yedekleyin -- **2026-09-23'ten itibaren** (bkz. aşağıdaki "SQLite WAL Modu"
  bölümü) bu klasörde `pts.db` ile birlikte `pts.db-wal` ve `pts.db-shm` dosyaları da
  oluşur; yedekleme betiğiniz YALNIZCA `pts.db`yi kopyalarsa, henüz ana dosyaya
  yazılmamış (`pts.db-wal`de bekleyen) en son işlemleri SESSİZCE KAÇIRABİLİR. Ya PTS
  kapalıyken/duraklatılmışken (ya da `sqlite3 veritabani/pts.db "PRAGMA
  wal_checkpoint(TRUNCATE);"` çalıştırıp hemen ardından) klasördeki ÜÇ dosyayı BİRLİKTE
  kopyalayın, ya da SQLite'ın kendi `.backup` komutunu/API'sini kullanan bir betik
  tercih edin.
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

## Nizamiye Bazlı Kamera Erişimi (2026-09-21)

Kullanıcı talebi: aynı ağdaki farklı fiziksel noktalardan (ör. "Ana Nizamiye" ve
"Lojman Nizamiye") çalışan güvenlik personelinin, panelde YALNIZCA kendi
noktasının kameralarını görebilmesi gerekiyordu — örneğin Ana Nizamiye'de 4
kamera izlenirken, Lojman Nizamiye'de çalışan bir personelin (örnekte "Bülent")
yalnızca 2 kamerayı görmesi, diğer 4 kameraya hiç erişememesi isteniyordu.
Önceden panelde HERHANGİ bir personel hesabı (izleyici dahil) TÜM kameraları
sınırsız görebiliyordu — hesap bazlı bir kamera kısıtlama mekanizması yoktu.

**Ne eklendi:**

- `Kullanıcılar` sekmesinde (hem "Yeni Kullanıcı" formunda hem de artık eklenen
  "Düzenle" modalında) bir kamera erişim kısıtlaması ayarlanabilir: "Tüm
  Kameralar" kutusu işaretliyken hesap eskisi gibi TÜM kameraları görür
  (varsayılan, geriye dönük uyumlu); işaret kaldırılıp belirli kameralar
  seçilirse hesap YALNIZCA o kameraları canlı izleyebilir VE genel "Kayıtlar"
  akışında yalnızca o kameralardan gelen geçişleri görür.
- Bu kısıtlama şu uç noktalarda uygulanır: `GET /kameralar` (liste), `GET
  /kameralar/{id}/goruntu` (anlık kare), `GET /kameralar/{id}/akis` (canlı MJPEG
  akışı), `GET /kameralar/{id}/son-plaka`, `GET /kameralar/{id}/saglik` ve `GET
  /kameralar/saglik/tumu` (izinsiz bir kameraya erişim 403 ile reddedilir/listeden
  çıkarılır); ayrıca CANLI SSE bildirimlerinde de (`/olaylar/sse`, "Son Geçişler"
  paneli) izinsiz bir kameradan gelen geçiş artık gösterilmez. Genel "Kayıtlar"
  listesi/raporları/istatistikleri de (`_guvenlik_kayit_filtresi_uygula` — daha
  önce yalnızca güvenlik personelinin vardiya penceresini uyguluyordu, artık
  HERHANGİ bir rol için kamera kısıtlamasını da AYNI ANDA uyguluyor) bu
  kısıtlamaya tabidir.
- Panelde artık bir kullanıcının rolünü/kamera erişimini/parolasını
  OLUŞTURULDUKTAN SONRA değiştirebileceğiniz bir "Düzenle" (kalem ikonu) düğmesi
  var — önceden yalnızca aktif/pasif yapma ve silme mümkündü, rol değiştirmenin
  panelden hiçbir yolu yoktu.

**Bilinçli istisna — "Plaka Analizi" (`GET /kayitlar/analiz/{plaka}`):** takip
sırasında ortaya çıkan gerçek ihtiyaç şuydu: "A Vardiyasının nöbet saatinde
giriş yapan bir aracı, B vardiyası geldiğinde tespit edebilmesi gerekiyor" —
yani farklı bir vardiyada/noktada çalışan personelin, belirli bir aracı
ararken diğer vardiyanın/noktanın kayıtlarına erişebilmesi gereken meşru bir
ihtiyaç var. Bu yüzden "Plaka Analizi" ekranı (belirli TEK bir plakayı
hedefleyen, kasıtlı bir arama) hem vardiya penceresi filtresinden HEM DE
kamera erişim kısıtlamasından MUAF tutuldu — güvenlik personeli genel kayıt
akışını (diğer vardiyaların/noktaların TÜM trafiğini) gezinemez ama belirli
bir aracı sorguladığında tam geçmişini görebilir. Genel "Kayıtlar" listesi bu
istisnanın DIŞINDA kalmaya devam ediyor (orada hem vardiya hem kamera filtresi
hâlâ tam olarak uygulanıyor).

**Kurulum örneği (kullanıcının senaryosu):** Ana Nizamiye'de 4, Lojman
Nizamiye'de 2 kamera olan bir kurulumda, Lojman'da çalışacak "Bülent" isimli
güvenlik hesabı oluşturulurken (veya sonradan "Düzenle" ile) "Tüm Kameralar"
kutusunun işareti kaldırılıp yalnızca Lojman'ın 2 kamerası seçilir — Bülent artık
Ana Nizamiye'nin 4 kamerasını ne canlı izleyebilir ne de genel Kayıtlar
listesinde görebilir, ama bir aracı ararken (Plaka Analizi) tüm noktaların
geçmişine erişebilir.

## Vardiya Grupları ve Otomatik Kapanma (2026-09-21)

Kullanıcı talebi: "kayıtlar ekranına yeni bir sütun ekleyebilir miyiz. A B C D
Vardiyaları olacak şekilde. bir de LOJMAN A Vardiyası Bülent ile aynı zaman
aralığında çalışacağı için Bülent vardiyası ve A vardiyası giriş yaptığı zaman
aynı raporlamayı yapabiliyor olması gerekiyor. Ana nizamiyeden bülent kontrol
ettiğinde Lojman A geçişlerini de görebilecek. Tüm Güvenlik Personeli kayıtlar
ekranından A B C D Vardiyalarında geçen araçları filtreleyip plaka arayınca
karşısına kimin vardiyasında girip çıktığı gözükebilsin. Bir de şunu istiyorum.
A B C D vardiyaları 8 saat bazlı çalışmakta yani vardiya amiri çıkış yapmayı
unutsa bile giriş saatinden 8 saat sonra otomatik çıkış yapılsın."

Bu talep, yukarıdaki "Nizamiye Bazlı Kamera Erişimi" özelliğiyle BİRLİKTE
düşünüldü: aynı PTS kurulumunu farklı fiziksel noktalardan (ör. Ana Nizamiye +
Lojman Nizamiye) çalıştıran iki ayrı bilgisayar senaryosunda, her nokta kendi
kameralarına kısıtlı kalırken (kamera erişimi), VARDİYA bazlı kayıt
görünürlüğünün noktalar ARASI paylaşılabilmesi gerekiyordu.

**Ne eklendi:**

- `Kullanici.vardiya_adi` (bkz. `models.py`): bir hesaba atanabilen,
  serbest metin ama arayüzde A/B/C/D önerilen bir "vardiya grubu adı".
  Baş/son boşluk temizlenir, büyük harfe çevrilir (`_vardiya_adi_normalize`).
  NULL/boş = hesap bağımsız kalır (eski/varsayılan davranış: yalnızca KENDİ
  vardiya oturumlarını görür).
- **Paylaşımlı görünürlük:** AYNI `vardiya_adi`'na sahip TÜM hesapların vardiya
  oturumları (giriş/çıkış), kayıt görünürlüğü açısından BİRLEŞİK sayılır (bkz.
  `_kullanicinin_vardiya_pencereleri`). Örnek: Lojman Nizamiye'deki "Bülent"
  hesabı "A" vardiyasına, Ana Nizamiye'deki başka bir hesap da "A" vardiyasına
  atanırsa, ikisi de birbirinin vardiya penceresinde geçen kayıtları (iki nokta
  BİRLİKTE) görebilir — fiziksel nokta/kamera farklı olsa bile.
- **Kayıtlar ekranında "Vardiya" sütunu ve filtresi:** her kayıt, o an AÇIK olan
  adlandırılmış vardiya oturumlarının adıyla (ör. "A", aynı anda birden fazla
  farklı vardiya açıksa "A/B") etiketlenir (bkz. `_kayitlarin_vardiya_adlarini_
  ekle`) — bu, rapor (Excel/PDF) dışa aktarımındaki AD+SAAT etiketinden
  (`_vardiya_etiketleri_haritasi`, adlandırılmamış hesaplar için de dolan, ayrı
  bir özellik) BİLİNÇLİ olarak farklıdır. Ayrıca rol ne olursa olsun (yalnızca
  güvenlik personeli değil, TÜM personel) kullanılabilen bir "Vardiya" filtresi
  eklendi (`_vardiya_adi_filtresi_uygula`) — Excel/PDF dışa aktarma da bu
  filtreyi kullanır.
- **Plaka Analizi:** "son_kayitlar" listesindeki her kayda da aynı `vardiya_adi`
  etiketi eklendi — "plaka arayınca karşısına kimin vardiyasında girip çıktığı
  gözükebilsin" talebini karşılar. Bu ekran zaten (bkz. yukarıdaki kamera
  erişimi bölümü) vardiya/kamera görünürlük FİLTRESİNDEN muaftı; bu etiketleme
  o muafiyetten bağımsız, yalnızca bilgilendirme amaçlıdır.
- **8 saatlik otomatik kapanma:** "A B C D vardiyaları 8 saat bazlı çalışmakta"
  — arka planda her 5 dakikada bir çalışan bir görev (`_vardiya_otomatik_
  kapama_dongu` / tek seferlik çalıştırması: `_vardiya_otomatik_kapama_
  calistir`), giriş saatinden 8 saati aşmış hâlâ AÇIK (`cikis_zamani IS NULL`)
  vardiya oturumlarını, `giris_zamani + 8 saat` çıkış zamanıyla otomatik olarak
  kapatır. Bu, mevcut "bir SONRAKİ girişte öz-düzeltme" mekanizmasını (bkz.
  `_guvenlik_oturum_baslat`) TAMAMLAR — artık hesap hiç tekrar giriş yapmasa
  bile oturum sonsuza kadar açık kalmaz. Vardiya grupları özelliğiyle birlikte
  bu ayrıca bir DOĞRULUK düzeltmesi de oldu: unutulmuş, süresiz açık bir oturum
  artık yalnızca o hesabın değil, AYNI vardiya adını paylaşan TÜM hesapların
  görünürlüğünü genişletiyordu.
- Kullanıcı Yönetimi sekmesinde (Yeni Kullanıcı formu VE Düzenle modalı) bir
  "Vardiya Grubu" seçici (Yok/A/B/C/D) ve kullanıcı tablosunda bir "Vardiya"
  rozeti sütunu eklendi; "Vardiya Oturumları" tablosuna da hangi oturumun hangi
  gruba ait olduğunu gösteren bir sütun eklendi.

**Bilinçli tasarım kararları:**

- Bu, `_kayitlari_rapor_satirlari`/`_vardiya_etiketleri_haritasi`'ndeki mevcut
  rapor-metni özelliğinin (ad+saat, ör. "Eser Akar (15:00-23:10)") YERİNE
  GEÇMEZ — o, adlandırılmamış hesaplar için de çalışan, farklı bir ihtiyaca
  (rapor okunabilirliği) hizmet eden ayrı bir mekanizma olarak KORUNDU. Excel/
  PDF sütun yapısı bu değişiklikte BİLİNÇLİ olarak değiştirilmedi (önceki PDF
  düzen hatalarından kaynaklanan risk nedeniyle) — yeni "Vardiya" sütunu/filtre
  yalnızca ekrandaki Kayıtlar tablosu ve JSON API'sine kapsam olarak eklendi.
- `vardiya_adi` serbest metindir, DB seviyesinde bir kısıtlama YOKTUR (arayüz
  yalnızca A/B/C/D önerir) — gelecekte 4'ten fazla vardiya/nokta gerekirse
  kod değişikliği gerekmez.

## Kamera Kısıtlaması "id" / "ad" Karışıklığı Düzeltmesi (2026-09-21)

**GERÇEK ÜRETİM VERİSİYLE BULUNAN KRİTİK HATA:** kullanıcı, "Lojman A
Vardiyası" isimli, yalnızca Lojman kameralarına kısıtlanmış bir güvenlik
hesabıyla giriş yaptığında panelinde/Kayıtlar ekranında HİÇBİR geçiş kaydı
görünmediğini bildirdi — hatta giriş yaptıktan SONRA yeni bir araç geçse
bile. Yönetici hesabı aynı kayıtları sorunsuz görebiliyor, "Vardiya" sütunu
da doğru etiketleniyordu; yalnızca kamera kısıtlaması olan hesap etkileniyordu.

**Kök neden:** "Nizamiye Bazlı Kamera Erişimi" (2026-09-21, önceki bölüm)
özelliği, bir hesabın kamera erişim kısıtlamasını cameras.json'daki "id"
alanına göre saklıyor (`kamera_erisim_listesi`, panel checkbox'larının
`value`si `k.id`dir) ve doğruluyordu (`_kamera_id_listesini_dogrula`). AMA
gerçek geçiş kayıtları (`Kayit.kamera_id`), kameranın "id"si DEĞİL "ad"ıyla
(insan tarafından okunabilir isim, ör. "Lojman Nizamiye Kamerası")
damgalanıyordu (bkz. `_pipeline_baslat`: `kamera_id=kamera["ad"]`) — bu,
patch #57'den ÖNCE, kamera erişim kısıtlaması hiç var olmadan önceki bir
tasarım kararıydı. `"id"` HER ZAMAN rastgele bir UUID'dir (`kamera_ekle`:
`"id": str(uuid.uuid4())`) — yani ID, "ad" ile ASLA örtüşmez. Sonuç: bir
hesaba kamera kısıtlaması atandığında, `_guvenlik_kayit_filtresi_uygula`,
`_guvenlik_kayit_gorunur_mu` ve canlı SSE bildirimi (`_sse_yayinla`),
`Kayit.kamera_id` ("ad") değerini DOĞRUDAN "id" kümesiyle karşılaştırıyordu
— bu ikisi asla eşleşmediği için kısıtlı HERHANGİ bir hesap, kısıtlandığı
kameralardan gelen kayıtları da dahil TÜM geçmiş kayıtları SESSİZCE
göremez hale geliyordu. (Patch #57'nin kendi testleri bu hatayı
YAKALAYAMAMIŞTI çünkü test verisi, gerçek pipeline'ı simüle etmek yerine
sentetik kayıtları doğrudan "id" ile oluşturuyordu — bu README'nin
güncellenmiş testleri artık gerçek pipeline'ı taklit ederek "ad" kullanıyor.)

Live kamera izleme uçları (`GET /kameralar`, `/kameralar/{id}/goruntu`,
`/akis`, `/son-plaka`, `/saglik`, `/saglik/tumu`) bu hatadan ETKİLENMEDİ —
onlar zaten hem kısıtlamayı hem URL parametresini "id" ile karşılaştırıyordu.

**Düzeltme:** yeni bir `_kullanicinin_izinli_kamera_adlari(kullanici)`
fonksiyonu, id bazlı kısıtlamayı cameras.json üzerinden karşılık gelen "ad"
değerlerine çevirir; `Kayit.kamera_id` ile KARŞILAŞTIRILACAK üç yer
(`_guvenlik_kayit_filtresi_uygula`, `_guvenlik_kayit_gorunur_mu`,
`sse_baglantisi`) artık bu yeni fonksiyonu kullanıyor. Kamera CRUD/canlı
izleme uçları hâlâ eski, id bazlı `_kullanicinin_izinli_kameralari`'yı
kullanmaya devam ediyor — kısıtlamanın PANELDEKİ/API'DEKİ biçimi (id
listesi) hiç değişmedi, yalnızca Kayıt kayıtlarıyla karşılaştırılırken
doğru alana çevriliyor.

## Arvento Sürücü Kimliği Entegrasyonu (2026-09-23)

**Kullanıcı isteği:** "Arvento Sisteminde kimlik kartı ile aracın çalıştıran
personelin, arvento tarafından gelen araç kullanan bilgisi pts sistemine
entegre edilmesini istiyorum. Arvento tarafından bana gönderilen kayıtlar
pts sistemine ekleyeceğim webhook link'i ile tespit edilecek ve o araç
plaka tanıma sisteminden geçiş yaptığında direkt olarak aracı kullanan
personel ismi ona göre güncellenecek."

### Nasıl çalışır

1. Arvento, "bu plakayı şu an kim kullanıyor" bilgisini her değiştiğinde
   PTS'e şu adrese bir `POST` isteği gönderir:

   ```
   POST http://<pts-sunucu-adresi>:8000/entegrasyonlar/arvento/webhook
   Content-Type: application/json
   X-Arvento-Anahtari: <PTS_ARVENTO_ANAHTARI ile aynı değer>

   { "plaka": "34 ABC 123", "surucu_adi": "Ahmet Yılmaz" }
   ```

2. PTS bu olayı `arvento_surucu_olaylari` tablosuna kaydeder (geçmiş, denetim
   ve hata ayıklama için — bkz. `backend/models.py::ArventoSuruculuOlay`).
3. O plaka bir kamera tarafından (veya elle) tekrar okunup yeni bir geçiş
   kaydı oluşturulduğunda, PTS o an için bilinen EN GÜNCEL Arvento sürücüsünü
   otomatik olarak bu yeni kayda ekler — Kayıtlar ekranındaki yeni "Sürücü"
   sütununda görünür.

### Kurulum

1. `.env` dosyanıza güçlü, rastgele bir `PTS_ARVENTO_ANAHTARI` değeri
   ekleyin (bkz. `.env.example`) ve PTS'i yeniden başlatın.
2. Arvento tarafında (veya Arvento entegrasyon ekibiyle görüşerek) webhook
   hedefini yukarıdaki adrese, `X-Arvento-Anahtari` başlığını da AYNI
   değerle ayarlatın.

### Bilinçli sınırlamalar / açık noktalar

- **Kimlik doğrulama şeması KESİNLEŞMEDİ.** Bu entegrasyon yazılırken
  Arvento'nun webhook isteklerini nasıl doğruladığı (paylaşılan anahtar mı,
  imza/HMAC mı, IP allowlist mi) bilinmiyordu. Şu an en basit/yaygın yöntem
  (özel bir HTTP başlığında paylaşılan gizli anahtar) uygulanıyor —
  `PTS_KAMERA_ANAHTARI`/`/kayitlar/otomatik` ile BİREBİR aynı desen. Arvento
  ile görüşüldükten sonra gerçek şema farklıysa, `backend/main.py::
  arvento_webhook` fonksiyonundaki kimlik doğrulama kontrolü (birkaç satır)
  güncellenmesi yeterlidir, geri kalan mantığa dokunulmaz.
- **Gövde alan adları KESİNLEŞMEDİ.** Yukarıdaki `plaka`/`surucu_adi` örnek
  alan adlarıdır — uç nokta ayrıca `plaka_no`, `plate`, `driver_name`,
  `surucu`, `personel_adi` gibi yaygın alternatifleri de otomatik dener (bkz.
  `backend/main.py::_ARVENTO_PLAKA_ALANLARI`/`_ARVENTO_SURUCU_ALANLARI`).
  Gerçek Arvento gövdesi bunların dışında bir alan adı kullanıyorsa, PTS
  buna net bir `422` hatasıyla (hangi alan adlarının denendiğini listeleyerek)
  cevap verir — bu listelere yeni bir alan adı eklemek tek satırlık bir
  değişikliktir.
- **Kişi kayıtlarıyla eşleştirme YAPILMAZ** (kullanıcının açık tercihi):
  Arvento'dan gelen sürücü adı PTS'teki "Kişi" (abone/personel) kayıtlarıyla
  otomatik ilişkilendirilmez, yalnızca serbest metin olarak gösterilir. Araç
  sahibi/abone bilgisi (mevcut "Kişi" sütunu) bundan ETKİLENMEZ — ikisi aynı
  kayıtta bağımsız olarak bir arada görünebilir.
- **Sürücü sütunu şu an yalnızca Kayıtlar ekranında** gösteriliyor; "Son
  Geçişler" paneli ve Plaka Analizi ekranındaki geçmiş listesi bu sütunu
  henüz göstermiyor (istenirse ayrı bir değişiklikle eklenebilir — veri
  zaten API yanıtında mevcut).
- Sürücü bilgisi yalnızca YENİ oluşturulan kayıtlara otomatik işlenir; eski
  kayıtlar geriye dönük GÜNCELLENMEZ.

## .env Dosyasının Gerçekten Okunması ve Otomatik Anahtar Üretimi (2026-09-23)

**Bulunan sorun:** `.env.example` dosyası (2026-09-20'de eklendi, bkz. yukarıdaki
"Daha Profesyonel Neler Yapabilirsin?" Denetimi bölümü) TÜM `PTS_*` ortam
değişkenlerini tek bir yerde belgeliyordu, ama PTS bu dosyayı **hiçbir zaman
gerçekten okumuyordu** — `PTS_LICENSE_SECRET`, `PTS_KAMERA_ANAHTARI`,
`PTS_ARVENTO_ANAHTARI` gibi güvenlik-kritik değişkenler yalnızca GERÇEK bir
Windows/Linux ortam değişkeni olarak tanımlanırsa işe yarıyordu. Bu, ".env"
dosyasının varlığının (yaygın "dotenv" kütüphaneleri sayesinde) çoğu
geliştiricide uyandırdığı beklentinin TAM TERSİYDİ. Sonuç: bu değişkenleri
ayarlamayı unutan (ya da .env'i doldurmanın yeterli olduğunu düşünen) bir
kurulum, hiçbir hata almadan güvensiz varsayılanlarla (herkese açık lisans
secret'ı, kimliksiz kamera/Arvento webhook uç noktaları) sessizce çalışmaya
devam ederdi — panelin "Güvenlik Uyarıları" bandını fark etmeyen bir
yönetici için bu süresiz sürebilirdi.

Bu, birden fazla sahaya (ör. farklı otopark noktalarına) kurulum yapma
planı gündeme gelince fark edildi: her yeni kurulumda bu adımın elle,
doğru şekilde tekrarlanmasına güvenmek ölçeklenebilir değil.

**Düzeltme:**

- `backend/__init__.py`, PTS'in HERHANGİ BİR modülü (`database`, `main`,
  `models`, ...) import edilmeden ÖNCE proje kökündeki `.env` dosyasını
  gerçekten okuyup `os.environ`'a uygular (bkz. dosyanın docstring'i —
  neden `main.py`'nin içine değil, paketin `__init__.py`'sine konduğu
  orada ayrıntılı açıklanıyor: `database.py`'nin `PTS_DATABASE_URL`'i
  MODÜL YÜKLENİRKEN okuması, .env'in ondan ÖNCE uygulanmasını zorunlu
  kılıyor). Yalnızca standart kütüphane kullanılır — `python-dotenv` gibi
  yeni bir bağımlılık EKLENMEDİ (bu patch'i uygulayıp bağımlılıkları
  yeniden kurmayı unutan bir kurulumda uygulamanın hiç açılamaması riskini
  tamamen ortadan kaldırmak için).
- `os.environ.setdefault(...)` kullanılır — GERÇEK bir OS ortam değişkeni
  zaten ayarlıysa `.env` bunun ÜZERİNE YAZMAZ, yalnızca EKSİK olanı
  tamamlar. Önceden bu değişkenleri gerçek ortam değişkeni olarak ayarlamış
  mevcut kurulumlar (ör. TPAO'daki üretim makinesi) bu değişiklikten
  HİÇBİR ŞEKİLDE etkilenmez.
- `kurulum.bat`, İLK kurulumda (proje kökünde `.env` hiç yoksa)
  `PTS_LICENSE_SECRET`, `PTS_KAMERA_ANAHTARI` ve `PTS_ARVENTO_ANAHTARI`
  için PowerShell'in kriptografik rastgele sayı üretecini kullanarak güçlü,
  benzersiz değerler üretir ve bunları otomatik olarak bir `.env` dosyasına
  yazar. Zaten bir `.env` varsa (ör. kurulum daha önce yapılmış) DOKUNULMAZ.
  PowerShell çalışmazsa (çok nadir), `.env` oluşturulmadan devam edilir ve
  kullanıcıya anahtarları elle ayarlaması gerektiği açıkça söylenir —
  sessizce geçilmez.
- `.env.example`'ın üst notu ve `.gitignore`'daki ilgili yorum bu yeni
  davranışı yansıtacak şekilde güncellendi.

**Kapsam dışı bırakılan (bilinçli):** `PTS_AUTH_SECRET` bu mekanizmaya DAHİL
EDİLMEDİ — o zaten kendi otomatik üretim/kalıcı saklama mekanizmasına sahip
(`backend/auth_secret.key`, bkz. ilgili .env.example notu), ayrıca bir işlem
gerekmiyor.

## SQLite WAL Modu ve `busy_timeout` (2026-09-23)

**Bulunan sorun:** "sistem nasıl daha sağlıklı/hızlı çalışır" denetiminde,
SQLite kullanan (SQL Server kurulmamış, çoğunlukla küçük/tek-şubeli sahalardaki
varsayılan) kurulumların SQLite'ın VARSAYILAN günlükleme modunda ("rollback
journal") çalıştığı görüldü. Bu modda bir YAZMA işlemi (ör. kamera pipeline'ının
sürekli yazdığı yeni `Kayit` satırları) TÜM veritabanı dosyasını kilitler — o an
başka HİÇBİR okuma/yazma yapılamaz. Panel kullanıcıları (Kontrol Merkezi'ndeki
"Son Geçişler" widget'ı, raporlar vb.) tam da bu sırada okuma yapmaya
çalışırsa, ara sıra "database is locked" hatasına ya da açıklanamayan kısa
yavaşlamalara maruz kalabilirler — özellikle geçiş trafiğinin yoğun olduğu
saatlerde.

**Düzeltme:** `backend/database.py`, veritabanı SQLite ise motora bir
`connect` olay dinleyicisi ekler ve HER yeni bağlantıda şu iki PRAGMA'yı
uygular:

- `PRAGMA journal_mode=WAL` — Write-Ahead Logging: okuyucular, bir yazma
  işlemi sürerken BLOKE OLMADAN eski veriyi okumaya devam edebilir; okuma/yazma
  eşzamanlılığı büyük ölçüde iyileşir.
- `PRAGMA busy_timeout=5000` — birden fazla YAZICI aynı anda çakışırsa (WAL
  modunda bile tek bir yazıcı sırası vardır), SQLite hemen hata vermek yerine
  5 saniye BEKLEYİP tekrar dener; çoğu geçici çakışma bu sürede kendiliğinden
  çözülür.

Bu PRAGMA'ların modül yüklenirken BİR KEZ değil de `event.listens_for(engine,
"connect")` ile HER bağlantı açılışında uygulanması bilinçli bir tercihtir:
`busy_timeout` bağlantı/oturum bazlıdır — havuzun sonradan açtığı yeni
bağlantılarda, yalnızca modül yüklenirken bir kez çalıştırılsaydı sessizce
devre dışı kalırdı.

**Etki alanı:** Yalnızca SQLite kurulumlarını ilgilendirir — `PTS_DATABASE_URL`
bir SQL Server bağlantısına ayarlıysa (`mssql+pyodbc://...`) bu blok hiç
çalışmaz, mevcut `pool_pre_ping`/`pool_recycle` davranışı değişmeden kalır.

**Yedekleme üzerindeki etkisi (ÖNEMLİ):** WAL modunda son işlemler bir süre
ana `pts.db` dosyasına değil, yanında oluşan `pts.db-wal` dosyasına yazılabilir
— yalnızca `pts.db`yi kopyalayan bir yedekleme betiği bu son işlemleri
SESSİZCE KAÇIRABİLİR. Ayrıntılı öneri (üç dosyayı birlikte kopyalama ya da
`wal_checkpoint(TRUNCATE)` / SQLite'ın kendi `.backup` mekanizması) için bkz.
yukarıdaki "Üretim Ortamı (Gerçek Kullanım) Notları" bölümündeki güncellenmiş
"Yedekleme" maddesi.

**Doğrulama notu:** Bu değişiklik yalnızca sözdizimsel olarak doğrulanmıştır
(`py_compile`) — SQLAlchemy'nin kurulu olmadığı bazı geliştirme/test
ortamlarında PRAGMA mantığı gerçek bir SQLite bağlantısı üzerinde ÇALIŞTIRILARAK
test edilememiştir. Gerçek bir SQLite kurulumunda `PRAGMA journal_mode;`
çalıştırıp `wal` döndüğünü doğrulamanız önerilir.

## Tespit Alanı (ROI)/Plaka Kutusu/Güven Skoru Bilgilerinin Görsellerden ve Raporlardan Kaldırılması (2026-09-23)

**Kullanıcı isteği:** "kayıtlarda tespit alanı ROI, plaka alanı ve % kaç ile
okunduğu raporlara/son geçişlere eklenmesin, hatta canlı izlemede bile görüntü
kirliliği olmasın."

**Bulunan durum:** `camera_reader.py::_kareyi_isle`, işlediği HER karenin bir
KOPYASI üzerine (varsa) yapılandırılmış ROI sınırının bir çizgisini, HER
tespit için yeşil/gri bir kutuyu ve `"PLAKA  %XX"` biçiminde bir metni
`_kare_uzerine_ciz` ile basıyordu. Bu TEK "işaretlenmiş" (annotated) kare hem
canlı izleme akışına (`/kameralar/{id}/akis`, `/kameralar/{id}/goruntu`) HEM DE
— oy birikimi oturumuna geçirilerek — nihayetinde KAYDEDİLEN, panelde
gösterilen ve PDF/Excel'e aktarılan araç fotoğrafının ta kendisi oluyordu.
Yani hem canlı izlemede hem arşivlenen her kayıtta bu teknik/hata-ayıklama
bilgileri kalıcı olarak görsele işlenmiş durumdaydı.

**Düzeltme:**

- `_kare_uzerine_ciz` fonksiyonu ve yalnızca onun kullandığı overlay renk
  sabitleri tamamen kaldırıldı. `_kareyi_isle` artık kareyi HİÇ İŞARETLEMEDEN
  JPEG'e kodluyor; bu TEK temiz kare hem canlı önizleme akışında hem
  kaydedilen/rapor edilen görsel olarak kullanılıyor.
- ROI'nin KENDİSİ (yapılandırılmış tespit alanı) işlevsel olarak
  DEĞİŞMEDİ -- hangi tespitlerin oy birikimine gireceğini belirlemek için
  hâlâ hesaplanıp uygulanıyor, yalnızca artık kare üzerine ÇİZİLMİYOR.
  Kamera kurulumunda ROI'yi tanımlamak için ayrı, isteğe bağlı açılan bir araç
  (Kameralar ekranındaki "Tespit Alanı (ROI) ayarla" düğmesi) zaten var ve bu
  tarayıcıda kendi etkileşimli SVG katmanını kullanıyor -- sunucu tarafında
  kare üzerine hiçbir şey basılmasına ihtiyaç yok.
- Kayıtlar ve Plaka Analizi tablolarındaki "Güven" (%) sütunu kaldırıldı.
- Tek-kayıt PDF indirmesindeki ("Kaydı Düzenle" ekranındaki "PDF indir")
  "Güven Skoru:" satırı kaldırıldı; yerine (panelin tek-kayıt detay
  modalinde 2026-09-20'de yapılan aynı gerekçeli değişiklikle tutarlı olarak)
  kaydın Not alanı (`Kayit.not_metni`) geldi. Toplu "GEÇİŞ RAPORU" PDF'inde
  zaten hiç güven skoru sütunu yoktu, Excel dışa aktarımında da hiç yoktu --
  ikisinde de değişiklik gerekmedi.

**Kapsam dışı bırakılan (bilinçli):** Sistem Ayarları'ndaki "Min. kayıt güven
skoru" eşikleri (`otomatik_kayit_min_guven_skoru` vb.) ve Toplu Doğruluk
Testi aracı DEĞİŞMEDİ -- bunlar birer YÖNETİCİ YAPILANDIRMASI/tanı aracı,
sıradan kayıt/rapor/son geçiş görüntüleme akışının bir parçası değil.

## Olay Detayındaki Ayrı "Bariyer Aç" Düğmesinin Kaldırılması (2026-09-24)

**Kullanıcı isteği:** "araçlarda bariyer aç kısmını kaldıralım, kayıtsız
olan araçlarda da sadece ziyaretçi giriş diye bir buton ekleyelim bariyer aç
butonu gereksiz."

**Bulunan durum:** Bir geçiş kaydına tıklanınca açılan tekil olay detayı
modalinde (`#olayDetayModal`, `olayDetayAc`), bariyeri açmanın İKİ AYRI yolu
aynı anda vardı:

1. Koşulsuz görünen, bağımsız bir **"Bariyer Aç"** düğmesi (`#bariyerAcBtn`,
   `_olayModalBariyerButonunuAyarla`) -- kaydın yetki durumundan bağımsız
   olarak her zaman gösteriliyordu (yalnızca ilgili noktaya bariyer
   tanımlı değilse veya rol yetersizse devre dışı bırakılıyordu).
2. **"Ziyaretçi Girişi (onayla + bariyeri aç)"** kutusu
   (`#ziyaretciGirisiKutusu`, `_ziyaretciGirisiKutusunuAyarla`, 2026-09-17'de
   eklendi) -- yalnızca kayıt HENÜZ onaylı değilse (`yetkili` veya
   `ziyaretci_onayli` DEĞİLSE) görünüyor, onaylama adımıyla BİRLİKTE aynı
   `/bariyer/{id}/ac` uç noktasını çağırıyordu.

Bu, kullanıcı için kafa karıştırıcı bir fazlalıktı: zaten "yetkili" (tanımlı)
bir araç için bariyer otomatik açılıyor (bkz. `main.py::
_kayit_olustur_ve_bildir` içindeki "Yetkili araç girişinde otomatik bariyer
açma"), yani ayrı "Bariyer Aç" düğmesine pratikte ancak (a) tanımsız/
kayıtsız bir aracı, ziyaretçi olarak KAYDETMEDEN sadece bariyeri açmak
istendiğinde -- ki bu, aracın kim/ne olduğu hiç kayda geçmeden bariyerin
açılabildiği, denetim izi bırakmayan bir arka kapıydı -- ya da (b) zaten
onaylı bir aracı manuel olarak tekrar açmak istendiğinde ihtiyaç
duyuluyordu; ikisi de nadir ve asıl "Ziyaretçi Girişi" akışının zaten
kapsadığı veya olmaması gereken durumlardı.

**Yapılan değişiklik:** `#bariyerAcBtn` düğmesi ve onu yöneten
`_olayModalBariyerButonunuAyarla` fonksiyonu tamamen kaldırıldı
(`frontend/index.html`, `frontend/app.js`). Artık modalde bariyer açmanın
TEK yolu "Ziyaretçi Girişi" kutusu -- ki bu zaten yalnızca kayıtsız/onaysız
araçlar için görünüyor, tam olarak kullanıcının istediği "kayıtsız olan
araçlarda sadece ziyaretçi giriş butonu" davranışı. `/bariyer/{id}/ac`
backend uç noktası KALDIRILMADI -- hem bu "Ziyaretçi Girişi" akışı hem de
ayrı, donanım kurulum/test amaçlı "Bariyer Kontrolü" yönetim paneli
(`#bariyer-sekme`, `bariyerAc(id)`) hâlâ onu kullanıyor; bu değişiklik
YALNIZCA olay detayı modalindeki gereksiz/kafa karıştırıcı ikinci düğmeyi
kaldırdı.

**Doğrulama:** Playwright ile modal, kayıtsız (`yetki_durumu: "yetkisiz"`)
sahte bir kayıtla açılıp `#bariyerAcBtn`'in artık DOM'da hiç bulunmadığı ve
"Ziyaretçi Girişi" kutusunun beklendiği gibi görünür olduğu doğrulandı.
`tests/test_olay_detay_plaka_analiz.py` ve `tests/test_frontend_rbac.py`
dahil tüm mevcut testler (230 test) değişiklikten etkilenmeden geçmeye
devam ediyor -- hiçbiri kaldırılan düğmeye bağımlı değildi.

## "Ziyaretçi Girişi" Onayından Bariyer Açma Adımının Kaldırılması + Son Geçişler Kartında Görsele Tıklamanın Artık Not/Detay Ekranını Açması (2026-09-24, devam)

Aynı gün yukarıdaki değişikliğin hemen ardından, kullanıcı iki ilgili ince
ayar daha istedi: "ziyaretçi giriş onayla + bariyer aç kısmınıda düzelt
sadece ziyaretçi giriş onayla kalsın, bir de son geçişlerde direkt araç
resmine tıkladığımda büyük ekranda araç görüntüsü açılmasın not ekleme
sayfası gelsin."

**1) "Ziyaretçi Girişi" onayından bariyer açma kaldırıldı.** Olay detayı
modalindeki "Ziyaretçi Girişi" kutusu (`_ziyaretciGirisiKutusunuAyarla`,
yukarıdaki bölümde tek kalan bariyer açma yolu olarak tarif edilmişti),
onaylarken AYNI ANDA `POST /bariyer/{id}/ac` çağırarak bariyeri de
açıyordu. Bu çağrı tamamen kaldırıldı -- düğme artık yalnızca kaydı
`yetki_durumu="ziyaretci_onayli"` yapıyor, bariyerle ilgili hiçbir işlem
yapmıyor. Düğme metni de "Ziyaretçi Girişi (onayla + bariyeri aç)"'den
"Ziyaretçi Girişi Onayla"ya güncellendi ki arayüz artık yapmadığı bir şeyi
vaat etmesin. Sonuç olarak olay detayı modalinde -- bir önceki bölümdeki
"Bariyer Aç" düğmesinin kaldırılmasıyla birlikte -- artık HİÇBİR bariyer
açma eylemi kalmadı; kayıtsız/ziyaretçi bir araç için bariyerin fiilen
açılması artık uygulamanın bu ekranının kapsamı dışında.

Bilinçli olarak DOKUNULMAYANLAR: `/bariyer/{id}/ac` backend uç noktası
(hâlâ diğer iki akış tarafından kullanılıyor); kamera tespitine hiç bağlı
olmayan, plakayı önceden bilinmeyen bir ziyaretçi için elle giren
"Bağımsız Ziyaretçi Girişi" formu (`ziyaretciBilgileriAc`) -- bu formda
bariyer açmak zaten TEK amaç, kamera tespiti hiç yok; ve "Bariyer
Kontrolü" yönetim paneli (`#bariyer-sekme`) -- donanım kurulum/test aracı.

**2) Son Geçişler kartında görsele tıklama artık detay/not ekranını
açıyor, büyük resim lightbox'ını DEĞİL.** `_gecisKartiOlustur`'ün
oluşturduğu kart görseli (`.gecis-karti-gorsel`) eskiden AYRICA `.thumb`
sınıfını da taşıyordu; bu, dosyanın üst kısmındaki paylaşılan, TÜM
uygulamada (Panel, Kayıtlar, Plaka Analizi, olay detayının kendi görseli)
ortak kullanılan `.thumb`/`.zoomable-img` document-level tıklama
delegasyonuna (bkz. `buyukGorselAc`) yakalanıyor ve yakınlaştırma/pan
destekli büyük görsel lightbox'ını açıyordu. Kullanıcı, kartın plaka/tarih
şeridine veya not ikonuna tıklarsa açılan (`olayDetayAc`) detay/not
modalinin, görsele tıklandığında da açılmasını istedi.

Görselden `.thumb` sınıfı kaldırıldı (artık genel lightbox delegasyonuna
yakalanmıyor) ve görsele doğrudan kendi `onclick`/`onkeydown`'ı eklendi --
kartın diğer iki tıklanabilir alanıyla (not ikonu, plaka/tarih şeridi)
AYNI şekilde `olayDetayAc(k.id)`'yi çağırıyor. Görselin GÖRSEL stili
(boyut, `object-fit`, hover büyütme efekti), artık var olmayan
`.gecis-karti-gorsel.thumb` bileşik seçicisine bağlı kalmadan, doğrudan
`.gecis-karti-gorsel` üzerinde tanımlandı (`frontend/style.css`).

**Kapsam (bilinçli):** yalnızca Son Geçişler kartlarındaki görsel
etkilendi. Kayıtlar/Plaka Analizi tablolarındaki küçük resimler ve olay
detayı modalinin kendi ana görseli (`#olayModalGorsel`) hâlâ `.thumb`/
`.zoomable-img` taşıyor ve eskisi gibi tıklanınca büyüyor -- kullanıcı
büyük/yakınlaştırılmış görseli görmek isterse artık Son Geçişler'den önce
detay modalini açıp (görsele veya plaka/tarih şeridine tıklayarak),
SONRA modal içindeki görsele tıklayarak ulaşabiliyor.

**Testler:** İki değişiklik de saf frontend (HTML/CSS/JS) olduğu için
Playwright ile doğrulandı: (a) "Ziyaretçi Girişi Onayla" düğmesine
tıklandığında `apiCagir`'in hiçbir `/bariyer/` isteği YAPMADIĞI ve düğme
metninin güncellendiği; (b) Son Geçişler kart görselinin artık `.thumb`
sınıfını taşımadığı, tıklandığında `olayDetayAc(id)`'nin çağrıldığı ve
büyük görsel lightbox'ının (`#gorselBuyutModal`) AÇILMADIĞI doğrulandı.
`node --check frontend/app.js` ve mevcut 230 test (hiçbiri bu iki
davranışa bağımlı değildi) değişiklikten etkilenmeden geçmeye devam ediyor.

## "Zombi" SSE Bağlantısı Yüzünden Canlı Ekranların Donması (2026-09-25)

**Kullanıcı talebi/bildirimi:** "sistem hiç kapanmadan aktif bir şekilde
çalışmaya devam etti fakat son geçişler ekranı akşam saatlerinde kalmış
güncellenmemiş neden?" — ardından "yenile desem de düzelmiyor" (uygulama
içi "Yenile" düğmesi de dahil) ve son olarak "sayfayı f5 yapınca düzeldi".
Bu üçü birlikte kök nedeni kesin olarak işaret ediyor: sunucu/kameralar
sorunsuz çalışmaya devam ediyordu (aksi halde tam sayfa yenileme de
düzeltmezdi) — sorun tamamen tarayıcı sekmesinin ağ durumundaydı.

**Kök neden:** `frontend/app.js::_sseBaslatFetch`, gerçek zamanlı olayları
`fetch()` tabanlı bir akışla (`reader.read()` döngüsü) okuyordu.
Bilgisayarın kısa süreliğine uykuya girip çıkması, uzun süreli bir ağ
kesintisi veya benzeri bir senaryoda, bu döngüdeki `reader.read()` çağrısı
bazı tarayıcı/işletim sistemi kombinasyonlarında ASLA sonuçlanmadan (ne
hata fırlatır ne `done: true` döner) sonsuza dek askıda kalabiliyor —
alttaki TCP bağlantısı fiilen ölü ama tarayıcı bunu fark etmiyor
("zombi" bağlantı). Bu durumda `_sseAktif` bayrağı sonsuza dek `true`
kalıyordu: ne `.finally()` bloğundaki yeniden bağlanma mantığı çalışıyordu
(çünkü `fetch` promise'i hiç tamamlanmıyordu), ne de 15 saniyelik yedek
polling (`if (!_sseAktif) {...}` şartına bağlı olduğu için) devreye
giriyordu. Sonuç: Panel, Kayıtlar VE Son Geçişler'in tümü, kullanıcı
sayfayı elle F5 ile (yeni bir `fetch`/TCP bağlantısı zorlayarak) yenileyene
kadar donmuş kalıyordu — uygulama içi "Yenile" düğmeleri de aynı türden
zombi ağ yığınına düşen `apiCagir`/`fetch()` çağrıları kullandığı için
onlar da işe yaramıyordu.

**Düzeltme:** Sunucu zaten `/olaylar/sse` üzerinden en geç 25 saniyede bir
bir "kalp atışı" yorum satırı gönderiyor (bkz. `main.py::sse_baglantisi`,
`asyncio.wait_for(q.get(), timeout=25.0)`). İstemci tarafında yeni
`_sseSonVeriZamani`, akıştan gelen HER parçada (gerçek bir olay veya
yalnızca kalp atışı olsun) güncelleniyor; yeni `_sseController` de o an
aktif `fetch`'in `AbortController`'ını tutuyor. 15 saniyelik yedek
zamanlayıcı, artık yalnızca isimsiz bir kapanış değil (test edilebilir
olması için) adlandırılmış `_canliYenilemeVeZombiSseKontrolu` fonksiyonu:
her turda `_sseAktif` iken de `_sseSonVeriZamani`'nin üzerinden
`SSE_DURGUNLUK_ESIGI_MS` (70 sn — birkaç kaçırılan kalp atışına tolerans
tanır) geçip geçmediğine bakıyor. Geçtiyse bağlantı "durgun/zombi" sayılıp
`_sseController.abort()` ile ZORLA kapatılıyor (bu, mevcut `.finally()`
bloğunu tetikleyip normal üstel-geri-çekilmeli yeniden bağlanma mantığını
devreye sokuyor) VE bu turda Panel/Kayıtlar/Son Geçişler yenilemesi de --
yeniden bağlanmayı beklemeden -- hemen çalıştırılıyor.

**Ek düzeltme (aynı bölge, ilişkili küçük bir sorun):** `_sseYenidenBaglaSayaci`
(üstel geri çekilme sayacı) daha önce hiç sıfırlanmıyordu -- sistemin
ömrü boyunca yaşanan TEK bir geçici ağ kesintisi bile, sonraki bambaşka bir
kesintide de yeniden bağlanmanın gereksiz yere 5 dakikaya kadar sürmesine
yol açabiliyordu. `calistir.bat`/`calistir.sh`'deki AYNI "en az 60 sn
sorunsuz çalıştıysa deneme sayacını sıfırla" deseni buraya da uygulandı --
bir SSE bağlantısı en az 60 saniye sağlıklı kaldıktan sonra koparsa, sayaç
sıfırlanıp bir sonraki yeniden bağlanma yine hızlı (2 sn) başlıyor.

**Testler:** Playwright ile üç senaryo doğrulandı: SSE sağlıklıyken (veri
yakın zamanda geldi) yedek yenilemenin HİÇ çalışmadığı; SSE "zombi"yken
(`_sseAktif=true` ama son veri 70 sn eşiğinden daha eski) hem
`_sseController.abort()`'un çağrıldığı HEM DE Panel/Kayıtlar/Son
Geçişler'in hemen yenilendiği; SSE hiç bağlı değilken (`_sseAktif=false`)
eskisi gibi normal yedek pollingin çalıştığı. Ayrıca sahte bir `fetch`
ile kısa süreli bir bağlantı kopmasının `_sseYenidenBaglaSayaci`'yi
ARTIRDIĞI (sıfırlamadığı) doğrulandı. `node --check frontend/app.js` ve
mevcut 230 test değişiklikten etkilenmeden geçmeye devam ediyor -- bu
saf frontend bir düzeltme olduğu için backend testleri kapsam dışı.

## Tanımlı Kamera Listesinden Kamera Adını Değiştirme (2026-09-25)

**Kullanıcı talebi:** "tanımlı kamera listesine tanımlı kameranın ismini
değiştirmek için buton koyar mısın."

Kameralar ekranındaki "Tanımlı Kameralar" tablosunda, her kameranın adının
yanına bir kalem düğmesi eklendi (`frontend/app.js::kameraAdDuzenleAc`,
yalnızca operatör+ rolüne görünür) — tıklandığında küçük bir modal
(`#kameraAdDuzenleModal`) açılıp yeni ad girilip kaydedilebiliyor. Yön
değiştirmede olduğu gibi (bkz. yukarıdaki 2026-09-17 "Kamera Yön Değiştirme"
notu) kameranın `id`'si, RTSP adresi ve parolası hiç değişmeden kalıyor —
kamerayı silip yeniden eklemeye gerek yok.

**Basit bir etiket değişikliğinden fazlası:** Kameranın "ad"ı yalnızca
`cameras.json`'da görünen bir isim değil, AYNI ZAMANDA her yeni geçiş
kaydına `Kayit.kamera_id` olarak damgalanan değerin ta kendisi (bkz.
`_pipeline_baslat`: `kamera_id=kamera["ad"]`, ve 2026-09-21 tarihli "id vs
ad" hata sınıfının kök nedeni). Yalnızca `cameras.json`'ı güncelleyip
veritabanına dokunmasaydık:

- bu kameraya ait TÜM geçmiş kayıtlar eski adla "yetim" kalırdı (aynı
  fiziksel kamera, raporlarda/filtrelerde SANKİ iki ayrı kameraymış gibi
  görünürdü),
- kamera erişim kısıtlaması olan bir hesap ("Nizamiye Bazlı Kamera
  Erişimi", 2026-09-21), bu kameranın GEÇMİŞ kayıtlarını SESSİZCE
  göremez hale gelebilirdi — çünkü kısıtlama id'den ada her seferinde
  GÜNCEL `cameras.json` ile çevriliyor, ama eski kayıtlar hâlâ eski adı
  taşırdı.

Bu yüzden yeni `PATCH /kameralar/{id}/ad` uç noktası (`main.py::
kamera_ad_degistir`), `cameras.json`'ı güncellemenin yanında, bu kameraya
ait TÜM `Kayit` satırlarının `kamera_id` alanını da (eski ad → yeni ad) TEK
bir veritabanı işleminde günceller. Aynı isimde BAŞKA bir kamera varsa (büyük/
küçük harf ve boşluktan bağımsız karşılaştırılır) 400 ile reddedilir — ileride
yeni kayıtların hangi kameraya ait olduğu belirsizleşmesin diye. Alarm/denetim
kaydı gibi noktasal, "o anki olayı" belgeleyen geçmiş metinler (ör. bir
"kamera_arizasi" alarmının mesaj metni) BİLİNÇLİ OLARAK değiştirilmez — onlar
birer olay günlüğü, geriye dönük "düzeltilmesi" yanlış olurdu; yalnızca fiilen
sorgulanan/filtrelenen `Kayit.kamera_id` alanı güncellenir. Değişiklik, kim
tarafından/eski-yeni ad/kaç kaydın etkilendiği bilgisiyle denetim kaydına
düşer (2026-09-20'deki "kamera silme" denetim kaydıyla aynı gerekçe).

**Testler:** `tests/test_api.py`'ye (fastapi gerektirdiği için yalnızca
`py_compile` ile doğrulandı) 6 yeni test eklendi: ad değişikliğinin hem
kamerayı hem de değişiklikten ÖNCE oluşturulmuş bir kaydı yeni adla
güncellediği (ve geri alındığında eski kaydın da eski ada döndüğü) — bu
testlerin asıl amacı; aynı ada "değiştirmenin" no-op gibi davrandığı; boş
adın 400 döndüğü; başka bir kamerayla ad çakışmasının (baş/son boşluk ve
büyük/küçük harf farkına rağmen) 400 döndüğü; var olmayan kamera için 404;
izleyici rolü için 403. Frontend tarafı Playwright ile doğrulandı: kalem
düğmesi doğru kamera için göründüğü, modal açılınca girdi kutusunun mevcut
adla önceden dolduğu, kaydet'e basınca doğru `PATCH /kameralar/{id}/ad`
isteğinin doğru gövdeyle atıldığı. Mevcut 230 test (saf backend/diğer
frontend testleri, bu değişiklikten etkilenmedi) geçmeye devam ediyor.

## Sistem Taraması: Bulunan Eksikler ve Düzeltmeler (2026-09-25)

Kullanıcı talebi ("sistem ile ilgili geliştirmelere bakar mısın eklenmesi
ya da düzeltmesi gereken eksiklikler var mı") üzerine backend, frontend ve
operasyonel/dağıtım katmanı ayrı ayrı derinlemesine tarandı. Bu bölüm, bu
taramada bulunan ve bu sürümde DÜZELTİLEN sorunları belgeler; henüz
düzeltilmemiş bulgular ilgili sonraki bölümlerde (bkz. aşağıdaki "Otomatik
Veritabanı Yedekleme" ve gelecekteki commit'ler) ele alınıyor.

**En kritik bulgu — bariyerin OTOMATİK açılması hiç devreye giremiyordu:**
panelde bariyer eklerken görünen "Yetkili araç girişinde otomatik aç" onay
kutusu (`frontend/app.js::bariyerForm`) işaretlenip kaydedilse bile,
`POST /bariyer/ayarlar` (`main.py::bariyer_ekle`) isteğin `auto_ac` alanını
HİÇ OKUMUYORDU — yeni bariyer her zaman `auto_ac=False` ile oluşuyordu.
Üstelik bariyer ayarlarını SONRADAN değiştirmenin (bu kutuyu işaretlemek
dahil) hiçbir yolu yoktu — panelde yalnızca ekleme ve silme vardı, "sil
+ yeniden ekle" ise o bariyere bağlı her `Nokta.bariyer_id` referansını
kırardı. Artık: `bariyer_ekle` `auto_ac` alanını okuyor; yeni
`PATCH /bariyer/ayarlar/{id}` uç noktası (`main.py::bariyer_guncelle`,
`schemas.BariyerAyarlariGuncelle` — önceden tanımlı ama hiç kullanılmayan
bir şema) ile bariyeri SİLMEDEN ayarları (ad, mod, http_url, http_metot,
http_govde, auto_ac, aktif) değiştirmek mümkün; panelde "Tanımlı
Bariyerler" tablosuna bir "Otomatik Aç: Açık/Kapalı" sütunu ve bir
düzenleme (kalem) düğmesi eklendi. Değişiklik denetim kaydına düşer.

**GPIO bariyer modu tanımlı ama uygulanmamış, sessizce hiçbir şey
yapmıyordu:** `models.BariyerAyarlari.mod` şemada "gpio" üçüncü bir seçenek
olarak tanımlansa da (panelin kendi arayüzü yalnızca Simülasyon/HTTP
sunuyor, yani bu yalnızca doğrudan API çağrısıyla ya da ileride eklenecek
bir arayüz seçeneğiyle karşılaşılabilecek bir durum), otomatik bariyer açma
döngüsü yalnızca `mod == "http"` durumunu ele alıyordu — `gpio` (ya da
`http_url` boş bırakılmış bir `http` bariyeri) için hiçbir şey olmuyordu:
ne log, ne alarm. Yetkili bir araç girse, plaka doğru okunup kayıt oluşsa
bile bariyer sessizce açılmıyordu. Artık bu durumlarda hem loglanıyor hem
de panelde görülebilecek bir `bariyer_hatasi` alarmı oluşturuluyor.
Gerçek bir GPIO sürücüsü bu sürümde YOK — kullanıcı bu modun herhangi bir
sahada kullanılmadığını (ya da emin olmadığını) belirtti, bu yüzden gerçek
donanım sürücüsü yazılmadı; yalnızca sessiz başarısızlık giderildi.

**LED panel hataları hiçbir yerde görünmüyordu:** `backend/led_panel.py`
tüm durum/hata mesajlarını `print()` ile yazıyordu — bir servis sürecinin
stdout'u tipik olarak hiçbir yerde toplanmaz/görüntülenmez, oysa kod
tabanının geri kalanı (main.py, camera_reader.py) bilinçli olarak
`logging` modülüne geçmiş durumda. Artık `pts.led` alt logger'ı kullanılıyor
(main.py'deki "pts" logger'ının `loglar/pts.log` dosyasına yazan
handler'ını miras alır), yani LED panel hataları da `/sistem/loglar`
üzerinden görülebilir. Ayrıca `LedMesaj` veritabanı tablosu yazma-yalnız
(write-only) idi — hiçbir uç nokta geri okumuyordu; yeni `GET /led/durum`
uç noktası son 20 gönderimi ve varsa en son başarısız gönderimi döner.

**`cameras.json`'a kilitsiz eşzamanlı yazma:** kamera ekleme/silme/yeniden
adlandırma/yön-ROI-aktiflik değiştirme uç noktalarının hepsi "oku → değiştir
→ yaz" işlemini hiçbir kilit olmadan yapıyordu. FastAPI'nin senkron `def`
uç noktaları bir iş parçacığı havuzunda çalıştığı için bu gerçek bir yarış
durumuydu: iki eşzamanlı istek birbirinin değişikliğini sessizce
ezebiliyordu; kamera ekleme tarafında ise lisans kamera limiti kontrolü de
aynı yarışa açıktı. Artık tüm bu uç noktalar `_kamera_dosya_kilit` ile
korunuyor. Ayrıca `_kameralari_yaz` artık ATOMİK yazıyor (geçici dosya +
`os.replace`) — bir okuyucunun yazma sırasında yarım/bozuk JSON okuyup
sessizce boş kamera listesi dönmesi ihtimali ortadan kalktı.

**Kamera adı değiştirmede DB/JSON tutarsızlığı riski:** `kamera_ad_degistir`
önceden ÖNCE veritabanını güncelleyip SONRA `cameras.json`'ı yazıyordu —
JSON yazımı DB commit'inden sonra başarısız olursa iki kaynak birbirinden
sapabiliyordu. Sıra tersine çevrildi (önce JSON, sonra DB) ve DB güncellemesi
başarısız olursa JSON eski adına geri alınmaya çalışılıyor.

**`PUT /sistem/ayarlar` hiçbir değeri doğrulamıyordu:** yalnızca anahtarın
geçerli olup olmadığına bakılıyordu, değerin tipi/aralığı hiç
kontrol edilmiyordu. Örneğin `min_tanima_guveni`'ne sayı yerine metin
yazılırsa, bu değer `_pipeline_baslat` içinde kullanılmaya çalışıldığında
istisna fırlatıyordu — bu da izleme (watchdog) döngüsü her denediğinde
(20 sn'de bir bu ayar okunduğu için) TÜM kameraların sürekli başlatılıp
hemen çökmesine yol açabiliyordu. Artık her ayar için tip/aralık doğrulaması
`_AYAR_DOGRULAYICILAR` sözlüğünde merkezi olarak tanımlı ve `PUT
/sistem/ayarlar` bunu uyguluyor; geçersiz bir değer 400 ile reddediliyor.

**Testler:** yukarıdaki değişikliklerin tümü için `tests/test_api.py`'ye
(yalnızca `py_compile` ile doğrulandı) yeni testler eklendi: ayar doğrulama
(geçersiz/geçerli değerler), LED ayarları/test/durum uç noktaları
(önceden hiç testi yoktu), otomatik bariyer açmanın `gpio` modunda alarm
ürettiği, `auto_ac`'ın artık kaydedildiği ve `PATCH /bariyer/ayarlar/{id}`
ile bir bariyerin id'si değişmeden güncellenebildiği. Mevcut 230 test
(fastapi gerektirmeyen testler) değişmeden geçmeye devam ediyor. Frontend
tarafı (bariyer düzenleme modalı) Playwright ile doğrulandı.

## Otomatik Veritabanı Yedekleme (2026-09-25, kullanıcı isteği)

Sistem taramasında bulunan en önemli operasyonel eksiklerden biri, veritabanının
TEK yedekleme yolunun bir yöneticinin panelden manuel olarak `/sistem/yedek`
indirmesi olmasıydı — bir operatör bunu düzenli yapmayı unutursa (ya da
gerektiğini hiç bilmiyorsa), disk arızası/bozulması durumunda TÜM geçiş
kayıtları ve denetim izi kalıcı olarak kaybolabilirdi. Kullanıcının "günlük
otomatik yedek ekle" talebi üzerine:

- Ayarlar panelinde yeni bir bölüm eklendi: "Veritabanını günde bir kez
  otomatik yedekle" (varsayılan: açık), yedek klasörü (varsayılan: proje
  kökünde `yedekler/` — canlı veritabanının bulunduğu `veritabani/` klasöründen
  KASITLI OLARAK ayrı, tek bir yanlış silme/üzerine yazmanın hem canlıyı hem
  yedekleri birden götürmesini engellemek için; farklı bir diske/harici
  depolamaya da yönlendirilebilir) ve saklama süresi (varsayılan: 30 gün,
  0 = süresiz sakla).
- Arka planda (`main.py::_otomatik_yedek_dongu`), görüntü temizliğiyle AYNI
  "periyodik arka plan bakım görevi" deseniyle her 6 saatte bir kontrol edilir,
  günde bir kez gerçek yedek alınır ve saklama süresinden eski otomatik
  yedekler otomatik silinir. Yalnızca SQLite için çalışır (SQL Server
  kurulumlarında kurumun kendi veritabanı yedekleme araçları kullanılmalı —
  manuel `/sistem/yedek` uç noktasıyla aynı kısıtlama).
- **WAL modu düzeltmesi (önceden bilinen bir kısıtlamaydı, artık giderildi):**
  hem otomatik hem manuel yedekleme, artık `sqlite3`'ün kendi `backup()` API'sini
  kullanan ortak bir yardımcı (`_sqlite_yedek_al`) üzerinden çalışıyor. Önceki
  "ham dosya kopyala" yaklaşımı, WAL modunda henüz ana `.db` dosyasına
  checkpoint yapılmamış (yalnızca `.db-wal` dosyasında duran) son işlemleri
  SESSİZCE KAÇIRABİLİYORDU — `sqlite3.backup()` ise kaynağı ÇALIŞIRKEN
  (okuma/yazmayı kilitlemeden) sayfa sayfa kopyalayıp bu bekleyen içeriği de
  otomatik dahil ediyor, elle bir "PRAGMA wal_checkpoint" adımına gerek
  kalmıyor.
- Otomatik yedekleme arka planda sessizce çalıştığı için, bunun "gerçekten
  çalışıp çalışmadığını" görünür kılmak amacıyla yeni `GET
  /sistem/yedek/otomatik-liste` uç noktası ve Ayarlar panelinde "Son otomatik
  yedek: ... (X MB) — toplam N yedek" şeklinde bir durum satırı eklendi.

**Testler:** `_sqlite_yedek_al`'ın WAL'da bekleyen veriyi gerçekten dahil
ettiğini doğrulayan bir test (yalnızca stdlib `sqlite3` kullandığı için bu
sandbox'ta GERÇEKTEN çalıştırılıp geçti — fastapi gerektirmiyor), ayar
doğrulama testleri (boş klasör yolu, negatif saklama süresi → 400) ve
otomatik yedek listeleme uç noktası için RBAC/içerik testleri eklendi.
Frontend tarafı (yeni ayar alanları + durum satırı) Playwright ile
doğrulandı.

## Frontend Sağlamlık Paketi: Kayıtlar Sekmesi Yarış Durumu + Diğer Küçük Düzeltmeler (2026-09-25, sistem taraması devamı)

Sistem taramasının frontend bulgularından, en görünür/en sık karşılaşılabilir
olanları bu pakette düzeltildi (backend'e dokunulmadı — yalnızca
`frontend/app.js`):

- **Kayıtlar sekmesinde sayfa/filtre yarış durumu (en önemli düzeltme):**
  `kayitlariYukle()` önceden istek sırasını takip etmiyordu — kullanıcı
  filtreyi değiştirip hemen ardından sayfa değiştirirse (ya da art arda hızlı
  filtre değiştirirse), önceki (yavaş) isteğin cevabı sonraki (hızlı) isteğin
  cevabından SONRA dönerse tabloda YANLIŞ sayfanın/filtrenin sonuçları
  görünebiliyordu, sessizce. Düzeltme, `sonGecislerYukle`'de 2026-09-24'te
  kullanılan aynı "istek sıra numarası" desenini uyguluyor: her çağrıda bir
  sayaç artırılıyor, `await` sonrası bu sayaç hâlâ aynıysa (yani araya başka
  bir istek girmemişse) sonuç DOM'a yazılıyor, aksi halde cevap sessizce
  atılıyor (daha yeni bir istek zaten devam ediyordur).
- **`alert()`'in tamamen kaldırılması:** 2026-09-23'te `confirm()`'ün
  `onayAl()`'a taşınmasına yol açan aynı UX sorunu (`alert()` de tarayıcının
  sitenin adresini gösteren, kapatılana kadar TÜM sayfayı bloke eden yerleşik
  penceresini kullanıyor) `alert()` çağrıları için de geçerliydi. Kalan tüm
  `alert()` çağrıları (test kaydı ekleme hatası, toplu Excel içe aktarma satır
  hataları) `toastGoster()`'a taşındı — artık hiçbir hata/bilgi mesajı sayfayı
  bloke etmiyor.
- **Çifte gönderim koruması genişletildi:** daha önce yalnızca birkaç formda
  (kamera, lisans, kayıt düzenleme, kişi, kişi düzenleme, LED, bariyer) olan
  "gönder düğmesini işlem sürerken devre dışı bırak" koruması artık kara
  listesi, site, erişim noktası, kullanıcı ekleme/düzenleme, webhook bildirimi
  ve test kaydı formlarına da eklendi — hızlı çift tıklama artık hiçbir yerde
  aynı kaydı iki kez oluşturamıyor. Ayrıca fiziksel donanıma doğrudan komut
  gönderen "Bariyer Aç" düğmesi için de benzer bir koruma eklendi (bariyer
  başına, önceki istek sürerken aynı bariyer için yeni bir "aç" komutunun
  gönderilmesini engelleyen bir bekleme kümesi) — bu, form gönderimi değil tek
  bir düğme tıklaması olduğundan `disabled` yerine bariyer id'sine göre bir
  koruma kümesi (`Set`) kullanıyor.
- **LED ayarları formu ve LED test gönderimi artık hataları yakalıyor:**
  önceden `ledForm`'un gönderim işleyicisinde ve `ledTestGonder()`'da hiç
  `try/catch` YOKTU — istek başarısız olursa (ör. sunucuya hiç ulaşılamazsa)
  kullanıcı hiçbir geri bildirim almıyor, işlemin sessizce hiçbir şey
  yapmadığı izlenimine kapılıyordu. İkisine de hata yakalama eklendi (LED
  test sonucu artık hatada da sonuç kutusunda kırmızı bir mesaj gösteriyor).
- **`diskBilgisiYukle()`'nin tamamen boş `catch` bloğu dolduruldu:** istek
  başarısız olursa artık en azından konsola loglanıyor ve disk bilgisi
  alanında "Disk bilgisi alınamadı" gösteriliyor (önceden alan sessizce eski
  haliyle kalıyordu, hatanın hiçbir izi yoktu).
- **Kamera adı değiştirme modalında Enter tuşu artık çalışıyor:** bu modal bir
  `<form>` değil (bilinçli bir tercih — bkz. 2026-09-25 tarihli ilgili yorum,
  isim değiştirmenin geçmiş kayıtları da güncelleyen ayrı bir işlem olması),
  bu yüzden uygulamanın geri kalanındaki tüm formlardan farklı olarak
  girdi alanında Enter'a basmak hiçbir şey yapmıyordu. Kaydet mantığı ortak bir
  `kameraAdDuzenleKaydet()` fonksiyonuna çıkarıldı ve hem Kaydet düğmesinin
  `click` olayına hem de girdi alanının `keydown`/Enter olayına bağlandı.

**Testler:** bu patch yalnızca `frontend/app.js` dosyasını değiştiriyor;
backend testleri (230 test) etkilenmeden geçmeye devam ediyor. Üç düzeltme
Playwright ile uçtan uca doğrulandı: (1) Kayıtlar sekmesindeki yarış durumu
düzeltmesinin dayandığı istek-sıra-numarası deseni zaten `sonGecislerYukle`
için 2026-09-24'te aynı yöntemle doğrulanmıştı; bu patchte aynı deseni
`kayitlariYukle`'ye taşıyan kodun `node --check` ile sözdizimi doğrulaması
yapıldı, (2) kamera adı değiştirme modalında Enter tuşuna basmanın gerçekten
`PATCH /kameralar/{id}/ad` isteğini tetiklediği, (3) bir formun gönderim
düğmesinin istek sürerken devre dışı kalıp tamamlanınca yeniden etkinleştiği,
(4) "Bariyer Aç" düğmesinin aynı bariyer için istek sürerken ikinci bir
tıklamayı engelleyip istek bitince yeni bir tıklamaya izin verdiği.

## Operasyonel İyileştirmeler: Otomatik Yeniden Başlatma, Panel Yenileme Ayarı, Elle Bariyer Açma Denetimi (2026-09-25, sistem taraması devamı)

- **`calistir.bat` / `calistir.sh` artık kalıcı olarak durmuyor:** eskiden
  PTS art arda 5 kez kısa sürede (60 sn içinde) çökerse betik "otomatik
  yeniden başlatma DURDURULDU" deyip kapanıyordu. Gözetimsiz çalışan bir
  nizamiye sisteminde bu, geçici ama birkaç dakika süren bir sorunun
  (veritabanı sunucusunun henüz ayağa kalkmamış olması, ağ sürücüsünün geç
  gelmesi, diskin anlık dolması vb.) PTS'i biri pencereye bakana kadar —
  belki saatlerce — kapalı bırakması demekti. Artık betik durmuyor; bunun
  yerine bekleme süresini artırıyor (ilk 4 denemede 5 sn, 5.–9. denemede
  60 sn, sonrasında 5 dk). Kalıcı bir yapılandırma hatası logları/CPU'yu
  boğmuyor, ama sorun kendiliğinden düzeldiğinde PTS de kendiliğinden geri
  geliyor. 5. denemeden itibaren pencerede `loglar/pts.log`'a bakılması
  gerektiğini söyleyen belirgin bir uyarı gösteriliyor. Port 8000 dolu
  kontrolü de ayrıldı: İLK başlatmada (kullanıcı pencerenin başındayken)
  eskisi gibi durup ne yapılması gerektiğini söylüyor; bir çökmeden SONRAKİ
  yeniden başlatmada port hâlâ doluysa (tipik neden: çöken sürecin soketi
  birkaç saniye daha bırakmaması) 30 sn bekleyip tekrar deniyor.
- **"Panel yenileme aralığı (sn)" ayarı artık gerçekten çalışıyor:** bu ayar
  Ayarlar ekranında gösterilip kaydedilebiliyordu ama hiçbir yerde
  kullanılmıyordu — yedek yenileme aralığı `app.js`'te 15 sn olarak sabit
  kodluydu (ölü ayar). Artık canlı bağlantı (SSE) koptuğunda devreye giren
  Panel/Son Geçişler/Kayıtlar yenilemesi bu ayara uyuyor ve ayar
  kaydedildiğinde sayfa yenilenmeden hemen geçerli oluyor. "Donmuş bağlantı"
  (zombi SSE) kontrolü ise ayardan bağımsız olarak en geç 15 sn'de bir
  çalışmaya devam ediyor; donmuş bir bağlantı tespit edildiğinde ayar ne
  olursa olsun ekran hemen yenileniyor.
- **Sistem Ayarları kaydetme hatası artık görünüyor:** bu formun gönderim
  işleyicisinde hata yakalama yoktu; backend geçersiz bir değeri (ör. panel
  yenileme 1 sn) reddettiğinde kullanıcı yalnızca genel "yakalanmamış hata"
  bildirimini görüyordu. Artık "Ayarlar kaydedilemedi: En az 2 olmalı..."
  gibi anlaşılır bir mesaj gösteriliyor; çifte gönderim koruması da eklendi.
- **Elle bariyer açma artık Denetim Kayıtları'na yazılıyor:** bir nizamiye
  sisteminin en hassas işlemlerinden biri olan elle bariyer açma, bugüne
  kadar yalnızca log dosyasına düşüyordu. Artık her başarılı açma
  (`bariyer_ac`) ve her başarısız deneme (`bariyer_ac_basarisiz` — röleye
  ulaşılamaması, HTTP adresinin tanımlı olmaması, desteklenmeyen mod) kim
  tarafından ve ne zaman yapıldığıyla birlikte Denetim Kayıtları ekranında
  görülebiliyor. HTTP modunda röle adresi boş bırakılmış bir bariyer için
  eskiden anlaşılmaz bir "yanıt alınamadı (unknown url type)" hatası
  dönüyordu; artık "HTTP röle adresi tanımlı değil — Bariyer ayarlarından
  düzenleyin" deniyor.
- **Bağlı olduğu erişim noktası olan bir bariyerin silinmesi düzeltildi:**
  `noktalar.bariyer_id` bariyer tablosuna bir FOREIGN KEY. Eskiden böyle bir
  bariyer silindiğinde SQL Server kurulumlarında silme anlamsız bir 500
  hatasıyla reddediliyor, SQLite'ta ise geçiyor ama erişim noktası artık var
  olmayan bir bariyeri göstermeye devam ediyordu. Artık önce bu bariyere
  bağlı noktaların bağlantısı kaldırılıyor (noktalar silinmez, yalnızca
  "bariyersiz" duruma düşer), kaç noktanın etkilendiği mesajda söyleniyor ve
  silme işlemi de denetim kaydına yazılıyor.

**Testler:** `calistir.sh` için sahte `uvicorn`/`sleep` ile GERÇEKTEN
çalıştırılan bir test eklendi (12 ardışık çökmeden sonra betiğin hâlâ
denemeye devam ettiğini ve bekleme sürelerinin 5→60→300 sn sırasıyla
arttığını doğruluyor); `calistir.bat` ve `panel_yenileme_sn` bağlantısı için
statik testler; `tests/test_api.py`'ye elle bariyer açma için 9 test
(simülasyon + denetim kaydı, operatör izni, izleyici 403, kimliksiz 401,
olmayan/pasif bariyer 404, boş HTTP adresi 400, sahte röleyle HTTP başarı,
röleye ulaşılamayınca 503 + başarısız denemenin denetim kaydı) ve bağlı
bariyer silme testi. Panel yenileme aralığının uygulanması (alt/üst sınırlar,
aralık dolmadan yenilememe, donmuş bağlantıda hemen yenileme) ve Ayarlar
formunun hata gösterimi Playwright ile doğrulandı.

## Backend Sağlamlık: Kamera Yeniden Bağlanma Çökme Riski ve Araç Fotoğrafı Kayıpları (2026-09-25, sistem taraması devamı)

- **Kamera yeniden bağlanırken tüm PTS'in çökme riski giderildi:** bir kamera
  kare göndermeyi kestiğinde pipeline yeniden bağlanırken eski bağlantıyı
  (`cv2.VideoCapture`) DOĞRUDAN kapatıyordu — ama ayrı çalışan okuyucu
  thread o anda aynı bağlantı üzerinde `read()` içinde bekliyor olabiliyordu
  (RTSP soket zaman aşımı ~5 sn). OpenCV/FFmpeg, okunmakta olan bir
  bağlantının başka bir thread'den kapatılmasını desteklemez; sonuç
  tanımsızdır ve yerel (native) bir çökme, uyarı vermeden TÜM PTS sürecini
  (tüm kameralar + web paneli) düşürebilir — üstelik tam da bir kameranın
  zaten sorun yaşadığı anda. Artık her bağlantıyı YALNIZCA onu okuyan thread
  kapatıyor: yeniden bağlanma yalnızca "nesil" sayacını artırıyor, eski
  okuyucu süren `read()`'i bitince bunu görüp döngüden çıkıyor ve kendi
  bağlantısını kendisi kapatıyor. Bu, okuma sırasında kapatmayı yakalayan
  sahte bir kamera nesnesiyle GERÇEKTEN çalıştırılan bir testle doğrulandı
  (test eski kodda başarısız oluyor, yeni kodda 5/5 tekrar geçiyor).
- **Aynı saniyedeki iki tespitin fotoğrafları artık birbirini ezmiyor:**
  otomatik kayıt fotoğrafının dosya adı yalnızca `PLAKA_unixsaniye.jpg` idi.
  Aynı geçidi paylaşan giriş+çıkış kameraları aynı aracı aynı saniyede
  gördüğünde ikinci kamera birinci kaydın fotoğrafının ÜZERİNE yazıyor,
  ardından "çapraz kamera tekrarı" olarak atlanınca kendi dosyasını — yani
  İLK kaydın tek fotoğrafını — siliyordu; ilk (geçerli) kayıt sessizce
  fotoğrafsız kalıyordu. Dosya adına kısa rastgele bir ek eklendi.
- **Disk dolduğunda geçiş kaydı artık kaybolmuyor:** fotoğraf diske
  yazılamazsa (disk dolu, izin sorunu) eskiden yarım bir `.jpg` diskte
  kalıyor ve istek 500 ile düşüyordu — yani GEÇİŞ KAYDI DA kayboluyordu.
  Artık yarım dosya siliniyor, kayıt fotoğrafsız oluşturuluyor ve panelde
  "Disk hatası (fotoğraf kaydedilemiyor)" alarmı gösteriliyor (disk doluyken
  her geçişte yeni alarm üretip listeyi boğmamak için en fazla 10 dakikada
  bir).
- **Kayıt oluşturulamazsa yetim fotoğraf kalmıyor:** fotoğraf yazıldıktan
  sonra kayıt oluşturma başarısız olursa (ör. veritabanına o an
  ulaşılamazsa) dosya, hiçbir kaydın göstermediği ve kayıt üzerinden çalışan
  hiçbir temizlik görevinin bulamadığı yetim bir dosya olarak diskte
  kalıyordu. Artık hiçbir kayda bağlanmadıysa siliniyor.
- Panelde ham kod olarak görünen `bariyer_hatasi` ve yeni `disk_hatasi`
  alarm tiplerine Türkçe etiket eklendi.

**Testler:** kamera yarış durumu için `tests/test_camera_reader.py`'ye
gerçekten çalıştırılan bir test; `tests/test_api.py`'ye aynı saniyedeki iki
görselin çakışmaması, çapraz kamera tekrarının ilk kaydın fotoğrafını
silmemesi, disk dolu senaryosu (kayıt oluşur + yarım dosya kalmaz + alarm)
ve kayıt oluşturulamayınca yetim dosya kalmaması testleri.

## Frontend: Oturum Süresi Dolması, Bağlantı Kopukluğu ve Sessiz Hatalar (2026-09-25, sistem taraması devamı)

- **Oturum süresi dolunca ekran artık sessizce donmuyor:** oturum anahtarı
  (token) 8 saat geçerli. Süre dolduktan sonra sunucu her isteği 401 ile
  reddediyordu, ama panelin arka planda kendini yenileyen bölümleri bu
  hatayı yalnızca konsola yazıyordu; canlı bildirim bağlantısı (SSE) da
  401 alıp beş dakikaya kadar aralıklarla sonsuza dek yeniden denemeye devam
  ediyordu. Sonuç: nizamiye ekranı, giriş yapıldıktan 8 saat sonra hiçbir
  uyarı vermeden eski verileri göstermeye devam ediyordu. Artık herhangi bir
  istek 401 aldığında kullanıcı "Oturumunuzun süresi doldu, lütfen tekrar
  giriş yapın" mesajıyla giriş ekranına yönlendiriliyor; ayrıca süre
  dolmadan 10 dakika önce bir uyarı gösteriliyor. (8 saatlik süre bilinçli
  bir güvenlik ayarı olarak DEĞİŞTİRİLMEDİ — yalnızca görünür kılındı.)
- **Sunucuya ulaşılamadığında ekranın üstünde sabit bir uyarı bandı:** PTS
  yeniden başlarken ya da ağ koptuğunda "PTS sunucusuna ulaşılamıyor —
  ekrandaki bilgiler güncel olmayabilir" bandı görünüyor; bağlantı geri
  gelince bant kayboluyor ve panel beklemeden tazeleniyor.
- **Sessiz yükleyici hataları:** Panel, lisans, kamera, grafik, kara liste,
  bariyer, site/erişim noktası, denetim, sistem sağlığı/log/ayarlar, webhook,
  kişi listesi, LED ayarları ve otomatik yedek durumu yükleyicilerindeki
  "yalnızca konsola yaz" hata yakalayıcıları ortak bir `_yuklemeHatasi`
  fonksiyonuna taşındı: gerçek hatalar (ör. 500) kullanıcıya bir uyarı
  olarak gösteriliyor (her bölüm için en fazla dakikada bir, ekranı boğmamak
  için); yetki (403) hataları — bir operatörün yönetici verisini görememesi
  beklenen bir durum — ve ağ kopukluğu (tek bir bant zaten gösteriyor)
  tekrar tekrar bildirilmiyor. Hiç hata yakalaması olmayan birkaç işlem
  (kişi düzenleme penceresini açma, görüntü temizleme, webhook aç/kapat ve
  silme) de artık hatayı kullanıcıya gösteriyor.
- **Olay detayı penceresinde yarış durumu:** iki farklı geçişe art arda
  hızlıca tıklandığında (ya da bir satıra tıklarken yeni bir canlı
  bildirime tıklandığında) ilk tıklamanın geç dönen cevabı pencereyi ikinci
  aracın bilgileriyle doldurduktan SONRA eski aracın plakası/fotoğrafıyla
  üzerine yazabiliyordu — görevli yanlış araca not yazabilir ya da yanlış
  kaydı onaylayabilirdi. Kayıtlar/Son Geçişler'deki aynı istek sıra numarası
  deseniyle artık yalnızca EN SON açılma isteği pencereyi dolduruyor; kişi ve
  erişim noktası bilgileri de artık paralel çekiliyor (pencere daha hızlı
  açılıyor).

**Testler:** Playwright ile doğrulandı: token bitiş zamanının okunması,
bağlantı bandının görünüp kaybolması, 403/ağ hatalarının tekrar
bildirilmemesi ve 500'ün dakikada bir bildirilmesi, olay detayında geç dönen
eski cevabın yeni aracın üzerine yazmaması, 401'de giriş ekranına
yönlendirme ve mesajın gösterilmesi.

## Performans: PDF/Excel Raporları ve Kayıt/Plaka Aramasındaki Yavaşlık (2026-09-25, kullanıcı geri bildirimi)

Kullanıcı geri bildirimi: "PDF ve Excel indirirken, sistemde kayıtlarda araç
arattığımda işlemin yavaş ilerlediğini tespit ettim ... her an çökecekmiş
gibi yavaş hareket ediyor" (ekran görüntüsünde Plaka Analizi penceresi
yükleniyor simgesinde bekliyor). Ölçüm ve kod incelemesiyle bulunan kök
nedenler ve düzeltmeler:

- **Rapor, tüm sistemi kilitliyordu (asıl neden):** büyük bir PDF raporu
  (2000 satıra kadar, her satırda bir görsel) ana PTS sürecinin içinde
  üretiliyordu. Python'da aynı süreçteki işler tek bir çekirdek kilidini
  (GIL) paylaştığı için, rapor hazırlanırken (ölçüm: 2000 satır ~41 sn)
  diğer kullanıcıların istekleri (Plaka Analizi, Kayıtlar), canlı kamera
  akışları ve plaka tanıma sırasını beklemek zorunda kalıyordu — tam olarak
  "rapor indirirken aramanın yavaşlaması". Artık rapor dosyası **ayrı bir
  işletim sistemi sürecinde** üretiliyor; ana süreç yalnızca sonucu
  bekliyor ve panel/kameralar etkilenmiyor. Aynı anda yalnızca bir büyük
  rapor üretiliyor (ikinci istek sırasını bekliyor). Ayrı süreç herhangi bir
  nedenle başlatılamazsa rapor eskisi gibi süreç içinde üretilir;
  `PTS_RAPOR_AYRI_SURECTE=0` ortam değişkeniyle bu özellik kapatılabilir.
- **PDF üretimi ~6 kat hızlandı (2000 satır: ~41 sn → ~7-12 sn):** sürenin
  ~%75'i her kamera karesini TAM çözünürlükte (1920x1080) açıp sonra
  küçültmekten geliyordu. Artık JPEG "draft" moduyla görsel doğrudan 1/8
  ölçekte çözülüyor (küçük resim için görsel kalite aynı); panelin
  oluşturduğu küçük resim önbelleği varsa o kullanılıyor. Kısa ve serbest
  metin olmayan hücreler (ID, plaka, tarih, geçiş tipi) daha hafif düz metin
  olarak çiziliyor.
- **Vardiya eşleştirmesi zamanla büyüyen bir yavaşlıktı:** Kayıtlar
  ekranındaki ve raporlardaki "Vardiya" sütunu için her kayıt, sistemin
  kurulduğu günden beri açılmış TÜM vardiya oturumlarıyla tek tek
  karşılaştırılıyordu (tek bir kaydın detayı için bile tüm oturum tablosu
  okunuyordu) — her vardiya girişiyle biraz daha yavaşlıyordu. Artık
  yalnızca kayıtların zaman aralığıyla çakışan oturumlar okunuyor ve
  eşleştirme bir süpürme algoritmasıyla yapılıyor (5000 kayıt x 3000
  oturum: saniyeler yerine ~0,1 sn; sonuçların eski yöntemle birebir aynı
  olduğu rastgele üretilmiş yüzlerce senaryoyla test edildi).
- **Güvenlik personeli / Vardiya filtresi için "saatli bomba" giderildi:**
  bu filtre, bir hesabın/vardiyanın TÜM geçmiş oturumlarını tek tek
  `(tarih >= a VE tarih < b) VEYA ...` biçiminde sıralayan bir SQL koşuluyla
  uygulanıyordu. Koşul her vardiya girişiyle büyüyordu; üstelik SQL Server
  tek sorguda en fazla 2100 parametreye izin verdiği için bir vardiya
  adında ~1050 oturum birikince (ör. 3 hesap x günde 1 oturum ≈ 1 yıl)
  Kayıtlar ekranı, Vardiya filtresi ve güvenlik personelinin tüm kayıt
  görünümleri hata verip TAMAMEN çalışmaz hale gelecekti. Artık sabit
  boyutlu bir `EXISTS` alt sorgusu kullanılıyor (anlamı aynı).
- **Küçük resimler:** Kayıtlar tablosu, Son Geçişler kartları ve Plaka
  Analizi penceresi 96x68 px'lik küçük resimler için TAM kamera karesini
  (150-400 KB) indiriyordu — 50 satırlık bir sayfa her yenilemede ~10-20 MB.
  Artık sunucu, ilk istekte üretip diske önbelleğe aldığı küçük resmi
  (~20 KB, `goruntuler/.kucuk/`) gönderiyor; tam çözünürlüklü görsel yalnızca
  görsel büyütülünce indiriliyor (önce küçük resim anında gösterilir, tam
  görsel hazır olunca yerine konur). Görseller oturum boyunca tarayıcıda
  önbelleğe alınıyor (tablo her yeni geçişte yeniden çizildiğinde aynı
  görseller tekrar indirilmiyor). Orijinali silinen küçük resimler periyodik
  görüntü temizliğinde otomatik siliniyor.
- **Plaka Analizi:** eşleşen kişi, tüm aktif kişileri (toplu içe aktarmayla
  binlerce olabilir) belleğe yükleyip tek tek karşılaştırmak yerine
  veritabanında bulunuyor. Ayrıca "Toplam Geçiş" sayısı eskiden listelenen
  en fazla 50 kayıtla sınırlıydı (50'den fazla geçişi olan araç için hep
  "50" yazıyordu) — artık gerçek toplam gösteriliyor.
- **Kayıtlar listesinde gereksiz sorgu:** her Kayıtlar yüklemesinde (ve her
  raporda) sonucu hiç kullanılmayan, filtrelenmiş tabloyu baştan sona sayan
  bir `COUNT` sorgusu çalışıyordu — kaldırıldı.
- **Rapor indirme deneyimi:** rapor eskiden yeni bir sekmede açılıyordu;
  hazırlanırken hiçbir geri bildirim yoktu, kullanıcı "takıldı" sanıp tekrar
  bastığında sunucuda ikinci bir rapor aynı anda üretilmeye başlıyordu.
  Artık "Rapor hazırlanıyor…" bildirimi gösteriliyor, düğmeler rapor
  bitene kadar devre dışı kalıyor ve dosya hazır olunca doğrudan iniyor.
- **Rapor ekrandaki filtreyle aynı:** ekranda "Yetki Durumu" filtresi
  seçiliyken alınan Excel/PDF bu filtreyi yok sayıp TÜM kayıtları
  içeriyordu — artık filtre rapora da uygulanıyor.
- **Geçici dosyalar birikmiyordu değil, birikiyordu:** üretilen her rapor ve
  her "DB Yedek" indirmesinin geçici TAM veritabanı kopyası
  `disa_aktarilanlar/` klasöründe süresiz kalıyordu (disk + kişisel veri
  riski). Artık dosyalar indirildikten sonra siliniyor; 24 saatten eski
  kalıntılar periyodik temizlikte temizleniyor.

**Testler:** gerçekten çalıştırılanlar: vardiya eşleştirme algoritmasının
eski yöntemle birebir aynı sonucu verdiği rastgele senaryolar + büyük veri
hız testi (`tests/test_vardiya_eslestirme.py`), küçük resim önbelleği
(`tests/test_kucuk_gorsel.py`), PDF/Excel'in "spawn" ile başlatılan ayrı
bir süreçte üretilebildiği (`tests/test_rapor_ayri_surec.py` — Windows'taki
davranışla aynı yöntem), mevcut PDF testleri (Türkçe karakter çizimi dahil).
`tests/test_api.py`'ye (CI'da çalışır): rapor yetki_durumu filtresi, rapor
dosyalarının indirildikten sonra silinmesi, küçük resim ucu (boyut, önbellek
başlığı, yol geçişi koruması, kimliksiz 401), Plaka Analizi'nde 50'yi aşan
toplam. Frontend (küçük resim isteği, büyütmede tam görselin yüklenmesi,
rapor indirme bildirimi/düğme kilidi/tek istek) Playwright ile doğrulandı.

## Okuma Doğruluğu Araçları: Model Karşılaştırma, Kamera Okuma Kalitesi, Riskli Kayıt Filtresi (2026-09-25, kullanıcı isteği)

Kullanıcı: "kameranın en doğru ve hatasız kayıt alması için yapmam gereken
iyileştirme var mı" → "yazılım tarafında ekleyebileceklerini deneyelim".
Kamera kurulumu (plakanın karede en az ~130-150 px görünmesi, 1/500 sn veya
daha hızlı enstantane, ≤30° açı, gece IR ayarı, ana yayın/H.264/≥4 Mbps)
en büyük etkiyi yapar; bu sürüm, yazılım tarafında neyin iyi neyin kötü
okuduğunu ÖLÇMEYİ ve farklı modelleri GÜVENLE denemeyi sağlar:

- **Kamera başına "Okuma Kalitesi" (Kameralar sekmesi):** son 24 saat / 7 /
  30 gündeki otomatik kayıtlardan her kamera için: tek karede okunup
  kaydedilen kayıt oranı (oylamayla doğrulanamamış, en riskli okumalar),
  aynı geçişte farklı karelerde FARKLI okunan (kararsız) kayıt oranı,
  kayıtlı plakaya bakılarak düzeltilen kayıt oranı, ortalama doğrulama kare
  sayısı. Her kamera "İyi / Dikkat / Zayıf / Kayıt yok" olarak
  değerlendirilir ve neyin kontrol edilmesi gerektiğine dair somut öneri
  gösterilir (zoom, enstantane, odak, IR, sıkıştırma, OCR modeli). Hiç kayıt
  üretmeyen tanımlı kameralar da listelenir. Eşikler:
  `backend/okuma_kalitesi.py`.
- **Kayıtlar'da "Doğrulama" filtresi:** "Riskli okumalar", "Tek karede
  okunan", "Farklı okunan (kararsız)", "Kayıtlı plakaya göre düzeltilen" —
  yanlış okunmuş olma ihtimali en yüksek otomatik kayıtları hızlıca gözden
  geçirmek için. Excel/PDF raporuna da uygulanır. Elle girilen kayıtlar bu
  filtrelerde görünmez.
- **OCR modeli artık seçilebilir ve karşılaştırılabilir:** plaka
  karakterlerini okuyan model önceden kodda sabitti (en küçük/en hızlı
  "xs" sürümü). Artık `.env`'de `PTS_ANPR_OCR_MODEL` ile seçilebiliyor
  (ör. daha büyük `cct-s-v2-global-model`). Sistem > Toplu Doğruluk
  Testi'nde dedektör ve OCR modeli açılır listeden seçilip kendi gerçek plaka
  fotoğraflarınızla denenebiliyor: test canlı sistemi DEĞİŞTİRMEDEN, ayrı ve
  CPU'da çalışan geçici bir motorla yapılıyor (canlı kameraların GPU'sunu ve
  ortak kilidini bekletmiyor). Sonuçta doğruluk oranının yanında fotoğraf
  başına süre de gösteriliyor ve aynı oturumdaki denemeler yan yana bir
  karşılaştırma tablosunda listeleniyor (en iyisi vurgulanıyor) — daha
  isabetli ama çok daha yavaş bir model, çok kameralı kurulumda araç başına
  okunan kare sayısını düşürebileceği için ikisi birlikte
  değerlendirilmeli. Karar verilen model `.env`'ye yazılıp PTS yeniden
  başlatılınca canlıya geçer.
- **Güvenli geri dönüş:** `.env`'de yazılan bir dedektör/OCR modeli
  yüklenemezse (yazım hatası ya da kurulu kütüphane sürümünde bulunmayan
  bir model) canlı sistemde TÜM kameraların tanıması durmuyor: hata loglanıp
  varsayılan modellerle devam ediliyor. Test ekranında ise yüklenemeyen
  model açık bir hata mesajıyla bildiriliyor.

**Testler:** gerçekten çalıştırılanlar: OCR modeli seçimi/ortam değişkeni,
yüklenemeyen modelde varsayılana dönüş, test motorunun ortam
değişkenlerini yok sayıp CPU'da çalışması (`tests/test_anpr_engine.py`);
toplu doğruluk testinin farklı modeli ayrı motorla deneyip canlı motora
dokunmaması, test motorunun önbelleklenmesi ve yüklenemeyen modelde
anlaşılır hata (`tests/test_camera_reader.py`); okuma kalitesi
değerlendirme eşikleri ve önerileri (`tests/test_okuma_kalitesi.py`).
`tests/test_api.py`'ye (CI'da çalışır): Doğrulama filtresi (liste, sayfa
bilgisi, rapor, geçersiz değer), okuma kalitesi ucu (oranlar, rol, gün
sınırı), model listesi, model adında yol karakterlerinin reddedilmesi.
Frontend (okuma kalitesi tablosu, HTML kaçışlama, model seçimi, karşılaştırma
tablosu, filtre parametresi) Playwright ile doğrulandı.

## Bekleyen Araç Kısa Süre Okunamayınca İkinci Kayıt Oluşması (2026-09-25, kullanıcı ekran görüntüsü)

Kullanıcının ekran görüntüsü: gece, bariyerde bekleyen "39 AES 145" aynı
giriş kamerasından 21:31 ve 21:32'de İKİ ayrı "Yetkisiz" kayıt olarak
düşmüş; ikinci karede aracın önünde bir görevli yürüyor.

**Kök neden:** 2026-09-24'te eklenen "bekleyen araç" koruması, aracın gidip
gitmediğine oturumun NASIL kapandığına bakarak karar veriyordu — plaka 1,2
saniye okunmazsa araç "gitti" sayılıyordu. Ama bekleyen bir aracın plakası
sık sık birkaç saniyeliğine okunamaz: önünden görevli geçer, gece far/IR
parlaması okumayı bozar, araç biraz ilerler. Böyle bir kesinti "araç gitti"
olarak yorumlanıyor; plaka tekrar okununca, son kayıttan beri 30 sn
(`tekrar_gecikme_sn`) geçmişse YENİ bir geçiş kaydı oluşuyordu. Görevli
aracı kontrol ederken bu tam olarak 1 dakika aralıkla iki kayıt demekti.

**Düzeltme:** kamera artık her plaka için ham okumalardan ayrı bir "görünüm"
tutuyor: plaka en az 60 sn (Ayarlar'daki tekrar gecikmesi daha büyükse o
kadar) boyunca HİÇ okunmadıysa araç gerçekten gitmiş sayılıyor. Bundan kısa
kesintiler aynı görünümün devamı ve aynı görünüm için en fazla BİR kayıt
oluşuyor. Güveni düşük okumalar (ör. gece, oy birikimine girmeyen) da
"araç hâlâ orada" kanıtı olarak sayılıyor. Aracın gerçekten gidip geri
gelmesi (60 sn'den uzun hiç görülmemesi) eskisi gibi yeni bir geçiş olarak
kaydediliyor.

**Testler:** `tests/test_camera_reader.py`'ye gerçek pipeline üzerinden
(sahte motor + kontrollü saat) çalıştırılan üç senaryo: bekleyen aracın
önünden iki kez biri geçmesi (eski kodda 2 kayıt, yenide 1), 65 sn boyunca
yalnızca düşük güvenli okumalar (eski kodda 2, yenide 1), aracın gerçekten
gidip dönmesi (her iki kodda da 2). İlk ikisi eski kodda başarısız oluyor.

## Kameranın Kendi Plaka Okumasını PTS'e Aktarma (Dahua ANPR, 2026-09-25, kullanıcı isteği)

Kullanıcı: "Dahua ITC413 ... PTS'e aktaran bir bağlantı ekler misin, nasıl
olacak deneyelim". Dahua ITC413-PW4D gibi giriş-çıkış ANPR kameraları
plakayı kendileri de okur (üretici: tanıma ≥%98). Bu sürümle PTS, kameranın
okumasını da alıp kendi okumasıyla birleştiriyor.

**Nasıl çalışır:**
- PTS, kameranın HTTP olay akışına bağlanır (Dahua HTTP API:
  `snapManager.cgi?action=attachFileProc&Flags[0]=Event&Events=[TrafficJunction]`,
  Digest kimlik doğrulama). Kullanıcı adı/parola ve IP, kameranın PTS'te
  zaten kayıtlı RTSP adresinden alınır; ayrıca girilmez.
- Kamera her plaka okuduğunda olay metnini (`...TrafficCar.PlateNumber=...`)
  ve fotoğrafını gönderir. PTS bu okumayı kendi çok kareli oylamasına
  **güçlü bir oy** olarak ekler (tek başına ~5 iyi kareye denk):
  - iki okuma aynıysa kayıt daha güvenilir olur;
  - PTS'in modeli okuyamasa bile (gece, parlama) kameranın okuması tek
    başına kaydı oluşturur (kaydedilen güven %98);
  - çelişkide kameranın okuması ağır basar (ör. PTS "39 AES 146", kamera
    "39 AES 145" → "39 AES 145").
  Aynı araç için tekrar kayıt koruması (bekleyen araç, çapraz kamera) bu
  okumalar için de aynen geçerli; kayıt yine tek kayıttır.
- Kameranın bağlantısı koparsa PTS artan beklemeyle (en fazla 60 sn) yeniden
  bağlanır; bağlantı yoksa PTS kendi okumasıyla eskisi gibi çalışmaya
  devam eder.

**Açmak için:** Kameralar sekmesi → kamera satırındaki yayın simgesi
(yalnızca yönetici). Önce "Bağlantıyı Test Et" (8 sn dinler; HTTP durumu,
kalp atışı ve bu sürede okunan plakaları gösterir), sonra "Kameranın kendi
plaka okumasını kullan" → Kaydet. Kamera satırında "Kamera ANPR" rozeti
bağlantı durumunu gösterir; penceredeki durum bölümünde alınan olay sayısı,
son plaka, son hata ve kameradan gelen ham mesajlar (teşhis için) görünür.
Her açma/kapama Denetim Kayıtları'na yazılır.

**Kamerada yapılması gerekenler:** kameranın web arayüzünde ANPR/plaka
tanıma açık olmalı, ülke Türkiye seçilmeli, çekim çizgisi (Snapshot
Triggering Line) aracın durduğu yere konmalı. RTSP adresinde kullanıcı
adı/parola bulunmalı (`rtsp://kullanici:parola@ip:554/...`). Kameranın web
portu 80 değilse pencerede belirtilmeli.

**Bilinen belirsizlik:** Dahua'nın farklı yazılım sürümleri olay metnini
farklı biçimde ve farklı olay adlarıyla gönderebiliyor. Plaka hem
`...PlateNumber=` satırlarından hem JSON'daki `"PlateNumber"` alanından
okunuyor; olay adı pencereden değiştirilebiliyor (ör.
`TrafficJunction,TrafficParkingSpace`). Test olay getirmiyorsa, penceredeki
ham mesajlar sahadaki gerçek biçimi gösterir.

**Testler (gerçekten çalıştırıldı):** `tests/test_dahua_olay.py` — Dahua'nın
API belgesindeki yanıt biçimini taklit eden yerel bir sahte kamera
sunucusuyla (gerçek Digest kimlik doğrulaması dahil): RTSP adresinden
bağlantı bilgisi, olay adı doğrulaması (URL enjeksiyonu), anahtar=değer ve
JSON biçimlerinden plaka çıkarma, parça parça gelen akışın doğru
ayrıştırılması ve fotoğrafla eşleştirilmesi, dinleyicinin plakayı ve
fotoğrafı alması, parolanın durum bilgisinde görünmemesi, bağlantı testi
(başarılı / yanlış parola / ulaşılamayan kamera). `tests/test_camera_reader.py`
— PTS okuyamasa da kameranın okumasıyla kayıt oluşması, çelişkide kameranın
okumasının ağır basması, dinleyicinin pipeline ile başlayıp durması.
`tests/test_api.py` (CI) — aç/kapat, kimliksiz RTSP'de 400, yetki, olay adı
doğrulaması, durum ve test uçları, denetim kaydı. Panel penceresi
Playwright ile doğrulandı.
