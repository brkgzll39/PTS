"""Expo Push Notifications API üzerinden mobil uygulamaya (React Native/
Expo) anlık bildirim gönderimi.

2026-09-27 kullanıcı isteği: "daha profesyonel mobil uygulama" -- alarm/olay
bildirimlerinin telefona, uygulama kapalıyken bile push bildirimi olarak
düşmesi istendi.

Mimari karar: telegram_bildirim.py ile AYNI yerleşik desen -- yeni/ayrı bir
"Push Ayarları" tablosu/ekranı AÇMAK yerine, zaten var olan genel bildirim
altyapısına (bkz. models.BildirimAyarlari, main.py::_bildirim_gonder_sync)
YENİ bir `tip` olarak eklendi: `tip="push"`.

TELEGRAM'DAN FARKI (bilinçli tasarım): Telegram'da `hedef` (chat_id)
gönderim adresinin KENDİSİDİR -- tek bir sabit hedef. Push bildirimde ise
tek bir "hedef adres" yok; kayıtlı HER cihaza (mobil uygulamayı kurup giriş
yapmış her kullanıcıya) gidebilir. Bu yüzden burada `hedef` alanı bir ADRES
değil, hangi ROL'e gönderileceğini belirten bir FİLTRE metnidir:
"yonetici" | "izleyici" | "operatör" | "güvenlik" | "hepsi" (boş/"hepsi" =
filtre yok, kayıtlı TÜM cihazlara gönderilir). Gerçek adresler (Expo push
token'ları) models.PushToken tablosunda saklanır ve gönderim ANINDA
veritabanından okunur -- bu, bu modülün (telegram_bildirim.py'nin aksine)
database/models'a bağımlı olmasının nedenidir; push bildirimin doğası
gereği (tokenlar veritabanında yaşadığı için) tam anlamıyla self-contained
tutulamadı.

Neden `python-telegram-bot`/`exponent-server-sdk` gibi bir kütüphane değil:
Expo'nun push API'si de tek bir düz HTTPS POST isteği -- proje genelinde
zaten aynı ilkeyle (bkz. main.py::_webhook_gonder_sync,
telegram_bildirim.py) çıplak `urllib.request` kullanılıyor, buraya da yeni
bir bağımlılık eklemeye gerek yok (bkz. README.md'deki "bağımlılık ayak
izini küçük tut" disiplini). Expo'nun API'si açık/anahtarsızdır -- gönderim
için hiçbir gizli anahtar/hesap gerekmez, yalnızca alıcı cihazların
"ExponentPushToken[...]" değerleri yeterlidir.
"""
import json
import logging
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger("pts")

EXPO_PUSH_API = "https://exp.host/--/api/v2/push/send"

# main.py::_bildirim_tetikle ile AYNI etiket eşleme mantığı (bkz.
# telegram_bildirim.py::_ETIKETLER) -- webhook/telegram'a gönderilen `veri`
# sözlüğü olay tipine göre farklı anahtarlar taşır, tanımadığımız bir anahtar
# sessizce atlanır, hiçbiri hata ÜRETMEZ.
_ETIKETLER = (
    ("plaka_no", "Plaka"),
    ("plaka", "Plaka"),
    ("kamera_id", "Kamera"),
    ("kamera_ad", "Kamera"),
    ("yon", "Yön"),
)


def _bildirim_metni_olustur(veri: dict) -> "tuple[str, str]":
    """`veri` sözlüğünü push bildiriminin (başlık, gövde) çiftine çevirir --
    Telegram'daki tek uzun metnin aksine, bir push bildirimi kısa bir başlık
    + tek satırlık özet olarak en iyi okunur (telefonun bildirim
    merkezinde/kilit ekranında görünen budur)."""
    olay = veri.get("olay") or veri.get("alarm_tipi") or veri.get("yetki_durumu")
    baslik = f"PTS: {olay}" if olay else "PTS Bildirimi"
    parcalar = []
    if veri.get("mesaj"):
        parcalar.append(str(veri["mesaj"]))
    gorulen = set()
    for anahtar, etiket in _ETIKETLER:
        if anahtar in gorulen:
            continue
        deger = veri.get(anahtar)
        if deger not in (None, ""):
            parcalar.append(f"{etiket}: {deger}")
            gorulen.add(anahtar)
    govde = " · ".join(parcalar) if parcalar else "Yeni bir olay kaydedildi."
    return baslik, govde


