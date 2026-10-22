"""PTS tanıtım videosu (2026-10-23): çalışan demoyu gezip ekranı kaydeder.

Önce demo çalışmalı:   python araclar\\demo.py --canli-aralik 8
Sonra:                 python araclar\\demo_video.py [--port 8100] [--cikti demo\\pts-tanitim.mp4]

Gerekenler: playwright (python -m playwright install chromium) ve ffmpeg
(webm -> mp4). Ekranın altında Türkçe açıklamalar ve tıklanan yerde kırmızı
halka görünür; ses yoktur (üzerine anlatım eklenebilir).
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENISLIK, YUKSEKLIK = 1280, 720

_STIL = """
#demoAltyazi{position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:2147483647;
  background:rgba(15,23,42,.88);color:#fff;font:600 22px/1.35 'IBM Plex Sans',system-ui,sans-serif;
  padding:14px 26px;border-radius:14px;max-width:86%;text-align:center;box-shadow:0 8px 30px rgba(0,0,0,.35);
  transition:opacity .35s}
#demoKart{position:fixed;inset:0;z-index:2147483647;display:flex;flex-direction:column;align-items:center;
  justify-content:center;background:linear-gradient(135deg,#0b3b2a,#14213d);color:#fff;text-align:center;
  font-family:'IBM Plex Sans',system-ui,sans-serif;transition:opacity .5s}
#demoKart h1{font-size:46px;margin:0 0 14px;font-weight:700} #demoKart p{font-size:24px;margin:6px;opacity:.9}
#demoHalka{position:fixed;width:46px;height:46px;margin:-23px 0 0 -23px;border:4px solid #ef4444;border-radius:50%;
  z-index:2147483647;pointer-events:none;animation:demoNabiz .6s ease-out}
