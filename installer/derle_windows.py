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

Kullanım: python installer/derle_windows.py --cikti derlenmis [--test-anahtarsiz]
"""
import argparse
import glob
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--test-anahtarsiz", action="store_true")
    args = ap.parse_args(argv)
    cikti = os.path.abspath(args.cikti)
    if os.path.exists(cikti):
        shutil.rmtree(cikti)
    os.makedirs(cikti)
    backend_derle(cikti, args.test_anahtarsiz)
    frontend_hazirla(cikti)
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
