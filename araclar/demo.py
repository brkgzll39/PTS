"""PTS demo ortamı (2026-10-23): satış sunumu ve tanıtım videosu için.

Gerçek sisteme DOKUNMAZ: veritabanı, görüntüler, ayarlar, lisans, yedekler ve
log `demo/` klasöründedir; .env okunmaz, kamera bağlanmaz, LED simülasyonda.
Marka: musteriler/ornek (Örnek Sanayi A.Ş., gerçek bir kurum değil).

Kullanım: demo.bat'a çift tıklayın, ya da proje klasöründe:
    python araclar\\demo.py                 -> http://127.0.0.1:8100
    python araclar\\demo.py --sifirla       -> demo verisini baştan üretir
    python araclar\\demo.py --marka musteriler/acme --port 8200
    python araclar\\demo.py --canli-aralik 0   -> canlı geçiş üretme

Kullanıcılar: demo / Demo12345 (yönetici, klasik panel)
              kapi / Kapi12345 (operatör, Kapı Modu)
Demo verisi: ~40 kişi, son 7 günün geçişleri (görselleriyle), kara liste,
alarmlar; çalışırken birkaç saniyede bir "canlı" araç geçişi gelir.
Kaldırmak için demo/ klasörünü silmek yeter.
"""
import argparse
import io
import json
import os
import random
import shutil
import sys
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timedelta

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KAMERA_ANAHTARI = "demo-kamera-anahtari"
KAMERALAR = [("Ana Kapı Giriş", "giris"), ("Ana Kapı Çıkış", "cikis")]

ADLAR = ["Ahmet", "Mehmet", "Ayşe", "Fatma", "Mustafa", "Emine", "Ali", "Hatice", "Hüseyin", "Zeynep",
         "Hasan", "Elif", "İbrahim", "Merve", "Murat", "Selin", "Burak", "Esra", "Emre", "Gizem",
         "Okan", "Derya", "Serkan", "Pınar", "Tolga", "Seda", "Kemal", "Büşra", "Onur", "Ece"]
SOYADLAR = ["Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Yıldız", "Yıldırım", "Öztürk", "Aydın", "Özdemir",
            "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Kara", "Koç", "Kurt", "Özkan", "Şimşek"]
BIRIMLER = ["Üretim", "Bakım", "Kalite", "Lojistik", "İnsan Kaynakları", "Muhasebe", "Bilgi İşlem", "Satın Alma"]
IL_KODLARI = ["34", "06", "35", "16", "41", "59", "22", "39", "07", "01"]
HARFLER = "ABCDEFGHJKLMNPRSTUVYZ"
RENKLER = [(200, 200, 205), (30, 30, 35), (235, 235, 235), (120, 20, 25), (25, 50, 110), (90, 95, 100), (150, 120, 70)]


def _ortami_hazirla(demo: str, marka: str, port: int) -> None:
    """backend içe aktarılmadan ÖNCE: her yol demo/ klasörüne."""
    os.makedirs(demo, exist_ok=True)
    for ad in [k for k in os.environ if k.startswith("PTS_")]:
        del os.environ[ad]
    os.environ.update({
        "PTS_ENV_DOSYASINI_ATLA": "1",
        "PTS_DATABASE_URL": "sqlite:///" + os.path.join(demo, "pts_demo.db").replace("\\", "/"),
        "PTS_AUTH_SECRET": "pts-demo-oturum-anahtari-0123456789abcdef",
        "PTS_LICENSE_SECRET": "pts-demo-lisans-anahtari",
        "PTS_LICENSE_FILE": os.path.join(demo, "license.json"),
        "PTS_CAMERAS_FILE": os.path.join(demo, "cameras.json"),
        "PTS_SISTEM_AYARLARI_FILE": os.path.join(demo, "sistem_ayarlari.json"),
        "PTS_LED_CONFIG_FILE": os.path.join(demo, "led_config.json"),
        "PTS_YEDEK_KLASORU": os.path.join(demo, "yedekler"),
        "PTS_GORUNTU_KLASORU": os.path.join(demo, "goruntuler"),
        "PTS_LOG_KLASORU": os.path.join(demo, "loglar"),
        "PTS_MARKA_FILE": os.path.join(KOK, marka, "marka.json"),
        "PTS_KAMERA_ANAHTARI": KAMERA_ANAHTARI,
        # Yalnız bu bilgisayar: Windows "erişime izin ver" sormasın, ağa açılmasın.
        "PTS_HOST": "127.0.0.1",
        "PTS_PORT": str(port),
        "PTS_OTOMATIK_GIRIS_PORTU": "0",
        "PTS_IC_PORT": str(port + 1),
    })


