"""
PTS - Plaka Tanıma Sistemi - Ana Uygulama
==========================================
Çalıştırma: uvicorn main:app --reload
Tarayıcıda açın: http://localhost:8000
"""
import os
import re
import hashlib
import hmac
import json
import tempfile
import logging
from logging.handlers import RotatingFileHandler
import secrets
import shutil
import threading
import time
import uuid
import base64
import asyncio
from collections import deque
from urllib.parse import urlsplit, urlunsplit, urlparse
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Query, Body, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_, and_, false, select

from backend import models
from backend import schemas
from backend.database import engine, get_db, Base, SessionLocal
from backend.database import SQLALCHEMY_DATABASE_URL
from backend import excel_export
from backend import pdf_export
from backend import led_panel
from backend import lisans as lisans_modulu
from backend.vardiya_eslestirme import kayitlari_oturumlarla_eslestir
from backend import kucuk_gorsel
from backend import telegram_bildirim
from backend.metin_araclari import levenshtein_mesafesi, en_yakin_bilinen_plakayi_bul, plaka_hucresini_ayir

# ---------------------- KLASÖR AYARLARI ----------------------
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJE_KOKU = os.path.dirname(BACKEND_DIR)
GORUNTU_KLASORU = os.path.join(PROJE_KOKU, "goruntuler")
DISA_AKTAR_KLASORU = os.path.join(PROJE_KOKU, "disa_aktarilanlar")
FRONTEND_KLASORU = os.path.join(PROJE_KOKU, "frontend")
# PTS_LICENSE_FILE / PTS_CAMERAS_FILE: normalde ayarlamanıza gerek yok (varsayılan
# yol kullanılır). Test paketi, gerçek bir kurulumun license.json/cameras.json
# dosyalarını ezmemek için bunları geçici bir dizine yönlendirir.
LISANS_DOSYASI = os.getenv("PTS_LICENSE_FILE") or os.path.join(BACKEND_DIR, "license.json")
KAMERA_DOSYASI = os.getenv("PTS_CAMERAS_FILE") or os.path.join(BACKEND_DIR, "cameras.json")
LOG_KLASORU = os.path.join(PROJE_KOKU, "loglar")
os.makedirs(GORUNTU_KLASORU, exist_ok=True)
os.makedirs(DISA_AKTAR_KLASORU, exist_ok=True)
os.makedirs(LOG_KLASORU, exist_ok=True)

logger = logging.getLogger("pts")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _log_dosyasi = RotatingFileHandler(
        os.path.join(LOG_KLASORU, "pts.log"), maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    _log_dosyasi.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(_log_dosyasi)

Base.metadata.create_all(bind=engine)
logger.info("PTS uygulaması başlatıldı")
if os.getenv("PTS_ARKASINDA_TERS_VEKIL", "").strip().lower() not in ("1", "true", "evet"):
    logger.warning(
        "HTTPS hatırlatması: PTS varsayılan olarak düz HTTP ile çalışır. İnternete açık veya "
        "güvenilmeyen bir ağdaysanız IIS/nginx gibi bir ters vekil arkasında TLS sonlandırması "
        "yapılandırın (bkz. README 'Üretim Ortamı Notları'). Bunu zaten yaptıysanız bu uyarıyı "
        "susturmak için PTS_ARKASINDA_TERS_VEKIL=1 ortam değişkenini ayarlayabilirsiniz."
    )

# ================================================================
# VERİTABANI MİGRASYONU — mevcut tablolara yeni sütun ekler
# ================================================================

_SUTUN_ZATEN_VAR_IPUCLARI = (
    "duplicate column",              # SQLite
    "already exists",                 # SQLite (bazı sürümler) / genel
    "there is already a column",      # SQL Server
    "column names in each table must be unique",  # SQL Server
)


def _sutun_zaten_var_hatasi_mi(exc: Exception) -> bool:
    """ALTER TABLE hatasının 'bu sütun zaten var' (beklenen, zararsız — bu
    migrasyon her başlangıçta yeniden denenir) mi yoksa GERÇEK bir sorun
    (izin, kilit, tip uyuşmazlığı, sözdizimi) mi olduğunu ayırt eder."""
    mesaj = str(exc).lower()
    return any(ipucu in mesaj for ipucu in _SUTUN_ZATEN_VAR_IPUCLARI)


def _veritabani_migrasyon() -> None:
    """create_all yeni sütun eklemez; bu fonksiyon ALTER TABLE ile tamamlar.

    ÖNEMLİ (2026-09-16 düzeltmesi): önceden HER hata (sütun zaten var mı,
    yoksa gerçek bir izin/kilit/sözdizimi hatası mı fark etmeksizin) sessizce
    yutuluyordu — SQLite'ta sorunsuz çalışan bir ifade SQL Server'da farklı
    bir sebeple başarısız olsa bile bu asla loglanmaz, şema sessizce eksik
    kalabilirdi. Artık yalnızca 'sütun zaten var' türü (beklenen, her
    başlangıçta yeniden denendiği için normal) hatalar sessiz geçilir; başka
    her şey `loglar/pts.log`'a uyarı olarak yazılır."""
    sqlite_mod = SQLALCHEMY_DATABASE_URL.startswith("sqlite")
    col_kw = "COLUMN " if sqlite_mod else ""
    bool_tip = "INTEGER DEFAULT 0" if sqlite_mod else "BIT DEFAULT 0"
    # SQL SERVER TUZAĞI (2026-09-17 canlı ortamda bulunan hata): "ADD <col>
    # BIT DEFAULT 0" bir SQL Server ALTER TABLE'ında -- sütun NULL kabul
    # ediyorsa (NOT NULL verilmediği için ediyor) -- yeni eklenen bu DEFAULT'u
    # yalnızca BUNDAN SONRA eklenecek satırlara uygular; TABLODA HALİHAZIRDA
    # VAR OLAN satırlar "WITH VALUES" açıkça belirtilmedikçe NULL kalır.
    # SQLite'ta ise ADD COLUMN ... DEFAULT zaten var olan satırları da o
    # değerle doldurur -- bu yüzden SQLite/SQL Server burada FARKLI davranıyor
    # ve bu fark test edilmeden fark edilemedi (testler SQLite kullanıyor).
    # Sonuç: kullanıcının gerçek SQL Server veritabanında manuel_giris sütunu
    # eklendiğinde, migrasyondan ÖNCE var olan TÜM kayıtlarda bu alan NULL
    # kaldı; schemas.KayitCevap.manuel_giris ise `bool` (Optional değil) olduğu
    # için Pydantic bunu doğrulayamadı ve /kayitlar gibi uçlar
    # ResponseValidationError ile 500 patlıyordu.
    bit_sonu = "" if sqlite_mod else " WITH VALUES"
    adimlar = [
        f"ALTER TABLE kisiler ADD {col_kw}giris_saati_baslangic VARCHAR(5)",
        f"ALTER TABLE kisiler ADD {col_kw}giris_saati_bitis VARCHAR(5)",
        f"ALTER TABLE kisiler ADD {col_kw}izin_verilen_gunler VARCHAR(20)",
        f"ALTER TABLE bariyer_ayarlari ADD {col_kw}auto_ac {bool_tip}{bit_sonu}",
        f"ALTER TABLE plaka_kayitlari ADD {col_kw}ham_plaka_metni VARCHAR(20)",
        f"ALTER TABLE noktalar ADD {col_kw}kamera_id VARCHAR(64)",
        f"ALTER TABLE noktalar ADD {col_kw}bariyer_id INTEGER",
        f"ALTER TABLE plaka_kayitlari ADD {col_kw}dogrulama_kare_sayisi INTEGER",
        f"ALTER TABLE plaka_kayitlari ADD {col_kw}farkli_okuma_sayisi INTEGER",
        # "Dahua ANPR Katkısı" (2026-09-25) -- bkz. models.Kayit.harici_katkili'nin
        # docstring'i. NULL kabul eden, DEFAULT'suz bir BOOLEAN sütun olduğu
        # için (misafir_adi/kisi_id ile AYNI gerekçe) burada "WITH VALUES"
        # ihtiyacı YOK -- var olan (bu alanın hiç hesaplanmadığı) satırlar
        # zaten istenen değer olan NULL'a düşer.
        f"ALTER TABLE plaka_kayitlari ADD {col_kw}harici_katkili {'INTEGER' if sqlite_mod else 'BIT'}",
        f"ALTER TABLE plaka_kayitlari ADD {col_kw}not_metni {'TEXT' if sqlite_mod else 'NVARCHAR(MAX)'}",
        # "Misafir Adı Soyadı" (2026-09-22) -- bkz. models.Kayit.misafir_adi'nin
        # docstring'i. NULL kabul eden, DEFAULT'suz bir metin sütunu olduğu
        # için (aşağıdaki kisi_id ile aynı gerekçe) burada "WITH VALUES"
        # ihtiyacı YOK.
        f"ALTER TABLE plaka_kayitlari ADD {col_kw}misafir_adi VARCHAR(100)",
        # "Arvento Sürücü Kimliği Entegrasyonu" (2026-09-23) -- bkz.
        # models.Kayit.surucu_adi'nin docstring'i. NULL kabul eden,
        # DEFAULT'suz bir metin sütunu olduğu için (misafir_adi ile AYNI
        # gerekçe) burada da "WITH VALUES" ihtiyacı YOK.
        f"ALTER TABLE plaka_kayitlari ADD {col_kw}surucu_adi VARCHAR(100)",
        f"ALTER TABLE plaka_kayitlari ADD {col_kw}manuel_giris {bool_tip}{bit_sonu}",
        f"ALTER TABLE plaka_kayitlari ADD {col_kw}duzenleyen VARCHAR(80)",
        f"ALTER TABLE plaka_kayitlari ADD {col_kw}duzenleme_tarihi DATETIME",
        # "sakin" (site sakini öz-hizmet) rolü: bir giriş hesabını bir Kişi
        # kaydına bağlar. NULL kabul eden, DEFAULT'suz bir INTEGER sütun
        # olduğu için (manuel_giris'teki BIT DEFAULT 0 vakasının aksine) burada
        # "WITH VALUES" ihtiyacı YOK -- var olan satırlarda zaten istenen
        # değer olan NULL'a düşer, ayrıca bir UPDATE gerekmez.
        f"ALTER TABLE kullanicilar ADD {col_kw}kisi_id INTEGER",
        # "Nizamiye Bazlı Kamera Erişimi" (2026-09-21) -- bkz. models.Kullanici.
        # kamera_erisim_listesi'nin docstring'i. NULL kabul eden, DEFAULT'suz
        # bir metin sütunu olduğu için (yukarıdaki kisi_id ile aynı gerekçe)
        # burada da "WITH VALUES" ihtiyacı YOK.
        f"ALTER TABLE kullanicilar ADD {col_kw}kamera_erisim_listesi {'TEXT' if sqlite_mod else 'NVARCHAR(MAX)'}",
        # "Vardiya Grubu Adı" (2026-09-21) -- bkz. models.Kullanici.vardiya_adi'nin
        # docstring'i. NULL kabul eden, DEFAULT'suz bir metin sütunu olduğu
        # için (yukarıdaki kisi_id ile aynı gerekçe) burada da "WITH VALUES"
        # ihtiyacı YOK.
        f"ALTER TABLE kullanicilar ADD {col_kw}vardiya_adi VARCHAR(20)",
        # Yukarıdaki "WITH VALUES" yalnızca BUNDAN SONRA çalışacak taze
        # migrasyonları düzeltir -- kullanıcının veritabanında sütun zaten
        # NULL değerlerle eklenmiş olabileceğinden (birebir bu vakadaki gibi),
        # var olan NULL'ları da açıkça 0'a çeken bu UPDATE HER başlangıçta
        # koşulsuz çalıştırılıyor (WHERE koşulu sayesinde etkisiz/idempotent --
        # düzeltilecek satır kalmadıysa hiçbir şey değiştirmez).
        "UPDATE plaka_kayitlari SET manuel_giris = 0 WHERE manuel_giris IS NULL",
    ]
    with engine.connect() as conn:
        for sql in adimlar:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception as exc:
                try:
                    conn.rollback()
                except Exception:
                    pass
                if _sutun_zaten_var_hatasi_mi(exc):
                    logger.debug("Migrasyon adımı atlandı (sütun zaten var): %s", sql)
                else:
                    logger.warning("Migrasyon adımı başarısız oldu: %s — hata: %s", sql, exc)

_veritabani_migrasyon()

# ================================================================
# SİSTEM AYARLARI (JSON dosyasında saklanan yapılandırma)
# ================================================================

SISTEM_AYARLARI_DOSYASI = os.getenv("PTS_SISTEM_AYARLARI_FILE") or os.path.join(BACKEND_DIR, "sistem_ayarlari.json")
_VARSAYILAN_AYARLAR = {
    "supheli_esik": 3,           # saatte kaç red → şüpheli alarm
    "goruntu_saklama_gun": 30,   # görüntü saklama süresi (gün)
    # AYNI KAMERANIN kendi tekrarını bastırma gecikmesi (sn) -- örn. bir araç
    # bariyer önünde birkaç saniye beklerse, aynı pipeline aynı plakayı tekrar
    # tekrar "yeni bir geçiş" olarak bildirmesin diye (bkz.
    # camera_reader.py::KameraPipeline.son_plaka_zamani/tekrar_gecikme_sn).
    # DÜZELTME (2026-09-18): bu ayar ÖNCEDEN burada tanımlıydı ama HİÇBİR
    # yerde okunmuyordu -- _pipeline_baslat her zaman KameraPipeline'ın kendi
    # sabit varsayılanını (30) kullanıyordu, panelden değiştirilse bile hiçbir
    # etkisi olmuyordu (sessiz/etkisiz ayar). Artık gerçekten uygulanıyor.
    "tekrar_gecikme_sn": 30,
    # FARKLI KAMERALAR ARASI kısa süreli tekrar penceresi (sn) -- 2026-09-18,
    # kullanıcı talebi: giriş kamerası bir aracı kaydettikten sonra araç
    # geçişine devam ederken çıkış kamerasının görüş açısına da girebiliyor
    # (iki kamera fiziksel olarak aynı geçidi/yolu paylaşıyor) -- bu TEK bir
    # fiziksel geçiş olmasına rağmen ikinci kamera bunu AYRI (yanlış yönde)
    # bir kayıt olarak düşürmemeli. tekrar_gecikme_sn'den FARKLIDIR: o AYNI
    # kameranın kendi belleğinde çalışır (camera_reader.py), bu ise TÜM
    # kameraların ortak gerçek kaynağı olan veritabanı seviyesinde, FARKLI
    # kamera_id'ler arasında çalışır (bkz. main.py::
    # _capraz_kamera_kisa_sureli_tekrar_mi). 0 veya negatif = özellik kapalı.
    "capraz_kamera_tekrar_penceresi_sn": 180,
    "auto_bariyer_giris": False, # yetkili girişte otomatik bariyer
    "panel_yenileme_sn": 15,     # frontend polling aralığı
    "min_tanima_guveni": 0.4,    # bu eşiğin altındaki OCR okumaları hiç DEĞERLENDİRMEYE (oy
                                 # birikimine) bile girmez -- bkz. camera_reader.py::min_guven_skoru,
                                 # yalnızca kameranın kendi in-process pipeline'ı için geçerlidir.
    "bilinen_plaka_duzeltme_aktif": True,  # bkz. _bilinen_plakaya_yakinlik_duzelt
    # "min_tanima_guveni"nden FARKLI bir eşiktir (2026-09-17): o, tek tek OCR
    # okumalarının oy birikimine girip girmeyeceğine bakar (yalnızca in-process
    # kamera pipeline'ında). Bu ayar ise OTURUM KAPANIP nihai/tek bir güven
    # skoru belirlendikten SONRA, bir tespitin panele/kayıtlara HİÇ
    # düşürülüp düşürülmeyeceğine bakar -- hem in-process pipeline'dan hem de
    # /kayitlar/otomatik'e doğrudan istek atan harici bir ANPR sisteminden
    # gelen TÜM otomatik tespitlere uygulanır (bkz. kayit_ekle_otomatik).
    # Kullanıcı talebi: yalnızca %97-%100 güvenli tespitler kayda düşsün,
    # geri kalanı (hatalı/yanlış okunup kayıtları şişiren düşük güvenli
    # tespitler) hiç kaydedilmesin. Elle girilen kayıtları (manuel_giris=True,
    # bkz. kayit_ekle_manuel) ETKİLEMEZ -- personel bilinçli olarak girdiği
    # bir kaydın OCR güveniyle değerlendirilmemesi gerektiği için.
    "otomatik_kayit_min_guven_skoru": 0.97,
    # BİLİNEN ARAÇ İSTİSNASI (2026-09-17, devam): kullanıcının kendi aracı
    # girişte %96.6 güvenle okundu ama genel eşik (%97) altında kaldığı için
    # o geçiş HİÇ KAYDEDİLMEDİ (bkz. _bilinen_plakaya_yakin_mi'nin
    # docstring'i). Genel eşik esasen SİSTEMDE KAYITLI OLMAYAN plakaların
    # (yanlış OCR okumaları) kayıtları şişirmesini önlemek içindir; sahada
    # zaten kayıtlı (abone/personel) bir plakayla TAM ya da tek karakter
    # farkla eşleşen bir tespit için bu, daha düşük/daha toleranslı bir ikinci
    # eşiktir. Bu eşiğin de altına düşen tespitler (bilinen araç olsa bile)
    # yine atlanır -- bu bir güvenlik tabanı değil, yalnızca "muhtemelen
    # doğru okunmuş bilinen bir araç" ile "muhtemelen gerçekten hatalı okuma"
    # ayrımı içindir.
    "otomatik_kayit_min_guven_skoru_bilinen_arac": 0.80,
    # OTOMATİK VERİTABANI YEDEKLEME (2026-09-25, kullanıcı isteği: "günlük
    # otomatik yedek ekle") -- bkz. _otomatik_yedek_dongu'nun docstring'i.
    # Varsayılan klasör, canlı veritabanının bulunduğu "veritabani" klasörüyle
    # KARIŞMASIN diye kasıtlı olarak ayrı bir üst klasördür (aynı diskte olsa
    # bile en azından tek bir yanlış silme/üzerine yazma işleminin hem canlı
    # veritabanını hem TÜM yedekleri birden götürmesi engellenir); panelden
    # farklı bir diske/yola da ayarlanabilir.
    "otomatik_yedek_aktif": True,
    "otomatik_yedek_klasoru": os.path.join(PROJE_KOKU, "yedekler"),
    "otomatik_yedek_saklama_gun": 30,
    # DİSKİN GERÇEKTEN DOLMASINA KARŞI ERKEN UYARI (2026-09-26, kullanıcı
    # isteği) -- bkz. _disk_izleme_dongu'nun docstring'i. Mevcut "disk_hatasi"
    # alarmından FARKLIDIR: bu, bir yazma FİİLEN başarısız olmadan, disk
    # doluluk YÜZDESİNE bakarak proaktif uyarır.
    "disk_izleme_aktif": True,
    "disk_uyari_esik_yuzde": 90,
}


def _sistem_ayarlari_oku() -> dict:
    if not os.path.exists(SISTEM_AYARLARI_DOSYASI):
        return dict(_VARSAYILAN_AYARLAR)
    try:
        with open(SISTEM_AYARLARI_DOSYASI, "r", encoding="utf-8") as f:
            mevcut = json.load(f)
        return {**_VARSAYILAN_AYARLAR, **mevcut}
    except (OSError, json.JSONDecodeError):
        return dict(_VARSAYILAN_AYARLAR)


def _sistem_ayarlari_yaz(ayarlar: dict) -> None:
    with open(SISTEM_AYARLARI_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(ayarlar, f, ensure_ascii=False, indent=2)


# ================================================================
# KAMERA PİPELİNE YÖNETİCİSİ (opsiyonel — kütüphaneler yoksa devre dışı)
# ================================================================
try:
    from backend.camera_reader import KameraPipeline as _KameraPipeline, KUTUPHANELER_MEVCUT as _CAM_LIBS
except Exception:
    _KameraPipeline = None  # type: ignore[assignment,misc]
    _CAM_LIBS = False

_aktif_pipelineler: dict = {}  # cameras.json id -> KameraPipeline
_pipeline_kilit = threading.Lock()

# DÜZELTME (2026-09-25, sistem taraması): cameras.json'a yapılan TÜM
# "oku -> değiştir -> yaz" işlemleri (kamera ekleme/silme/yeniden adlandırma/
# yön-ROI-aktiflik değiştirme) önceden hiçbir kilit olmadan çalışıyordu.
# FastAPI senkron `def` uç noktaları bir iş parçacığı havuzunda çalıştığı için
# bu GERÇEK bir yarış durumuydu: iki admin/operatör aynı anda farklı
# kameraları düzenlerse (ör. biri kamera A'yı yeniden adlandırırken diğeri
# kamera B'yi aktif/pasif yapıyor), ikinci yazan birincinin değişikliğini
# sessizce silebiliyordu; kamera ekleme tarafında ise lisans kamera limiti
# kontrolü de aynı yarışa açıktı (iki eşzamanlı POST /kameralar isteği,
# limite çok yakınken ikisi de kontrolü geçip limiti aşabiliyordu). Bu kilit,
# ilgili her uç noktanın "oku -> değiştir -> yaz" bloğunu tek seferde bir
# istekle sınırlar. _kameralari_yaz'daki atomik yazma (temp dosya + os.replace)
# ise BU kilitten bağımsız olarak, kilidin dışındaki salt-okuma çağrılarının
# (ör. GET /kameralar) yazma sırasında yarım/bozuk bir JSON okumasını önler.
_kamera_dosya_kilit = threading.Lock()


def _pipeline_baslat(kamera: dict) -> bool:
    if not _CAM_LIBS or _KameraPipeline is None:
        return False
    kid = kamera["id"]
    with _pipeline_kilit:
        if kid in _aktif_pipelineler and _aktif_pipelineler[kid].calisiyor and _aktif_pipelineler[kid].thread_canli_mi():
            return True
        try:
            ayarlar = _sistem_ayarlari_oku()
            # DÜZELTME (2026-09-25): PUT /sistem/ayarlar artık bu değeri
            # yazarken doğruluyor (bkz. _AYAR_DOGRULAYICILAR), ama disk
            # üzerindeki ayar dosyasına doğrulama eklenmeden ÖNCE elle/başka
            # bir yolla bozuk bir değer yazılmış olabileceği ihtimaline karşı
            # burada da (tekrar_gecikme_sn'deki gibi) savunmacı bir try/except
            # bırakılıyor -- amaç, bozuk bir ayar TÜM kameraların 20 sn'de bir
            # sürekli çökmesine değil, en fazla varsayılana geri dönmesine
            # yol açsın.
            try:
                min_guven = float(ayarlar.get("min_tanima_guveni", 0.4) or 0.0)
            except (TypeError, ValueError):
                min_guven = 0.4
            min_guven = max(0.0, min(1.0, min_guven))  # ayar dosyasından gelen değeri emniyete al
            # DÜZELTME (2026-09-18): bu ayar ÖNCEDEN _pipeline_baslat'a hiç
            # geçirilmiyordu -- panelden değiştirilse bile KameraPipeline
            # her zaman kendi sabit varsayılanını (30 sn) kullanıyordu (bkz.
            # _VARSAYILAN_AYARLAR'daki "tekrar_gecikme_sn" notu).
            try:
                tekrar_gecikme_sn = int(ayarlar.get("tekrar_gecikme_sn", 30))
            except (TypeError, ValueError):
                tekrar_gecikme_sn = 30
            p = _KameraPipeline(
                video_kaynagi=kamera["rtsp_url"],
                kamera_id=kamera["ad"],
                yon=kamera.get("yon", "giris"),
                min_guven_skoru=min_guven,
                roi=kamera.get("roi"),
                tekrar_gecikme_sn=max(0, tekrar_gecikme_sn),
                # 2026-09-25: kameranın kendi ANPR okuması (Dahua) açıksa
                # pipeline onu da dinleyip oylamaya ekler -- bkz.
                # backend/dahua_olay.py.
                dahua_ayarlari=kamera.get("dahua_anpr"),
            )
            p.baslat()
            _aktif_pipelineler[kid] = p
            logger.info("Pipeline başlatıldı: %s", kamera["ad"])
            return True
        except Exception as exc:
            logger.error("Pipeline başlatılamadı %s: %s", kamera["ad"], exc)
            return False


def _pipeline_durdur(kamera_id: str) -> None:
    with _pipeline_kilit:
        p = _aktif_pipelineler.pop(kamera_id, None)
        if p:
            p.durdur()
            logger.info("Pipeline durduruldu: %s", kamera_id)


# ================================================================
# KAMERA BEKÇİSİ (watchdog) — pipeline'ın gerçekten canlı olduğunu ve
# görüntünün donmadığını periyodik olarak doğrular, gerekirse kendi kendine
# yeniden başlatır. Amaç: kamera bağlantısında/görüntüde operatör müdahalesi
# gerektiren bir "takılma" durumunun sessizce kalıcı olmaması.
# ================================================================
KAMERA_BEKCI_ARALIK_SN = 20
KAMERA_UZUN_SURELI_DONMA_ESIK_SN = 90   # bu kadar süre kesintisiz donuk kalırsa alarm oluştur
KAMERA_ALARM_TEKRAR_ARALIK_SN = 3600     # aynı kamera için alarmı en fazla saatte bir tekrar oluştur

_kamera_donuk_baslangic: dict = {}   # kamera_id -> ilk donma zamanı (monotonic)
_kamera_son_alarm_zamani: dict = {}  # kamera_id -> son "kamera_arizasi" alarmının zamanı (monotonic)


def _kamera_ariza_alarmi_olustur(kamera_ad: str, kamera_id: str, mesaj: str) -> None:
    simdi = time.monotonic()
    son = _kamera_son_alarm_zamani.get(kamera_id)
    if son and (simdi - son) < KAMERA_ALARM_TEKRAR_ARALIK_SN:
        return  # aynı kamera için kısa süre içinde tekrar alarm oluşturma (spam önleme)
    _kamera_son_alarm_zamani[kamera_id] = simdi
    db = SessionLocal()
    try:
        db.add(models.Alarm(
            kayit_id=None,
            plaka_no=kamera_ad or kamera_id,
            alarm_tipi="kamera_arizasi",
            mesaj=mesaj,
        ))
        db.commit()
        logger.error("Kamera arıza alarmı oluşturuldu: %s — %s", kamera_ad, mesaj)

        # Mevcut bildirim sistemine bağla (webhook/telegram, hepsi |
        # kamera_arizasi tetikleyicili olanlar) -- bkz. _bildirim_tetikle.
        try:
            _bildirim_tetikle(db, "kamera_arizasi", {
                "olay": "kamera_arizasi",
                "kamera_id": kamera_id,
                "kamera_ad": kamera_ad,
                "mesaj": mesaj,
            })
        except Exception as exc:
            logger.error("Kamera arıza webhook bildirimi hazırlanamadı: %s", exc)
    except Exception as exc:
        logger.error("Kamera arıza alarmı DB'ye yazılamadı: %s", exc)
    finally:
        db.close()


async def _kamera_bekci_dongu() -> None:
    """Sonsuz döngü: aktif olması gereken her kamera için pipeline'ın gerçekten
    çalıştığını (thread canlı) ve görüntünün taze olduğunu kontrol eder.

    LİSANS UYGULAMASI: Önceden lisans yalnızca YENİ bir kamera eklenirken
    (`POST /kameralar`) kontrol ediliyordu — uygulama açılışında
    (`_kameralari_otomatik_baslat`) `cameras.json`'daki mevcut kameralar
    lisans durumuna HİÇ bakılmadan başlatılıyordu ve bir lisans süresi
    dolduğunda/silindiğinde de HİÇBİR yerde tekrar kontrol edilmiyordu — yani
    "tam lisanslı" bir üründe, süresi dolmuş bir lisansla sistem sınırsız
    çalışmaya devam edebiliyordu. Artık bu döngü her turda lisansı da
    kontrol eder: geçersizse (süre doldu, imza artık geçerli secret ile
    uyuşmuyor, cihaz değişti vb.) TÜM kamera pipeline'ları durdurulur ve bir
    kez (saatte bir tekrarlanan) arıza alarmı oluşturulur; lisans yeniden
    aktive edilene kadar normal sağlık kontrolü/restart mantığı devre dışı
    kalır (aksi halde bu döngü, az önce lisans yüzünden durdurduğu
    pipeline'ı "çökmüş" sanıp hemen yeniden başlatmaya çalışırdı)."""
    while True:
        try:
            if not _lisans_aktif_mi():
                if any(p.calisiyor for p in _aktif_pipelineler.values()):
                    logger.error("[bekci] Lisans aktif değil/süresi dolmuş — tüm kamera pipeline'ları durduruluyor")
                    for kamera in _kameralari_oku():
                        _pipeline_durdur(kamera["id"])
                    _kamera_ariza_alarmi_olustur(
                        "LİSANS", "lisans_durumu",
                        "LİSANS SÜRESİ DOLDU/GEÇERSİZ: tüm kamera pipeline'ları durduruldu. "
                        "Devam etmek için Sistem > Lisans ekranından geçerli bir anahtar girin.",
                    )
                await asyncio.sleep(KAMERA_BEKCI_ARALIK_SN)
                continue

            for kamera in _kameralari_oku():
                if not kamera.get("aktif", True):
                    continue
                kid = kamera["id"]
                p = _aktif_pipelineler.get(kid)

                if p is None or not p.calisiyor or not p.thread_canli_mi():
                    logger.warning("[bekci] Kamera pipeline çalışmıyor/çökmüş, yeniden başlatılıyor: %s", kamera["ad"])
                    _pipeline_durdur(kid)
                    basarili = await asyncio.get_event_loop().run_in_executor(None, _pipeline_baslat, kamera)
                    if not basarili:
                        _kamera_ariza_alarmi_olustur(
                            kamera["ad"], kid,
                            f"KAMERA ÇEVRİMDIŞI: {kamera['ad']} pipeline'ı başlatılamadı (log dosyasını kontrol edin)",
                        )
                    continue

                durum = p.durum_bilgisi()
                if durum["donmus"]:
                    ilk = _kamera_donuk_baslangic.setdefault(kid, time.monotonic())
                    if time.monotonic() - ilk >= KAMERA_UZUN_SURELI_DONMA_ESIK_SN:
                        _kamera_ariza_alarmi_olustur(
                            kamera["ad"], kid,
                            f"KAMERA GÖRÜNTÜSÜ DONDU: {kamera['ad']} {KAMERA_UZUN_SURELI_DONMA_ESIK_SN:.0f} sn üzerinde taze kare almıyor",
                        )
                else:
                    _kamera_donuk_baslangic.pop(kid, None)
        except Exception as exc:
            logger.error("[bekci] Kamera bekçisi döngüsünde hata: %s", exc, exc_info=True)
        await asyncio.sleep(KAMERA_BEKCI_ARALIK_SN)


# ================================================================
# OTOMATİK GÖRÜNTÜ/KAYIT SAKLAMA — disk sürekli dolup sistemi
# (kayıt/görüntü yazma hataları yüzünden) yavaşlatmasın/durdurmasın diye
# "goruntu_saklama_gun" ayarına göre periyodik olarak eski görüntüleri siler.
# Daha önce sadece manuel bir uç nokta (/sistem/goruntu-temizle) vardı; bir
# operatör onu çağırmayı unutursa disk sessizce dolabilirdi.
# ================================================================
GORUNTU_TEMIZLIK_ARALIK_SN = 6 * 3600  # her 6 saatte bir kontrol et


async def _goruntu_temizlik_dongu() -> None:
    """Sonsuz döngü: periyodik olarak sistem ayarlarındaki saklama süresine
    göre eski görüntü dosyalarını temizler. Ayar 0 veya negatifse otomatik
    temizlik devre dışı bırakılmış demektir (manuel uç nokta yine çalışır)."""
    while True:
        try:
            gun = int(_sistem_ayarlari_oku().get("goruntu_saklama_gun") or 0)
            if gun > 0:
                db = SessionLocal()
                try:
                    silinen, sinir = _goruntu_temizle_calistir(gun, db)
                    if silinen:
                        logger.info(
                            "Görüntü temizliği (otomatik): %d dosya silindi (>%d gün, sınır: %s)",
                            silinen, gun, sinir.isoformat(),
                        )
                finally:
                    db.close()
            # Orijinali silinmiş (saklama süresi, kayıt silme, düşük güven
            # temizliği vb.) küçük resimleri de temizle -- bkz. kucuk_gorsel.py.
            yetim = kucuk_gorsel.yetim_kucuk_gorselleri_temizle(GORUNTU_KLASORU)
            if yetim:
                logger.info("Görüntü temizliği: %d yetim küçük resim silindi", yetim)
            eski_rapor = _eski_gecici_raporlari_temizle()
            if eski_rapor:
                logger.info("Geçici rapor/yedek temizliği: %d eski dosya silindi (disa_aktarilanlar/)", eski_rapor)
        except Exception as exc:
            logger.error("[görüntü-temizlik] Otomatik temizlik döngüsünde hata: %s", exc, exc_info=True)
        await asyncio.sleep(GORUNTU_TEMIZLIK_ARALIK_SN)


# ================================================================
# OTOMATİK VERİTABANI YEDEKLEME (2026-09-25, kullanıcı isteği)
# ================================================================
# Önceden veritabanının TEK yedekleme yolu, bir yöneticinin panelden manuel
# olarak /sistem/yedek'i indirmesiydi (bkz. README.md'nin "Üretim Ortamı"
# bölümündeki uyarı). Bir operatör bunu düzenli yapmayı unutursa (ya da
# yapması gerektiğini hiç bilmiyorsa), disk arızası/bozulması durumunda TÜM
# geçiş kayıtları/denetim izi kalıcı olarak kaybolabilirdi -- kullanıcının
# kendisinin belirttiği "görüntülerin 2-3 yıl hiç silinmeden durması"
# hedefiyle de doğrudan çelişen bir risk. Bu bölüm, ayarlarda etkinse
# (varsayılan: etkin), günde bir kez veritabanının TUTARLI bir kopyasını
# ayrı bir klasöre otomatik olarak yazar ve eski yedekleri (varsayılan 30
# gün) otomatik temizler -- görüntü saklama/temizliğiyle AYNI "arka planda
# sessizce çalışan bakım görevi" deseni (bkz. yukarısı).
YEDEK_KONTROL_ARALIK_SN = 6 * 3600  # her 6 saatte bir kontrol et (gerçek yedek günde 1 kez alınır)
OTOMATIK_YEDEK_DOSYA_ONEKI = "pts_otomatik_yedek_"
_VARSAYILAN_YEDEK_KLASORU = os.path.join(PROJE_KOKU, "yedekler")


def _sqlite_yedek_al(kaynak_yolu: str, hedef_yolu: str) -> None:
    """DÜZELTME (2026-09-25): önceden (hem burada eklenen otomatik yedekleme
    hem de mevcut manuel /sistem/yedek uç noktası) veritabanını WAL modunda
    ÇALIŞIRKEN doğrudan dosya kopyalayarak yedekliyordu -- ama WAL modunda
    (bkz. database.py'deki ayrıntılı not) son yazılan işlemler bir süre ana
    ".db" dosyasına değil, yanındaki ".db-wal" dosyasına yazılır; yalnızca
    ana dosyayı kopyalamak bu son işlemleri SESSİZCE KAÇIRABİLİR -- yani bir
    yönetici düzenli yedek alsa bile, geri yükleme sırasında "en son birkaç
    saatlik/dakikalık kayıt nereye kayboldu" sürprizi yaşayabilirdi.
    `sqlite3` modülünün kendi `Connection.backup()` API'si, hedefi KAYNAK
    ÇALIŞIRKEN (okuma/yazmayı kilitlemeden) sayfa sayfa kopyalar ve WAL'daki
    henüz checkpoint yapılmamış içeriği de otomatik olarak dahil eder --
    elle bir "PRAGMA wal_checkpoint" adımına gerek kalmadan tutarlı, TAM bir
    yedek üretir."""
    import sqlite3
    os.makedirs(os.path.dirname(os.path.abspath(hedef_yolu)) or ".", exist_ok=True)
    kaynak = sqlite3.connect(kaynak_yolu)
    try:
        hedef = sqlite3.connect(hedef_yolu)
        try:
            kaynak.backup(hedef)
        finally:
            hedef.close()
    finally:
        kaynak.close()


def _otomatik_yedek_klasoru_al(ayarlar: dict) -> str:
    return str(ayarlar.get("otomatik_yedek_klasoru") or "").strip() or _VARSAYILAN_YEDEK_KLASORU


_YEDEK_BEKLENEN_TABLOLAR = ("plaka_kayitlari", "kullanicilar", "kisiler")


def _yedek_dosyasi_saglam_mi(yol: str) -> "tuple[bool, Optional[str]]":
    """Bir SQLite yedek dosyasının GERÇEKTEN geri yüklenebilir olduğunu
    doğrular (2026-09-26, kullanıcı isteği: "yedek dosyasının gerçekten
    sağlam olduğunu otomatik doğrulama").

    KÖK NEDEN: `_sqlite_yedek_al` (sqlite3 Connection.backup() ile) her gece
    sessizce çalışıyor ve "başarılı" loglanıyordu, ama bu yalnızca kopyalama
    işleminin İSTİSNASIZ tamamlandığını gösterir -- disk yedekleme sırasında
    dolarsa, süreç yarıda kesilirse ya da hedef klasör bozuk bir dosya
    sistemindeyse, sonuçta ortada duran ".db" dosyası panelde/klasörde
    tamamen normal bir yedek gibi GÖRÜNÜR ama gerçek bir geri yükleme
    ihtiyacında (asıl felaket anında) açılamayabilir/eksik olabilir --
    bu ta ki birileri onu geri yüklemeye çalışana kadar fark edilmez.

    İki kontrol yapılır: (1) `PRAGMA integrity_check` -- SQLite'ın kendi
    sayfa/b-tree bütünlük taraması; (2) üretim şemasının temel
    tablolarının GERÇEKTEN var olduğu -- tamamen boş/ilgisiz bir sqlite
    dosyası da integrity_check'ten "ok" geçebilir ama hiçbir PTS verisi
    içermeyebilir, bu da ayrı bir sessiz-başarısızlık türüdür."""
    import sqlite3
    if not os.path.isfile(yol) or os.path.getsize(yol) == 0:
        return False, "Yedek dosyası bulunamadı veya boş"
    try:
        con = sqlite3.connect(f"file:{yol}?mode=ro", uri=True)
    except Exception as exc:
        return False, f"Yedek dosyası açılamadı: {exc}"
    try:
        try:
            sonuc = con.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.DatabaseError as exc:
            return False, f"Yedek dosyası okunamadı (bozuk olabilir): {exc}"
        if not sonuc or sonuc[0] != "ok":
            return False, f"integrity_check başarısız: {sonuc[0] if sonuc else 'sonuç alınamadı'}"
        tablolar = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        eksik = [t for t in _YEDEK_BEKLENEN_TABLOLAR if t not in tablolar]
        if eksik:
            return False, f"Beklenen tablolar eksik: {', '.join(eksik)}"
        return True, None
    finally:
        con.close()


def _yedegi_bozuk_olarak_isaretle(tam_yol: str) -> str:
    """Bütünlük doğrulaması başarısız olan bir otomatik yedeği adında AÇIKÇA
    görülür biçimde işaretler -- dosyayı SİLMEZ (ileride incelenebilsin),
    yalnızca ".BOZUK.db" ile yeniden adlandırır. Saklama süresi dolduğunda
    yine normal temizlik tarafından silinir (bkz. _eski_otomatik_yedekleri_temizle,
    hâlâ ".db" ile bitiyor ve aynı önekle başlıyor)."""
    if tam_yol.endswith(".BOZUK.db"):
        return tam_yol
    if not tam_yol.endswith(".db"):
        return tam_yol
    yeni_yol = tam_yol[: -len(".db")] + ".BOZUK.db"
    try:
        os.replace(tam_yol, yeni_yol)
        _dosyayi_sessizce_sil(tam_yol + ".verified")
        return yeni_yol
    except OSError as exc:
        logger.error("Bozuk yedek yeniden adlandırılamadı '%s': %s", tam_yol, exc)
        return tam_yol


def _yedegi_dogrulandi_olarak_isaretle(tam_yol: str) -> None:
    """Başarıyla doğrulanan bir yedeğin yanına küçük, boş bir işaretçi dosya
    (`<dosya>.verified`) bırakır -- panelin `/sistem/yedek/otomatik-liste`
    yanıtında hangi yedeklerin GERÇEKTEN doğrulandığını (yalnızca alındığını
    değil) süreç yeniden başlasa bile kalıcı olarak gösterebilmesi için.
    Doğrulanmamış (bu özellikten ÖNCEKİ) eski yedeklerle karıştırılmasın."""
    try:
        with open(tam_yol + ".verified", "w", encoding="utf-8") as f:
            f.write(datetime.now().isoformat())
    except OSError as exc:
        logger.error("Yedek doğrulama işaretçisi yazılamadı '%s': %s", tam_yol, exc)


def _eski_otomatik_yedekleri_temizle(klasor: str, saklama_gun: int) -> int:
    if saklama_gun <= 0 or not os.path.isdir(klasor):
        return 0
    sinir = time.time() - saklama_gun * 86400
    silinen = 0
    for ad in os.listdir(klasor):
        if not (ad.startswith(OTOMATIK_YEDEK_DOSYA_ONEKI) and ad.endswith(".db")):
            continue
        tam_yol = os.path.join(klasor, ad)
        try:
            if os.path.getmtime(tam_yol) < sinir:
                os.remove(tam_yol)
                # DÜZELTME (2026-09-26): yedekle BİRLİKTE oluşan doğrulama
                # işaretçisi (bkz. _yedegi_dogrulandi_olarak_isaretle) yedek
                # silinince YETİM kalmasın -- yoksa bu klasörde süresiz
                # birikir.
                _dosyayi_sessizce_sil(tam_yol + ".verified")
                silinen += 1
        except OSError as exc:
            logger.error("[otomatik-yedek] '%s' silinemedi: %s", tam_yol, exc)
    return silinen


def _otomatik_yedek_uret_ve_dogrula(db_yolu: str, klasor: str) -> None:
    """Tek bir otomatik yedek üretir (zaman damgalı dosya adıyla), HEMEN
    bütünlüğünü doğrular ve sonuca göre işaretler/alarm+bildirim üretir
    (bkz. _otomatik_yedek_dongu'nun docstring'i). Döngüden ayrı, kendi
    başına çağrılabilir bir fonksiyon olarak tutulur ki testler (ve
    gerekirse ileride "şimdi yedek al" gibi elle tetiklenen bir uç nokta)
    tek bir "tık"ı, sonsuz döngüyü hiç başlatmadan deterministik biçimde
    çalıştırabilsin."""
    zaman_damgasi = datetime.now().strftime("%Y%m%d_%H%M%S")
    hedef_yol = os.path.join(klasor, f"{OTOMATIK_YEDEK_DOSYA_ONEKI}{zaman_damgasi}.db")
    try:
        _sqlite_yedek_al(db_yolu, hedef_yol)
        # DÜZELTME (2026-09-26, kullanıcı isteği: "yedek dosyasının gerçekten
        # sağlam olduğunu otomatik doğrulama"): kopyalama istisnasız bitse
        # bile sonuçtaki dosya bozuk/eksik olabilir (bkz.
        # _yedek_dosyasi_saglam_mi'nin docstring'i) -- artık HER otomatik
        # yedekten hemen sonra gerçekten geri yüklenebilir mi diye kontrol
        # ediliyor.
        saglam, dogrulama_hatasi = _yedek_dosyasi_saglam_mi(hedef_yol)
        if saglam:
            _yedegi_dogrulandi_olarak_isaretle(hedef_yol)
            logger.info("Otomatik veritabanı yedeği alındı ve bütünlüğü doğrulandı: %s", hedef_yol)
        else:
            bozuk_yol = _yedegi_bozuk_olarak_isaretle(hedef_yol)
            logger.error(
                "Otomatik veritabanı yedeği BOZUK üretildi (%s): %s",
                dogrulama_hatasi, bozuk_yol,
            )
            db = SessionLocal()
            try:
                yedek_mesaji = f"Otomatik veritabanı yedeği bozuk üretildi: {dogrulama_hatasi}"[:255]
                db.add(models.Alarm(plaka_no="SISTEM", alarm_tipi="yedek_bozuk", mesaj=yedek_mesaji))
                db.commit()
                _bildirim_tetikle(db, "yedek_bozuk", {
                    "olay": "yedek_bozuk", "alarm_tipi": "yedek_bozuk", "mesaj": yedek_mesaji,
                })
            except Exception as exc2:
                logger.error("Bozuk yedek alarmı kaydedilemedi: %s", exc2)
            finally:
                db.close()
    except Exception as exc:
        logger.error("Otomatik veritabanı yedeği alınamadı: %s", exc, exc_info=True)


async def _otomatik_yedek_dongu() -> None:
    """Sonsuz döngü: ayarlarda etkinse, günde bir kez veritabanının tutarlı
    bir kopyasını `otomatik_yedek_klasoru`'na yazar (bkz.
    _otomatik_yedek_uret_ve_dogrula) ve `otomatik_yedek_saklama_gun`'dan
    eski otomatik yedekleri temizler. Yalnızca SQLite için çalışır (SQL
    Server kurulumlarında kurumun kendi veritabanı yedekleme araçları
    kullanılmalı, bkz. manuel /sistem/yedek uç noktasındaki aynı
    kısıtlama)."""
    son_yedek_gunu = None
    while True:
        try:
            ayarlar = _sistem_ayarlari_oku()
            if SQLALCHEMY_DATABASE_URL.startswith("sqlite") and ayarlar.get("otomatik_yedek_aktif", True):
                bugun = datetime.now().date()
                if son_yedek_gunu != bugun:
                    db_yolu = urlparse(SQLALCHEMY_DATABASE_URL).path.lstrip("/")
                    klasor = _otomatik_yedek_klasoru_al(ayarlar)
                    if os.path.exists(db_yolu):
                        _otomatik_yedek_uret_ve_dogrula(db_yolu, klasor)
                        # gün başarısız da olsa bir dahaki 6 saatlik kontrolde
                        # HEMEN tekrar denenmesin diye (ör. disk o an geçici
                        # olarak doluysa) gün işaretlenir -- bir sonraki gün
                        # tekrar denenir; kalıcı bir sorun varsa bu, yukarıdaki
                        # error logunda GÖRÜNÜR kalır (sessiz değildir).
                        son_yedek_gunu = bugun
                        try:
                            saklama_gun = int(ayarlar.get("otomatik_yedek_saklama_gun", 30) or 0)
                            silinen = _eski_otomatik_yedekleri_temizle(klasor, saklama_gun)
                            if silinen:
                                logger.info("Eski otomatik yedeklerden %d tanesi temizlendi (>%d gün)", silinen, saklama_gun)
                        except (TypeError, ValueError, OSError) as exc:
                            logger.error("[otomatik-yedek] eski yedekler temizlenirken hata: %s", exc)
        except Exception as exc:
            logger.error("[otomatik-yedek] döngüsünde beklenmeyen hata: %s", exc, exc_info=True)
        await asyncio.sleep(YEDEK_KONTROL_ARALIK_SN)


# ================================================================
# DİSKİN GERÇEKTEN DOLMASINA KARŞI ERKEN UYARI (2026-09-26, kullanıcı
# isteği: "diskin gerçekten dolmasına karşı erken uyarı")
# ================================================================
# Kök neden: mevcut "disk_hatasi" alarmı (bkz. _gorsel_yazma_hatasini_bildir)
# yalnızca bir görsel yazma İSTİSNASI FİİLEN oluştuktan SONRA (yani disk
# ZATEN dolduktan sonra) tetiklenir -- bu noktada kayıtlar artık fotoğrafsız
# oluşuyor demektir, ki bu ÖNLENEBİLECEK bir durumdur. Bu döngü, veritabanı/
# görsel/otomatik-yedek klasörlerinin bulunduğu disklerin doluluk YÜZDESİNİ
# periyodik olarak izleyip bir eşiği aşınca (henüz hiçbir yazma
# başarısız olmadan) proaktif bir uyarı üretir.

DISK_IZLEME_ARALIK_SN = 1800            # her 30 dakikada bir kontrol et
DISK_UYARI_TEKRAR_ARALIK_SN = 6 * 3600  # aynı disk için alarmı en fazla 6 saatte bir tekrar üret

_disk_son_alarm_zamani: dict = {}  # izlenen yol -> son "disk_doluyor" alarmının zamanı (monotonic)


def _var_olan_en_yakin_klasor(yol: str) -> str:
    """`shutil.disk_usage`, henüz VAR OLMAYAN bir yol için FileNotFoundError
    fırlatır (ör. otomatik yedek klasörü ilk yedekten önce, ya da elle
    ayarlanmış ama henüz oluşturulmamış bir yol) -- bu yüzden var olan en
    yakın üst klasöre çıkılır (aynı diskte olduğu için doluluk oranı
    aynıdır)."""
    yol = os.path.abspath(yol)
    while yol and not os.path.isdir(yol):
        ust = os.path.dirname(yol)
        if ust == yol:
            break
        yol = ust
    return yol if os.path.isdir(yol) else os.getcwd()


def _disk_kullanim_yuzdesi(yol: str) -> Optional[float]:
    try:
        kullanim = shutil.disk_usage(_var_olan_en_yakin_klasor(yol))
        if kullanim.total <= 0:
            return None
        return round(kullanim.used / kullanim.total * 100, 1)
    except OSError as exc:
        logger.error("[disk-izleme] '%s' için disk kullanımı okunamadı: %s", yol, exc)
        return None


def _izlenen_disk_yollari(ayarlar: dict) -> dict:
    """Etiket -> yol: veritabanının, araç görsellerinin ve otomatik
    yedeklerin bulunduğu (genellikle aynı ama FARKLI diskler de olabilen)
    klasörler AYRI AYRI izlenir -- yalnızca biri dolmaya başlasa bile fark
    edilebilsin diye (ör. yedekler ayrı bir harici diskteyken canlı
    veritabanının bulunduğu disk dolabilir ya da tam tersi)."""
    yollar = {"Araç görselleri": GORUNTU_KLASORU, "Otomatik yedekler": _otomatik_yedek_klasoru_al(ayarlar)}
    if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        db_yolu = urlparse(SQLALCHEMY_DATABASE_URL).path.lstrip("/")
        yollar["Veritabanı"] = os.path.dirname(os.path.abspath(db_yolu)) or "."
    return yollar


def _disk_izleme_bir_kontrol(ayarlar: dict) -> None:
    """Tek bir kontrol turu: izlenen her diski kontrol eder, eşiği aşanlar
    için alarm+bildirim üretir (bkz. _disk_izleme_dongu'nun docstring'i).
    Döngüden AYRI, kendi başına çağrılabilir bir fonksiyon olarak tutulur
    ki testler sonsuz döngüyü hiç başlatmadan tek bir "tık"ı deterministik
    biçimde çalıştırabilsin (bkz. _otomatik_yedek_uret_ve_dogrula'daki AYNI
    desen)."""
    if not ayarlar.get("disk_izleme_aktif", True):
        return
    esik = float(ayarlar.get("disk_uyari_esik_yuzde", 90))
    for etiket, yol in _izlenen_disk_yollari(ayarlar).items():
        yuzde = _disk_kullanim_yuzdesi(yol)
        if yuzde is None:
            continue
        if yuzde >= esik:
            simdi = time.monotonic()
            son = _disk_son_alarm_zamani.get(yol)
            if son and (simdi - son) < DISK_UYARI_TEKRAR_ARALIK_SN:
                continue
            _disk_son_alarm_zamani[yol] = simdi
            mesaj = (
                f"Disk doluyor: '{etiket}' klasörünün bulunduğu disk %{yuzde:.1f} dolu "
                f"(eşik: %{esik:.0f}) -- yol: {yol}"
            )[:255]
            logger.error("[disk-izleme] %s", mesaj)
            db = SessionLocal()
            try:
                db.add(models.Alarm(plaka_no="SISTEM", alarm_tipi="disk_doluyor", mesaj=mesaj))
                db.commit()
                _bildirim_tetikle(db, "disk_doluyor", {
                    "olay": "disk_doluyor", "alarm_tipi": "disk_doluyor", "mesaj": mesaj,
                })
            except Exception as exc:
                logger.error("[disk-izleme] alarm kaydedilemedi: %s", exc)
            finally:
                db.close()
        else:
            _disk_son_alarm_zamani.pop(yol, None)


async def _disk_izleme_dongu() -> None:
    """Sonsuz döngü: ayarlarda etkinse (`disk_izleme_aktif`, varsayılan
    açık), izlenen disklerin doluluk yüzdesini periyodik olarak kontrol
    eder ve `disk_uyari_esik_yuzde` (varsayılan %90) eşiğini aşan bir disk
    için panelde görülebilir bir `disk_doluyor` alarmı oluşturup Patch
    #111'in _bildirim_tetikle'si ile dış bildirime de bağlar (bkz.
    _disk_izleme_bir_kontrol). Aynı disk için tekrar tekrar alarm
    üretmemek adına `DISK_UYARI_TEKRAR_ARALIK_SN` kadar beklenir; disk
    tekrar eşiğin altına düşerse (ör. temizlik sonrası) bir dahaki dolmada
    YENİDEN uyarabilmek için kayıt sıfırlanır."""
    while True:
        try:
            _disk_izleme_bir_kontrol(_sistem_ayarlari_oku())
        except Exception as exc:
            logger.error("[disk-izleme] döngüsünde beklenmeyen hata: %s", exc, exc_info=True)
        await asyncio.sleep(DISK_IZLEME_ARALIK_SN)


# ================================================================
# SON KULLANILAN NOT ÖNBELLEĞİ — kullanıcı talebi (2026-09-17, devam)
# ================================================================
# Kullanıcı senaryosu: yetkisiz bir araca (örn. bir kargo aracına) panelden
# elle bir not eklendiğinde ("PTT Kargo" gibi), aynı plaka aynı gün içinde
# tekrar geldiğinde görevli notu yeniden yazmak zorunda kalmasın istendi --
# ama bu önerinin bir SONRAKİ güne hiç taşınmaması, her gece sıfırlanması
# açıkça talep edildi. Bu, `Kayit.not_metni` gibi KALICI/denetime tabi bir
# alan DEĞİLDİR -- yalnızca bir kullanıcı kolaylığı (öneri) önbelleğidir;
# sunucu yeniden başlatıldığında da zaten kaybolur. Geçmiş kayıtlardaki
# gerçek notlar (Kayit.not_metni) bundan HİÇBİR ŞEKİLDE etkilenmez, onlar
# denetim/soruşturma amaçlı olarak sonsuza dek olduğu gibi saklanır -- bkz.
# Kayit.not_metni'nin kendi docstring'i.
_SON_NOT_ONBELLEGI: dict = {}  # normalize edilmiş plaka -> {"not_metni": str, "tarih": date}


def _son_not_kaydet(plaka_no: str, not_metni: Optional[str]) -> None:
    """Bir kayda not eklendiğinde/güncellendiğinde çağrılır (bkz.
    _kayit_olustur_ve_bildir ve kayit_duzenle); o plaka için "son kullanılan
    not" önerisini bugünün tarihiyle günceller."""
    if not not_metni or not not_metni.strip():
        return
    hedef = _plaka_normalize(plaka_no)
    if not hedef:
        return
    _SON_NOT_ONBELLEGI[hedef] = {"not_metni": not_metni.strip(), "tarih": datetime.now().date()}


def _son_not_oku(plaka_no: str) -> Optional[str]:
    """Bir plaka için (varsa) son kullanılan not önerisini döner. Önbellekteki
    kayıt BUGÜNE ait değilse (gün değişmiş), pasif olarak sıfırlanır ve None
    döner -- aktif temizlik döngüsü (aşağısı) henüz çalışmamış olsa bile
    doğruluk garanti edilir, döngü yalnızca belleği erkenden boşaltmak
    içindir."""
    hedef = _plaka_normalize(plaka_no)
    if not hedef:
        return None
    kayit = _SON_NOT_ONBELLEGI.get(hedef)
    if not kayit:
        return None
    if kayit["tarih"] != datetime.now().date():
        _SON_NOT_ONBELLEGI.pop(hedef, None)
        return None
    return kayit["not_metni"]


SON_NOT_ONBELLEK_TEMIZLIK_ARALIK_SN = 60  # her dakika saat 23:59'u kontrol et


async def _son_not_onbellek_temizlik_dongu() -> None:
    """Kullanıcının açık talebi: "her gün 23:59'da, yani bir sonraki güne
    geçişte araçların notları sıfırlansın". Her dakika saatin 23:59 olup
    olmadığına bakar, olduğunda (o gün için daha önce yapılmadıysa) SON
    KULLANILAN NOT önbelleğini tamamen temizler. Bu yalnızca yukarıdaki
    öneri önbelleğini etkiler -- kalıcı Kayit.not_metni alanına dokunmaz."""
    son_temizlenen_gun = None
    while True:
        try:
            simdi = datetime.now()
            if simdi.hour == 23 and simdi.minute == 59 and son_temizlenen_gun != simdi.date():
                adet = len(_SON_NOT_ONBELLEGI)
                _SON_NOT_ONBELLEGI.clear()
                son_temizlenen_gun = simdi.date()
                if adet:
                    logger.info(
                        "Son kullanılan not önbelleği gece yarısı sıfırlandı (%d kayıt temizlendi)",
                        adet,
                    )
        except Exception as exc:
            logger.error("[son-not-onbellek] Temizlik döngüsünde hata: %s", exc, exc_info=True)
        await asyncio.sleep(SON_NOT_ONBELLEK_TEMIZLIK_ARALIK_SN)


# ================================================================
# SSE (Server-Sent Events) YAYINCISI — gerçek zamanlı istemci bildirimi
# ================================================================
# Her eleman bir dict: {"kuyruk": asyncio.Queue, "kullanici_id": int, "rol": str}.
# Önceden yalnızca çıplak bir Queue tutuluyordu; güvenlik personeli için
# CANLI akışın da vardiya penceresine göre filtrelenebilmesi (bkz.
# "GÜVENLİK PERSONELİ VARDİYA FİLTRESİ" notu) için bağlı istemcinin kimliği
# de gerekiyor -- aksi halde bir güvenlik personeli, kayıtlar listesinde
# hiç göremeyeceği bir plakanın "Son Geçişler" panelinde anlık olarak
# belirdiğini görebilirdi (tutarsız/sessiz bir bilgi sızıntısı olurdu).
_sse_istemcileri: list = []


async def _sse_yayinla(olay_turu: str, veri: dict, db: Optional[Session] = None) -> None:
    payload = f"event: {olay_turu}\ndata: {json.dumps(veri, ensure_ascii=False, default=str)}\n\n"
    kayit_tarihi = None
    if olay_turu == "kayit" and veri.get("tarih_saat"):
        try:
            kayit_tarihi = datetime.fromisoformat(veri["tarih_saat"])
        except ValueError:
            kayit_tarihi = None
    olum = []
    for istemci in list(_sse_istemcileri):
        if istemci["rol"] == ROL_GUVENLIK:
            # GÜVENLİ TARAF: pencere doğrulanamıyorsa (db/tarih eksikse) ya da
            # kayıt hiçbir pencereye denk düşmüyorsa bu istemciye YOLLANMAZ.
            if db is None or kayit_tarihi is None:
                continue
            pencereler = _kullanicinin_vardiya_pencereleri(db, istemci["kullanici_id"], istemci.get("vardiya_adi"))
            if not any(_pencere_icinde_mi(kayit_tarihi, b, e) for b, e in pencereler):
                continue
        # KAMERA/NOKTA ERİŞİMİ (2026-09-21): bağlı istemcinin kamera
        # kısıtlaması varsa ve bu kayıt izinli olmayan bir kameradan
        # geliyorsa, canlı "Son Geçişler" bildirimi de gönderilmez -- aksi
        # halde izleyemediği bir kameranın plakası CANLI olarak beliriyor
        # olurdu (tutarsız/sessiz bir bilgi sızıntısı). `izinli_kameralar`
        # bağlantı anında hesaplanıp istemci sözlüğünde tutuluyor (bkz.
        # sse_baglantisi) -- `rol` ile aynı desen.
        izinli_kameralar = istemci.get("izinli_kameralar")
        if izinli_kameralar is not None and veri.get("kamera_id") not in izinli_kameralar:
            continue
        try:
            await istemci["kuyruk"].put(payload)
        except Exception:
            olum.append(istemci)
    for istemci in olum:
        try:
            _sse_istemcileri.remove(istemci)
        except ValueError:
            pass


def _api_dokumantasyonu_acik_mi() -> bool:
    """Otomatik oluşturulan Swagger UI (`/docs`), ReDoc (`/redoc`) ve ham
    OpenAPI şeması (`/openapi.json`) FastAPI'de VARSAYILAN OLARAK açık ve
    HİÇBİR kimlik doğrulaması gerektirmiyordu.

    KÖK NEDEN (2026-09-20, "daha profesyonel neler yapabilirsin" denetimi):
    bu, ağa erişimi olan HERKESİN (giriş yapmadan) TÜM API uç noktalarının
    tam listesini, istek/yanıt şemalarını ve alan adlarını görebilmesi
    anlamına geliyordu -- tek başına bir veri sızıntısı değil ama bir saldırı
    yüzeyi haritası (attack surface map) sunuyordu, ve ticari/özel bir ürün
    için gereksiz bir açık kapıydı. Projedeki diğer "varsayılan olarak
    güvenli, isteyen açar" desenleriyle (PTS_CORS_ORIGINS, PTS_KAMERA_ANAHTARI
    vb.) tutarlı olması için: varsayılan olarak KAPALI, yalnızca bu ortam
    değişkeni açıkça ayarlanırsa (örn. geliştirme/hata ayıklama sırasında)
    devreye giriyor."""
    return os.getenv("PTS_API_DOKUMANTASYONU_AC", "").strip().lower() in ("1", "true", "evet")


_API_DOKUMANTASYONU_ACIK = _api_dokumantasyonu_acik_mi()

app = FastAPI(
    title="PTS - Plaka Tanıma Sistemi",
    version="2.0",
    docs_url="/docs" if _API_DOKUMANTASYONU_ACIK else None,
    redoc_url="/redoc" if _API_DOKUMANTASYONU_ACIK else None,
    openapi_url="/openapi.json" if _API_DOKUMANTASYONU_ACIK else None,
)


def _cors_origin_listesi() -> list[str]:
    """PTS_CORS_ORIGINS ortam değişkeni yoksa varsayılan olarak hiçbir çapraz
    kaynak (cross-origin) isteğe izin verilmez — panel zaten aynı FastAPI
    sunucusundan servis edildiği için buna normalde gerek yoktur. Panel
    dışarıdaki farklı bir origin'den (örn. ayrı bir kiosk/entegrasyon
    uygulaması) çağrılacaksa, virgülle ayrılmış origin listesini bu değişkene
    yazın (örn. "https://panel.example.com,https://kiosk.example.com").
    "*" verilirse tüm origin'lere izin verilir ama bu üretimde önerilmez."""
    deger = os.getenv("PTS_CORS_ORIGINS", "").strip()
    if not deger:
        return []
    if deger == "*":
        logger.warning("PTS_CORS_ORIGINS='*' — tüm origin'lere izin veriliyor, üretimde önerilmez")
        return ["*"]
    return [o.strip() for o in deger.split(",") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origin_listesi(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def _guvenlik_basliklarini_ekle(request: Request, call_next):
    """Her yanıta, tarayıcı tarafında ek bir savunma katmanı (defense in
    depth) sağlayan birkaç standart güvenlik başlığı ekler.

    KÖK NEDEN (2026-09-20, geniş kapsamlı denetim): bu başlıklar hiç
    ayarlanmıyordu -- eksiklikleri kendi başına açık bir güvenlik AÇIĞI
    oluşturmaz (asıl yetkilendirme zaten backend'de yapılıyor), ama panel
    başka bir sayfaya (örn. kimlik avı amaçlı sahte bir sayfaya) gömülüp
    tıklama kaçırma (clickjacking) denenirse, ya da bir tarayıcı bir JSON/
    metin yanıtını hatalı biçimde HTML/JS olarak yorumlamaya çalışırsa
    (MIME sniffing) hiçbir ek koruma yoktu. `X-Content-Type-Options` ve
    `X-Frame-Options` her zaman güvenlidir (panel hiçbir yerde başka bir
    origin'den iframe içine gömülmüyor -- kod tabanında hiç `<iframe>`
    kullanılmıyor). `Strict-Transport-Security`, tarayıcılar tarafından
    yalnızca YANIT gerçekten HTTPS üzerinden geldiyse dikkate alınır (düz
    HTTP üzerinden gönderilirse tarayıcı onu sessizce yok sayar), bu yüzden
    ters vekil (reverse proxy) TLS sonlandırması olmayan kurulumlarda da
    zararsızdır. Kapsamlı bir Content-Security-Policy BİLİNÇLİ OLARAK
    eklenmedi -- panelin envanterini (inline script/style kullanımı dahil)
    çıkarmadan eklenen bir CSP, test edilmeden üretimde paneli sessizce
    bozabilir; bu, ayrı ve daha dikkatli bir çalışma gerektirir."""
    yanit = await call_next(request)
    yanit.headers["X-Content-Type-Options"] = "nosniff"
    yanit.headers["X-Frame-Options"] = "SAMEORIGIN"
    yanit.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    yanit.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return yanit


# ================================================================
# KÜRESEL (GLOBAL) HATA YAKALAYICILAR
# ================================================================
# FastAPI/Starlette varsayılan olarak beklenmeyen (bizim `HTTPException`
# olarak fırlatmadığımız) bir hatada istemciye traceback SIZDIRMAZ
# (debug=False varsayılan) — ama hatayı sunucu tarafında HİÇBİR YERE de
# LOGLAMAZ. Sahada bunun sonucu tipik olarak şudur: kullanıcı "sistem hata
# verdi" der, ama `/sistem/loglar` ekranında bu hatanın hiçbir izi yoktur,
# çünkü Starlette onu sessizce yutup düz metin "Internal Server Error"
# döndürmüştür. Bu iki handler, (1) her beklenmeyen hatayı tam traceback'iyle
# uygulama logumuza yazar (böylece `/sistem/loglar` üzerinden görülebilir),
# (2) istemciye diğer tüm hata gövdeleriyle (`{"detail": "..."}`) tutarlı,
# bilgi sızdırmayan bir JSON döner. `HTTPException` (kendi bilerek
# fırlattığımız 4xx/403/404/429 vb.) bu handler'dan ETKİLENMEZ — FastAPI onu
# zaten kendi özel handler'ıyla, daha spesifik bir eşleşme olarak önce yakalar.
@app.exception_handler(RequestValidationError)
async def _dogrulama_hatasi_yakalayici(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Pydantic/istek gövdesi doğrulama hatalarını (422) da aynı tutarlı
    gövdeyle döner ve düşük seviyede loglar (bunlar genelde istemci hatasıdır,
    sunucu tarafında alarm gerektirmez, bu yüzden `logger.exception` değil
    `logger.info` kullanılır)."""
    logger.info("İstek doğrulama hatası: %s %s -> %s", request.method, request.url.path, exc.errors())
    return JSONResponse(status_code=422, content={"detail": "Gönderilen veri geçersiz.", "hatalar": exc.errors()})


@app.exception_handler(Exception)
async def _beklenmeyen_hata_yakalayici(request: Request, exc: Exception) -> JSONResponse:
    """Yakalanmamış her hatayı tam traceback'iyle loglar, istemciye ise genel
    ve bilgi sızdırmayan bir JSON gövdesi döner."""
    logger.exception("Beklenmeyen hata: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Sunucuda beklenmeyen bir hata oluştu. Lütfen tekrar deneyin veya sistem yöneticisine bildirin."},
    )


# ================================================================
# BASİT BELLEK-İÇİ HIZ SINIRLAMA (rate limiting)
# ================================================================
# Tek instance/tek process kurulumlar için yeterlidir (PTS tipik olarak tek
# bir sahada/sunucuda çalışır). Çok sunuculu bir yayılıma geçilirse paylaşımlı
# bir depoya (Redis vb.) taşınmalıdır.

def _hiz_siniri_olustur(limit: int, pencere_sn: float):
    """IP başına sabit pencereli hız sınırlayıcı bağımlılığı üretir."""
    kayitlar: dict[str, "deque"] = {}
    kilit = threading.Lock()

    def bagimlilik(request: Request) -> None:
        istemci = request.client.host if request.client else "bilinmeyen"
        simdi = time.monotonic()
        with kilit:
            kuyruk = kayitlar.setdefault(istemci, deque())
            while kuyruk and simdi - kuyruk[0] > pencere_sn:
                kuyruk.popleft()
            if len(kuyruk) >= limit:
                raise HTTPException(429, "Çok fazla istek gönderildi, lütfen biraz sonra tekrar deneyin.")
            kuyruk.append(simdi)

    return bagimlilik


# /auth/giris: kullanıcı adı bazlı kilitlemeye (yukarıda) ek olarak, IP başına
# da sınır koyar — farklı kullanıcı adlarıyla otomatik deneme (enumeration) saldırısını yavaşlatır.
_hiz_sinir_giris = _hiz_siniri_olustur(limit=20, pencere_sn=60)

# /kayitlar/otomatik: kimlik doğrulaması olmayan, kameraların/NVR'ların doğrudan
# POST ettiği tek uç nokta. Normal kullanımda kamera başına birkaç saniyede bir
# istek yeterlidir; limit bunun oldukça üzerinde tutulup asıl amaç (bir cihazın
# arızalanıp saniyede yüzlerce istek göndermesi ya da kötü niyetli akış) engellenir.
_hiz_sinir_otomatik_kayit = _hiz_siniri_olustur(limit=120, pencere_sn=60)

# Arvento'nun sürücü-atama webhook'u için -- normal kullanımda araç/kart
# başına günde birkaç olay yeterlidir; limit kamera uç noktasınınkinden daha
# düşük tutulup yine de olası bir hatalı/aşırı-istekli entegrasyonu
# durdurabilecek kadar geniş bırakıldı.
_hiz_sinir_arvento_webhook = _hiz_siniri_olustur(limit=60, pencere_sn=60)


def _kamera_anahtari_degeri() -> Optional[str]:
    """PTS_KAMERA_ANAHTARI'nı okur ve .strip() uygular.

    GERÇEK ÜRETİMDE BULUNAN HATA (2026-09-21): kullanıcı bu değişkeni
    Windows'ta ayarlarken (kopyala-yapıştır) sona görünmez bir satır sonu
    (\n) karakteri karışmıştı. `requests` kütüphanesi (bkz. camera_reader.py
    -- aynı düzeltmenin kök neden notu), başlık değerinde satır sonu
    karakterini KABUL ETMEZ ve isteği hiç GÖNDERMEDEN reddeder -- yani
    anahtarın kendisi doğru olsa BİLE, dedektörün gerçekten doğruladığı HER
    plaka sessizce kayboluyordu. Karşılaştırmanın YAPILDIĞI (bu fonksiyon)
    ve gönderilen (camera_reader.py) TARAFLARIN İKİSİ DE aynı şekilde
    .strip() uygulamalı -- aksi halde biri düzeltilip diğeri unutulursa iki
    taraf arasında SESSİZ bir uyuşmazlık oluşabilir."""
    return (os.getenv("PTS_KAMERA_ANAHTARI") or "").strip() or None


def _kamera_anahtari_uyarisi() -> None:
    """PTS_KAMERA_ANAHTARI ayarlanmamışsa `/kayitlar/otomatik` TAMAMEN
    kimliksizdir (kameralar giriş yapamadığı için bu uç nokta bilinçli olarak
    auth istemez) — CORS '*' için yapıldığı gibi, bu durumda da çalışma
    zamanında bir kez uyarılır. Zorunlu KILINMIYOR (bazı kurulumlar
    kameraları güvenilir, izole bir ağda çalıştırıp bu anahtarı bilinçli
    olarak atlıyor olabilir), ama sessizce geçilmemesi gerekir."""
    if not _kamera_anahtari_degeri():
        logger.warning(
            "PTS_KAMERA_ANAHTARI ayarlanmamış — /kayitlar/otomatik uç noktası TAMAMEN "
            "kimliksiz (rate-limit dışında hiçbir koruması yok). Kameralar/NVR'lar güvenilmeyen "
            "bir ağdaysa bu değişkeni ayarlayıp kamera tarafında X-PTS-Kamera-Anahtari "
            "başlığıyla göndermeniz önerilir."
        )


_kamera_anahtari_uyarisi()


def _arvento_anahtari_degeri() -> Optional[str]:
    """PTS_ARVENTO_ANAHTARI'nı okur ve .strip() uygular -- bkz.
    _kamera_anahtari_degeri'nin docstring'indeki AYNI kök neden notu (Windows'ta
    .env düzenlenirken görünmez satır sonu karışması); iki tarafın da (burası
    ve Arvento'nun isteği göndermesi) .strip() uygulaması gerekiyor."""
    return (os.getenv("PTS_ARVENTO_ANAHTARI") or "").strip() or None


def _arvento_anahtari_uyarisi() -> None:
    """PTS_ARVENTO_ANAHTARI ayarlanmamışsa `/entegrasyonlar/arvento/webhook`
    uç noktası TAMAMEN kimliksizdir -- bkz. _kamera_anahtari_uyarisi'nin AYNI
    deseni. Zorunlu KILINMIYOR (bu entegrasyon opsiyoneldir, Arvento henüz
    kendi kimlik doğrulama şemasını bildirmediyse kullanıcı önce anahtarsız
    test edebilir), ama sessizce geçilmemesi gerekir."""
    if not _arvento_anahtari_degeri():
        logger.warning(
            "PTS_ARVENTO_ANAHTARI ayarlanmamış — /entegrasyonlar/arvento/webhook uç noktası "
            "TAMAMEN kimliksiz (rate-limit dışında hiçbir koruması yok). Arvento'nun webhook "
            "isteklerini güvenilmeyen bir ağdan/internetten göndermesi ihtimaline karşı bu "
            "değişkeni ayarlayıp Arvento tarafında X-Arvento-Anahtari başlığıyla göndermeniz "
            "önerilir (bkz. README.md'deki 'Arvento Sürücü Kimliği Entegrasyonu' bölümü)."
        )


_arvento_anahtari_uyarisi()

# /kayitlar/otomatik'e yüklenen görsel için üst sınır — sınırsız boyutlu bir
# dosya kabul edip diske olduğu gibi yazmak (eski davranış), kimliksiz bir uç
# noktada disk-doldurma tabanlı bir DoS'a açık kapı bırakıyordu. Rate limit
# bunu YAVAŞLATIR ama tek başına yeterli değildir (limit içinde kalan az
# sayıda ama çok büyük dosya da diski doldurabilir).
MAKS_GORSEL_BOYUTU_BAYT = 8 * 1024 * 1024  # 8 MB (tipik bir plaka fotoğrafının çok üzerinde)

class _OnbellegiHicDogrulamadanKullanma(StaticFiles):
    """Varsayılan StaticFiles davranışı, tarayıcının app.js/style.css'i kendi
    sezgisel önbellek süresi boyunca sunucuya HİÇ sormadan kullanmasına izin
    verebiliyor. Bu depoda birden çok kez şu duruma yol açtı: bir düzeltme
    sunucuya kurulup uygulama yeniden başlatılsa bile, kullanıcı sayfayı normal
    şekilde yenilediğinde tarayıcı hâlâ ESKİ app.js/style.css'i belleğinden/
    diskinden kullanmaya devam ediyor ve düzeltme hiç etkinleşmemiş gibi
    görünüyordu. `Cache-Control: no-cache` ile tarayıcı her sayfa yenilemesinde
    dosyanın değişip değişmediğini sunucuya SORMAK ZORUNDA kalır (ETag/
    If-None-Match sayesinde değişmediyse yine hızlı bir 304 döner, yani ek bir
    performans bedeli yoktur) — böylece normal bir yenileme (sert yenileme
    gerekmeden) her zaman en güncel sürümü garanti eder."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", _OnbellegiHicDogrulamadanKullanma(directory=FRONTEND_KLASORU), name="static")
# DİKKAT: /goruntuler artık BURADA bir StaticFiles mount'u DEĞİL — araç/sürücü
# görselleri kişisel veridir (KVKK), kimliksiz servis edilmemeli. Auth-gated
# servis, /auth/me'nin hemen altında `gorsel_getir` uç noktası olarak
# tanımlanıyor (bkz. o fonksiyonun docstring'i).


@app.on_event("startup")
async def _kameralari_otomatik_baslat():
    """Uygulama açılışında cameras.json'daki aktif kameralar için pipeline başlatır."""
    for kamera in _kameralari_oku():
        if kamera.get("aktif", True):
            _pipeline_baslat(kamera)


@app.on_event("startup")
async def _kamera_bekcisini_baslat():
    """Arka planda sürekli çalışan kamera bekçisini (watchdog) başlatır."""
    asyncio.ensure_future(_kamera_bekci_dongu())
    logger.info("Kamera bekçisi başlatıldı (her %d sn kontrol)", KAMERA_BEKCI_ARALIK_SN)


@app.on_event("startup")
async def _goruntu_temizligini_baslat():
    """Arka planda sürekli çalışan otomatik görüntü/kayıt saklama görevini başlatır."""
    asyncio.ensure_future(_goruntu_temizlik_dongu())
    logger.info("Otomatik görüntü temizliği başlatıldı (her %d sn kontrol)", GORUNTU_TEMIZLIK_ARALIK_SN)


@app.on_event("startup")
async def _otomatik_yedeklemeyi_baslat():
    """Arka planda sürekli çalışan otomatik veritabanı yedekleme görevini
    başlatır (bkz. yukarısı, kullanıcı isteği: "günlük otomatik yedek ekle")."""
    asyncio.ensure_future(_otomatik_yedek_dongu())
    logger.info("Otomatik veritabanı yedekleme başlatıldı (her %d sn kontrol, günde 1 yedek)", YEDEK_KONTROL_ARALIK_SN)


@app.on_event("startup")
async def _disk_izlemeyi_baslat():
    """Arka planda sürekli çalışan, diskin gerçekten dolmasına karşı ERKEN
    uyaran görevi başlatır (bkz. yukarısı, kullanıcı isteği: "diskin
    gerçekten dolmasına karşı erken uyarı")."""
    asyncio.ensure_future(_disk_izleme_dongu())
    logger.info("Disk doluluk izleme başlatıldı (her %d sn kontrol)", DISK_IZLEME_ARALIK_SN)


@app.on_event("startup")
async def _son_not_onbellek_temizligini_baslat():
    """Arka planda sürekli çalışan, "son kullanılan not" önbelleğini her gece
    23:59'da sıfırlayan görevi başlatır (bkz. yukarısı)."""
    asyncio.ensure_future(_son_not_onbellek_temizlik_dongu())
    logger.info("Son kullanılan not önbelleği temizliği başlatıldı (her gece 23:59)")


@app.on_event("startup")
async def _vardiya_otomatik_kapamayi_baslat():
    """Arka planda sürekli çalışan, 8 saati aşan (unutulmuş) açık vardiya
    oturumlarını otomatik kapatan görevi başlatır (bkz. yukarısı)."""
    asyncio.ensure_future(_vardiya_otomatik_kapama_dongu())
    logger.info(
        "Vardiya otomatik kapama başlatıldı (her %d sn kontrol, sınır: %d saat)",
        VARDIYA_OTOMATIK_KAPAMA_ARALIK_SN, VARDIYA_MAKS_SURE_SAAT,
    )


_klasor_izleyici = None  # bkz. _klasor_izlemeyi_baslat_gerekirse — /sistem/saglik'te de raporlanır


@app.on_event("startup")
async def _klasor_izlemeyi_baslat_gerekirse():
    """`PTS_GORSEL_IZLEME_DIZINI` ayarlıysa, bu klasöre bırakılan araç
    fotoğraflarını gerçek bir kamera geçişiymiş gibi otomatik işleyen arka
    plan görevini başlatır (bkz. camera_reader.py::KlasorIzleyici). Kamera
    bağlanmadan sistemi uçtan uca test etmek ya da gerçek, sorunlu bir
    fotoğrafı dedektör eşiğine karşı denemek için kullanışlıdır."""
    global _klasor_izleyici
    dizin = os.getenv("PTS_GORSEL_IZLEME_DIZINI", "").strip()
    if not dizin:
        return
    if not _CAM_LIBS:
        logger.warning(
            "PTS_GORSEL_IZLEME_DIZINI ayarlanmış ama kamera kütüphaneleri kurulu değil "
            "(pip install \"fast-alpr[onnx]\" opencv-python requests) — klasör izleme başlatılamadı."
        )
        return
    try:
        from backend.camera_reader import KlasorIzleyici as _KlasorIzleyici
        _klasor_izleyici = _KlasorIzleyici(dizin)
        _klasor_izleyici.baslat()
    except Exception:
        logger.exception("Klasör izleyici başlatılamadı: %s", dizin)

AUTH_SECRET_DOSYASI = os.path.join(BACKEND_DIR, "auth_secret.key")


def _auth_secret_al() -> str:
    """Ortam değişkeni yoksa gizli anahtar yerel dosyada kalıcı tutulur (yeniden başlatmada oturumların düşmemesi için).

    .strip(): tutarlılık için -- bkz. _kamera_anahtari_degeri/lisans.secret_al'daki
    aynı kök neden notu (sona karışan görünmez bir \n bu değişken için de mümkündür)."""
    env_deger = (os.getenv("PTS_AUTH_SECRET") or "").strip()
    if env_deger:
        return env_deger
    if os.path.exists(AUTH_SECRET_DOSYASI):
        with open(AUTH_SECRET_DOSYASI, "r", encoding="utf-8") as dosya:
            mevcut = dosya.read().strip()
            if mevcut:
                return mevcut
    yeni = secrets.token_hex(32)
    with open(AUTH_SECRET_DOSYASI, "w", encoding="utf-8") as dosya:
        dosya.write(yeni)
    return yeni


AUTH_SECRET = _auth_secret_al()


def _parola_hashle(parola: str, tuz: Optional[bytes] = None) -> str:
    tuz = tuz or secrets.token_bytes(16)
    sonuc = hashlib.pbkdf2_hmac("sha256", parola.encode("utf-8"), tuz, 310_000)
    return f"{tuz.hex()}${sonuc.hex()}"


def _parola_dogrula(parola: str, kayit: str) -> bool:
    try:
        tuz_hex, hash_hex = kayit.split("$", 1)
        beklenen = hashlib.pbkdf2_hmac("sha256", parola.encode("utf-8"), bytes.fromhex(tuz_hex), 310_000).hex()
        return hmac.compare_digest(beklenen, hash_hex)
    except (ValueError, TypeError):
        return False


def _token_uret(kullanici_id: int) -> str:
    bitis = int(time.time()) + 8 * 60 * 60
    govde = f"{kullanici_id}:{bitis}".encode("utf-8")
    imza = hmac.new(AUTH_SECRET.encode("utf-8"), govde, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(govde + b":" + imza).decode("ascii").rstrip("=")


def _token_coz(token: str) -> int:
    try:
        veri = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        kullanici_id, bitis, imza = veri.split(b":", 2)
        govde = b":".join((kullanici_id, bitis))
        beklenen = hmac.new(AUTH_SECRET.encode("utf-8"), govde, hashlib.sha256).digest()
        if not hmac.compare_digest(imza, beklenen) or int(bitis) < int(time.time()):
            raise ValueError
        return int(kullanici_id)
    except (ValueError, TypeError, UnicodeDecodeError):
        raise HTTPException(401, "Oturum geçersiz veya süresi dolmuş")


def _giris_gerekli(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = None,
    db: Session = Depends(get_db),
) -> models.Kullanici:
    """Korumalı uç noktalar için geçerli oturum zorunluluğu.

    GÜVENLİK KÖK NEDEN DÜZELTMESİ (2026-09-18): `/disa-aktar/...` gibi dosya
    indirme uçları tarayıcıda `window.open()` ile açılıyor -- bu, `fetch()`in
    aksine bir `Authorization` header TAŞIYAMAZ (bkz. app.js'teki
    `korumaliGorselAta`'nın AYNI kısıtlama yüzünden neden fetch+blob URL
    kullandığını anlatan not). Bu yüzden o uç noktaların HİÇBİRİ bugüne kadar
    HİÇ kimlik doğrulaması istemiyordu -- yani plaka/isim/daire gibi KVKK
    kapsamındaki kişisel verileri içeren TÜM kayıt/kişi dışa aktarma uçları,
    oturum açmamış HERKESE (internete açık bir kurulumda kimliksiz herhangi
    bir istemciye) açıktı. Düzeltme: `Authorization` header yoksa, aynı
    JWT'nin `?token=` sorgu parametresi olarak da gönderilmesine izin
    verilir -- yalnızca indirme uçları (frontend'de sessionStorage'daki
    token URL'e eklenir, bkz. app.js) bunu kullanır; normal API çağrıları
    (fetch tabanlı `apiCagir`) yine header kullanmaya devam eder, davranışları
    değişmez.
    """
    ham_token = None
    if authorization and authorization.lower().startswith("bearer "):
        ham_token = authorization[7:].strip()
    elif token:
        ham_token = token.strip()
    if not ham_token:
        raise HTTPException(401, "Bearer token gerekli")
    kullanici = db.query(models.Kullanici).filter(models.Kullanici.id == _token_coz(ham_token)).first()
    if not kullanici or not kullanici.aktif:
        raise HTTPException(401, "Kullanıcı hesabı aktif değil")
    return kullanici


# ================================================================
# ROL BAZLI YETKİLENDİRME
# ================================================================
# Roller (models.Kullanici.rol ile birebir aynı yazılmalı — "operatör" içindeki
# Türkçe "ö" harfi dahil; bu sabitler tanımlanmadan önce bu yazım hatası bir
# yerde "operator" olarak yazılıp sessizce YETKİSİZ erişime izin verebilirdi).
ROL_YONETICI = "yonetici"
ROL_OPERATOR = "operatör"
# "güvenlik" (Güvenlik Personeli): bkz. 2026-09-18 "Güvenlik Personeli Vardiya
# Filtresi" notu, README. Yetki/görünürlük açısından "operatör" ile BİREBİR
# AYNI kademede -- _rol_dogrula bu iki rolü eşdeğer sayar (aşağıya bakınız),
# frontend/app.js::ROL_SEVIYE de aynı sıralamayı kullanır. TEK gerçek farkı:
# kayıtlar listesi/raporları kendi vardiya saatleriyle filtrelenir (bkz.
# _guvenlik_kayit_filtresi_uygula) -- "operatör"ün göremediği hiçbir şeyi
# görmez, yalnızca operatörün gördüğü kayıtların bir ALT KÜMESİNİ görür.
ROL_GUVENLIK = "güvenlik"
ROL_IZLEYICI = "izleyici"
# "sakin": panel PERSONELİ değil, bir Kişi (abone/sakin) kaydına bağlı öz-hizmet
# giriş hesabı (bkz. 2026-09-17 notu, README). Diğer üç rolden temelde
# FARKLI: yönetici/operatör/izleyici hep aynı "panel personeli" ailesinin
# kademeleri (izleyici en az yetkili, yonetici en çok), sakin ise bu
# hiyerarşinin TAMAMEN DIŞINDA, yalnızca kendi /sakin/... uç noktalarına
# erişebilen ayrı bir hesap türü. Bu yüzden ROL_SEVIYE benzeri bir
# sıralamaya sokulmuyor; bkz. _personel_girisi_gerekli.
ROL_SAKIN = "sakin"


def _personel_girisi_gerekli(kullanici: models.Kullanici = Depends(_giris_gerekli)) -> models.Kullanici:
    """`_giris_gerekli` ile aynı oturum zorunluluğuna EK olarak çağıranın panel
    PERSONELİ (yönetici/operatör/izleyici) olmasını ister.

    NEDEN GEREKLİ: aşağıdaki "sakin" (site sakini öz-hizmet portalı) rolü
    eklenmeden önce, bu dosyadaki HER korumalı uç nokta ya `_giris_gerekli`
    ile "herhangi bir giriş yapmış personel" (izleyici dahil salt-okunur
    uçlar) ya da onun ÜZERİNE `_rol_dogrula(..., ROL_YONETICI, ROL_OPERATOR)`
    ile daha dar bir personel alt kümesini şart koşuyordu — her iki durumda
    da örtük varsayım "giriş yapabilen herkes güvenilir iç personeldir"
    şeklindeydi. "sakin" ise bu varsayımı bozan İLK dış/daha az güvenilir
    hesap türü: bir site sakini kendi plakasını/geçmişini görebilmeli ama
    TÜM kişilerin listesini, tüm kameraları, tüm geçiş kayıtlarını,
    sistem loglarını vb. GÖREMEMELİ. `_rol_dogrula(..., ROL_YONETICI,
    ROL_OPERATOR)` ile zaten korunan yazma uçları "sakin"i otomatik
    reddediyor (izin listesinde yok), ama yalnızca `_giris_gerekli` ile
    korunan (ekstra rol kontrolü OLMAYAN, "her personel okuyabilir" niyetiyle
    yazılmış) onlarca salt-okunur uç nokta bu ek kontrol olmadan "sakin"
    rolüne de açık kalırdı. Bu yüzden TÜM dahili/genel amaçlı uç noktalar
    (yeni `/sakin/...` öz-hizmet uçları VE `/auth/me` hariç) bu fonksiyonu
    kullanmalı — tek bir merkezi kontrol, `_rol_dogrula`'nın kendi
    docstring'indeki "aynı mantığın birden fazla bağımsız kopyası" hata
    sınıfını burada da tekrarlamamak için."""
    if kullanici.rol == ROL_SAKIN:
        raise HTTPException(403, "Bu işlem için personel girişi gerekli")
    return kullanici


def _rol_dogrula(kullanici: models.Kullanici, *izinli_roller: str) -> None:
    """`kullanici.rol` izinli_roller içinde değilse 403 fırlatır.

    TÜM rol kontrolleri bu tek fonksiyon üzerinden yapılmalı — aksi halde her
    uç noktada elle yazılan `if kullanici.rol != "..."` ifadeleri birbirinden
    bağımsız kopyalar haline gelir ve biri unutulduğunda/yanlış yazıldığında
    fark edilmesi zor bir yetki açığı oluşur (bu depoda daha önce görülen
    "aynı mantığın birden fazla, birbirinden sapabilen kopyası" hata sınıfının
    güvenlik tarafındaki karşılığı).

    Rol politikası (bkz. README "Rol Bazlı Yetkilendirme"):
      - izleyici: HİÇBİR yazma işlemi yapamaz, sadece görüntüler.
      - operatör: günlük operasyon (kişi/kara liste/kamera/bariyer açma/LED/
        manuel kayıt/toplu içe aktarma/görüntü temizleme).
      - güvenlik: operatör ile YETKİ açısından BİREBİR AYNI (bkz. aşağıdaki
        eşdeğerlik notu) -- tek farkı kayıtlar listesinin kendi vardiyasıyla
        filtrelenmesi (bkz. _guvenlik_kayit_filtresi_uygula), bu fonksiyon
        seviyesinde HİÇBİR ayrım yapılmaz.
      - yonetici: operatörün yapabildiği HER ŞEY + kullanıcı yönetimi, lisans,
        sistem ayarları, site/erişim noktası/webhook yapılandırması, kayıt
        silme, veritabanı yedeği.

    GÜVENLİK PERSONELİ EŞDEĞERLİĞİ (2026-09-18): `ROL_GUVENLIK`, çağıranın
    rolü kontrol edilmeden ÖNCE burada `ROL_OPERATOR`'a eşlenir -- böylece bu
    dosyadaki `_rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)` şeklindeki
    ONLARCA mevcut çağrı satırının HİÇBİRİNE dokunmadan "güvenlik" rolü de
    aynı işlemlere otomatik olarak izinli hale gelir (ve yeni eklenecek
    çağrılar da otomatik kapsanır). Bu, dosyanın başındaki "aynı mantığın
    birden fazla bağımsız kopyası" hata sınıfından kaçınma ilkesiyle
    birebir aynı gerekçeye dayanır: eşdeğerliği her çağrı satırında ayrı ayrı
    (`ROL_YONETICI, ROL_OPERATOR, ROL_GUVENLIK`) tekrar etmek yerine TEK bir
    yerde tanımlanır.
    """
    etkin_rol = ROL_OPERATOR if kullanici.rol == ROL_GUVENLIK else kullanici.rol
    if etkin_rol not in izinli_roller:
        raise HTTPException(
            403,
            f"Bu işlem için yetkiniz yok (gereken rol: {' veya '.join(izinli_roller)})",
        )


def _denetim_kaydet(db: Session, kullanici_adi: str, eylem: str, aciklama: str) -> None:
    """Hassas bir yönetici işlemini hem log dosyasına HEM DE kalıcı
    `denetim_kayitlari` tablosuna (bkz. models.DenetimKaydi) yazar.

    KÖK NEDEN (2026-09-20, kullanıcı talebi: "kalıcı bir veritabanı tablosu +
    panelde ayrı bir Denetim Kayıtları ekranı olan tam bir audit-trail
    sistemi kurabilirim -- bunu yapabilirsin"): önceki tur yalnızca
    `loglar/pts.log`'a yazıyordu -- bu ne filtrelenebiliyor ne de panelde
    görülebiliyordu. Bu fonksiyon TEK çağrı noktası olarak kullanılmalı ki
    ileride eklenecek yeni bir hassas işlem türü (varsa) iki kayıt yerinden
    birini unutmasın.

    GÜVENLİK/DAYANIKLILIK: denetim kaydının YAZILAMAMASI (ör. veritabanı o an
    kilitliyse) asıl işlemi (kullanıcı silme, kamera silme vb.) ASLA
    engellememeli/geri almamalı -- bu, ikincil bir gözlemlenebilirlik
    özelliğidir, birincil iş akışı değil. Bu yüzden ayrı bir try/except'e
    sarılı; asıl işlemin `db.commit()`'i bu çağrıdan ÖNCE zaten yapılmış
    olmalı ki bu fonksiyondaki bir hata (varsa) asıl değişikliği geri
    almasın."""
    logger.info("[denetim] %s: %s (yapan: %s)", eylem, aciklama, kullanici_adi)
    try:
        db.add(models.DenetimKaydi(kullanici_adi=kullanici_adi, eylem=eylem, aciklama=aciklama))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Denetim kaydı veritabanına yazılamadı (eylem=%s)", eylem)


# ================================================================
# GÜVENLİK PERSONELİ VARDİYA FİLTRESİ (2026-09-18, 2026-09-20'de öz-hizmete
# geçirildi -- bkz. aşağıdaki güncelleme notu)
# ================================================================
# Kullanıcı talebi (birebir, 2026-09-18): "Yönetici panelinden tüm kayıtlar
# gözükecek güvenlik panellerinde sadece kendi vardiyalarında geçen araçların
# raporları ve kayıtları gözükecek." + "4 vardiya 4 vardiya amiri 24 saat
# esaslı çalıştığı için [personel] bir gün 15:00-23:00 aralığında çalışıyor
# diğer gün 07:00-15:00 gibi çalışıyor" (yani vardiya saatleri GÜNDEN GÜNE
# değişebiliyor, sabit bir haftalık program yeterli değil) + "Aynı anda
# birden fazla güvenlik personeli giriş yapmışsa kayıt HERKESTE ayrı ayrı
# gösterilir" (çakışma durumunda dışlama değil, çoğullama).
#
# GÜNCELLEME (2026-09-20, birebir): "bunu sürekli ben yapamam vardiyaya gelen
# personel kendisi vardiya başlangıcını kendisi yapabilsin ... kullanıcı giriş
# yapınca çıkış yapana kadar onun vardiyası devam etsin" -- yöneticinin ELLE,
# GÜN BAZLI vardiya ataması yapması yerine (eski models.VardiyaAtamasi), her
# güvenlik kullanıcısının vardiya penceresi artık KENDİ GİRİŞ/ÇIKIŞINA bağlı
# (bkz. models.VardiyaOturumu, giris_yap::_guvenlik_oturum_baslat, cikis_yap).
# Aşağıdaki iki tasarım kararı DEĞİŞMEDİ, yalnızca pencerelerin KAYNAĞI
# değişti: bir kayıt, bu pencerelerden HERHANGİ BİRİNE denk düşüyorsa o
# kullanıcıya "ait" sayılır (çakışan pencerelerde birden fazla kullanıcıya
# aynı anda ait olabilir -- dışlayıcı bir atama YOKTUR).
#
# KAPSAM (bilinçli sınır -- README'de de belgelenmiştir): bu filtre
# GÖRÜNÜRLÜĞE uygulanır (kayıtlar listesi, dışa aktarma raporları, plaka
# analizi geçmişi, canlı SSE akışı, panel istatistiklerinin kayıt bazlı
# alanları). Kaydı DÜZENLEME/SİLME yetkisi (zaten operatör-eşdeğerliği
# üzerinden var olan) vardiya dışı kayıtlar için AYRICA kısıtlanmaz --
# tıpkı 2026-09-18 tarihli "Operatör Panelinden Yönetim Görünürlüğü" notunda
# olduğu gibi bu da bilinçli olarak bir GÖRÜNÜRLÜK kısıtlamasıdır, API'yi
# doğrudan çağıran (kaydın ID'sini zaten bilen) bir istemciye karşı ekstra
# bir yetkilendirme katmanı değildir.


def _pencere_icinde_mi(zaman: datetime, baslangic: datetime, bitis: Optional[datetime]) -> bool:
    """`zaman`, [baslangic, bitis) aralığında mı? `bitis` NULL ise ilgili
    vardiya oturumu HÂLÂ AÇIK demektir (bkz. models.VardiyaOturumu) ve üst
    sınır yok sayılır -- yani `baslangic`'tan bu yana geçen HER ŞEY dahildir."""
    if zaman < baslangic:
        return False
    return bitis is None or zaman < bitis


def _vardiya_adi_normalize(v: Optional[str]) -> Optional[str]:
    """Vardiya grubu adını normalize eder: baş/son boşluk temizlenir, büyük
    harfe çevrilir. Boş string (temizlik sonrası) `None` döner -- yani hem
    `kullanici_ekle`/`kullanici_guncelle`'daki ATAMA/TEMİZLEME hem de Kayıtlar
    ekranındaki "Vardiya" FİLTRESİ (bkz. kayitlari_listele) AYNI kuralı
    kullanır (ör. " a " ve "A" aynı gruba işaret eder). Arayüz A/B/C/D önerir
    ama serbest metindir -- DB seviyesinde bir kısıtlama YOK (bkz.
    models.Kullanici.vardiya_adi)."""
    if v is None:
        return None
    temiz = v.strip().upper()
    return temiz or None


def _kullanicinin_vardiya_pencereleri(db: Session, kullanici_id: Optional[int], vardiya_adi: Optional[str] = None) -> list:
    """Bir hesabın (ya da PAYLAŞILAN bir vardiya grubunun) TÜM vardiya
    oturumlarını (giriş, çıkış) çiftleri olarak döner -- çıkış NULL ise oturum
    hâlâ AÇIKTIR (bkz. _pencere_icinde_mi).

    "Vardiya Grupları" (2026-09-21, kullanıcı talebi): "LOJMAN A Vardiyası
    Bülent ile aynı zaman aralığında çalışacağı için ... Ana nizamiyeden
    bülent kontrol ettiğinde Lojman A geçişlerini de görebilecek" -- yani
    FARKLI fiziksel noktalardaki (Ana Nizamiye/Lojman Nizamiye) hesaplar aynı
    isimde bir vardiyaya (bkz. models.Kullanici.vardiya_adi) atanmışsa
    birbirinin kayıt görünürlüğünü PAYLAŞMALI. Bu yüzden:
    - `vardiya_adi` verilmişse: yalnızca `kullanici_id`'nin DEĞİL, AYNI
      `vardiya_adi`'na sahip TÜM hesapların oturumları BİRLİKTE döner (Kayıtlar
      ekranındaki "Vardiya" filtresi de -- bkz. kayitlari_listele -- bunu
      `kullanici_id=None` ile çağırır, çünkü orada belirli bir hesap değil
      doğrudan vardiya ADI sorgulanır).
    - `vardiya_adi` verilmemişse (None): eski/varsayılan davranış -- yalnızca
      `kullanici_id`'nin KENDİ oturumları döner (adlandırılmamış güvenlik
      hesapları için).

    Bu tablo küçük ölçekli olduğu için (kullanıcı/vardiya başına yılda genelde
    birkaç yüz oturum) tüm satırlar belleğe alınır; ayrı bir SQL tarih
    aralığı ön-filtresi bu ölçekte gerekmiyor."""
    sorgu = db.query(models.VardiyaOturumu)
    if vardiya_adi:
        sorgu = (
            sorgu.join(models.Kullanici, models.VardiyaOturumu.kullanici_id == models.Kullanici.id)
            .filter(models.Kullanici.vardiya_adi == vardiya_adi)
        )
    elif kullanici_id is not None:
        sorgu = sorgu.filter(models.VardiyaOturumu.kullanici_id == kullanici_id)
    else:
        return []
    return [(o.giris_zamani, o.cikis_zamani) for o in sorgu.all()]


def _vardiya_oturumu_kosulu(kullanici_id: Optional[int], vardiya_adi: Optional[str]):
    """`Kayit.tarih_saat`in, verilen hesabın (ya da vardiya ADININ) açık bir
    vardiya oturumuna denk düştüğünü ifade eden, veritabanında çalışan bir
    EXISTS koşulu (bkz. `_pencere_icinde_mi` ile BİREBİR aynı anlam:
    giriş <= zaman VE (çıkış YOK ya da zaman < çıkış)).

    2026-09-25 (kullanıcı: "kayıtlarda araç arattığımda ... her an
    çökecekmiş gibi yavaş"): bu filtre eskiden `_pencerelerden_or_kosulu`
    ile kurulan, hesabın/vardiyanın TÜM geçmiş oturumlarını tek tek
    `(tarih >= a AND tarih < b) OR ...` biçiminde sıralayan bir koşuldu.
    Her yeni vardiya girişiyle bu koşul BÜYÜYORDU: aylar içinde yüzlerce,
    sonra binlerce terimlik bir SQL ifadesi -- sorgu her gün biraz daha
    yavaşlıyordu. Daha kötüsü, SQL Server tek bir sorguda en fazla 2100
    parametreye izin verir: bir vardiya adının ~1050 oturumu birikince
    (ör. 3 hesap x günde 1 oturum = ~1 yıl) Kayıtlar ekranı, Vardiya
    filtresi ve güvenlik personelinin tüm kayıt görünümleri 500 hatasıyla
    TAMAMEN çalışmaz hale gelecekti. EXISTS alt sorgusu sabit sayıda
    parametre kullanır ve veritabanının kendi indeksleriyle değerlendirilir.
    """
    O = models.VardiyaOturumu
    zaman_kosullari = (
        O.giris_zamani <= models.Kayit.tarih_saat,
        or_(O.cikis_zamani.is_(None), O.cikis_zamani > models.Kayit.tarih_saat),
    )
    if vardiya_adi:
        alt = (
            select(O.id)
            .join(models.Kullanici, O.kullanici_id == models.Kullanici.id)
            .where(models.Kullanici.vardiya_adi == vardiya_adi, *zaman_kosullari)
        )
    elif kullanici_id is not None:
        alt = select(O.id).where(O.kullanici_id == kullanici_id, *zaman_kosullari)
    else:
        return false()
    return alt.correlate(models.Kayit).exists()


def _kullanicinin_izinli_kameralari(kullanici: models.Kullanici) -> Optional[set]:
    """"Nizamiye Bazlı Kamera Erişimi" (2026-09-21) -- bkz.
    models.Kullanici.kamera_erisim_listesi'nin docstring'i.

    `None` dönerse KISITLAMA YOK -- hesap tüm kameraları görebilir (geriye
    dönük uyumluluk varsayılanı: mevcut tüm hesaplar bu haldeydi). Bir `set`
    dönerse (BOŞ set dahil), yalnızca o id'lere sahip kameralar bu hesaba
    görünür/erişilebilir olmalıdır."""
    if not kullanici.kamera_erisim_listesi:
        return None
    try:
        idler = json.loads(kullanici.kamera_erisim_listesi)
    except (ValueError, TypeError):
        return None
    if not isinstance(idler, list):
        return None
    return set(idler)


def _kamera_erisimi_var_mi(kullanici: models.Kullanici, kamera_id: str) -> bool:
    """Tek bir kameraya (canlı izleme uçlarında) erişim kontrolü -- bkz.
    _kullanicinin_izinli_kameralari. Burada `kamera_id`, cameras.json'daki
    "id" alanıdır (URL path parametresi -- ör. `/kameralar/{kamera_id}/
    goruntu`) -- bu yüzden `Kayit.kamera_id` (kaydın "ad" ile damgalanmış
    ETİKETİ) ile KARIŞTIRILMAMALI (bkz. _kullanicinin_izinli_kamera_adlari'nın
    docstring'indeki KÖK NEDEN notu)."""
    izinli = _kullanicinin_izinli_kameralari(kullanici)
    return izinli is None or kamera_id in izinli


def _kamera_id_den_ad_haritasi() -> dict:
    """cameras.json'daki her kameranın "id" -> "ad" eşlemesini döner (ad
    boşsa id'nin kendisine düşer). `Kayit.kamera_id` (HER ZAMAN ad bazlı,
    bkz. _pipeline_baslat) ile KARŞILAŞTIRILACAK id bazlı bir veriyi (ör.
    kamera erişim kısıtlaması, Nokta.kamera_id) çevirmek isteyen HER YER
    bunu kullanmalı -- bkz. _kullanicinin_izinli_kamera_adlari ve
    _kayitlari_rapor_satirlari'nin docstring'lerindeki aynı kök neden
    (2026-09-21, "id vs ad" hata sınıfı). Tek doğru kaynak burası: aynı
    eşleme iki ayrı yerde ayrı ayrı yazılırsa biri güncellenip diğeri
    unutulabilir."""
    return {k["id"]: (k.get("ad") or k["id"]) for k in _kameralari_oku()}


def _kullanicinin_izinli_kamera_adlari(kullanici: models.Kullanici) -> Optional[set]:
    """`_kullanicinin_izinli_kameralari`'nin döndürdüğü kısıtlama listesi
    cameras.json'daki "id" alanına göredir (kamera CRUD/canlı izleme uçları
    -- ör. `GET /kameralar`, `/kameralar/{id}/goruntu` -- hep "id" ile
    çalışır). AMA gerçek geçiş kayıtları (`Kayit.kamera_id`) "id" DEĞİL,
    kameranın "ad" (isim) alanıyla damgalanır (bkz. _pipeline_baslat:
    `kamera_id=kamera["ad"]`) -- yani "kamera kimliği" (id) ile "geçiş
    kaydındaki kamera etiketi" (ad) İKİ FARKLI KAVRAM, ama ikisi de aynı
    `kamera_id` ismiyle anılıyor.

    GERÇEK ÜRETİM VERİSİYLE BULUNAN HATA (2026-09-21, kullanıcının "Lojman A
    Vardiyası" hesabı hiçbir geçiş göremiyor" geri bildirimiyle ortaya
    çıktı): bir hesaba id bazlı bir kısıtlama atandığında (ör. panelden
    "Lojman" ve "L.ÇIKIŞ" kameraları seçilince), `_guvenlik_kayit_filtresi_
    uygula`/`_guvenlik_kayit_gorunur_mu`/SSE bu id kümesini DOĞRUDAN
    `Kayit.kamera_id.in_(...)` ile karşılaştırıyordu. Bir kameranın "id"si
    "ad"ıyla TESADÜFEN aynıysa çalışıyor gibi görünüyordu, ama genelde
    id != ad olduğu için kısıtlı bir hesap kendi noktasının TÜM geçmiş
    kayıtlarını SESSİZCE göremez hale geliyordu (boş bir liste dönüyordu --
    "hiç geçiş gözükmüyor" şikayeti tam olarak buradan kaynaklandı; oysa
    aynı kayıtlar kısıtlamasız -- yönetici -- bir hesapta ve "Vardiya"
    etiketlemesinde doğru görünüyordu, çünkü o ikisi kamera kısıtlamasına
    hiç bakmıyor/id'ye değil vardiya penceresine dayanıyor).

    Bu fonksiyon, id bazlı kısıtlamayı cameras.json üzerinden KARŞILIK GELEN
    "ad" değerlerine çevirir. `Kayit.kamera_id` ile KARŞILAŞTIRILACAK HER
    YERDE (`_guvenlik_kayit_filtresi_uygula`, `_guvenlik_kayit_gorunur_mu`,
    `sse_baglantisi`/`_sse_yayinla`) bu fonksiyon kullanılmalı; canlı izleme/
    kamera CRUD uçlarında (id bazlı çalışmaya devam eden)
    `_kullanicinin_izinli_kameralari` KULLANILMAYA DEVAM EDER.

    Silinmiş/artık cameras.json'da bulunmayan bir id, hiçbir "ad"a
    çevrilemediği için sessizce ATLANIR (o kısıtlama parçası kalıcı olarak
    erişilemez hale gelir -- zaten var olmayan bir kamera için beklenen
    davranış budur)."""
    izinli_idler = _kullanicinin_izinli_kameralari(kullanici)
    if izinli_idler is None:
        return None
    id_den_ada = _kamera_id_den_ad_haritasi()
    return {id_den_ada[kid] for kid in izinli_idler if kid in id_den_ada}


def _vardiya_adi_filtresi_uygula(sorgu, vardiya_adi: Optional[str], db: Session):
    """Kayıtlar ekranındaki (2026-09-21) "Vardiya" FİLTRESİNİ uygular --
    `_guvenlik_kayit_filtresi_uygula`'daki GÖRÜNÜRLÜK kısıtlamasından
    BAĞIMSIZDIR: rol ne olursa olsun (kullanıcı talebi: "Tüm Güvenlik
    Personeli kayıtlar ekranından A B C D Vardiyalarında geçen araçları
    filtreleyip ... arayabilsin") çağrılabilir.

    ÖNEMLİ (2026-09-22 düzeltmesi, bkz. _guvenlik_kayit_filtresi_uygula'nın
    `vardiya_penceresini_atla` parametresinin docstring'i): bu fonksiyon
    kendisi HER ZAMAN sadece BU filtreyi uygular; çağıran taraf (bkz.
    kayitlari_listele/kayitlar_sayfa_bilgisi), `vardiya_adi` doluysa
    `_guvenlik_kayit_filtresi_uygula`'daki KENDİ vardiya penceresi
    kısıtlamasını AYRICA atlamalıdır -- aksi halde iki filtre birbirini
    neredeyse her zaman boşa çıkaran bir AND oluşturur (iki farklı vardiyanın
    pencereleri tanım gereği çakışmaz).

    `vardiya_adi` (zaten `_vardiya_adi_normalize` ile normalize edilmiş
    olmalı) boş/None ise sorgu DEĞİŞMEDEN döner. O isimde HİÇ vardiya
    oturumu yoksa (ör. hiç kullanılmayan bir isim aranırsa) GÜVENLİ TARAF
    seçilir: hiçbir kayıt döndürülmez (`_guvenlik_kayit_filtresi_uygula`'daki
    aynı "hiç oturum yoksa hiçbir şey gösterme" kuralıyla tutarlı)."""
    if not vardiya_adi:
        return sorgu
    # O isimde hiç oturum yoksa EXISTS her satır için yanlış olur -- yani
    # önceki "hiçbir kayıt döndürme" güvenli davranışı aynen korunur.
    return sorgu.filter(_vardiya_oturumu_kosulu(None, vardiya_adi))


def _guvenlik_kayit_filtresi_uygula(sorgu, kullanici: models.Kullanici, db: Session, vardiya_penceresini_atla: bool = False):
    """Verilen SQLAlchemy sorgusuna İKİ BAĞIMSIZ kayıt görünürlüğü
    kısıtlamasını birlikte uygular:

    1) VARDİYA PENCERESİ (yalnızca `kullanici.rol == ROL_GUVENLIK`): bu
       kullanıcının (ya da -- 2026-09-21, bkz. models.Kullanici.vardiya_adi --
       AYNI isimde bir vardiyaya atanmışsa, O VARDİYA GRUBUNUN TÜM üyelerinin)
       vardiya oturumlarından HİÇBİRİNE denk düşmeyen kayıtları eleyen bir OR
       filtresi ekler. Hiç vardiya oturumu yoksa (henüz hiç giriş yapmamışsa)
       GÜVENLİ TARAF seçilir: varsayılan olarak her şeyi göstermek yerine
       HİÇBİR kayıt döndürülmez.
    2) KAMERA/NOKTA ERİŞİMİ (2026-09-21, HERHANGİ bir rol için): kullanıcıya
       bir `kamera_erisim_listesi` kısıtlaması atanmışsa (bkz.
       _kullanicinin_izinli_kamera_adlari -- Kayit.kamera_id ile
       karşılaştırma bu fonksiyonla, "ad" bazlı yapılır, ham id'lerle DEĞİL,
       bkz. o fonksiyonun docstring'indeki kök neden), yalnızca izinli
       kameralardan gelen kayıtlar görünür kalır. Örn. "Lojman Nizamiye"de
       çalışan ve yalnızca o noktanın kameralarını izleyebilen bir hesap,
       genel "Kayıtlar" listesinde gezinerek "Ana Nizamiye"nin geçmiş
       kayıtlarını da GÖREMEZ -- ama BELİRLİ bir plakayı hedefleyen "Plaka
       Analizi" aramasından (bkz. plaka_analiz) KASITLI OLARAK MUAFTIR,
       çünkü bir vardiyanın/noktanın başka bir vardiyada/noktada geçen
       belirli bir aracı tespit edebilmesi meşru bir ihtiyaçtır (kullanıcı
       talebi, 2026-09-21: "A Vardiyasının nöbet saatinde giriş yapan bir
       aracı, B vardiyası geldiğinde tespit edebilmesi gerekiyor").

    İkisi de geçerli değilse (izleyici/operatör/yönetici, kısıtlamasız
    güvenlik) sorgu değişmeden döner.

    `vardiya_penceresini_atla=True` (2026-09-22 GERÇEK ÜRETİMDE BULUNAN HATA
    düzeltmesi): çağıran taraf AYRICA açık bir "Vardiya" adı filtresi (bkz.
    _vardiya_adi_filtresi_uygula) uyguluyorsa, yukarıdaki (1) numaralı KENDİ
    vardiya penceresi kısıtlaması TAMAMEN ATLANIR. Önceden bu iki filtre HER
    ZAMAN ANDlanıyordu: "kayıt BENİM vardiya penceremde OLMALI" VE "kayıt
    filtre olarak seçilen (BAŞKA olabilecek) bir vardiyanın penceresinde
    OLMALI" -- iki FARKLI adlandırılmış vardiyanın pencereleri (tanım gereği,
    aynı anda nöbet tutmadıkları sürece) neredeyse hiç çakışmadığından, bu AND
    neredeyse HER ZAMAN boş sonuç veriyordu. Kullanıcı raporu (2026-09-22,
    ekran görüntüleriyle): "A" vardiyasındaki bir güvenlik hesabı Kayıtlar
    ekranındaki "Vardiya" filtresini "D" olarak seçip aratınca (plakasız
    aratınca bile) "Kayıt bulunamadı" dönüyordu -- oysa gerçekten "D"
    vardiyasına ait bir kayıt VARDI (kısıtlamasız bir görünümde ya da "D"
    vardiyasının KENDİ hesabıyla aratılınca doğru görünüyordu). Bu, filtrenin
    VAR OLMA amacına (yukarıdaki kullanıcı talebi: "Tüm Güvenlik Personeli
    ... A B C D Vardiyalarında geçen araçları filtreleyip ... arayabilsin")
    doğrudan aykırıydı -- bu filtrenin amacı TAM OLARAK kendi vardiya
    kısıtlamasını GEÇİCİ olarak AŞMAKTI, ona ek bir kısıtlama eklemek değil.
    KAMERA/NOKTA erişim kısıtlaması (2 numaralı madde) bundan ETKİLENMEZ --
    bu, vardiya zamanlamasından bağımsız gerçek bir fiziksel erişim sınırı
    olduğu için açık bir vardiya filtresiyle birlikte de HER ZAMAN
    uygulanmaya devam eder."""
    if kullanici.rol == ROL_GUVENLIK and not vardiya_penceresini_atla:
        # bkz. _vardiya_oturumu_kosulu (oturum yoksa -> hiçbir kayıt; önceki
        # `filter(false())` davranışıyla aynı).
        sorgu = sorgu.filter(_vardiya_oturumu_kosulu(kullanici.id, kullanici.vardiya_adi))
    izinli_kameralar = _kullanicinin_izinli_kamera_adlari(kullanici)
    if izinli_kameralar is not None:
        sorgu = sorgu.filter(models.Kayit.kamera_id.in_(izinli_kameralar))
    return sorgu


def _guvenlik_kayit_gorunur_mu(
    kayit: "models.Kayit", kullanici: models.Kullanici, db: Session, vardiya_adi_filtresi: Optional[str] = None,
) -> bool:
    """Tek bir Kayit'in (ör. `/disa-aktar/pdf/kayit/{id}` gibi tekil dışa
    aktarma uçlarında) bu kullanıcı için görünür olup olmadığını kontrol eder
    -- `_guvenlik_kayit_filtresi_uygula` ile AYNI iki kısıtlamayı (vardiya
    penceresi + kamera erişimi) tek bir kayda uygular.

    `vardiya_adi_filtresi` (zaten normalize edilmiş olmalı -- bkz.
    _vardiya_adi_normalize): Kayıtlar ekranındaki listede kullanıcı açık bir
    "Vardiya" filtresiyle (ör. kendi vardiyası DIŞINDA bir vardiyayı) bu
    kaydı zaten görebiliyorsa, o kaydın tekil PDF indirmesi de aynı gerekçeyle
    (bkz. _guvenlik_kayit_filtresi_uygula'daki `vardiya_penceresini_atla`
    notu) izin VERMELİDİR -- aksi halde kullanıcı listede gördüğü bir kaydı
    tıklayıp indiremez, "Bu kayıt vardiyanıza ait değil" hatası alırdı (liste
    doğru filtrelendikten SONRA bulunan ikinci bir gerçek üretim hatası).
    Verilirse KENDİ vardiya penceresi kontrolü yerine, kaydın BU vardiya
    adının (`vardiya_adi_filtresi`) herhangi bir oturum penceresine denk
    düşüp düşmediği kontrol edilir."""
    izinli_kameralar = _kullanicinin_izinli_kamera_adlari(kullanici)
    if izinli_kameralar is not None and kayit.kamera_id not in izinli_kameralar:
        return False
    if kullanici.rol != ROL_GUVENLIK:
        return True
    if vardiya_adi_filtresi:
        pencereler = _kullanicinin_vardiya_pencereleri(db, None, vardiya_adi_filtresi)
    else:
        pencereler = _kullanicinin_vardiya_pencereleri(db, kullanici.id, kullanici.vardiya_adi)
    return any(_pencere_icinde_mi(kayit.tarih_saat, baslangic, bitis) for baslangic, bitis in pencereler)


def _kayitlara_kisi_adini_ekle(kayitlar: list, db: Session) -> None:
    """`kayitlar` listesindeki HER kayda, varsa bağlı olduğu Kisi'nin (bkz.
    Kayit.kisi_id) ad_soyad'ını bellek-içi bir `kisi_adi` özniteliği olarak
    ekler -- bu bir ORM sütunu DEĞİLDİR, yalnızca bu yanıt için hesaplanıp
    schemas.KayitCevap.kisi_adi tarafından `from_attributes` ile okunur
    (öznitelik hiç atanmamış bir Kayit için de alan sorunsuzca varsayılan
    `None`a düşer).

    2026-09-22 GERÇEK KULLANICI GERİ BİLDİRİMİ: "Kaydı Düzenle" ekranındaki
    "Kişi eşleştirmesi" alanından bir kişi seçilip kaydedildiğinde,
    kisi_id/kisi_tip_anlik backend'de doğru güncelleniyordu (bkz.
    kayit_duzenle) AMA Kayıtlar/Plaka Analizi tablolarının HİÇBİRİ
    eşleştirilen kişinin ADINI göstermiyordu -- yalnızca TİPİNİ (Abone/
    Personel/Ziyaretçi rozeti) gösteren "Kişi/Tip" sütunu vardı, bu yüzden
    kullanıcıya "seçtim ama hiçbir yerde gözükmüyor" gibi görünüyordu; bu
    yeni alan tam olarak bu boşluğu dolduruyor.

    N+1 sorgudan kaçınmak için (bkz. _kayitlarin_vardiya_adlarini_ekle'deki
    aynı gerekçe) TÜM ilgili Kişi'ler TEK SEFERDE çekilip bellekte
    eşleştirilir."""
    if not kayitlar:
        return
    kisi_idler = {k.kisi_id for k in kayitlar if k.kisi_id is not None}
    if not kisi_idler:
        for k in kayitlar:
            k.kisi_adi = None
        return
    adlar = dict(
        db.query(models.Kisi.id, models.Kisi.ad_soyad)
        .filter(models.Kisi.id.in_(kisi_idler))
        .all()
    )
    for k in kayitlar:
        k.kisi_adi = adlar.get(k.kisi_id)


def _kayitlarin_vardiya_adlarini_ekle(kayitlar: list, db: Session) -> None:
    """`kayitlar` listesindeki HER kayda, o kaydın gerçekleştiği anda AÇIK
    olan (bkz. _pencere_icinde_mi) adlandırılmış vardiya oturumlarının
    (bkz. models.Kullanici.vardiya_adi) isimlerinden oluşan bellek-içi bir
    `vardiya_adi` özniteliği ekler -- bu bir ORM SÜTUNU DEĞİLDİR, yalnızca bu
    yanıt için hesaplanır ve schemas.KayitCevap.vardiya_adi tarafından
    `from_attributes` ile okunur (bkz. o alanın docstring'i; öznitelik hiç
    ATANMAMIŞ bir Kayit için de alan sorunsuzca varsayılan `None`a düşer).

    2026-09-21 kullanıcı talebi: "kayıtlar ekranına yeni bir sütun
    ekleyebilir miyiz. A B C D Vardiyaları olacak şekilde ... Tüm Güvenlik
    Personeli kayıtlar ekranından A B C D Vardiyalarında geçen araçları
    filtreleyip plaka arayınca karşısına kimin vardiyasında girip çıktığı
    gözükebilsin." Bu, RAPOR (Excel/PDF) çıktısındaki ad+saat etiketinden
    (bkz. _vardiya_etiketleri_haritasi) BİLİNÇLİ olarak AYRI bir özelliktir:
    adlandırılmamış (vardiya_adi IS NULL) hesapların oturumları bu sütuna
    KATKI YAPMAZ -- yalnızca rapor metninde görünürler.

    Aynı anda BİRDEN FAZLA FARKLI adlandırılmış vardiya açık olabilir (ör.
    Ana Nizamiye'de "A", Lojman'da "B" aynı gerçek zaman diliminde
    çalışıyor olabilir) -- bu durumda tüm farklı adlar görülme sırasına göre
    "/" ile birleştirilir; AYNI ad birden fazla hesapta (ör. Ana Nizamiye VE
    Lojman ikisi de "A") açıksa TEKRARLANMAZ.

    N+1 sorgudan kaçınmak için (bkz. _vardiya_etiketleri_haritasi'ndeki aynı
    ölçek gerekçesi) TÜM adlandırılmış vardiya oturumları TEK SEFERDE
    çekilip bellekte eşleştirilir."""
    if not kayitlar:
        return
    # PERFORMANS (2026-09-25): yalnızca bu kayıtların zaman aralığıyla
    # ÇAKIŞAN oturumlar çekilir (eskiden sistemin kurulduğu günden beri TÜM
    # oturumlar -- tek bir kaydın detayı için bile) ve eşleştirme her kaydı
    # her oturumla karşılaştırmak yerine süpürme algoritmasıyla yapılır --
    # bkz. backend/vardiya_eslestirme.py.
    zamanlar = [k.tarih_saat for k in kayitlar if k.tarih_saat is not None]
    oturumlar = []
    if zamanlar:
        oturumlar = (
            db.query(models.VardiyaOturumu.giris_zamani, models.VardiyaOturumu.cikis_zamani, models.Kullanici.vardiya_adi)
            .join(models.Kullanici, models.VardiyaOturumu.kullanici_id == models.Kullanici.id)
            .filter(
                models.Kullanici.vardiya_adi.isnot(None),
                models.VardiyaOturumu.giris_zamani <= max(zamanlar),
                or_(models.VardiyaOturumu.cikis_zamani.is_(None), models.VardiyaOturumu.cikis_zamani > min(zamanlar)),
            )
            .order_by(models.VardiyaOturumu.id)
            .all()
        )
    eslesmeler = kayitlari_oturumlarla_eslestir(
        [(i, k.tarih_saat) for i, k in enumerate(kayitlar)],
        [(giris, cikis, ad) for giris, cikis, ad in oturumlar],
    )
    for i, k in enumerate(kayitlar):
        adlar = []
        for vardiya_adi in eslesmeler.get(i, []):
            if vardiya_adi not in adlar:
                adlar.append(vardiya_adi)
        k.vardiya_adi = "/".join(adlar) if adlar else None


def _guvenlik_oturum_baslat(db: Session, kullanici: models.Kullanici) -> None:
    """`kullanici.rol == ROL_GUVENLIK` ise başarılı bir `/auth/giris`
    çağrısının hemen ardından çağrılır (bkz. giris_yap): bu kullanıcının
    unutulmuş, hâlâ AÇIK kalmış önceki oturumu varsa (bkz. VardiyaOturumu
    docstring'indeki "unutulan çıkış" notu) bu ANDA kapatır, ardından YENİ
    bir oturum açar. Böylece unutulan bir çıkış, bir SONRAKİ gerçek vardiyanın
    kayıtlarına asla karışmaz -- her giriş, en fazla BİR açık oturumla
    sonuçlanır."""
    if kullanici.rol != ROL_GUVENLIK:
        return
    simdi = datetime.now()
    acik_onceki = (
        db.query(models.VardiyaOturumu)
        .filter(models.VardiyaOturumu.kullanici_id == kullanici.id, models.VardiyaOturumu.cikis_zamani.is_(None))
        .all()
    )
    for onceki in acik_onceki:
        onceki.cikis_zamani = simdi
    db.add(models.VardiyaOturumu(kullanici_id=kullanici.id, giris_zamani=simdi))
    db.commit()


# ================================================================
# VARDİYA OTOMATİK KAPAMA (8 SAAT) — kullanıcı talebi (2026-09-21)
# ================================================================
VARDIYA_MAKS_SURE_SAAT = 8
VARDIYA_OTOMATIK_KAPAMA_ARALIK_SN = 300  # her 5 dakikada bir kontrol et


def _vardiya_otomatik_kapama_calistir(db: Session) -> int:
    """TEK SEFERLİK çalıştırma -- 8 saati aşan, hâlâ AÇIK (unutulmuş) tüm
    vardiya oturumlarını kapatır ve kaç tanesinin kapatıldığını döner (bkz.
    _goruntu_temizle_calistir'deki AYNI "döngü/tek-çalıştırma" ayrımı --
    döngü fonksiyonu test edilemez ama bu fonksiyon doğrudan testlerde
    çağrılabilir).

    `cikis_zamani`, bu fonksiyonun ÇAĞRILDIĞI an DEĞİL, `giris_zamani + 8
    saat` olarak ayarlanır -- yani kayıt görünürlüğü GERÇEKTEN 8 saatlik
    pencereyle sınırlanır; kontrol ANI (ör. 8 saat 3 dakika sonra fark
    edilmesi) görünürlük sınırını KAYDIRMAZ."""
    simdi = datetime.now()
    sinir = simdi - timedelta(hours=VARDIYA_MAKS_SURE_SAAT)
    acik_ve_gecmis = (
        db.query(models.VardiyaOturumu)
        .filter(
            models.VardiyaOturumu.cikis_zamani.is_(None),
            models.VardiyaOturumu.giris_zamani <= sinir,
        )
        .all()
    )
    for oturum in acik_ve_gecmis:
        oturum.cikis_zamani = oturum.giris_zamani + timedelta(hours=VARDIYA_MAKS_SURE_SAAT)
    if acik_ve_gecmis:
        db.commit()
    return len(acik_ve_gecmis)


async def _vardiya_otomatik_kapama_dongu() -> None:
    """Sonsuz döngü: "unutulan çıkış" (bkz. VardiyaOturumu docstring'i ve
    yukarıdaki _guvenlik_oturum_baslat) için, bir SONRAKİ girişe kadar
    BEKLEMEDEN, ZAMANA dayalı bir ikinci güvenlik ağı ekler.

    2026-09-21 kullanıcı talebi: "A B C D vardiyaları 8 saat bazlı çalışmakta
    yani vardiya amiri çıkış yapmayı unutsa bile giriş saatinden 8 saat sonra
    otomatik çıkış yapılsın." `_guvenlik_oturum_baslat`'taki öz-düzeltme
    yalnızca AYNI hesabın bir SONRAKİ girişinde tetiklenir -- hesap hiç
    tekrar giriş yapmazsa oturum eskiden SONSUZA kadar açık kalırdı.

    Bu düzeltme, "Vardiya Grupları" (bkz. models.Kullanici.vardiya_adi)
    özelliğiyle BİRLİKTE ayrıca önem kazandı: unutulmuş, süresiz açık bir
    oturum artık yalnızca o hesabın DEĞİL, AYNI vardiya adını paylaşan TÜM
    hesapların (bkz. _kullanicinin_vardiya_pencereleri) kayıt görünürlüğünü
    de SINIRSIZCA genişletiyordu -- bu döngü olmadan, unutulan tek bir çıkış
    tüm vardiya grubuna aşırı geniş görünürlük kazandırabilirdi.

    Gerçek işi (bkz. yukarısı) _vardiya_otomatik_kapama_calistir yapar --
    burada yalnızca periyodik çağrı ve hata izolasyonu var."""
    while True:
        try:
            db = SessionLocal()
            try:
                kapatilan = _vardiya_otomatik_kapama_calistir(db)
                if kapatilan:
                    logger.info(
                        "Vardiya otomatik kapama: %d oturum giriş saatinden %d saat sonrasına "
                        "ayarlanarak kapatıldı (unutulan çıkış)",
                        kapatilan, VARDIYA_MAKS_SURE_SAAT,
                    )
            finally:
                db.close()
        except Exception as exc:
            logger.error("[vardiya-otomatik-kapama] Döngüde hata: %s", exc, exc_info=True)
        await asyncio.sleep(VARDIYA_OTOMATIK_KAPAMA_ARALIK_SN)


# Basit bellek-içi bruteforce koruması: kullanıcı adı -> (başarısız deneme sayısı, kilit bitiş zamanı)
_GIRIS_DENEME_LIMITI = 5
_GIRIS_KILIT_SURESI_SN = 15 * 60
_basarisiz_girisler: dict[str, tuple[int, float]] = {}


def _giris_kilitli_mi(kullanici_adi: str) -> float:
    """Kilitliyse kalan saniyeyi, değilse 0 döner."""
    kayit = _basarisiz_girisler.get(kullanici_adi)
    if not kayit:
        return 0
    sayac, kilit_bitis = kayit
    if sayac < _GIRIS_DENEME_LIMITI:
        return 0
    kalan = kilit_bitis - time.time()
    return kalan if kalan > 0 else 0


# GÜVENLİK/KARARLILIK: `_basarisiz_girisler` VAR OLAN bir kullanıcı başarıyla
# giriş yaptığında temizlenir (bkz. giris_yap), ama VAR OLMAYAN bir kullanıcı
# adıyla (ör. otomatik bir enumeration denemesiyle) yapılan başarısız
# denemeler hiçbir zaman kendiliğinden silinmez — her benzersiz sahte
# kullanıcı adı sözlükte kalıcı bir girdi bırakır. Aylarca yeniden
# başlatılmadan çalışması beklenen bir üretim sürecinde bu, kasıtlı olarak
# (her denemede farklı bir kullanıcı adı kullanarak) tetiklenebilecek yavaş
# bir bellek sızıntısıdır. Bu döngü, kilidi çoktan sona ermiş (artık aktif
# bir tehdit oluşturmayan) girdileri periyodik olarak temizler.
GIRIS_DENEME_TEMIZLIK_ARALIK_SN = 30 * 60  # 30 dakikada bir


async def _basarisiz_giris_temizlik_dongu() -> None:
    while True:
        await asyncio.sleep(GIRIS_DENEME_TEMIZLIK_ARALIK_SN)
        try:
            simdi = time.time()
            eskiler = [
                k for k, (_sayac, kilit_bitis) in list(_basarisiz_girisler.items())
                if simdi - kilit_bitis > _GIRIS_KILIT_SURESI_SN
            ]
            for k in eskiler:
                _basarisiz_girisler.pop(k, None)
            if eskiler:
                logger.debug("Başarısız giriş kayıtları temizlendi: %d girdi", len(eskiler))
        except Exception as exc:
            logger.error("[giriş-temizlik] Temizlik döngüsünde hata: %s", exc, exc_info=True)


@app.on_event("startup")
async def _basarisiz_giris_temizligini_baslat():
    asyncio.ensure_future(_basarisiz_giris_temizlik_dongu())


@app.post("/auth/ilk-yonetici", response_model=schemas.KullaniciCevap)
def ilk_yonetici_olustur(istek: schemas.IlkYoneticiOlustur, db: Session = Depends(get_db)):
    if db.query(models.Kullanici).count() > 0:
        raise HTTPException(409, "Yönetici hesabı zaten oluşturulmuş")
    if len(istek.parola) < 8:
        raise HTTPException(400, "Parola en az 8 karakter olmalıdır")
    kullanici = models.Kullanici(
        kullanici_adi=istek.kullanici_adi.strip(),
        parola_hash=_parola_hashle(istek.parola),
        rol="yonetici",
    )
    db.add(kullanici)
    db.commit()
    db.refresh(kullanici)
    return kullanici


@app.get("/auth/durum")
def auth_durumu(db: Session = Depends(get_db)):
    return {"kurulum_tamamlandi": db.query(models.Kullanici).count() > 0}


@app.post("/auth/giris", dependencies=[Depends(_hiz_sinir_giris)])
def giris_yap(istek: schemas.GirisIstegi, db: Session = Depends(get_db)):
    kullanici_adi = istek.kullanici_adi.strip()
    kalan_kilit = _giris_kilitli_mi(kullanici_adi)
    if kalan_kilit > 0:
        logger.warning("Kilitli hesaba giriş denemesi: %s", kullanici_adi)
        raise HTTPException(429, f"Çok fazla başarısız deneme. {int(kalan_kilit // 60) + 1} dakika sonra tekrar deneyin.")

    kullanici = db.query(models.Kullanici).filter(models.Kullanici.kullanici_adi == kullanici_adi).first()
    if not kullanici or not kullanici.aktif or not _parola_dogrula(istek.parola, kullanici.parola_hash):
        sayac = _basarisiz_girisler.get(kullanici_adi, (0, 0.0))[0] + 1
        _basarisiz_girisler[kullanici_adi] = (sayac, time.time() + _GIRIS_KILIT_SURESI_SN)
        logger.warning("Başarısız giriş denemesi (%d/%d): %s", sayac, _GIRIS_DENEME_LIMITI, kullanici_adi)
        raise HTTPException(401, "Kullanıcı adı veya parola hatalı")

    _basarisiz_girisler.pop(kullanici_adi, None)
    kullanici.son_giris = datetime.now()
    db.commit()
    # Öz-hizmet vardiya oturumu (bkz. 2026-09-20 "Öz-Hizmet Vardiya
    # Oturumları" notu, README): rol=="güvenlik" için burada YENİ bir
    # VardiyaOturumu açılır (ve varsa unutulmuş önceki açık oturum kapatılır).
    _guvenlik_oturum_baslat(db, kullanici)
    logger.info("Başarılı giriş: %s", kullanici_adi)
    return {"token": _token_uret(kullanici.id), "kullanici": kullanici}


@app.post("/auth/cikis")
def cikis_yap(db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_giris_gerekli)):
    """İstemcinin "Çıkış Yap" butonuna bastığında (bkz. frontend/app.js::
    oturumKapat) token'ı silmeden HEMEN ÖNCE çağrılır. `kullanici.rol ==
    ROL_GUVENLIK` için o anki AÇIK VardiyaOturumu'nu bu anda kapatır --
    vardiya biter, o andan sonraki hiçbir geçiş artık bu kullanıcının
    listesinde görünmez (bkz. _kullanicinin_vardiya_pencereleri).

    Diğer roller için bu uç nokta zararsızdır (yalnızca 200 döner). Token'ın
    kendisi için sunucu tarafında ayrı bir "iptal listesi" TUTULMUYOR (bkz.
    _token_uret/_token_coz'daki önceden var olan tasarım) -- bu uç nokta
    yalnızca vardiya oturumunu kapatmak içindir, JWT/oturum güvenliğiyle
    ilgili DEĞİLDİR; istemci token'ı zaten kendi tarafında hemen siliyor.
    """
    if kullanici.rol == ROL_GUVENLIK:
        simdi = datetime.now()
        acik = (
            db.query(models.VardiyaOturumu)
            .filter(models.VardiyaOturumu.kullanici_id == kullanici.id, models.VardiyaOturumu.cikis_zamani.is_(None))
            .all()
        )
        for oturum in acik:
            oturum.cikis_zamani = simdi
        if acik:
            db.commit()
            logger.info("Vardiya oturumu kapatıldı (çıkış): kullanıcı=%s", kullanici.kullanici_adi)
    return {"mesaj": "Çıkış yapıldı"}


@app.get("/auth/me", response_model=schemas.KullaniciCevap)
def mevcut_kullanici(kullanici: models.Kullanici = Depends(_giris_gerekli)):
    # NOT: burada kasıtlı olarak _personel_girisi_gerekli DEĞİL, temel
    # _giris_gerekli kullanılıyor -- "sakin" rolündeki bir hesap da giriş
    # sonrası kendi rolünü öğrenip doğru arayüze (öz-hizmet paneli) yönlenmek
    # için bu uç noktayı çağırabilmeli.
    return kullanici


@app.get("/goruntuler/{dosya_adi}")
def gorsel_getir(dosya_adi: str, kucuk: bool = False, _: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Araç/sürücü görsellerini (plaka + fotoğraf — KVKK kapsamında kişisel
    veri) YALNIZCA giriş yapmış kullanıcılara servis eder.

    GÜVENLİK GEÇMİŞİ: bu yol önceden `app.mount("/goruntuler", StaticFiles(...))`
    ile TAMAMEN kimliksiz servis ediliyordu; dosya adı kalıbı tahmin
    edilebilir olduğu için (`PLAKA_unixzaman.jpg`, bkz. otomatik-kayıt uç
    noktası) ağdaki (veya ileride bir ters vekil arkasında internete açılan)
    HERKES, hiç giriş yapmadan araç+sürücü fotoğraflarını indirebilir ya da
    dosya adlarını deneyerek numaralandırabilirdi — bu, aynı dosyada RTSP
    parolasını maskeleme veya MJPEG akışını bearer-token'a bağlama gibi
    gösterilen özenle doğrudan çelişiyordu. `<img>` etiketi Authorization
    header taşıyamadığı için frontend bu uca artık `fetch()` + Bearer token
    ile erişip yanıtı bir blob URL'ine çeviriyor (bkz. app.js).
    """
    # Yol geçişini (path traversal) engelle: yalnızca DÜZ dosya adı kabul
    # edilir; herhangi bir dizin ayırıcı veya ".." reddedilir.
    if "/" in dosya_adi or "\\" in dosya_adi or ".." in dosya_adi:
        raise HTTPException(400, "Geçersiz dosya adı")
    tam_yol = os.path.join(GORUNTU_KLASORU, dosya_adi)
    if not os.path.isfile(tam_yol):
        raise HTTPException(404, "Görsel bulunamadı")
    # PERFORMANS (2026-09-25, kullanıcı: "kayıtlarda araç arattığımda ...
    # yavaş"): tablolar/kartlar 96x68 px'lik küçük resimler için TAM kamera
    # karesini (150-400 KB) indiriyordu -- 50 satırlık bir sayfa her
    # yenilemede ~10-20 MB. `?kucuk=1` ile disk önbelleğindeki küçük resim
    # (~20 KB) döner (bkz. backend/kucuk_gorsel.py); üretilemezse orijinale
    # düşülür. Dosya adları benzersiz olduğundan (bkz. kayit_ekle_otomatik)
    # tarayıcının oturum boyunca (1 saat) önbelleğe almasına izin veriyoruz:
    # tablo her yeni geçişte yeniden çizildiğinde aynı görseller tekrar
    # indirilmesin. `private`: ara vekil sunucular saklamaz.
    servis_yolu = (kucuk_gorsel.kucuk_gorsel_yolu(tam_yol) or tam_yol) if kucuk else tam_yol
    return FileResponse(servis_yolu, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/")
def anasayfa():
    return FileResponse(
        os.path.join(FRONTEND_KLASORU, "index.html"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.get("/saglik")
def saglik_kontrolu(db: Session = Depends(get_db)):
    """İzleme/servis denetleyicileri için basit sağlık kontrolü uç noktası."""
    try:
        db.execute(text("SELECT 1"))
        veritabani_durumu = "tamam"
    except Exception as e:  # noqa: BLE001 - izleme amaçlı, hatayı yutup durumu bildiriyoruz
        logger.error("Sağlık kontrolünde veritabanı hatası: %s", e)
        veritabani_durumu = "hata"
    return {"durum": "calisiyor", "veritabani": veritabani_durumu}


# ==================================================================
# LİSANS YÖNETİMİ
# ==================================================================

def _cihaz_kodu() -> str:
    return lisans_modulu.cihaz_kodu()


def _lisans_durumunu_oku() -> dict:
    varsayilan = {
        "aktif": False,
        "anahtar": None,
        "kamera_limiti": 0,
        "bitis_tarihi": None,
        "cihaz_kodu": _cihaz_kodu(),
    }
    if not os.path.exists(LISANS_DOSYASI):
        return varsayilan
    try:
        with open(LISANS_DOSYASI, "r", encoding="utf-8") as dosya:
            return {**varsayilan, **json.load(dosya)}
    except (OSError, json.JSONDecodeError):
        return varsayilan


def _lisans_aktif_mi() -> bool:
    """Lisansın GERÇEKTEN aktif olup olmadığını, diskteki bayrağa güvenmeden,
    HER ÇAĞRIDA imzayı yeniden doğrulayarak belirler.

    ÖNCEKİ DAVRANIŞ: bu fonksiyon yalnızca `license.json`'daki statik "aktif"
    booleanına ve ayrı bir "bitis_tarihi" KOPYASINA bakıyordu. Bu iki alan
    yalnızca aktivasyon ANINDA (`lisans_aktive_et`), imzalı anahtarın
    `lisans_modulu.coz()` ile doğrulanmasının bir SONUCU olarak dosyaya
    yazılıyordu — ama sonraki hiçbir kontrolde imza TEKRAR doğrulanmıyordu.
    Yani `license.json` dosyasına (ör. bir metin editörüyle) doğrudan
    `"aktif": true` ve uzak bir `"bitis_tarihi"` yazan biri, GEÇERLİ imzalı
    bir anahtara hiç ihtiyaç duymadan lisansı süresiz aktif gösterebiliyordu
    — "tam lisanslı" bir ürün için kabul edilemez bir açıktı. Artık HER
    kontrolde saklı `anahtar` alanının kendisi yeniden doğrulanıyor (imza +
    süre + cihaz kilidi); `"aktif"`/`"bitis_tarihi"` alanları artık yalnızca
    bilgi/gösterim amaçlıdır, yetkilendirme kararı bunlara dayanmaz."""
    anahtar = _lisans_durumunu_oku().get("anahtar")
    if not anahtar:
        return False
    try:
        lisans_modulu.coz(anahtar, beklenen_cihaz_kodu=_cihaz_kodu())
    except lisans_modulu.LisansGecersiz:
        return False
    return True


def _lisans_anahtarini_coz(anahtar: str) -> dict:
    try:
        return lisans_modulu.coz(anahtar, beklenen_cihaz_kodu=_cihaz_kodu())
    except lisans_modulu.LisansGecersiz as exc:
        raise HTTPException(400, str(exc))


def _lisans_durumunu_yaz(durum: dict) -> None:
    with open(LISANS_DOSYASI, "w", encoding="utf-8") as dosya:
        json.dump(durum, dosya, ensure_ascii=False, indent=2)


_LISANS_UYARI_ESIK_GUN = 14  # bitişe bu kadar veya daha az gün kalınca "yakında dolacak" uyarısı gösterilir


def _lisans_kalan_gun_ekle(durum: dict) -> dict:
    """`durum` sözlüğüne `kalan_gun` (bitişe kaç gün kaldığı, tam sayı) ve
    `yakinda_doluyor` (eşik altına düştü mü) alanlarını ekler.

    KÖK NEDEN (2026-09-20, geniş kapsamlı denetim): lisans süresi kontrolü
    tamamen İKİLİ idi (aktif/pasif) -- süre dolmadan önce HİÇBİR uyarı
    yoktu. Bekçi döngüsü (`_kamera_bekcisi`), lisans süresi dolduğu ANDA
    (önceden hiçbir belirti olmadan) TÜM kamera pipeline'larını durdurup
    bariyer/ANPR'ı komple karartıyor -- sahada bu, müşteriye önceden
    haber verilmeden aniden "sistem çalışmıyor" şikayetine dönüşecek bir
    senaryo. Bu fonksiyon yalnızca PASİF görünürlük ekler (lisans üretme/
    doğrulama mekanizmasının kendisine HİÇ dokunmuyor) -- panel artık
    süre dolmadan `_LISANS_UYARI_ESIK_GUN` gün önceden turuncu bir uyarı
    gösterebiliyor."""
    durum["kalan_gun"] = None
    durum["yakinda_doluyor"] = False
    bitis_metni = durum.get("bitis_tarihi")
    if durum.get("aktif") and bitis_metni:
        try:
            bitis = datetime.fromisoformat(bitis_metni).date()
        except ValueError:
            return durum
        kalan = (bitis - datetime.now().date()).days
        durum["kalan_gun"] = kalan
        durum["yakinda_doluyor"] = 0 <= kalan <= _LISANS_UYARI_ESIK_GUN
    return durum


@app.get("/lisans")
def lisans_durumunu_getir(_: models.Kullanici = Depends(_personel_girisi_gerekli)):
    durum = _lisans_durumunu_oku()
    durum["aktif"] = _lisans_aktif_mi()
    return _lisans_kalan_gun_ekle(durum)


@app.post("/lisans/aktive-et")
def lisans_aktive_et(istek: schemas.LisansAktivasyonIstegi, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI)
    temiz_anahtar = istek.anahtar.strip()
    payload = _lisans_anahtarini_coz(temiz_anahtar)
    durum = _lisans_durumunu_oku()
    if not payload.get("cihaz_kodu"):
        payload["cihaz_kodu"] = _cihaz_kodu()
    durum.update({
        "aktif": True,
        "anahtar": temiz_anahtar,
        "lisans_id": payload["lisans_id"],
        "musteri": payload["musteri"],
        "kamera_limiti": int(payload["kamera_limiti"]),
        "baslangic_tarihi": payload["baslangic_tarihi"],
        "bitis_tarihi": payload["bitis_tarihi"],
        "cihaz_kodu": payload["cihaz_kodu"],
    })
    _lisans_durumunu_yaz(durum)
    durum["aktif"] = _lisans_aktif_mi()
    _denetim_kaydet(
        db, kullanici.kullanici_adi, "lisans_aktivasyon",
        f"müşteri={payload['musteri']}, lisans_id={payload['lisans_id']}, bitiş={payload['bitis_tarihi']}",
    )
    return _lisans_kalan_gun_ekle(durum)


def _kameralari_oku() -> list:
    if not os.path.exists(KAMERA_DOSYASI):
        return []
    try:
        with open(KAMERA_DOSYASI, "r", encoding="utf-8") as dosya:
            return json.load(dosya)
    except (OSError, json.JSONDecodeError):
        return []


def _kamera_id_listesini_dogrula(id_listesi: list) -> list:
    """"Nizamiye Bazlı Kamera Erişimi" (2026-09-21): bir kullanıcıya kamera
    erişim kısıtlaması atanırken gönderilen id listesini `cameras.json`'daki
    GERÇEK kamera id'leriyle doğrular -- var olmayan/typo bir id sessizce
    kaydedilip o hesabı (kısıtlama artık NULL olmadığı için) fiilen HİÇBİR
    kameraya erişemez hale getirmesin diye (bkz. kullanici_ekle,
    kullanici_guncelle). Yinelenenler elenir, sıra korunur."""
    gecerli_idler = {k["id"] for k in _kameralari_oku()}
    temiz = []
    for kid in id_listesi:
        kid = str(kid).strip()
        if not kid:
            continue
        if kid not in gecerli_idler:
            raise HTTPException(400, f"'{kid}' id'li bir kamera bulunamadı")
        if kid not in temiz:
            temiz.append(kid)
    return temiz


def _kameralari_yaz(kameralar: list) -> None:
    """DÜZELTME (2026-09-25): önceden dosya doğrudan "w" modunda açılıp
    üzerine yazılıyordu -- bu, `_kameralari_oku`'yu AYNI ANDA çağıran başka
    bir istek (ör. bir okuma isteği kilit dışında çalışıyorsa) json.dump
    henüz bitmeden dosyayı yarım/kesik okuyup `json.JSONDecodeError`'a
    (ve dolayısıyla sessizce boş kamera listesi dönmesine, bkz.
    _kameralari_oku'nun except bloğu) düşmesine yol açabiliyordu. Artık önce
    aynı dizinde geçici bir dosyaya tam olarak yazılıp, ardından işletim
    sisteminin ATOMİK `os.replace` işlemiyle asıl dosyanın yerine konuyor --
    bir okuyucu her zaman ya eski ya da yeni içeriğin TAMAMINI görür, hiçbir
    zaman yarısını görmez."""
    dizin = os.path.dirname(os.path.abspath(KAMERA_DOSYASI)) or "."
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=dizin, prefix=".cameras_tmp_", suffix=".json", delete=False
    ) as gecici:
        json.dump(kameralar, gecici, ensure_ascii=False, indent=2)
        gecici_yol = gecici.name
    os.replace(gecici_yol, KAMERA_DOSYASI)


def _kamera_guvenli_gorunum(kamera: dict) -> dict:
    """RTSP parolasını istemciye göndermeden kamera kaydını döndürür."""
    sonuc = dict(kamera)
    parcalar = urlsplit(str(sonuc.get("rtsp_url", "")))
    if parcalar.username or parcalar.password:
        host = parcalar.hostname or ""
        if parcalar.port:
            host = f"{host}:{parcalar.port}"
        sonuc["rtsp_url"] = urlunsplit((parcalar.scheme, f"{parcalar.username or 'kamera'}:****@{host}", parcalar.path, parcalar.query, parcalar.fragment))
    return sonuc


@app.get("/kameralar")
def kameralari_getir(kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    izinli = _kullanicinin_izinli_kameralari(kullanici)
    kameralar = _kameralari_oku()
    if izinli is not None:
        # "Nizamiye Bazlı Kamera Erişimi" (2026-09-21): kısıtlı bir hesap,
        # canlı izleme listesinde YALNIZCA kendi noktasına atanmış kameraları
        # görür -- bkz. models.Kullanici.kamera_erisim_listesi'nin docstring'i.
        kameralar = [k for k in kameralar if k["id"] in izinli]
    sonuclar = []
    for k in kameralar:
        gorunum = _kamera_guvenli_gorunum(k)
        p = _aktif_pipelineler.get(k["id"])
        canli_thread = p is not None and p.calisiyor and p.thread_canli_mi()
        gorunum["pipeline_calisiyor"] = canli_thread
        gorunum["kutuphaneler_mevcut"] = _CAM_LIBS
        if p is not None:
            gorunum.update({k2: v2 for k2, v2 in p.durum_bilgisi().items() if k2 != "calisiyor"})
            if isinstance(gorunum.get("dahua"), dict):
                # Ham olay metinleri yalnızca teşhis ekranında (dahua-durum,
                # yönetici/operatör) gösterilir; bu sık çağrılan listede değil.
                gorunum["dahua"] = {k3: v3 for k3, v3 in gorunum["dahua"].items() if k3 != "ham_ornekler"}
        else:
            gorunum.update({"son_kare_yasi_sn": None, "donmus": False,
                             "yeniden_baglanma_sayisi": 0, "calisma_suresi_sn": 0})
        sonuclar.append(gorunum)
    return sonuclar


@app.post("/kameralar/{kamera_id}/yeniden-baslat")
def kamera_yeniden_baslat(kamera_id: str, kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    kamera = next((k for k in _kameralari_oku() if k["id"] == kamera_id), None)
    if not kamera:
        raise HTTPException(404, "Kamera bulunamadı")
    _pipeline_durdur(kamera_id)
    time.sleep(0.3)
    basarili = _pipeline_baslat(kamera)
    return {"basarili": basarili, "kutuphaneler_mevcut": _CAM_LIBS}


@app.patch("/kameralar/{kamera_id}/aktif")
def kamera_aktif_toggle(kamera_id: str, kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    with _kamera_dosya_kilit:
        kameralar = _kameralari_oku()
        kamera = next((k for k in kameralar if k["id"] == kamera_id), None)
        if not kamera:
            raise HTTPException(404, "Kamera bulunamadı")
        kamera["aktif"] = not kamera.get("aktif", True)
        _kameralari_yaz(kameralar)
    if not kamera["aktif"]:
        _pipeline_durdur(kamera_id)
    else:
        _pipeline_baslat(kamera)
    return {"id": kamera_id, "aktif": kamera["aktif"]}


@app.patch("/kameralar/{kamera_id}/yon")
def kamera_yon_degistir(kamera_id: str, veri: schemas.KameraYonGuncelle, kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Var olan bir kameranın giriş/çıkış yönünü DEĞİŞTİRİR (RTSP adresi/parola
    dokunulmadan) -- örn. iki kamera aynı fiziksel bariyeri/geçidi farklı
    açılardan izliyorsa ve biri yanlışlıkla ters yönle tanımlanmışsa (bkz.
    README.md'deki 2026-09-17 notu: aynı plakanın aynı dakikada hem "giriş" hem
    "çıkış" olarak iki ayrı kayda düşmesi).

    Önceden bunu düzeltmenin TEK yolu kamerayı SİLİP RTSP adresini (ve varsa
    parolasını) elle yeniden yazarak baştan eklemekti -- ama panel, güvenlik
    gereği RTSP adresindeki parolayı istemciye asla düz metin göndermiyor
    (bkz. _kamera_guvenli_gorunum), yani kullanıcı parolayı unuttuysa/notlarında
    yoksa kamerayı siler silmez o bağlantıyı yeniden kuramaz hale gelebilirdi.
    Bu uç nokta yalnızca `yon` alanını değiştirdiği için kameranın `id`'si,
    RTSP adresi ve parolası hiç değişmeden kalır; yön değişikliği pipeline'a
    yansısın diye kamera etkinse yeniden başlatılır."""
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    with _kamera_dosya_kilit:
        kameralar = _kameralari_oku()
        kamera = next((k for k in kameralar if k["id"] == kamera_id), None)
        if not kamera:
            raise HTTPException(404, "Kamera bulunamadı")
        yon = veri.yon.strip().lower()
        if yon not in ("giris", "cikis"):
            raise HTTPException(400, "Yön 'giris' veya 'cikis' olmalıdır")
        kamera["yon"] = yon
        _kameralari_yaz(kameralar)
    if kamera.get("aktif", True):
        _pipeline_durdur(kamera_id)
        time.sleep(0.3)
        _pipeline_baslat(kamera)
    return _kamera_guvenli_gorunum(kamera)


@app.patch("/kameralar/{kamera_id}/ad")
def kamera_ad_degistir(kamera_id: str, veri: schemas.KameraAdGuncelle, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Var olan bir kameranın görünen adını ("ad") DEĞİŞTİRİR -- kameranın
    id'si, RTSP adresi ve parolası hiç değişmeden kalır (bkz.
    kamera_yon_degistir'in üstündeki AYNI "kamerayı silip yeniden eklemeye
    gerek yok" gerekçesi). Kullanıcı isteği (2026-09-25): "tanımlı kamera
    listesine tanımlı kameranın ismini değiştirmek için buton koyar mısın".

    ÖNEMLİ -- bu, cameras.json'da bir etiket değiştirmekten daha fazlasını
    gerektiriyor: kameranın "ad"ı, HER yeni geçiş kaydına `Kayit.kamera_id`
    olarak DAMGALANAN değerin ta kendisidir (bkz. _pipeline_baslat:
    `kamera_id=kamera["ad"]`, ve _kullanicinin_izinli_kamera_adlari'nin
    docstring'indeki "id vs ad" kök nedeni, 2026-09-21). Yalnızca
    cameras.json'ı güncelleyip veritabanına dokunmasaydık:
      - bu kameraya ait TÜM geçmiş kayıtlar eski adla "yetim" kalırdı (yeni
        kayıtlar yeni adla, eskiler eski adla -- aynı fiziksel kamera için
        raporlarda/filtrelerde SANKİ iki ayrı kameraymış gibi görünürdü),
      - kamera erişim kısıtlaması olan bir hesap ("Nizamiye Bazlı Kamera
        Erişimi", 2026-09-21), bu kameranın GEÇMİŞ kayıtlarını SESSİZCE
        göremez hale gelebilirdi -- çünkü kısıtlama id'den ada her seferinde
        GÜNCEL cameras.json ile çevriliyor (bkz. _kamera_id_den_ad_haritasi),
        ama eski kayıtlar hâlâ eski adı taşırdı.
    Bu yüzden ad değişikliği, aynı işlemde bu kameraya ait TÜM `Kayit`
    satırlarının `kamera_id` alanına da (eski ad -> yeni ad) yansıtılır.
    Alarm/denetim kaydı gibi noktasal, "o anki olayı" belgeleyen geçmiş
    metinler (ör. bir "kamera_arizasi" alarmının mesaj metni) BİLİNÇLİ
    OLARAK değiştirilmez -- onlar birer olay günlüğü, geriye dönük
    "düzeltilmesi" yanlış olurdu; yalnızca fiilen sorgulanan/filtrelenen
    `Kayit.kamera_id` alanı güncellenir.

    DÜZELTME (2026-09-25, sistem taraması): önceden ÖNCE veritabanı
    güncelleniyor, SONRA cameras.json yazılıyordu -- JSON yazımı (disk dolu,
    izin hatası, vb.) veritabanı commit'inden SONRA başarısız olursa, tüm
    geçmiş kayıtlar yeni adı taşırken cameras.json hâlâ eski adı listeler,
    ki bu da fonksiyonun yukarıdaki gerekçesinde tarif edilen TAM OLARAK aynı
    "sessiz veri kaybı" riskini geri getirirdi. Artık sıra tersine çevrildi
    (önce JSON, sonra DB) ve tüm "oku->değiştir->yaz" bloğu _kamera_dosya_kilit
    ile korunuyor; DB güncellemesi JSON yazımından SONRA başarısız olursa
    JSON en azından eski adına geri alınmaya çalışılır ki iki kaynak
    birbirinden sapmasın."""
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    with _kamera_dosya_kilit:
        kameralar = _kameralari_oku()
        kamera = next((k for k in kameralar if k["id"] == kamera_id), None)
        if not kamera:
            raise HTTPException(404, "Kamera bulunamadı")
        yeni_ad = veri.ad.strip()
        if not yeni_ad:
            raise HTTPException(400, "Kamera adı boş olamaz")
        eski_ad = kamera.get("ad") or kamera_id
        if yeni_ad == eski_ad:
            return _kamera_guvenli_gorunum(kamera)
        if any(
            k["id"] != kamera_id and (k.get("ad") or "").strip().casefold() == yeni_ad.casefold()
            for k in kameralar
        ):
            raise HTTPException(400, f"'{yeni_ad}' adında başka bir kamera zaten var")

        kamera["ad"] = yeni_ad
        _kameralari_yaz(kameralar)

        try:
            etkilenen_kayit = db.query(models.Kayit).filter(models.Kayit.kamera_id == eski_ad).update({"kamera_id": yeni_ad})
            db.commit()
        except Exception:
            db.rollback()
            kamera["ad"] = eski_ad
            try:
                _kameralari_yaz(kameralar)
            except OSError:
                logger.critical(
                    "kamera_ad_degistir: DB güncellemesi başarısız oldu VE cameras.json geri alınamadı "
                    "(kamera_id=%s, eski_ad=%r, yeni_ad=%r) -- iki kaynak birbirinden sapmış olabilir, elle kontrol gerekir",
                    kamera_id, eski_ad, yeni_ad,
                )
            raise HTTPException(500, "Kamera adı güncellenirken veritabanı hatası oluştu, değişiklik geri alındı")

        if kamera.get("aktif", True):
            _pipeline_durdur(kamera_id)
            time.sleep(0.3)
            _pipeline_baslat(kamera)

    # 2026-09-20'den beri kamera silmede olduğu gibi (bkz. kamera_sil), kamera
    # kimliğini etkileyen değişiklikler de denetim kaydına düşer -- bir
    # kameranın adının kimin tarafından, ne zaman, neden/neye değiştirildiği
    # sessiz kalmasın.
    _denetim_kaydet(
        db, kullanici.kullanici_adi, "kamera_ad_degistir",
        f"kamera_id={kamera_id}, eski_ad={eski_ad!r}, yeni_ad={yeni_ad!r}, etkilenen_kayit={etkilenen_kayit}",
    )
    return _kamera_guvenli_gorunum(kamera)


_ROI_POLIGON_MIN_NOKTA = 3
_ROI_POLIGON_MAX_NOKTA = 20


def _roi_polygon_gecerlilestir(noktalar: list) -> dict:
    """`schemas.KameraRoiNoktasi` listesini doğrulayıp ROI olarak diskte
    saklanacak `{"tip": "polygon", "noktalar": [{"x","y"}, ...]}` biçimine
    çevirir. En az 3 (bir çokgen için asgari), en fazla
    `_ROI_POLIGON_MAX_NOKTA` nokta kabul edilir -- üst sınır, kullanıcının
    yanlışlıkla binlerce nokta gönderip (örn. bir sürükleme olayını tıklama
    sanarak) diski/pipeline'ı şişirmesini engeller."""
    if len(noktalar) < _ROI_POLIGON_MIN_NOKTA:
        raise HTTPException(400, f"Serbest çizim (polygon) için en az {_ROI_POLIGON_MIN_NOKTA} nokta gerekir")
    if len(noktalar) > _ROI_POLIGON_MAX_NOKTA:
        raise HTTPException(400, f"Serbest çizim (polygon) için en fazla {_ROI_POLIGON_MAX_NOKTA} nokta desteklenir")
    temiz = []
    for n in noktalar:
        x, y = float(n.x), float(n.y)
        if not (0 <= x <= 100 and 0 <= y <= 100):
            raise HTTPException(400, "Polygon noktalarının x/y değerleri 0-100 arasında olmalı")
        temiz.append({"x": x, "y": y})
    return {"tip": "polygon", "noktalar": temiz}


@app.patch("/kameralar/{kamera_id}/roi")
def kamera_roi_guncelle(kamera_id: str, veri: schemas.KameraRoiGuncelle, kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Bir kameranın tespit alanını (ROI -- region of interest) yüzde (0-100,
    çözünürlükten bağımsız) cinsinden sınırlar veya bu sınırı kaldırır.

    NEDEN GEREKLİ (2026-09-17): sahada giriş ve çıkış kameralarının açıları
    birbirinin şeridini de görebiliyor -- bu durumda giriş yapan bir araç
    çıkış kamerasına da yansıyıp "çıkış" olarak, çıkış yapan araç da giriş
    kamerasına yansıyıp "giriş" olarak kaydediliyor; aynı plaka aynı dakikada
    hem giriş hem çıkış olarak iki ayrı kayda düşerek paneli kafa karıştırıcı
    hale getiriyor. Her kameraya SADECE kendi şeridine denk gelen bir ROI
    tanımlanarak, komşu şeritteki araçların merkez noktası bu dikdörtgenin
    dışında kaldığı için oy birikimine hiç girmemesi sağlanır (bkz.
    camera_reader.py::_kutu_roi_icinde_mi, `_kareyi_isle`).

    ROI, kameranın id'sini, RTSP adresini/parolasını DEĞİŞTİRMEZ -- yalnızca
    bu alanı günceller; değişikliğin pipeline'a yansıması için kamera etkinse
    yeniden başlatılır.

    2026-09-20: `veri.polygon` gönderilirse (en az 3 nokta), dikdörtgen
    yerine SERBEST ÇİZİM (polygon) ROI kaydedilir -- bkz.
    schemas.KameraRoiGuncelle'nin docstring'i ve camera_reader.py::
    _kutu_polygon_icinde_mi."""
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    with _kamera_dosya_kilit:
        kameralar = _kameralari_oku()
        kamera = next((k for k in kameralar if k["id"] == kamera_id), None)
        if not kamera:
            raise HTTPException(404, "Kamera bulunamadı")
        if veri.temizle:
            kamera.pop("roi", None)
        elif veri.polygon is not None:
            kamera["roi"] = _roi_polygon_gecerlilestir(veri.polygon)
        else:
            degerler = (veri.x1, veri.y1, veri.x2, veri.y2)
            if any(v is None for v in degerler):
                raise HTTPException(400, "x1, y1, x2, y2 değerlerinin hepsi gönderilmeli (veya polygon / temizle=true)")
            x1, y1, x2, y2 = (float(v) for v in degerler)
            if not all(0 <= v <= 100 for v in (x1, y1, x2, y2)):
                raise HTTPException(400, "Değerler 0-100 arasında olmalı")
            if x1 >= x2 or y1 >= y2:
                raise HTTPException(400, "x1 < x2 ve y1 < y2 olmalı")
            kamera["roi"] = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
        _kameralari_yaz(kameralar)
    if kamera.get("aktif", True):
        _pipeline_durdur(kamera_id)
        time.sleep(0.3)
        _pipeline_baslat(kamera)
    return _kamera_guvenli_gorunum(kamera)


# ------------------------------------------------------------------
# KAMERANIN KENDİ PLAKA OKUMASI (Dahua ANPR) -- 2026-09-25, kullanıcı:
# "Dahua ITC413 ... PTS'e aktaran bir bağlantı ekler misin, deneyelim".
# Bkz. backend/dahua_olay.py'nin docstring'i.
# ------------------------------------------------------------------

@app.patch("/kameralar/{kamera_id}/dahua")
def kamera_dahua_guncelle(kamera_id: str, veri: schemas.KameraDahuaGuncelle, db: Session = Depends(get_db),
                          kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Kameranın kendi ANPR okumasını PTS'e aktarmayı açar/kapatır. Kamera
    etkinse pipeline yeniden başlatılır (dinleyici onunla birlikte başlar)."""
    _rol_dogrula(kullanici, ROL_YONETICI)
    from backend.dahua_olay import olaylari_dogrula, rtsp_adresinden_baglanti
    with _kamera_dosya_kilit:
        kameralar = _kameralari_oku()
        kamera = next((k for k in kameralar if k["id"] == kamera_id), None)
        if not kamera:
            raise HTTPException(404, "Kamera bulunamadı")
        try:
            olaylar = olaylari_dogrula(veri.olaylar)
            if veri.aktif:
                # Açmadan ÖNCE RTSP adresinden kimlik bilgisi çıkarılabildiğini
                # doğrula -- aksi halde "açık" görünüp sessizce hiç bağlanmazdı.
                rtsp_adresinden_baglanti(kamera.get("rtsp_url", ""), veri.http_port)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        kamera["dahua_anpr"] = {"aktif": veri.aktif, "olaylar": olaylar, "http_port": veri.http_port}
        _kameralari_yaz(kameralar)
    _denetim_kaydet(
        db, kullanici.kullanici_adi, "kamera_dahua_anpr",
        f"kamera={kamera.get('ad')!r}, aktif={veri.aktif}, olaylar={olaylar}, http_port={veri.http_port}",
    )
    if kamera.get("aktif", True):
        _pipeline_durdur(kamera_id)
        time.sleep(0.3)
        _pipeline_baslat(kamera)
    return _kamera_guvenli_gorunum(kamera)


@app.post("/kameralar/{kamera_id}/dahua-test")
async def kamera_dahua_test(kamera_id: str, veri: schemas.KameraDahuaGuncelle,
                            kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Kameraya bir kez bağlanıp ~8 sn dinler ve sonucu (HTTP durumu, kalp
    atışı, gelen plaka olayları, HAM mesaj örnekleri) döner. Hiçbir ayarı
    değiştirmez, hiçbir kayıt oluşturmaz. `aktif` alanı yok sayılır."""
    _rol_dogrula(kullanici, ROL_YONETICI)
    kamera = next((k for k in _kameralari_oku() if k["id"] == kamera_id), None)
    if not kamera:
        raise HTTPException(404, "Kamera bulunamadı")
    from backend.dahua_olay import baglanti_testi
    return await asyncio.get_event_loop().run_in_executor(
        None, lambda: baglanti_testi(kamera.get("rtsp_url", ""), veri.olaylar, veri.http_port),
    )


@app.get("/kameralar/{kamera_id}/dahua-durum")
def kamera_dahua_durum(kamera_id: str, kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    kamera = next((k for k in _kameralari_oku() if k["id"] == kamera_id), None)
    if not kamera:
        raise HTTPException(404, "Kamera bulunamadı")
    ayar = kamera.get("dahua_anpr") or {"aktif": False}
    p = _aktif_pipelineler.get(kamera_id)
    durum = p.dahua_durumu() if p is not None and hasattr(p, "dahua_durumu") else None
    return {"ayar": ayar, "durum": durum}


@app.get("/kameralar/okuma-kalitesi")
def kamera_okuma_kalitesi(
    gun: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    """Kamera başına plaka okuma kalitesi (2026-09-25, kullanıcı: "kameranın
    en doğru ve hatasız kayıt alması için ..."). Son `gun` gündeki OTOMATİK
    (kamera kaynaklı, elle girilmemiş) kayıtlardan: tek karede okunan kayıt
    oranı, aynı geçişte farklı okunan (kararsız) kayıt oranı, kayıtlı plakaya
    göre düzeltilen kayıt oranı, ortalama doğrulama kare sayısı ve güven.
    Değerlendirme ve öneriler: backend/okuma_kalitesi.py. Sayılar veritabanında
    tek bir GROUP BY sorgusuyla hesaplanır. Kamera erişimi kısıtlı hesaplar
    yalnızca kendi kameralarını görür."""
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    from sqlalchemy import case
    from backend.okuma_kalitesi import kalite_degerlendir

    K = models.Kayit
    sinir = datetime.now() - timedelta(days=gun)
    sorgu = (
        db.query(
            K.kamera_id,
            func.count(K.id),
            func.sum(case((K.dogrulama_kare_sayisi.isnot(None), 1), else_=0)),
            func.sum(case((K.dogrulama_kare_sayisi <= 1, 1), else_=0)),
            func.sum(case((K.farkli_okuma_sayisi > 1, 1), else_=0)),
            func.sum(case((K.ham_plaka_metni.isnot(None), 1), else_=0)),
            func.avg(K.dogrulama_kare_sayisi),
            func.avg(K.guven_skoru),
        )
        .filter(K.tarih_saat >= sinir, or_(K.manuel_giris == False, K.manuel_giris.is_(None)))  # noqa: E712
    )
    izinli_adlar = _kullanicinin_izinli_kamera_adlari(kullanici)
    if izinli_adlar is not None:
        sorgu = sorgu.filter(K.kamera_id.in_(izinli_adlar))
    satirlar = {r[0]: r for r in sorgu.group_by(K.kamera_id).all()}

    # Tanımlı ama bu dönemde HİÇ kayıt üretmemiş kameralar da listelensin --
    # "hiç okumuyor" en kötü durumdur ve GROUP BY sonucunda görünmez.
    izinli_idler = _kullanicinin_izinli_kameralari(kullanici)
    tanimli = [
        k for k in _kameralari_oku()
        if (izinli_idler is None or k.get("id") in izinli_idler)
    ]
    sonuc = []
    gorulen = set()
    for k in tanimli:
        ad = k.get("ad")
        gorulen.add(ad)
        r = satirlar.get(ad)
        degerlendirme = kalite_degerlendir(
            int(r[1]) if r else 0, int(r[2] or 0) if r else 0, int(r[3] or 0) if r else 0,
            int(r[4] or 0) if r else 0, int(r[5] or 0) if r else 0,
            float(r[6]) if r and r[6] is not None else None,
            float(r[7]) if r and r[7] is not None else None,
        )
        sonuc.append({"kamera": ad, "yon": k.get("yon"), "aktif": k.get("aktif", True), "tanimli": True, **degerlendirme})
    # Artık tanımlı olmayan (silinmiş/yeniden adlandırılmış) kamera adlarıyla
    # gelen kayıtlar (ör. klasör izleyici, harici sistem) da görünür kalsın.
    for ad, r in satirlar.items():
        if ad in gorulen:
            continue
        degerlendirme = kalite_degerlendir(
            int(r[1]), int(r[2] or 0), int(r[3] or 0), int(r[4] or 0), int(r[5] or 0),
            float(r[6]) if r[6] is not None else None, float(r[7]) if r[7] is not None else None,
        )
        sonuc.append({"kamera": ad, "yon": None, "aktif": None, "tanimli": False, **degerlendirme})
    sira = {"zayif": 0, "dikkat": 1, "kayit_yok": 2, "yetersiz_veri": 3, "iyi": 4}
    sonuc.sort(key=lambda s: (sira.get(s["durum"], 9), str(s["kamera"])))
    return {"gun": gun, "kameralar": sonuc}


@app.get("/kameralar/dahua-karsilastirma")
def kamera_dahua_karsilastirma(
    saat: int = Query(12, ge=1, le=168),
    db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    """Kamera bazında "Dahua ANPR katkısı" karşılaştırması (2026-09-25
    kullanıcı isteği: "Bu akşamki geçişleri takip etmek için yeni yaptığım
    dahua eklemesiyle hangisi daha verimli çalışmış tespit edebilmem için
    bir grafik"). `/kameralar/okuma-kalitesi` ile AYNI GROUP BY sorgu
    şeklini kullanır (bkz. yukarıdaki `kamera_okuma_kalitesi`) ama iki
    farkla:

    1) Varsayılan pencere GÜN değil SAAT'tir (varsayılan 12 -- "bu akşam"),
       çünkü kullanıcı belirli bir vardiya/gece dilimini karşılaştırmak
       istiyor, genel bir kalite trendini değil.
    2) Her kamera için ayrıca `harici_katkili_kayit`/`harici_katki_orani`
       (kaç/% kaydın KAZANAN metninin kameranın kendi Dahua ANPR okumasıyla
       desteklendiği -- bkz. models.Kayit.harici_katkili'nin docstring'i)
       ve `dahua_aktif` (bkz. cameras.json'daki dahua_anpr.aktif) döner ki
       panel Dahua'sı açık kameralarla kapalı kameraları aynı grafikte yan
       yana gösterebilsin. `harici_katkili` sütunu YALNIZCA bu değişiklikten
       SONRA oluşan kayıtlarda doludur -- eski kayıtlarda None'dır ve
       `harici_katki_orani` hesabında (toplam PAYDA olsa da) pay olarak hiç
       sayılmaz; yani bu oran, "Dahua kaç kaydı GERÇEKTEN etkiledi" sorusunun
       eldeki VERİYLE ölçülebilen alt sınırıdır, üst sınırı değil."""
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    from sqlalchemy import case
    from backend.okuma_kalitesi import kalite_degerlendir

    K = models.Kayit
    sinir = datetime.now() - timedelta(hours=saat)
    sorgu = (
        db.query(
            K.kamera_id,
            func.count(K.id),
            func.sum(case((K.dogrulama_kare_sayisi.isnot(None), 1), else_=0)),
            func.sum(case((K.dogrulama_kare_sayisi <= 1, 1), else_=0)),
            func.sum(case((K.farkli_okuma_sayisi > 1, 1), else_=0)),
            func.sum(case((K.ham_plaka_metni.isnot(None), 1), else_=0)),
            func.avg(K.dogrulama_kare_sayisi),
            func.avg(K.guven_skoru),
            func.sum(case((K.harici_katkili == True, 1), else_=0)),  # noqa: E712
        )
        .filter(K.tarih_saat >= sinir, or_(K.manuel_giris == False, K.manuel_giris.is_(None)))  # noqa: E712
    )
    izinli_adlar = _kullanicinin_izinli_kamera_adlari(kullanici)
    if izinli_adlar is not None:
        sorgu = sorgu.filter(K.kamera_id.in_(izinli_adlar))
    satirlar = {r[0]: r for r in sorgu.group_by(K.kamera_id).all()}

    # okuma-kalitesi ile AYNI GEREKÇE: tanımlı ama bu pencerede hiç kayıt
    # üretmemiş kameralar da (özellikle "Dahua'yı yeni açtım ama hiç geçiş
    # olmadı" durumunu görünür kılmak için) listelensin.
    izinli_idler = _kullanicinin_izinli_kameralari(kullanici)
    tanimli = [
        k for k in _kameralari_oku()
        if (izinli_idler is None or k.get("id") in izinli_idler)
    ]
    sonuc = []
    gorulen = set()
    for k in tanimli:
        ad = k.get("ad")
        gorulen.add(ad)
        r = satirlar.get(ad)
        toplam = int(r[1]) if r else 0
        degerlendirme = kalite_degerlendir(
            toplam, int(r[2] or 0) if r else 0, int(r[3] or 0) if r else 0,
            int(r[4] or 0) if r else 0, int(r[5] or 0) if r else 0,
            float(r[6]) if r and r[6] is not None else None,
            float(r[7]) if r and r[7] is not None else None,
        )
        harici = int(r[8] or 0) if r else 0
        degerlendirme["harici_katkili_kayit"] = harici
        degerlendirme["harici_katki_orani"] = round(harici / toplam, 3) if toplam else None
        dahua_ayari = k.get("dahua_anpr") or {}
        sonuc.append({
            "kamera": ad,
            "yon": k.get("yon"),
            "aktif": k.get("aktif", True),
            "tanimli": True,
            "dahua_aktif": bool(dahua_ayari.get("aktif")),
            **degerlendirme,
        })
    for ad, r in satirlar.items():
        if ad in gorulen:
            continue
        toplam = int(r[1])
        degerlendirme = kalite_degerlendir(
            toplam, int(r[2] or 0), int(r[3] or 0), int(r[4] or 0), int(r[5] or 0),
            float(r[6]) if r[6] is not None else None, float(r[7]) if r[7] is not None else None,
        )
        harici = int(r[8] or 0)
        degerlendirme["harici_katkili_kayit"] = harici
        degerlendirme["harici_katki_orani"] = round(harici / toplam, 3) if toplam else None
        sonuc.append({
            "kamera": ad, "yon": None, "aktif": None, "tanimli": False,
            "dahua_aktif": False, **degerlendirme,
        })
    # Dahua açık kameralar önce -- kullanıcının asıl merak ettiği karşılaştırma
    # bu ikisi arasında olduğu için grafikte/tabloda hemen göze çarpsınlar.
    sonuc.sort(key=lambda s: (not s["dahua_aktif"], str(s["kamera"])))
    return {"saat": saat, "kameralar": sonuc}


@app.get("/kameralar/{kamera_id}/goruntu")
async def kamera_goruntu_al(kamera_id: str, kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Kameradan anlık JPEG kare alır. Pipeline çalışıyorsa cached (temiz,
    işaretlenmemiş -- bkz. camera_reader.py::_kareyi_isle'deki 2026-09-23 notu)
    frame döner (sıfır gecikme)."""
    if not _kamera_erisimi_var_mi(kullanici, kamera_id):
        raise HTTPException(403, "Bu kameraya erişim yetkiniz yok")
    kamera = next((k for k in _kameralari_oku() if k["id"] == kamera_id), None)
    if not kamera:
        raise HTTPException(404, "Kamera bulunamadı")

    # Pipeline çalışıyorsa son (temiz) frame'i doğrudan dön (hızlı yol)
    pipeline = _aktif_pipelineler.get(kamera_id)
    if pipeline and pipeline.calisiyor:
        kare = pipeline.son_goruntu_al()
        if kare:
            return Response(content=kare, media_type="image/jpeg")

    # Pipeline yoksa yeni bağlantı aç (yavaş yol)
    try:
        import cv2
    except ImportError:
        raise HTTPException(503, "opencv-python kurulu değil")

    def _kare_al():
        cap = cv2.VideoCapture(kamera["rtsp_url"], cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return None
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buf.tobytes()

    import asyncio
    kare = await asyncio.get_event_loop().run_in_executor(None, _kare_al)
    if kare is None:
        raise HTTPException(503, "Kameradan görüntü alınamadı")
    return Response(content=kare, media_type="image/jpeg")


@app.get("/kameralar/{kamera_id}/akis")
async def kamera_akis(kamera_id: str, request: Request, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """Kameradan GERÇEK ZAMANLI MJPEG akışı (multipart/x-mixed-replace).

    Panel eskiden bu kareyi 3 saniyede bir `fetch` ile "anlık görüntü" (snapshot)
    olarak çekiyordu; bu, doğası gereği kesikli/adım adım görünüyordu. Bu uç nokta
    yerine tek bir bağlantı üzerinden pipeline'ın ürettiği HER yeni kareyi
    (tipik olarak ~4 FPS'e kadar) anında iletir.

    Tarayıcının `<img>` etiketi özel başlık (Authorization) taşıyamadığı için
    (SSE'deki ile aynı kısıtlama, bkz. /olaylar/sse), istemci tarafında token'lı
    `fetch()` + elle multipart ayrıştırma ile tüketilir
    (frontend/app.js: `_kameraAkisiBaslat`)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Bearer token gerekli")
    kullanici_id = _token_coz(authorization[7:].strip())

    kamera = next((k for k in _kameralari_oku() if k["id"] == kamera_id), None)
    if not kamera:
        raise HTTPException(404, "Kamera bulunamadı")

    # Kamera erişim kısıtlaması (2026-09-21) -- bu uç nokta yalnızca token'ı
    # (kullanıcı ID'sini) doğruluyordu, hesabın kısıtlamasına hiç BAKMIYORDU;
    # bkz. _kamera_erisimi_var_mi.
    baglanan = db.query(models.Kullanici).filter(models.Kullanici.id == kullanici_id).first()
    if not baglanan or not _kamera_erisimi_var_mi(baglanan, kamera_id):
        raise HTTPException(403, "Bu kameraya erişim yetkiniz yok")

    SINIR = b"ptsframe"

    async def _akis():
        son_kare_kimligi = None
        while True:
            if await request.is_disconnected():
                break
            pipeline = _aktif_pipelineler.get(kamera_id)
            if not pipeline or not pipeline.calisiyor:
                await asyncio.sleep(0.5)
                continue
            kare = pipeline.son_goruntu_al()
            if kare is None or id(kare) == son_kare_kimligi:
                await asyncio.sleep(0.08)  # ~12/sn kontrol — yeni kare geldiği an hemen yakalanır
                continue
            son_kare_kimligi = id(kare)
            yield (
                b"--" + SINIR + b"\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(kare)).encode("ascii") + b"\r\n\r\n"
                + kare + b"\r\n"
            )

    return StreamingResponse(
        _akis(),
        media_type=f"multipart/x-mixed-replace; boundary={SINIR.decode()}",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/kameralar/{kamera_id}/son-plaka")
def kamera_son_plaka(kamera_id: str, kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Pipeline'ın son tespit ettiği plaka(ları) döner (canlı overlay için)."""
    if not _kamera_erisimi_var_mi(kullanici, kamera_id):
        raise HTTPException(403, "Bu kameraya erişim yetkiniz yok")
    pipeline = _aktif_pipelineler.get(kamera_id)
    if not pipeline or not pipeline.calisiyor:
        return {"tespitler": []}
    return {"tespitler": pipeline.son_tespitler_al()}


_GECERLI_KAMERA_SEMALARI = ("rtsp", "rtsps", "http", "https")


@app.post("/kameralar")
def kamera_ekle(kamera: dict = Body(...), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    if not _lisans_aktif_mi():
        raise HTTPException(403, "Kamera eklemek için aktif lisans gereklidir")
    gerekli_alanlar = ("ad", "rtsp_url", "yon")
    if any(not str(kamera.get(alan, "")).strip() for alan in gerekli_alanlar):
        raise HTTPException(400, "Kamera adı, RTSP adresi ve yön zorunludur")

    rtsp_url = str(kamera["rtsp_url"]).strip()
    sema = urlsplit(rtsp_url).scheme.lower()
    if sema not in _GECERLI_KAMERA_SEMALARI:
        raise HTTPException(
            400,
            f"Desteklenmeyen adres türü ('{sema or '?'}'). Adres şunlardan biriyle "
            f"başlamalı: {', '.join(s + '://' for s in _GECERLI_KAMERA_SEMALARI)}",
        )

    yon = str(kamera["yon"]).strip().lower()
    if yon not in ("giris", "cikis"):
        raise HTTPException(400, "Yön 'giris' veya 'cikis' olmalıdır")

    # Opsiyonel tespit alanı (ROI) -- eklerken de belirtilebilir, bkz.
    # PATCH /kameralar/{id}/roi'nin docstring'i (aynı doğrulama kuralları).
    roi = kamera.get("roi")
    roi_temiz = None
    if roi:
        try:
            x1, y1, x2, y2 = float(roi["x1"]), float(roi["y1"]), float(roi["x2"]), float(roi["y2"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(400, "roi alanı x1, y1, x2, y2 (0-100) içermeli")
        if not all(0 <= v <= 100 for v in (x1, y1, x2, y2)) or x1 >= x2 or y1 >= y2:
            raise HTTPException(400, "roi değerleri geçersiz (0-100 arası ve x1<x2, y1<y2 olmalı)")
        roi_temiz = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}

    yeni_kamera = {
        "id": str(uuid.uuid4()),
        "ad": str(kamera["ad"]).strip(),
        "rtsp_url": rtsp_url,
        "yon": yon,
        "aktif": True,
    }
    if roi_temiz:
        yeni_kamera["roi"] = roi_temiz

    # DÜZELTME (2026-09-25): lisans kamera limiti kontrolü ("len(kameralar) >=
    # kamera_limiti") ile listeye ekleyip yazma işlemi önceden AYNI kilit
    # altında değildi -- iki eşzamanlı POST /kameralar isteği, limite tam
    # sınırdayken ikisi de kontrolü geçip toplam kamera sayısının lisans
    # limitini aşmasına yol açabiliyordu. Artık kontrol de, ekleme de tek bir
    # kilit altında, aynı okumaya dayanarak yapılıyor.
    with _kamera_dosya_kilit:
        lisans = _lisans_durumunu_oku()
        kameralar = _kameralari_oku()
        if len(kameralar) >= lisans["kamera_limiti"]:
            raise HTTPException(403, "Aktif lisans kamera limitine ulaşıldı")
        kameralar.append(yeni_kamera)
        _kameralari_yaz(kameralar)
    _pipeline_baslat(yeni_kamera)
    return _kamera_guvenli_gorunum(yeni_kamera)


@app.delete("/kameralar/{kamera_id}")
def kamera_sil(kamera_id: str, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    with _kamera_dosya_kilit:
        kameralar = _kameralari_oku()
        silinen = next((kamera for kamera in kameralar if kamera["id"] == kamera_id), None)
        yeni_kameralar = [kamera for kamera in kameralar if kamera["id"] != kamera_id]
        if len(yeni_kameralar) == len(kameralar):
            raise HTTPException(404, "Kamera bulunamadı")
        _kameralari_yaz(yeni_kameralar)
    _pipeline_durdur(kamera_id)
    # 2026-09-20: hangi yöneticinin/operatörün hangi kamerayı kaldırdığı
    # önceden hiçbir yere loglanmıyordu -- bir güvenlik kamerasının
    # kaldırılması (kazayla ya da kötü niyetle) sessiz kalıyordu.
    _denetim_kaydet(
        db, kullanici.kullanici_adi, "kamera_sil",
        f"kamera_id={kamera_id}, ad={(silinen or {}).get('ad', '?')}",
    )
    return {"mesaj": "Kamera silindi"}


# ==================================================================
# SİTE VE NOKTA YÖNETİMİ
# ==================================================================

@app.post("/siteler", response_model=schemas.SiteCevap)
def site_ekle(site: schemas.SiteOlustur, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI)
    if db.query(models.Site).filter(models.Site.ad == site.ad.strip()).first():
        raise HTTPException(409, "Bu site zaten kayıtlı")
    yeni_site = models.Site(ad=site.ad.strip(), aciklama=site.aciklama)
    db.add(yeni_site)
    db.commit()
    db.refresh(yeni_site)
    return yeni_site


@app.get("/siteler", response_model=List[schemas.SiteCevap])
def siteleri_listele(db: Session = Depends(get_db), _: models.Kullanici = Depends(_personel_girisi_gerekli)):
    return db.query(models.Site).order_by(models.Site.ad).all()


@app.delete("/siteler/{site_id}")
def site_sil(site_id: int, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI)
    site = db.query(models.Site).filter(models.Site.id == site_id).first()
    if not site:
        raise HTTPException(404, "Site bulunamadı")
    db.delete(site)
    db.commit()
    return {"mesaj": "Site silindi"}


@app.post("/noktalar", response_model=schemas.NoktaCevap)
def nokta_ekle(nokta: schemas.NoktaOlustur, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI)
    if not db.query(models.Site).filter(models.Site.id == nokta.site_id).first():
        raise HTTPException(404, "Bağlı site bulunamadı")
    if nokta.bariyer_id is not None and not db.query(models.BariyerAyarlari).filter(models.BariyerAyarlari.id == nokta.bariyer_id).first():
        raise HTTPException(404, "Bağlı bariyer bulunamadı")
    if nokta.kamera_id and not any(k["id"] == nokta.kamera_id for k in _kameralari_oku()):
        raise HTTPException(404, "Bağlı kamera bulunamadı")
    yeni_nokta = models.Nokta(**nokta.model_dump())
    db.add(yeni_nokta)
    db.commit()
    db.refresh(yeni_nokta)
    return yeni_nokta


@app.get("/noktalar", response_model=List[schemas.NoktaCevap])
def noktalari_listele(site_id: Optional[int] = None, db: Session = Depends(get_db), _: models.Kullanici = Depends(_personel_girisi_gerekli)):
    sorgu = db.query(models.Nokta)
    if site_id is not None:
        sorgu = sorgu.filter(models.Nokta.site_id == site_id)
    noktalar = sorgu.order_by(models.Nokta.ad).all()
    # bkz. schemas.NoktaCevap.kamera_adi'nin docstring'i -- Nokta.kamera_id
    # "id" bazlıdır, Kayit.kamera_id "ad" bazlıdır; istemcinin bu ikisini
    # karıştırmadan eşleştirebilmesi için "ad" karşılığı burada eklenir.
    id_den_ad = _kamera_id_den_ad_haritasi()
    for nokta in noktalar:
        nokta.kamera_adi = id_den_ad.get(nokta.kamera_id) if nokta.kamera_id else None
    return noktalar


@app.delete("/noktalar/{nokta_id}")
def nokta_sil(nokta_id: int, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI)
    nokta = db.query(models.Nokta).filter(models.Nokta.id == nokta_id).first()
    if not nokta:
        raise HTTPException(404, "Nokta bulunamadı")
    db.delete(nokta)
    db.commit()
    return {"mesaj": "Nokta silindi"}


# ==================================================================
# KİŞİLER (Abone / Personel / Ziyaretçi)
# ==================================================================

@app.post("/kisiler", response_model=schemas.KisiCevap)
def kisi_ekle(kisi: schemas.KisiOlustur, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    yeni_kisi = models.Kisi(**kisi.model_dump())
    db.add(yeni_kisi)
    db.commit()
    db.refresh(yeni_kisi)
    # 2026-09-18: bu plakaya ait, kayıt ANINDA henüz kişi bulunamadığı için
    # "yetkisiz" kalmış GEÇMİŞ tespitler varsa, bu kişi eklendiği anda
    # otomatik olarak düzeltilir (bkz. _gecmis_kayitlari_kisiye_bagla'nın
    # docstring'i). Bir hata olursa (beklenmez) ana kişi ekleme işlemini
    # BOZMAMALI -- yalnızca loglanır.
    try:
        _gecmis_kayitlari_kisiye_bagla(db, yeni_kisi, kullanici.kullanici_adi)
    except Exception:
        logger.exception("Kişi eklendikten sonra geçmiş kayıtları bağlama başarısız oldu (kişi id=%s)", yeni_kisi.id)
    # TUTARLILIK DÜZELTMESİ (2026-09-22 kod incelemesi): kayit_duzenle'deki
    # AYNI kök nedenle (bkz. o fonksiyonun sonundaki not) bu uç nokta da
    # response_model=KisiCevap'ın ilk_gecis/son_gecis/son_yetki_durumu/
    # son_not_metni/son_not_ekleyen alanlarını hiç doldurmadan çıplak ORM
    # nesnesini dönüyordu -- yalnızca GET /kisiler (liste) bunları
    # _kisilerin_gecis_ozetini_ekle ile dolduruyordu. Yukarıdaki
    # _gecmis_kayitlari_kisiye_bagla tam da bu kişiye YENİ geçmiş kayıtlar
    # bağlamış olabileceğinden, bu özet şimdi doldurulmazsa panelin ilk
    # gösterdiği veri (bir sonraki tam liste yenilemesine kadar) yanlış/eksik
    # görünürdü.
    _kisilerin_gecis_ozetini_ekle(db, [yeni_kisi])
    return yeni_kisi


def _kisilerin_gecis_ozetini_ekle(db: Session, kisiler: List[models.Kisi]) -> None:
    """Kişiler ekranındaki listeye (frontend/app.js::kisileriYukle) eklenen
    "İlk Geçiş" / "Son Geçiş" / "Son Not" sütunları ve plaka linkinin
    yetkisiz/kırmızı renklendirmesi için gereken özeti hesaplayıp `kisiler`
    listesindeki ORM nesnelerinin üzerine GEÇİCİ (Kisi tablosunda karşılığı
    olmayan, DB'ye asla yazılmayan) attribute olarak ekler --
    schemas.KisiCevap bunları `from_attributes=True` sayesinde otomatik okur.

    Kayit.kisi_id, bir kişinin TÜM plakalarıyla (ana plaka_no + ek_plakalar)
    eşleşen geçişleri tespit anında zaten doğrudan bağladığı için (bkz.
    _yetki_kontrol_et'teki eşleştirme) burada plaka string'i tekrar
    eşleştirilmiyor, doğrudan bu foreign key üzerinden gruplanıyor -- yani
    bu özet, kişinin BİRDEN FAZLA plakası varsa hepsini kapsar.

    2026-09-22 kullanıcı isteği: "aracın sisteme kayıtlara ilk giriş tarihi
    eklensin. son güncel geçiş tarihi ve saati eklensin. Not ekleyen
    Personel veya vardiyanın da bilgisi yazılsın ... yetkisiz araç
    olduğunda kırmızı ile belirtilsin".
    """
    for k in kisiler:
        k.ilk_gecis = None
        k.son_gecis = None
        k.son_yetki_durumu = None
        k.son_not_metni = None
        k.son_not_ekleyen = None
    kisi_idler = [k.id for k in kisiler]
    if not kisi_idler:
        return

    ilk_gecis_map = dict(
        db.query(models.Kayit.kisi_id, func.min(models.Kayit.tarih_saat))
        .filter(models.Kayit.kisi_id.in_(kisi_idler))
        .group_by(models.Kayit.kisi_id)
        .all()
    )

    son_tarih_alt_sorgu = (
        db.query(
            models.Kayit.kisi_id.label("kisi_id"),
            func.max(models.Kayit.tarih_saat).label("son_tarih"),
        )
        .filter(models.Kayit.kisi_id.in_(kisi_idler))
        .group_by(models.Kayit.kisi_id)
        .subquery()
    )
    son_kayitlar = (
        db.query(models.Kayit)
        .join(
            son_tarih_alt_sorgu,
            and_(
                models.Kayit.kisi_id == son_tarih_alt_sorgu.c.kisi_id,
                models.Kayit.tarih_saat == son_tarih_alt_sorgu.c.son_tarih,
            ),
        )
        .all()
    )
    # Aynı kişi + aynı ANDA (nadiren, örn. saniye çözünürlüğü nedeniyle) birden
    # fazla kayıt eşleşirse, en yüksek id'ye (en son EKLENEN) sahip olanı
    # gerçek "son kayıt" say.
    son_kayit_map: dict = {}
    for kayit in son_kayitlar:
        mevcut = son_kayit_map.get(kayit.kisi_id)
        if mevcut is None or kayit.id > mevcut.id:
            son_kayit_map[kayit.kisi_id] = kayit

    for k in kisiler:
        k.ilk_gecis = ilk_gecis_map.get(k.id)
        son_kayit = son_kayit_map.get(k.id)
        if son_kayit:
            k.son_gecis = son_kayit.tarih_saat
            k.son_yetki_durumu = son_kayit.yetki_durumu
            k.son_not_metni = son_kayit.not_metni
            k.son_not_ekleyen = son_kayit.duzenleyen


@app.get("/kisiler", response_model=List[schemas.KisiCevap])
def kisileri_listele(
    tip: Optional[str] = None,
    aktif: Optional[bool] = None,
    arama: Optional[str] = None,
    db: Session = Depends(get_db),
    _: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    sorgu = db.query(models.Kisi)
    if tip:
        sorgu = sorgu.filter(models.Kisi.tip == tip)
    if aktif is not None:
        sorgu = sorgu.filter(models.Kisi.aktif == aktif)
    if arama:
        arama_terimi = f"%{arama}%"
        sorgu = sorgu.filter(
            (models.Kisi.ad_soyad.ilike(arama_terimi))
            | (models.Kisi.plaka_no.ilike(arama_terimi))
        )
    kisiler = sorgu.order_by(desc(models.Kisi.olusturma_tarihi)).all()
    _kisilerin_gecis_ozetini_ekle(db, kisiler)
    return kisiler


@app.get("/kisiler/{kisi_id}", response_model=schemas.KisiCevap)
def kisi_getir(kisi_id: int, db: Session = Depends(get_db), _: models.Kullanici = Depends(_personel_girisi_gerekli)):
    kisi = db.query(models.Kisi).filter(models.Kisi.id == kisi_id).first()
    if not kisi:
        raise HTTPException(404, "Kişi bulunamadı")
    _kisilerin_gecis_ozetini_ekle(db, [kisi])
    return kisi


@app.put("/kisiler/{kisi_id}", response_model=schemas.KisiCevap)
def kisi_guncelle(kisi_id: int, degisiklik: schemas.KisiGuncelle, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    kisi = db.query(models.Kisi).filter(models.Kisi.id == kisi_id).first()
    if not kisi:
        raise HTTPException(404, "Kişi bulunamadı")
    for alan, deger in degisiklik.model_dump(exclude_unset=True).items():
        setattr(kisi, alan, deger)
    db.commit()
    db.refresh(kisi)
    # 2026-09-18: plaka veya tip değişmiş olabilir (ör. abone->personel) --
    # bkz. kisi_ekle'deki aynı çağrının notu.
    try:
        _gecmis_kayitlari_kisiye_bagla(db, kisi, kullanici.kullanici_adi)
    except Exception:
        logger.exception("Kişi güncellendikten sonra geçmiş kayıtları bağlama başarısız oldu (kişi id=%s)", kisi.id)
    # TUTARLILIK DÜZELTMESİ (2026-09-22): bkz. kisi_ekle'nin sonundaki AYNI
    # notun gerekçesi.
    _kisilerin_gecis_ozetini_ekle(db, [kisi])
    return kisi


@app.delete("/kisiler/{kisi_id}")
def kisi_sil(kisi_id: int, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    kisi = db.query(models.Kisi).filter(models.Kisi.id == kisi_id).first()
    if not kisi:
        raise HTTPException(404, "Kişi bulunamadı")
    db.query(models.Kayit).filter(models.Kayit.kisi_id == kisi_id).update({"kisi_id": None})
    # Bu kişiye bağlı bir "sakin" öz-hizmet hesabı varsa (bkz.
    # models.Kullanici.kisi_id), kişi silinince sarkan bir referans kalmasın
    # diye bağlantı temizlenir -- hesabın kendisi silinmez, yalnızca artık
    # hiçbir kişiye bağlı olmadığı için /sakin/... uçları 400 dönene kadar
    # devre dışı kalır (bkz. main.py::_sakin_kisisini_al).
    db.query(models.Kullanici).filter(models.Kullanici.kisi_id == kisi_id).update({"kisi_id": None})
    db.delete(kisi)
    db.commit()
    return {"mesaj": "Kişi silindi"}


@app.get("/kisiler/{kisi_id}/plakalar", response_model=List[schemas.KisiPlakaCevap])
def kisi_plakalarini_listele(kisi_id: int, db: Session = Depends(get_db), _: models.Kullanici = Depends(_personel_girisi_gerekli)):
    if not db.query(models.Kisi).filter(models.Kisi.id == kisi_id).first():
        raise HTTPException(404, "Kişi bulunamadı")
    return db.query(models.KisiPlaka).filter(models.KisiPlaka.kisi_id == kisi_id).all()


@app.post("/kisiler/{kisi_id}/plakalar", response_model=schemas.KisiPlakaCevap)
def kisi_plaka_ekle(kisi_id: int, istek: schemas.KisiPlakaOlustur, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    if not db.query(models.Kisi).filter(models.Kisi.id == kisi_id).first():
        raise HTTPException(404, "Kişi bulunamadı")
    yeni = models.KisiPlaka(kisi_id=kisi_id, plaka_no=istek.plaka_no, aciklama=istek.aciklama)
    db.add(yeni)
    db.commit()
    db.refresh(yeni)
    # 2026-09-18: yeni bağlanan bu ek plakaya ait geçmiş "yetkisiz" tespitler
    # varsa düzeltilir (bkz. kisi_ekle'deki aynı çağrının notu).
    try:
        kisi = db.query(models.Kisi).filter(models.Kisi.id == kisi_id).first()
        if kisi:
            _gecmis_kayitlari_kisiye_bagla(db, kisi, kullanici.kullanici_adi)
    except Exception:
        logger.exception("Ek plaka eklendikten sonra geçmiş kayıtları bağlama başarısız oldu (kişi id=%s)", kisi_id)
    return yeni


@app.delete("/kisiler/{kisi_id}/plakalar/{plaka_id}")
def kisi_plaka_sil(kisi_id: int, plaka_id: int, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    kayit = db.query(models.KisiPlaka).filter(models.KisiPlaka.id == plaka_id, models.KisiPlaka.kisi_id == kisi_id).first()
    if not kayit:
        raise HTTPException(404, "Plaka kaydı bulunamadı")
    db.delete(kayit)
    db.commit()
    return {"mesaj": "Plaka silindi"}


@app.post("/kisiler/{kisi_id}/gecmis-kayitlari-guncelle")
def kisi_gecmis_kayitlarini_guncelle(
    kisi_id: int, db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    """Bu kişinin plakasına (+ ek plakalarına) ait, kayıt ANINDA henüz bu
    kişi tanımlı olmadığı için "yetkisiz" kalmış GEÇMİŞ tespitleri elle
    yeniden değerlendirir (bkz. _gecmis_kayitlari_kisiye_bagla'nın
    docstring'i, 2026-09-18). Bu aslında kisi_ekle/kisi_guncelle/
    kisi_plaka_ekle her çağrıldığında ZATEN otomatik çalışır -- bu uç nokta,
    bu özellik eklenmeden ÖNCE kaydedilmiş kişiler için panelden elle
    tetiklenebilsin diye (ve kullanıcıya kaç kaydın güncellendiğini
    gösterebilmek için) ayrıca sunulur."""
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    kisi = db.query(models.Kisi).filter(models.Kisi.id == kisi_id).first()
    if not kisi:
        raise HTTPException(404, "Kişi bulunamadı")
    guncellenen = _gecmis_kayitlari_kisiye_bagla(db, kisi, kullanici.kullanici_adi)
    return {"guncellenen_kayit_sayisi": guncellenen}


# ==================================================================
# KARA LİSTESİ
# ==================================================================

@app.get("/kara-listesi", response_model=List[schemas.KaraListesiCevap])
def kara_listesini_getir(db: Session = Depends(get_db), _: models.Kullanici = Depends(_personel_girisi_gerekli)):
    return db.query(models.KaraListesi).order_by(desc(models.KaraListesi.olusturma_tarihi)).all()


@app.post("/kara-listesi", response_model=schemas.KaraListesiCevap)
def kara_listeye_ekle(istek: schemas.KaraListesiOlustur, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    mevcut = db.query(models.KaraListesi).filter(models.KaraListesi.plaka_no == istek.plaka_no).first()
    if mevcut:
        mevcut.aktif = True
        mevcut.sebep = istek.sebep
        mevcut.ekleyen = kullanici.kullanici_adi
        db.commit()
        db.refresh(mevcut)
        return mevcut
    yeni = models.KaraListesi(plaka_no=istek.plaka_no, sebep=istek.sebep, ekleyen=kullanici.kullanici_adi)
    db.add(yeni)
    db.commit()
    db.refresh(yeni)
    logger.warning("Kara listeye eklendi: %s (ekleyen: %s)", istek.plaka_no, kullanici.kullanici_adi)
    return yeni


@app.delete("/kara-listesi/{kayit_id}")
def kara_listeden_cikar(kayit_id: int, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    kayit = db.query(models.KaraListesi).filter(models.KaraListesi.id == kayit_id).first()
    if not kayit:
        raise HTTPException(404, "Kayıt bulunamadı")
    db.delete(kayit)
    db.commit()
    return {"mesaj": "Kara listeden çıkarıldı"}


def _plaka_normalize(plaka: str) -> str:
    return plaka.upper().replace(" ", "").strip()


def _plaka_normalize_sql(kolon):
    """`_plaka_normalize()`'ın SQL karşılığı: DB'de saklanan plaka_no
    değerinin (BOŞLUKLAR KORUNARAK saklanır, bkz. schemas.py::plaka_normalize)
    boşluksuz/büyük harf halini, sorgu SIRASINDA (DB tarafında) üretir --
    Kisi/KisiPlaka/KaraListesi/Kayit tablolarının HEPSİ zaten uppercase+temiz
    saklandığı için func.upper() yalnızca eski/elle düzenlenmiş satırlara
    karşı ekstra bir savunma katmanıdır."""
    return func.replace(func.upper(kolon), " ", "")


def _plaka_yetki_kontrol(db: Session, plaka_no: str, referans_zaman: Optional[datetime] = None):
    """Önce kara liste, sonra aktif kişiler + saat/gün kısıtlaması kontrol edilir.

    `referans_zaman`: saat/gün kısıtlaması hangi ana göre değerlendirilsin?
    Normal (canlı) bir tespitte bu HER ZAMAN "şimdi" olmalı (parametre
    verilmezse varsayılan budur) -- ama GEÇMİŞ bir Kayıt satırını yeniden
    değerlendirirken (bkz. _gecmis_kayitlari_kisiye_bagla, 2026-09-18) "şimdi"
    YANLIŞ olur: örn. yalnızca 08:00-18:00 arası yetkili bir personelin
    GECE geçmiş eski bir kaydı, bu fonksiyon "şimdi" gündüzse yanlışlıkla
    yetkili işaretlerdi. Bu yüzden geçmişe dönük yeniden değerlendirmede
    kaydın KENDİ `tarih_saat`i buraya verilir."""
    simdi = referans_zaman or datetime.now()
    hedef = _plaka_normalize(plaka_no)

    # GÜVENLİK KÖK NEDEN DÜZELTMESİ (2026-09-17): bu iki sorgu (kara liste ve
    # ek plaka) önceden `Model.plaka_no == hedef` biçiminde DOĞRUDAN eşitlik
    # kullanıyordu. `hedef` boşluksuz normalize edilmiş bir değerken (bkz.
    # _plaka_normalize), KaraListesi.plaka_no/KisiPlaka.plaka_no DB'de
    # BOŞLUKLU saklanıyor (bkz. schemas.py::plaka_normalize, ki boşlukları
    # KORUR ve tüm giriş uçlarında -- KaraListesiOlustur, KisiPlakaOlustur,
    # KisiOlustur -- kullanılan TEK doğrulama kuralıdır). Sonuç: "34 GA 0835"
    # kara listeye eklense bile gerçek bir kamera tespitinde ("34 GA 0835"
    # okunduğunda hedef="34GA0835" olur) ASLA eşleşmiyordu -- kara liste
    # engeli VE bir kişinin ek plakaları FİİLEN HİÇ ÇALIŞMIYORDU. Artık
    # karşılaştırma DB tarafında da boşluksuzlaştırılarak (bkz.
    # _plaka_normalize_sql) yapılıyor; aşağıdaki Kişi eşleştirmesi zaten
    # bu deseni (Python tarafında normalize edip karşılaştırma) doğru
    # uyguluyordu, artık üçü de tutarlı.
    kara = db.query(models.KaraListesi).filter(
        models.KaraListesi.aktif == True,  # noqa: E712
        _plaka_normalize_sql(models.KaraListesi.plaka_no) == hedef,
    ).first()
    if kara:
        return "kara_liste", None, None

    kisi = None
    for k in db.query(models.Kisi).filter(models.Kisi.aktif == True).all():  # noqa: E712
        if _plaka_normalize(k.plaka_no) == hedef:
            kisi = k
            break

    if not kisi:
        ek = db.query(models.KisiPlaka).filter(
            models.KisiPlaka.aktif == True,  # noqa: E712
            _plaka_normalize_sql(models.KisiPlaka.plaka_no) == hedef,
        ).first()
        if ek:
            kisi = db.query(models.Kisi).filter(
                models.Kisi.id == ek.kisi_id,
                models.Kisi.aktif == True,  # noqa: E712
            ).first()

    if not kisi:
        return "yetkisiz", None, None

    if kisi.tip == "ziyaretci" and kisi.bitis_tarihi and kisi.bitis_tarihi < simdi:
        return "suresi_dolmus", kisi.id, kisi.tip

    # Saat kısıtlaması
    #
    # GÜVENLİK KÖK NEDEN DÜZELTMESİ (2026-09-22 kod incelemesi): bu blok
    # (ve aşağıdaki gün kısıtlaması bloğu) önceden `except Exception: pass`
    # kullanıyordu -- yani kısıtlama HESAPLANIRKEN beklenmedik bir hata
    # oluşursa (ör. ileride eklenebilecek bir toplu içe aktarma yolunun,
    # pydantic doğrulamasını atlayıp giris_saati_baslangic'e "25:99" gibi
    # bozuk bir değer yazması), kod sessizce bu try/except'i atlayıp
    # fonksiyonun sonundaki `return "yetkili", ...`a düşüyordu. Bu, bir
    # ERİ�ŞİM KONTROL SİSTEMİ için TAM TERS yönde bir hata: bir kısıtlamayı
    # DEĞERLENDİREMEMEK asla "izin ver" anlamına gelmemeli, "reddet" anlamına
    # gelmeli (fail-closed, fail-open değil). Bugünkü giriş yolları (pydantic
    # `pattern=r"^\d{2}:\d{2}$"` -- bkz. schemas.py::KisiOlustur/KisiGuncelle
    # -- ve yalnızca rakamları süzen izin_verilen_gunler ayrıştırması) bunu
    # tetiklemeyi zorlaştırıyor, ama sıfır-sessiz-hata ilkesi gereği bu kod
    # yolu da düzeltildi: artık hem GÜVENLİ tarafa (yetkisiz) düşer hem de
    # `pass` yerine bir hata logu bırakır (bkz. _iso_tarih_parametresini_coz
    # docstring'indeki AYNI ilke).
    try:
        if kisi.giris_saati_baslangic and kisi.giris_saati_bitis:
            simdi_hm = simdi.strftime("%H:%M")
            if not (kisi.giris_saati_baslangic <= simdi_hm <= kisi.giris_saati_bitis):
                return "yetkisiz", None, None
    except Exception as exc:
        logger.error(
            "Kişi #%s için saat kısıtlaması değerlendirilemedi (giris_saati_baslangic=%r, "
            "giris_saati_bitis=%r) -- güvenli taraf gereği YETKİSİZ sayıldı: %s",
            kisi.id, kisi.giris_saati_baslangic, kisi.giris_saati_bitis, exc,
        )
        return "yetkisiz", None, None

    # Gün kısıtlaması (0=Pazartesi … 6=Pazar)
    try:
        if kisi.izin_verilen_gunler:
            izin = {int(g.strip()) for g in kisi.izin_verilen_gunler.split(",") if g.strip().isdigit()}
            if simdi.weekday() not in izin:
                return "yetkisiz", None, None
    except Exception as exc:
        logger.error(
            "Kişi #%s için gün kısıtlaması değerlendirilemedi (izin_verilen_gunler=%r) -- "
            "güvenli taraf gereği YETKİSİZ sayıldı: %s",
            kisi.id, kisi.izin_verilen_gunler, exc,
        )
        return "yetkisiz", None, None

    return "yetkili", kisi.id, kisi.tip


def _gecmis_kayitlari_kisiye_bagla(db: Session, kisi: models.Kisi, duzenleyen_kullanici_adi: str) -> int:
    """Bir Kişi eklendikten/düzenlendikten (ya da bir ek plaka bağlandıktan)
    SONRA, o kişinin plakasıyla eşleşen ama o an henüz kayıtlı olmadığı için
    "yetkisiz" kalmış GEÇMİŞ `Kayit` satırlarını bulur ve bu kişiyle
    günceller (kullanıcı bildirimi, 2026-09-18: "39 AEZ 645" aracı personel
    olarak kaydedildikten SONRA o araca ait YENİ kamera tespitleri doğru
    şekilde "yetkili" gösteriliyordu -- yalnızca kayıt ANINDA değerlendirilip
    DONDURULMUŞ, kaydedilmeden ÖNCEKİ eski satırlar "yetkisiz" olarak geride
    kalmıştı; bu beklenen bir davranıştı ama kullanıcı bunların da
    düzeltilebilmesini istedi).

    GÜVENLİK/DOĞRULUK: yalnızca şu ANDA `yetki_durumu="yetkisiz"` VE
    `kisi_id IS NULL` olan satırlara dokunulur -- kara liste (`kara_liste`),
    süresi dolmuş ziyaretçi (`suresi_dolmus`) ya da BAŞKA bir kişiye zaten
    bağlı satırlar ASLA sessizce üzerine yazılmaz. Her satır, "şimdi" değil
    KENDİ ORİJİNAL `tarih_saat`i referans alınarak yeniden değerlendirilir
    (bkz. _plaka_yetki_kontrol'ün `referans_zaman` parametresi) -- bu sayede
    saat/gün kısıtlaması olan bir personelin bu kısıtlamaya UYMAYAN eski bir
    kaydı yanlışlıkla yetkili işaretlenmez. Döner: güncellenen kayıt sayısı."""
    hedef_plakalar = {_plaka_normalize(kisi.plaka_no)}
    for ek in db.query(models.KisiPlaka).filter(
        models.KisiPlaka.kisi_id == kisi.id, models.KisiPlaka.aktif == True,  # noqa: E712
    ).all():
        hedef_plakalar.add(_plaka_normalize(ek.plaka_no))

    adaylar = (
        db.query(models.Kayit)
        .filter(
            models.Kayit.yetki_durumu == "yetkisiz",
            models.Kayit.kisi_id.is_(None),
            _plaka_normalize_sql(models.Kayit.plaka_no).in_(hedef_plakalar),
        )
        .all()
    )

    guncellenen = 0
    for kayit in adaylar:
        yeni_yetki, yeni_kisi_id, yeni_kisi_tip = _plaka_yetki_kontrol(
            db, kayit.plaka_no, referans_zaman=kayit.tarih_saat
        )
        if yeni_kisi_id != kisi.id or yeni_yetki != "yetkili":
            # Kara liste, farklı bir kişi ya da hâlâ saat/gün kısıtlamasına
            # takılan bir satırsa DOKUNMA -- yalnızca GERÇEKTEN bu kişiye
            # bağlanıp yetkili hale gelen satırlar güncellenir.
            continue
        kayit.yetki_durumu = yeni_yetki
        kayit.kisi_id = yeni_kisi_id
        kayit.kisi_tip_anlik = yeni_kisi_tip
        kayit.duzenleyen = duzenleyen_kullanici_adi
        kayit.duzenleme_tarihi = datetime.now()
        guncellenen += 1

    if guncellenen:
        db.commit()
        logger.info(
            "Geçmiş kayıtlar yeniden değerlendirildi: kişi=%s (%s), güncellenen=%d/%d",
            kisi.id, kisi.ad_soyad, guncellenen, len(adaylar),
        )
    return guncellenen


_BILINEN_PLAKA_DUZELTME_GUVEN_TAVANI = 0.90  # bu güvenin ÜZERİNDEKİ okumalar zaten güvenilir, dokunma


def _bilinen_plakalar_sozlugu(db: Session) -> dict:
    """normalize edilmiş (boşluksuz, büyük harf) plaka -> orijinal (admin'in
    girdiği, boşluklu) biçim. Sahadaki TÜM bilinen (abone/personel) ana ve ek
    plakaları kapsar.

    Hem `_bilinen_plakaya_yakinlik_duzelt` (OCR düzeltmesi) hem de
    `_bilinen_plakaya_yakin_mi` (otomatik-kayıt güven eşiği filtresindeki
    "bilinen araç" istisnası, bkz. kayit_ekle_otomatik) tarafından ortak
    kullanılır -- aynı sorgu mantığının iki yerde birbirinden bağımsız,
    zamanla sapabilecek iki kopyası olmasın diye (bu depoda daha önce görülen
    "sessiz tekrar" hata sınıfının bir başka biçimi, bkz. metin_araclari.py).
    """
    sozluk: dict = {}
    for k in db.query(models.Kisi).filter(models.Kisi.aktif == True).all():  # noqa: E712
        norm = _plaka_normalize(k.plaka_no)
        if norm:
            sozluk.setdefault(norm, k.plaka_no)
    for ek in db.query(models.KisiPlaka).filter(models.KisiPlaka.aktif == True).all():  # noqa: E712
        norm = _plaka_normalize(ek.plaka_no)
        if norm:
            sozluk.setdefault(norm, ek.plaka_no)
    return sozluk


def _bilinen_plakaya_yakin_mi(db: Session, ham_plaka: str) -> bool:
    """Ham OCR metni, sahadaki bilinen (abone/personel) bir plakayla TAM
    eşleşiyor ya da (en_yakin_bilinen_plakayi_bul'daki gibi) tek karakter
    farkla eşleşiyor mu?

    KÖK NEDEN (kullanıcı bildirimi, 2026-09-17 devam): kullanıcının kendi
    aracı girişte %96.6 güvenle okundu ama genel otomatik-kayıt eşiği
    (varsayılan %97) altında kaldığı için o geçiş HİÇ KAYDEDİLMEDİ -- aynı
    araç çıkışta (daha yüksek güvenle) kaydedildiği için giriş/çıkış kayıtları
    tutarsız hale geldi. Genel eşik, aslında SİSTEMDE HİÇ KAYITLI OLMAYAN
    (yani yanlış/hatalı okunmuş) plakaların kayıtları şişirmesini önlemek
    için var; ama sahada zaten kayıtlı bir araç için düşük bir OCR güven
    skoru genellikle ışık/açı gibi görüntü kalitesi sorunlarından kaynaklanır,
    okunan METNİN kendisi çoğu zaman yine de doğrudur. Bu fonksiyon, güven
    eşiği filtresinin böyle bir tespiti yanlışlıkla atmasını önlemek için
    kullanılır (bkz. kayit_ekle_otomatik'teki "bilinen araç" istisnası).
    """
    hedef = _plaka_normalize(ham_plaka)
    if not hedef:
        return False
    bilinenler = _bilinen_plakalar_sozlugu(db)
    if hedef in bilinenler:
        return True
    return en_yakin_bilinen_plakayi_bul(hedef, set(bilinenler.keys())) is not None


def _bilinen_plakaya_yakinlik_duzelt(db: Session, ham_plaka: str, guven_skoru: Optional[float]) -> tuple:
    """OCR'ın tek bir karakteri yanlış okuduğu durumları, sahadaki BİLİNEN
    (abone/personel) plakalara karşı çapraz kontrol ederek düzeltir.

    Bu, ANPR endüstrisinde doğruluğu artıran standart bir teknik olarak bilinir
    ("veritabanı çapraz kontrolü / cross-referencing" — bkz. README'deki ANPR
    doğruluğu bölümü) ve özellikle site girişi gibi KAPALI bir plaka evreni
    olan sistemlerde etkilidir: OCR "34 ABC 128" okusa bile, sahada kayıtlı
    "34 ABC 123" ile tek karakter farkı varsa ve başka hiçbir bilinen plaka bu
    kadar yakın değilse, muhtemelen aynı araçtır.

    Güvenlik notu: bu düzeltme SADECE erişim vermek için kullanılır, asla kara
    listeye eklemek için değil — kara liste eşleşmesi (_plaka_yetki_kontrol
    içinde) her zaman TAM eşleşme ister. Böylece bu özellik yanlışlıkla
    erişimi KISITLAMAZ, sadece meşru bir aracın tesadüfi bir OCR hatası
    yüzünden yanlışlıkla "yetkisiz" görünmesini engeller.

    Döner: (kullanılacak_plaka, duzeltme_yapildiysa_orijinal_ham_okuma_yoksa_None)
    """
    hedef = _plaka_normalize(ham_plaka)

    # Zaten yeterince güvenli bir okuma varsa dokunma — yanlış bir "düzeltme"
    # ile doğru bir okumayı bozma riskini almayalım.
    if guven_skoru is not None and guven_skoru >= _BILINEN_PLAKA_DUZELTME_GUVEN_TAVANI:
        return ham_plaka, None

    # normalize edilmiş (boşluksuz) hal -> orijinal (admin'in girdiği) biçim.
    # Böylece düzeltme sonucu, sitedeki kayda göre TUTARLI bir biçimde
    # (örn. "34 ABC 123") döner; ham OCR metninin boşluk düzeni değil.
    bilinen_plakalar = _bilinen_plakalar_sozlugu(db)

    en_yakin_norm = en_yakin_bilinen_plakayi_bul(hedef, set(bilinen_plakalar.keys()))
    if en_yakin_norm is not None:
        return bilinen_plakalar[en_yakin_norm], ham_plaka
    return ham_plaka, None


# ------------------------------------------------------------------
# ÇAPRAZ KAMERA KISA SÜRELİ TEKRARI (2026-09-18)
# ------------------------------------------------------------------
# Kullanıcı talebi: giriş kamerası bir aracı kaydettikten sonra, araç geçişine
# devam ederken çıkış kamerasının açısına da girebiliyor (fiziksel olarak iki
# kameranın görüş alanı aynı geçidi/yolu paylaşıyor) -- bu TEK bir fiziksel
# geçiş olmasına rağmen, ikinci kameranın bunu AYRI bir kayıt (yanlış yönde
# bir "giriş" ya da "çıkış") olarak kaydetmesi isteniyordu. Bu,
# camera_reader.py::KameraPipeline.son_plaka_zamani/tekrar_gecikme_sn
# mekanizmasıyla ÇÖZÜLEMEZ -- o mekanizma yalnızca TEK bir kameranın kendi
# tekrarlarını (aynı pipeline nesnesinin belleğinde) bastırır; farklı
# kameralar (ayrı KameraPipeline nesneleri, hatta ayrı süreçler) birbirinin
# tespitlerinden habersizdir. Bu yüzden çapraz kamera kontrolü, TÜM
# kameraların ortak gerçek kaynağı olan VERİTABANI seviyesinde yapılır.
def _capraz_kamera_kisa_sureli_tekrar_mi(db: Session, plaka_no: str, kamera_id: str) -> Optional[models.Kayit]:
    """Aynı (normalize edilmiş) plaka, FARKLI bir kameradan, yapılandırılmış
    pencere içinde (varsayılan 180 sn = 3 dakika, bkz.
    `capraz_kamera_tekrar_penceresi_sn` sistem ayarı) zaten kaydedildiyse, o
    önceki Kayit satırını döner (yoksa None). Yalnızca OTOMATİK (kamera
    pipeline/harici ANPR) tespitlere uygulanır -- elle girilen kayıtlar
    (manuel_giris=True) bu kontrolden HİÇ geçirilmez, çünkü görevlinin
    bilinçli girdiği bir kaydın sessizce atlanması yanlış olur (bkz.
    _kayit_olustur_ve_bildir'deki çağrı).

    Pencere 0 veya negatifse özellik tamamen KAPALIDIR (geriye dönük
    uyumluluk / kullanıcı devre dışı bırakmak isteyebilir)."""
    # Kayit.plaka_no VERİTABANINA HER ZAMAN büyük harf/kırpılmış yazılır (bkz.
    # _kayit_olustur_ve_bildir'in sonundaki models.Kayit(...) çağrısı) --
    # ama bu fonksiyona gelen `plaka_no` argümanı, bilinen-plaka OCR
    # düzeltmesinden (bkz. _bilinen_plakaya_yakinlik_duzelt) doğrudan
    # gelmiş olabilir ve o, admin'in Kişi kaydına GİRDİĞİ ham biçimi (farklı
    # harf büyüklüğünde olabilir) döner. Burada da normalize etmezsek,
    # karşılaştırma sessizce eşleşmeyip gerçek bir çapraz kamera tekrarını
    # KAÇIRABİLİRDİ -- bu yüzden savunmacı olarak burada da normalize edilir.
    plaka_no = plaka_no.upper().strip()
    pencere_ham = _sistem_ayarlari_oku().get("capraz_kamera_tekrar_penceresi_sn", 180)
    try:
        pencere_sn = int(pencere_ham)
    except (TypeError, ValueError):
        pencere_sn = 180
    if pencere_sn <= 0:
        return None

    esik_zaman = datetime.now() - timedelta(seconds=pencere_sn)
    return (
        db.query(models.Kayit)
        .filter(
            models.Kayit.plaka_no == plaka_no,
            models.Kayit.kamera_id != kamera_id,
            models.Kayit.tarih_saat >= esik_zaman,
        )
        .order_by(desc(models.Kayit.tarih_saat))
        .first()
    )


# ================================================================
# ARVENTO ENTEGRASYONU (harici sürücü-kimlik sistemi) -- 2026-09-23
# ================================================================
# Kullanıcı isteği: "Arvento Sisteminde kimlik kartı ile aracın çalıştıran
# personelin, arvento tarafından gelen araç kullanan bilgisi pts sistemine
# entegre edilmesini istiyorum ... o araç plaka tanıma sisteminden geçiş
# yaptığında direkt olarak aracı kullanan personel ismi ona göre
# güncellenecek." Arvento'nun webhook gövdesinin TAM biçimi bu yazılırken
# bilinmiyordu (kullanıcı: "bu konuyu arvento ile konuşmam gerekiyor") --
# bu yüzden aşağıdaki `_arvento_alan_bul` yaygın alan adı varyasyonlarını
# (Türkçe/İngilizce, snake_case/camelCase) tolere eder ve HİÇBİRİ
# bulunamazsa net bir 422 hatasıyla hangi anahtarların beklendiğini bildirir
# -- gerçek Arvento gövdesi farklı bir isim kullanıyorsa, bu sessizce
# yutulan bir eşleşme hatası yerine panelin/loglar'ın hemen fark edeceği bir
# hata olarak görünür.
_ARVENTO_PLAKA_ALANLARI = ["plaka", "plaka_no", "plate", "plateNo", "vehicle_plate", "vehiclePlate", "arac_plaka"]
_ARVENTO_SURUCU_ALANLARI = [
    "surucu_adi", "surucu", "surucuAdi", "driver_name", "driverName", "driver",
    "personel_adi", "personelAdi", "kullanici_adi", "employee_name", "employeeName",
]
_ARVENTO_KART_ALANLARI = ["kart_no", "kartNo", "card_no", "cardNo", "card_id", "rfid", "personel_no", "sicil_no", "employee_id", "employeeId"]
_ARVENTO_ZAMAN_ALANLARI = ["olay_zamani", "olayZamani", "zaman", "timestamp", "event_time", "eventTime", "time"]


def _arvento_alan_bul(veri: dict, anahtarlar: list) -> Optional[str]:
    """`veri` sözlüğünde `anahtarlar` listesindeki adlardan (büyük/küçük harf
    duyarsız) ilk DOLU olanı bulup döner; hiçbiri yoksa/boşsa None döner."""
    kucuk_harfli = {str(k).lower(): v for k, v in veri.items()}
    for anahtar in anahtarlar:
        deger = kucuk_harfli.get(anahtar.lower())
        if deger is not None and str(deger).strip():
            return str(deger).strip()
    return None


def _arvento_surucu_bul(db: Session, plaka_no: str) -> Optional[str]:
    """Verilen (normalize edilmiş) plaka için Arvento'dan gelen EN GÜNCEL
    sürücü atamasını döner -- bkz. models.ArventoSuruculuOlay'ın docstring'i
    (neden `alinma_zamani`ya göre sıralandığı orada açıklanıyor). Hiç olay
    yoksa (Arvento entegrasyonu kullanılmıyor veya bu plaka için henüz bir
    olay gelmediyse) None döner ve models.Kayit.surucu_adi boş kalır --
    bu SESSİZ bir hata değildir, bu entegrasyonun kullanılmadığı/plakanın
    henüz bilinmediği normal durumdur."""
    olay = (
        db.query(models.ArventoSuruculuOlay)
        .filter(models.ArventoSuruculuOlay.plaka_no == plaka_no)
        .order_by(desc(models.ArventoSuruculuOlay.alinma_zamani))
        .first()
    )
    return olay.surucu_adi if olay else None


def _kayit_olustur_ve_bildir(db: Session, plaka_no: str, kamera_id: str, yon: str,
                              guven_skoru: Optional[float], goruntu_yolu: Optional[str],
                              dogrulama_kare_sayisi: Optional[int] = None,
                              not_metni: Optional[str] = None, manuel_giris: bool = False,
                              farkli_okuma_sayisi: Optional[int] = None,
                              misafir_adi: Optional[str] = None,
                              harici_katkili: Optional[bool] = None):
    plaka_no = re.sub(r"[^A-Za-z0-9 ]", "", plaka_no).strip().upper() or "BILINMEYEN"
    kamera_id = re.sub(r"[^A-Za-z0-9 _.\-]", "", str(kamera_id)).strip()[:50] or "KAMERA-1"

    ham_plaka_metni = None
    if _sistem_ayarlari_oku().get("bilinen_plaka_duzeltme_aktif", True):
        duzeltilmis, ham = _bilinen_plakaya_yakinlik_duzelt(db, plaka_no, guven_skoru)
        if ham is not None:
            logger.info("OCR düzeltmesi uygulandı: '%s' -> bilinen plaka '%s'", ham, duzeltilmis)
            ham_plaka_metni = ham
            plaka_no = duzeltilmis

    if not manuel_giris:
        onceki = _capraz_kamera_kisa_sureli_tekrar_mi(db, plaka_no, kamera_id)
        if onceki is not None:
            # AYNI aracın tek bir fiziksel geçişi iki farklı kameranın görüş
            # alanına da girmiş olabilir (bkz. yukarıdaki modül notu) -- bunu
            # AYRI bir giriş/çıkış kaydı olarak SAYMIYORUZ; önceki (ilk
            # kaydeden) kameranın kaydı zaten geçerli kalır.
            if goruntu_yolu and os.path.isfile(goruntu_yolu):
                try:
                    os.remove(goruntu_yolu)
                except OSError:
                    pass
            logger.info(
                "[%s] Çapraz kamera kısa süreli tekrarı atlandı: plaka=%s, %.0f sn önce "
                "kamera '%s' tarafından zaten kaydedilmiş (kayıt id=%d) -- aynı fiziksel "
                "geçiş olarak değerlendirildi, yeni kayıt oluşturulmadı.",
                kamera_id, plaka_no, (datetime.now() - onceki.tarih_saat).total_seconds(),
                onceki.kamera_id, onceki.id,
            )
            return JSONResponse(status_code=200, content={
                "atlandi": True,
                "sebep": "capraz_kamera_kisa_sureli_tekrar",
                "plaka_no": plaka_no,
                "onceki_kamera_id": onceki.kamera_id,
                "onceki_kayit_id": onceki.id,
                "onceki_tarih_saat": onceki.tarih_saat.isoformat(),
            })

    yetki, kisi_id, kisi_tip = _plaka_yetki_kontrol(db, plaka_no)

    not_metni_temiz = (not_metni or "").strip() or None
    misafir_adi_temiz = (misafir_adi or "").strip() or None
    # Arvento entegrasyonu (2026-09-23): "o araç plaka tanıma sisteminden
    # geçiş yaptığında direkt olarak aracı kullanan personel ismi ona göre
    # güncellenecek" -- bkz. _arvento_surucu_bul'un docstring'i. Hem kamera
    # pipeline'ından (kayit_ekle_otomatik) hem manuel eklemeden
    # (kayit_ekle_manuel) gelen TÜM kayıtlar bu TEK fonksiyondan geçtiği için
    # arama burada, tek bir yerde yapılır.
    surucu_adi = _arvento_surucu_bul(db, plaka_no)
    kayit = models.Kayit(
        plaka_no=plaka_no.upper().strip(),
        kamera_id=kamera_id,
        yon=yon,
        guven_skoru=guven_skoru,
        goruntu_yolu=goruntu_yolu,
        ham_plaka_metni=ham_plaka_metni,
        yetki_durumu=yetki,
        kisi_id=kisi_id,
        kisi_tip_anlik=kisi_tip,
        dogrulama_kare_sayisi=dogrulama_kare_sayisi,
        not_metni=not_metni_temiz,
        misafir_adi=misafir_adi_temiz,
        surucu_adi=surucu_adi,
        manuel_giris=manuel_giris,
        farkli_okuma_sayisi=farkli_okuma_sayisi,
        harici_katkili=harici_katkili,
    )
    db.add(kayit)
    db.commit()
    db.refresh(kayit)

    # SON KULLANILAN NOT ÖNBELLEĞİ (2026-09-17, devam): bkz. modülün üst
    # kısmındaki açıklama -- kalıcı kayda (yukarıdaki not_metni) HİÇ
    # dokunmaz, yalnızca bir sonraki not girişi için geçici bir öneri sağlar.
    if not_metni_temiz:
        _son_not_kaydet(plaka_no, not_metni_temiz)

    if yetki == "yetkili":
        mesaj = f"HOŞ GELDİNİZ {plaka_no.upper()}"
    elif yetki == "suresi_dolmus":
        mesaj = f"ZİYARETÇİ SÜRESİ DOLDU: {plaka_no.upper()}"
    elif yetki == "kara_liste":
        mesaj = f"KARA LİSTE: {plaka_no.upper()} GEÇİŞ ENGELLENDİ"
    else:
        mesaj = f"YETKİSİZ ARAÇ: {plaka_no.upper()}"

    basarili = led_panel.led_mesaj_gonder(mesaj)
    db.add(models.LedMesaj(mesaj=mesaj, basarili=basarili))
    if yetki != "yetkili":
        db.add(models.Alarm(
            kayit_id=kayit.id,
            plaka_no=kayit.plaka_no,
            alarm_tipi="kara_liste" if yetki == "kara_liste" else (
                "suresi_dolmus" if yetki == "suresi_dolmus" else "yetkisiz_arac"
            ),
            mesaj=mesaj,
        ))

    # Şüpheli araç tespiti: son 1 saatte eşiği aşan red sayısı
    if yetki in ("yetkisiz", "kara_liste"):
        try:
            esik = int(_sistem_ayarlari_oku().get("supheli_esik", 3))
            bir_saat_once = datetime.now() - timedelta(hours=1)
            red_sayisi = db.query(models.Kayit).filter(
                models.Kayit.plaka_no == plaka_no,
                models.Kayit.yetki_durumu.in_(["yetkisiz", "kara_liste"]),
                models.Kayit.tarih_saat >= bir_saat_once,
            ).count()
            if red_sayisi >= esik:
                mevcut = db.query(models.Alarm).filter(
                    models.Alarm.plaka_no == plaka_no,
                    models.Alarm.alarm_tipi == "supheli_arac",
                    models.Alarm.tarih_saat >= bir_saat_once,
                    models.Alarm.okundu == False,  # noqa: E712
                ).first()
                if not mevcut:
                    supheli_mesaj = f"ŞÜPHELİ ARAÇ: {plaka_no} son 1 saatte {red_sayisi} kez reddedildi"
                    db.add(models.Alarm(
                        kayit_id=kayit.id,
                        plaka_no=plaka_no,
                        alarm_tipi="supheli_arac",
                        mesaj=supheli_mesaj,
                    ))
                    logger.warning("Şüpheli araç: %s (%d red/saat)", plaka_no, red_sayisi)
                    # DÜZELTME (2026-09-26): bu alarm ÖNCEDEN yalnızca panelde
                    # görünüyordu, hiçbir dış bildirime (webhook/telegram)
                    # bağlı değildi -- tam da "şüpheli araç" gibi ACİL bir
                    # durumda nöbetçi ekrana bakmıyorsa hiç haberi olmuyordu.
                    _bildirim_tetikle(db, "supheli_arac", {
                        "olay": "supheli_arac", "alarm_tipi": "supheli_arac",
                        "plaka_no": plaka_no, "mesaj": supheli_mesaj,
                    })
        except Exception as exc:
            logger.error("Şüpheli araç kontrolü hatası: %s", exc)

    db.commit()

    # Yetkili araç girişinde otomatik bariyer açma
    if yetki == "yetkili" and yon == "giris":
        try:
            auto_bariyerler = db.query(models.BariyerAyarlari).filter(
                models.BariyerAyarlari.aktif == True,  # noqa: E712
                models.BariyerAyarlari.auto_ac == True,  # noqa: E712
            ).all()
            for b in auto_bariyerler:
                if b.mod == "http" and b.http_url:
                    threading.Thread(
                        target=_webhook_gonder_sync,
                        args=(b.http_url, b.http_metot, {"plaka": plaka_no, "eylem": "ac", "otopark": b.ad}),
                        daemon=True,
                    ).start()
                elif b.mod == "simulate":
                    # Manuel açmadaki (bkz. bariyer_ac) davranışla tutarlı
                    # olsun diye: gerçekte hiçbir şey açılmıyor ama en azından
                    # loglanıyor, sessizce hiçbir iz bırakmıyor.
                    logger.info("Bariyer açıldı (simülasyon, otomatik): %s, plaka=%s", b.ad, plaka_no)
                else:
                    # DÜZELTME (2026-09-25, sistem taraması): "gpio" modu
                    # (ve http modu http_url'siz tanımlanmışsa) önceden bu
                    # döngüde SESSİZCE hiçbir şey yapmıyordu -- yetkili bir
                    # araç girse, plaka doğru okunup kayıt oluşsa bile fiziksel
                    # bariyer hiç açılmıyor ve bunun nedenini gösteren HİÇBİR
                    # log/alarm/denetim izi kalmıyordu. GPIO modu şemada/
                    # panelde bir seçenek olarak sunulsa da bu sürümde gerçek
                    # bir GPIO sürücüsü yok (bkz. bariyer_ac'ın manuel açma
                    # tarafındaki aynı "Desteklenmeyen bariyer modu" hatası).
                    # Artık en azından açıkça loglanıyor VE panelde görülebilir
                    # bir alarm kaydı düşülüyor ki personel "araç girdi ama
                    # bariyer açılmadı" durumunun nedenini bulabilsin.
                    sebep = (
                        f"'{b.ad}' bariyeri GPIO modunda tanımlı ama bu sürüm GPIO desteği içermiyor"
                        if b.mod == "gpio"
                        else f"'{b.ad}' bariyeri HTTP modunda ama http_url tanımlanmamış"
                    )
                    logger.error("Otomatik bariyer açılamadı (plaka=%s): %s", plaka_no, sebep)
                    bariyer_mesaj = f"Yetkili araç girişinde bariyer otomatik AÇILAMADI: {sebep}"
                    db.add(models.Alarm(
                        kayit_id=kayit.id,
                        plaka_no=plaka_no,
                        alarm_tipi="bariyer_hatasi",
                        mesaj=bariyer_mesaj,
                    ))
                    db.commit()
                    # DÜZELTME (2026-09-26): bkz. supheli_arac'taki AYNI notu --
                    # bariyer açılamaması yetkili bir aracın nizamiyede
                    # BEKLEMESİ demektir, panelin dışında da anında bilinmeli.
                    _bildirim_tetikle(db, "bariyer_hatasi", {
                        "olay": "bariyer_hatasi", "alarm_tipi": "bariyer_hatasi",
                        "plaka_no": plaka_no, "mesaj": bariyer_mesaj,
                    })
        except Exception as exc:
            logger.error("Otomatik bariyer hatası: %s", exc)

    # SSE ile bağlı tüm istemcilere gerçek zamanlı bildirim gönder
    sse_veri = {
        "id": kayit.id,
        "plaka_no": kayit.plaka_no,
        "kamera_id": kayit.kamera_id,
        "yon": kayit.yon,
        "yetki_durumu": kayit.yetki_durumu,
        "tarih_saat": kayit.tarih_saat.isoformat(),
        "guven_skoru": kayit.guven_skoru,
    }
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_sse_yayinla("kayit", sse_veri, db))
            asyncio.ensure_future(_webhook_bildir(db, yetki, sse_veri))
    except RuntimeError:
        pass

    # TUTARLILIK DÜZELTMESİ (2026-09-22 kod incelemesi): kayit_duzenle'deki
    # AYNI kök nedenle -- bu fonksiyon (POST /kayitlar VE POST /kayitlar/
    # otomatik'in ikisi de buradan geçer) response_model=KayitCevap'ın
    # kisi_adi/vardiya_adi alanlarını hiç doldurmadan çıplak `kayit`ı
    # dönüyordu. Örn. manuel olarak zaten kayıtlı bir kişinin plakasını
    # girdiğinizde (kisi_id backend'de doğru atanır) yanıttaki kisi_adi
    # yine de None gelirdi -- GET /kayitlar'ın aynı satır için döneceğinden
    # farklı, tutarsız bir görünüm.
    _kayitlarin_vardiya_adlarini_ekle([kayit], db)
    _kayitlara_kisi_adini_ekle([kayit], db)
    return kayit


def _webhook_gonder_sync(url: str, metot: str, veri: dict) -> bool:
    """Urllib ile senkron webhook isteği — arka plan thread'inde çalıştırılır."""
    import urllib.request
    govde = json.dumps(veri, ensure_ascii=False, default=str).encode("utf-8")
    req = urllib.request.Request(url, data=govde, method=metot,
                                  headers={"Content-Type": "application/json", "User-Agent": "PTS/2.0"})
    try:
        with urllib.request.urlopen(req, timeout=8):
            pass
        return True
    except Exception as exc:
        logger.warning("Webhook gönderilemedi %s: %s", url, exc)
        return False


_BILDIRIM_TIPLERI = ("webhook", "telegram")


def _bildirim_gonder_sync(tip: str, hedef: str, http_metot: str, veri: dict) -> "tuple[bool, Optional[str]]":
    """`BildirimAyarlari.tip`'e göre GERÇEK gönderimi yapan tek dispatcher
    (2026-09-26, kullanıcı isteği: "Telegram ile anlık dış bildirim").

    KÖK NEDEN düzeltmesi: bu fonksiyondan ÖNCE `/bildirim/test/{id}` ve her
    çağıran, `tip` alanına HİÇ bakmadan koşulsuz `_webhook_gonder_sync`'i
    çağırıyordu -- panelden/API'den `tip="email"` (şemada belgelenen ama
    hiçbir zaman gerçekten uygulanmamış bir değer) ya da bir yazım hatası
    (`"webbhook"`) ile bir bildirim ayarı oluşturulursa, `hedef` bir URL
    değilmiş gibi `urllib`'e verilip anlaşılmaz bir bağlantı hatasıyla
    "başarısız" dönüyordu -- ayarın kendisinin desteklenmediği HİÇBİR
    zaman söylenmiyordu (sessiz/yanıltıcı başarısızlık). Artık tanımadığımız
    bir `tip` için açıkça "Desteklenmeyen bildirim tipi" hatası dönülür."""
    if tip == "webhook":
        basarili = _webhook_gonder_sync(hedef, http_metot, veri)
        return basarili, (None if basarili else "Webhook isteği başarısız oldu (bkz. sunucu logu)")
    if tip == "telegram":
        return telegram_bildirim.telegram_gonder_sync(hedef, veri)
    return False, f"Desteklenmeyen bildirim tipi: '{tip}' (yalnızca {'/'.join(_BILDIRIM_TIPLERI)} desteklenir)"


def _bildirim_tetikle(db: Session, tetikleyici: str, veri: dict) -> None:
    """Tetikleyicisi `tetikleyici` ile TAM eşleşen VEYA `hepsi` olan, aktif
    TÜM bildirim ayarlarına (tip'ten bağımsız -- webhook/telegram) arka
    planda (ayrı thread) bildirim gönderir. Hem senkron (ör. kamera bekçisi
    thread'i) hem "async def" içinden (aşağıdaki `kayit_ekle_otomatik`
    akışı gibi) çağrılabilir -- kendisi bloklamaz, yalnızca BildirimAyarlari
    sorgusu (birkaç satır, hızlı) senkron çalışır."""
    try:
        ayarlar = db.query(models.BildirimAyarlari).filter(
            models.BildirimAyarlari.aktif == True,  # noqa: E712
            or_(models.BildirimAyarlari.tetikleyici == "hepsi", models.BildirimAyarlari.tetikleyici == tetikleyici),
        ).all()
    except Exception as exc:
        logger.error("Bildirim ayarları okunamadı: %s", exc)
        return
    for a in ayarlar:
        threading.Thread(
            target=_bildirim_gonder_sync, args=(a.tip, a.hedef, a.http_metot, veri), daemon=True,
        ).start()


async def _webhook_bildir(db: Session, yetki_durumu: str, veri: dict) -> None:
    """Kayıt oluşturma akışının (bkz. aşağıdaki `kayit_ekle_otomatik`/
    `kayit_ekle_manuel` -> `_kayit_olustur_ve_bildir`) bildirim tetikleyici
    noktası -- `yetki_durumu` ("yetkili"/"yetkisiz"/"kara_liste"/
    "suresi_dolmus") tetikleyici değeri olarak kullanılır."""
    _bildirim_tetikle(db, yetki_durumu, veri)


@app.post("/kayitlar", response_model=schemas.KayitCevap)
def kayit_ekle_manuel(kayit: schemas.KayitManuel, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Elle / test amaçlı kayıt ekleme (görsel olmadan). Panel üzerindeki 'Test Kaydı Ekle' formu bunu kullanır."""
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    return _kayit_olustur_ve_bildir(
        db, kayit.plaka_no, kayit.kamera_id, kayit.yon, kayit.guven_skoru, None,
        not_metni=kayit.not_metni, manuel_giris=True, misafir_adi=kayit.misafir_adi,
    )


@app.post("/kayitlar/otomatik", response_model=schemas.KayitCevap, dependencies=[Depends(_hiz_sinir_otomatik_kayit)])
async def kayit_ekle_otomatik(
    plaka_no: str = Form(...),
    kamera_id: str = Form("KAMERA-1"),
    yon: str = Form("giris"),
    guven_skoru: Optional[float] = Form(None),
    dogrulama_kare_sayisi: Optional[int] = Form(None),
    farkli_okuma_sayisi: Optional[int] = Form(None),
    # "Dahua Katkısı" (2026-09-25) -- bkz. models.Kayit.harici_katkili'nin
    # docstring'i. Yalnızca camera_reader.py'nin kendi pipeline'ından gelir
    # (bkz. oradaki POST gövdesi); harici bir ANPR sisteminin bu alanı hiç
    # göndermediği (Optional, varsayılan None) durumda "hesaplanmadı" anlamına
    # gelmeye devam eder.
    harici_katkili: Optional[bool] = Form(None),
    gorsel: Optional[UploadFile] = File(None),
    x_pts_kamera_anahtari: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Gerçek kamera pipeline'ının veya harici bir sistemin görsel ile kayıt gönderdiği uç nokta.

    Kullanıcı oturumu gerektirmez (kameralar giriş yapamaz); bunun yerine PTS_KAMERA_ANAHTARI ortam
    değişkeni ayarlıysa X-PTS-Kamera-Anahtari başlığıyla eşleşmesi zorunlu tutulur.
    """
    beklenen_anahtar = _kamera_anahtari_degeri()
    # x_pts_kamera_anahtari.strip(): gönderen taraf (camera_reader.py) artık
    # kendi değerini .strip() ediyor, ama gelen başlığı da aynı şekilde ele
    # almak (harici bir CCTV/NVR sisteminin kendi ayarlarında sona boşluk/
    # satır sonu bırakması ihtimaline karşı) savunmayı iki katına çıkarır --
    # bkz. _kamera_anahtari_degeri'nin kök neden notu.
    if beklenen_anahtar and (x_pts_kamera_anahtari or "").strip() != beklenen_anahtar:
        raise HTTPException(401, "Geçersiz kamera anahtarı")

    goruntu_yolu = None
    if gorsel is not None:
        # GÜVENLİK: içerik türü ve boyut doğrulaması — bu uç nokta kimliksiz
        # olabildiğinden (PTS_KAMERA_ANAHTARI ayarlanmamışsa), önceden hiçbir
        # kısıtlama olmadan HERHANGİ bir dosya (rastgele boyutta, rastgele
        # türde) diske "gorsel" adı altında olduğu gibi yazılabiliyordu.
        if gorsel.content_type and not gorsel.content_type.startswith("image/"):
            raise HTTPException(400, f"Yalnızca görsel dosyaları kabul edilir (alınan: {gorsel.content_type})")

        # Dosya adı kullanıcı girdisinden (plaka_no) üretildiği için yalnızca güvenli karakterler bırakılır (path traversal önlemi).
        guvenli_plaka = re.sub(r"[^A-Za-z0-9]", "", plaka_no) or "PLAKA"
        # 2026-09-25 (sistem taraması): dosya adı eskiden yalnızca
        # `PLAKA_unixsaniye.jpg` idi. AYNI saniye içinde aynı plakayı gören iki
        # kamera (tipik: aynı geçidi paylaşan giriş+çıkış kameraları -- tam da
        # `_capraz_kamera_kisa_sureli_tekrar_mi`'nin var olma nedeni) AYNI
        # dosyaya yazıyordu: ikinci kamera birinci kaydın fotoğrafının ÜZERİNE
        # yazıyor, ardından çapraz-kamera tekrarı olarak atlanınca "kendi"
        # dosyasını -- yani birinci kaydın tek fotoğrafını -- SİLİYORDU. Sonuç:
        # ilk (geçerli) kayıt fotoğrafsız kalıyordu, sessizce. Kısa rastgele bir
        # ek bu çakışmayı ortadan kaldırıyor (ayrıca dosya adlarının tahmin
        # edilebilirliğini de azaltıyor, bkz. gorsel_getir'in güvenlik notu).
        dosya_adi = f"{guvenli_plaka}_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}.jpg"
        goruntu_yolu = os.path.join(GORUNTU_KLASORU, dosya_adi)
        toplam_bayt = 0
        asildi = False
        try:
            with open(goruntu_yolu, "wb") as f:
                while True:
                    parca = await gorsel.read(1024 * 1024)
                    if not parca:
                        break
                    toplam_bayt += len(parca)
                    if toplam_bayt > MAKS_GORSEL_BOYUTU_BAYT:
                        asildi = True
                        break
                    f.write(parca)
        except OSError as exc:
            # 2026-09-25 (sistem taraması): disk doluysa/izin sorunu varsa
            # eskiden yarım yazılmış bir .jpg diskte kalıyor (hiçbir kayda
            # bağlı olmayan yetim dosya) VE istek 500 ile düşüyordu -- yani
            # GEÇİŞ KAYDI DA kayboluyordu. Bir nizamiyede geçiş kaydı
            # fotoğraftan daha önemli: yarım dosyayı temizleyip kaydı
            # FOTOĞRAFSIZ oluşturuyoruz ve durumu görünür kılıyoruz.
            _yarim_dosyayi_sil(goruntu_yolu)
            goruntu_yolu = None
            _gorsel_yazma_hatasini_bildir(db, kamera_id, plaka_no, exc)
        if asildi:
            _yarim_dosyayi_sil(goruntu_yolu)
            raise HTTPException(
                413,
                f"Görsel {MAKS_GORSEL_BOYUTU_BAYT // (1024 * 1024)} MB sınırını aşıyor",
            )

    # GÜVEN EŞİĞİ FİLTRESİ (2026-09-17): kullanıcı talebiyle eklendi -- yalnızca
    # yeterince güvenli (varsayılan >= %97) OTOMATİK tespitler panele/kayıtlara
    # düşer; geri kalanı (hatalı/yanlış okunup kayıtları şişiren düşük güvenli
    # tespitler) burada, kayıt HİÇ OLUŞTURULMADAN elenir -- "kaydet sonra sil"
    # yerine "hiç kaydetme" tercih edildi (gereksiz DB satırı/disk yazımı yok).
    # Yalnızca guven_skoru DOLU olan (yani gerçek bir OCR tespiti olan)
    # isteklere uygulanır; bu uç nokta yalnızca kamera pipeline'ı/harici ANPR
    # sistemleri tarafından çağrıldığından (bkz. fonksiyon docstring'i) elle
    # girilen kayıtlar (kayit_ekle_manuel) bu filtreden HİÇ etkilenmez.
    ayarlar = _sistem_ayarlari_oku()
    esik = ayarlar.get("otomatik_kayit_min_guven_skoru", 0.97)
    try:
        esik = max(0.0, min(1.0, float(esik)))
    except (TypeError, ValueError):
        esik = 0.97
    if guven_skoru is not None and not (esik <= guven_skoru <= 1.0001):
        # BİLİNEN ARAÇ İSTİSNASI (2026-09-17, devam) -- bkz.
        # _bilinen_plakaya_yakin_mi'nin docstring'i: genel eşiğin altında
        # kalan bir tespit, sahada zaten kayıtlı bir plakayla TAM/çok yakın
        # eşleşiyorsa VE daha düşük "bilinen araç" eşiğini geçiyorsa yine de
        # kaydedilir -- kullanıcının kendi aracının, düşük bir OCR güven
        # skoru yüzünden girişte hiç kayda düşmeyip çıkışta düşmesi (giriş/
        # çıkış tutarsızlığı) buradan kaynaklanıyordu.
        bilinen_esik = ayarlar.get("otomatik_kayit_min_guven_skoru_bilinen_arac", 0.80)
        try:
            bilinen_esik = max(0.0, min(1.0, float(bilinen_esik)))
        except (TypeError, ValueError):
            bilinen_esik = 0.80
        bilinen_arac_istisnasi = (
            guven_skoru >= bilinen_esik and _bilinen_plakaya_yakin_mi(db, plaka_no)
        )
        if bilinen_arac_istisnasi:
            logger.info(
                "[%s] Bilinen araca yakın düşük güvenli tespit YİNE DE kaydedildi: "
                "plaka=%s güven=%.3f (genel eşik=%.3f, bilinen araç eşiği=%.3f)",
                kamera_id, plaka_no, guven_skoru, esik, bilinen_esik,
            )
            return _kaydi_olustur_gorseli_koru(db, plaka_no, kamera_id, yon, guven_skoru, goruntu_yolu,
                                               dogrulama_kare_sayisi, farkli_okuma_sayisi,
                                               harici_katkili=harici_katkili)

        if goruntu_yolu and os.path.isfile(goruntu_yolu):
            try:
                os.remove(goruntu_yolu)
            except OSError:
                pass
        logger.info(
            "[%s] Düşük güvenli tespit kayda düşürülmedi (atlandı): plaka=%s güven=%.3f (eşik=%.3f)",
            kamera_id, plaka_no, guven_skoru, esik,
        )
        return JSONResponse(status_code=200, content={
            "atlandi": True,
            "sebep": "dusuk_guven_skoru",
            "plaka_no": plaka_no,
            "guven_skoru": guven_skoru,
            "esik": esik,
        })

    return _kaydi_olustur_gorseli_koru(db, plaka_no, kamera_id, yon, guven_skoru, goruntu_yolu,
                                       dogrulama_kare_sayisi, farkli_okuma_sayisi,
                                       harici_katkili=harici_katkili)


def _yarim_dosyayi_sil(yol: Optional[str]) -> None:
    if yol and os.path.isfile(yol):
        try:
            os.remove(yol)
        except OSError:
            logger.warning("Yarım kalan görsel dosyası silinemedi: %s", yol)


_GORSEL_YAZMA_ALARM_ARALIK_SN = 600
_son_gorsel_yazma_alarm_zamani = 0.0
_gorsel_yazma_alarm_kilit = threading.Lock()


def _gorsel_yazma_hatasini_bildir(db: Session, kamera_id: str, plaka_no: str, exc: Exception) -> None:
    """Araç fotoğrafı diske yazılamadığında (disk dolu, izin sorunu vb.) her
    seferinde loglar; panelde görülebilir bir alarmı ise en fazla 10 dakikada
    bir üretir -- disk doluyken HER geçiş yeni bir alarm üretip alarm listesini
    boğmasın. Alarmın yazılamaması asıl kaydı engellemez."""
    global _son_gorsel_yazma_alarm_zamani
    logger.error("[%s] Araç görseli diske yazılamadı (plaka=%s), kayıt fotoğrafsız oluşturulacak: %s",
                 kamera_id, plaka_no, exc)
    with _gorsel_yazma_alarm_kilit:
        simdi = time.monotonic()
        if _son_gorsel_yazma_alarm_zamani and simdi - _son_gorsel_yazma_alarm_zamani < _GORSEL_YAZMA_ALARM_ARALIK_SN:
            return
        _son_gorsel_yazma_alarm_zamani = simdi
    try:
        disk_mesaji = f"Araç fotoğrafları diske YAZILAMIYOR (kayıtlar fotoğrafsız oluşturuluyor): {exc}"[:255]
        db.add(models.Alarm(
            # plaka_no NOT NULL + String(15) (bkz. models.Alarm); kamera
            # arızası alarmındaki gibi alarmın kaynağını (kamerayı) yazıyoruz.
            plaka_no=(re.sub(r"[^A-Za-z0-9 _.\-]", "", str(kamera_id)).strip() or "SISTEM")[:15],
            alarm_tipi="disk_hatasi",
            mesaj=disk_mesaji,
        ))
        db.commit()
        # DÜZELTME (2026-09-26): bkz. supheli_arac/bariyer_hatasi'ndeki AYNI
        # notu -- disk sorunu, kayıtların fotoğrafsız kalmaya BAŞLADIĞI andır,
        # yönetici bunu panelin dışında da anında bilmeli (zaten 10 dakikada
        # bir ile SINIRLI olduğu için burada bir bildirim spam riski yok).
        _bildirim_tetikle(db, "disk_hatasi", {
            "olay": "disk_hatasi", "alarm_tipi": "disk_hatasi", "mesaj": disk_mesaji,
        })
    except Exception:
        db.rollback()
        logger.exception("Görsel yazma hatası alarmı kaydedilemedi")


def _kaydi_olustur_gorseli_koru(db: Session, plaka_no: str, kamera_id: str, yon: str,
                                guven_skoru: Optional[float], goruntu_yolu: Optional[str],
                                dogrulama_kare_sayisi: Optional[int], farkli_okuma_sayisi: Optional[int],
                                harici_katkili: Optional[bool] = None):
    """`_kayit_olustur_ve_bildir`'i çağırır; kayıt oluşturma bir istisnayla
    başarısız olursa (ör. veritabanı o an erişilemez) ve bu görsel hiçbir
    kayda BAĞLANMADIYSA diskteki dosyayı siler -- eskiden bu durumda dosya,
    hiçbir kaydın göstermediği ve hiçbir temizlik görevinin (kayıt üzerinden
    çalıştıkları için) bulamadığı yetim bir dosya olarak diskte kalıyordu.
    Kayıt commit edildikten SONRAKİ bir adımda hata çıkarsa (bildirim vb.)
    dosya SİLİNMEZ, çünkü artık bir kayda bağlı."""
    try:
        return _kayit_olustur_ve_bildir(db, plaka_no, kamera_id, yon, guven_skoru, goruntu_yolu,
                                         dogrulama_kare_sayisi, farkli_okuma_sayisi=farkli_okuma_sayisi,
                                         harici_katkili=harici_katkili)
    except Exception:
        if goruntu_yolu:
            try:
                db.rollback()
                bagli = db.query(models.Kayit.id).filter(models.Kayit.goruntu_yolu == goruntu_yolu).first()
            except Exception:
                bagli = True  # emin olamıyorsak dosyayı silmeyelim
            if not bagli:
                _yarim_dosyayi_sil(goruntu_yolu)
        raise


def _iso_tarih_parametresini_coz(deger: Optional[str], alan_adi: str) -> Optional[datetime]:
    """Bir tarih filtresi query parametresini (`baslangic`/`bitis`) ISO 8601
    biçiminde ayrıştırır.

    KÖK NEDEN (2026-09-20): öncesinde `datetime.fromisoformat()` bu
    parametrelerin olduğu HER yerde doğrudan çağrılıyordu -- geçersiz bir
    değer (örn. `?baslangic=abc`) yakalanmamış bir `ValueError` fırlatıp
    isteği düz bir 500'e düşürüyordu. Bu, projenin kendi "sıfır sessiz hata"
    ilkesine aykırıydı: istemciye ne yanlış yaptığı hiç söylenmiyordu (genel
    500 mesajı "beklenmeyen bir hata" der, oysa bu tamamen beklenen ve
    açıkça reddedilmesi gereken bir istemci hatasıdır). Artık geçersiz bir
    değer, hangi alanın ve hangi değerin sorunlu olduğunu söyleyen açık bir
    400 ile reddediliyor."""
    if deger is None:
        return None
    try:
        return datetime.fromisoformat(deger)
    except ValueError:
        raise HTTPException(
            400,
            f"'{alan_adi}' alanı geçerli bir ISO 8601 tarihi olmalı (örn. 2026-01-31): '{deger}'",
        )


def _bitis_tarih_filtresi_sinirini_hesapla(bitis: Optional[str]) -> Optional[datetime]:
    """`bitis` filtre parametresini, SQL sorgusunda `<=` ile kullanılacak
    somut bir ÜST SINIR datetime'ına çevirir.

    KÖK NEDEN (2026-09-21, kullanıcı talebi: "kayıt filtreleme kısmına saat
    seçme özelliği de ekler misin, sadece tarih var, belirli saat
    aralıklarıyla da kayıt almam gerekiyor"): `bitis` önceden HER ZAMAN salt
    bir tarih ("2026-09-21") olarak kabul edilip, kullanıcının "o gün DAHİL"
    beklentisini karşılamak için körlemesine +1 gün eklenirdi (aksi halde
    tarih 00:00:00'a ayrıştığından o günün TAMAMI filtre dışı kalırdı).
    Şimdi `bitis` bir SAAT de içerebiliyor (örn. "2026-09-21T18:00:00",
    frontend'deki yeni saat seçiciyle üretilir) -- bu durumda kullanıcı
    "o günün SONUNA kadar" değil, TAM O ANA kadar filtrelemek istiyor;
    körlemesine +1 gün eklemek isteği bir sonraki güne kaydırıp yanlış
    (fazladan ~24 saatlik) sonuçlar döndürürdü.

    Ayrım, ayrıştırılmış datetime nesnesinin SAAT bileşenine bakılarak
    YAPILMAZ (saat bileşeni tesadüfen 00:00:00 da olabilir -- örn. kullanıcı
    bilerek "gece yarısına kadar" filtrelemek isteyebilir) -- ham metnin
    "T" ayırıcısı içerip içermediğine bakılır: ISO 8601'de salt tarih
    biçimi ("YYYY-MM-DD") "T" İÇEREMEZ, yalnızca tarih+saat biçimi
    ("YYYY-MM-DDTHH:MM[:SS]") içerir.

    `/kayitlar`, `/kayitlar/sayfa-bilgisi` ve `_rapor_tarih_araligi_metni`
    (Excel/PDF dışa aktarma başlığı) AYNI mantığı kullanmalı -- aksi halde
    dışa aktarılan rapordaki "arasında" metni ile gerçekte dönen kayıt
    kümesi birbirinden sapabilir."""
    if not bitis:
        return None
    bitis_dt = _iso_tarih_parametresini_coz(bitis, "bitis")
    if "T" not in bitis:
        bitis_dt = bitis_dt + timedelta(days=1)
    return bitis_dt


@app.post("/entegrasyonlar/arvento/webhook", response_model=schemas.ArventoWebhookCevap,
          dependencies=[Depends(_hiz_sinir_arvento_webhook)])
async def arvento_webhook(istek: Request, x_arvento_anahtari: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """Arvento'nun "bu plakayı şu an kim kullanıyor" olaylarını aldığı uç
    nokta (2026-09-23 kullanıcı isteği: "Arvento Sisteminde kimlik kartı ile
    aracın çalıştıran personelin ... bilgisi pts sistemine entegre
    edilmesini istiyorum ... o araç plaka tanıma sisteminden geçiş
    yaptığında direkt olarak aracı kullanan personel ismi ona göre
    güncellenecek"). Kullanıcı oturumu gerektirmez (Arvento giriş yapamaz);
    bunun yerine PTS_ARVENTO_ANAHTARI ortam değişkeni ayarlıysa
    X-Arvento-Anahtari başlığıyla eşleşmesi zorunlu tutulur -- bkz.
    _arvento_anahtari_degeri'nin docstring'i, /kayitlar/otomatik'teki AYNI
    desen.

    ÖNEMLİ (kimlik doğrulama): Arvento'nun KENDİ webhook doğrulama şeması
    (imza/HMAC, farklı bir başlık adı, IP allowlist vb.) olabilir --
    kullanıcı bunu henüz Arvento ile netleştirmedi ("bu konuyu arvento ile
    konuşmam gerekiyor fakat kendi webhook doğrulama şemaları olduğunu
    düşünüyorum"). Bu uç nokta bilinçli olarak EN BASİT/en yaygın yöntemi
    (paylaşılan gizli anahtar + özel başlık) uygular; gerçek şema netleşince
    yalnızca yukarıdaki kontrol (birkaç satır) değiştirilmesi yeterli olur,
    geri kalan eşleştirme/kayıt mantığına dokunulmaz.

    Gövde biçimi de KESİN değildir -- bkz. _arvento_alan_bul ve üstündeki
    _ARVENTO_*_ALANLARI listeleri: yaygın alternatif alan adları
    (Türkçe/İngilizce, snake_case/camelCase) denenir. Gerçek Arvento
    gövdesinde bunların DIŞINDA bir alan adı kullanılıyorsa, buradaki 422
    hata mesajı hangi adların denendiğini açıkça listeler -- yeni bir alan
    adı eklemek tek satırlık bir değişikliktir (bkz. yukarıdaki listeler).
    """
    beklenen_anahtar = _arvento_anahtari_degeri()
    if beklenen_anahtar and (x_arvento_anahtari or "").strip() != beklenen_anahtar:
        raise HTTPException(401, "Geçersiz Arvento anahtarı")

    try:
        veri = await istek.json()
    except Exception:
        raise HTTPException(400, "Geçersiz JSON gövdesi")
    if not isinstance(veri, dict):
        raise HTTPException(400, "Geçersiz JSON gövdesi (bir nesne/obje bekleniyor)")

    plaka_ham = _arvento_alan_bul(veri, _ARVENTO_PLAKA_ALANLARI)
    if not plaka_ham:
        raise HTTPException(
            422,
            "Gövdede plaka alanı bulunamadı (denenen anahtarlar: " + ", ".join(_ARVENTO_PLAKA_ALANLARI) + ")",
        )
    surucu_ham = _arvento_alan_bul(veri, _ARVENTO_SURUCU_ALANLARI)
    if not surucu_ham:
        raise HTTPException(
            422,
            "Gövdede sürücü adı alanı bulunamadı (denenen anahtarlar: " + ", ".join(_ARVENTO_SURUCU_ALANLARI) + ")",
        )

    plaka_no = re.sub(r"[^A-Za-z0-9 ]", "", plaka_ham).strip().upper()
    if not plaka_no:
        raise HTTPException(422, "Plaka alanı geçersiz/boş")
    surucu_adi = surucu_ham[:100]

    kart_no_ham = _arvento_alan_bul(veri, _ARVENTO_KART_ALANLARI)
    kart_no = kart_no_ham[:50] if kart_no_ham else None

    olay_zamani = None
    zaman_ham = _arvento_alan_bul(veri, _ARVENTO_ZAMAN_ALANLARI)
    if zaman_ham:
        try:
            olay_zamani = datetime.fromisoformat(zaman_ham.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            # Ayrıştırılamayan bir zaman damgası SESSİZCE yutulur --
            # eşleştirme zaten alinma_zamani'ya göre sıralanıyor (bkz.
            # models.ArventoSuruculuOlay'ın docstring'i), bu yüzden
            # olay_zamani salt bilgi/denetim amaçlıdır, eşleşme mantığını
            # etkilemez.
            olay_zamani = None

    try:
        ham_veri_json = json.dumps(veri, ensure_ascii=False)[:4000]
    except (TypeError, ValueError):
        ham_veri_json = None

    olay = models.ArventoSuruculuOlay(
        plaka_no=plaka_no,
        surucu_adi=surucu_adi,
        kart_no=kart_no,
        olay_zamani=olay_zamani,
        ham_veri=ham_veri_json,
    )
    db.add(olay)
    db.commit()
    logger.info("Arvento sürücü ataması alındı: plaka=%s, sürücü=%s", plaka_no, surucu_adi)
    return {"durum": "ok", "plaka_no": plaka_no, "surucu_adi": surucu_adi}


_DOGRULAMA_FILTRELERI = ("riskli", "tek_kare", "kararsiz", "duzeltilmis")


def _dogrulama_filtresi_uygula(sorgu, dogrulama: Optional[str]):
    """Kayıtlar ekranındaki "Doğrulama" filtresi (2026-09-25, kullanıcı:
    "kameranın en doğru ve hatasız kayıt alması için ..."). Yanlış okunmuş
    olma ihtimali EN YÜKSEK otomatik kayıtları hızlıca gözden geçirebilmek
    için (bkz. backend/okuma_kalitesi.py'deki ölçütlerin açıklaması):

    * tek_kare    -- plaka yalnızca 1 karede okunup kaydedilmiş
    * kararsiz    -- aynı geçişte plaka farklı karelerde FARKLI okunmuş
    * duzeltilmis -- kayıtlı bir plakaya bakılarak tek karakter düzeltilmiş
    * riskli      -- yukarıdakilerden herhangi biri

    Elle girilen kayıtlar bu filtrelerde hiç görünmez (doğrulanacak bir OCR
    okuması yoktur)."""
    if not dogrulama:
        return sorgu
    K = models.Kayit
    kosullar = {
        "tek_kare": K.dogrulama_kare_sayisi <= 1,
        "kararsiz": K.farkli_okuma_sayisi > 1,
        "duzeltilmis": K.ham_plaka_metni.isnot(None),
    }
    if dogrulama == "riskli":
        kosul = or_(*kosullar.values())
    elif dogrulama in kosullar:
        kosul = kosullar[dogrulama]
    else:
        raise HTTPException(400, f"Geçersiz doğrulama filtresi: {dogrulama!r} (geçerli: {', '.join(_DOGRULAMA_FILTRELERI)})")
    return sorgu.filter(kosul, or_(K.manuel_giris == False, K.manuel_giris.is_(None)))  # noqa: E712


@app.get("/kayitlar", response_model=List[schemas.KayitCevap])
def kayitlari_listele(
    plaka: Optional[str] = None,
    baslangic: Optional[str] = None,
    bitis: Optional[str] = None,
    yetki_durumu: Optional[str] = None,
    kamera_id: Optional[str] = None,
    vardiya_adi: Optional[str] = None,
    yon: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_personel_girisi_gerekli),
    dogrulama: Optional[str] = None,
):
    sorgu = db.query(models.Kayit)
    sorgu = _dogrulama_filtresi_uygula(sorgu, dogrulama)
    if plaka:
        sorgu = sorgu.filter(models.Kayit.plaka_no.ilike(f"%{plaka}%"))
    if yetki_durumu:
        sorgu = sorgu.filter(models.Kayit.yetki_durumu == yetki_durumu)
    if kamera_id:
        sorgu = sorgu.filter(models.Kayit.kamera_id.ilike(f"%{kamera_id}%"))
    # 2026-09-24 kullanıcı geri bildirimi: "Son Geçişler" ekranında GİRİŞ/ÇIKIŞ
    # ızgaraları, TEK bir karma (yön filtresi olmayan) sayfadan istemci
    # tarafında ikiye ayrılıyordu -- bkz. bu parametrenin frontend/app.js
    # ::sonGecislerYukle'deki kullanım notu. Burada eklenen `yon` filtresi,
    # her ızgaranın kendi sayfasını/offsetini bağımsız çekebilmesini sağlar.
    if yon:
        sorgu = sorgu.filter(models.Kayit.yon == yon)
    if baslangic:
        sorgu = sorgu.filter(models.Kayit.tarih_saat >= _iso_tarih_parametresini_coz(baslangic, "baslangic"))
    bitis_siniri = _bitis_tarih_filtresi_sinirini_hesapla(bitis)
    if bitis_siniri is not None:
        sorgu = sorgu.filter(models.Kayit.tarih_saat <= bitis_siniri)
    # bkz. "GÜVENLİK PERSONELİ VARDİYA FİLTRESİ" notu: güvenlik rolü dışındaki
    # kullanıcılar için bu çağrı sorguyu DEĞİŞTİRMEDEN döner.
    #
    # 2026-09-22 KRİTİK HATA DÜZELTMESİ: `vardiya_adi` (aşağıdaki "Vardiya"
    # ekran filtresi) doluysa, buradaki KENDİ vardiya penceresi kısıtlaması
    # ATLANIR (`vardiya_penceresini_atla=True`) -- bkz.
    # _guvenlik_kayit_filtresi_uygula'nın bu parametreye ait docstring'i. Aksi
    # halde bir güvenlik hesabı "Vardiya" filtresinden KENDİ vardiyası
    # DIŞINDA bir vardiya seçtiğinde iki kısıtlama birbirini boşa çıkarıyordu
    # (gerçek üretim raporu: "A" hesabı "D" filtresini seçince "Kayıt
    # bulunamadı" dönüyordu, oysa gerçek bir "D" kaydı vardı).
    normalize_edilmis_vardiya_adi = _vardiya_adi_normalize(vardiya_adi)
    sorgu = _guvenlik_kayit_filtresi_uygula(
        sorgu, kullanici, db, vardiya_penceresini_atla=bool(normalize_edilmis_vardiya_adi),
    )
    # "Vardiya" (A/B/C/D) ekran filtresi (2026-09-21) -- yukarıdaki görünürlük
    # kısıtlamasından BAĞIMSIZ, bkz. _vardiya_adi_filtresi_uygula.
    sorgu = _vardiya_adi_filtresi_uygula(sorgu, normalize_edilmis_vardiya_adi, db)
    # PERFORMANS (2026-09-25): burada eskiden sonucu HİÇ kullanılmayan bir
    # `toplam = sorgu.count()` vardı -- Kayıtlar ekranının her yüklenişinde
    # (ve her Excel/PDF raporunda) filtrelenmiş tabloyu baştan sona sayan
    # gereksiz bir ikinci sorgu. Toplam sayı zaten ayrı `/kayitlar/sayfa-bilgisi`
    # ucundan geliyor.
    # NOT (2026-09-20): `limit`/`offset` artık yukarıdaki `Query(ge=..., le=...)`
    # ile FastAPI/Pydantic seviyesinde doğrulanıyor -- önceden burada
    # `min(limit, 500)` gibi bir "üst sınırı kırp" deseni vardı, ama SQLite
    # (ve bazı motorlar) NEGATİF bir LIMIT değerini "sınırsız" olarak
    # yorumluyor (`min(-1, 500) == -1`); yani `?limit=-1` göndererek 500
    # satırlık üst sınırı tamamen ATLAYIP tüm tabloyu (KVKK kapsamındaki
    # plaka/kişi verileriyle birlikte) tek istekte dökebiliyordunuz -- en
    # düşük yetkili "izleyici" rolü dahil. `Query(ge=1, le=500)` bu değeri
    # isteğin FastAPI'ye ulaştığı ANDA reddeder (422), sorgu hiç kurulmaz.
    kayitlar = sorgu.order_by(desc(models.Kayit.tarih_saat)).offset(offset).limit(limit).all()
    # Ekrandaki "Vardiya" sütunu için her kayda o anki adlandırılmış vardiya
    # adını(nı) ekler (bkz. _kayitlarin_vardiya_adlarini_ekle) -- bu FİLTREden
    # BAĞIMSIZDIR, filtre uygulanmasa (vardiya_adi=None) bile sütun doludur.
    _kayitlarin_vardiya_adlarini_ekle(kayitlar, db)
    _kayitlara_kisi_adini_ekle(kayitlar, db)
    return kayitlar


@app.get("/kayitlar/sayfa-bilgisi")
def kayitlar_sayfa_bilgisi(
    plaka: Optional[str] = None,
    baslangic: Optional[str] = None,
    bitis: Optional[str] = None,
    yetki_durumu: Optional[str] = None,
    kamera_id: Optional[str] = None,
    vardiya_adi: Optional[str] = None,
    yon: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_personel_girisi_gerekli),
    dogrulama: Optional[str] = None,
):
    """Sayfalama için toplam kayıt sayısını döndürür."""
    sorgu = db.query(models.Kayit)
    sorgu = _dogrulama_filtresi_uygula(sorgu, dogrulama)
    if plaka:
        sorgu = sorgu.filter(models.Kayit.plaka_no.ilike(f"%{plaka}%"))
    if yetki_durumu:
        sorgu = sorgu.filter(models.Kayit.yetki_durumu == yetki_durumu)
    if kamera_id:
        sorgu = sorgu.filter(models.Kayit.kamera_id.ilike(f"%{kamera_id}%"))
    # bkz. kayitlari_listele'deki AYNI başlıklı 2026-09-24 notu.
    if yon:
        sorgu = sorgu.filter(models.Kayit.yon == yon)
    if baslangic:
        sorgu = sorgu.filter(models.Kayit.tarih_saat >= _iso_tarih_parametresini_coz(baslangic, "baslangic"))
    bitis_siniri = _bitis_tarih_filtresi_sinirini_hesapla(bitis)
    if bitis_siniri is not None:
        sorgu = sorgu.filter(models.Kayit.tarih_saat <= bitis_siniri)
    # bkz. kayitlari_listele'deki AYNI başlıklı 2026-09-22 notu -- bu uç nokta
    # sayfalama sayacını /kayitlar ile AYNI filtrelerden hesapladığı için,
    # burada da "Vardiya" filtresi verilince kendi vardiya penceresi
    # kısıtlaması atlanmalı, aksi halde sayaç 0 gösterip liste ile
    # tutarsızlaşabilirdi (ya da tam tersi, ama bu düzeltmeden önce ikisi de
    # 0'da tutarlıydı çünkü ikisi de AYNI hatayı taşıyordu).
    normalize_edilmis_vardiya_adi = _vardiya_adi_normalize(vardiya_adi)
    sorgu = _guvenlik_kayit_filtresi_uygula(
        sorgu, kullanici, db, vardiya_penceresini_atla=bool(normalize_edilmis_vardiya_adi),
    )
    sorgu = _vardiya_adi_filtresi_uygula(sorgu, normalize_edilmis_vardiya_adi, db)
    toplam = sorgu.count()
    sayfa_sayisi = max(1, -(-toplam // max(1, limit)))
    return {"toplam": toplam, "sayfa_sayisi": sayfa_sayisi, "limit": limit}


@app.get("/olaylar", response_model=List[schemas.KayitCevap])
def olaylari_getir(
    since_id: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    """Canlı ekran için son olayları veya verilen ID'den sonrasını döndürür."""
    sorgu = db.query(models.Kayit).filter(models.Kayit.id > since_id)
    sorgu = _guvenlik_kayit_filtresi_uygula(sorgu, kullanici, db)
    kayitlar = sorgu.order_by(desc(models.Kayit.id)).limit(limit).all()
    _kayitlarin_vardiya_adlarini_ekle(kayitlar, db)
    _kayitlara_kisi_adini_ekle(kayitlar, db)
    return kayitlar


@app.get("/alarmlar", response_model=List[schemas.AlarmCevap])
def alarmlari_listele(
    sadece_acik: bool = False,
    alarm_tipi: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    sorgu = db.query(models.Alarm)
    if sadece_acik:
        sorgu = sorgu.filter(models.Alarm.okundu == False)  # noqa: E712
    if alarm_tipi:
        sorgu = sorgu.filter(models.Alarm.alarm_tipi == alarm_tipi)
    return sorgu.order_by(desc(models.Alarm.tarih_saat)).limit(limit).all()


@app.patch("/alarmlar/{alarm_id}/okundu", response_model=schemas.AlarmCevap)
def alarmi_okundu_isaretle(alarm_id: int, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    alarm = db.query(models.Alarm).filter(models.Alarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(404, "Alarm bulunamadı")
    alarm.okundu = True
    db.commit()
    db.refresh(alarm)
    return alarm


@app.post("/alarmlar/tumu-okundu")
def tum_alarmlari_okundu_isaretle(db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    guncellenen = db.query(models.Alarm).filter(models.Alarm.okundu == False).update({"okundu": True})  # noqa: E712
    db.commit()
    return {"guncellenen": guncellenen}


@app.delete("/kayitlar/{kayit_id}")
def kayit_sil(kayit_id: int, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI)
    kayit = db.query(models.Kayit).filter(models.Kayit.id == kayit_id).first()
    if not kayit:
        raise HTTPException(404, "Kayıt bulunamadı")
    # Alarm günlüğü korunur; sadece silinecek kayda olan bağlantı koparılır (FK ihlalini önler).
    db.query(models.Alarm).filter(models.Alarm.kayit_id == kayit_id).update({"kayit_id": None})
    db.delete(kayit)
    db.commit()
    return {"mesaj": "Kayıt silindi"}


# "ziyaretci_onayli": bir görevlinin, bir geçişi (ister kamera tespitinden
# ister elle girilmiş olsun) BİLİNÇLİ OLARAK ziyaretçi olarak onaylayıp
# bariyeri açtığı durumları, otomatik sınıflandırılan diğer durumlardan
# ("yetkili" = tanımlı/otomatik onaylı, "yetkisiz"/"kara_liste" = reddedilen,
# "suresi_dolmus" = süresi geçmiş kayıtlı ziyaretçi) ayırt etmek için
# eklendi (bkz. README'deki 2026-09-17 "Ziyaretçi Girişi" notu). Panelde
# ayrı bir rozet/etiketle gösterilir; _rol_dogrula'nın aksine burada
# yetki_durumu bir DB CHECK constraint'i değil, yalnızca bu whitelist ile
# sınırlanan serbest bir string sütun (models.Kayit.yetki_durumu).
_KAYIT_GECERLI_YETKI_DURUMLARI = ("yetkili", "yetkisiz", "suresi_dolmus", "kara_liste", "bilinmiyor", "ziyaretci_onayli")


@app.patch("/kayitlar/{kayit_id}", response_model=schemas.KayitCevap)
def kayit_duzenle(
    kayit_id: int,
    veri: schemas.KayitDuzenle,
    db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    """Mevcut bir geçiş kaydının panelden tam düzenlenmesi -- OCR'ın yanlış
    okuduğu bir plakanın düzeltilmesi, yanlış hesaplanmış yetki durumunun
    elle değiştirilmesi, veya kayda kişi eşleştirmesi/not eklenmesi için.

    GÜVENLİK/DENETİM: bu bir erişim kontrol sistemi olduğundan, kim neyi ne
    zaman değiştirdi HER ZAMAN kayıtta tutulur (duzenleyen/duzenleme_tarihi) --
    bu alanlar panelden ASLA doğrudan set edilemez, yalnızca bu uç nokta
    tarafından otomatik doldurulur."""
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    kayit = db.query(models.Kayit).filter(models.Kayit.id == kayit_id).first()
    if not kayit:
        raise HTTPException(404, "Kayıt bulunamadı")

    degisti = False

    if veri.plaka_no is not None:
        yeni_plaka = re.sub(r"[^A-Za-z0-9 ]", "", veri.plaka_no).strip().upper()
        if not yeni_plaka:
            raise HTTPException(400, "Plaka boş olamaz")
        if yeni_plaka != kayit.plaka_no:
            kayit.plaka_no = yeni_plaka
            degisti = True

    if veri.yon is not None:
        if veri.yon not in ("giris", "cikis"):
            raise HTTPException(400, "yon 'giris' veya 'cikis' olmalı")
        if veri.yon != kayit.yon:
            kayit.yon = veri.yon
            degisti = True

    if veri.yetki_durumu is not None:
        if veri.yetki_durumu not in _KAYIT_GECERLI_YETKI_DURUMLARI:
            raise HTTPException(400, f"yetki_durumu şunlardan biri olmalı: {', '.join(_KAYIT_GECERLI_YETKI_DURUMLARI)}")
        if veri.yetki_durumu != kayit.yetki_durumu:
            kayit.yetki_durumu = veri.yetki_durumu
            degisti = True

    if veri.kisi_id_temizle:
        if kayit.kisi_id is not None or kayit.kisi_tip_anlik is not None:
            kayit.kisi_id = None
            kayit.kisi_tip_anlik = None
            degisti = True
    elif veri.kisi_id is not None:
        kisi = db.query(models.Kisi).filter(models.Kisi.id == veri.kisi_id).first()
        if not kisi:
            raise HTTPException(404, "Eşleştirilecek kişi bulunamadı")
        if kayit.kisi_id != kisi.id:
            kayit.kisi_id = kisi.id
            kayit.kisi_tip_anlik = kisi.tip
            degisti = True

    if veri.not_metni is not None:
        yeni_not = veri.not_metni.strip() or None
        if yeni_not != kayit.not_metni:
            kayit.not_metni = yeni_not
            degisti = True
        # SON KULLANILAN NOT ÖNBELLEĞİ (2026-09-17, devam): Ziyaretçi Girişi
        # akışı da (bkz. app.js::_ziyaretciGirisiKutusunuAyarla) bu uç
        # noktadan (PATCH /kayitlar/{id}) not ekliyor -- bu yüzden öneri
        # önbelleği burada da güncellenir (bkz. modülün üst kısmındaki not).
        if yeni_not:
            _son_not_kaydet(kayit.plaka_no, yeni_not)

    if veri.misafir_adi is not None:
        yeni_misafir_adi = veri.misafir_adi.strip() or None
        if yeni_misafir_adi != kayit.misafir_adi:
            kayit.misafir_adi = yeni_misafir_adi
            degisti = True

    if degisti:
        kayit.duzenleyen = kullanici.kullanici_adi
        kayit.duzenleme_tarihi = datetime.now()
        logger.info("Kayıt #%d panelden düzenlendi (%s)", kayit_id, kullanici.kullanici_adi)
        db.commit()
        db.refresh(kayit)
    # KÖK NEDEN DÜZELTMESİ (2026-09-22 kullanıcı geri bildirimi: "bu ekran
    # şimdi not ve isim ekledim ekranı kapatıp açmadan güncellenmiyor"):
    # bu uç nokta önceden kisi_adi/vardiya_adi'yı HİÇ doldurmadan çıplak
    # `kayit`ı dönüyordu (bu iki alan yalnızca kayitlari_listele/olaylari_getir
    # gibi LİSTE uç noktalarında _kayitlara_kisi_adini_ekle/
    # _kayitlarin_vardiya_adlarini_ekle ile dolduruluyordu). Frontend artık
    # (bkz. app.js::kayitDuzenleForm submit ve _ziyaretciGirisiKutusunuAyarla)
    # bu PATCH yanıtını sonKayitlarCache'e DOĞRUDAN yazıyor -- yanıt eksik
    # gelirse az önce eşleştirilen kişinin adı (kisi_adi) ekranda BİR SONRAKİ
    # tam liste yenilemesine kadar boş görünürdü. Tek bir kayıt için de aynı
    # yardımcılar (liste bekleyen bir parametre olsa da tek elemanlı bir liste
    # ile) çağrılarak yanıt, liste uç noktalarıyla TUTARLI hale getirildi.
    _kayitlarin_vardiya_adlarini_ekle([kayit], db)
    _kayitlara_kisi_adini_ekle([kayit], db)
    return kayit


@app.get("/kayitlar/istatistik")
def istatistikler(db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    bugun = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    # "toplam_kayit" (tüm zamanların toplamı) ve "aktif_kisi_sayisi"/
    # "kara_liste_kayit_sayisi" (Kişi/KaraListesi TANIMLARININ sayısı, birer
    # GEÇİŞ KAYDI değil) bilinçli olarak vardiya filtresinin DIŞINDA
    # tutuluyor -- bkz. modülün üstündeki "GÜVENLİK PERSONELİ VARDİYA
    # FİLTRESİ" notundaki kapsam açıklaması. Yalnızca gerçekten birer geçiş
    # KAYDI sayısı olan alanlar (bugünkü kayıt/yetkisiz deneme/kara liste
    # geçişi) güvenlik rolü için vardiyayla filtrelenir.
    toplam = db.query(models.Kayit).count()
    bugunku = _guvenlik_kayit_filtresi_uygula(
        db.query(models.Kayit).filter(models.Kayit.tarih_saat >= bugun), kullanici, db
    ).count()
    yetkisiz = _guvenlik_kayit_filtresi_uygula(
        db.query(models.Kayit).filter(models.Kayit.yetki_durumu == "yetkisiz"), kullanici, db
    ).count()
    kara_liste_gecis = _guvenlik_kayit_filtresi_uygula(
        db.query(models.Kayit).filter(models.Kayit.yetki_durumu == "kara_liste"), kullanici, db
    ).count()
    toplam_kisi = db.query(models.Kisi).filter(models.Kisi.aktif == True).count()  # noqa: E712
    kara_liste_sayisi = db.query(models.KaraListesi).filter(models.KaraListesi.aktif == True).count()  # noqa: E712
    return {
        "toplam_kayit": toplam,
        "bugunku_kayit": bugunku,
        "yetkisiz_giris_denemesi": yetkisiz,
        "kara_liste_gecis": kara_liste_gecis,
        "aktif_kisi_sayisi": toplam_kisi,
        "kara_liste_kayit_sayisi": kara_liste_sayisi,
    }


@app.get("/kayitlar/grafik")
def grafik_verisi(gun: int = 7, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Son N günlük istatistik — dashboard grafikleri için."""
    baslangic = datetime.now() - timedelta(days=max(1, min(gun, 90)))
    sorgu = _guvenlik_kayit_filtresi_uygula(
        db.query(models.Kayit).filter(models.Kayit.tarih_saat >= baslangic), kullanici, db
    )
    kayitlar = sorgu.all()

    gunluk: dict = {}
    for k in kayitlar:
        gun_str = k.tarih_saat.strftime("%Y-%m-%d")
        e = gunluk.setdefault(gun_str, {"toplam": 0, "yetkili": 0, "yetkisiz": 0, "kara_liste": 0})
        e["toplam"] += 1
        if k.yetki_durumu == "yetkili":
            e["yetkili"] += 1
        elif k.yetki_durumu == "kara_liste":
            e["kara_liste"] += 1
        elif k.yetki_durumu in ("yetkisiz", "suresi_dolmus"):
            e["yetkisiz"] += 1

    yetki_dagilimi = {"yetkili": 0, "yetkisiz": 0, "kara_liste": 0, "suresi_dolmus": 0}
    for k in kayitlar:
        if k.yetki_durumu in yetki_dagilimi:
            yetki_dagilimi[k.yetki_durumu] += 1

    return {"gunluk": gunluk, "yetki_dagilimi": yetki_dagilimi}


@app.get("/kayitlar/son-not")
def son_not_getir(plaka: str, _: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Bir plaka için (varsa) "son kullanılan not" önerisini döner (bkz.
    modülün üst kısmındaki _SON_NOT_ONBELLEGI açıklaması). Panelde
    Ziyaretçi Girişi, Kayıt Düzenle ve Ziyaretçi Bilgileri (panel) not
    kutuları açılırken bu uç nokta çağrılır ki görevli aynı gün aynı plaka
    için notu yeniden yazmak zorunda kalmasın; öneri her zaman DÜZENLENEBİLİR
    kalır ve her gece 23:59'da otomatik olarak sıfırlanır."""
    return {"not_metni": _son_not_oku(plaka)}


@app.get("/kayitlar/analiz/{plaka_no}")
def plaka_analiz(plaka_no: str, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Bir plaka için geçiş geçmişi, kişi bilgisi ve kara liste durumu."""
    hedef = _plaka_normalize(plaka_no)
    # GÜVENLİK/DOĞRULUK KÖK NEDEN DÜZELTMESİ (2026-09-17): bkz.
    # _plaka_yetki_kontrol'deki aynı başlıklı not -- `Kayit.plaka_no` DB'de
    # BOŞLUKLU saklandığı için (bkz. _kayit_olustur_ve_bildir'in kendi
    # temizleme mantığı, schemas.py::plaka_normalize ile BİREBİR AYNI), bu
    # sorgu boşluksuz `hedef` ile karşılaştırıldığında ASLA eşleşmiyordu --
    # "Plaka Analizi" penceresi HER ZAMAN "Toplam Geçiş: 0" gösteriyordu.
    # Görünen plaka biçimi de artık boşluksuz `hedef` yerine, sahadaki
    # kayıtlarla AYNI (boşluklu) biçime sahip `goruntu_plaka` ile dönüyor
    # (ör. "Kara Listeye Ekle" düğmesi artık doğru biçimde plaka gönderir).
    goruntu_plaka = re.sub(r"[^A-Za-z0-9 ]", "", plaka_no).strip().upper() or hedef
    # GÜVENLİK PERSONELİ VARDİYA FİLTRESİ / KAMERA ERİŞİMİ İSTİSNASI
    # (2026-09-21): bu ekran ÖNCEDEN (2026-09-18) diğer KAYIT görünürlüğü
    # ekranlarıyla (bkz. _guvenlik_kayit_filtresi_uygula) AYNI vardiya
    # penceresi filtresine tabiydi -- güvenlik personeli yalnızca KENDİ
    # vardiya penceresinde geçen kayıtları "Plaka Analizi" ile de görebiliyordu.
    # Kullanıcı geri bildirimi (2026-09-21): "A Vardiyasının nöbet saatinde
    # giriş yapan bir aracı, B vardiyası geldiğinde TESPİT edebilmesi
    # gerekiyor" -- yani bir sonraki vardiyanın/noktanın, BELİRLİ bir plakayı
    # arayarak önceki vardiya(lar)ın/noktanın kayıtlarına erişebilmesi
    # gereken, meşru ve BİLİNÇLİ bir ihtiyaç. "Kayıtlar" listesi (bkz.
    # kayitlari_listele) genel BROWSE ekranı olduğu için hem vardiya hem de
    # kamera erişim filtresi ORADA hâlâ uygulanıyor -- ama bu uç nokta (Plaka
    # Analizi) TEK BİR plakayı hedefleyen, kasıtlı bir arama olduğundan artık
    # HER İKİ kısıtlamadan da BAĞIMSIZ olarak tüm geçmişi döner. Böylece
    # güvenlik personeli genel kayıt akışını (diğer vardiyaların/noktaların
    # TÜM trafiğini) gezinemez ama belirli bir aracı sorduğunda tam geçmişini
    # görebilir (kişi/kara liste bilgisi zaten PLAKAYA ait sabit veridir,
    # hiçbir filtreye tabi değildir).
    plaka_kosulu = _plaka_normalize_sql(models.Kayit.plaka_no) == hedef
    kayitlar = (
        db.query(models.Kayit)
        .filter(plaka_kosulu)
        .order_by(desc(models.Kayit.tarih_saat))
        .limit(50).all()
    )
    # DÜZELTME (2026-09-25): "Toplam Geçiş" eskiden `len(kayitlar)` idi --
    # yani yukarıdaki 50 satırlık listeleme sınırıyla kırpılmış sayı; 50'den
    # fazla geçişi olan bir araç için ekran her zaman "50" gösteriyordu.
    toplam_gecis = len(kayitlar) if len(kayitlar) < 50 else db.query(func.count(models.Kayit.id)).filter(plaka_kosulu).scalar()
    # "Vardiya Grupları" (2026-09-21): "plaka arayınca karşısına kimin
    # vardiyasında girip çıktığı gözükebilsin" -- bkz.
    # _kayitlarin_vardiya_adlarini_ekle; bu ekranın vardiya/kamera
    # FİLTRESİNDEN muaf olması (yukarıdaki not) ile bu ETİKETLEME birbirinden
    # BAĞIMSIZDIR -- etiket yalnızca BİLGİLENDİRME amaçlıdır, hiçbir kaydı
    # gizlemez.
    _kayitlarin_vardiya_adlarini_ekle(kayitlar, db)
    _kayitlara_kisi_adini_ekle(kayitlar, db)
    # PERFORMANS (2026-09-25): eskiden TÜM aktif kişiler (toplu içe
    # aktarmayla binlerce olabilir) belleğe yüklenip Python'da tek tek
    # karşılaştırılıyordu; artık eşleşme veritabanında yapılıyor
    # (_plaka_yetki_kontrol ile aynı `_plaka_normalize_sql` kuralı).
    kisi = (
        db.query(models.Kisi)
        .filter(models.Kisi.aktif == True, _plaka_normalize_sql(models.Kisi.plaka_no) == hedef)  # noqa: E712
        .order_by(models.Kisi.id)
        .first()
    )
    if not kisi:
        ek = db.query(models.KisiPlaka).filter(
            _plaka_normalize_sql(models.KisiPlaka.plaka_no) == hedef,
            models.KisiPlaka.aktif == True,  # noqa: E712
        ).first()
        if ek:
            kisi = db.query(models.Kisi).filter(models.Kisi.id == ek.kisi_id).first()
    kara = db.query(models.KaraListesi).filter(
        _plaka_normalize_sql(models.KaraListesi.plaka_no) == hedef,
        models.KaraListesi.aktif == True,  # noqa: E712
    ).first()
    return {
        "plaka_no": goruntu_plaka,
        "toplam_gecis": toplam_gecis,
        "son_gecis": kayitlar[0].tarih_saat.isoformat() if kayitlar else None,
        "kisi": {"id": kisi.id, "ad_soyad": kisi.ad_soyad, "tip": kisi.tip, "telefon": kisi.telefon} if kisi else None,
        "kara_listesinde": kara is not None,
        "kara_sebep": kara.sebep if kara else None,
        # Bu ekrandaki "Manuel Kayıt Ekle" not kutusunu doldurmak için (bkz.
        # _SON_NOT_ONBELLEGI) -- her gece 23:59'da sıfırlanan, kalıcı OLMAYAN
        # bir öneridir.
        "son_not_onerisi": _son_not_oku(goruntu_plaka),
        "son_kayitlar": [
            # NOT: bu alanların tamamı, panelin "Kayıtlar" tablosundaki
            # kayitDuzenleAc()/kayitSil() fonksiyonlarının aynı obje şeklini
            # (sonKayitlarCache girdisiyle birebir) beklemesi nedeniyle
            # burada da eksiksiz veriliyor -- Plaka Analizi ekranından da
            # aynı düzenle/sil akışı tekrar kullanılabilsin diye.
            {"id": k.id, "plaka_no": k.plaka_no, "tarih_saat": k.tarih_saat.isoformat(), "yon": k.yon,
             "yetki_durumu": k.yetki_durumu, "kamera_id": k.kamera_id,
             "goruntu_yolu": k.goruntu_yolu, "guven_skoru": k.guven_skoru,
             "dogrulama_kare_sayisi": k.dogrulama_kare_sayisi, "farkli_okuma_sayisi": k.farkli_okuma_sayisi,
             "not_metni": k.not_metni,
             "misafir_adi": k.misafir_adi,
             # Arvento entegrasyonu (2026-09-23) -- bu dict elle kurulduğu
             # için (yukarıdaki kisi_adi notundaki AYNI kök neden) bu sütunu
             # eklemeyi unutmak, ORM sütunu olmasına rağmen bu ekranda
             # sessizce boş görünmesine yol açardı.
             "surucu_adi": k.surucu_adi,
             # kisi_adi burada da (Kayıtlar tablosundaki gibi) verilmezse
             # bu ekranın "İsim" sütunu -- _kayitlara_kisi_adini_ekle() bu
             # kaydın kendisine kisi_adi'yı eklemiş olsa bile -- HER ZAMAN
             # "-" gösterirdi, çünkü bu dict elle (alan alan) kuruluyor ve
             # ORM nesnesine sonradan eklenen niteliği burada ayrıca elle
             # kopyalamak gerekiyor (bkz. kayitIsimGoster() -- 2026-09-22
             # kullanıcı geri bildirimi: "kişi eşleştirmesi ... seçtim fakat
             # herhangi bir yerde gözükmüyor").
             "kisi_adi": getattr(k, "kisi_adi", None),
             "manuel_giris": k.manuel_giris, "kisi_id": k.kisi_id,
             "duzenleyen": k.duzenleyen,
             "duzenleme_tarihi": k.duzenleme_tarihi.isoformat() if k.duzenleme_tarihi else None,
             "vardiya_adi": k.vardiya_adi}
            for k in kayitlar[:15]
        ],
    }


@app.get("/kayitlar/{kayit_id}", response_model=schemas.KayitCevap)
def kayit_getir(
    kayit_id: int, vardiya_adi: Optional[str] = None, db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    """Tek bir kaydı ID'siyle döner (yalnızca bu kaydı görmeye yetkiliyse).

    2026-09-23 GERÇEK KULLANICI GERİ BİLDİRİMİ ("tüm alarmlar okundu
    işaretle demeden son giriş yapan araçların ekranı açılmıyor"): Panel'deki
    "Son Geçişler" widget'ı yalnızca en son 10 kaydı (bkz. panelYenile)
    `sonKayitlarCache` önbelleğine alıyor. Henüz okundu işaretlenmemiş bir
    ALARM satırına (ör. "Yetkisiz araç") bağlı kayıt, aradan geçen başka
    trafik yüzünden bu "son 10" listesinin dışında kalmışsa, frontend'deki
    olayDetayAc(id) kaydı önbellekte bulamıyor ve (eski davranış) SESSİZCE
    hiçbir şey yapmıyordu -- kullanıcıya tıklamanın hiç işe yaramadığı
    izlenimini veriyordu, "tüm alarmlar okundu işaretle"ye basılıp panel
    yenilenince kayıt tesadüfen tekrar "son 10" içine girdiğinde
    çalışıyormuş GİBİ görünüyordu. Bu uç nokta, önbellekte YOKSA tek kaydı
    doğrudan sunucudan çekebilmek için eklendi (bkz. app.js::olayDetayAc'in
    güncellenmiş sürümü).

    `vardiya_adi` (2026-09-22 düzeltmesindeki AYNI gerekçe, bkz.
    kayit_detay_pdf_indir): Kayıtlar ekranındaki "Vardiya" filtresiyle bu
    kaydı zaten görebilen bir güvenlik kullanıcısının bu uç noktadan da
    403 almaması için."""
    kayit = db.query(models.Kayit).filter(models.Kayit.id == kayit_id).first()
    if not kayit:
        raise HTTPException(404, "Kayıt bulunamadı")
    if not _guvenlik_kayit_gorunur_mu(kayit, kullanici, db, vardiya_adi_filtresi=_vardiya_adi_normalize(vardiya_adi)):
        raise HTTPException(403, "Bu kayıt vardiyanıza ait değil")
    _kayitlarin_vardiya_adlarini_ekle([kayit], db)
    _kayitlara_kisi_adini_ekle([kayit], db)
    return kayit


@app.get("/olaylar/sse")
async def sse_baglantisi(request: Request, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """Server-Sent Events — yeni plaka geçişlerini anlık olarak istemciye iletir."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Bearer token gerekli")
    kullanici_id = _token_coz(authorization[7:].strip())
    # Güvenlik personeli için canlı akışın da vardiya penceresine göre
    # filtrelenebilmesi (bkz. _sse_yayinla) için bağlı istemcinin rolü de
    # tutulur -- token yalnızca ID doğrular, rolü vermez. 2026-09-21: aynı
    # gerekçeyle kamera erişim kısıtlaması ve adlandırılmış vardiya grubu adı
    # (bkz. Kullanici.vardiya_adi) da bağlantı anında hesaplanıp tutuluyor --
    # üçü de yalnızca BU bağlantı açıldığı anki değeri yansıtır; hesap
    # sonradan değişirse istemcinin yeniden bağlanması (sayfa yenilemesi)
    # gerekir. `_kullanicinin_izinli_kamera_adlari` (id DEĞİL, "ad" bazlı)
    # kullanılıyor çünkü burada karşılaştırılacak olan canlı olay payload'ının
    # `kamera_id` alanı da (bkz. _sse_yayinla) gerçek Kayit.kamera_id
    # değeridir -- yani "ad" (bkz. o fonksiyonun docstring'indeki kök neden).
    baglanan = db.query(models.Kullanici).filter(models.Kullanici.id == kullanici_id).first()
    rol = baglanan.rol if baglanan else ROL_IZLEYICI
    izinli_kameralar = _kullanicinin_izinli_kamera_adlari(baglanan) if baglanan else None
    vardiya_adi = baglanan.vardiya_adi if baglanan else None

    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    istemci = {
        "kuyruk": q,
        "kullanici_id": kullanici_id,
        "rol": rol,
        "izinli_kameralar": izinli_kameralar,
        "vardiya_adi": vardiya_adi,
    }
    _sse_istemcileri.append(istemci)

    async def _akis():
        try:
            yield ": bağlandı\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield payload
                except asyncio.TimeoutError:
                    yield ": kalp-atisi\n\n"
        finally:
            try:
                _sse_istemcileri.remove(istemci)
            except ValueError:
                pass

    return StreamingResponse(
        _akis(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ==================================================================
# DIŞA AKTARMA (Excel / PDF)
# ==================================================================

def _rapor_tarih_araligi_metni(baslangic: Optional[str], bitis: Optional[str], kayitlar: list) -> str:
    """"GEÇİŞ RAPORU" başlığının altındaki açıklama cümlesini üretir (bkz.
    kullanıcının paylaştığı referans rapordaki "Bu raporda X - Y tarihleri
    arasındaki geçiş kayıtları listelenmektedir." metni). Kullanıcı bir
    tarih filtresi seçtiyse onu kullanır; seçmediyse dönen kayıtların
    GERÇEK en eski/en yeni tarihlerini gösterir (referanstaki gibi sabit
    bir varsayım -- örn. "son 24 saat" -- UYDURMAZ).

    NOT: `baslangic`/`bitis` burada da `_iso_tarih_parametresini_coz` ile
    ayrıştırılıyor -- pratikte bu fonksiyona ulaşan değerler zaten
    `kayitlari_listele` tarafından (aynı parametrelerle, DAHA ÖNCE) doğrulanmış
    oluyor (dışa aktarma uçları onu doğrudan çağırıyor), ama savunma amaçlı
    bu fonksiyonun kendi başına da güvenli olması tercih edildi.

    2026-09-21: `baslangic`/`bitis` artık bir SAAT de içerebiliyor (bkz.
    _bitis_tarih_filtresi_sinirini_hesapla'daki aynı tarihli kök neden
    notu) -- bu fonksiyon o durumda `%H:%M` içeren bir metin üretir ("...
    21.09.2026 14:00 - 21.09.2026 18:00 tarihleri arasında..."), salt tarih
    filtrelerinde ise eski davranış (gün bazlı, "arasında" ifadesinin
    ima ettiği ÜST SINIRIN bir sonraki güne denk gelmesi) korunur. Üst
    sınır hesaplaması `_bitis_tarih_filtresi_sinirini_hesapla` ile PAYLAŞILIR
    -- burada AYRI bir +1 gün mantığı tekrarlanırsa, dışa aktarılan
    rapordaki "arasında" metni ile sorgunun GERÇEKTEN döndürdüğü kayıt
    kümesi birbirinden sessizce sapabilirdi."""
    if baslangic or bitis:
        baslangic_saatli = bool(baslangic) and "T" in baslangic
        bitis_saatli = bool(bitis) and "T" in bitis
        b1 = (
            _iso_tarih_parametresini_coz(baslangic, "baslangic").strftime(
                "%d.%m.%Y %H:%M" if baslangic_saatli else "%d.%m.%Y"
            )
            if baslangic else "en eski kayıt"
        )
        bitis_siniri = _bitis_tarih_filtresi_sinirini_hesapla(bitis)
        b2 = (
            bitis_siniri.strftime("%d.%m.%Y %H:%M" if bitis_saatli else "%d.%m.%Y")
            if bitis_siniri is not None else "şimdi"
        )
        return f"Bu raporda {b1} - {b2} tarihleri arasındaki geçiş kayıtları listelenmektedir."
    if kayitlar:
        ilk = min(k.tarih_saat for k in kayitlar).strftime("%d.%m.%Y %H:%M")
        son = max(k.tarih_saat for k in kayitlar).strftime("%d.%m.%Y %H:%M")
        return f"Bu raporda {ilk} - {son} tarihleri arasındaki geçiş kayıtları listelenmektedir."
    return "Bu kriterlere uyan hiçbir geçiş kaydı bulunamadı."


def _vardiya_etiketleri_haritasi(kayitlar: list, db: Session) -> dict:
    """`kayitlar` listesindeki HER kayıt için, o kaydın gerçekleştiği anda
    AÇIK olan (giriş <= kayıt VE (çıkış YOK ya da çıkış > kayıt)) TÜM
    güvenlik personeli vardiya oturumlarını bulur ve `kayit.id ->
    "Ad Soyad (HH:MM-HH:MM)[; Ad Soyad2 (...)]"` biçiminde bir metne çevirir
    (aynı anda birden fazla personelin vardiyası açıksa hepsi listelenir --
    bkz. models.VardiyaOturumu'ndaki "devir teslim" notu). Hiçbir oturum
    denk düşmüyorsa değer boş string olur.

    2026-09-20 kullanıcı talebi: "her vardiya için kendi geçiş raporları
    olsun ... raporda bir sütun tanımlansın" -- bkz. README'deki aynı tarihli
    not. TÜM oturumlar (bu tabloda ölçek küçük olduğu için, bkz.
    _kullanicinin_vardiya_pencereleri'ndeki aynı gerekçe) TEK SEFERDE
    çekilip bellekte eşleştirilir; her kayıt için ayrı bir SQL sorgusu
    YAPILMAZ (N+1'den kaçınma, bkz. bu fonksiyonun çağrıldığı yerdeki not)."""
    if not kayitlar:
        return {}
    # PERFORMANS (2026-09-25): bkz. _kayitlarin_vardiya_adlarini_ekle'deki
    # aynı başlıklı not ve backend/vardiya_eslestirme.py.
    zamanlar = [k.tarih_saat for k in kayitlar if k.tarih_saat is not None]
    if not zamanlar:
        return {k.id: "" for k in kayitlar}
    oturumlar = (
        db.query(models.VardiyaOturumu.giris_zamani, models.VardiyaOturumu.cikis_zamani, models.Kullanici.kullanici_adi)
        .join(models.Kullanici, models.VardiyaOturumu.kullanici_id == models.Kullanici.id)
        .filter(
            models.VardiyaOturumu.giris_zamani <= max(zamanlar),
            or_(models.VardiyaOturumu.cikis_zamani.is_(None), models.VardiyaOturumu.cikis_zamani > min(zamanlar)),
        )
        .order_by(models.VardiyaOturumu.id)
        .all()
    )
    etiketli = []
    for giris, cikis, kullanici_adi in oturumlar:
        bitis_metni = cikis.strftime("%H:%M") if cikis else "devam ediyor"
        etiketli.append((giris, cikis, f"{kullanici_adi} ({giris.strftime('%H:%M')}-{bitis_metni})"))
    eslesmeler = kayitlari_oturumlarla_eslestir([(k.id, k.tarih_saat) for k in kayitlar], etiketli)
    return {k.id: "; ".join(eslesmeler.get(k.id, [])) for k in kayitlar}


def _kayitlari_rapor_satirlari(kayitlar: list, db: Session) -> list:
    """Kayıtlar dışa aktarma (Excel/PDF) raporunun her satırını, kişi (ad/
    soyad/tip/daire-departman), erişim noktası/site bilgisiyle ve vardiya
    etiketiyle ZENGİNLEŞTİRİR -- kullanıcının paylaştığı referans "GEÇİŞ
    RAPORU" biçimine (Site/Blok/Daire/Otopark/Nokta/Geçiş Tipi/Araç Tipi
    sütunları) yaklaştırma kararı, bkz. README'deki 2026-09-18 notu. N+1
    sorgudan kaçınmak için kişiler, noktalar ve vardiya oturumları TOPLU
    olarak önceden yüklenir.

    Not: "Blok" ve "Otopark" kavramları bu sistemin veri modelinde YOKTUR
    (Site > Blok > Daire hiyerarşisi ve otopark ataması, 2026-09-17'de
    "Ziyaretçi Girişi" özelliği eklenirken bilinçli olarak kapsam dışı
    bırakılmıştı, bkz. README). Bu sütunlar, referans raporla sütun
    uyumluluğu için yer tutucu olarak eklendi ama HER ZAMAN boş kalır --
    var olmayan bir veri UYDURULMAZ.

    KÖK NEDEN (2026-09-21, "id vs ad" hata sınıfı -- bkz.
    _kullanicinin_izinli_kamera_adlari'nin docstring'indeki aynı kök neden):
    `Nokta.kamera_id` cameras.json'daki kamera "id"siyle doğrulanır (bkz.
    nokta_ekle), ama `Kayit.kamera_id` HER ZAMAN kameranın "ad" alanıyla
    damgalanır (bkz. _pipeline_baslat). Bu fonksiyon eskiden Nokta'ları
    DOĞRUDAN "id" ile anahtarlayıp `k.kamera_id` ("ad") ile arıyordu -- id
    rastgele bir uuid4 olduğu (yani neredeyse HER ZAMAN id != ad olduğu)
    için bu eşleşme HİÇBİR ZAMAN tutmuyordu: bir Nokta/Site tanımlanmış
    olsa BİLE, Excel/PDF dışa aktarımındaki "Nokta" ve "Site" sütunları
    her kurulumda SESSİZCE boş kalıyordu. Artık Nokta'lar "ad" ile
    anahtarlanıyor (_kamera_id_den_ad_haritasi ile çevrilerek).
    """
    kisi_idler = {k.kisi_id for k in kayitlar if k.kisi_id}
    kisiler = {
        kisi.id: kisi
        for kisi in (db.query(models.Kisi).filter(models.Kisi.id.in_(kisi_idler)).all() if kisi_idler else [])
    }
    id_den_ad = _kamera_id_den_ad_haritasi()
    nokta_by_kamera_ad = {}
    for n in db.query(models.Nokta).filter(models.Nokta.kamera_id.isnot(None)).all():
        ad = id_den_ad.get(n.kamera_id)
        if ad:
            nokta_by_kamera_ad[ad] = n
    site_adi_by_id = {s.id: s.ad for s in db.query(models.Site).all()}
    vardiya_etiketi_by_kayit_id = _vardiya_etiketleri_haritasi(kayitlar, db)

    satirlar = []
    for k in kayitlar:
        kisi = kisiler.get(k.kisi_id) if k.kisi_id else None
        nokta = nokta_by_kamera_ad.get(k.kamera_id)
        site_adi = site_adi_by_id.get(nokta.site_id) if nokta else ""

        ad, soyad = "", ""
        if kisi and kisi.ad_soyad and kisi.ad_soyad.strip():
            parcalar = kisi.ad_soyad.strip().rsplit(" ", 1)
            ad, soyad = (parcalar[0], parcalar[1]) if len(parcalar) == 2 else (parcalar[0], "")

        # "Araç Tipi" sınıflandırması -- referans rapordaki aynı sütunun
        # (personel->departman adı, sakin->"Tanımlı", ziyaretçi->"Ziyaretçi",
        # eşleşmeyen->"Tanımsız Araç") bizim veri modelimizdeki karşılığı.
        # "Kara Liste" ise referansta yok, sistemimizin kendi eklediği bir
        # netlik -- bu bilgiyi zaten tuttuğumuz için "Tanımsız Araç" içinde
        # gizlemek yerine ayrıca gösteriyoruz.
        if k.yetki_durumu == "kara_liste":
            arac_tipi = "Kara Liste"
        elif kisi and kisi.tip == "personel":
            arac_tipi = kisi.daire_departman or "Tanımlı"
        elif kisi and kisi.tip == "abone":
            arac_tipi = "Tanımlı"
        elif (kisi and kisi.tip == "ziyaretci") or k.yetki_durumu in ("ziyaretci_onayli", "suresi_dolmus"):
            arac_tipi = "Ziyaretçi"
        else:
            arac_tipi = "Tanımsız Araç"

        if kisi and kisi.tip == "personel":
            daire = "PERSONEL"
        elif kisi:
            daire = kisi.daire_departman or ""
        else:
            daire = ""

        satirlar.append({
            "id": k.id,
            "plaka_no": k.plaka_no,
            "ad": ad,
            "soyad": soyad,
            "site": site_adi or "",
            "blok": "",
            "daire": daire,
            "otopark": "",
            "nokta": (nokta.ad if nokta else None) or k.kamera_id or "",
            "gecis_tipi": "Giriş" if k.yon == "giris" else "Çıkış",
            "arac_tipi": arac_tipi,
            "tarih_saat": k.tarih_saat,
            "notlar": k.not_metni or "",
            "goruntu_yolu": k.goruntu_yolu,
            "vardiya": vardiya_etiketi_by_kayit_id.get(k.id, ""),
        })
    return satirlar


# ==================================================================
# RAPOR ÜRETİMİ: AYRI SÜREÇ + TEK SEFERDE BİR RAPOR (2026-09-25)
# ==================================================================
# Kullanıcı geri bildirimi: "pdf ve excel indirirken sistemde kayıtlarda araç
# arattığımda işlemin yavaş ilerlediğini tespit ettim ... her an çökecekmiş
# gibi yavaş hareket ediyor". KÖK NEDEN: büyük bir PDF raporu (2000 satır +
# her satırda bir görsel) ana PTS sürecinin içinde, saniyelerce (ölçümde
# 1000 satır ~20 sn) Python'un tek çekirdek kilidini (GIL) meşgul eden saf
# Python koduyla (reportlab) üretiliyordu. O sürede AYNI süreçteki her şey --
# diğer kullanıcıların istekleri (Plaka Analizi, Kayıtlar), canlı kamera
# akışları ve plaka tanıma -- sırasını beklemek zorunda kalıyordu. Kullanıcı
# "takıldı" sanıp düğmeye tekrar bastığında İKİNCİ bir rapor da aynı anda
# üretilmeye başlıyor, durum daha da kötüleşiyordu.
#
# Düzeltme:
#   1) Rapor dosyası (PDF/Excel) AYRI bir işletim sistemi sürecinde üretilir
#      -- ana süreç yalnızca sonucu bekler (bekleme GIL'i tutmaz), panel ve
#      kameralar etkilenmez. Ayrı süreç herhangi bir nedenle başlatılamazsa
#      (ör. kısıtlı bir ortam) rapor eskisi gibi süreç içinde üretilir --
#      bu bir iyileştirmedir, raporu asla engellememeli.
#      PTS_RAPOR_AYRI_SURECTE=0 ile kapatılabilir.
#   2) Aynı anda yalnızca BİR büyük rapor üretilir; ikinci bir istek
#      öncekinin bitmesini sırayla bekler (paralel üretim yerine).
#   3) Üretilen dosya indirildikten sonra diskten silinir (eskiden
#      `disa_aktarilanlar/` klasöründe sonsuza dek birikiyordu -- veritabanı
#      yedeklerinin geçici kopyaları dahil).
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from starlette.background import BackgroundTask

_RAPOR_KILIDI = threading.BoundedSemaphore(1)
_RAPOR_BEKLEME_SN = 300
_RAPOR_URETIM_ZAMAN_ASIMI_SN = 900
_rapor_havuzu: Optional[ProcessPoolExecutor] = None
_rapor_havuzu_kilit = threading.Lock()


def _rapor_havuzunu_al() -> Optional[ProcessPoolExecutor]:
    global _rapor_havuzu
    if os.getenv("PTS_RAPOR_AYRI_SURECTE", "1").strip().lower() in ("0", "false", "hayir", "hayır", "no"):
        return None
    with _rapor_havuzu_kilit:
        if _rapor_havuzu is None:
            try:
                # "spawn": Windows'ta zaten tek seçenek; Linux'ta da "fork"
                # yerine bilinçli olarak seçildi -- çok iş parçacıklı (kamera
                # thread'leri, ONNX, logging kilitleri) bir süreçten fork
                # almak, çocukta kilitlenmelere yol açabilir.
                _rapor_havuzu = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
            except Exception as exc:
                logger.warning("Rapor süreci başlatılamadı, raporlar ana süreçte üretilecek: %s", exc)
                return None
        return _rapor_havuzu


def _rapor_havuzunu_sifirla() -> None:
    global _rapor_havuzu
    with _rapor_havuzu_kilit:
        if _rapor_havuzu is not None:
            try:
                _rapor_havuzu.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
        _rapor_havuzu = None


def _raporu_uret(fonksiyon, *args, **kwargs):
    """`fonksiyon(*args, **kwargs)`'ı (modül seviyesinde, içe aktarılabilir
    bir fonksiyon olmalı; argümanlar pickle'lanabilir olmalı) ayrı süreçte
    çalıştırır; süreç havuzu kullanılamazsa süreç içinde çalıştırır."""
    havuz = _rapor_havuzunu_al()
    if havuz is not None:
        try:
            return havuz.submit(fonksiyon, *args, **kwargs).result(timeout=_RAPOR_URETIM_ZAMAN_ASIMI_SN)
        except BrokenProcessPool as exc:
            logger.warning("Rapor süreci beklenmedik şekilde kapandı, rapor ana süreçte üretiliyor: %s", exc)
            _rapor_havuzunu_sifirla()
    return fonksiyon(*args, **kwargs)


class _RaporSirasi:
    """`with _RaporSirasi():` -- aynı anda tek rapor. Sıra
    `_RAPOR_BEKLEME_SN` içinde gelmezse anlaşılır bir 503 döner."""

    def __enter__(self):
        if not _RAPOR_KILIDI.acquire(timeout=_RAPOR_BEKLEME_SN):
            raise HTTPException(503, "Şu anda başka bir rapor hazırlanıyor. Lütfen biraz sonra tekrar deneyin.")
        return self

    def __exit__(self, *a):
        _RAPOR_KILIDI.release()
        return False


def _gecici_rapor_yolu(on_ek: str, uzanti: str) -> str:
    return os.path.join(DISA_AKTAR_KLASORU, f"{on_ek}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.{uzanti}")


def _indirip_sil(dosya_yolu: str, dosya_adi: str, media_type: str) -> FileResponse:
    """Dosyayı indirir ve yanıt gönderildikten SONRA diskten siler."""
    return FileResponse(
        dosya_yolu, filename=dosya_adi, media_type=media_type,
        background=BackgroundTask(_dosyayi_sessizce_sil, dosya_yolu),
    )


def _dosyayi_sessizce_sil(yol: str) -> None:
    try:
        os.remove(yol)
    except OSError:
        pass


def _eski_gecici_raporlari_temizle(saat: int = 24) -> int:
    """`disa_aktarilanlar/` içinde `saat`ten eski dosyaları siler (indirme
    yarıda kesilip arka plan silme görevi çalışamadıysa ya da bu düzeltmeden
    ÖNCE birikmiş dosyalar için)."""
    sinir = time.time() - saat * 3600
    silinen = 0
    try:
        for ad in os.listdir(DISA_AKTAR_KLASORU):
            yol = os.path.join(DISA_AKTAR_KLASORU, ad)
            try:
                if os.path.isfile(yol) and os.path.getmtime(yol) < sinir:
                    os.remove(yol)
                    silinen += 1
            except OSError:
                pass
    except OSError:
        pass
    return silinen


@app.on_event("shutdown")
def _rapor_havuzunu_kapat() -> None:
    _rapor_havuzunu_sifirla()


_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@app.get("/disa-aktar/excel/kayitlar")
def kayitlari_excel_indir(
    plaka: Optional[str] = None, baslangic: Optional[str] = None,
    bitis: Optional[str] = None, vardiya_adi: Optional[str] = None,
    yetki_durumu: Optional[str] = None, dogrulama: Optional[str] = None, db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    # NOT: kayitlari_listele() burada FastAPI'nin DI mekanizması ÜZERİNDEN
    # DEĞİL, doğrudan bir Python fonksiyonu olarak çağrılıyor -- bu yüzden
    # `kullanici` parametresi burada AÇIKÇA geçirilmezse (Depends() varsayılan
    # değeri hiç ÇÖZÜLMEZ) vardiya filtresi sessizce uygulanmaz ve bir güvenlik
    # personeli dışa aktarma raporunda TÜM kayıtları görebilirdi.
    #
    # KÖK NEDEN (2026-09-21, kullanıcının paylaştığı GERÇEK hata izinden
    # bulundu -- önceki iki "düzeltme" turu bu asıl sorunu KAÇIRMIŞTI):
    # AYNI sebepten `offset` de burada AÇIKÇA geçirilmeliydi ama
    # geçirilmiyordu. `kayitlari_listele`'nin imzasındaki
    # `offset: int = Query(0, ge=0)` -- FastAPI bir HTTP isteğini bu
    # fonksiyona yönlendirirken bu `Query(...)` işaretleyicisini TANIYIP
    # gerçek tam sayı değerine ÇÖZER, ama fonksiyon burada olduğu gibi
    # DÜZ bir Python çağrısıyla (routing katmanı hiç devreye girmeden)
    # çağrılırsa, Python parametrenin varsayılan değeri olarak doğrudan bu
    # `Query(...)` NESNESİNİ kullanır -- yani `offset` isim olarak var ama
    # DEĞERİ bir tam sayı DEĞİL, FastAPI'nin kendi `Query` sınıfının bir
    # örneğiydi. Bu, `sorgu...offset(offset)` satırına kadar sessizce
    # ilerleyip SQLAlchemy içinde yakalanmamış bir
    # `TypeError: int() argument must be ... not 'Query'` fırlatıyordu --
    # istek kendisi (kimlik doğrulaması, tarih filtresi, veri, hepsi)
    # tamamen geçerli olsa bile HER Excel/PDF dışa aktarma isteği bu
    # yüzden çöküyordu.
    #
    # DÜZELTME (2026-09-25): `yetki_durumu` eskiden burada her zaman None
    # geçiriliyordu -- ekranda "Yetki Durumu: Yetkisiz" filtresi seçiliyken
    # alınan rapor, filtreyi yok sayıp TÜM kayıtları içeriyordu (ekran ile
    # rapor sessizce farklı). Artık ekrandaki filtre rapora da uygulanıyor.
    with _RaporSirasi():
        kayitlar = kayitlari_listele(
            plaka=plaka, baslangic=baslangic, bitis=bitis, yetki_durumu=yetki_durumu or None,
            kamera_id=None, yon=None, vardiya_adi=vardiya_adi,
            limit=5000, offset=0, db=db, kullanici=kullanici, dogrulama=dogrulama or None,
        )
        satirlar = _kayitlari_rapor_satirlari(kayitlar, db)
        dosya_yolu = _gecici_rapor_yolu("pts_kayitlar", "xlsx")
        _raporu_uret(excel_export.kayitlar_excel_olustur, satirlar, dosya_yolu)
    return _indirip_sil(dosya_yolu, "pts_kayitlari.xlsx", _XLSX_MEDIA)


@app.get("/disa-aktar/pdf/kayitlar")
def kayitlari_pdf_indir(
    plaka: Optional[str] = None, baslangic: Optional[str] = None,
    bitis: Optional[str] = None, vardiya_adi: Optional[str] = None,
    yetki_durumu: Optional[str] = None, dogrulama: Optional[str] = None, db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    # bkz. kayitlari_excel_indir'deki AYNI başlıklı not: `kullanici` VE
    # `offset` burada da AÇIKÇA geçirilmeli (offset eksikliği, gerçek
    # üretim verisiyle raporlanan asıl 500 çökmesinin kök nedeniydi).
    # `yetki_durumu`: bkz. kayitlari_excel_indir'deki 2026-09-25 düzeltmesi.
    with _RaporSirasi():
        kayitlar = kayitlari_listele(
            plaka=plaka, baslangic=baslangic, bitis=bitis, yetki_durumu=yetki_durumu or None,
            kamera_id=None, yon=None, vardiya_adi=vardiya_adi,
            limit=2000, offset=0, db=db, kullanici=kullanici, dogrulama=dogrulama or None,
        )
        satirlar = _kayitlari_rapor_satirlari(kayitlar, db)
        tarih_araligi_metni = _rapor_tarih_araligi_metni(baslangic, bitis, kayitlar)
        dosya_yolu = _gecici_rapor_yolu("pts_kayitlar", "pdf")
        _raporu_uret(pdf_export.kayitlar_pdf_olustur, satirlar, dosya_yolu, tarih_araligi_metni=tarih_araligi_metni)
    return _indirip_sil(dosya_yolu, "pts_kayitlari.pdf", "application/pdf")


@app.get("/disa-aktar/pdf/kayit/{kayit_id}")
def kayit_detay_pdf_indir(
    kayit_id: int, vardiya_adi: Optional[str] = None, db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    """Tek bir kaydı, araç görseliyle birlikte PDF olarak indirir.

    `vardiya_adi` (2026-09-22 düzeltmesi): Kayıtlar ekranındaki "Vardiya"
    filtresiyle (bkz. kayitlari_listele) bu kaydı görüp "PDF indir"e basan
    bir güvenlik kullanıcısı, filtre KENDİ vardiyası DIŞINDA bir vardiyaya
    aitse bu parametre olmadan 403 alırdı -- listede görebildiği bir kaydı
    indiremiyordu (bkz. _guvenlik_kayit_gorunur_mu'nun `vardiya_adi_filtresi`
    parametresinin docstring'i). Frontend, o an ekrandaki "Vardiya" filtre
    değerini buraya da iletir (bkz. app.js::kayitPdfIndir)."""
    kayit = db.query(models.Kayit).filter(models.Kayit.id == kayit_id).first()
    if not kayit:
        raise HTTPException(404, "Kayıt bulunamadı")
    if not _guvenlik_kayit_gorunur_mu(kayit, kullanici, db, vardiya_adi_filtresi=_vardiya_adi_normalize(vardiya_adi)):
        raise HTTPException(403, "Bu kayıt vardiyanıza ait değil")
    # Benzersiz geçici ad: iki kullanıcı aynı kaydı aynı anda indirirse biri
    # diğerinin yarım yazılmış dosyasını almasın; indirildikten sonra silinir.
    dosya_yolu = _gecici_rapor_yolu(f"kayit_{kayit_id}", "pdf")
    pdf_export.kayit_detay_pdf_olustur(kayit, dosya_yolu)
    return _indirip_sil(dosya_yolu, f"kayit_{kayit_id}.pdf", "application/pdf")


@app.get("/disa-aktar/excel/kisiler")
def kisileri_excel_indir(
    tip: Optional[str] = None, db: Session = Depends(get_db),
    _: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    kisiler = kisileri_listele(tip=tip, aktif=None, arama=None, db=db)
    dosya_yolu = _gecici_rapor_yolu("pts_kisiler", "xlsx")
    excel_export.kisiler_excel_olustur(kisiler, dosya_yolu)
    return _indirip_sil(dosya_yolu, "pts_kisiler.xlsx", _XLSX_MEDIA)


# ==================================================================
# LED PANEL AYARLARI
# ==================================================================

@app.get("/led/ayarlar")
def led_ayarlarini_getir(_: models.Kullanici = Depends(_personel_girisi_gerekli)):
    return led_panel.ayarlari_oku()


@app.put("/led/ayarlar")
def led_ayarlarini_guncelle(ayarlar: dict, kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    mevcut = led_panel.ayarlari_oku()
    mevcut.update(ayarlar)
    led_panel.ayarlari_kaydet(mevcut)
    return mevcut


@app.post("/led/test")
def led_test_mesaji(mesaj: str = Query("PTS SİSTEMİ TEST MESAJI"), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    basarili = led_panel.led_mesaj_gonder(mesaj)
    return {"basarili": basarili, "mesaj": mesaj}


@app.get("/led/durum")
def led_durumu_getir(db: Session = Depends(get_db), _: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """DÜZELTME (2026-09-25, sistem taraması): `LedMesaj` tablosuna her LED
    gönderiminde (kayıt bildirimi veya /led/test) bir satır düşülüyordu
    (bkz. yukarıdaki kayıt bildirim akışı), ama bunu geri okuyan HİÇBİR uç
    nokta yoktu -- yani panel kablosu çıkıp/IP'ye ulaşılamayıp HER gönderim
    sessizce başarısız olmaya başlasa bile, arayüzde bunu gösterecek hiçbir
    yer yoktu; tek yol sunucunun kendi log dosyasına elle bakmaktı. Bu uç
    nokta, panelin "LED Ayarları" ekranında son gönderimleri ve varsa en
    son başarısız gönderimi gösterebilmesi için döner."""
    son_mesajlar = (
        db.query(models.LedMesaj)
        .order_by(models.LedMesaj.tarih_saat.desc())
        .limit(20)
        .all()
    )
    son_basarisiz = next((m for m in son_mesajlar if not m.basarili), None)
    return {
        "son_mesajlar": [
            {"id": m.id, "mesaj": m.mesaj, "tarih_saat": m.tarih_saat.isoformat(), "basarili": m.basarili}
            for m in son_mesajlar
        ],
        "son_basarisiz_gonderim": (
            {"id": son_basarisiz.id, "mesaj": son_basarisiz.mesaj, "tarih_saat": son_basarisiz.tarih_saat.isoformat()}
            if son_basarisiz else None
        ),
    }


# ==================================================================
# KULLANICI YÖNETİMİ
# ==================================================================

@app.get("/kullanicilar", response_model=List[schemas.KullaniciCevap])
def kullanicilari_listele(db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI)
    return db.query(models.Kullanici).order_by(models.Kullanici.olusturma_tarihi).all()


@app.post("/kullanicilar", response_model=schemas.KullaniciCevap)
def kullanici_ekle(istek: schemas.KullaniciOlustur, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI)
    if db.query(models.Kullanici).filter(models.Kullanici.kullanici_adi == istek.kullanici_adi).first():
        raise HTTPException(409, "Bu kullanıcı adı zaten kullanımda")
    kisi_id = _sakin_kisi_id_dogrula(db, istek.rol, istek.kisi_id)
    # "Nizamiye Bazlı Kamera Erişimi" (2026-09-21): None = kısıtlama yok
    # (varsayılan, geriye dönük uyumlu); bir liste (BOŞ liste dahil)
    # gönderilirse hesap SADECE o kamera id'lerini görebilir -- geçersiz bir
    # id sessizce kaydedilmesin diye önce doğrulanır (bkz.
    # _kamera_id_listesini_dogrula).
    kamera_listesi = (
        _kamera_id_listesini_dogrula(istek.kamera_erisim_listesi)
        if istek.kamera_erisim_listesi is not None else None
    )
    yeni = models.Kullanici(
        kullanici_adi=istek.kullanici_adi.strip(),
        parola_hash=_parola_hashle(istek.parola),
        rol=istek.rol,
        kisi_id=kisi_id,
        kamera_erisim_listesi=json.dumps(kamera_listesi) if kamera_listesi is not None else None,
        # "Vardiya Grupları" (2026-09-21) -- bkz. _vardiya_adi_normalize ve
        # models.Kullanici.vardiya_adi'nin docstring'i.
        vardiya_adi=_vardiya_adi_normalize(istek.vardiya_adi),
    )
    db.add(yeni)
    db.commit()
    db.refresh(yeni)
    _denetim_kaydet(db, kullanici.kullanici_adi, "kullanici_olustur", f"{yeni.kullanici_adi} (rol: {yeni.rol})")
    return yeni


def _sakin_kisi_id_dogrula(db: Session, rol: str, kisi_id: Optional[int]) -> Optional[int]:
    """`rol="sakin"` için `kisi_id` ZORUNLUDUR ve var olan bir Kişi kaydını
    göstermelidir; diğer roller için `kisi_id` her zaman yok sayılır (None
    döner) -- bir "sakin" hesabının kime bağlı olduğu belirsiz kalamaz, ve
    yönetici/operatör/izleyici hesaplarında bu alanın anlamı yoktur."""
    if rol != ROL_SAKIN:
        return None
    if kisi_id is None:
        raise HTTPException(400, "'sakin' rolü için kisi_id zorunludur")
    if not db.query(models.Kisi).filter(models.Kisi.id == kisi_id).first():
        raise HTTPException(404, "Bağlanacak kişi bulunamadı")
    return kisi_id


@app.put("/kullanicilar/{kullanici_id}", response_model=schemas.KullaniciCevap)
def kullanici_guncelle(kullanici_id: int, istek: schemas.KullaniciGuncelle, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI)
    hedef = db.query(models.Kullanici).filter(models.Kullanici.id == kullanici_id).first()
    if not hedef:
        raise HTTPException(404, "Kullanıcı bulunamadı")
    onceki_rol, onceki_aktif = hedef.rol, hedef.aktif
    degisiklikler = []
    if istek.rol is not None:
        # Rol "sakin"e değişiyorsa (ya da zaten "sakin" olup kisi_id
        # gönderilmişse) bağlantı yeniden doğrulanır; "sakin"den başka bir
        # role geçiliyorsa eski kisi_id artık anlamsız olduğu için temizlenir.
        yeni_kisi_id = _sakin_kisi_id_dogrula(
            db, istek.rol, istek.kisi_id if istek.kisi_id is not None else hedef.kisi_id
        )
        hedef.rol = istek.rol
        hedef.kisi_id = yeni_kisi_id
        if istek.rol != onceki_rol:
            degisiklikler.append(f"rol: {onceki_rol} -> {istek.rol}")
    elif istek.kisi_id is not None and hedef.rol == ROL_SAKIN:
        hedef.kisi_id = _sakin_kisi_id_dogrula(db, ROL_SAKIN, istek.kisi_id)
    if istek.aktif is not None:
        if hedef.id == kullanici.id:
            raise HTTPException(400, "Kendinizi pasif yapamazsınız")
        hedef.aktif = istek.aktif
        if istek.aktif != onceki_aktif:
            degisiklikler.append(f"aktif: {onceki_aktif} -> {istek.aktif}")
    if istek.parola:
        hedef.parola_hash = _parola_hashle(istek.parola)
        degisiklikler.append("parola sıfırlandı")  # asla parolanın kendisini loglama
    # "Nizamiye Bazlı Kamera Erişimi" (2026-09-21) -- bkz. modelin docstring'i.
    # `kamera_erisimi_temizle=true` KASITLI OLARAK diğer alanların "None =
    # değiştirme" kuralının DIŞINDA: kısıtlamayı tamamen kaldırıp hesabı
    # yeniden "tüm kameralar" durumuna getirmenin TEK yolu budur (bkz.
    # kamera_roi_guncelle'deki aynı "temizle" deseni). `kamera_erisim_listesi`
    # gönderilirse (BOŞ liste dahil) kısıtlama TAM OLARAK o listeye ayarlanır.
    if istek.kamera_erisimi_temizle:
        if hedef.kamera_erisim_listesi is not None:
            hedef.kamera_erisim_listesi = None
            degisiklikler.append("kamera erişimi: kısıtlama kaldırıldı (tüm kameralar)")
    elif istek.kamera_erisim_listesi is not None:
        kamera_listesi = _kamera_id_listesini_dogrula(istek.kamera_erisim_listesi)
        hedef.kamera_erisim_listesi = json.dumps(kamera_listesi)
        degisiklikler.append(f"kamera erişimi: {len(kamera_listesi)} kameraya kısıtlandı")
    # "Vardiya Grupları" (2026-09-21) -- bkz. schemas.KullaniciGuncelle.vardiya_adi
    # docstring'i: None = değiştirme; normalize sonrası boş string = kaldır;
    # normalize sonrası dolu = ata/değiştir.
    if istek.vardiya_adi is not None:
        yeni_vardiya_adi = _vardiya_adi_normalize(istek.vardiya_adi)
        if yeni_vardiya_adi != hedef.vardiya_adi:
            degisiklikler.append(f"vardiya adı: {hedef.vardiya_adi or '(yok)'} -> {yeni_vardiya_adi or '(yok)'}")
            hedef.vardiya_adi = yeni_vardiya_adi
    db.commit()
    db.refresh(hedef)
    # 2026-09-20: bu uç nokta (rol değişikliği, hesap aktif/pasif yapma,
    # parola sıfırlama gibi HASSAS işlemler) önceden HİÇBİR YERE
    # loglanmıyordu -- "kim ne zaman kimin rolünü değiştirdi" sorusunun
    # cevabı yoktu. Değişiklik yoksa (boş bir PUT) log spam'i olmasın diye
    # yalnızca gerçek bir değişiklik olduğunda yazılıyor.
    if degisiklikler:
        _denetim_kaydet(db, kullanici.kullanici_adi, "kullanici_guncelle", f"{hedef.kullanici_adi}: {', '.join(degisiklikler)}")
    return hedef


@app.delete("/kullanicilar/{kullanici_id}")
def kullanici_sil(kullanici_id: int, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI)
    hedef = db.query(models.Kullanici).filter(models.Kullanici.id == kullanici_id).first()
    if not hedef:
        raise HTTPException(404, "Kullanıcı bulunamadı")
    if hedef.id == kullanici.id:
        raise HTTPException(400, "Kendi hesabınızı silemezsiniz")
    silinen_kullanici_adi, silinen_rol = hedef.kullanici_adi, hedef.rol
    db.delete(hedef)
    db.commit()
    # 2026-09-20: bir hesabın silinmesi önceden hiçbir yere loglanmıyordu --
    # kim, hangi hesabı, ne zaman sildi sorusu tamamen cevapsızdı.
    _denetim_kaydet(db, kullanici.kullanici_adi, "kullanici_sil", f"{silinen_kullanici_adi} (rol: {silinen_rol})")
    return {"mesaj": "Kullanıcı silindi"}


# ==================================================================
# ÖZ-HİZMET VARDİYA OTURUMLARI (2026-09-20) -- bkz. "GÜVENLİK PERSONELİ
# VARDİYA FİLTRESİ" notu (modülün üst kısmı) ve models.VardiyaOturumu.
# Önceki elle/gün-bazlı "Vardiya Planlaması" (models.VardiyaAtamasi, bu
# bölümün eski hâli) bununla DEĞİŞTİRİLDİ -- kullanıcı geri bildirimi:
# yönetici artık her personel için her günü elle girmek ZORUNDA kalmasın,
# personel giriş yapınca vardiyası kendiliğinden başlasın, çıkış yapana
# kadar sürsün (bkz. giris_yap::_guvenlik_oturum_baslat, cikis_yap).
# ==================================================================
# Oturumlar YALNIZCA giriş/çıkışla otomatik açılıp kapanır -- yönetici için
# burada elle "oluştur" uç noktası YOK; yalnızca izleme (listele) ve, açık
# kalmış bir oturumu (ör. personel çıkış yapmadan cihazını kaybetti/
# değiştirdi) elle sonlandırma imkânı var.

@app.get("/vardiya-oturumlari", response_model=List[schemas.VardiyaOturumuCevap])
def vardiya_oturumlarini_listele(
    kullanici_id: Optional[int] = None,
    db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    _rol_dogrula(kullanici, ROL_YONETICI)
    sorgu = db.query(models.VardiyaOturumu)
    if kullanici_id is not None:
        sorgu = sorgu.filter(models.VardiyaOturumu.kullanici_id == kullanici_id)
    return sorgu.order_by(desc(models.VardiyaOturumu.giris_zamani)).limit(500).all()


@app.post("/vardiya-oturumlari/{oturum_id}/sonlandir")
def vardiya_oturumunu_sonlandir(
    oturum_id: int,
    db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    """Yönetici, açık kalmış (ör. personel çıkış yapmayı unuttu) bir vardiya
    oturumunu elle sonlandırabilir -- personelin bir dahaki girişinde ZATEN
    otomatik kapanacağı için (bkz. _guvenlik_oturum_baslat) bu yalnızca "o
    kişi bugün artık giriş yapmayacak ama kayıtlar listesinde şu ana kadarki
    vardiyası kapalı görünsün" gibi durumlar için bir KOLAYLIKTIR."""
    _rol_dogrula(kullanici, ROL_YONETICI)
    hedef = db.query(models.VardiyaOturumu).filter(models.VardiyaOturumu.id == oturum_id).first()
    if not hedef:
        raise HTTPException(404, "Vardiya oturumu bulunamadı")
    if hedef.cikis_zamani is not None:
        raise HTTPException(400, "Bu oturum zaten kapatılmış")
    hedef.cikis_zamani = datetime.now()
    db.commit()
    return {"mesaj": "Vardiya oturumu sonlandırıldı"}


@app.get("/vardiya-oturumlari/durumum")
def vardiya_oturumu_durumum(db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Çağıran kullanıcının KENDİ vardiya oturumlarını ve şu anki (SUNUCUNUN
    kendi saatine göre -- `datetime.now()`) açık/kapalı durumunu döner.

    NEDEN GEREKLİ (2026-09-18 kullanıcı geri bildirimi, önceki elle-atama
    sistemi için yazılmıştı, aynı gerekçe öz-hizmet sistemi için de geçerli):
    filtre tamamen SUNUCU TARAFINDA çalıştığı için, sunucunun sistem saatinin
    (Windows makinesi) yönetici panelini kullanan kişinin bildiği saatten
    FARKLI olması ihtimaline karşı, bunu TEŞHİS ETMENİN bir yolu olmalı.
    `sunucu_simdiki_zaman` alanı tam olarak bunu sağlar. Frontend'de Kayıtlar
    sekmesindeki banner (bkz. app.js) bu veriyi gösterir.

    Güvenlik dışı roller için de zararsız bir yanıt döner (yalnızca
    `rol_guvenlik_mi: false`) -- bu uç nokta rol kontrolü yapmaz, çünkü
    yalnızca ÇAĞIRANIN KENDİ verisini döner.

    "Vardiya Grupları" (2026-09-21): `kullanici.vardiya_adi` DOLU ise
    (bkz. _kullanicinin_vardiya_pencereleri'ndeki AYNI gerekçe), gerçek kayıt
    görünürlüğü artık yalnızca BU hesabın DEĞİL, AYNI vardiya adını paylaşan
    TÜM hesapların oturumlarına dayandığı için, bu teşhis uç noktası da GRUP
    genelindeki oturumları döner -- aksi halde banner "şu an aktif vardiyanız
    yok" derken, aslında AYNI grup içindeki BAŞKA bir hesap (ör. diğer
    noktadaki) o an giriş yapmış olabilir ve kayıtlar zaten görünür olurdu;
    bu YANILTICI teşhis mesajı olurdu.
    """
    simdi = datetime.now()
    if kullanici.rol != ROL_GUVENLIK:
        return {"rol_guvenlik_mi": False, "sunucu_simdiki_zaman": simdi.isoformat()}
    if kullanici.vardiya_adi:
        oturumlar = (
            db.query(models.VardiyaOturumu)
            .join(models.Kullanici, models.VardiyaOturumu.kullanici_id == models.Kullanici.id)
            .filter(models.Kullanici.vardiya_adi == kullanici.vardiya_adi)
            .order_by(desc(models.VardiyaOturumu.giris_zamani))
            .limit(30)
            .all()
        )
    else:
        oturumlar = (
            db.query(models.VardiyaOturumu)
            .filter(models.VardiyaOturumu.kullanici_id == kullanici.id)
            .order_by(desc(models.VardiyaOturumu.giris_zamani))
            .limit(30)
            .all()
        )
    su_an_aktif = any(o.cikis_zamani is None for o in oturumlar)
    liste = [{
        "id": o.id,
        "giris_zamani": o.giris_zamani.isoformat(),
        "cikis_zamani": o.cikis_zamani.isoformat() if o.cikis_zamani else None,
        "devam_ediyor": o.cikis_zamani is None,
    } for o in oturumlar]
    return {
        "rol_guvenlik_mi": True,
        "sunucu_simdiki_zaman": simdi.isoformat(),
        "vardiya_adi": kullanici.vardiya_adi,
        "su_an_aktif_vardiya_var_mi": su_an_aktif,
        "toplam_oturum_sayisi": len(oturumlar),
        "oturumlar": liste,
    }


# ==================================================================
# SAKİN ÖZ-HİZMET PORTALI (2026-09-17)
# ==================================================================
# "sakin" rolündeki bir hesap, bir Kişi (site sakini) kaydına bağlıdır (bkz.
# models.Kullanici.kisi_id) ve panel PERSONELİ değildir -- yalnızca burada
# tanımlanan uçlara erişebilir (bkz. _personel_girisi_gerekli, ki tüm dahili/
# genel amaçlı uçları bu rolden korur). Amaç: bir sakinin kendi plaka(lar)ını
# ve kendi giriş/çıkış geçmişini görebilmesi, gerekirse kendi ek aracını
# eklemesi -- başka hiçbir kişinin, kameranın veya sistem verisinin GÖRÜLMESİ
# MÜMKÜN OLMAMALI. Bu yüzden hiçbir uç noktada kaynak kimliği (kisi_id) istek
# gövdesinden/parametresinden alınmaz; her zaman `kullanici.kisi_id` (JWT'den
# çözülen, DB'de doğrulanan oturum sahibi) kullanılır.

def _sakin_girisi_gerekli(kullanici: models.Kullanici = Depends(_giris_gerekli)) -> models.Kullanici:
    """Yalnızca 'sakin' rolündeki hesaplara izin verir (bkz.
    _personel_girisi_gerekli'nin tam tersi kısıtlaması)."""
    if kullanici.rol != ROL_SAKIN:
        raise HTTPException(403, "Bu işlem yalnızca sakin hesapları için geçerli")
    return kullanici


def _sakin_kisisini_al(db: Session, kullanici: models.Kullanici) -> models.Kisi:
    """Oturumdaki sakin hesabının bağlı olduğu Kişi kaydını döner; hesap henüz
    bağlanmamışsa ya da bağlı olduğu kişi silinmişse (bkz. main.py::kisi_sil)
    açık bir hata verir -- sessizce boş veri dönmek, sakinin "hesabım bozuk
    mu" diye anlamasını zorlaştırırdı."""
    if not kullanici.kisi_id:
        raise HTTPException(400, "Bu hesap henüz bir sakin kaydına bağlanmamış. Yöneticinizle iletişime geçin.")
    kisi = db.query(models.Kisi).filter(models.Kisi.id == kullanici.kisi_id).first()
    if not kisi:
        raise HTTPException(404, "Bağlı sakin kaydı bulunamadı. Yöneticinizle iletişime geçin.")
    return kisi


@app.get("/sakin/profilim", response_model=schemas.KisiCevap)
def sakin_profilim(db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_sakin_girisi_gerekli)):
    """Sakinin kendi Kişi kaydını (ad/soyad, ana plaka, daire/departman,
    aktiflik, erişim pencereleri) ve ek plakalarını döner."""
    return _sakin_kisisini_al(db, kullanici)


@app.post("/sakin/arac-ekle", response_model=schemas.KisiPlakaCevap)
def sakin_arac_ekle(istek: schemas.KisiPlakaOlustur, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_sakin_girisi_gerekli)):
    """Sakinin kendi hesabına EK bir araç plakası eklemesi (bkz.
    models.KisiPlaka) -- ana plaka (Kişi.plaka_no) yönetici/operatör
    tarafından belirlendiği için burada değiştirilemez, yalnızca ek plaka
    eklenebilir."""
    kisi = _sakin_kisisini_al(db, kullanici)
    yeni = models.KisiPlaka(kisi_id=kisi.id, plaka_no=istek.plaka_no, aciklama=istek.aciklama)
    db.add(yeni)
    db.commit()
    db.refresh(yeni)
    logger.info("Sakin kendi hesabına araç ekledi: kişi=%s plaka=%s", kisi.id, yeni.plaka_no)
    return yeni


@app.delete("/sakin/arac/{plaka_id}")
def sakin_arac_sil(plaka_id: int, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_sakin_girisi_gerekli)):
    """Sakinin kendi eklediği bir ek plakayı kaldırması. Sorgu kasıtlı olarak
    hem `id` hem `kisi_id == kullanici.kisi_id` ile filtrelenir -- aksi halde
    bir sakin, başka bir kişiye ait plaka_id'yi tahmin ederek onu silebilirdi
    (IDOR)."""
    kisi = _sakin_kisisini_al(db, kullanici)
    kayit = db.query(models.KisiPlaka).filter(models.KisiPlaka.id == plaka_id, models.KisiPlaka.kisi_id == kisi.id).first()
    if not kayit:
        raise HTTPException(404, "Plaka kaydı bulunamadı")
    db.delete(kayit)
    db.commit()
    return {"mesaj": "Plaka silindi"}


@app.get("/sakin/gecmisim", response_model=List[schemas.KayitCevap])
def sakin_gecmisim(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_sakin_girisi_gerekli),
):
    """Sakinin KENDİ plakalarına ait geçiş kayıtları -- sorgu her zaman
    `kisi_id == kullanici.kisi_id` ile sınırlanır, hiçbir filtre parametresi
    bu sınırı genişletemez (bkz. dosya başındaki güvenlik notu)."""
    kisi = _sakin_kisisini_al(db, kullanici)
    sorgu = db.query(models.Kayit).filter(models.Kayit.kisi_id == kisi.id)
    return sorgu.order_by(desc(models.Kayit.tarih_saat)).offset(offset).limit(limit).all()


@app.get("/sakin/goruntu/{kayit_id}")
def sakin_goruntu(kayit_id: int, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_sakin_girisi_gerekli)):
    """Sakinin kendi bir geçiş kaydının fotoğrafını görebilmesi. Genel
    `/goruntuler/{dosya_adi}` ucunun aksine dosya adı istekten ALINMAZ --
    yalnızca `kayit_id` alınır ve o kaydın gerçekten bu sakine ait olduğu
    (`kisi_id == kullanici.kisi_id`) DB'de doğrulanıp goruntu_yolu oradan
    okunur; böylece bir sakin başka bir dosya adı tahmin ederek başka bir
    sakinin fotoğrafını göremez (IDOR)."""
    kisi = _sakin_kisisini_al(db, kullanici)
    kayit = db.query(models.Kayit).filter(models.Kayit.id == kayit_id, models.Kayit.kisi_id == kisi.id).first()
    if not kayit or not kayit.goruntu_yolu:
        raise HTTPException(404, "Görsel bulunamadı")
    if not os.path.isfile(kayit.goruntu_yolu):
        raise HTTPException(404, "Görsel bulunamadı")
    return FileResponse(kayit.goruntu_yolu, media_type="image/jpeg")


# ==================================================================
# BARİYER KONTROLÜ
# ==================================================================

@app.get("/bariyer/ayarlar")
def bariyer_ayarlarini_getir(db: Session = Depends(get_db), _: models.Kullanici = Depends(_personel_girisi_gerekli)):
    return db.query(models.BariyerAyarlari).all()


@app.post("/bariyer/ayarlar")
def bariyer_ekle(istek: dict = Body(...), db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """DÜZELTME (2026-09-25, sistem taraması): bu uç nokta önceden isteğin
    `auto_ac` alanını TAMAMEN GÖZ ARDI EDİYORDU -- yeni bir bariyer her zaman
    modelin varsayılanıyla (`auto_ac=False`) oluşturuluyordu. Frontend ise
    (frontend/app.js::bariyerForm) panelde bir "Otomatik Aç" onay kutusu
    gösterip bu değeri isteğe ekliyordu -- yani bir yönetici bu kutuyu
    işaretleyip kaydetse bile, panelin en güvenlik-kritik özelliklerinden
    biri (yetkili araç girişinde bariyerin OTOMATİK açılması) SESSİZCE hiçbir
    zaman devreye girmiyordu; hiçbir hata/uyarı da gösterilmiyordu. Şimdi bu
    alan da okunuyor."""
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    yeni = models.BariyerAyarlari(
        ad=str(istek.get("ad", "Bariyer")).strip()[:80],
        mod=str(istek.get("mod", "simulate")),
        http_url=istek.get("http_url"),
        http_metot=str(istek.get("http_metot", "GET")),
        http_govde=istek.get("http_govde"),
        gpio_pin=istek.get("gpio_pin"),
        auto_ac=bool(istek.get("auto_ac", False)),
    )
    db.add(yeni)
    db.commit()
    db.refresh(yeni)
    return yeni


@app.patch("/bariyer/ayarlar/{bariyer_id}")
def bariyer_guncelle(bariyer_id: int, veri: schemas.BariyerAyarlariGuncelle, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """DÜZELTME (2026-09-25, sistem taraması): önceden bir bariyerin ayarlarını
    (ör. yanlış girilmiş bir http_url'i düzeltmek, ya da "auto_ac"ı sonradan
    açmak) değiştirmenin TEK yolu bariyeri SİLİP YENİDEN EKLEMEKTİ -- ama bir
    bariyer silindiğinde, ona atanmış her `Nokta.bariyer_id` referansı kırılır
    (bkz. nokta_ekle/nokta_guncelle'nin bariyer_id doğrulaması) ve yeni
    bariyer farklı bir id ile oluşturulduğu için o noktalar yeniden elle
    bariyere bağlanmalıydı. Bu, kamera_yon_degistir/kamera_ad_degistir'in
    üstündeki AYNI "sil-yeniden-ekle yerine tek alanı değiştir" gerekçesiyle
    eklendi. Yalnızca istekte GÖNDERİLEN (None olmayan) alanlar güncellenir."""
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    bariyer = db.query(models.BariyerAyarlari).filter(models.BariyerAyarlari.id == bariyer_id).first()
    if not bariyer:
        raise HTTPException(404, "Bariyer bulunamadı")
    guncellemeler = veri.model_dump(exclude_unset=True, exclude_none=True)
    if not guncellemeler:
        return bariyer
    for alan, deger in guncellemeler.items():
        if alan == "ad":
            deger = str(deger).strip()[:80]
        setattr(bariyer, alan, deger)
    db.commit()
    db.refresh(bariyer)
    # Bariyerin otomatik açılıp açılmayacağını ya da nasıl açılacağını
    # (mod/http_url) değiştiren bir ayar -- kim, ne zaman değiştirdi sessiz
    # kalmasın (bkz. kamera_ad_degistir/kamera_sil'deki aynı denetim ilkesi).
    _denetim_kaydet(
        db, kullanici.kullanici_adi, "bariyer_ayarlari_guncelle",
        f"bariyer_id={bariyer_id}, ad={bariyer.ad!r}, degisen_alanlar={sorted(guncellemeler.keys())}",
    )
    return bariyer


@app.post("/bariyer/{bariyer_id}/ac")
def bariyer_ac(bariyer_id: int, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    bariyer = db.query(models.BariyerAyarlari).filter(models.BariyerAyarlari.id == bariyer_id, models.BariyerAyarlari.aktif == True).first()  # noqa: E712
    if not bariyer:
        raise HTTPException(404, "Bariyer bulunamadı")

    # 2026-09-25 (sistem taraması): elle bariyer açma, bir nizamiye sisteminde
    # en hassas işlemlerden biri (yetkisiz bir aracın içeri alınması) -- ama
    # bugüne kadar YALNIZCA log dosyasına düşüyordu, Denetim Kayıtları
    # ekranında "kim, ne zaman, hangi bariyeri elle açtı" sorusunun cevabı
    # yoktu. Artık başarılı ve BAŞARISIZ her deneme denetim kaydına yazılıyor.
    if bariyer.mod == "simulate":
        logger.info("Bariyer açıldı (simülasyon): %s", bariyer.ad)
        _denetim_kaydet(db, kullanici.kullanici_adi, "bariyer_ac", f"{bariyer.ad} (id={bariyer.id}) elle açıldı (simülasyon)")
        return {"basarili": True, "mod": "simulate", "mesaj": f"{bariyer.ad} açıldı (simülasyon)"}

    if bariyer.mod == "http":
        if not (bariyer.http_url or "").strip():
            # Eskiden bu durumda urllib'in anlaşılmaz "unknown url type: ''"
            # hatası 503 ("yanıt alınamadı") olarak dönüyordu -- sorun ağda
            # değil yapılandırmada; kullanıcıya doğrudan söyleyelim.
            _denetim_kaydet(db, kullanici.kullanici_adi, "bariyer_ac_basarisiz", f"{bariyer.ad} (id={bariyer.id}): HTTP adresi tanımlı değil")
            raise HTTPException(400, f"{bariyer.ad} için HTTP röle adresi tanımlı değil -- Bariyer ayarlarından düzenleyin.")
        try:
            import urllib.request
            govde = (bariyer.http_govde or "").encode("utf-8") or None
            req = urllib.request.Request(bariyer.http_url, data=govde, method=bariyer.http_metot or "GET")
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception as exc:
            logger.error("Bariyer HTTP hatası %s: %s", bariyer.ad, exc)
            _denetim_kaydet(db, kullanici.kullanici_adi, "bariyer_ac_basarisiz", f"{bariyer.ad} (id={bariyer.id}): {exc}")
            raise HTTPException(503, f"Bariyer komutuna yanıt alınamadı: {exc}")
        logger.info("Bariyer HTTP komutu gönderildi: %s", bariyer.ad)
        _denetim_kaydet(db, kullanici.kullanici_adi, "bariyer_ac", f"{bariyer.ad} (id={bariyer.id}) elle açıldı (HTTP)")
        return {"basarili": True, "mod": "http", "mesaj": f"{bariyer.ad} komutu gönderildi"}

    _denetim_kaydet(db, kullanici.kullanici_adi, "bariyer_ac_basarisiz", f"{bariyer.ad} (id={bariyer.id}): desteklenmeyen mod {bariyer.mod}")
    raise HTTPException(400, f"Desteklenmeyen bariyer modu: {bariyer.mod}")


@app.delete("/bariyer/ayarlar/{bariyer_id}")
def bariyer_sil(bariyer_id: int, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    b = db.query(models.BariyerAyarlari).filter(models.BariyerAyarlari.id == bariyer_id).first()
    if not b:
        raise HTTPException(404, "Bariyer bulunamadı")
    # 2026-09-25 (sistem taraması): `noktalar.bariyer_id` bu tabloya bir
    # FOREIGN KEY. Eskiden bir erişim noktasına atanmış bir bariyer
    # silindiğinde: SQL Server kurulumlarında FK kısıtı silmeyi reddedip
    # kullanıcıya anlamsız bir 500 dönüyordu; SQLite'ta (FK zorlaması kapalı)
    # ise silme geçiyor ama nokta, artık var olmayan bir bariyer id'sini
    # göstermeye devam ediyordu (sessiz, kırık referans). Artık önce bu
    # bariyere bağlı noktaların bağlantısını kaldırıyoruz (nokta silinmez,
    # yalnızca "bariyeri yok" durumuna düşer) ve kaç noktanın etkilendiğini
    # cevapta söylüyoruz.
    etkilenen_noktalar = db.query(models.Nokta).filter(models.Nokta.bariyer_id == bariyer_id).all()
    for n in etkilenen_noktalar:
        n.bariyer_id = None
    bariyer_adi = b.ad
    db.delete(b)
    db.commit()
    _denetim_kaydet(
        db, kullanici.kullanici_adi, "bariyer_sil",
        f"bariyer_id={bariyer_id}, ad={bariyer_adi!r}, baglantisi_kaldirilan_nokta_sayisi={len(etkilenen_noktalar)}",
    )
    mesaj = "Bariyer silindi"
    if etkilenen_noktalar:
        mesaj += f" ({len(etkilenen_noktalar)} erişim noktasının bariyer bağlantısı kaldırıldı)"
    return {"mesaj": mesaj, "baglantisi_kaldirilan_nokta_sayisi": len(etkilenen_noktalar)}


# ==================================================================
# SİSTEM SAĞLIĞI VE LOG
# ==================================================================

_YEDEK_GECIKME_ESIGI_GUN = 2  # bu kadar günden eski bir yedek "gecikmiş" sayılır


def _son_yedek_bilgisini_al() -> dict:
    """SQL Server kullanan kurulumlarda "DB Yedek" butonu işlevsiz olduğu için
    (bkz. README "DB Yedek is SQLite-only"), yedekleme SQL Server Agent bakım
    planı gibi harici bir mekanizmaya bırakılır — ama sistem bu mekanizmanın
    GERÇEKTEN çalışıp çalışmadığını hiçbir şekilde izlemiyordu; bir operatör
    bakım planını hiç kurmasa ya da plan sessizce başarısız olmaya başlasa
    bile PTS bunu asla fark edip bildirmiyordu (aylarca yedeksiz kalınabilirdi).

    PTS_SQL_YEDEK_KLASORU ortam değişkeni, bakım planının .bak dosyalarını
    yazdığı klasöre ayarlanırsa, bu fonksiyon o klasördeki EN YENİ dosyanın
    yaşını okuyup /sistem/saglik üzerinden raporlar — panel/izleme aracı bu
    sinyali kullanarak "yedek gecikmiş" durumunu görünür kılabilir. Ayarlı
    değilse (varsayılan) hiçbir davranış değişmez, yalnızca `null` döner."""
    klasor = os.getenv("PTS_SQL_YEDEK_KLASORU", "").strip()
    if not klasor or not os.path.isdir(klasor):
        return {"izleniyor": False, "son_yedek_zamani": None, "yedek_gecikmis": None}
    try:
        dosyalar = [os.path.join(klasor, f) for f in os.listdir(klasor)]
        dosyalar = [f for f in dosyalar if os.path.isfile(f)]
        if not dosyalar:
            return {"izleniyor": True, "son_yedek_zamani": None, "yedek_gecikmis": True}
        en_yeni = max(dosyalar, key=os.path.getmtime)
        degistirilme = datetime.fromtimestamp(os.path.getmtime(en_yeni))
        gecikmis = (datetime.now() - degistirilme) > timedelta(days=_YEDEK_GECIKME_ESIGI_GUN)
        return {"izleniyor": True, "son_yedek_zamani": degistirilme.isoformat(), "yedek_gecikmis": gecikmis}
    except OSError as exc:
        logger.warning("Yedek klasörü okunamadı (%s): %s", klasor, exc)
        return {"izleniyor": True, "son_yedek_zamani": None, "yedek_gecikmis": None}


def _guvenlik_uyarilarini_topla(db: Session) -> dict:
    """Yalnızca başlangıçta BİR KEZ log dosyasına yazılan (bkz.
    `_kamera_anahtari_uyarisi`, `_cors_origin_listesi`, `lisans.secret_al`)
    "varsayılan/güvensiz ayar kullanılıyor" uyarılarının aynısını, kimsenin
    günlük olarak açıp okumadığı `loglar/pts.log`'un YANINDA panelde de
    görünür kılar (2026-09-20 -- kullanıcı isteğiyle yapılan geniş kapsamlı
    denetimde tespit edilen "sessiz güvenlik borcu" sınıfı: bu ayarlardan
    biri eksikse sistem GAYET normal çalışır, hiçbir hata vermez, ama gerçek
    bir güvenlik açığı sessizce açık kalır). Burada log YAZMIYORUZ (yalnızca
    env değişkenlerini okuyoruz) -- bu uç nokta periyodik olarak (panel
    yenilemesinde) çağrıldığı için, aksi halde her çağrıda log spam'ine yol
    açardı."""
    uyarilar = {
        # .strip(): sadece boşluk/satır sonundan oluşan bir değer de
        # "ayarlanmamış" sayılmalı -- bkz. _kamera_anahtari_degeri'nin kök
        # neden notu (aynı sınıf hata, burada yalnızca DOĞRU/YANLIŞ göstergesi
        # olduğu için sessiz bir kayıp riski yok, ama tutarlılık için aynı
        # şekilde ele alınır).
        "lisans_secret_ayarli_mi": bool((os.getenv("PTS_LICENSE_SECRET") or "").strip()),
        "kamera_anahtari_ayarli_mi": bool(_kamera_anahtari_degeri()),
        "cors_tum_originlere_acik": os.getenv("PTS_CORS_ORIGINS", "").strip() == "*",
    }
    # Arvento entegrasyonu (2026-09-23): kamera anahtarının aksine bu
    # entegrasyon OPSİYONELDİR -- çoğu kurulum hiç kullanmayacak. Anahtar
    # ayarlanmamışsa HER kurulumda uyarmak (kamera_anahtari_ayarli_mi gibi
    # koşulsuz) gereksiz gürültü olurdu; bu yüzden yalnızca entegrasyon
    # GERÇEKTEN kullanılıyorsa (en az bir Arvento olayı alınmışsa) VE anahtar
    # yoksa bu anahtar eklenir -- kullanılmayan bir özellik için sahte bir
    # güvenlik uyarısı göstermemek ile gerçekten kullanılan ama korumasız
    # bırakılan bir entegrasyonu sessizce geçmemek arasındaki denge budur.
    try:
        arvento_kullaniliyor = db.query(models.ArventoSuruculuOlay.id).first() is not None
    except Exception:
        arvento_kullaniliyor = False
    if arvento_kullaniliyor and not _arvento_anahtari_degeri():
        uyarilar["arvento_anahtari_ayarli_mi"] = False
    return uyarilar


@app.get("/sistem/saglik")
async def sistem_sagligi(db: Session = Depends(get_db), _: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Sistem durumunu (DB bağlantısı, aktif kamera pipeline sayısı, SSE
    istemci sayısı, yedek/görsel-izleme durumu vb.) döner -- panelin Sistem
    sekmesindeki "Sistem Durumu" kartının veri kaynağıdır.

    GÜVENLİK (2026-09-20): önceden bu uç nokta HİÇBİR kimlik doğrulaması
    istemiyordu -- ağa erişimi olan HERKES (oturum açmadan) aktif pipeline/
    SSE istemci sayısını, yedek durumunu ve ANPR eşik yapılandırmasını
    görebiliyordu. Diğer tüm teşhis/izleme uçları (`/sistem/loglar`,
    `/sistem/disk-kullanimi` vb.) zaten personel girişi istiyordu; bu
    tutarsızlık fark edilmemiş bir istisnaydı, düzeltildi. `tests/test_api.py`
    içindeki testler artık personel token'ı gönderiyor."""
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {
        "durum": "cevrimici",
        "veritabani": "ok" if db_ok else "hata",
        "aktif_pipeline": len(_aktif_pipelineler),
        "sse_istemci": len(_sse_istemcileri),
        "kutuphaneler_mevcut": _CAM_LIBS,
        "zaman": datetime.now().isoformat(),
        # KÖK NEDEN (2026-09-20): burada "2.0" sabit metni, `app = FastAPI(...,
        # version="2.0")` çağrısındaki AYNI değerin BAĞIMSIZ bir kopyasıydı --
        # biri güncellenip diğeri unutulursa (bu depoda daha önce defalarca
        # görülen "aynı gerçeğin birden fazla, birbirinden sapabilen kopyası"
        # hata sınıfı) panel yanlış bir sürüm numarası gösterirdi. Artık TEK
        # doğru kaynak `app.version`.
        "surum": app.version,
        "yedek": _son_yedek_bilgisini_al(),
        "gorsel_izleme": {
            "aktif": _klasor_izleyici is not None and _klasor_izleyici.calisiyor,
            "klasor": _klasor_izleyici.kok_klasor if _klasor_izleyici else None,
        },
        "anpr_dedektor_esigi": _anpr_dedektor_esigi_bilgisi_al(),
        "guvenlik_uyarilari": _guvenlik_uyarilarini_topla(db),
    }


def _anpr_dedektor_esigi_bilgisi_al() -> Optional[dict]:
    """PTS_ANPR_DETECTOR_ESIGI'nin fiilen uygulanıp uygulanmadığını panelden
    tek bakışta doğrulayabilmek için eklendi (bkz. camera_reader.py'deki
    dedektor_esigi_bilgisi() docstring'i — geçmişte bu ayarın panelin "Min.
    plaka tanıma güveni" alanıyla karıştırılması kullanıcı karışıklığına yol
    açmıştı). Kamera kütüphaneleri kurulu değilse veya motor henüz hiçbir
    kamera/klasör izleyici tarafından oluşturulmadıysa None döner."""
    if not _CAM_LIBS:
        return None
    try:
        from backend.camera_reader import dedektor_esigi_bilgisi as _bilgi_al
        return _bilgi_al()
    except Exception:
        return None


@app.post("/sistem/dogruluk-testi")
async def dogruluk_testi_calistir(
    istek: schemas.DogrulukTestiIstegi,
    kullanici: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    """Etiketli bir fotoğraf klasörü (bkz. camera_reader.py::toplu_dogruluk_testi
    docstring'i — Dahua NVR'ın ANPR dışa aktarım adlandırmasıyla uyumlu:
    "ONEK_PLAKA.jpg") üzerinde ANPR doğruluğunu ölçer. CANLI SİSTEME HİÇBİR
    YAN ETKİSİ YOKTUR (kayıt oluşturmaz, veritabanına dokunmaz) — farklı
    PTS_ANPR_DETECTOR_ESIGI / PTS_ANPR_DETECTOR_MODEL / kontrast ayarlarını,
    üretimi hiç etkilemeden, GERÇEK geçmiş fotoğraflarla karşılaştırmak için
    kullanılır. Yönetici/operatör ile sınırlıdır: sunucudaki dosya sistemini
    okuyan bir işlem olduğu için izleyici rolüne açılmamıştır.

    ONNX çıkarımı CPU'yu bloke eden senkron bir işlemdir; event loop'u
    kilitlememek için run_in_executor ile ayrı bir thread'de çalıştırılır
    (bkz. bu dosyadaki diğer run_in_executor kullanımları)."""
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    if not _CAM_LIBS:
        raise HTTPException(400, "Kamera/ANPR kütüphaneleri kurulu değil.")
    try:
        from backend.camera_reader import (
            toplu_dogruluk_testi as _testi_calistir,
            VARSAYILAN_MIN_GUVEN_SKORU as _varsayilan_esik,
        )
        sonuc = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _testi_calistir(
                istek.klasor,
                min_guven_skoru=istek.min_guven_skoru if istek.min_guven_skoru is not None else _varsayilan_esik,
                kontrast_iyilestir=istek.kontrast_iyilestir,
                dedektor_modeli=istek.dedektor_modeli or None,
                ocr_modeli=istek.ocr_modeli or None,
            ),
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return sonuc


@app.get("/sistem/anpr-modelleri")
def anpr_modellerini_listele(kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Toplu Doğruluk Testi'nde seçilebilecek bilinen dedektör/OCR modelleri
    ve canlı sistemin şu an kullandığı modeller (2026-09-25). Canlı motor
    henüz oluşturulmadıysa (hiç kamera başlamadıysa) `canli` alanları,
    ortam değişkenlerinden/varsayılandan hesaplanan değerlerdir."""
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    try:
        from backend import anpr_engine as _ae
    except Exception as exc:  # anpr_engine yalnızca stdlib'e bağlı; yine de güvenli
        raise HTTPException(400, f"ANPR modülü yüklenemedi: {exc}")
    bilgi = _anpr_dedektor_esigi_bilgisi_al() or {}
    return {
        "dedektor_modelleri": [
            {"ad": ad, "aciklama": f"{v['boyut']} px giriş, beklenen recall {v['recall']:.3f}"}
            for ad, v in _ae.DEDEKTOR_MODELI_BILGILERI.items()
        ],
        "ocr_modelleri": [{"ad": ad, "aciklama": aciklama} for ad, aciklama in _ae.OCR_MODELI_BILGILERI.items()],
        "canli_dedektor_modeli": bilgi.get("model")
            or (os.getenv("PTS_ANPR_DETECTOR_MODEL", "").strip() or _ae.DEDEKTOR_MODELI_VARSAYILAN),
        "canli_ocr_modeli": bilgi.get("ocr_model")
            or (os.getenv("PTS_ANPR_OCR_MODEL", "").strip() or _ae.OCR_MODELI_VARSAYILAN),
    }


_RTSP_KIMLIK_MASKELE_DESENI = re.compile(r"(rtsp://)([^/@\s:]+):([^/@\s]+)@")


def _log_satirini_maskele(satir: str) -> str:
    """Log satırındaki `rtsp://kullanici:parola@...` biçimindeki gömülü RTSP
    kimlik bilgilerini maskeler.

    GEÇMİŞ AÇIK: camera_reader.py, pipeline başlarken kamera bağlantı adresini
    (kullanıcı adı+parola dahil) doğrudan loglayıp `loglar/pts.log`'a
    yazıyordu; bu uç nokta ise o dosyayı OLDUĞU GİBİ döndürüyordu. Aynı
    dosyadaki `_kamera_guvenli_gorunum()` ile bilinçli yapılan parola
    maskeleme, bu iki delikten (ham log yazımı + maskesiz log servisi)
    tamamen boşa çıkıyordu. Kalıcı çözüm camera_reader.py'de artık kaynağında
    maskeleniyor olsa da, DİSKTE ZATEN duran eski log satırları hâlâ düz metin
    parola içerebilir — bu yüzden servis ederken de (savunma derinliği) ikinci
    kez maskeleniyor.
    """
    return _RTSP_KIMLIK_MASKELE_DESENI.sub(r"\1\2:****@", satir)


@app.get("/sistem/loglar")
def son_loglari_getir(satir: int = 200, kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    # GÜVENLİK: log satırları kamera bağlantı adresleri (RTSP kimlik bilgileri
    # dahil, bkz. _log_satirini_maskele) ve dahili hata detayları içerebilir —
    # salt-okunur "izleyici" rolüne açık bırakılmamalı.
    _rol_dogrula(kullanici, ROL_OPERATOR, ROL_YONETICI)
    log_dosyasi = os.path.join(LOG_KLASORU, "pts.log")
    if not os.path.exists(log_dosyasi):
        return {"satirlar": []}
    try:
        with open(log_dosyasi, "r", encoding="utf-8", errors="replace") as f:
            tum = f.readlines()
        return {"satirlar": [_log_satirini_maskele(s.rstrip()) for s in tum[-min(satir, 500):]]}
    except OSError:
        return {"satirlar": []}


@app.get("/denetim-kayitlari", response_model=List[schemas.DenetimKaydiCevap])
def denetim_kayitlarini_listele(
    kullanici_adi: Optional[str] = None,
    eylem: Optional[str] = None,
    baslangic: Optional[str] = None,
    bitis: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    """Hassas yönetici işlemlerinin (kullanıcı yönetimi, kamera silme, lisans
    aktivasyonu, sistem ayarları değişikliği -- bkz. main.py::_denetim_kaydet)
    kalıcı izini listeler.

    GÜVENLİK: yalnızca YÖNETİCİ görebilir -- `/sistem/loglar`'ın aksine
    (operatöre de açık genel arıza teşhis logu), bu uç nokta özellikle
    "kimin parolası sıfırlandı", "kim hangi role yükseltildi" gibi hesap
    yönetimi bilgilerini taşır; bu bilgi yalnızca yöneticinin işi."""
    _rol_dogrula(kullanici, ROL_YONETICI)
    sorgu = db.query(models.DenetimKaydi)
    if kullanici_adi:
        sorgu = sorgu.filter(models.DenetimKaydi.kullanici_adi.ilike(f"%{kullanici_adi.strip()}%"))
    if eylem:
        sorgu = sorgu.filter(models.DenetimKaydi.eylem == eylem.strip())
    baslangic_dt = _iso_tarih_parametresini_coz(baslangic, "baslangic")
    bitis_dt = _iso_tarih_parametresini_coz(bitis, "bitis")
    if baslangic_dt:
        sorgu = sorgu.filter(models.DenetimKaydi.zaman >= baslangic_dt)
    if bitis_dt:
        sorgu = sorgu.filter(models.DenetimKaydi.zaman <= bitis_dt)
    return (
        sorgu.order_by(models.DenetimKaydi.zaman.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@app.get("/denetim-kayitlari/eylem-listesi")
def denetim_eylem_listesini_getir(db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Panelin filtre açılır menüsünü doldurmak için, o ana kadar KAYDEDİLMİŞ
    benzersiz eylem türlerini döner -- sabit bir liste yerine bu tercih
    edildi ki ileride yeni bir `_denetim_kaydet` çağrı noktası eklendiğinde
    (bkz. yukarıdaki fonksiyonun docstring'i) filtre listesi otomatik
    güncel kalsın, kimse ayrıca burayı da güncellemeyi unutmasın."""
    _rol_dogrula(kullanici, ROL_YONETICI)
    sonuc = db.query(models.DenetimKaydi.eylem).distinct().order_by(models.DenetimKaydi.eylem).all()
    return {"eylemler": [s[0] for s in sonuc]}


# ==================================================================
# BİLDİRİM AYARLARI (Webhook / Telegram)
# ==================================================================
# 2026-09-26: `tip="telegram"` desteği eklendi -- bkz. backend/
# telegram_bildirim.py'nin docstring'i. `hedef`, tip="webhook" için bir URL,
# tip="telegram" için ise bot'un konuştuğu sohbetin chat_id'sidir (bot
# TOKEN'ı panelden/DB'den DEĞİL, PTS_TELEGRAM_BOT_TOKEN ortam değişkeninden
# okunur -- gizli bir değer düz metin olarak DB'de dolaşmasın diye).

@app.get("/bildirim/ayarlar")
def bildirim_ayarlarini_getir(db: Session = Depends(get_db), _: models.Kullanici = Depends(_personel_girisi_gerekli)):
    return db.query(models.BildirimAyarlari).order_by(models.BildirimAyarlari.olusturma_tarihi).all()


@app.post("/bildirim/ayarlar")
def bildirim_ayari_ekle(istek: dict = Body(...), db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI)
    ad = re.sub(r"[<>&\"']", "", str(istek.get("ad", "Bildirim"))).strip()[:80] or "Bildirim"
    hedef = str(istek.get("hedef", "")).strip()
    if not hedef:
        raise HTTPException(400, "Hedef boş olamaz (webhook için URL, telegram için chat_id)")
    tip = str(istek.get("tip", "webhook")).strip().lower()
    # DÜZELTME (2026-09-26): bkz. _bildirim_gonder_sync'in docstring'indeki
    # kök neden notu -- ÖNCEDEN `tip` HİÇ doğrulanmıyordu; artık desteklenen
    # bir değer değilse ayar HİÇ oluşturulmadan, işe yaramayacağı en baştan
    # (açık bir 400 ile) söylenir.
    if tip not in _BILDIRIM_TIPLERI:
        raise HTTPException(400, f"Desteklenmeyen bildirim tipi: '{tip}' (yalnızca {'/'.join(_BILDIRIM_TIPLERI)})")
    if tip == "telegram" and not telegram_bildirim.telegram_ayarli_mi():
        raise HTTPException(
            400,
            "Telegram bildirimi eklenemedi: sunucuda PTS_TELEGRAM_BOT_TOKEN ortam değişkeni ayarlanmamış "
            "(bkz. README.md'deki Telegram kurulum notu)",
        )
    yeni = models.BildirimAyarlari(
        ad=ad,
        tip=tip,
        hedef=hedef,
        tetikleyici=str(istek.get("tetikleyici", "hepsi")),
        http_metot=str(istek.get("http_metot", "POST")),
    )
    db.add(yeni)
    db.commit()
    db.refresh(yeni)
    return yeni


@app.patch("/bildirim/ayarlar/{ayar_id}/aktif")
def bildirim_aktif_toggle(ayar_id: int, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI)
    ayar = db.query(models.BildirimAyarlari).filter(models.BildirimAyarlari.id == ayar_id).first()
    if not ayar:
        raise HTTPException(404, "Ayar bulunamadı")
    ayar.aktif = not ayar.aktif
    db.commit()
    return {"id": ayar.id, "aktif": ayar.aktif}


@app.delete("/bildirim/ayarlar/{ayar_id}")
def bildirim_ayari_sil(ayar_id: int, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI)
    ayar = db.query(models.BildirimAyarlari).filter(models.BildirimAyarlari.id == ayar_id).first()
    if not ayar:
        raise HTTPException(404, "Ayar bulunamadı")
    db.delete(ayar)
    db.commit()
    return {"mesaj": "Bildirim ayarı silindi"}


@app.post("/bildirim/test/{ayar_id}")
async def bildirim_test_gonder(ayar_id: int, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI)
    ayar = db.query(models.BildirimAyarlari).filter(models.BildirimAyarlari.id == ayar_id).first()
    if not ayar:
        raise HTTPException(404, "Ayar bulunamadı")
    test_veri = {"test": True, "mesaj": "PTS test bildirimi", "zaman": datetime.now().isoformat()}
    basarili, hata = await asyncio.get_event_loop().run_in_executor(
        None, _bildirim_gonder_sync, ayar.tip, ayar.hedef, ayar.http_metot, test_veri
    )
    return {"basarili": basarili, "hedef": ayar.hedef, "tip": ayar.tip, "hata": hata}


# ==================================================================
# KAMERA SAĞLIK KONTROLÜ
# ==================================================================

@app.get("/kameralar/{kamera_id}/saglik")
async def kamera_saglik_kontrol(kamera_id: str, kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Kameranın TCP portuna bağlanabilirliğini ve pipeline durumunu raporlar."""
    if not _kamera_erisimi_var_mi(kullanici, kamera_id):
        raise HTTPException(403, "Bu kameraya erişim yetkiniz yok")
    kamera = next((k for k in _kameralari_oku() if k["id"] == kamera_id), None)
    if not kamera:
        raise HTTPException(404, "Kamera bulunamadı")

    # RTSP URL'den host:port çıkar
    parcalar = urlsplit(kamera["rtsp_url"])
    host = parcalar.hostname or ""
    port = parcalar.port or 554
    tcp_ok = False
    gecikme_ms = None

    if host:
        import socket
        t0 = time.monotonic()
        try:
            s = socket.create_connection((host, port), timeout=3)
            s.close()
            tcp_ok = True
            gecikme_ms = round((time.monotonic() - t0) * 1000, 1)
        except (OSError, socket.timeout):
            gecikme_ms = None

    p = _aktif_pipelineler.get(kamera_id)
    pipeline_calisiyor = p is not None and p.calisiyor and p.thread_canli_mi()
    durum_bilgisi = p.durum_bilgisi() if p is not None else {
        "son_kare_yasi_sn": None, "donmus": False, "yeniden_baglanma_sayisi": 0, "calisma_suresi_sn": 0,
    }

    if not kamera.get("aktif", True):
        durum = "kapali"
    elif not tcp_ok:
        durum = "bagli_degil"
    elif not pipeline_calisiyor:
        durum = "bagli_degil"
    elif durum_bilgisi.get("donmus"):
        durum = "donmus"
    else:
        durum = "canli"

    return {
        "id": kamera_id,
        "ad": kamera["ad"],
        "host": host,
        "port": port,
        "tcp_erisim": tcp_ok,
        "gecikme_ms": gecikme_ms,
        "pipeline_calisiyor": pipeline_calisiyor,
        "son_kare_yasi_sn": durum_bilgisi.get("son_kare_yasi_sn"),
        "yeniden_baglanma_sayisi": durum_bilgisi.get("yeniden_baglanma_sayisi", 0),
        "calisma_suresi_sn": durum_bilgisi.get("calisma_suresi_sn", 0),
        "durum": durum,  # canli | donmus | bagli_degil | kapali — frontend'in göstereceği tek özet alan
        "rtsp_url_maskelendi": _kamera_guvenli_gorunum(kamera)["rtsp_url"],
    }


@app.get("/kameralar/saglik/tumu")
async def tum_kameralar_saglik(kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Tüm kameralar için sağlık kontrolü — toplu sorgu."""
    izinli = _kullanicinin_izinli_kameralari(kullanici)
    kameralar = _kameralari_oku()
    if izinli is not None:
        kameralar = [k for k in kameralar if k["id"] in izinli]
    if not kameralar:
        return []
    sonuclar = []
    for k in kameralar:
        parcalar = urlsplit(k["rtsp_url"])
        host = parcalar.hostname or ""
        port = parcalar.port or 554
        tcp_ok = False
        gecikme_ms = None
        if host:
            import socket
            t0 = time.monotonic()
            try:
                s = await asyncio.get_event_loop().run_in_executor(
                    None, lambda h=host, p=port: socket.create_connection((h, p), timeout=3)
                )
                s.close()
                tcp_ok = True
                gecikme_ms = round((time.monotonic() - t0) * 1000, 1)
            except Exception:
                pass
        p = _aktif_pipelineler.get(k["id"])
        pipeline_calisiyor = p is not None and p.calisiyor and p.thread_canli_mi()
        donmus = bool(p.durum_bilgisi().get("donmus")) if p is not None else False
        if not k.get("aktif", True):
            durum = "kapali"
        elif not tcp_ok or not pipeline_calisiyor:
            durum = "bagli_degil"
        elif donmus:
            durum = "donmus"
        else:
            durum = "canli"
        sonuclar.append({
            "id": k["id"],
            "ad": k["ad"],
            "tcp_erisim": tcp_ok,
            "gecikme_ms": gecikme_ms,
            "pipeline_calisiyor": pipeline_calisiyor,
            "durum": durum,
        })
    return sonuclar


# ==================================================================
# TOPLU İÇE AKTARMA (Excel'den kişi ekleme)
# ==================================================================

@app.get("/kisiler/toplu-import/sablon")
def kisi_ice_aktarma_sablonu_indir(
    _: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    """Kullanıcı talebi (2026-09-18): personel/abone/ziyaretçi kaydını toplu
    içe aktarmak için boş bir Excel ŞABLONU indirilebilsin -- önceden yalnızca
    `toplu_kisi_import`'un docstring'inde hangi sütunların beklendiği
    YAZIYORDU ama operatörün kendi başına doğru başlıklarla bir dosya
    OLUŞTURMASI gerekiyordu (yazım hatası/sütun sırası hatası riski). Bu uç
    nokta, `toplu_kisi_import`'un beklediği sütunlarla BİREBİR eşleşen,
    örnek satırlar ve açıklama sayfası içeren, "tip" sütununda açılır liste
    doğrulaması olan hazır bir şablon üretir."""
    dosya_yolu = _gecici_rapor_yolu("pts_kisi_ice_aktarma_sablonu", "xlsx")
    excel_export.kisi_ice_aktarma_sablonu_olustur(dosya_yolu)
    return _indirip_sil(dosya_yolu, "pts_kisi_ice_aktarma_sablonu.xlsx", _XLSX_MEDIA)


@app.post("/kisiler/toplu-import")
async def toplu_kisi_import(
    dosya: UploadFile = File(...),
    db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    """
    Excel (.xlsx) dosyasından toplu kişi içe aktarır.
    Beklenen sütunlar: ad_soyad, plaka_no, tip, telefon, daire_departman
    İlk satır başlık satırı olmalıdır.

    2026-09-23 kullanıcı isteği: "çoklu plaka tekrar eden isimler olarak
    düzenle" -- aynı kişinin (ör. bir departmanın havuz araçları, ya da
    birden fazla aracı olan bir personelin) artık AYRI satırlar yerine TEK
    satırda, 'plaka_no' hücresine virgül (,) veya noktalı virgülle (;)
    ayrılmış birden fazla plaka yazılarak içe aktarılabilmesi için (bkz.
    metin_araclari.py::plaka_hucresini_ayir). Hücredeki İLK plaka kişinin
    ana plaka_no'su, kalanlar models.KisiPlaka (ek_plakalar) olarak eklenir
    -- panelden Kişiler ekranında "+ Plaka Ekle" ile tek tek eklemekle
    birebir aynı veri modeli, tek farkı hepsinin tek adımda yapılabilmesi.
    """
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    if not dosya.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Sadece .xlsx veya .xls dosyası kabul edilir")

    from openpyxl import load_workbook
    import io

    icerik = await dosya.read()
    try:
        wb = load_workbook(filename=io.BytesIO(icerik), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(400, "Dosya okunamadı. Geçerli bir Excel dosyası olduğundan emin olun.")

    ws = wb.active
    satirlar = list(ws.iter_rows(values_only=True))
    if len(satirlar) < 2:
        raise HTTPException(400, "Dosyada veri satırı bulunamadı")

    # Başlık satırını normalize et
    basliklar = [str(b).strip().lower().replace(" ", "_") if b else "" for b in satirlar[0]]
    alan_indeksi = {alan: basliklar.index(alan) for alan in ("ad_soyad", "plaka_no", "tip") if alan in basliklar}

    if not all(alan in alan_indeksi for alan in ("ad_soyad", "plaka_no", "tip")):
        raise HTTPException(400, "Excel başlıklarında 'ad_soyad', 'plaka_no', 'tip' sütunları bulunamadı")

    eklendi = 0
    eklenen_ek_plaka = 0
    hatalar = []
    olusturulan_kisiler = []
    GECERLI_TIPLER = ("abone", "personel", "ziyaretci")

    for satir_no, satir in enumerate(satirlar[1:], start=2):
        try:
            ad_soyad = str(satir[alan_indeksi["ad_soyad"]] or "").strip()
            tip = str(satir[alan_indeksi["tip"]] or "").strip().lower()

            # 'plaka_no' hücresi artık virgül/noktalı virgülle ayrılmış
            # BİRDEN FAZLA plaka içerebilir (bkz. yukarıdaki fonksiyon notu
            # ve plaka_hucresini_ayir'ın kendi docstring'i) -- her parça
            # ayrı ayrı temizlenir/normalize edilir, geçersiz/boş olanlar
            # ve hücre içi tekrarlar sessizce elenir.
            plakalar = plaka_hucresini_ayir(str(satir[alan_indeksi["plaka_no"]] or ""))

            if not ad_soyad or not plakalar:
                hatalar.append(f"Satır {satir_no}: ad_soyad veya plaka_no boş")
                continue
            if tip not in GECERLI_TIPLER:
                tip = "abone"

            telefon = str(satir[alan_indeksi["telefon"]] or "").strip() if "telefon" in alan_indeksi else None
            daire = str(satir[alan_indeksi["daire_departman"]] or "").strip() if "daire_departman" in alan_indeksi else None

            yeni = models.Kisi(
                ad_soyad=ad_soyad[:100],
                plaka_no=plakalar[0][:15],
                tip=tip,
                telefon=telefon[:20] if telefon else None,
                daire_departman=daire[:50] if daire else None,
            )
            db.add(yeni)
            db.flush()  # yeni.id'yi almak için -- aşağıdaki KisiPlaka satırları FK olarak buna ihtiyaç duyar
            for ek_plaka in plakalar[1:]:
                db.add(models.KisiPlaka(kisi_id=yeni.id, plaka_no=ek_plaka[:15]))
                eklenen_ek_plaka += 1
            olusturulan_kisiler.append(yeni)
            eklendi += 1
        except Exception as exc:
            hatalar.append(f"Satır {satir_no}: {exc}")

    guncellenen_gecmis_kayit = 0
    if eklendi:
        db.commit()
        logger.info("Toplu import: %d kişi eklendi (kullanıcı: %s)", eklendi, kullanici.kullanici_adi)
        # 2026-09-18: her içe aktarılan kişi için de -- panelden tek tek
        # eklerken olduğu gibi -- geçmiş "yetkisiz" tespitler otomatik
        # düzeltilir (bkz. kisi_ekle'deki aynı çağrının notu).
        for yeni_kisi in olusturulan_kisiler:
            try:
                guncellenen_gecmis_kayit += _gecmis_kayitlari_kisiye_bagla(db, yeni_kisi, kullanici.kullanici_adi)
            except Exception:
                logger.exception(
                    "Toplu import sonrası geçmiş kayıtları bağlama başarısız oldu (kişi id=%s)", yeni_kisi.id
                )

    return {
        "eklendi": eklendi, "eklenen_ek_plaka": eklenen_ek_plaka, "hatalar": hatalar[:20],
        "guncellenen_gecmis_kayit": guncellenen_gecmis_kayit,
    }


# ==================================================================
# SİSTEM AYARLARI
# ==================================================================

@app.get("/sistem/ayarlar")
def sistem_ayarlarini_getir(_: models.Kullanici = Depends(_personel_girisi_gerekli)):
    return _sistem_ayarlari_oku()


def _ayar_int_dogrula(v, min_deger: Optional[int] = None, max_deger: Optional[int] = None) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise HTTPException(400, f"Tam sayı olmalı, alınan değer: {v!r}")
    if isinstance(v, bool):  # bool, int'in alt sınıfı olduğu için int(True)==1 sessizce geçerdi
        raise HTTPException(400, f"Tam sayı olmalı, alınan değer: {v!r}")
    if min_deger is not None and n < min_deger:
        raise HTTPException(400, f"En az {min_deger} olmalı, alınan değer: {n}")
    if max_deger is not None and n > max_deger:
        raise HTTPException(400, f"En fazla {max_deger} olmalı, alınan değer: {n}")
    return n


def _ayar_float_dogrula(v, min_deger: float = 0.0, max_deger: float = 1.0) -> float:
    if isinstance(v, bool):
        raise HTTPException(400, f"Sayısal bir değer olmalı, alınan değer: {v!r}")
    try:
        n = float(v)
    except (TypeError, ValueError):
        raise HTTPException(400, f"Sayısal bir değer olmalı, alınan değer: {v!r}")
    if not (min_deger <= n <= max_deger):
        raise HTTPException(400, f"{min_deger}-{max_deger} arasında olmalı, alınan değer: {n}")
    return n


def _ayar_bool_dogrula(v) -> bool:
    if isinstance(v, bool):
        return v
    raise HTTPException(400, f"true/false olmalı, alınan değer: {v!r}")


def _ayar_klasor_yolu_dogrula(v) -> str:
    if not isinstance(v, str) or isinstance(v, bool):
        raise HTTPException(400, f"Bir klasör yolu (metin) olmalı, alınan değer: {v!r}")
    v = v.strip()
    if not v:
        raise HTTPException(400, "Klasör yolu boş olamaz")
    if len(v) > 500:
        raise HTTPException(400, "Klasör yolu en fazla 500 karakter olmalı")
    return v


# DÜZELTME (2026-09-25, sistem taraması): PUT /sistem/ayarlar önceden
# gönderilen değerin TİPİNİ/ARALIĞINI hiç doğrulamıyordu -- yalnızca
# anahtarın _VARSAYILAN_AYARLAR'da var olup olmadığına bakılıyordu. Bu iki
# gerçek üretim riskine yol açıyordu: (1) "min_tanima_guveni" gibi bir eşiğe
# sayı yerine metin/bozuk bir değer yazılırsa, bu değer _pipeline_baslat
# içinde float()'a çevrilmeye çalışıldığında istisna fırlatıyor -- bu da
# İZLEME (watchdog) döngüsü her denediğinde (20 sn'de bir) TÜM kameraların
# sürekli başlatılıp hemen çökmesine yol açabiliyordu; (2) "supheli_esik"
# gibi güvenlik eşikleri negatif/anlamsız bir değere ayarlanabiliyordu.
# Her ayar için tip/aralık kontrolü burada MERKEZİ olarak tanımlanır --
# ileride yeni bir ayar eklenirse bu sözlüğe eklenmediği sürece
# doğrulanmadan kabul edilir, bu yüzden yeni ayar eklerken buraya da
# eklemek gerekir.
_AYAR_DOGRULAYICILAR = {
    "supheli_esik": lambda v: _ayar_int_dogrula(v, 0, 1000),
    "goruntu_saklama_gun": lambda v: _ayar_int_dogrula(v, 0, None),
    "tekrar_gecikme_sn": lambda v: _ayar_int_dogrula(v, 0, 3600),
    "capraz_kamera_tekrar_penceresi_sn": lambda v: _ayar_int_dogrula(v, None, None),
    "auto_bariyer_giris": _ayar_bool_dogrula,
    "panel_yenileme_sn": lambda v: _ayar_int_dogrula(v, 2, 3600),
    "min_tanima_guveni": lambda v: _ayar_float_dogrula(v, 0.0, 1.0),
    "bilinen_plaka_duzeltme_aktif": _ayar_bool_dogrula,
    "otomatik_kayit_min_guven_skoru": lambda v: _ayar_float_dogrula(v, 0.0, 1.0),
    "otomatik_kayit_min_guven_skoru_bilinen_arac": lambda v: _ayar_float_dogrula(v, 0.0, 1.0),
    "otomatik_yedek_aktif": _ayar_bool_dogrula,
    "otomatik_yedek_klasoru": _ayar_klasor_yolu_dogrula,
    "otomatik_yedek_saklama_gun": lambda v: _ayar_int_dogrula(v, 0, None),
    "disk_izleme_aktif": _ayar_bool_dogrula,
    "disk_uyari_esik_yuzde": lambda v: _ayar_int_dogrula(v, 50, 99),
}


@app.put("/sistem/ayarlar")
def sistem_ayarlarini_guncelle(yeni: dict = Body(...), db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    _rol_dogrula(kullanici, ROL_YONETICI)
    mevcut = _sistem_ayarlari_oku()
    degisiklikler = []
    for k, v in yeni.items():
        if k not in _VARSAYILAN_AYARLAR:
            continue
        dogrulayici = _AYAR_DOGRULAYICILAR.get(k)
        if dogrulayici is not None:
            v = dogrulayici(v)
        if mevcut.get(k) != v:
            degisiklikler.append(f"{k}: {mevcut.get(k)!r} -> {v!r}")
            mevcut[k] = v
    _sistem_ayarlari_yaz(mevcut)
    # 2026-09-20: sistem ayarları (ör. min_guven_skoru gibi güvenlik/doğruluk
    # açısından kritik bir eşik) değiştirildiğinde önceden HİÇBİR log satırı
    # yazılmıyordu -- "bu eşik ne zaman, kim tarafından değiştirildi" sorusu
    # cevapsızdı. Gerçek bir değişiklik yoksa (aynı değerler tekrar
    # gönderildiyse) log spam'i olmasın diye yalnızca fark varsa yazılıyor.
    if degisiklikler:
        _denetim_kaydet(db, kullanici.kullanici_adi, "sistem_ayarlari_guncelle", "; ".join(degisiklikler))
    return mevcut


# ==================================================================
# ARAÇ İÇERİDE / DIŞARIDA TAKİBİ
# ==================================================================

@app.get("/araclar/iceridedurum")
def araclar_iceridedurum(db: Session = Depends(get_db), _: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Her plaka için son yetkili geçiş 'giris' ise aracı içeride sayar."""
    from sqlalchemy import func
    son_kayit_sq = (
        db.query(
            models.Kayit.plaka_no,
            func.max(models.Kayit.tarih_saat).label("son_zaman"),
        )
        .filter(models.Kayit.yetki_durumu == "yetkili")
        .group_by(models.Kayit.plaka_no)
        .subquery()
    )
    iceride = (
        db.query(models.Kayit)
        .join(
            son_kayit_sq,
            (models.Kayit.plaka_no == son_kayit_sq.c.plaka_no)
            & (models.Kayit.tarih_saat == son_kayit_sq.c.son_zaman),
        )
        .filter(models.Kayit.yon == "giris")
        .all()
    )
    return {
        "iceride_sayisi": len(iceride),
        "araclar": [
            {
                "plaka_no": k.plaka_no,
                "giris_saati": k.tarih_saat.isoformat(),
                "kamera_id": k.kamera_id,
                "goruntu_yolu": k.goruntu_yolu,
            }
            for k in sorted(iceride, key=lambda x: x.tarih_saat, reverse=True)
        ],
    }


# ==================================================================
# DİSK YÖNETİMİ VE VERİTABANI YEDEĞİ
# ==================================================================

@app.get("/sistem/disk-kullanimi")
def disk_kullanimi(_: models.Kullanici = Depends(_personel_girisi_gerekli)):
    toplam_mb = 0.0
    dosya_sayisi = 0
    try:
        for dosya in os.listdir(GORUNTU_KLASORU):
            yol = os.path.join(GORUNTU_KLASORU, dosya)
            if os.path.isfile(yol):
                toplam_mb += os.path.getsize(yol) / (1024 * 1024)
                dosya_sayisi += 1
    except OSError:
        pass
    # DÜZELTME (2026-09-26, kullanıcı isteği: "diskin gerçekten dolmasına
    # karşı erken uyarı"): bu uç nokta önceden yalnızca görüntü klasörünün
    # BAYT boyutunu raporluyordu -- diskin kendisinin ne kadar dolu olduğu
    # (yüzde olarak) panelde HİÇ görünmüyordu, yalnızca arka planda sessizce
    # çalışan _disk_izleme_dongu bunu biliyordu. Artık aynı bilgi burada da
    # (panelin görebileceği şekilde) döndürülüyor.
    ayarlar = _sistem_ayarlari_oku()
    diskler = []
    for etiket, yol in _izlenen_disk_yollari(ayarlar).items():
        yuzde = _disk_kullanim_yuzdesi(yol)
        diskler.append({"etiket": etiket, "yol": yol, "kullanim_yuzdesi": yuzde})
    return {
        "goruntu_mb": round(toplam_mb, 2),
        "goruntu_sayisi": dosya_sayisi,
        "diskler": diskler,
        "uyari_esigi_yuzde": ayarlar.get("disk_uyari_esik_yuzde", 90),
    }


def _goruntu_temizle_calistir(gun: int, db: Session) -> tuple[int, "datetime"]:
    """Paylaşılan temizlik mantığı: hem manuel uç nokta hem de otomatik
    saklama görevi tarafından kullanılır. `gun`'dan eski, görüntüsü olan
    kayıtların diskteki dosyasını siler ve kayıttaki goruntu_yolu alanını
    temizler (kaydın kendisi silinmez, sadece görüntü dosyası)."""
    sinir = datetime.now() - timedelta(days=gun)
    eski_kayitlar = db.query(models.Kayit).filter(
        models.Kayit.tarih_saat < sinir,
        models.Kayit.goruntu_yolu.isnot(None),
    ).all()
    silinen = 0
    for kayit in eski_kayitlar:
        try:
            dosya_adi = os.path.basename(kayit.goruntu_yolu)
            tam_yol = os.path.join(GORUNTU_KLASORU, dosya_adi)
            if os.path.exists(tam_yol):
                os.remove(tam_yol)
                silinen += 1
            kucuk_gorsel.kucuk_gorseli_sil(tam_yol)
            kayit.goruntu_yolu = None
        except OSError:
            pass
    db.commit()
    return silinen, sinir


@app.post("/sistem/goruntu-temizle")
def goruntu_temizle(gun: int = Query(30, ge=1, le=365), kullanici: models.Kullanici = Depends(_personel_girisi_gerekli), db: Session = Depends(get_db)):
    _rol_dogrula(kullanici, ROL_YONETICI, ROL_OPERATOR)
    silinen, sinir = _goruntu_temizle_calistir(gun, db)
    logger.info("Görüntü temizliği (manuel): %d dosya silindi (>%d gün)", silinen, gun)
    return {"silinen_goruntu": silinen, "sinir_tarihi": sinir.isoformat()}


@app.post("/sistem/dusuk-guven-temizle")
def dusuk_guven_kayitlarini_temizle(
    esik: Optional[float] = Query(None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_personel_girisi_gerekli),
):
    """"Güven eşiği" özelliği devreye alınmadan ÖNCE zaten kaydedilmiş, düşük
    güvenli OTOMATİK tespit kayıtlarını (ve varsa görsel dosyalarını) toplu
    olarak temizler (bkz. kayit_ekle_otomatik'teki gerçek-zamanlı filtre --
    o filtre yalnızca BUNDAN SONRAKİ tespitleri etkiler, bu uç nokta ise
    geriye dönük birikmiş "kayıtları şişiren" eski kayıtlar içindir).

    `esik` verilmezse Sistem Ayarları'ndaki `otomatik_kayit_min_guven_skoru`
    kullanılır. Yalnızca `guven_skoru` DOLU olan (yani gerçek bir OCR
    tespiti olan) ve elle girilmemiş (`manuel_giris=False`) kayıtlar hedef
    alınır -- personelin bilinçli olarak girdiği kayıtlara veya ziyaretçi
    girişi/sakin geçmişi gibi elle onaylanmış kayıtlara ASLA dokunulmaz.
    Silinen kayıtlara bağlı alarm günlüğü korunur, yalnızca artık var
    olmayan kayda olan bağlantısı koparılır (bkz. kayit_sil'deki aynı
    FK-güvenliği deseni)."""
    _rol_dogrula(kullanici, ROL_YONETICI)
    if esik is None:
        esik = _sistem_ayarlari_oku().get("otomatik_kayit_min_guven_skoru", 0.97)
    try:
        esik = max(0.0, min(1.0, float(esik)))
    except (TypeError, ValueError):
        esik = 0.97

    hedefler = db.query(models.Kayit).filter(
        models.Kayit.manuel_giris == False,  # noqa: E712
        models.Kayit.guven_skoru.isnot(None),
        models.Kayit.guven_skoru < esik,
    ).all()

    kayit_idleri = [k.id for k in hedefler]
    if kayit_idleri:
        db.query(models.Alarm).filter(models.Alarm.kayit_id.in_(kayit_idleri)).update(
            {"kayit_id": None}, synchronize_session=False,
        )

    silinen_kayit = 0
    silinen_goruntu = 0
    for k in hedefler:
        if k.goruntu_yolu and os.path.isfile(k.goruntu_yolu):
            try:
                os.remove(k.goruntu_yolu)
                silinen_goruntu += 1
            except OSError:
                pass
        db.delete(k)
        silinen_kayit += 1
    db.commit()
    logger.info(
        "Düşük güvenli kayıt temizliği (manuel): %d kayıt, %d görüntü silindi (eşik<%.3f)",
        silinen_kayit, silinen_goruntu, esik,
    )
    return {"silinen_kayit": silinen_kayit, "silinen_goruntu": silinen_goruntu, "esik": esik}


@app.get("/sistem/yedek")
def veritabani_yedek(kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """DÜZELTME (2026-09-25): bu uç nokta önceden WAL modundaki veritabanı
    dosyasını doğrudan (checkpoint yapmadan) kopyalıyordu -- bkz.
    _sqlite_yedek_al'ın docstring'i: WAL modunda son işlemler bir süre
    yalnızca ".db-wal" dosyasında durabilir, ana dosyanın ham kopyası bunları
    SESSİZCE KAÇIRABİLİRDİ. Artık aynı sqlite3.backup() tabanlı yardımcıyı
    (otomatik yedeklemeyle ORTAK) kullanarak DISA_AKTAR_KLASORU altında
    tutarlı bir geçici kopya üretip onu indiriyor."""
    _rol_dogrula(kullanici, ROL_YONETICI)
    if not SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        raise HTTPException(400, "Otomatik yedek sadece SQLite için desteklenir. SQL Server için veritabanı yönetim araçlarını kullanın.")
    db_yolu = urlparse(SQLALCHEMY_DATABASE_URL).path.lstrip("/")
    if not os.path.exists(db_yolu):
        raise HTTPException(404, "Veritabanı dosyası bulunamadı")
    zaman_damgasi = datetime.now().strftime("%Y%m%d_%H%M%S")
    dosya_adi = f"pts_yedek_{zaman_damgasi}.db"
    gecici_yol = os.path.join(DISA_AKTAR_KLASORU, f"pts_yedek_gecici_{uuid.uuid4().hex}.db")
    try:
        _sqlite_yedek_al(db_yolu, gecici_yol)
        # DÜZELTME (2026-09-26): elle indirilen yedek de artık otomatik
        # yedekle AYNI bütünlük kontrolünden geçiyor -- kopyalama istisnasız
        # bitse bile sonuç bozuk olabilir (bkz. _yedek_dosyasi_saglam_mi),
        # bunu indirdikten SONRA (belki aylar sonra bir felakette) fark
        # etmek yerine indirme ANINDA açıkça söylemek daha iyidir.
        saglam, hata = _yedek_dosyasi_saglam_mi(gecici_yol)
        if not saglam:
            _dosyayi_sessizce_sil(gecici_yol)
            raise HTTPException(500, f"Yedek dosyası bütünlük kontrolünden geçemedi, indirme iptal edildi: {hata}")
    except HTTPException:
        raise
    except Exception as exc:
        _dosyayi_sessizce_sil(gecici_yol)
        raise HTTPException(500, f"Yedek alınamadı: {exc}")
    # 2026-09-25: geçici tam veritabanı kopyası indirildikten sonra SİLİNİR
    # -- eskiden her "DB Yedek" tıklaması, tüm kişisel verileri içeren tam
    # bir kopyayı `disa_aktarilanlar/` klasöründe süresiz bırakıyordu.
    return _indirip_sil(gecici_yol, dosya_adi, "application/octet-stream")


@app.get("/sistem/yedek/otomatik-liste")
def otomatik_yedekleri_listele(kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """DÜZELTME (2026-09-25): otomatik yedekleme arka planda sessizce
    çalıştığı için (bkz. _otomatik_yedek_dongu), bir yöneticinin bunun
    GERÇEKTEN çalıştığını panelden görebilmesi gerekir -- yoksa "otomatik
    yedek aktif" ayarı işaretlense bile, aslında hiç yedek üretilmiyor olsa
    (ör. yanlış/erişilemez bir klasör yolu yazılmışsa) bunu fark etmenin tek
    yolu sunucunun log dosyasına elle bakmak olurdu.

    DÜZELTME (2026-09-26): her yedeğin yanına artık `saglam` alanı eklendi --
    `True` (yanında `.verified` işaretçisi var, bkz. _yedegi_dogrulandi_olarak_isaretle),
    `False` (adı ".BOZUK.db" ile işaretli, bkz. _yedegi_bozuk_olarak_isaretle)
    ya da `None` (bu özellikten ÖNCE alınmış, hiç doğrulanmamış eski yedek --
    panelden "Şimdi Doğrula" ile istendiğinde doğrulanabilir, bkz.
    otomatik_yedek_dogrula)."""
    _rol_dogrula(kullanici, ROL_YONETICI)
    ayarlar = _sistem_ayarlari_oku()
    klasor = _otomatik_yedek_klasoru_al(ayarlar)
    yedekler = []
    if os.path.isdir(klasor):
        for ad in sorted(os.listdir(klasor), reverse=True):
            if ad.startswith(OTOMATIK_YEDEK_DOSYA_ONEKI) and ad.endswith(".db"):
                tam_yol = os.path.join(klasor, ad)
                try:
                    istat = os.stat(tam_yol)
                    if ad.endswith(".BOZUK.db"):
                        saglam = False
                    elif os.path.isfile(tam_yol + ".verified"):
                        saglam = True
                    else:
                        saglam = None
                    yedekler.append({
                        "dosya_adi": ad,
                        "boyut_bayt": istat.st_size,
                        "tarih_saat": datetime.fromtimestamp(istat.st_mtime).isoformat(),
                        "saglam": saglam,
                    })
                except OSError:
                    continue
    return {
        "klasor": klasor,
        "aktif": bool(ayarlar.get("otomatik_yedek_aktif", True)),
        "yedekler": yedekler[:30],
    }


@app.post("/sistem/yedek/otomatik-liste/{dosya_adi}/dogrula")
def otomatik_yedek_dogrula(dosya_adi: str, kullanici: models.Kullanici = Depends(_personel_girisi_gerekli)):
    """Panelden istek üzerine, listelenen belirli bir otomatik yedeğin
    GERÇEKTEN geri yüklenebilir olduğunu (yeniden) doğrular -- hem bu
    patch'ten ÖNCE alınmış (hiç doğrulanmamış, `saglam: null` görünen) eski
    yedekler hem de zaten doğrulanmış bir yedek bir yöneticinin isteğiyle
    her an yeniden kontrol edilebilsin diye (bkz. _yedek_dosyasi_saglam_mi)."""
    _rol_dogrula(kullanici, ROL_YONETICI)
    # /goruntuler/{dosya_adi}'daki ile AYNI yol geçişi koruması (bkz. o uç
    # noktanın docstring'i): tek segment içinde kalan ama yine de ".." içeren
    # bir değer de reddedilir.
    if os.path.basename(dosya_adi) != dosya_adi or ".." in dosya_adi:
        raise HTTPException(400, "Geçersiz dosya adı")
    if not (dosya_adi.startswith(OTOMATIK_YEDEK_DOSYA_ONEKI) and dosya_adi.endswith(".db")):
        raise HTTPException(400, "Geçersiz yedek dosyası adı")
    ayarlar = _sistem_ayarlari_oku()
    klasor = _otomatik_yedek_klasoru_al(ayarlar)
    tam_yol = os.path.join(klasor, dosya_adi)
    if not os.path.isfile(tam_yol):
        raise HTTPException(404, "Yedek dosyası bulunamadı")
    saglam, hata = _yedek_dosyasi_saglam_mi(tam_yol)
    yeni_ad = dosya_adi
    if saglam:
        _yedegi_dogrulandi_olarak_isaretle(tam_yol)
    else:
        yeni_ad = os.path.basename(_yedegi_bozuk_olarak_isaretle(tam_yol))
    return {"dosya_adi": yeni_ad, "saglam": saglam, "hata": hata}


if __name__ == "__main__":
    import uvicorn
    # NOT: gerçek üretim başlatıcıları (calistir.bat/calistir.sh) zaten doğrudan
    # `uvicorn ... --host 0.0.0.0 --port 8000` çağırıyor (reload'sız) — bu blok
    # yalnızca birinin `python main.py` ile DOĞRUDAN çalıştırması durumunda
    # devreye girer. Önceden burada `reload=True` sabitti; bu saf bir geliştirme
    # özelliğidir (dosya değişikliklerini izleyip süreci otomatik yeniden
    # başlatır) ve üretimde istenmeyen otomatik yeniden başlatma/çift süreç
    # davranışına yol açabilir. Artık varsayılan KAPALI, yalnızca
    # PTS_GELISTIRME_MODU=1 ile açıkça istenirse açılıyor.
    _gelistirme_modu = os.getenv("PTS_GELISTIRME_MODU", "").strip().lower() in ("1", "true", "evet")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=_gelistirme_modu)
