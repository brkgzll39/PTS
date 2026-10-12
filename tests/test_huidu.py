"""backend/huidu.py testleri. Beklenen baytlar, NİZAMİYE kartı (HD-E62,
172.17.1.224) ile eski Pts.exe arasındaki gerçek trafiğin pktmon
yakalamasından (2026-10-10) alındı."""
import os
import socket
import threading

import pytest

from backend import huidu, led_panel

CIHAZ_ID = bytes.fromhex("A7FF607C66A090C1F45F27020B869458")

# Bölge 0, "T.P.A.O." yazısı; sıra 0x35-0x37, sayaç 0xF6B8
YAKALANAN_BASLA_0 = bytes.fromhex(
    "4854001B004D1800000000000000000000000000000000000000352FF6B8000100070000000000000115"
    "0000000000000000000000000000000000000000000000000000000000000000034CAA"
)
YAKALANAN_BITMAP_0 = bytes.fromhex(
    "4854001B013819000000000000000000000000000000000000003605F6B8000048560015000000000000"
    "1E0000000000010000011500000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000000007C7808038000000"
    "000000000000000001044140440000000000000000000000010441408200000000000000000000000104"
    "414082000000000000000000000001078220820000000000000000000000010403E08200000000000000"
    "000000000104041044000000000000000000000001141412384000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000C60AA"
)
YAKALANAN_BITIR_0 = bytes.fromhex(
    "4854001B00211A000000000000000000000000000000000000003703F6B802DAAA"
)
# Bölge 1, boş; sıra 0x38-0x39, sayaç 0xF82F
YAKALANAN_BASLA_1 = bytes.fromhex(
    "4854001B004D1800000000000000000000000000000000000000382FF82F000100070001000000000115"
    "000000000000000000000000000000000000000000000000000000000000000002C9AA"
)
YAKALANAN_BITMAP_1_BASLIK = bytes.fromhex(
    "4854001B013819000000000000000000000000000000000000003905F82F0000485600150000000000001900"
    "000000000100000115"
)
YAKALANAN_BITMAP_1_SON = bytes.fromhex("0351AA")
YAKALANAN_ONAY = bytes.fromhex("4852A7FF607C66A090C1F45F27020B869458001C180000000000003508D5AA")


def _onay(komut, sira, durum=bytes(6)):
    ham = b"HR" + CIHAZ_ID + b"\x00\x1c" + bytes([komut]) + durum + bytes([sira])
    return ham + huidu.checksum(ham).to_bytes(2, "big") + b"\xaa"


# ------------------------------------------------------------------
# Çerçeveler -- yakalamayla birebir
# ------------------------------------------------------------------

def test_yakalanan_sabitler_tutarli():
    assert len(YAKALANAN_BASLA_0) == 77
    assert len(YAKALANAN_BITMAP_0) == 312
    assert len(YAKALANAN_BITIR_0) == 33
    assert len(YAKALANAN_BASLA_1) == 77
    assert len(YAKALANAN_BITMAP_1_BASLIK) + huidu.BITMAP_BOYUTU + len(YAKALANAN_BITMAP_1_SON) == 312


def test_basla_cercevesi_yakalamayla_ayni():
    assert huidu.cerceve(0x18, 0x35, 0xF6B8, huidu.basla_govdesi(0)) == YAKALANAN_BASLA_0
    assert huidu.cerceve(0x18, 0x38, 0xF82F, huidu.basla_govdesi(1)) == YAKALANAN_BASLA_1


def test_bitmap_cercevesi_yakalamayla_ayni():
    bitmap = YAKALANAN_BITMAP_0[53:309]
    assert huidu.cerceve(0x19, 0x36, 0xF6B8, huidu.bitmap_govdesi(0, bitmap)) == YAKALANAN_BITMAP_0

    bos = huidu.cerceve(0x19, 0x39, 0xF82F, huidu.bitmap_govdesi(1, bytes(huidu.BITMAP_BOYUTU)))
    assert bos == YAKALANAN_BITMAP_1_BASLIK + bytes(huidu.BITMAP_BOYUTU) + YAKALANAN_BITMAP_1_SON


