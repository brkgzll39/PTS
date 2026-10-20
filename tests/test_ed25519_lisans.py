"""2026-10-20: Ed25519 imzalı (PTS2) lisanslar ve eski (PTS1) lisans kabul ayarı."""
import os
import secrets

import pytest

from backend import ed25519, lisans


def test_rfc8032_test_vektoru_1():
    ozel = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    acik = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
    imza = bytes.fromhex(
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
    assert ed25519.acik_anahtar(ozel) == acik
    assert ed25519.imzala(ozel, b"") == imza
    assert ed25519.dogrula(acik, b"", imza)
    assert not ed25519.dogrula(acik, b"x", imza)


def test_cryptography_kutuphanesiyle_uyumlu():
    c = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    for _ in range(5):
        ozel = secrets.token_bytes(32)
        mesaj = secrets.token_bytes(40)
        ref = c.Ed25519PrivateKey.from_private_bytes(ozel)
        from cryptography.hazmat.primitives import serialization
        ref_acik = ref.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        assert ed25519.acik_anahtar(ozel) == ref_acik
        assert ed25519.imzala(ozel, mesaj) == ref.sign(mesaj)
        bozuk = bytearray(ref.sign(mesaj)); bozuk[5] ^= 1
        assert not ed25519.dogrula(ref_acik, mesaj, bytes(bozuk))


@pytest.fixture
def anahtar_cifti(monkeypatch):
    ozel = secrets.token_bytes(32)
    monkeypatch.setattr(lisans, "ACIK_ANAHTAR_HEX", ed25519.acik_anahtar(ozel).hex())
    return ozel


def test_imzali_lisans_dogrulanir(anahtar_cifti):
    anahtar = lisans.imzali_uret(anahtar_cifti, "Müşteri A", 4, 30, "ABCDEF0123456789")
    assert anahtar.startswith("PTS2.")
    p = lisans.coz(anahtar, beklenen_cihaz_kodu="ABCDEF0123456789")
    assert p["kamera_limiti"] == 4 and p["musteri"] == "Müşteri A"
    with pytest.raises(lisans.LisansGecersiz):
        lisans.coz(anahtar, beklenen_cihaz_kodu="0000000000000000")


def test_baska_ozel_anahtarla_ya_da_degistirilmis_lisans_reddedilir(anahtar_cifti):
    sahte = lisans.imzali_uret(secrets.token_bytes(32), "Sahte", 99, 3650)
    with pytest.raises(lisans.LisansGecersiz):
        lisans.coz(sahte)
    gercek = lisans.imzali_uret(anahtar_cifti, "Müşteri", 2, 30)
    surum, govde, imza = gercek.split(".")
    oynanmis = lisans._payload_olustur("Müşteri", 99, 3650, None)
    with pytest.raises(lisans.LisansGecersiz):
        lisans.coz(f"{surum}.{oynanmis}.{imza}")


def test_acik_anahtar_yoksa_imzali_lisans_kabul_edilmez(monkeypatch):
    monkeypatch.setattr(lisans, "ACIK_ANAHTAR_HEX", "")
    with pytest.raises(lisans.LisansGecersiz):
        lisans.coz(lisans.imzali_uret(secrets.token_bytes(32), "X", 1, 1))


def test_eski_lisans_derlenmis_surumde_reddedilir(monkeypatch):
    eski = lisans.uret("Kendi Sistemim", 8, 365)
    assert lisans.coz(eski)["kamera_limiti"] == 8          # kaynak kurulum: kabul
    monkeypatch.setattr(lisans, "ESKI_LISANS_KABUL", False)
    with pytest.raises(lisans.LisansGecersiz, match="Eski tip"):
        lisans.coz(eski)


def test_lisans_araci(tmp_path, capsys, monkeypatch):
    import importlib.util
    yol = os.path.join(os.path.dirname(os.path.dirname(__file__)), "araclar", "lisans_araci.py")
    spec = importlib.util.spec_from_file_location("lisans_araci", yol)
    arac = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(arac)
    dosya = str(tmp_path / "ozel.key")
    assert arac.main(["anahtar-olustur", "--dosya", dosya]) == 0
    acik = capsys.readouterr().out.strip().splitlines()[-1]
    assert arac.main(["anahtar-olustur", "--dosya", dosya]) == 1   # üzerine yazmaz
    monkeypatch.setattr(lisans, "ACIK_ANAHTAR_HEX", acik)
    capsys.readouterr()
    assert arac.main(["uret", "--anahtar", dosya, "--musteri", "M", "--kamera", "3", "--gun", "10"]) == 0
    uretilen = capsys.readouterr().out.strip().splitlines()[-1]
    assert lisans.coz(uretilen)["kamera_limiti"] == 3
