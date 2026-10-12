"""
LED Panel Entegrasyon Modülü
----------------------------
Desteklenen modlar:
  - simulate : Gerçek donanım yok, mesaj sadece konsola / veritabanına yazılır (varsayılan).
  - serial   : RS232/USB seri port üzerinden bağlı LED panel (pyserial gerektirir).
  - tcp      : Ağ (Ethernet/WiFi) üzerinden IP adresiyle konuşan LED panel.
  - huidu    : Huidu HD-E62 kontrol kartı (TCP 6101, metin bitmap olarak gönderilir;
               protokol ayrıntıları backend/huidu.py'de).

Ayarlar backend/config.json dosyasında tutulur, panelden (LED Ayarları sekmesi) değiştirilebilir.

Not: Çoğu ticari LED panel kendi metin protokolüne sahiptir (örn. başına/sonuna özel
komut baytları eklemek gerekebilir). "serial" ve "tcp" modlarındaki gönderim fonksiyonlarını
kullandığınız panelin kullanım kılavuzuna göre uyarlamanız gerekebilir; iskelet burada hazır.
"""
import json
import logging
import os
import socket
import threading
import time
from datetime import datetime
from typing import Iterable, Optional, Sequence

from backend import huidu

# DÜZELTME (2026-09-25, sistem taraması): bu modül önceden TÜM durum/hata
# mesajlarını `print()` ile yazıyordu -- bir servis/arka plan sürecinin
# stdout'u tipik olarak hiçbir yerde toplanmaz/görüntülenmez, oysa main.py ve
# camera_reader.py gibi kod tabanının geri kalanı bilinçli olarak `logging`
# modülüne geçmiş durumda (camera_reader.py'nin kendi modül docstring'i bunu
# özellikle "`print()` kullanılmaz -- her şey logging modülü üzerinden
# `/sistem/loglar` uç noktasında görülebilir olmalı" diye vurguluyor). LED
# panel, güvenlik görevlisine "KARA LİSTE / YETKİSİZ ARAÇ" gibi mesajları
# gösteren FİZİKSEL tabeladır -- panel kablosu çıkarsa/IP'ye ulaşılamazsa bu
# önceden HİÇBİR yerde görünmüyordu. "pts.led" alt logger'ı, main.py'de
# tanımlanan "pts" logger'ının (loglar/pts.log dosyasına yazan) handler'ını
# miras alır (bkz. camera_reader.py'nin aynı "pts.camera" deseni), yani bu
# modülün logları da artık /sistem/loglar üzerinden görülebilir.
logger = logging.getLogger("pts.led")

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
# PTS_LED_CONFIG_FILE: normalde ayarlamanıza gerek yok. Test paketi, canlı
# kurulumun LED ayarlarını ezmemek (ve testlerin gönderdiği mesajların gerçek
# panele gitmemesi) için bunu geçici bir dizine yönlendirir.
CONFIG_YOLU = os.getenv("PTS_LED_CONFIG_FILE") or os.path.join(BACKEND_DIR, "config.json")

VARSAYILAN_AYARLAR = {
    "led_mod": "simulate",       # simulate | serial | tcp | huidu
    "serial_port": "COM3",
    "serial_baudrate": 9600,
    "tcp_host": "192.168.1.50",
    "tcp_port": 5000,
    "huidu_host": "172.17.1.224",
    "huidu_port": huidu.VARSAYILAN_PORT,
    "huidu_iki_bolge": False,    # panel 32 px yüksekse (ör. 64x32) True: 1. satır üst, 2. satır alt bölgeye
    "huidu_genislik": huidu.VARSAYILAN_GORUNUR_GENISLIK,  # panelin gösterdiği sütun sayısı (NİZAMİYE: 64)
    # Panelin boştaki yazısı (eski Pts.exe gibi). Araç mesajı `huidu_mesaj_suresi`
    # saniye görünür, sonra bu yazıya dönülür. Boş yazı ya da 0 sn: dönülmez.
    "huidu_bekleme_yazisi": "T.P.A.O.",
    "huidu_bekleme_yazisi_2": "TRAKYA",  # alt satır (iki bölgede alt yarıda, biraz küçük); boş olabilir
    "huidu_mesaj_suresi": 10,
    # Kart, PC'den gelen yazıyı bir süre sonra bırakıp boş ekrana ya da kendi
    # kayıtlı programına dönüyor (2026-10-12 saha: araç geçişinden 15-30 sn sonra,
    # yani T.P.A.O. yazıldıktan ~5-20 sn sonra ekran tamamen boşalıyor). Pts.exe
    # çerçevelerindeki sabit 0x15 (=21) büyük olasılıkla bu gösterim süresi
    # (doğrulanmadı). Araç mesajı yokken bekleme yazısı bu kadar saniyede bir
    # yeniden yazılır (süreden kısa olmalı); 0 = kapalı.
    "huidu_yenileme_sn": 10,
    # Birden çok Huidu paneli: [{"ad", "host", "port", "kameralar": [kamera id, ...]}].
    # Araç mesajı yalnızca o aracın kamerası listede olan panellere gider; boş
    # kamera listesi = tüm kameralar. Liste boşsa huidu_host/huidu_port tek panel
    # olarak kullanılır (eski kurulumlar). Ör. NİZAMİYE paneli yalnızca nizamiye
    # giriş/çıkış kameralarını, LOJMAN paneli yalnızca lojman kameralarını gösterir.
    "huidu_paneller": [],
}