def test_bitir_cercevesi_yakalamayla_ayni():
    assert huidu.cerceve(0x1A, 0x37, 0xF6B8) == YAKALANAN_BITIR_0


def test_sira_ve_sayac_tasar():
    c = huidu.cerceve(0x1A, 0x1FF, 0x1F6B8)
    assert c[26] == 0xFF and c[28:30] == b"\xf6\xb8"


def test_gecersiz_bolge_ve_bitmap_reddedilir():
    with pytest.raises(ValueError):
        huidu.basla_govdesi(2)
    with pytest.raises(ValueError):
        huidu.bitmap_govdesi(0, bytes(10))


# ------------------------------------------------------------------
# Onay
# ------------------------------------------------------------------

def test_onay_yardimcisi_yakalamayla_ayni():
    assert _onay(0x18, 0x35) == YAKALANAN_ONAY


def test_yakalanan_onay_gecerli():
    huidu.onay_dogrula(YAKALANAN_ONAY, 0x18, 0x35)


@pytest.mark.parametrize("onay, komut, sira", [
    (YAKALANAN_ONAY, 0x19, 0x35),                        # yanlış komut
    (YAKALANAN_ONAY, 0x18, 0x36),                        # yanlış sıra no
    (YAKALANAN_ONAY[:-3] + b"\x00\x00\xaa", 0x18, 0x35),  # bozuk checksum
    (YAKALANAN_ONAY[:20], 0x18, 0x35),                   # eksik
    (_onay(0x18, 0x35, durum=b"\x00\x00\x00\x00\x00\x01"), 0x18, 0x35),  # hata kodu
])
def test_gecersiz_onay_reddedilir(onay, komut, sira):
    with pytest.raises(huidu.HuiduHatasi):
        huidu.onay_dogrula(onay, komut, sira)


# ------------------------------------------------------------------
# Metin -> bitmap
# ------------------------------------------------------------------

def _yanik_satirlar(bitmap):
    return [y for y in range(huidu.YUKSEKLIK) if any(bitmap[y * 16:(y + 1) * 16])]


def test_kisa_metin_tek_satir_kalir():
    assert huidu.satirlari_duzenle(["34ABC123"]) == ["34ABC123"]


def test_uzun_metin_ikiye_bolunur():
    duzen = huidu.satirlari_duzenle(["KARA LİSTE: 34ABC123 GEÇİŞ ENGELLENDİ"])
    assert len(duzen) == 2
    assert " ".join(duzen) == "KARA LİSTE: 34ABC123 GEÇİŞ ENGELLENDİ"


def test_bos_satirlar_atilir():
    assert huidu.satirlari_duzenle(["", "  ", "34ABC123"]) == ["34ABC123"]
    assert huidu.metin_bitmap([]) == bytes(huidu.BITMAP_BOYUTU)


def test_iki_satir_ust_ve_alt_yariya_cizilir():
    bitmap = huidu.metin_bitmap(["HOŞ GELDİNİZ", "34ABC123"])
    assert len(bitmap) == huidu.BITMAP_BOYUTU
    satirlar = _yanik_satirlar(bitmap)
    assert any(y < 8 for y in satirlar) and any(y >= 8 for y in satirlar)


def test_tek_satir_bitmap_dolu():
    bitmap = huidu.metin_bitmap(["34ABC123"])
    assert len(bitmap) == huidu.BITMAP_BOYUTU
    assert len(_yanik_satirlar(bitmap)) >= 8, "tek satır büyük yazıyla çizilmeli"


# ------------------------------------------------------------------
# Gönderim -- sahte kart
# ------------------------------------------------------------------

