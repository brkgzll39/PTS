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


def _kilitli_open(kilitli_yol, kac_kez):
    """`kilitli_yol` ilk `kac_kez` açılışta Windows'taki gibi PermissionError verir."""
    import builtins
    gercek = builtins.open
    sayac = {"n": 0}

    def sahte(yol, *a, **kw):
        if str(yol) == str(kilitli_yol) and sayac["n"] < kac_kez:
            sayac["n"] += 1
            raise PermissionError(13, "Permission denied", str(yol))
        return gercek(yol, *a, **kw)
    return sahte, sayac


def test_kilitli_kucuk_resim_yeniden_denenir(tmp_path, monkeypatch):
    """2026-10-14 Windows saha hatası: küçük resim başka bir istek/antivirüs
    tarafından o an kilitliyse okuma kısa bir beklemeyle yeniden denenir."""
    kaynak = _kare(tmp_path / "39ADE811_1_ab.jpg")
    yol = kucuk_gorsel.kucuk_gorsel_yolu(kaynak)
    sahte, sayac = _kilitli_open(yol, 2)
    monkeypatch.setattr("builtins.open", sahte)
    veri = kucuk_gorsel.kucuk_gorsel_baytlari(kaynak)
    assert sayac["n"] == 2
    assert veri[:2] == b"\xff\xd8"


def test_kucuk_resim_hic_okunamazsa_bellekte_uretilir(tmp_path, monkeypatch):
    kaynak = _kare(tmp_path / "39ADE811_2_ab.jpg")
    yol = kucuk_gorsel.kucuk_gorsel_yolu(kaynak)
    sahte, _ = _kilitli_open(yol, 99)
    monkeypatch.setattr("builtins.open", sahte)
    monkeypatch.setattr(kucuk_gorsel.time, "sleep", lambda s: None)
    veri = kucuk_gorsel.kucuk_gorsel_baytlari(kaynak)
    assert veri and veri[:2] == b"\xff\xd8"


def test_ayni_kucuk_resim_eszamanli_istekte_bir_kez_uretilir(tmp_path, monkeypatch):
    import threading
    kaynak = _kare(tmp_path / "a.jpg")
    gercek = kucuk_gorsel._hizli_ac_ve_kucult
    uretim = {"n": 0}

    def yavas(*a, **kw):
        uretim["n"] += 1
        time.sleep(0.05)
        return gercek(*a, **kw)
    monkeypatch.setattr(kucuk_gorsel, "_hizli_ac_ve_kucult", yavas)
    sonuclar = []
    isler = [threading.Thread(target=lambda: sonuclar.append(kucuk_gorsel.kucuk_gorsel_yolu(kaynak))) for _ in range(5)]
    for t in isler:
        t.start()
    for t in isler:
        t.join()
    assert uretim["n"] == 1
    assert len(set(sonuclar)) == 1 and sonuclar[0]
