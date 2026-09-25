"""backend/kucuk_gorsel.py testleri (fastapi'den bağımsız -- GERÇEKTEN
çalıştırıldı). Bkz. modülün docstring'i: 2026-09-25 "kayıtlarda araç
arattığımda / PDF indirirken yavaş" geri bildirimi."""
import os
import time

from PIL import Image

from backend import kucuk_gorsel


def _kare(yol, boyut=(1920, 1080)):
    Image.new("RGB", boyut, (40, 90, 160)).save(yol, quality=85)
    return str(yol)


def test_kucuk_resim_uretilir_boyutu_sinirli_ve_onbellege_yazilir(tmp_path):
    kaynak = _kare(tmp_path / "34ABC123_1_ab.jpg")
    yol = kucuk_gorsel.kucuk_gorsel_yolu(kaynak)
    assert yol == str(tmp_path / ".kucuk" / "34ABC123_1_ab.jpg")
    with Image.open(yol) as img:
        assert img.width <= 480 and img.height <= 320
        assert img.size == (480, 270), "en-boy oranı korunmalı"
    assert os.path.getsize(yol) < os.path.getsize(kaynak)


def test_ikinci_istekte_onbellekten_doner_yeniden_uretmez(tmp_path):
    kaynak = _kare(tmp_path / "a.jpg")
    ilk = kucuk_gorsel.kucuk_gorsel_yolu(kaynak)
    ilk_mtime = os.path.getmtime(ilk)
    time.sleep(0.02)
    assert kucuk_gorsel.kucuk_gorsel_yolu(kaynak) == ilk
    assert os.path.getmtime(ilk) == ilk_mtime


def test_orijinal_guncellenirse_kucuk_resim_yenilenir(tmp_path):
    kaynak = _kare(tmp_path / "a.jpg")
    ilk = kucuk_gorsel.kucuk_gorsel_yolu(kaynak)
    eski = os.path.getmtime(ilk)
    os.utime(ilk, (eski - 100, eski - 100))  # önbellek orijinalden eski
    kucuk_gorsel.kucuk_gorsel_yolu(kaynak)
    assert os.path.getmtime(ilk) > eski - 100


def test_bozuk_veya_olmayan_dosyada_none_doner_cokmez(tmp_path):
    assert kucuk_gorsel.kucuk_gorsel_yolu(None) is None
    assert kucuk_gorsel.kucuk_gorsel_yolu(str(tmp_path / "yok.jpg")) is None
    bozuk = tmp_path / "bozuk.jpg"
    bozuk.write_bytes(b"bu bir jpeg degil")
    assert kucuk_gorsel.kucuk_gorsel_yolu(str(bozuk)) is None
    assert kucuk_gorsel.bellekte_kucuk_jpeg(str(bozuk), (240, 160), 60) is None
    # Yarım .tmp dosyası kalmamalı.
    klasor = tmp_path / ".kucuk"
    assert not klasor.exists() or not [a for a in os.listdir(klasor) if a.endswith(".tmp")]


def test_bellekte_kucuk_jpeg_pdf_boyutunda(tmp_path):
    kaynak = _kare(tmp_path / "a.jpg")
    akis = kucuk_gorsel.bellekte_kucuk_jpeg(kaynak, (240, 160), 60)
    with Image.open(akis) as img:
        assert img.size == (240, 135)


def test_yetim_kucuk_resimler_temizlenir(tmp_path):
    a = _kare(tmp_path / "a.jpg")
    b = _kare(tmp_path / "b.jpg")
    kucuk_gorsel.kucuk_gorsel_yolu(a)
    kucuk_gorsel.kucuk_gorsel_yolu(b)
    os.remove(b)  # orijinal silindi (ör. saklama süresi doldu)
    eski_tmp = tmp_path / ".kucuk" / "yarim.tmp"
    eski_tmp.write_bytes(b"x")
    os.utime(eski_tmp, (time.time() - 3600, time.time() - 3600))
    taze_tmp = tmp_path / ".kucuk" / "suruyor.tmp"
    taze_tmp.write_bytes(b"x")

    assert kucuk_gorsel.yetim_kucuk_gorselleri_temizle(str(tmp_path)) == 2
    kalan = sorted(os.listdir(tmp_path / ".kucuk"))
    assert kalan == ["a.jpg", "suruyor.tmp"], "Başka bir isteğin o an yazdığı taze .tmp silinmemeli"


def test_kucuk_gorseli_sil(tmp_path):
    a = _kare(tmp_path / "a.jpg")
    yol = kucuk_gorsel.kucuk_gorsel_yolu(a)
    kucuk_gorsel.kucuk_gorseli_sil(a)
    assert not os.path.exists(yol)
    kucuk_gorsel.kucuk_gorseli_sil(a)  # ikinci kez: hata vermemeli