class SahteKart:
    """Localhost'ta kartı taklit eder: çerçeveleri doğrular, onaylar, kaydeder."""

    def __init__(self, onayla=True):
        self.onayla = onayla
        self.cerceveler = []
        self.sunucu = socket.socket()
        self.sunucu.bind(("127.0.0.1", 0))
        self.sunucu.listen()
        self.port = self.sunucu.getsockname()[1]
        threading.Thread(target=self._dongu, daemon=True).start()

    def _oku(self, s, n):
        veri = b""
        while len(veri) < n:
            parca = s.recv(n - len(veri))
            if not parca:
                return None
            veri += parca
        return veri

    def _dongu(self):
        while True:
            try:
                baglanti, _ = self.sunucu.accept()
            except OSError:
                return
            with baglanti:
                acik_sayac = None
                while True:
                    bas = self._oku(baglanti, 6)
                    if bas is None:
                        break
                    kalan = self._oku(baglanti, int.from_bytes(bas[4:6], "big") - 6)
                    if kalan is None:
                        break
                    c = bas + kalan
                    assert huidu.checksum(c[:-3]) == int.from_bytes(c[-3:-1], "big")
                    self.cerceveler.append(c)
                    if self.onayla:
                        # Gerçek kart gibi: 0x19/0x1A, 0x18'in sayacını taşımıyorsa 05 ile reddedilir.
                        if c[6] == huidu.KOMUT_BASLA:
                            acik_sayac = c[28:30]
                        durum = bytes(6) if c[28:30] == acik_sayac else b"\x05" + bytes(5)
                        baglanti.sendall(_onay(c[6], c[26], durum))

    def kapat(self):
        self.sunucu.close()


@pytest.fixture
def kart():
    k = SahteKart()
    yield k
    k.kapat()


def test_gonder_iki_bolgeyi_sirayla_yazar(kart):
    huidu.gonder("127.0.0.1", kart.port, ["HOŞ GELDİNİZ", "34ABC123"], zaman_asimi=2)
    assert [c[6] for c in kart.cerceveler] == [0x18, 0x19, 0x1A] * 2
    assert [c[35] for c in kart.cerceveler if c[6] == 0x18] == [0, 1]  # bölge no
    bitmap0, bitmap1 = (c[53:309] for c in kart.cerceveler if c[6] == 0x19)
    assert any(bitmap0)
    assert bitmap1 == bytes(huidu.BITMAP_BOYUTU), "tek bölge modunda bölge 1 boşaltılır"


def test_bolgenin_uc_cercevesi_ayni_sayaci_tasir(kart, monkeypatch):
    """Yakalamada bir bölgenin 0x18/0x19/0x1A çerçeveleri aynı sayacı taşıyor;
    farklı sayaçla kart 0x19'u 05 ile reddediyordu (2026-10-12 saha)."""
    sayaclar = iter(range(0x1000, 0x2000, 7))
    monkeypatch.setattr(huidu, "_sayac", lambda: next(sayaclar))
    huidu.gonder("127.0.0.1", kart.port, ["34ABC123"], zaman_asimi=2)
    for bolge in range(2):
        uc = kart.cerceveler[bolge * 3:(bolge + 1) * 3]
        assert len({c[28:30] for c in uc}) == 1


def test_gonder_iki_bolge_modunda_satirlari_ayirir(kart):
    huidu.gonder("127.0.0.1", kart.port, ["HOŞ GELDİNİZ", "34ABC123"], iki_bolge=True, zaman_asimi=2)
    bitmap0, bitmap1 = (c[53:309] for c in kart.cerceveler if c[6] == 0x19)
    assert any(bitmap0) and any(bitmap1)


def test_onay_gelmezse_hata():
    k = SahteKart(onayla=False)
    try:
        with pytest.raises(huidu.HuiduHatasi):
            huidu.gonder("127.0.0.1", k.port, ["TEST"], zaman_asimi=0.5)
    finally:
        k.kapat()


def test_kart_ulasilamazsa_hata():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # dinleyen yok -> bağlantı reddedilir
    with pytest.raises(huidu.HuiduHatasi):
        huidu.gonder("127.0.0.1", port, ["TEST"], zaman_asimi=0.5)


# ------------------------------------------------------------------
# led_panel entegrasyonu
# ------------------------------------------------------------------

