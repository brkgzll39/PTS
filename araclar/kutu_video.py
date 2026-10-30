"""Kapı Kutusu kurulum videosu (2026-10-30): kurulum çizimleri + PTS'de kutunun
eklenmesi + okunamayan geçişin görevliye düşmesi.

Önce demo çalışmalı:   python araclar\\demo.py --canli-aralik 0
Sonra:                 python araclar\\kutu_video.py [--port 8100] [--cikti demo\\kapi-kutusu-kurulum.mp4]

Kutu donanımı gerekmez: kutunun PTS'ye gönderdiği olaylar, gerçek kutunun
gönderdiği biçimde (kapi_kutusu/src/mantik.cpp::olayJson) bu betikten gönderilir.
"""
import argparse
import importlib.util
import json
import os
import pathlib
import random
import shutil
import subprocess
import sys
import time
import urllib.request

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("demo_video", os.path.join(KOK, "araclar", "demo_video.py"))
dv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dv)


class SahteKutu:
    """Gerçek kutunun POST /kapi-kutusu/olay gövdesini gönderir."""

    def __init__(self, adres: str, anahtar: str):
        self.adres, self.anahtar = adres.rstrip("/"), anahtar
        self.acilis, self.sira = random.randint(1, 2**31), 0

    def gonder(self, olaylar: list) -> None:
        govde = {"kutu": "Ana Kapı Kutusu", "surum": "1.1.0", "acilis": self.acilis, "calisma_ms": 60000,
                 "dusen": 0, "girisler": 0, "olaylar": olaylar}
        istek = urllib.request.Request(self.adres + "/kapi-kutusu/olay", data=json.dumps(govde).encode(), method="POST",
                                       headers={"Content-Type": "application/json", "X-Kutu-Anahtar": self.anahtar})
        with urllib.request.urlopen(istek, timeout=5):
            pass

    def kalp(self) -> None:
        self.gonder([])

    def arac_gecti(self, giris: int = 1, once_ms: int = 0) -> None:
        self.sira += 1
        self.gonder([{"sira": self.sira, "tur": "giris", "giris": giris, "durum": "var", "once_ms": once_ms}])


_VURGU_CSS = """
.sayfa { max-width: 1140px !important; }
.cizim svg.adim-modu [data-adim] { opacity: .12; transition: opacity .35s, stroke-width .35s; }
.cizim svg.adim-modu [data-adim].adim-aktif { opacity: 1; stroke-width: 5; stroke-dasharray: 12 7;
  animation: kablo-akis .7s linear infinite; }
@keyframes kablo-akis { to { stroke-dashoffset: -19; } }
"""

# Pano bağlantıları, adım adım (kurulum.html'deki data-adim numaraları).
_BAGLANTI_ADIMLARI = [
    (1, "1 · 220V'u güç kaynağının girişine elektrikçi bağlar: sigortalı hattan", 6),
    (2, "2 · Güç kaynağı +V → kartın 12V ucu · −V → kartın GND ucu. Kart 12V ister: 24V vermeyin", 7),
    (3, "3 · Aynı +V ve −V'den loop dedektörünün +12V ve GND uçları beslenir", 6),
    (4, "4 · Asfalttaki döngünün iki ucu, burulmuş olarak, dedektörün L1 ve L2 uçlarına", 6),
    (5, "5 · Dedektörün rölesi: COM → kartın GND'si · NO → kartın IN1 girişi. Araç varken kontak kapanır", 7),
    (6, "6 · İsteğe bağlı görevli düğmesi: bir ucu IN8'e, diğer ucu GND'ye", 6),
    (7, "7 · Kartın Röle 1 COM ve NO uçları → bariyer kartının COM ve START (aç) girişleri", 7),
    (0, "8 · Fotosel kutuya değil, doğrudan bariyer kartının güvenlik girişine bağlanır", 6),
    (9, "9 · Kart → ağ anahtarı, Cat6 kablo. Kutu PTS'ye buradan ulaşır", 6),
]


def _bolume_git(k: "dv.Kayit", secici: str, blok: str = "start") -> None:
    k.s.evaluate("([q, b]) => document.querySelector(q).scrollIntoView({behavior: 'smooth', block: b})", [secici, blok])
    time.sleep(1.3)


def _adim_vurgula(k: "dv.Kayit", adim) -> None:
    k.s.evaluate("""a => { const svg = document.querySelector('#b4').closest('section').querySelector('svg');
        svg.classList.toggle('adim-modu', a !== null);
        svg.querySelectorAll('[data-adim]').forEach(el => el.classList.toggle('adim-aktif', el.dataset.adim === String(a))); }""",
                 adim)


