"""Telegram Bot API üzerinden anlık bildirim gönderimi.

2026-09-26 kullanıcı isteği: sistemi incelerken önerdiğim geliştirmelerden
biri olarak kullanıcı "Telegram ile anlık dış bildirim" seçeneğini onayladı
-- şu ana kadar ALARM tablosuna düşen her şey (kara liste geçişi, kamera/
bariyer arızası, disk sorunu) YALNIZCA panelde görünüyordu; nöbetçi/yönetici
o an ekrana bakmıyorsa haberi olmuyordu.

Mimari karar: yeni/ayrı bir "Telegram Ayarları" tablosu/ekranı AÇMAK yerine,
zaten var olan (ama panelde hiçbir arayüzü olmayan, yalnızca API'den
kullanılabilen -- bkz. models.BildirimAyarlari ve main.py'deki "BİLDİRİM
AYARLARI (Webhook)" bölümü) genel bildirim altyapısına YENİ bir `tip` olarak
eklendi: `tip="telegram"`, `hedef=<chat_id>`. Bot TOKEN'ı (tüm kurulum için
TEK, gizli bir değer) `PTS_KAMERA_ANAHTARI` ile aynı desende bir ortam
değişkeninden (`PTS_TELEGRAM_BOT_TOKEN`) okunur -- her bildirim satırına
ayrı ayrı girilmez, panelde/veritabanında düz metin olarak dolaşmaz.

Neden `python-telegram-bot` gibi bir kütüphane değil: Telegram Bot API'nin
`sendMessage` uç noktası tek bir düz HTTPS POST isteği -- proje genelinde
zaten aynı ilkeyle (bkz. main.py::_webhook_gonder_sync) çıplak
`urllib.request` kullanılıyor, buraya da yeni bir bağımlılık eklemeye
gerek yok (bkz. README.md'deki "bağımlılık ayak izini küçük tut" disiplini).
"""
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger("pts")

TELEGRAM_API_KOKU = "https://api.telegram.org"


def bot_token_al() -> Optional[str]:
    """`PTS_TELEGRAM_BOT_TOKEN` ortam değişkenini okur. `.strip()`: aynı
    `PTS_KAMERA_ANAHTARI`'nda gerçek üretimde bulunan hatayla AYNI sınıf
    (Windows'ta kopyala-yapıştırdan gelen görünmez satır sonu/boşluk) --
    bkz. camera_reader.py'deki ilgili kök neden notu."""
    return (os.getenv("PTS_TELEGRAM_BOT_TOKEN") or "").strip() or None


def telegram_ayarli_mi() -> bool:
    return bot_token_al() is not None


# `main.py::_webhook_bildir`/`_kamera_ariza_alarmi_olustur`'un webhook'a
# gönderdiği `veri` sözlüğü olay tipine göre farklı anahtarlar taşıyor
# (ör. kayıt olayında "plaka_no"/"yon", kamera arızasında "kamera_ad", vb.)
# -- burada TÜMÜNÜ tek tek bilmek yerine, sık kullanılan anahtarları
# bulundukları YERDE (varsa) okunaklı bir satıra çeviriyoruz; tanımadığımız
# bir anahtar sessizce atlanır (mesajı şişirmez), hiçbiri hata ÜRETMEZ.
_ETIKETLER = (
    ("mesaj", None),  # ayrı işlenir (bkz. aşağıda), burada tekrar basılmaz
    ("plaka_no", "Plaka"),
    ("plaka", "Plaka"),
    ("kamera_id", "Kamera"),
    ("kamera_ad", "Kamera"),
    ("yon", "Yön"),
    ("tarih_saat", "Zaman"),
    ("guven_skoru", "Güven skoru"),
)