def _huidu_ayarlari(port):
    return dict(led_panel.VARSAYILAN_AYARLAR, led_mod="huidu", huidu_host="127.0.0.1", huidu_port=port)


def test_led_panel_huidu_modu_satirlari_iletir(kart, monkeypatch):
    monkeypatch.setattr(led_panel, "ayarlari_oku", lambda: _huidu_ayarlari(kart.port))
    assert led_panel.led_mesaj_gonder("HOŞ GELDİNİZ 34ABC123", satirlar=("HOŞ GELDİNİZ", "34ABC123")) is True
    assert len(kart.cerceveler) == 6


def test_led_panel_huidu_hatasinda_false_doner(monkeypatch):
    k = SahteKart(onayla=False)
    k.kapat()
    monkeypatch.setattr(led_panel, "ayarlari_oku", lambda: _huidu_ayarlari(k.port))
    assert led_panel.led_mesaj_gonder("TEST") is False


def test_testler_canli_led_ayarlarina_dokunmaz():
    """conftest LED ayar dosyasını geçici dizine yönlendirir; testler gerçek
    backend/config.json'ı ezmemeli ve oradaki panele mesaj göndermemeli."""
    gercek = os.path.join(led_panel.BACKEND_DIR, "config.json")
    assert os.path.abspath(led_panel.CONFIG_YOLU) != os.path.abspath(gercek)


# ------------------------------------------------------------------
# Görünür genişlik (NİZAMİYE paneli 64x32, yalnızca soldaki 64 sütunu gösterir)
# ------------------------------------------------------------------

def _yanik_sutunlar(bitmap):
    return {x for y in range(huidu.YUKSEKLIK) for x in range(huidu.GENISLIK)
            if bitmap[y * 16 + x // 8] >> (7 - x % 8) & 1}


@pytest.mark.parametrize("metin", [
    ["YETKİSİZ ARAÇ"], ["HOŞ GELDİNİZ"], ["KARA LİSTE"], ["SÜRESİ DOLDU"],
    ["34ABC1234"], ["PTS SİSTEMİ TEST MESAJI"], ["HOŞ GELDİNİZ", "34ABC123"],
])
def test_yazi_gorunur_genislige_sigar(metin):
    sutunlar = _yanik_sutunlar(huidu.metin_bitmap(metin, genislik=64))
    assert sutunlar, "bir şey çizilmeli"
    assert max(sutunlar) < 64, "64 px panelde sağdaki sütunlar görünmez, yazı kesilirdi"


def test_pts_exe_gibi_64_pxin_ortasina_cizer():
    # Pts.exe "T.P.A.O."yu x=13..50'ye çizmişti: ortası 31.5
    sutunlar = _yanik_sutunlar(huidu.metin_bitmap(["T.P.A.O."], genislik=64))
    assert abs((min(sutunlar) + max(sutunlar)) / 2 - 31.5) <= 2


def test_128_genislikte_tum_bitmap_kullanilir():
    assert max(_yanik_sutunlar(huidu.metin_bitmap(["YETKİSİZ ARAÇ 34ABC123"], genislik=128))) >= 64


@pytest.mark.parametrize("genislik", [0, 7, 129])
def test_gecersiz_genislik_reddedilir(genislik):
    with pytest.raises(ValueError):
        huidu.metin_bitmap(["TEST"], genislik=genislik)


def test_led_panel_genislik_ayarini_iletir(kart, monkeypatch):
    ayarlar = dict(_huidu_ayarlari(kart.port), huidu_genislik=64, huidu_iki_bolge=True)
    monkeypatch.setattr(led_panel, "ayarlari_oku", lambda: ayarlar)
    assert led_panel.led_mesaj_gonder("YETKİSİZ ARAÇ: 34TD1234", satirlar=("YETKİSİZ ARAÇ", "34TD1234"))
    for c in kart.cerceveler:
        if c[6] == huidu.KOMUT_BITMAP:
            assert max(_yanik_sutunlar(c[53:309])) < 64
