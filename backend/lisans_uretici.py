"""PTS lisans üretici aracı.

Örnek:
  python lisans_uretici.py --musteri "ABC Site" --kamera 8 --gun 365

Üretim ortamında PTS_LICENSE_SECRET ortam değişkenini lisans sunucusunda
ve doğrulama yapan uygulamada aynı, güçlü değerle ayarlayın.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import date, timedelta


def _b64(veri: bytes) -> str:
    return base64.urlsafe_b64encode(veri).decode("ascii").rstrip("=")


def lisans_uret(musteri: str, kamera_limiti: int, gun: int, cihaz_kodu: str | None = None) -> str:
    if kamera_limiti < 1 or gun < 1:
        raise ValueError("Kamera limiti ve gün sayısı 1 veya daha büyük olmalıdır")
    payload = {
        "lisans_id": secrets.token_hex(8).upper(),
        "musteri": musteri.strip(),
        "cihaz_kodu": cihaz_kodu.strip().upper() if cihaz_kodu else None,
        "kamera_limiti": kamera_limiti,
        "baslangic_tarihi": date.today().isoformat(),
        "bitis_tarihi": (date.today() + timedelta(days=gun)).isoformat(),
    }
    govde = _b64(json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))
    secret = os.getenv("PTS_LICENSE_SECRET", "gelistirme-lisans-anahtari-degistir")
    imza = _b64(hmac.new(secret.encode("utf-8"), govde.encode("ascii"), hashlib.sha256).digest())
    return f"PTS1.{govde}.{imza}"


def main() -> None:
    parser = argparse.ArgumentParser(description="İmzalı PTS lisans anahtarı üretir")
    parser.add_argument("--musteri", required=True, help="Müşteri veya tesis adı")
    parser.add_argument("--kamera", type=int, default=2, help="İzin verilen kamera sayısı")
    parser.add_argument("--gun", type=int, default=365, help="Lisans süresi")
    parser.add_argument("--cihaz", help="İsteğe bağlı 16 haneli cihaz kodu")
    args = parser.parse_args()
    print(lisans_uret(args.musteri, args.kamera, args.gun, args.cihaz))


if __name__ == "__main__":
    main()