def _kayitli_tokenlari_al(hedef_rol: str) -> "list[str]":
    """`hedef_rol` boş/"hepsi" ise TÜM kayıtlı cihazların, aksi halde yalnızca
    o role sahip kullanıcıların cihazlarının Expo push token'larını döner.
    Kendi kısa ömürlü DB oturumunu açar/kapatır (bkz. main.py::
    _kamera_ariza_alarmi_olustur'daki AYNI "arka plan thread'i kendi
    SessionLocal()'ını açar" deseni) -- bu fonksiyon arka plan thread'inde
    çağrıldığı için ana istek döngüsünün oturumunu PAYLAŞAMAZ."""
    from backend.database import SessionLocal
    from backend import models

    db = SessionLocal()
    try:
        sorgu = db.query(models.PushToken.expo_push_token)
        hedef_rol = (hedef_rol or "").strip()
        if hedef_rol and hedef_rol != "hepsi":
            sorgu = sorgu.join(models.Kullanici, models.Kullanici.id == models.PushToken.kullanici_id).filter(
                models.Kullanici.rol == hedef_rol
            )
        return [t for (t,) in sorgu.all()]
    except Exception as exc:
        logger.error("Push token listesi okunamadı: %s", exc)
        return []
    finally:
        db.close()


def expo_push_gonder_sync(hedef_rol: str, veri: dict) -> "tuple[bool, Optional[str]]":
    """Senkron gönderim -- arka plan thread'inde çağrılmak üzere tasarlandı
    (bkz. main.py::_bildirim_gonder_sync, telegram_gonder_sync ile AYNI
    `(başarılı_mı, hata_mesajı)` dönüş biçimi)."""
    tokenlar = _kayitli_tokenlari_al(hedef_rol)
    if not tokenlar:
        return False, "Kayıtlı mobil cihaz (push token) bulunamadı -- kimse uygulamayı kurup giriş yapmamış olabilir"

    baslik, govde_metni = _bildirim_metni_olustur(veri)
    mesajlar = [
        {"to": t, "title": baslik, "body": govde_metni, "sound": "default", "priority": "high"}
        for t in tokenlar
    ]
    govde = json.dumps(mesajlar, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        EXPO_PUSH_API, data=govde, method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "PTS/2.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as yanit:
            sonuc = json.loads(yanit.read().decode("utf-8"))
    except Exception as exc:
        aciklama = _baglanti_hatasi_aciklamasi(exc)
        logger.warning("Expo push bildirimi gönderilemedi (%d cihaz): %s", len(tokenlar), aciklama)
        return False, aciklama

    # Expo, gönderilen dizideki HER mesaj için ayrı bir durum döner --
    # bazı token'lar geçersiz/kayıt silinmiş olabilir, bu TÜM gönderimi
    # başarısız SAYMAZ (kısmi başarı normaldir, ör. bir kullanıcı
    # uygulamayı telefonundan sildiyse o token artık geçersizdir).
    sonuclar = sonuc.get("data", []) if isinstance(sonuc, dict) else []
    basarili = sum(1 for s in sonuclar if isinstance(s, dict) and s.get("status") == "ok")
    if sonuclar and basarili == 0:
        ilk_hata = next((s.get("message") for s in sonuclar if isinstance(s, dict)), None)
        return False, f"Expo push API tüm gönderimleri reddetti: {ilk_hata or 'bilinmeyen hata'}"
    logger.info("Push bildirimi gönderildi: %d/%d cihaz başarılı", basarili, len(tokenlar))
    return True, None


def _baglanti_hatasi_aciklamasi(exc: Exception) -> str:
    """main.py::_disaridan_http_hatasi_aciklamasi /
    telegram_bildirim.py::_disaridan_baglanti_hatasi_aciklamasi ile AYNI
    kurumsal SSL inceleme/proxy tanıma mantığının bir kopyası -- bu
    modülün de kendi başına anlaşılır hata üretebilmesi için kasıtlı
    olarak tekrar edildi (bkz. o modüllerdeki AYNI gerekçe)."""
    aciklama = str(exc)
    if "CERTIFICATE_VERIFY_FAILED" in aciklama:
        aciklama += (
            " -- KURUMSAL AĞDA SSL İNCELEME/PROXY CİHAZI OLABİLİR: "
            "'pip install -r requirements.txt' ile 'truststore' paketinin "
            "kurulu olduğundan emin olup sunucuyu yeniden başlatın "
            "(bkz. README.md'deki 'Kurumsal Ağda SSL Sertifika Hatası' notu)."
        )
    return aciklama