def kurulum_cizimleri(k: "dv.Kayit") -> None:
    s = k.s
    s.goto(pathlib.Path(KOK, "kapi_kutusu", "kurulum.html").as_uri())
    s.add_style_tag(content=_VURGU_CSS)
    time.sleep(1.5)
    k.kart("PTS Kapı Kutusu · Kurulum", ["Döngü, dedektör ve kutunun bağlanması, adım adım",
                                         "Kart: KinCony KC868-A8 · 12V"], 5)
    _bolume_git(k, "#b1")
    k.altyazi("Döngü aracı algılar, kutu PTS'ye “araç geçti” der; kamera okumadıysa görevliye düşer", 6)
    _bolume_git(k, "#b2")
    k.altyazi("Bir şerit için gerekenler: kart, 12V loop dedektörü, loop kablosu, 12V güç kaynağı, IP65 pano", 6)

    # Döngü
    _bolume_git(k, "#b3")
    k.altyazi("Döngü, kameranın plakayı okuduğu noktanın altına döşenir", 4.5)
    k.altyazi("Şeridin iki yanından 30–50 cm içeride, yol yönünde 1,5–2 m; köşeler 45° kesilir", 5.5)
    s.evaluate("() => document.querySelector('#b3').closest('section').querySelectorAll('figure')[1].scrollIntoView({behavior:'smooth', block:'center'})")
    time.sleep(1.3)
    k.altyazi("Kanal 3–5 cm derin; kabloyu 3 tur sarın, üstünü bitüm ya da epoksiyle kapatın", 5.5)
    k.altyazi("Döngüden panoya giden iki uç metre başına en az 20 kez burulur ve kısa tutulur", 5)

    # Pano bağlantıları
    _bolume_git(k, "#b4")
    s.evaluate("() => { const svg = document.querySelector('#b4').closest('section').querySelector('svg');"
               " window.scrollTo({top: svg.getBoundingClientRect().top + window.scrollY - 12, behavior: 'smooth'}); }")
    time.sleep(1.3)
    k.altyazi("Panonun içi: kırmızı +12V, koyu GND, mavi sinyal, turuncu bariyer ve döngü", 5)
    for adim, metin, sure in _BAGLANTI_ADIMLARI:
        _adim_vurgula(k, adim)
        k.altyazi(metin, sure)
    _adim_vurgula(k, None)
    k.altyazi("Dedektörü “varlık (presence)” moduna alın: araç döngünün üstündeyken röle çekili kalsın", 5.5)

    # Yazılım ve deneme
    _bolume_git(k, "#b5")
    k.altyazi("Yazılım: GitHub'dan indirilen tam.bin, Flash Download Tool ile 0x0 adresine bir kez yazılır", 6)
    k.altyazi("Sonra kutunun sayfası (http://kutu-ip/): parola, PTS adresi ve kutu anahtarı", 5)
    _bolume_git(k, "#b6")
    k.altyazi("Sahaya çıkmadan: IN1 ile GND'ye kabloyla dokunun, kutu sayfasında giriş 1 yanar", 5.5)
    k.altyazi("~30 sn sonra PTS'de “okunamayan geçiş” çıkar: sinyal kutudan PTS'ye kadar gidiyor", 5.5)
    k.altyazi("")


