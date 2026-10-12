"""
Huidu HD-E62 LED kontrol kartı -- ağ protokolü
----------------------------------------------
Kartın kendi metin komutu yok: PC metni 128x16 piksel, 1 bit/piksel bir
bitmap olarak çizip gönderir. Protokol, sahadaki NİZAMİYE kartı
(172.17.1.224) ile eski Pts.exe arasındaki trafiğin pktmon yakalamasından
(2026-10-10) çözüldü; bilinmeyen başlık alanları yakalamadaki değerlerle
birebir gönderilir.

Bir bölgenin güncellenmesi = kartın TCP 6101 portuna tek bağlantı, 3 komut:
    0x18  başla / bölge seç
    0x19  bitmap (128x16, 256 bayt, satır başına 16 bayt, MSB solda, 1 = yanık)
    0x1A  bitir / uygula
Kart her komutu 31 baytlık bir onayla yanıtlar; onay gelmeden sonraki komut
gönderilmez.

Çerçeve (PC -> kart):
    0   2  "HT"
    2   2  0x001B (sabit)
    4   2  toplam çerçeve uzunluğu (big-endian)
    6   1  komut
    7  19  0x00
    26  1  sıra no (her çerçevede +1)
    27  1  komuta bağlı sabit (0x18 -> 2F, 0x19 -> 05, 0x1A -> 03)
    28  2  milisaniye sayacı (big-endian, taşar)
    30  .. komut gövdesi
    -3  2  checksum = baştan buraya kadar tüm baytların toplamı & 0xFFFF (big-endian)
    -1  1  0xAA

Onay (kart -> PC, 31 bayt):
    "HR" + cihaz kimliği (16) + 0x001C + komut + 0x00 x 6 + sıra no + checksum + 0xAA
"""
import logging
import os
import socket
import threading
import time
from typing import Optional, Sequence

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("pts.led.huidu")

VARSAYILAN_PORT = 6101
GENISLIK = 128
YUKSEKLIK = 16
BITMAP_BOYUTU = GENISLIK * YUKSEKLIK // 8  # 256

KOMUT_BASLA = 0x18
KOMUT_BITMAP = 0x19
KOMUT_BITIR = 0x1A

ONAY_BOYUTU = 31
_BASLIK_BOYUTU = 30

# Anlamı çözülmemiş, yakalamada sabit görülen değerler.
_KOMUT_ALT_KODU = {KOMUT_BASLA: 0x2F, KOMUT_BITMAP: 0x05, KOMUT_BITIR: 0x03}
_BITMAP_BOLGE_KODU = {0: 0x1E, 1: 0x19}
BOLGELER = tuple(sorted(_BITMAP_BOLGE_KODU))

FONT_YOLU = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "DejaVuSans-Bold.ttf")


class HuiduHatasi(Exception):
    """Kart bağlantısı, zaman aşımı ya da geçersiz onay."""


# ------------------------------------------------------------------
# Çerçeve oluşturma / doğrulama
# ------------------------------------------------------------------

def checksum(veri: bytes) -> int:
    return sum(veri) & 0xFFFF


def cerceve(komut: int, sira: int, sayac: int, govde: bytes = b"") -> bytes:
    uzunluk = _BASLIK_BOYUTU + len(govde) + 3
    ham = (
        b"HT\x00\x1b"
        + uzunluk.to_bytes(2, "big")
        + bytes([komut])
        + bytes(19)
        + bytes([sira & 0xFF, _KOMUT_ALT_KODU[komut]])
        + (sayac & 0xFFFF).to_bytes(2, "big")
        + govde
    )
    return ham + checksum(ham).to_bytes(2, "big") + b"\xaa"


def basla_govdesi(bolge: int) -> bytes:
    _bolge_dogrula(bolge)
    return b"\x00\x01\x00\x07" + bolge.to_bytes(2, "big") + bytes(4) + b"\x01\x15" + bytes(32)


