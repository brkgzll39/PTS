"""PTS lisans aracı (YALNIZCA lisans verenin bilgisayarı için -- kuruluma girmez).

2026-10-20: Lisanslar Ed25519 ile imzalanır. Özel anahtar YALNIZCA bu araçla
oluşturulan dosyada durur; müşteriye giden PTS'te yalnızca açık anahtar vardır
(backend/lisans.py::ACIK_ANAHTAR_HEX) ve onunla lisans üretilemez.

Proje klasöründen (PowerShell):

  1) Bir kez: anahtar çifti oluştur
     .venv\\Scripts\\python.exe araclar\\lisans_araci.py anahtar-olustur
       -> lisans_ozel_anahtar.key dosyası yazılır (GİZLİ: kimseye vermeyin,
          yedeğini USB/kasa gibi güvenli bir yerde tutun; kaybolursa yeni
          lisans üretilemez) ve AÇIK anahtar ekrana basılır (paylaşılabilir).

  2) Her müşteri için lisans üret:
     .venv\\Scripts\\python.exe araclar\\lisans_araci.py uret --musteri "ABC Tesisi" --kamera 4 --gun 365 [--cihaz XXXXXXXXXXXXXXXX]
       --cihaz: müşterinin panelindeki Lisans sekmesinde görünen cihaz kodu
       (lisans yalnızca o bilgisayarda çalışır; önerilir).
"""
import argparse
import os
import secrets
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)

from backend import ed25519, lisans  # noqa: E402

VARSAYILAN_DOSYA = os.path.join(KOK, "lisans_ozel_anahtar.key")


def _ozel_oku(yol: str) -> bytes:
    with open(yol, encoding="ascii") as f:
        return bytes.fromhex(f.read().strip())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PTS lisans aracı (Ed25519)")
    alt = ap.add_subparsers(dest="komut", required=True)
    a = alt.add_parser("anahtar-olustur", help="özel/açık anahtar çifti oluşturur")
    a.add_argument("--dosya", default=VARSAYILAN_DOSYA)
    u = alt.add_parser("uret", help="imzalı lisans üretir")
    u.add_argument("--anahtar", default=VARSAYILAN_DOSYA, help="özel anahtar dosyası")
    u.add_argument("--musteri", required=True)
    u.add_argument("--kamera", type=int, required=True)
    u.add_argument("--gun", type=int, required=True)
    u.add_argument("--cihaz")
    u.add_argument("--modul", action="append", default=None,
                   help="lisansa açılacak modül (tekrarlanabilir; hiç verilmezse TÜM modüller açık): "
                        + ", ".join(lisans.MODULLER))
    alt.add_parser("acik-anahtar", help="özel anahtar dosyasından açık anahtarı gösterir").add_argument(
        "--anahtar", default=VARSAYILAN_DOSYA)
    args = ap.parse_args(argv)

    if args.komut == "anahtar-olustur":
        if os.path.exists(args.dosya):
            print(f"HATA: {args.dosya} zaten var -- üzerine yazılmadı (eski anahtarla üretilen lisanslar geçersiz kalırdı).")
            return 1
        ozel = secrets.token_bytes(32)
        with open(args.dosya, "w", encoding="ascii") as f:
            f.write(ozel.hex())
        print(f"Özel anahtar yazıldı: {args.dosya}  (GİZLİ -- kimseyle paylaşmayın, yedekleyin)")
        print("AÇIK anahtar (bunu gönderin, paylaşılabilir):")
        print(ed25519.acik_anahtar(ozel).hex())
        return 0

    ozel = _ozel_oku(args.anahtar)
    if args.komut == "acik-anahtar":
        print(ed25519.acik_anahtar(ozel).hex())
        return 0
    try:
        anahtar = lisans.imzali_uret(ozel, args.musteri, args.kamera, args.gun, args.cihaz, args.modul)
    except ValueError as exc:
        print(f"HATA: {exc}")
        return 1
    if args.modul is not None:
        print("Modüller: " + ", ".join(f"{m} ({lisans.MODULLER[m]})" for m in sorted(set(args.modul))))
    else:
        print("Modüller: tümü açık")
    if lisans.ACIK_ANAHTAR_HEX and lisans.ACIK_ANAHTAR_HEX != ed25519.acik_anahtar(ozel).hex():
        print("UYARI: bu özel anahtar, PTS'e gömülü açık anahtarla eşleşmiyor -- lisans kabul edilmez!")
    print(anahtar)
    return 0


if __name__ == "__main__":
    sys.exit(main())