def ayarlari_oku() -> dict:
    if not os.path.exists(CONFIG_YOLU):
        ayarlari_kaydet(VARSAYILAN_AYARLAR)
        return dict(VARSAYILAN_AYARLAR)
    with open(CONFIG_YOLU, "r", encoding="utf-8") as f:
        ayarlar = json.load(f)
    # eksik anahtarları varsayılanla tamamla
    for k, v in VARSAYILAN_AYARLAR.items():
        ayarlar.setdefault(k, v)
    return ayarlar


def ayarlari_kaydet(ayarlar: dict) -> None:
    with open(CONFIG_YOLU, "w", encoding="utf-8") as f:
        json.dump(ayarlar, f, ensure_ascii=False, indent=2)


def led_mesaj_gonder(
    mesaj: str,
    satirlar: Optional[Sequence[str]] = None,
    kamera_idleri: Optional[Iterable[str]] = None,
) -> bool:
    """Ayarlarda seçili moda göre LED panele mesaj gönderir. Başarılıysa True döner.

    `satirlar` verilirse (ör. ("PERSONEL", "34ABC123")) satır tabanlı
    paneller (huidu) metni bu şekilde böler; diğer modlar yalnızca `mesaj`ı kullanır.
    `kamera_idleri`: aracı gören kameranın cameras.json id'leri; huidu modunda
    mesaj yalnızca bu kameraya bağlı panellere gider. None (ör. /led/test): tüm paneller.
    """
    ayarlar = ayarlari_oku()
    mod = ayarlar.get("led_mod", "simulate")

    try:
        if mod == "simulate":
            logger.info("[LED SİMÜLASYON] %s -> %s", datetime.now().strftime("%H:%M:%S"), mesaj)
            return True

        elif mod == "serial":
            try:
                import serial  # pyserial - opsiyonel bağımlılık
            except ImportError:
                logger.error("LED mesajı gönderilemedi: pyserial kurulu değil (kurulum: pip install pyserial)")
                return False
            with serial.Serial(
                ayarlar["serial_port"], ayarlar["serial_baudrate"], timeout=2
            ) as ser:
                ser.write((mesaj + "\r\n").encode("utf-8"))
            return True

        elif mod == "tcp":
            with socket.create_connection(
                (ayarlar["tcp_host"], ayarlar["tcp_port"]), timeout=3
            ) as s:
                s.sendall((mesaj + "\r\n").encode("utf-8"))
            return True

        elif mod == "huidu":
            return _huidu_mesaj_gonder(ayarlar, satirlar or [mesaj], kamera_idleri)

        else:
            logger.error("LED mesajı gönderilemedi: bilinmeyen LED modu '%s'", mod)
            return False

    except Exception as e:
        logger.error("LED mesajı gönderilemedi (mod=%s): %s", mod, e)
        return False


# ------------------------------------------------------------------
# Huidu: paneller, kamera eşleşmesi ve boştaki yazı (T.P.A.O.)
# ------------------------------------------------------------------

