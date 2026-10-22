"""PTS paneli için HTTPS sertifikası üretir (2026-10-22).

Kullanıcı bildirimi: panel http:// ile açıldığı için Chrome/Edge Excel
indirmesini "Güvenli olmayan indirme işlemi engellendi" diye durduruyor;
kurum bilgisayarlarında tarayıcı ilkesi (kayıt defteri) de yazılamıyor.

Çözüm: PTS'e özel küçük bir sertifika yetkilisi (CA) ve bu CA'nın imzaladığı
sunucu sertifikası. CA sertifikası (pts-ca.crt) panelin açıldığı her
bilgisayara KULLANICI deposuna bir kez yüklenir (yönetici yetkisi gerekmez);
sonra https://<sunucu>:8000 kilitli, "güvenli" görünür ve indirmeler engellenmez.

KULLANIM (proje klasöründen, PowerShell):
  .venv\\Scripts\\python.exe -m backend.sertifika_olustur
      sertifika\\ klasörüne pts-ca.crt (dağıtılacak), sunucu.crt, sunucu.key
      (GİZLİ) ve CA anahtarı yazar. Sunucunun IP'leri otomatik bulunur.
  --ip 172.17.1.254 --ip 100.64.0.5     IP'leri elle ver (tekrarlanabilir;
                                        Tailscale IP'sini de ekleyin)
  --ad pts.kurum.local                  ek alan adı (tekrarlanabilir)

Sunucu sertifikası yenilenirken CA KORUNUR (bilgisayarlara yeniden yüklemek
gerekmez). .env'e PTS_HTTPS=1 yazıp PTS'i yeniden başlatınca panel HTTPS olur.
"""
import argparse
import datetime
import ipaddress
import os
import socket
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KLASOR = os.path.join(KOK, "sertifika")


def _yerel_ipler() -> list:
    ipler = {"127.0.0.1"}
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            ipler.add(ip)
    except OSError:
        pass
    try:  # varsayılan ağ arayüzünün IP'si (paket gönderilmez)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ipler.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ip for ip in ipler if not ip.startswith("169.254."))


def _yaz(yol: str, veri: bytes, gizli: bool = False) -> None:
    with open(yol, "wb") as f:
        f.write(veri)
    if gizli:
        try:
            os.chmod(yol, 0o600)
        except OSError:
            pass


def olustur(klasor: str, ipler: list, adlar: list) -> dict:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    os.makedirs(klasor, exist_ok=True)
    simdi = datetime.datetime.now(datetime.timezone.utc)
    ca_key_yol = os.path.join(klasor, "pts-ca.key")
    ca_crt_yol = os.path.join(klasor, "pts-ca.crt")
    pem = serialization.Encoding.PEM

    if os.path.exists(ca_key_yol) and os.path.exists(ca_crt_yol):
        with open(ca_key_yol, "rb") as f:
            ca_key = serialization.load_pem_private_key(f.read(), None)
        with open(ca_crt_yol, "rb") as f:
            ca_crt = x509.load_pem_x509_certificate(f.read())
        yeni_ca = False
    else:
        ca_key = ec.generate_private_key(ec.SECP256R1())
        ca_ad = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"PTS Yerel Sertifika Yetkilisi ({socket.gethostname()})")])
        ca_crt = (
            x509.CertificateBuilder().subject_name(ca_ad).issuer_name(ca_ad)
            .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(simdi - datetime.timedelta(days=1))
            .not_valid_after(simdi + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                         content_commitment=False, key_encipherment=False, data_encipherment=False,
                                         key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256())
        )
        _yaz(ca_key_yol, ca_key.private_bytes(pem, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()), gizli=True)
        _yaz(ca_crt_yol, ca_crt.public_bytes(pem))
        yeni_ca = True

    sunucu_key = ec.generate_private_key(ec.SECP256R1())
    san = [x509.IPAddress(ipaddress.ip_address(ip)) for ip in ipler] + [x509.DNSName(a) for a in adlar]
    sunucu_crt = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ipler[0] if ipler else adlar[0])]))
        .issuer_name(ca_crt.subject).public_key(sunucu_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(simdi - datetime.timedelta(days=1))
        .not_valid_after(simdi + datetime.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    _yaz(os.path.join(klasor, "sunucu.key"), sunucu_key.private_bytes(
        pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()), gizli=True)
    _yaz(os.path.join(klasor, "sunucu.crt"), sunucu_crt.public_bytes(pem) + ca_crt.public_bytes(pem))
    return {"yeni_ca": yeni_ca, "ca": ca_crt_yol, "bitis": sunucu_crt.not_valid_after_utc.date()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PTS paneli için HTTPS sertifikası üretir.")
    ap.add_argument("--ip", action="append", default=[], help="sertifikaya eklenecek IP (tekrarlanabilir)")
    ap.add_argument("--ad", action="append", default=[], help="sertifikaya eklenecek alan adı (tekrarlanabilir)")
    ap.add_argument("--klasor", default=KLASOR, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        import cryptography  # noqa: F401
    except ImportError:
        print("HATA: 'cryptography' paketi kurulu değil. Kurmak için:\n"
              "  .venv\\Scripts\\python.exe -m pip install cryptography")
        return 2
    ipler = sorted(set(args.ip) | {"127.0.0.1"}) if args.ip else _yerel_ipler()
    for ip in ipler:
        ipaddress.ip_address(ip)  # hatalı IP'de hemen dur
    adlar = sorted(set(args.ad) | {"localhost", socket.gethostname()})
    sonuc = olustur(args.klasor, ipler, adlar)
    print("Sertifika hazır:", args.klasor)
    print("  IP'ler :", ", ".join(ipler))
    print("  Adlar  :", ", ".join(adlar))
    print("  Geçerli:", sonuc["bitis"], "tarihine kadar")
    print()
    if sonuc["yeni_ca"]:
        print("YENİ sertifika yetkilisi oluşturuldu. Panelin açıldığı HER bilgisayarda bir kez:")
    else:
        print("Mevcut sertifika yetkilisi kullanıldı (bilgisayarlara yeniden yüklemeye gerek yok).")
        print("Henüz yüklenmemiş bir bilgisayar varsa:")
    print(f"  1) {sonuc['ca']} dosyasını o bilgisayara kopyalayın")
    print("  2) PowerShell (yönetici GEREKMEZ):  certutil -user -addstore Root pts-ca.crt")
    print("     çıkan güvenlik sorusuna Evet deyin, tarayıcıyı kapatıp açın.")
    print()
    print("Ardından .env dosyasına  PTS_HTTPS=1  satırını ekleyip:  Restart-Service PTS")
    print("Panel adresi: https://<sunucu IP>:8000 (ve Lojman https://<sunucu IP>:8787)")
    print("UYARI: sertifika klasöründeki .key dosyaları GİZLİDİR; kimseyle paylaşmayın.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