def bitmap_govdesi(bolge: int, bitmap: bytes) -> bytes:
    _bolge_dogrula(bolge)
    if len(bitmap) != BITMAP_BOYUTU:
        raise ValueError(f"bitmap {BITMAP_BOYUTU} bayt olmalı, {len(bitmap)} bayt verildi")
    return (
        b"\x00\x00\x48\x56\x00\x15"
        + bytes(6)
        + bytes([_BITMAP_BOLGE_KODU[bolge]])
        + bytes(5)
        + b"\x01\x00\x00\x01\x15"
        + bitmap
    )


def onay_dogrula(onay: bytes, komut: int, sira: int) -> None:
    """Kartın onayı beklenen komut/sıra no için geçerli değilse HuiduHatasi."""
    if len(onay) != ONAY_BOYUTU or onay[:2] != b"HR" or onay[-1] != 0xAA:
        raise HuiduHatasi(f"geçersiz onay çerçevesi: {onay.hex()}")
    if checksum(onay[:-3]) != int.from_bytes(onay[-3:-1], "big"):
        raise HuiduHatasi(f"onay checksum hatalı: {onay.hex()}")
    if onay[18:20] != b"\x00\x1c" or onay[20] != komut or onay[27] != (sira & 0xFF):
        raise HuiduHatasi(
            f"beklenmeyen onay (komut=0x{komut:02X}, sıra=0x{sira & 0xFF:02X}): {onay.hex()}"
        )
    if any(onay[21:27]):
        # Yakalamada bu alan hep sıfırdı; sıfır dışı değer büyük olasılıkla hata kodu.
        raise HuiduHatasi(f"kart hata kodu döndü: {onay[21:27].hex()}")


def _bolge_dogrula(bolge: int) -> None:
    if bolge not in _BITMAP_BOLGE_KODU:
        raise ValueError(f"desteklenmeyen bölge: {bolge} (desteklenen: {BOLGELER})")


# ------------------------------------------------------------------
# Metin -> bitmap
# ------------------------------------------------------------------

_font_onbellegi: dict = {}


def _font(boyut: int) -> ImageFont.FreeTypeFont:
    if boyut not in _font_onbellegi:
        _font_onbellegi[boyut] = ImageFont.truetype(FONT_YOLU, boyut)
    return _font_onbellegi[boyut]


def _buyuk_harf_yuksekligi(font: ImageFont.FreeTypeFont) -> int:
    return -font.getbbox("H", anchor="ls")[1]


def _font_sec(metin: str, alan_yuksekligi: int, en_buyuk: int, en_kucuk: int) -> Optional[ImageFont.FreeTypeFont]:
    """Metnin genişliğe, büyük harf yüksekliğinin alana (1 px pay ile) sığdığı en büyük font."""
    for boyut in range(en_buyuk, en_kucuk - 1, -1):
        font = _font(boyut)
        if _buyuk_harf_yuksekligi(font) <= alan_yuksekligi - 2 and font.getlength(metin) <= GENISLIK:
            return font
    return None


def _ikiye_bol(metin: str) -> list:
    """Metni kelime sınırından, uzun satır en kısa olacak şekilde ikiye böler."""
    kelimeler = metin.split()
    if len(kelimeler) < 2:
        return [metin]
    en_iyi = min(
        range(1, len(kelimeler)),
        key=lambda i: max(len(" ".join(kelimeler[:i])), len(" ".join(kelimeler[i:]))),
    )
    return [" ".join(kelimeler[:en_iyi]), " ".join(kelimeler[en_iyi:])]


