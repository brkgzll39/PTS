"""PTS lisans üretici aracı.

Örnek:
  python lisans_uretici.py --musteri "ABC Site" --kamera 8 --gun 365

Üretim ortamında PTS_LICENSE_SECRET ortam değişkenini lisans sunucusunda
ve doğrulama yapan uygulamada aynı, güçlü değerle ayarlayın.

İmzalama/doğrulama mantığının kendisi backend/lisans.py içindedir — bu dosya
sadece o modülün ince bir komut satırı arayüzüdür (main.py da aynı modülü
kullanır, böylece iki taraf birbirinden asla sapmaz).
"""
import argparse

try:
    from backend import lisans  # proje kökünden çalıştırılınca
except ImportError:
    import lisans  # backend/ içinden doğrudan çalıştırılınca


def lisans_uret(musteri: str, kamera_limiti: int, gun: int, cihaz_kodu: str | None = None) -> str:
    return lisans.uret(musteri, kamera_limiti, gun, cihaz_kodu)


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