"""Merkezi izleme istemcisi (2026-10-31, kullanıcı isteği "6 numara").

Her kurulum birkaç dakikada bir SAĞLIK ÖZETİNİ satıcının merkezi izleme
sunucusuna (bkz. `merkez/` klasörü) gönderir. Bağlantıyı hep PTS başlatır
(dışarı giden HTTPS), müşterinin güvenlik duvarında port açılması gerekmez.

KVKK: özete plaka, kişi adı, fotoğraf, telefon ya da geçiş kaydı KONMAZ —
yalnız sayılar ve durumlar (kamera adı, çalışıyor mu, bugün kaç okuma, disk
yüzdesi, yedek yaşı, lisansın kalan günü, alarm TİPİ başına sayı…). Özet
main.py::_merkez_saglik_ozeti'nde hazırlanır; panelde "Gönderilen veriyi
göster" ile olduğu gibi görülebilir. `yasakli_alan_var_mi` testlerde ve
gönderimden hemen önce bu sözün tutulduğunu denetler.

Ayarlar `merkez_izleme.json`'da (panelden) ya da ortam değişkenlerinde
(PTS_MERKEZ_URL, PTS_MERKEZ_ANAHTARI — kurulum betiği için) durur; dosya önceliklidir.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import urlsplit

VARSAYILAN_ARALIK_SN = 300
ZAMAN_ASIMI_SN = 20

# Özette hiçbir derinlikte bulunmaması gereken anahtarlar (KVKK sözü).
YASAKLI_ANAHTARLAR = {"plaka", "plaka_no", "kisi", "kisi_adi", "ad_soyad", "misafir_adi", "telefon",
                      "tc", "tc_no", "foto", "fotograf", "goruntu_yolu", "jpeg", "not_metni", "kayitlar"}

_kilit = threading.Lock()
_durum = {"son_gonderim": None, "son_basarili": None, "son_hata": None, "ardisik_hata": 0, "son_yanit": None}


def ayar_dosyasi(klasor: str) -> str:
    return os.getenv("PTS_MERKEZ_AYAR_FILE") or os.path.join(klasor, "merkez_izleme.json")


def ayarlari_oku(klasor: str) -> dict:
    ayar = {"aktif": False, "url": (os.getenv("PTS_MERKEZ_URL") or "").strip(),
            "anahtar": (os.getenv("PTS_MERKEZ_ANAHTARI") or "").strip(), "aralik_sn": VARSAYILAN_ARALIK_SN}
    ayar["aktif"] = bool(ayar["url"] and ayar["anahtar"])
    try:
        with open(ayar_dosyasi(klasor), "r", encoding="utf-8") as f:
            ayar.update({k: v for k, v in json.load(f).items() if k in ayar})
    except (OSError, ValueError):
        pass
    try:
        ayar["aralik_sn"] = max(60, min(3600, int(ayar.get("aralik_sn") or VARSAYILAN_ARALIK_SN)))
    except (TypeError, ValueError):
        ayar["aralik_sn"] = VARSAYILAN_ARALIK_SN
    ayar["url"] = (ayar.get("url") or "").strip().rstrip("/")
    return ayar


def ayarlari_yaz(klasor: str, ayar: dict) -> None:
    yol = ayar_dosyasi(klasor)
    gecici = yol + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump({k: ayar.get(k) for k in ("aktif", "url", "anahtar", "aralik_sn")}, f, ensure_ascii=False, indent=2)
    os.replace(gecici, yol)


def url_dogrula(url: str) -> str:
    """Merkez adresi https olmalı (sağlık özeti ve kurulum anahtarı internetten geçer);
    yalnız denemede yerel ağ adresi için http kabul edilir."""
    url = (url or "").strip().rstrip("/")
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("Merkez adresi https://alan-adi biçiminde olmalı.")
    if p.scheme == "http" and p.hostname not in ("localhost", "127.0.0.1") and not p.hostname.startswith(("192.168.", "10.")):
        raise ValueError("İnternet üzerinden gönderim için https:// adres girin (kurulum anahtarı açık metin gitmesin).")
    return url


def anahtari_maskele(anahtar: str) -> str:
    anahtar = anahtar or ""
    return (anahtar[:4] + "…" + anahtar[-4:]) if len(anahtar) > 10 else ("•" * len(anahtar))


def yasakli_alan_var_mi(veri, yol: str = "") -> Optional[str]:
    """Özette yasaklı bir anahtar varsa yolunu döner (ör. "kameralar[0].plaka")."""
    if isinstance(veri, dict):
        for k, v in veri.items():
            if str(k).lower() in YASAKLI_ANAHTARLAR:
                return f"{yol}.{k}" if yol else str(k)
            bulunan = yasakli_alan_var_mi(v, f"{yol}.{k}" if yol else str(k))
            if bulunan:
                return bulunan
    elif isinstance(veri, list):
        for i, v in enumerate(veri):
            bulunan = yasakli_alan_var_mi(v, f"{yol}[{i}]")
            if bulunan:
                return bulunan
    return None


def gonder(url: str, anahtar: str, ozet: dict, zaman_asimi: float = ZAMAN_ASIMI_SN) -> dict:
    """Özeti `{url}/api/nabiz`'e gönderir; başarılıysa merkezin cevabını döner, değilse
    Türkçe açıklamalı RuntimeError atar. Durum bilgisi (son gönderim/hata) güncellenir."""
    yasak = yasakli_alan_var_mi(ozet)
    if yasak:  # kodlama hatası: kişisel veri asla dışarı çıkmasın
        aciklama = f"Özette kişisel veri alanı var ({yasak}); gönderilmedi."
        _hata(time.time(), aciklama)
        raise RuntimeError(aciklama)
    govde = json.dumps(ozet, ensure_ascii=False, default=str).encode("utf-8")
    istek = urllib.request.Request(f"{url}/api/nabiz", data=govde, method="POST", headers={
        "Content-Type": "application/json", "X-Kurulum-Anahtari": anahtar, "User-Agent": "PTS-merkez-istemci/1"})
    simdi = time.time()
    try:
        with urllib.request.urlopen(istek, timeout=zaman_asimi) as yanit:
            cevap = json.loads(yanit.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        aciklama = {401: "kurulum anahtarı merkezde tanınmıyor (merkez panelinden anahtarı kontrol edin)",
                    403: "bu kurulum merkezde devre dışı bırakılmış",
                    413: "özet çok büyük"}.get(exc.code, f"merkez HTTP {exc.code} döndü")
        _hata(simdi, aciklama)
        raise RuntimeError(aciklama) from exc
    except Exception as exc:  # noqa: BLE001 - ağ hatalarının hepsi aynı şekilde raporlanır
        neden = getattr(exc, "reason", exc)
        aciklama = f"merkeze ulaşılamadı ({neden})"
        _hata(simdi, aciklama)
        raise RuntimeError(aciklama) from exc
    with _kilit:
        _durum.update(son_gonderim=simdi, son_basarili=simdi, son_hata=None, ardisik_hata=0, son_yanit=cevap)
    return cevap


def _hata(zaman: float, aciklama: str) -> None:
    with _kilit:
        _durum["son_gonderim"] = zaman
        _durum["son_hata"] = aciklama
        _durum["ardisik_hata"] += 1


def durum() -> dict:
    with _kilit:
        return dict(_durum)