@keyframes demoNabiz{from{transform:scale(.4);opacity:1}to{transform:scale(1.3);opacity:.2}}
"""


class Kayit:
    def __init__(self, sayfa):
        self.s = sayfa

    def _stil(self):
        self.s.evaluate("""css => { if (!document.getElementById('demoStil')) {
            const st = document.createElement('style'); st.id = 'demoStil'; st.textContent = css;
            document.head.appendChild(st); } }""", _STIL)

    def altyazi(self, metin: str, sure: float = 0):
        self._stil()
        self.s.evaluate("""m => { let a = document.getElementById('demoAltyazi');
            if (!a) { a = document.createElement('div'); a.id = 'demoAltyazi'; document.body.appendChild(a); }
            a.style.opacity = m ? 1 : 0; if (m) a.textContent = m; }""", metin)
        if sure:
            time.sleep(sure)

    def kart(self, baslik: str, satirlar: list, sure: float):
        self._stil()
        self.s.evaluate("""([b, ss]) => { const k = document.createElement('div'); k.id = 'demoKart';
            k.innerHTML = '<h1></h1>' + ss.map(() => '<p></p>').join('');
            k.querySelector('h1').textContent = b; k.querySelectorAll('p').forEach((p, i) => p.textContent = ss[i]);
            document.body.appendChild(k); }""", [baslik, satirlar])
        time.sleep(sure)
        self.s.evaluate("() => { const k = document.getElementById('demoKart'); if (k) { k.style.opacity = 0; setTimeout(() => k.remove(), 500); } }")
        time.sleep(0.6)

    def tikla(self, secici: str, bekle: float = 1.0):
        el = self.s.locator(secici).first
        el.scroll_into_view_if_needed()
        kutu = el.bounding_box()
        if kutu:
            self._stil()
            self.s.evaluate("""([x, y]) => { const h = document.createElement('div'); h.id = 'demoHalka';
                h.style.left = x + 'px'; h.style.top = y + 'px'; document.body.appendChild(h);
                setTimeout(() => h.remove(), 900); }""", [kutu["x"] + kutu["width"] / 2, kutu["y"] + kutu["height"] / 2])
            time.sleep(0.45)
        el.click()
        time.sleep(bekle)

    def yaz(self, secici: str, metin: str):
        el = self.s.locator(secici).first
        el.click()
        el.press_sequentially(metin, delay=70)


def _satir_bekle(s, secici: str, en_az: int = 3):
    try:
        s.wait_for_function("([q, n]) => document.querySelectorAll(q).length >= n", arg=[secici, en_az], timeout=10000)
    except Exception:
        pass
    time.sleep(0.8)


def giris(k: Kayit, kullanici: str, parola: str):
    k.s.wait_for_selector("#authForm", state="visible")
    k.yaz("#authKullanici", kullanici)
    k.yaz("#authParola", parola)
    k.tikla("#authForm button[type=submit]", 2.5)


def senaryo(k: Kayit, adres: str):
    s = k.s
    s.goto(adres)
    s.wait_for_selector("#authForm", state="visible")
    time.sleep(1)
    k.kart("Plaka Tanıma ve Geçiş Kontrol Sistemi",
           ["Kendi sunucunuzda çalışır · Buluta veri göndermez · KVKK'ya uygun",
            "Mevcut IP kameralarınızla, Türk plakasına özel"], 5)

    # --- Kapı görevlisi
    k.altyazi("Kapıdaki görevli için sade ekran: Kapı Modu", 2.5)
    giris(k, "kapi", "Kapi12345")
    s.wait_for_selector("#kapiModu:not(.d-none)")
    k.altyazi("Araç geçtiği anda plaka, kişi, fotoğraf ve yön ekrana gelir", 1)
    ilk = s.locator("#kapiListe [data-kapi-kayit]").first.get_attribute("data-kapi-kayit")
    try:
        s.wait_for_function("id => { const e = document.querySelector('#kapiListe [data-kapi-kayit]'); return e && e.dataset.kapiKayit !== id; }",
                            arg=ilk, timeout=25000)
    except Exception:
        pass
    s.wait_for_function("() => { const i = document.querySelector('#kapiGoruntu img'); return i && i.complete && i.naturalWidth > 0; }",
                        timeout=10000)
    time.sleep(3)
    k.altyazi("Renk kimin geçtiğini söyler: personel, ziyaretçi, alt işveren, kara liste", 4)
    k.altyazi("Tek dokunuşla not: kargo, misafir, teslimat...", 0.5)
    k.tikla("#kapiSonKart .kd-ana", 1.2)
    cip = s.locator("#kapiNotCipler button").first
    if cip.count():
        k.tikla("#kapiNotCipler button >> nth=0", 0.6)
    k.yaz("#kapiNotAlani", " — Yurtiçi Kargo, sürücü Ahmet")
    time.sleep(0.8)
    k.tikla("#kapiNotKaydet", 2)
    k.altyazi("Not kayda işlenir; aynı araç gün içinde tekrar gelirse not hazır gelir", 3.5)

    k.altyazi("İçeride kim var, ne kadar süredir?", 0.3)
    k.tikla("[data-kapi-sekme=iceride]", 0.3)
    _satir_bekle(s, "#kapiIcerideTablo > *")
    time.sleep(3.5)
    k.altyazi("Plaka, isim ya da notla arama; Excel ve PDF rapor", 0.3)
    k.tikla("[data-kapi-sekme=ara]", 1)
    k.yaz("#kapiAramaMetin", "Servis")
    time.sleep(3.5)
    k.tikla("[data-kapi-sekme=kapi]", 2)

    # --- Yönetici
    k.altyazi("Yönetici paneli", 0.3)
    k.tikla("#kapiCikis", 2)
    giris(k, "demo", "Demo12345")
    s.wait_for_selector("#authKapisi.d-none", state="attached")
    k.tikla('button.nav-link[data-bs-target="#kontrol-sekme"]', 1)
    k.altyazi("Kontrol Merkezi: günün özeti, nizamiye durumu, uyarılar", 5)
    k.tikla('button.nav-link[data-bs-target="#kayitlar-sekme"]', 0.3)
    _satir_bekle(s, "#kayitlar-sekme table tbody tr")
    k.altyazi("Tüm geçişler: tarih, kapı, kişi tipi filtreleri; Excel / PDF", 5)
    k.tikla('button.nav-link[data-bs-target="#iceride-sekme"]', 1)
    k.altyazi("İçerideki araçlar ve uzun süredir içeride kalan ziyaretçiler", 4)
    k.tikla('button.nav-link[data-bs-target="#kisiler-sekme"]', 0.3)
    _satir_bekle(s, "#kisiler-sekme table tbody tr")
    k.altyazi("Personel, ziyaretçi, alt işveren, VIP — kişi başına birden çok plaka, Excel'den içe aktarma", 5)
    k.tikla('button.nav-link[data-bs-target="#karaliste-sekme"]', 1)
    k.altyazi("Kara listedeki araç geldiğinde anında alarm, Telegram bildirimi ve LED tabela", 4.5)
    k.tikla('button.nav-link[data-bs-target="#kullanicilar-sekme"]', 1.5)
    k.altyazi("Rol bazlı yetki, iki adımlı doğrulama ve denetim kaydı", 4.5)
    k.altyazi("")
    k.kart("PTS", ["Bariyer · LED tabela · Telegram · Mobil uygulama · Filo (Arvento) entegrasyonu",
                   "Uzaktan izleme ve tek adımda güncelleme",
                   "Demo ve kurulum için bizimle iletişime geçin"], 6)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PTS tanıtım videosu")
    ap.add_argument("--port", type=int, default=8100)
    ap.add_argument("--cikti", default=os.path.join(KOK, "demo", "pts-tanitim.mp4"))
    ap.add_argument("--chromium", help="Chromium yolu (playwright kendi tarayıcısını bulamazsa)")
    args = ap.parse_args(argv)
    from playwright.sync_api import sync_playwright

    gecici = os.path.join(os.path.dirname(os.path.abspath(args.cikti)), "video_gecici")
    shutil.rmtree(gecici, ignore_errors=True)
    with sync_playwright() as p:
        tarayici = p.chromium.launch(executable_path=args.chromium) if args.chromium else p.chromium.launch()
        baglam = tarayici.new_context(viewport={"width": GENISLIK, "height": YUKSEKLIK}, locale="tr-TR",
                                      record_video_dir=gecici, record_video_size={"width": GENISLIK, "height": YUKSEKLIK})
        sayfa = baglam.new_page()
        try:
            senaryo(Kayit(sayfa), f"http://127.0.0.1:{args.port}/")
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