def _mesaj_metni_olustur(veri: dict) -> str:
    """`veri` sözlüğünü (webhook'a gönderilenle AYNI sözlük) okunaklı, tek
    bakışta anlaşılır bir Telegram mesajına çevirir -- ham JSON değil, çünkü
    bu mesaj bir nöbetçinin telefonunda okunacak."""
    olay = veri.get("olay") or veri.get("alarm_tipi") or veri.get("yetki_durumu")
    baslik = f"🔔 PTS: {olay}" if olay else "🔔 PTS Bildirimi"
    satirlar = [baslik]
    if veri.get("mesaj"):
        satirlar.append(str(veri["mesaj"]))
    gorulen = set()
    for anahtar, etiket in _ETIKETLER:
        if etiket is None or anahtar in gorulen:
            continue
        deger = veri.get(anahtar)
        if deger not in (None, ""):
            satirlar.append(f"{etiket}: {deger}")
            gorulen.add(anahtar)
    return "\n".join(satirlar)


def telegram_gonder_sync(chat_id: str, veri: dict) -> "tuple[bool, Optional[str]]":
    """Senkron gönderim -- arka plan thread'inde çağrılmak üzere tasarlandı
    (bkz. main.py::_bildirim_gonder_sync). `(başarılı_mı, hata_mesajı)`
    döner; `hata_mesajı` yalnızca başarısızlıkta doludur ve Telegram'ın
    KENDİ döndürdüğü `description` alanını (varsa) taşır -- "yanlış chat_id"
    ile "bot token geçersiz" ile "ağ hatası" panelde birbirinden AYIRT
    edilebilsin diye (bkz. main.py::bildirim_test_gonder'in yeni `hata`
    alanı)."""
    token = bot_token_al()
    if not token:
        return False, "PTS_TELEGRAM_BOT_TOKEN ortam değişkeni ayarlanmamış"
    chat_id = str(chat_id or "").strip()
    if not chat_id:
        return False, "Telegram chat_id (hedef) boş olamaz"

    govde = json.dumps({"chat_id": chat_id, "text": _mesaj_metni_olustur(veri)}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{TELEGRAM_API_KOKU}/bot{token}/sendMessage",
        data=govde, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "PTS/2.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as yanit:
            yanit.read()
        return True, None
    except urllib.error.HTTPError as exc:
        aciklama = _http_hatasi_aciklamasi(exc)
        logger.warning("Telegram bildirimi gönderilemedi (chat_id=%s): %s", chat_id, aciklama)
        return False, aciklama
    except Exception as exc:
        aciklama = _disaridan_baglanti_hatasi_aciklamasi(exc)
        logger.warning("Telegram bildirimi gönderilemedi (chat_id=%s): %s", chat_id, aciklama)
        return False, aciklama


def _disaridan_baglanti_hatasi_aciklamasi(exc: Exception) -> str:
    """`exc`'in insan-okunur açıklamasını döner; KURUMSAL AĞ SSL İNCELEME/
    PROXY kök nedenini (2026-09-26, gerçek üretimde bulunan hata --
    "CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate
    chain") tanıyıp somut bir çözüm ipucu ekler -- bkz. main.py'nin en
    üstündeki `truststore` enjeksiyonu ve README.md'deki ilgili not.
    main.py::_disaridan_http_hatasi_aciklamasi ile AYNI mantığın bir
    kopyası -- bu modülün kendi kendine yeten (main.py'ye bağımlı olmayan)
    tasarımını korumak için kasıtlı olarak tekrar edildi."""
    aciklama = str(exc)
    if "CERTIFICATE_VERIFY_FAILED" in aciklama:
        aciklama += (
            " -- KURUMSAL AĞDA SSL İNCELEME/PROXY CİHAZI OLABİLİR: "
            "'pip install -r requirements.txt' ile 'truststore' paketinin "
            "kurulu olduğundan emin olup sunucuyu yeniden başlatın "
            "(bkz. README.md'deki 'Kurumsal Ağda SSL Sertifika Hatası' notu)."
        )
    return aciklama


def _http_hatasi_aciklamasi(exc: urllib.error.HTTPError) -> str:
    """Telegram API'si hata gövdesinde JSON `{"ok": false, "description":
    "..."}` döner (ör. "Bad Request: chat not found", "Unauthorized") --
    bu, kullanıcının panelde göreceği anlaşılır hata metnidir; okunamazsa
    (beklenmeyen bir gövde biçimi) HTTPError'ın kendi metnine düşülür."""
    try:
        govde = json.loads(exc.read().decode("utf-8", errors="replace"))
        return govde.get("description") or str(exc)
    except Exception:
        return str(exc)