def _satir_ciz(ciz: ImageDraw.ImageDraw, metin: str, alan_ust: int, alan_yuksekligi: int, en_buyuk: int) -> None:
    font = _font_sec(metin, alan_yuksekligi, en_buyuk, en_kucuk=6)
    if font is None:
        font = _font(6)
        logger.warning("LED metni panele sığmıyor, kırpılacak: %r", metin)
    taban = alan_ust + (alan_yuksekligi + _buyuk_harf_yuksekligi(font)) // 2
    ciz.text((GENISLIK // 2, taban), metin, font=font, fill=1, anchor="ms")


def satirlari_duzenle(satirlar: Sequence[str]) -> list:
    """Boşları atar; tek satır 16 px yüksekliğe okunur boyutta (>= 10 pt) sığmıyorsa ikiye böler."""
    temiz = [s.strip() for s in satirlar if s and s.strip()][:2]
    if len(temiz) == 1 and _font_sec(temiz[0], YUKSEKLIK, en_buyuk=20, en_kucuk=10) is None:
        return _ikiye_bol(temiz[0])
    return temiz


def metin_bitmap(satirlar: Sequence[str]) -> bytes:
    """En fazla 2 satırı 128x16 bitmap'e çizer: 1 satır tam yükseklikte, 2 satır 8'er px."""
    img = Image.new("1", (GENISLIK, YUKSEKLIK), 0)
    ciz = ImageDraw.Draw(img)
    ciz.fontmode = "1"
    duzen = satirlari_duzenle(satirlar)
    if len(duzen) == 1:
        _satir_ciz(ciz, duzen[0], 0, YUKSEKLIK, en_buyuk=20)
    elif len(duzen) == 2:
        _satir_ciz(ciz, duzen[0], 0, YUKSEKLIK // 2, en_buyuk=10)
        _satir_ciz(ciz, duzen[1], YUKSEKLIK // 2, YUKSEKLIK // 2, en_buyuk=10)
    return img.tobytes()


# ------------------------------------------------------------------
# Gönderim
# ------------------------------------------------------------------

_sira_kilidi = threading.Lock()
_sira = 0
# Aynı karta iki gönderim iç içe geçmesin (kayıt bildirimi + /led/test gibi).
_gonderim_kilidi = threading.Lock()


def _siradaki() -> int:
    global _sira
    with _sira_kilidi:
        _sira = (_sira + 1) & 0xFF
        return _sira


def _sayac() -> int:
    return int(time.monotonic() * 1000) & 0xFFFF


def _tam_oku(s: socket.socket, boyut: int) -> bytes:
    veri = b""
    while len(veri) < boyut:
        parca = s.recv(boyut - len(veri))
        if not parca:
            raise HuiduHatasi(f"kart bağlantıyı kapattı ({len(veri)}/{boyut} bayt onay alındı)")
        veri += parca
    return veri


def bolge_gonder(host: str, port: int, bolge: int, bitmap: bytes, zaman_asimi: float = 3.0) -> None:
    adimlar = [
        (KOMUT_BASLA, basla_govdesi(bolge)),
        (KOMUT_BITMAP, bitmap_govdesi(bolge, bitmap)),
        (KOMUT_BITIR, b""),
    ]
    try:
        with socket.create_connection((host, port), timeout=zaman_asimi) as s:
            for komut, govde in adimlar:
                sira = _siradaki()
                s.sendall(cerceve(komut, sira, _sayac(), govde))
                onay_dogrula(_tam_oku(s, ONAY_BOYUTU), komut, sira)
    except HuiduHatasi:
        raise
    except OSError as e:  # socket.timeout dahil
        raise HuiduHatasi(f"{host}:{port} bölge {bolge}: {e}") from e


def gonder(
    host: str,
    port: int = VARSAYILAN_PORT,
    satirlar: Sequence[str] = (),
    iki_bolge: bool = False,
    zaman_asimi: float = 3.0,
) -> None:
    """Metni panele yazar. Hata durumunda HuiduHatasi fırlatır.

    iki_bolge=False: tüm metin bölge 0'a çizilir, bölge 1 boşaltılır (Pts.exe'nin
    yaptığı). iki_bolge=True: 1. satır bölge 0'a, 2. satır bölge 1'e, her biri
    tam 16 px yükseklikte -- panel 128x32 ise bu kullanılmalı.
    """
    if iki_bolge:
        duzen = satirlari_duzenle(satirlar)
        bitmapler = {0: metin_bitmap(duzen[:1]), 1: metin_bitmap(duzen[1:2])}
    else:
        bitmapler = {0: metin_bitmap(satirlar), 1: bytes(BITMAP_BOYUTU)}
    with _gonderim_kilidi:
        for bolge, bitmap in bitmapler.items():
            bolge_gonder(host, port, bolge, bitmap, zaman_asimi)
