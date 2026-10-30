"""Müşteriye giden DERLENMİŞ PTS paketini hazırlar (2026-10-20).

Kullanıcı isteği: "kurulum yaptığım kişilerin py dosyalarım dahil kaynak
kodların hiçbirine erişimi olmaması gerekiyor".

  * backend/ paketi Nuitka ile TEK bir derlenmiş modüle (backend.*.pyd)
    çevrilir; pakete hiçbir .py dosyası girmez. Docstring'ler de çıkarılır.
  * Lisans: eski (PTS1/HMAC) lisanslar kapatılır (lisans.ESKI_LISANS_KABUL =
    False) ve lisans üretme aracı pakete girmez. Açık anahtar tanımlı değilse
    derleme durur (--test-anahtarsiz yalnızca deneme derlemesi içindir).
  * frontend/: JavaScript küçültülüp yerel adlar karıştırılır (terser), HTML/CSS
    yorumları silinir. Tarayıcıda çalışan kod her zaman indirilebilir; amaç
    okunmasını zorlaştırmak.

Windows'ta çalışır (GitHub Actions: .github/workflows/derle-windows.yml);
Nuitka ve MSVC gerekir, terser için Node.js (npx).

  * Marka (2026-10-23): pakete her zaman bir marka.json girer (--marka ile
    verilen müşteri klasöründen; verilmezse kurumsuz "{}") ve frontend'den
    TPAO adı/logosu/iletişim bilgisi silinir. İz kalırsa derleme durur.

Kullanım: python installer/derle_windows.py --cikti derlenmis [--test-anahtarsiz]
          [--marka musteriler/acme]   (klasörde marka.json + logo dosyası)
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TERSER = "terser@5.31.0"
NUITKA_DISI = ("lisans_uretici.py",)  # lisans verenin aracı: müşteriye gitmez
KOK_DOSYALARI = ("calistir.bat", "kurulum.bat", "guvenlik_duvari.ps1", ".env.example", "pts_baslat.py")


def _calistir(komut, **kw):
    print("+", " ".join(komut), flush=True)
    subprocess.run(komut, check=True, **kw)


def lisansi_hazirla(backend_dizini: str, test_anahtarsiz: bool) -> None:
    yol = os.path.join(backend_dizini, "lisans.py")
    with open(yol, encoding="utf-8") as f:
        s = f.read()
    s, n = re.subn(r"^ESKI_LISANS_KABUL = True$", "ESKI_LISANS_KABUL = False", s, flags=re.M)
    if n != 1:
        raise SystemExit("HATA: lisans.py içinde 'ESKI_LISANS_KABUL = True' satırı bulunamadı")
    acik = re.search(r'^ACIK_ANAHTAR_HEX = "([0-9a-f]*)"$', s, flags=re.M)
    if not acik:
        raise SystemExit("HATA: lisans.py içinde ACIK_ANAHTAR_HEX satırı bulunamadı")
    if len(acik.group(1)) != 64:
        if not test_anahtarsiz:
            raise SystemExit("HATA: lisans.ACIK_ANAHTAR_HEX boş -- müşteri paketi lisans doğrulayamaz. "
                             "Deneme derlemesi için --test-anahtarsiz.")
        print("UYARI: açık anahtar yok -- bu paket MÜŞTERİYE VERİLEMEZ (lisans kabul etmez).")
    with open(yol, "w", encoding="utf-8") as f:
        f.write(s)


def backend_derle(cikti: str, test_anahtarsiz: bool) -> None:
    calisma = os.path.join(cikti, "_derleme")
    paket = os.path.join(calisma, "backend")
    shutil.copytree(os.path.join(KOK, "backend"), paket,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", *NUITKA_DISI))
    lisansi_hazirla(paket, test_anahtarsiz)
    _calistir([
        sys.executable, "-m", "nuitka", "--module", "backend", "--include-package=backend",
        "--python-flag=no_docstrings", "--python-flag=no_asserts",
        "--output-dir=" + calisma, "--remove-output", "--assume-yes-for-downloads",
    ], cwd=calisma)
    pydler = glob.glob(os.path.join(calisma, "backend.*.pyd"))
    if len(pydler) != 1:
        raise SystemExit(f"HATA: derlenmiş modül bulunamadı: {pydler}")
    shutil.move(pydler[0], cikti)
    # Veri dosyaları (fontlar, bağımlılık listesi) backend\ klasöründe kalır;
    # klasörde __init__.py OLMADIĞI için Python 'backend'i .pyd'den yükler.
    hedef = os.path.join(cikti, "backend")
    shutil.copytree(os.path.join(paket, "fonts"), os.path.join(hedef, "fonts"))
    shutil.copy2(os.path.join(paket, "requirements-windows.txt"), hedef)
    shutil.copy2(os.path.join(paket, "kilavuz_icerik.html"), hedef)  # kullanım kılavuzu metni (main.py::kilavuz_icerik)
    shutil.rmtree(calisma)


def _css_html_yorumsuz(yol: str, desen: str) -> None:
    with open(yol, encoding="utf-8") as f:
        s = f.read()
    s = re.sub(desen, "", s, flags=re.S)
    s = re.sub(r"\n\s*\n+", "\n", s)
    with open(yol, "w", encoding="utf-8") as f:
        f.write(s)


def frontend_hazirla(cikti: str) -> None:
    hedef = os.path.join(cikti, "frontend")
    shutil.copytree(os.path.join(KOK, "frontend"), hedef)
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        raise SystemExit("HATA: npx (Node.js) bulunamadı")
    vendor = os.path.join(hedef, "vendor") + os.sep
    kendi = lambda desen: [p for p in glob.glob(os.path.join(hedef, "**", desen), recursive=True)
                           if not p.startswith(vendor)]  # kütüphaneler zaten küçük; lisans başlıkları kalsın
    for js in kendi("*.js"):
        # Üst düzey fonksiyon adları KARIŞTIRILMAZ: index.html'deki onclick="..."
        # bunları adıyla çağırır. Yerel değişkenler ve yorumlar gider.
        _calistir([npx, "--yes", TERSER, js, "--compress", "--mangle", "--comments", "false", "-o", js])
    for css in kendi("*.css"):
        _css_html_yorumsuz(css, r"/\*.*?\*/")
    for html in kendi("*.html"):
        _css_html_yorumsuz(html, r"<!--.*?-->")


# Müşteri paketinin frontend'inde TPAO'ya ait metinlerin yerine geçenler.
# Asıl değerler açılışta /marka'dan (marka.json) gelir; bunlar yalnız ilk
# boyamada ve JavaScript'siz görünümde kalır.
_TPAO_DEGISIMLERI = [
    ("/static/img/tpao-logo.png", "/marka/logo"),
    ("TÜRKİYE PETROLLERİ ANONİM ORTAKLIĞI", "PLAKA TANIMA SİSTEMİ"),
    ("Türkiye Petrolleri Anonim Ortaklığı", "PTS"),
    ('alt="TPAO"', 'alt="PTS"'),
    ("TPAO - Plaka Tanıma Sistemi", "PTS - Plaka Tanıma Sistemi"),
    ("TPAO PTS", "PTS"),
    ('href="tel:+905372102313"', 'href="tel:"'),
    ("0537 210 2313", ""),
    ("0288 427 4864", ""),
    ("mailto:bguzelel@tpao.gov.tr", "mailto:"),
    ("bguzelel@tpao.gov.tr", ""),
    ('placeholder="T.P.A.O."', 'placeholder="HOŞ GELDİNİZ"'),
    ('placeholder="TRAKYA"', 'placeholder=""'),
]
_TPAO_IZI = re.compile(r"TPAO|tpao|T\.P\.A\.O|PETROLLER|Petroller|TRAKYA|Trakya|0537 210|bguzelel")


def tpao_izlerini_temizle(frontend_dizini: str) -> None:
    """Müşteri paketinin frontend'inden TPAO'ya ait ad/logo/iletişim bilgisini
    siler; iz kalırsa SystemExit (yanlışlıkla başka kuruma gitmesin)."""
    logo = os.path.join(frontend_dizini, "img", "tpao-logo.png")
    if os.path.exists(logo):
        os.remove(logo)
    vendor = os.path.join(frontend_dizini, "vendor") + os.sep
    kalan = []
    for yol in glob.glob(os.path.join(frontend_dizini, "**", "*"), recursive=True):
        if yol.startswith(vendor) or not yol.endswith((".html", ".js", ".css", ".json")):
            continue
        with open(yol, encoding="utf-8") as f:
            metin = f.read()
        yeni = metin
        for eski, karsilik in _TPAO_DEGISIMLERI:
            yeni = yeni.replace(eski, karsilik)
        if os.path.basename(yol) == "sw.js":
            yeni = yeni.replace('"/marka/logo",', '"/static/img/pts-logo.svg",')
        if yeni != metin:
            with open(yol, "w", encoding="utf-8") as f:
                f.write(yeni)
        kalan += [f"{os.path.relpath(yol, frontend_dizini)}:{n}" for n, satir in enumerate(yeni.splitlines(), 1)
                  if _TPAO_IZI.search(satir)]
    if kalan:
        raise SystemExit("HATA: müşteri paketinde TPAO izi kaldı: " + ", ".join(kalan[:20]))


def marka_kopyala(cikti: str, marka_klasoru) -> None:
    """Müşterinin marka.json'u (+ logo) pakete; yoksa kurumsuz "{}"."""
    hedef = os.path.join(cikti, "marka.json")
    if not marka_klasoru:
        with open(hedef, "w", encoding="utf-8") as f:
            f.write("{}\n")
        return
    kaynak = os.path.join(marka_klasoru, "marka.json")
    if not os.path.isfile(kaynak):
        raise SystemExit(f"HATA: {kaynak} yok")
    with open(kaynak, encoding="utf-8") as f:
        ayar = json.load(f)
    shutil.copy2(kaynak, hedef)
    if ayar.get("logo_dosyasi"):
        logo = os.path.join(marka_klasoru, ayar["logo_dosyasi"])
        if not os.path.isfile(logo):
            raise SystemExit(f"HATA: logo dosyası yok: {logo}")
        shutil.copy2(logo, os.path.join(cikti, ayar["logo_dosyasi"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--test-anahtarsiz", action="store_true")
    ap.add_argument("--marka", help="müşteri klasörü (marka.json + logo); verilmezse kurumsuz")
    args = ap.parse_args(argv)
    cikti = os.path.abspath(args.cikti)
    if os.path.exists(cikti):
        shutil.rmtree(cikti)
    os.makedirs(cikti)
    backend_derle(cikti, args.test_anahtarsiz)
    frontend_hazirla(cikti)
    tpao_izlerini_temizle(os.path.join(cikti, "frontend"))
    marka_kopyala(cikti, args.marka)
    for ad in KOK_DOSYALARI:
        shutil.copy2(os.path.join(KOK, ad), cikti)
    kalan = [p for p in glob.glob(os.path.join(cikti, "**", "*.py"), recursive=True)
             if os.path.basename(p) != "pts_baslat.py"]
    if kalan:
        raise SystemExit(f"HATA: pakette kaynak dosya kaldı: {kalan}")
    print("Derlenmiş paket hazır:", cikti)
    return 0


if __name__ == "__main__":
    sys.exit(main())