# ---------------------------------------------------------------- görseller
def _yazi_tipi(boyut: int):
    from PIL import ImageFont
    for ad in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(ad, boyut)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=boyut)
    except TypeError:
        return ImageFont.load_default()


def arac_gorseli(plaka: str, gece: bool, tohum, zaman: datetime = None, kamera: str = "") -> bytes:
    """Kamera karesini andıran sentetik görüntü (araç önü + Türk plakası)."""
    from PIL import Image, ImageDraw, ImageFilter
    r = random.Random(tohum)
    g, y = 960, 540
    im = Image.new("RGB", (g, y))
    d = ImageDraw.Draw(im)
    ust, alt = ((18, 22, 30), (45, 48, 55)) if gece else ((150, 160, 170), (95, 100, 105))
    for i in range(y):
        k = i / y
        d.line([(0, i), (g, i)], fill=tuple(int(ust[j] * (1 - k) + alt[j] * k) for j in range(3)))
    d.polygon([(0, y), (g, y), (g * 0.62, y * 0.35), (g * 0.38, y * 0.35)], fill=(60, 62, 66) if gece else (110, 112, 115))
    renk = r.choice(RENKLER)
    golge = tuple(max(0, c - 40) for c in renk)
    cx, gen = g // 2 + r.randint(-60, 60), r.randint(430, 500)
    x0, x1 = cx - gen // 2, cx + gen // 2
    d.rounded_rectangle([x0 + 40, 150, x1 - 40, 260], radius=40, fill=golge)          # kabin
    d.rounded_rectangle([x0 + 70, 165, x1 - 70, 245], radius=24, fill=(40, 55, 70))    # cam
    d.rounded_rectangle([x0, 240, x1, 430], radius=36, fill=renk)                       # gövde
    d.rectangle([x0 + 110, 330, x1 - 110, 370], fill=(25, 25, 28))                       # ızgara
    far = (255, 250, 220) if gece else (230, 230, 225)
    d.ellipse([x0 + 25, 285, x0 + 105, 325], fill=far)
    d.ellipse([x1 - 105, 285, x1 - 25, 325], fill=far)
    if gece:
        isik = Image.new("L", (g, y), 0)
        ImageDraw.Draw(isik).ellipse([x0 - 40, 250, x1 + 40, 360], fill=90)
        im = Image.composite(Image.new("RGB", (g, y), (255, 245, 200)), im, isik.filter(ImageFilter.GaussianBlur(40)))
        d = ImageDraw.Draw(im)
    # Plaka
    pg, py = 230, 52
    px0, py0 = cx - pg // 2, 378
    d.rectangle([px0 - 3, py0 - 3, px0 + pg + 3, py0 + py + 3], fill=(20, 20, 20))
    d.rectangle([px0, py0, px0 + pg, py0 + py], fill=(245, 245, 240))
    d.rectangle([px0, py0, px0 + 26, py0 + py], fill=(29, 63, 187))
    d.text((px0 + 13, py0 + py - 12), "TR", font=_yazi_tipi(12), fill="white", anchor="mm")
    d.text((px0 + 26 + (pg - 26) // 2, py0 + py // 2 + 1), plaka, font=_yazi_tipi(30), fill=(15, 15, 15), anchor="mm")
    if gece:
        im = im.convert("L").convert("RGB")   # IR kamera gibi
    d = ImageDraw.Draw(im)
    d.text((14, 12), f"{kamera}  {(zaman or datetime.now()):%d.%m.%Y %H:%M:%S}", font=_yazi_tipi(16), fill=(255, 255, 255))
    tampon = io.BytesIO()
    im.save(tampon, "JPEG", quality=82)
    return tampon.getvalue()


def rastgele_plaka(r: random.Random) -> str:
    harf = "".join(r.choice(HARFLER) for _ in range(r.choice([1, 2, 3])))
    sayi = r.randint(10, 99) if len(harf) == 3 else r.randint(100, 9999 if len(harf) == 1 else 999)
    return f"{r.choice(IL_KODLARI)} {harf} {sayi}"


# ---------------------------------------------------------------- veri
def veri_uret(m, demo: str) -> dict:
    """Demo veritabanını doldurur; canlı üretici için plaka havuzunu döner."""
    from backend import lisans, models
    r = random.Random(2026)
    db = m.SessionLocal()
    try:
        for ad, sifre, rol in (("demo", "Demo12345", m.ROL_YONETICI), ("kapi", "Kapi12345", m.ROL_OPERATOR)):
            db.add(models.Kullanici(kullanici_adi=ad, parola_hash=m._parola_hashle(sifre), rol=rol, aktif=True))
        kisiler = []
        kullanilan = set()

        def yeni_plaka():
            while True:
                p = rastgele_plaka(r)
                if p not in kullanilan:
                    kullanilan.add(p)
                    return p

        for i in range(30):
            ad = f"{ADLAR[i % len(ADLAR)]} {r.choice(SOYADLAR)}"
            kisiler.append(models.Kisi(ad_soyad=ad, plaka_no=yeni_plaka(), tip="personel",
                                       daire_departman=r.choice(BIRIMLER), telefon=f"05{r.randint(30, 59)} {r.randint(100, 999)} {r.randint(1000, 9999)}"))
        kisiler += [
            models.Kisi(ad_soyad="Selim Ergin", plaka_no=yeni_plaka(), tip="vip", daire_departman="Genel Müdürlük"),
            models.Kisi(ad_soyad="Nermin Ateş", plaka_no=yeni_plaka(), tip="vip", daire_departman="Genel Müdürlük"),
            models.Kisi(ad_soyad="Personel Servisi 1", plaka_no=yeni_plaka(), tip="alt_isveren", daire_departman="Servis"),
            models.Kisi(ad_soyad="Personel Servisi 2", plaka_no=yeni_plaka(), tip="alt_isveren", daire_departman="Servis"),
            models.Kisi(ad_soyad="Yemek Firması", plaka_no=yeni_plaka(), tip="alt_isveren", daire_departman="Yemekhane",
                        otomatik_not="Yemek teslimatı"),
            models.Kisi(ad_soyad="Temizlik Firması", plaka_no=yeni_plaka(), tip="alt_isveren", daire_departman="Temizlik"),
            models.Kisi(ad_soyad="Kargo (Anlaşmalı)", plaka_no=yeni_plaka(), tip="ziyaretci", otomatik_not="Kargo teslimatı"),
            models.Kisi(ad_soyad="Teknik Servis", plaka_no=yeni_plaka(), tip="ziyaretci", otomatik_not="Jeneratör bakımı"),
        ]
        db.add_all(kisiler)
        kara = [yeni_plaka(), yeni_plaka()]
        db.add_all([models.KaraListesi(plaka_no=kara[0], sebep="Tesise girişi yasaklı (güvenlik ihlali)", ekleyen="demo"),
                    models.KaraListesi(plaka_no=kara[1], sebep="Sözleşmesi feshedilen firma", ekleyen="demo")])
        db.commit()
        ziyaretciler = [yeni_plaka() for _ in range(25)]

        goruntu = os.environ["PTS_GORUNTU_KLASORU"]
        os.makedirs(goruntu, exist_ok=True)
        simdi = datetime.now().replace(second=0, microsecond=0)

        def kayit(plaka, zaman, yon, kisi=None, yetki="yetkili", not_metni=None):
            gece = zaman.hour < 7 or zaman.hour >= 19
            dosya = f"demo_{zaman:%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}.jpg"
            with open(os.path.join(goruntu, dosya), "wb") as f:
                f.write(arac_gorseli(plaka, gece, f"{plaka}{zaman}", zaman, KAMERALAR[0 if yon == "giris" else 1][0]))
            k = models.Kayit(plaka_no=plaka, tarih_saat=zaman, kamera_id=KAMERALAR[0 if yon == "giris" else 1][0],
                             yon=yon, goruntu_yolu=os.path.join(goruntu, dosya), guven_skoru=round(r.uniform(0.86, 0.99), 3),
                             yetki_durumu=yetki, kisi_id=kisi.id if kisi else None,
                             kisi_tip_anlik=kisi.tip if kisi else None, dogrulama_kare_sayisi=r.randint(3, 12),
                             farkli_okuma_sayisi=1, not_metni=not_metni or (kisi.otomatik_not if kisi else None),
                             manuel_giris=False)
            db.add(k)
            return k

        personel = [k for k in kisiler if k.tip == "personel"]
        diger = [k for k in kisiler if k.tip != "personel"]
        for gun in range(7, -1, -1):
            tarih = (simdi - timedelta(days=gun)).date()
            hafta_sonu = tarih.weekday() >= 5
            for p in r.sample(personel, 8 if hafta_sonu else 26):
                giris = datetime.combine(tarih, datetime.min.time()) + timedelta(hours=7, minutes=r.randint(20, 75))
                cikis = giris + timedelta(hours=8, minutes=r.randint(30, 110))
                for z, yon in ((giris, "giris"), (cikis, "cikis")):
                    if z <= simdi - timedelta(minutes=3):
                        kayit(p.plaka_no, z, yon, p)
            for k in r.sample(diger, 5):
                giris = datetime.combine(tarih, datetime.min.time()) + timedelta(hours=r.randint(9, 15), minutes=r.randint(0, 59))
                for z, yon in ((giris, "giris"), (giris + timedelta(minutes=r.randint(20, 140)), "cikis")):
                    if z <= simdi - timedelta(minutes=3):
                        kayit(k.plaka_no, z, yon, k, "yetkili" if k.tip != "ziyaretci" else "ziyaretci_onayli")
            for plaka in r.sample(ziyaretciler, 4):
                giris = datetime.combine(tarih, datetime.min.time()) + timedelta(hours=r.randint(9, 16), minutes=r.randint(0, 59))
                if giris <= simdi - timedelta(minutes=3):
                    k = kayit(plaka, giris, "giris", None, "ziyaretci_onayli" if r.random() < .6 else "yetkisiz",
                              r.choice(["Toplantı - Satın Alma", "Teklif sunumu", "Aday görüşmesi", None]))
                    db.flush()
                    cikis = giris + timedelta(minutes=r.randint(25, 150))
                    # Geçmiş günlerin ziyaretçileri çıkmış olsun; bugün biri içeride kalabilir.
                    if cikis <= simdi - timedelta(minutes=3) and (gun > 0 or r.random() < .5):
                        kayit(plaka, cikis, "cikis", None, k.yetki_durumu, k.not_metni)
                    if k.yetki_durumu == "yetkisiz":
                        db.add(models.Alarm(kayit_id=k.id, plaka_no=plaka, alarm_tipi="yetkisiz_arac",
                                            mesaj=f"Tanımsız araç: {plaka}", tarih_saat=giris, okundu=gun > 0))
            if gun in (5, 2):
                z = datetime.combine(tarih, datetime.min.time()) + timedelta(hours=14, minutes=12)
                k = kayit(kara[gun == 2], z, "giris", None, "kara_liste")
                db.flush()
                db.add(models.Alarm(kayit_id=k.id, plaka_no=k.plaka_no, alarm_tipi="kara_liste",
                                    mesaj=f"KARA LİSTEDEKİ ARAÇ: {k.plaka_no}", tarih_saat=z, okundu=gun > 2))
        db.commit()

        # Lisans (demo anahtarıyla), kameralar (bağlantısız), sistem ayarları.
        anahtar = lisans.uret("Demo", kamera_limiti=8, gun=365)
        payload = lisans.coz(anahtar)
        with open(os.environ["PTS_LICENSE_FILE"], "w", encoding="utf-8") as f:
            json.dump({"aktif": True, "anahtar": anahtar, "lisans_id": payload["lisans_id"], "musteri": "Demo",
                       "kamera_limiti": 8, "baslangic_tarihi": payload["baslangic_tarihi"],
                       "bitis_tarihi": payload["bitis_tarihi"], "cihaz_kodu": m._cihaz_kodu()}, f)
        with open(os.environ["PTS_CAMERAS_FILE"], "w", encoding="utf-8") as f:
            json.dump([{"id": f"demo-{i}", "ad": ad, "rtsp_url": "rtsp://demo/kamera", "yon": yon, "aktif": False}
                       for i, (ad, yon) in enumerate(KAMERALAR)], f, ensure_ascii=False)
        with open(os.environ["PTS_SISTEM_AYARLARI_FILE"], "w", encoding="utf-8") as f:
            json.dump({"otomatik_yedek_aktif": False}, f)
        havuz = {"personel": [p.plaka_no for p in personel], "diger": [k.plaka_no for k in diger],
                 "ziyaretci": ziyaretciler, "kara": kara}
        with open(os.path.join(demo, "plakalar.json"), "w", encoding="utf-8") as f:
            json.dump(havuz, f, ensure_ascii=False)
        return havuz
    finally:
        db.close()


# ---------------------------------------------------------------- canlı geçiş
def _cok_parcali(alanlar: dict, dosya: bytes) -> tuple:
    sinir = uuid.uuid4().hex
    govde = io.BytesIO()
    for ad, deger in alanlar.items():
        govde.write(f'--{sinir}\r\nContent-Disposition: form-data; name="{ad}"\r\n\r\n{deger}\r\n'.encode("utf-8"))
    govde.write(f'--{sinir}\r\nContent-Disposition: form-data; name="gorsel"; filename="kare.jpg"\r\n'
                f"Content-Type: image/jpeg\r\n\r\n".encode() + dosya + b"\r\n")
    govde.write(f"--{sinir}--\r\n".encode())
    return govde.getvalue(), f"multipart/form-data; boundary={sinir}"


def gecis_gonder(port: int, plaka: str, yon: str) -> None:
    alanlar = {"plaka_no": plaka, "kamera_id": KAMERALAR[0 if yon == "giris" else 1][0], "yon": yon,
               "guven_skoru": f"{random.uniform(0.88, 0.99):.3f}", "dogrulama_kare_sayisi": str(random.randint(4, 12)),
               "farkli_okuma_sayisi": "1"}
    govde, tur = _cok_parcali(alanlar, arac_gorseli(plaka, not 7 <= datetime.now().hour < 19, random.random(),
                                                    datetime.now(), alanlar["kamera_id"]))
    istek = urllib.request.Request(f"http://127.0.0.1:{port}/kayitlar/otomatik", data=govde, method="POST",
                                   headers={"Content-Type": tur, "X-PTS-Kamera-Anahtari": KAMERA_ANAHTARI})
    urllib.request.urlopen(istek, timeout=10).read()


def canli_uretici(port: int, havuz: dict, aralik: float) -> None:
    """Sunucu ayağa kalkınca birkaç saniyede bir gerçekçi bir geçiş gönderir."""
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/saglik", timeout=2)
            break
        except OSError:
            time.sleep(1)
    iceride = set()
    while True:
        zar = random.random()
        if zar < 0.08:
            plaka, yon = random.choice(havuz["kara"]), "giris"
        elif zar < 0.25:
            plaka, yon = random.choice(havuz["ziyaretci"]), "giris"
        else:
            plaka = random.choice(havuz["personel"] + havuz["diger"])
            yon = "cikis" if plaka in iceride else "giris"
            (iceride.discard if yon == "cikis" else iceride.add)(plaka)
        try:
            gecis_gonder(port, plaka, yon)
        except OSError as exc:
            print("Canlı geçiş gönderilemedi:", exc, flush=True)
        time.sleep(aralik * random.uniform(0.6, 1.4))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PTS demo ortamı (gerçek sisteme dokunmaz)")
    ap.add_argument("--port", type=int, default=8100)
    ap.add_argument("--marka", default="musteriler/ornek", help="marka klasörü (marka.json + logo)")
    ap.add_argument("--klasor", default=os.path.join(KOK, "demo"))
    ap.add_argument("--sifirla", action="store_true", help="demo verisini silip baştan üret")
    ap.add_argument("--canli-aralik", type=float, default=25, help="canlı geçişler arası ortalama sn (0 = kapalı)")
    ap.add_argument("--yalniz-hazirla", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    demo = os.path.abspath(args.klasor)
    if os.path.abspath(demo) == KOK:
        raise SystemExit("Demo klasörü proje klasörünün kendisi olamaz")
    if args.sifirla and os.path.isdir(demo):
        if os.listdir(demo) and not os.path.exists(os.path.join(demo, "pts_demo.db")):
            raise SystemExit(f"{demo} bir demo klasörü değil (pts_demo.db yok); silinmedi")
        shutil.rmtree(demo)
    _ortami_hazirla(demo, args.marka, args.port)
    sys.path.insert(0, KOK)
    from backend import main as m   # noqa: E402 - ortam değişkenlerinden sonra

    havuz_yolu = os.path.join(demo, "plakalar.json")
    if os.path.exists(havuz_yolu):
        with open(havuz_yolu, encoding="utf-8") as f:
            havuz = json.load(f)
    else:
        print("Demo verisi üretiliyor (bir kez, ~1 dk)...", flush=True)
        havuz = veri_uret(m, demo)
    if args.yalniz_hazirla:
        return 0
    if args.canli_aralik > 0:
        threading.Thread(target=canli_uretici, args=(args.port, havuz, args.canli_aralik), daemon=True).start()
    print(f"\nPTS DEMO: http://127.0.0.1:{args.port}\n"
          f"  demo / Demo12345  (yönetici)   kapi / Kapi12345  (Kapı Modu)\n"
          f"  Veriler: {demo}  (gerçek sisteme dokunulmaz)\n", flush=True)
    from backend import sunucu
    sunucu.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