def pts_tarafi(k: "dv.Kayit", adres: str) -> None:
    s = k.s
    s.goto(adres)
    dv.giris(k, "demo", "Demo12345")
    s.wait_for_selector("#authKapisi.d-none", state="attached")
    time.sleep(1)
    k.altyazi("PTS'de kutuyu tanıtın: Bariyer → Kapı Kutuları → Yeni kutu", 0.5)
    k.tikla('button.nav-link[data-bs-target="#bariyer-sekme"]', 1.2)
    s.locator("text=Kapı Kutuları").first.scroll_into_view_if_needed()
    time.sleep(1)
    k.tikla("#bariyer-sekme button:has-text('Yeni kutu')", 1.2)
    k.yaz("#kkAd", "Ana Kapı Kutusu")
    k.altyazi("Giriş 1 = çıkış şeridinin döngüsü; şeridin kamerasıyla eşleyin", 0.5)
    s.select_option('[data-kk-kamera="1"]', "Ana Kapı Çıkış")
    time.sleep(0.6)
    s.select_option('[data-kk-yon="1"]', "cikis")
    time.sleep(1.5)
    k.tikla("#kapiKutusuModal .modal-footer .btn-primary", 2)
    k.altyazi("PTS adresi ve kutu anahtarı kutunun kendi web sayfasına yazılır", 5)
    anahtar = s.evaluate("_kapiKutulari[0].anahtar")
    kutu = SahteKutu(adres, anahtar)
    kutu.kalp()
    s.keyboard.press("Escape")
    time.sleep(0.8)
    s.evaluate("kapiKutulariniYukle()")
    time.sleep(1)
    s.locator("#kapiKutusuTablo").scroll_into_view_if_needed()
    k.altyazi("Kutu ağa bağlanınca PTS'de “Çevrimiçi” görünür", 4)

    # Görevli
    k.tikla("#cikisButonu", 2)
    dv.giris(k, "kapi", "Kapi12345")
    s.wait_for_selector("#kapiModu:not(.d-none)")
    time.sleep(1.5)
    if s.locator("#nobetOkunmamisModal.show").count():
        s.click("#nobetOkunmamisModal .modal-footer button")
        time.sleep(1)
    k.altyazi("Bir araç çıkış şeridinden geçti; döngü gördü, kamera plakayı okuyamadı", 1)
    # 40 sn önceki geçiş: eşleşme beklemesi (25 sn) videoda beklenmesin diye.
    kutu.arac_gecti(1, once_ms=40000)
    try:
        s.wait_for_function("() => { const a = document.querySelector('#kapiSekme_kapi .okunamayan-alan:not([data-klon])');"
                            " return a && !a.classList.contains('d-none'); }", timeout=40000, polling=1000)
    except Exception:
        s.evaluate("okunamayanlariYukle()")
    time.sleep(1)
    k.altyazi("Görevlinin ekranına “okunamayan geçiş” düşer", 4)
    k.altyazi("Görevli plakayı geçiş anının fotoğrafından yazar", 0.3)
    k.yaz("#kapiSekme_kapi .okunamayan-form input", "34 KTU 55")
    time.sleep(0.8)
    k.tikla("#kapiSekme_kapi .okunamayan-form button[type=submit]", 2)
    k.altyazi("Geçiş, olduğu saatle kayda işlenir; araç artık “içeride” kalmaz", 4.5)
    k.altyazi("")
    k.kart("PTS Kapı Kutusu", ["Hiçbir geçiş kaybolmaz · Bariyer PTS'den ya da görevli düğmesiyle açılır",
                               "Ağ koparsa biriktirir · Ağdan güncellenir",
                               "Kurulum rehberi: kapi_kutusu/README.md"], 6)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kapı Kutusu kurulum videosu")
    ap.add_argument("--port", type=int, default=8100)
    ap.add_argument("--cikti", default=os.path.join(KOK, "demo", "kapi-kutusu-kurulum.mp4"))
    ap.add_argument("--chromium", help="Chromium yolu (playwright kendi tarayıcısını bulamazsa)")
    args = ap.parse_args(argv)
    from playwright.sync_api import sync_playwright

    os.makedirs(os.path.dirname(os.path.abspath(args.cikti)), exist_ok=True)
    gecici = os.path.join(os.path.dirname(os.path.abspath(args.cikti)), "video_gecici_kutu")
    shutil.rmtree(gecici, ignore_errors=True)
    with sync_playwright() as p:
        tarayici = p.chromium.launch(executable_path=args.chromium) if args.chromium else p.chromium.launch()
        baglam = tarayici.new_context(viewport={"width": dv.GENISLIK, "height": dv.YUKSEKLIK}, locale="tr-TR",
                                      record_video_dir=gecici, record_video_size={"width": dv.GENISLIK, "height": dv.YUKSEKLIK})
        sayfa = baglam.new_page()
        try:
            k = dv.Kayit(sayfa)
            kurulum_cizimleri(k)
            pts_tarafi(k, f"http://127.0.0.1:{args.port}/")
        finally:
            video = sayfa.video.path()
            baglam.close()
            tarayici.close()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        hedef = os.path.splitext(args.cikti)[0] + ".webm"
        shutil.move(video, hedef)
        print("ffmpeg yok; video webm olarak kaydedildi:", hedef)
        return 0
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", video, "-c:v", "libx264", "-preset", "slow", "-crf", "22",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", args.cikti], check=True)
    shutil.rmtree(gecici, ignore_errors=True)
    print("Video hazır:", args.cikti)
    return 0


if __name__ == "__main__":
    sys.exit(main())