def huidu_panelleri(ayarlar: dict) -> list:
    """Ayarlardaki Huidu panellerini normalize eder (bkz. VARSAYILAN_AYARLAR['huidu_paneller'])."""
    paneller = []
    for p in ayarlar.get("huidu_paneller") or []:
        host = str(p.get("host") or "").strip()
        if not host:
            continue
        paneller.append({
            "ad": str(p.get("ad") or "").strip() or host,
            "host": host,
            "port": int(p.get("port") or huidu.VARSAYILAN_PORT),
            "kameralar": [str(k) for k in (p.get("kameralar") or [])],
        })
    if not paneller:
        paneller.append({
            "ad": ayarlar["huidu_host"], "host": ayarlar["huidu_host"],
            "port": int(ayarlar["huidu_port"]), "kameralar": [],
        })
    return paneller


def _panel_kameraya_ait_mi(panel: dict, kamera_idleri: Optional[Iterable[str]]) -> bool:
    if not panel["kameralar"] or kamera_idleri is None:
        return True
    return bool(set(panel["kameralar"]) & set(kamera_idleri))


class _PanelDurumu:
    """Panel başına: araç mesajı "nesil"i ve bekleme yazısı zamanlayıcısı.

    Her araç mesajı nesli artırır; zamanlayıcı tetiklendiğinde bu arada o panele
    yeni bir mesaj geldiyse (nesil değiştiyse) bekleme yazısını GÖNDERMEZ. Kilit,
    "kontrol et + gönder"in yeni bir mesajla iç içe geçip onu ezmesini önler."""

    def __init__(self):
        self.kilit = threading.Lock()
        self.nesil = 0
        self.zamanlayici: Optional[threading.Timer] = None
        self.son_mesaj: Optional[float] = None   # son araç mesajı (time.monotonic)
        self.son_yazim: Optional[float] = None   # panele son başarılı yazım (bekleme ya da mesaj)


_panel_durumlari: dict = {}
_durumlar_kilidi = threading.Lock()


def _durum(panel: dict) -> _PanelDurumu:
    with _durumlar_kilidi:
        return _panel_durumlari.setdefault((panel["host"], panel["port"]), _PanelDurumu())


def _huidu_mesaj_gonder(ayarlar: dict, satirlar: Sequence[str], kamera_idleri: Optional[Iterable[str]]) -> bool:
    if kamera_idleri is not None:
        kamera_idleri = list(kamera_idleri)
    hedefler = [p for p in huidu_panelleri(ayarlar) if _panel_kameraya_ait_mi(p, kamera_idleri)]
    if not hedefler:
        logger.info("LED: bu kameraya bağlı Huidu paneli yok (kamera id=%s), panele yazılmadı", kamera_idleri)
        return True
    basarili = True
    for panel in hedefler:
        durum = _durum(panel)
        try:
            with durum.kilit:
                durum.nesil += 1
                durum.son_mesaj = time.monotonic()
                try:
                    huidu.gonder(
                        panel["host"], panel["port"], satirlar=satirlar,
                        iki_bolge=bool(ayarlar["huidu_iki_bolge"]),
                        genislik=int(ayarlar["huidu_genislik"]),
                    )
                    durum.son_yazim = time.monotonic()
                finally:
                    # Gönderim yarıda kalsa da (ör. kart o an meşgul) panel bekleme
                    # yazısına dönsün; önceden yarım mesajla kalabiliyordu.
                    _bekleme_yazisini_zamanla(ayarlar, panel, durum)
        except Exception as e:  # bir panel hatası diğerlerini engellemesin
            logger.error("LED mesajı gönderilemedi (mod=huidu, panel=%s): %s", panel["ad"], e)
            basarili = False
    return basarili


def _bekleme_yazisini_zamanla(ayarlar: dict, panel: dict, durum: _PanelDurumu) -> None:
    """durum.kilit tutulurken çağrılır."""
    if durum.zamanlayici is not None:
        durum.zamanlayici.cancel()
        durum.zamanlayici = None
    sure = float(ayarlar.get("huidu_mesaj_suresi") or 0)
    if sure <= 0 or not str(ayarlar.get("huidu_bekleme_yazisi") or "").strip():
        return
    durum.zamanlayici = threading.Timer(sure, _bekleme_yazisina_don, args=(panel, durum.nesil))
    durum.zamanlayici.daemon = True
    durum.zamanlayici.start()


