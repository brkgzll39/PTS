"""PTS backend paketi.

BİLİNÇLİ YERLEŞİM: aşağıdaki ".env dosyasını oku" mantığı buraya, paketin
KENDİSİNE (main.py'nin içine DEĞİL) konur -- çünkü Python paket import
sırası garantisi gereği bu dosya, `backend` paketinin İÇİNDEKİ herhangi bir
modül (`backend.database`, `backend.main`, `backend.models`, ...) import
edilmeden ÖNCE HER ZAMAN çalışır. Bu, kritik bir sıralama gerçeğinden
kaynaklanıyor: `backend/database.py`, `PTS_DATABASE_URL` ortam değişkenini
MODÜL YÜKLENİRKEN (bir fonksiyon çağrılmasını beklemeden, dosyanın en
üstünde) okur -- `.env` yükleme mantığı `main.py`'nin tepesinde olsaydı bile
`database.py` `main.py`'den önce import edildiği için ".env"deki
PTS_DATABASE_URL hiçbir zaman uygulanamazdı.

2026-09-23 kullanıcı isteği (dolaylı -- "başka sitelere (otopark vb.)
kurmak" bağlamında yapılan geniş kapsamlı öneri turunda gündeme geldi):
ÖNCEDEN `.env`/`.env.example` YALNIZCA DOKÜMANTASYONDU -- hiçbir kod bu
dosyayı OKUMUYORDU; `PTS_LICENSE_SECRET`/`PTS_KAMERA_ANAHTARI`/
`PTS_ARVENTO_ANAHTARI` gibi güvenlik-kritik değişkenler yalnızca GERÇEK bir
Windows/Linux ortam değişkeni olarak tanımlanırsa işe yarıyordu. Bu, ".env"
dosyasının VARLIĞININ KENDİSİNİN ima ettiği (dotenv kütüphaneleriyle çok
yaygın olan) davranışın TAM TERSİYDİ -- yeni bir sahaya kurulum yapan biri
(özellikle teknik olmayan bir operatör) bunu bilmezse, sistem HİÇBİR HATA
VERMEDEN güvensiz varsayılanlarla (herkese açık lisans secret'ı, kimliksiz
kamera/Arvento webhook uç noktaları) sessizce çalışmaya devam ederdi --
tam olarak bu kod tabanının her yerde savaştığı "sessiz güvenlik borcu"
sınıfı bir hata.

TASARIM KARARLARI:
- Yalnızca standart kütüphane kullanılır (`python-dotenv` gibi yeni bir
  bağımlılık EKLENMEDİ) -- bkz. `lisans.py`'nin modül docstring'indeki AYNI
  tercih ("Bağımlılık: yalnızca standart kütüphane"). Bunun asıl nedeni:
  main.py'nin İÇİNE yeni bir ZORUNLU import eklemek, bu patch'i uygulayıp
  `pip install -r requirements.txt`'i YENİDEN çalıştırmayı UNUTAN bir
  kurulumda uygulamanın hiç AÇILAMAMASINA (ModuleNotFoundError) yol açardı
  -- eksik bir güvenlik ayarından çok daha kötü bir başarısızlık biçimi.
  Stdlib-only bir çözüm bu riski TAMAMEN ortadan kaldırır.
- `os.environ.setdefault(...)` kullanılır, DOĞRUDAN ATAMA (`os.environ[k] =
  v`) DEĞİL: gerçek bir OS ortam değişkeni zaten ayarlıysa (ör. Windows
  Sistem Özellikleri'nden, bir Windows Servisi/NSSM yapılandırmasından ya da
  bir systemd `EnvironmentFile`'dan) ".env" dosyası bunun ÜZERİNE YAZMAZ --
  ".env" yalnızca EKSİK olanı TAMAMLAR. Bu, önceden GERÇEK ortam
  değişkenleriyle kurulmuş mevcut sahalarla GERİYE DÖNÜK UYUMLULUĞU garanti
  eder (bkz. .env.example'ın güncellenen üst notu).
- ".env" bulunamazsa (önceki davranışla TAM AYNI şekilde) sessizce hiçbir
  şey yapılmaz -- bu dosya OPSİYONELDİR, salt bir kolaylıktır.
- Bozuk/ayrıştırılamayan tek tek SATIRLAR sessizce atlanır (tüm dosyayı
  reddetmek yerine) -- ör. kullanıcının dosyaya elle bir açıklama satırı
  eklemesi (# ile başlamayan) uygulamanın hiç açılmamasına yol açmamalı.
- Dosya GERÇEKTEN okunamazsa (izin hatası vb.) `stderr`e yazılır (sessizce
  yutulmaz) -- ama bu noktada `logging` modülü main.py tarafından henüz
  yapılandırılmamış olabileceğinden `logger.warning` yerine `print`
  kullanılır.
"""
import os
import sys


def _env_dosyasini_yukle() -> None:
    proje_koku = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_yolu = os.path.join(proje_koku, ".env")
    if not os.path.isfile(env_yolu):
        return
    try:
        # utf-8-sig: Windows'ta Not Defteri gibi bazı editörler dosyayı BOM
        # ile kaydedebilir -- düz "utf-8" ile açılırsa ilk satırın anahtar
        # adının başına görünmez bir BOM karakteri karışıp o TEK satırı
        # (genelde ilk/en üstteki anahtarı) sessizce eşleşmez hale getirirdi.
        with open(env_yolu, "r", encoding="utf-8-sig") as dosya:
            satirlar = dosya.readlines()
    except OSError as exc:
        print(f"UYARI: .env dosyası okunamadı ({env_yolu}): {exc}", file=sys.stderr)
        return

    for satir in satirlar:
        satir = satir.strip()
        if not satir or satir.startswith("#") or "=" not in satir:
            continue
        anahtar, _, deger = satir.partition("=")
        anahtar = anahtar.strip()
        if not anahtar:
            continue
        deger = deger.strip()
        # Tırnak içine alınmış değerleri (bazı kullanıcılar/araçlar
        # DEGER="..." biçiminde yazabilir) soy.
        if len(deger) >= 2 and deger[0] == deger[-1] and deger[0] in ("'", '"'):
            deger = deger[1:-1]
        os.environ.setdefault(anahtar, deger)


_env_dosyasini_yukle()
