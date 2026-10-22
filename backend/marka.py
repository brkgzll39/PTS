"""Kuruma özel görünüm ve etiketler (2026-10-23, ürünleştirme).

PTS ilk olarak TPAO Trakya için yazıldı; kurum adı, logo, iletişim bilgisi,
"Bölge Müdürü" etiketi ve LED bekleme yazısı koda gömülüydü. Başka bir kuruma
kurulurken kod değiştirilmesin diye bunlar `marka.json`'dan okunur.

Dosya YOKSA bugünkü TPAO değerleri kullanılır -- çalışan sistem hiçbir fark
görmez. Yeni müşteri kurulumunda proje klasörüne (ya da PTS_MARKA_FILE ile
gösterilen yere) bir marka.json konur; örnek: installer/marka-ornek.json.
Dosya VARSA eksik alanlar TPAO'dan değil GENEL'den (kurumsuz) gelir: başka
bir kurumda TPAO adı, telefonu ya da LED yazısı hiçbir durumda görünmesin.
Logo: "logo_dosyasi" marka.json'un bulunduğu klasöre göre bir PNG/SVG yolu;
verilmezse kurumsuz PTS logosu (frontend/img/pts-logo.svg).
"""
import copy
import json
import logging
import os
from typing import Optional

logger = logging.getLogger("pts.marka")

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VARSAYILAN = {
    "kurum_adi": "TÜRKİYE PETROLLERİ ANONİM ORTAKLIĞI",
    "logo_alt": "Türkiye Petrolleri Anonim Ortaklığı",
    "uygulama_adi": "TPAO - Plaka Tanıma Sistemi",
    "kisa_ad": "TPAO PTS",
    "logo_dosyasi": None,   # None: frontend/img/tpao-logo.png
    "iletisim": {
        "telefon": "0537 210 2313",
        "telefon_uri": "+905372102313",
        "dahili": "0288 427 4864",
        "eposta": "bguzelel@tpao.gov.tr",
    },
    # Kişi tipi "vip"in adı (panel / Excel) ve LED'de görünen hali.
    "vip_adi": "Bölge Müdürü",
    "vip_etiketi": "BÖLGE MÜDÜRÜ",
    # Huidu LED panelinin boştaki iki satırı (led_config.json'da değer yoksa).
    "led_bekleme_yazisi": "T.P.A.O.",
    "led_bekleme_yazisi_2": "TRAKYA",
    # Hiç vardiya çizelgesi girilmemişse yüklenecek hazır çizelge ("ekim_2026"
    # = TPAO Trakya Bölge Müdürlüğü Ekim 2026 listesi) ya da null.
    "varsayilan_vardiya_cizelgesi": "ekim_2026",
}

# marka.json varken eksik alanların değeri (kurumsuz ürün).
GENEL = {
    "kurum_adi": "PLAKA TANIMA SİSTEMİ",
    "logo_alt": "PTS",
    "uygulama_adi": "PTS - Plaka Tanıma Sistemi",
    "kisa_ad": "PTS",
    "logo_dosyasi": None,
    "iletisim": {"telefon": "", "telefon_uri": "", "dahili": "", "eposta": ""},
    "vip_adi": "VIP",
    "vip_etiketi": "VIP",
    "led_bekleme_yazisi": "HOŞ GELDİNİZ",
    "led_bekleme_yazisi_2": "",
    "varsayilan_vardiya_cizelgesi": None,
}

_onbellek: dict = {"yol": None, "zaman": None, "deger": None}


def dosya_yolu() -> str:
    return (os.environ.get("PTS_MARKA_FILE") or "").strip() or os.path.join(_KOK, "marka.json")


def _birlestir(taban: dict, ust: dict) -> dict:
    sonuc = copy.deepcopy(taban)
    for anahtar, deger in ust.items():
        if anahtar not in taban:
            logger.warning("marka.json: bilinmeyen alan yok sayıldı: %s", anahtar)
            continue
        if isinstance(taban[anahtar], dict) and isinstance(deger, dict):
            sonuc[anahtar] = {**taban[anahtar], **{k: v for k, v in deger.items() if k in taban[anahtar]}}
        else:
            sonuc[anahtar] = deger
    return sonuc


def oku() -> dict:
    """Geçerli marka ayarları (dosya değişince yeniden okunur)."""
    yol = dosya_yolu()
    try:
        zaman = os.path.getmtime(yol)
    except OSError:
        zaman = None
    if _onbellek["yol"] == yol and _onbellek["zaman"] == zaman and _onbellek["deger"] is not None:
        return _onbellek["deger"]
    deger = copy.deepcopy(VARSAYILAN)
    if zaman is not None:
        try:
            with open(yol, encoding="utf-8") as f:
                deger = _birlestir(GENEL, json.load(f))
        except (OSError, ValueError) as exc:
            # Bozuk dosyada da TPAO değil kurumsuz değerler: yanlış kurumda TPAO görünmesin.
            logger.error("marka.json okunamadı (%s); kurumsuz değerler kullanılıyor: %s", yol, exc)
            deger = copy.deepcopy(GENEL)
    _onbellek.update(yol=yol, zaman=zaman, deger=deger)
    return deger


def dosya_var_mi() -> bool:
    return os.path.isfile(dosya_yolu())


def ozel_logo_yolu() -> Optional[str]:
    """marka.json'da geçerli bir logo dosyası varsa tam yolu; yoksa None."""
    ad = oku().get("logo_dosyasi")
    if not ad:
        return None
    yol = ad if os.path.isabs(ad) else os.path.join(os.path.dirname(dosya_yolu()), ad)
    return yol if os.path.isfile(yol) else None
