"""Sahte Kapı Kutusu (2026-10-28): donanım gelmeden PTS tarafını denemek için.

Gerçek kutunun (kapi_kutusu/src) PTS'ye gönderdiği olayları aynı biçimde
gönderir ve bariyer "aç" komutunu dinler.

    python kapi_kutusu/araclar/sahte_kutu.py --pts https://127.0.0.1:8000 --anahtar <ANAHTAR>

Sonra:  Enter          -> giriş 1'de araç geçti
        2 + Enter      -> giriş 2'de araç geçti
        b + Enter      -> görevli düğmesi
        q + Enter      -> çıkış
Bariyer adresi olarak http://127.0.0.1:8090/ac?anahtar=<ANAHTAR> verilirse
PTS'nin açma komutu ekrana "BARİYER AÇILDI" diye düşer.
"""
import argparse
import hmac
import json
import random
import ssl
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SURUM = "sahte-1.0"


class Kutu:
    def __init__(self, pts: str, anahtar: str, ad: str):
        self.pts, self.anahtar, self.ad = pts.rstrip("/"), anahtar, ad
        self.acilis = random.randint(1, 2**31)
        self.sira = 0
        self.kuyruk = []  # (sira, tur, giris, durum, zaman, kaynak)
        self.kilit = threading.Lock()
        self.baslangic = time.monotonic()

    def ms(self) -> int:
        return int((time.monotonic() - self.baslangic) * 1000)

    def olay(self, tur: str, giris: int, durum: bool = True, kaynak: str = None) -> None:
        with self.kilit:
            self.sira += 1
            self.kuyruk.append((self.sira, tur, giris, durum, self.ms(), kaynak))

    def gonder(self) -> None:
        with self.kilit:
            paket = self.kuyruk[:20]
        simdi = self.ms()
        olaylar = [{"sira": s, "tur": t, "giris": g, "durum": "var" if d else "yok", "once_ms": simdi - z,
                    **({"kaynak": k} if k else {})} for s, t, g, d, z, k in paket]
        govde = json.dumps({"kutu": self.ad, "surum": SURUM, "acilis": self.acilis, "calisma_ms": simdi,
                            "dusen": 0, "girisler": 0, "olaylar": olaylar}).encode()
        istek = urllib.request.Request(self.pts + "/kapi-kutusu/olay", data=govde, method="POST",
                                       headers={"Content-Type": "application/json", "X-Kutu-Anahtar": self.anahtar})
        baglam = ssl._create_unverified_context()  # yerel deneme aracı
        try:
            with urllib.request.urlopen(istek, timeout=4, context=baglam):
                pass
        except Exception as exc:
            print(f"  ! PTS'ye gönderilemedi: {exc}")
            return
        with self.kilit:
            son = paket[-1][0] if paket else 0
            self.kuyruk = [o for o in self.kuyruk if o[0] > son]
        if paket:
            print(f"  → {len(paket)} olay gönderildi")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sahte PTS Kapı Kutusu")
    ap.add_argument("--pts", required=True, help="PTS adresi, ör. https://127.0.0.1:8000")
    ap.add_argument("--anahtar", required=True, help="PTS → Bariyer → Kapı Kutuları ekranındaki anahtar")
    ap.add_argument("--ad", default="Sahte Kutu")
    ap.add_argument("--port", type=int, default=8090, help="bariyer komutunu dinleyen port")
    args = ap.parse_args(argv)
    kutu = Kutu(args.pts, args.anahtar, args.ad)

    class Isleyici(BaseHTTPRequestHandler):
        def _ac(self):
            sorgu = parse_qs(urlparse(self.path).query)
            gelen = self.headers.get("X-Kutu-Anahtar") or (sorgu.get("anahtar") or [""])[0]
            if urlparse(self.path).path != "/ac":
                self.send_response(404)
            elif not hmac.compare_digest(gelen.encode(), args.anahtar.encode()):
                self.send_response(401)
            else:
                role = int((sorgu.get("role") or ["1"])[0])
                print(f"\n  ■ BARİYER AÇILDI (röle {role})")
                kutu.olay("acma", role, True, "pts")
                self.send_response(200)
            self.end_headers()

        do_GET = do_POST = _ac

        def log_message(self, *a):
            pass

    sunucu = ThreadingHTTPServer(("0.0.0.0", args.port), Isleyici)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()

    def gonderici():
        son = 0.0
        while True:
            time.sleep(0.2)
            if kutu.kuyruk or time.monotonic() - son > 30:
                kutu.gonder()
                son = time.monotonic()

    threading.Thread(target=gonderici, daemon=True).start()
    print(f"Sahte kutu hazır. Bariyer adresi: http://127.0.0.1:{args.port}/ac?anahtar={args.anahtar}")
    print("Enter: giriş 1'de araç · 2..8: o girişte araç · b: görevli düğmesi · q: çıkış")
    for satir in sys.stdin:
        komut = satir.strip().lower()
        if komut == "q":
            break
        if komut == "b":
            kutu.olay("buton", 8, True)
            kutu.olay("acma", 1, True, "buton")
            print("  ■ Görevli düğmesi: bariyer yerelde açıldı")
            continue
        giris = int(komut) if komut.isdigit() and 1 <= int(komut) <= 8 else 1
        kutu.olay("giris", giris, True)
        time.sleep(0.4)
        kutu.olay("giris", giris, False)
        print(f"  • Giriş {giris}: araç geçti")
    sunucu.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