def _bekleme_yazisina_don(panel: Optional[dict] = None, nesil: Optional[int] = None) -> bool:
    """Bekleme yazısını panele (panel None ise tüm panellere) yazar. `nesil`
    verilmişse yalnızca o mesajdan sonra o panele yeni mesaj gelmediyse yazar.
    Huidu modunda değilse ya da yazı boşsa hiçbir şey yapmaz."""
    ayarlar = ayarlari_oku()
    yazi = str(ayarlar.get("huidu_bekleme_yazisi") or "").strip()
    if ayarlar.get("led_mod") != "huidu" or not yazi:
        return False
    guncel = huidu_panelleri(ayarlar)
    if panel is not None:
        # Zamanlayıcı kurulduktan sonra panel ayarlardan çıkarıldıysa yazma.
        guncel = [p for p in guncel if (p["host"], p["port"]) == (panel["host"], panel["port"])]
    basarili = bool(guncel)
    for p in guncel:
        durum = _durum(p)
        with durum.kilit:
            if nesil is not None and nesil != durum.nesil:
                basarili = False
                continue
            try:
                huidu.bekleme_yazisi_gonder(
                    p["host"], p["port"],
                    ust=yazi,
                    alt=str(ayarlar.get("huidu_bekleme_yazisi_2") or ""),
                    iki_bolge=bool(ayarlar["huidu_iki_bolge"]),
                    genislik=int(ayarlar["huidu_genislik"]),
                )
                durum.son_yazim = time.monotonic()
            except Exception as e:
                logger.error("LED bekleme yazısı gönderilemedi (mod=huidu, panel=%s): %s", p["ad"], e)
                basarili = False
    return basarili


def bekleme_yazisini_goster_arka_planda() -> None:
    """PTS açılışında / LED ayarları kaydedilince bekleme yazısını panellere yazar.
    Panel ulaşılamazsa isteği/açılışı bekletmemek için ayrı iş parçacığında çalışır."""
    threading.Thread(target=_bekleme_yazisina_don, name="led-bekleme-yazisi", daemon=True).start()


# ------------------------------------------------------------------
# Huidu: bekleme yazısını düzenli yenileme (2026-10-12)
# ------------------------------------------------------------------

def _panel_bosta_mi(durum: _PanelDurumu, ayarlar: dict, simdi: float) -> bool:
    """Araç mesajı gösterilmiyorsa True. Mesaj süresi 0 ise (mesaj kalıcı) son
    mesajdan sonra panel boşta sayılmaz -- mesajın üzerine yazılmasın."""
    if durum.son_mesaj is None:
        return True
    sure = float(ayarlar.get("huidu_mesaj_suresi") or 0)
    return sure > 0 and simdi - durum.son_mesaj >= sure


def bekleme_yazisini_yenile_tik(simdi: Optional[float] = None) -> int:
    """Boştaki ve son yazımı `huidu_yenileme_sn`den eski panellere bekleme
    yazısını yeniden yazar; yazılan panel sayısını döner. Arka plan döngüsü
    (bkz. bekleme_yenileyicisini_baslat) bunu birkaç saniyede bir çağırır."""
    ayarlar = ayarlari_oku()
    aralik = float(ayarlar.get("huidu_yenileme_sn") or 0)
    if ayarlar.get("led_mod") != "huidu" or aralik <= 0:
        return 0
    simdi = time.monotonic() if simdi is None else simdi
    yazilan = 0
    for panel in huidu_panelleri(ayarlar):
        durum = _durum(panel)
        if not _panel_bosta_mi(durum, ayarlar, simdi):
            continue
        if durum.son_yazim is not None and simdi - durum.son_yazim < aralik:
            continue
        if _bekleme_yazisina_don(panel, durum.nesil):  # arada mesaj gelirse nesil değişir, yazmaz
            yazilan += 1
        # Başarısızsa da: ulaşılamayan panel her turda (5 sn) denenmesin, aralıkta bir denensin.
        durum.son_yazim = simdi
    return yazilan


_yenileyici_baslatildi = False


def bekleme_yenileyicisini_baslat(tur_sn: float = 5.0) -> None:
    """Uygulama açılışında bir kez çağrılır (main.py startup)."""
    global _yenileyici_baslatildi
    if _yenileyici_baslatildi:
        return
    _yenileyici_baslatildi = True

    def _dongu():
        while True:
            time.sleep(tur_sn)
            try:
                bekleme_yazisini_yenile_tik()
            except Exception:
                logger.exception("LED bekleme yazısı yenileme turunda hata")

    threading.Thread(target=_dongu, name="led-bekleme-yenileyici", daemon=True).start()
