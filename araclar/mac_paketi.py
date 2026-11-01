"""Mac paketi: `python araclar/mac_paketi.py [çıktı.zip]` (2026-11-01).

Depoda izlenen dosyalardan (sırlar ve yerel veri girmez) PTS-Mac.zip üretir;
mac/ klasöründeki .command betikleri zip'in köküne çalıştırılabilir olarak konur.
Kurulum Mac'te: 1-Kurulum.command (bkz. mac/OKU-BENI.txt)."""
import os
import subprocess
import sys
import zipfile

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICERIK = ["backend", "frontend", "araclar", "musteriler", "pts_baslat.py", "README.md", ".env.example"]


def main(cikti: str) -> None:
    os.chdir(KOK)
    dosyalar = [d for d in subprocess.check_output(["git", "ls-files", *ICERIK], text=True).split() if os.path.isfile(d)]
    with zipfile.ZipFile(cikti, "w", zipfile.ZIP_DEFLATED) as z:
        def ekle(yol, hedef, calistirilir=False):
            bilgi = zipfile.ZipInfo(hedef)
            bilgi.compress_type = zipfile.ZIP_DEFLATED
            bilgi.external_attr = ((0o100755 if calistirilir else 0o100644) & 0xFFFF) << 16
            with open(yol, "rb") as f:
                z.writestr(bilgi, f.read())
        for d in dosyalar:
            ekle(d, "PTS-Mac/" + d)
        for d in sorted(os.listdir("mac")):
            ekle(os.path.join("mac", d), "PTS-Mac/" + d, d.endswith(".command"))
    print(f"{cikti}: {len(dosyalar)} dosya")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "PTS-Mac.zip")
