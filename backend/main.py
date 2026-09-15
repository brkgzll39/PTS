"""
PTS - Plaka Tanıma Sistemi - Ana Uygulama
==========================================
Çalıştırma: uvicorn main:app --reload
Tarayıcıda açın: http://localhost:8000
"""
import os
import re
import shutil
import hashlib
import hmac
import json
import logging
from logging.handlers import RotatingFileHandler
import platform
import secrets
import threading
import time
import uuid
import base64
import asyncio
from urllib.parse import urlsplit, urlunsplit
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Query, Body, Header, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend import models
from backend import schemas
from backend.database import engine, get_db, Base
from backend.database import SQLALCHEMY_DATABASE_URL
from backend import excel_export
from backend import pdf_export
from backend import led_panel

# ---------------------- KLASÖR AYARLARI ----------------------
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJE_KOKU = os.path.dirname(BACKEND_DIR)
GORUNTU_KLASORU = os.path.join(PROJE_KOKU, "goruntuler")
DISA_AKTAR_KLASORU = os.path.join(PROJE_KOKU, "disa_aktarilanlar")
FRONTEND_KLASORU = os.path.join(PROJE_KOKU, "frontend")
LISANS_DOSYASI = os.path.join(BACKEND_DIR, "license.json")
KAMERA_DOSYASI = os.path.join(BACKEND_DIR, "cameras.json")
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

# ================================================================
# VERİTABANI MİGRASYONU — mevcut tablolara yeni sütun ekler
# ================================================================

def _veritabani_migrasyon() -> None:
    """create_all yeni sütun eklemez; bu fonksiyon ALTER TABLE ile tamamlar."""
    sqlite_mod = SQLALCHEMY_DATABASE_URL.startswith("sqlite")
    col_kw = "COLUMN " if sqlite_mod else ""
    bool_tip = "INTEGER DEFAULT 0" if sqlite_mod else "BIT DEFAULT 0"
    adimlar = [
        f"ALTER TABLE kisiler ADD {col_kw}giris_saati_baslangic VARCHAR(5)",
        f"ALTER TABLE kisiler ADD {col_kw}giris_saati_bitis VARCHAR(5)",
        f"ALTER TABLE kisiler ADD {col_kw}izin_verilen_gunler VARCHAR(20)",
        f"ALTER TABLE bariyer_ayarlari ADD {col_kw}auto_ac {bool_tip}",
    ]
    with engine.connect() as conn:
        for sql in adimlar:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass

_veritabani_migrasyon()

# ================================================================
# SİSTEM AYARLARI (JSON dosyasında saklanan yapılandırma)
# ================================================================

SISTEM_AYARLARI_DOSYASI = os.path.join(BACKEND_DIR, "sistem_ayarlari.json")
_VARSAYILAN_AYARLAR = {
    "supheli_esik": 3,           # saatte kaç red → şüpheli alarm
    "goruntu_saklama_gun": 30,   # görüntü saklama süresi (gün)
    "tekrar_gecikme_sn": 30,     # aynı plakayı tekrar bildirme gecikmesi
    "auto_bariyer_giris": False, # yetkili girişte otomatik bariyer
    "panel_yenileme_sn": 15,     # frontend polling aralığı
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


def _pipeline_baslat(kamera: dict) -> bool:
    if not _CAM_LIBS or _KameraPipeline is None:
        return False
    kid = kamera["id"]
    with _pipeline_kilit:
        if kid in _aktif_pipelineler and _aktif_pipelineler[kid].calisiyor:
            return True
        try:
            p = _KameraPipeline(
                video_kaynagi=kamera["rtsp_url"],
                kamera_id=kamera["ad"],
                yon=kamera.get("yon", "giris"),
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
# SSE (Server-Sent Events) YAYINCISI — gerçek zamanlı istemci bildirimi
# ================================================================
_sse_istemcileri: list = []


async def _sse_yayinla(olay_turu: str, veri: dict) -> None:
    payload = f"event: {olay_turu}\ndata: {json.dumps(veri, ensure_ascii=False, default=str)}\n\n"
    olum = []
    for q in list(_sse_istemcileri):
        try:
            await q.put(payload)
        except Exception:
            olum.append(q)
    for q in olum:
        try:
            _sse_istemcileri.remove(q)
        except ValueError:
            pass


app = FastAPI(title="PTS - Plaka Tanıma Sistemi", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=FRONTEND_KLASORU), name="static")
app.mount("/goruntuler", StaticFiles(directory=GORUNTU_KLASORU), name="goruntuler")


@app.on_event("startup")
async def _kameralari_otomatik_baslat():
    """Uygulama açılışında cameras.json'daki aktif kameralar için pipeline başlatır."""
    for kamera in _kameralari_oku():
        if kamera.get("aktif", True):
            _pipeline_baslat(kamera)

AUTH_SECRET_DOSYASI = os.path.join(BACKEND_DIR, "auth_secret.key")


def _auth_secret_al() -> str:
    """Ortam değişkeni yoksa gizli anahtar yerel dosyada kalıcı tutulur (yeniden başlatmada oturumların düşmemesi için)."""
    env_deger = os.getenv("PTS_AUTH_SECRET")
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


def _giris_gerekli(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> models.Kullanici:
    """Korumalı uç noktalar için geçerli oturum zorunluluğu."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Bearer token gerekli")
    kullanici = db.query(models.Kullanici).filter(models.Kullanici.id == _token_coz(authorization[7:].strip())).first()
    if not kullanici or not kullanici.aktif:
        raise HTTPException(401, "Kullanıcı hesabı aktif değil")
    return kullanici


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


@app.post("/auth/giris")
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
    logger.info("Başarılı giriş: %s", kullanici_adi)
    return {"token": _token_uret(kullanici.id), "kullanici": kullanici}


@app.get("/auth/me", response_model=schemas.KullaniciCevap)
def mevcut_kullanici(kullanici: models.Kullanici = Depends(_giris_gerekli)):
    return kullanici


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
    kaynak = f"{platform.node()}-{uuid.getnode()}-{platform.system()}"
    return hashlib.sha256(kaynak.encode("utf-8")).hexdigest()[:16].upper()


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
    durum = _lisans_durumunu_oku()
    if not durum.get("aktif"):
        return False
    bitis = durum.get("bitis_tarihi")
    if not bitis:
        return True
    try:
        return datetime.fromisoformat(bitis).date() >= datetime.now().date()
    except ValueError:
        return False


def _lisans_anahtarini_coz(anahtar: str) -> dict:
    try:
        versiyon, govde, imza = anahtar.strip().split(".", 2)
        if versiyon != "PTS1":
            raise ValueError
        secret = os.getenv("PTS_LICENSE_SECRET", "gelistirme-lisans-anahtari-degistir")
        beklenen = base64.urlsafe_b64encode(
            hmac.new(secret.encode("utf-8"), govde.encode("ascii"), hashlib.sha256).digest()
        ).decode("ascii").rstrip("=")
        if not hmac.compare_digest(imza, beklenen):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(govde + "=" * (-len(govde) % 4)))
        if payload.get("cihaz_kodu") and payload["cihaz_kodu"] != _cihaz_kodu():
            raise ValueError
        if datetime.fromisoformat(payload["bitis_tarihi"]).date() < datetime.now().date():
            raise ValueError
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(400, "Lisans anahtarı geçersiz veya süresi dolmuş")


def _lisans_durumunu_yaz(durum: dict) -> None:
    with open(LISANS_DOSYASI, "w", encoding="utf-8") as dosya:
        json.dump(durum, dosya, ensure_ascii=False, indent=2)


@app.get("/lisans")
def lisans_durumunu_getir(_: models.Kullanici = Depends(_giris_gerekli)):
    durum = _lisans_durumunu_oku()
    durum["aktif"] = _lisans_aktif_mi()
    return durum


@app.post("/lisans/aktive-et")
def lisans_aktive_et(istek: schemas.LisansAktivasyonIstegi, _: models.Kullanici = Depends(_giris_gerekli)):
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
    return durum


def _kameralari_oku() -> list:
    if not os.path.exists(KAMERA_DOSYASI):
        return []
    try:
        with open(KAMERA_DOSYASI, "r", encoding="utf-8") as dosya:
            return json.load(dosya)
    except (OSError, json.JSONDecodeError):
        return []


def _kameralari_yaz(kameralar: list) -> None:
    with open(KAMERA_DOSYASI, "w", encoding="utf-8") as dosya:
        json.dump(kameralar, dosya, ensure_ascii=False, indent=2)


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
def kameralari_getir(_: models.Kullanici = Depends(_giris_gerekli)):
    kameralar = _kameralari_oku()
    sonuclar = []
    for k in kameralar:
        gorunum = _kamera_guvenli_gorunum(k)
        gorunum["pipeline_calisiyor"] = k["id"] in _aktif_pipelineler and _aktif_pipelineler[k["id"]].calisiyor
        gorunum["kutuphaneler_mevcut"] = _CAM_LIBS
        sonuclar.append(gorunum)
    return sonuclar


@app.post("/kameralar/{kamera_id}/yeniden-baslat")
def kamera_yeniden_baslat(kamera_id: str, _: models.Kullanici = Depends(_giris_gerekli)):
    kamera = next((k for k in _kameralari_oku() if k["id"] == kamera_id), None)
    if not kamera:
        raise HTTPException(404, "Kamera bulunamadı")
    _pipeline_durdur(kamera_id)
    time.sleep(0.3)
    basarili = _pipeline_baslat(kamera)
    return {"basarili": basarili, "kutuphaneler_mevcut": _CAM_LIBS}


@app.patch("/kameralar/{kamera_id}/aktif")
def kamera_aktif_toggle(kamera_id: str, _: models.Kullanici = Depends(_giris_gerekli)):
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


@app.get("/kameralar/{kamera_id}/goruntu")
async def kamera_goruntu_al(kamera_id: str, _: models.Kullanici = Depends(_giris_gerekli)):
    """Kameradan anlık JPEG kare alır. Pipeline çalışıyorsa cached+annotated frame döner (sıfır gecikme)."""
    kamera = next((k for k in _kameralari_oku() if k["id"] == kamera_id), None)
    if not kamera:
        raise HTTPException(404, "Kamera bulunamadı")

    # Pipeline çalışıyorsa son annotated frame'i doğrudan dön (hızlı yol)
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


@app.get("/kameralar/{kamera_id}/son-plaka")
def kamera_son_plaka(kamera_id: str, _: models.Kullanici = Depends(_giris_gerekli)):
    """Pipeline'ın son tespit ettiği plaka(ları) döner (canlı overlay için)."""
    pipeline = _aktif_pipelineler.get(kamera_id)
    if not pipeline or not pipeline.calisiyor:
        return {"tespitler": []}
    return {"tespitler": pipeline.son_tespitler_al()}


@app.post("/kameralar")
def kamera_ekle(kamera: dict = Body(...), _: models.Kullanici = Depends(_giris_gerekli)):
    lisans = _lisans_durumunu_oku()
    kameralar = _kameralari_oku()
    if not _lisans_aktif_mi():
        raise HTTPException(403, "Kamera eklemek için aktif lisans gereklidir")
    if len(kameralar) >= lisans["kamera_limiti"]:
        raise HTTPException(403, "Aktif lisans kamera limitine ulaşıldı")
    gerekli_alanlar = ("ad", "rtsp_url", "yon")
    if any(not str(kamera.get(alan, "")).strip() for alan in gerekli_alanlar):
        raise HTTPException(400, "Kamera adı, RTSP adresi ve yön zorunludur")
    yeni_kamera = {
        "id": str(uuid.uuid4()),
        "ad": str(kamera["ad"]).strip(),
        "rtsp_url": str(kamera["rtsp_url"]).strip(),
        "yon": str(kamera["yon"]).strip(),
        "aktif": True,
    }
    kameralar.append(yeni_kamera)
    _kameralari_yaz(kameralar)
    _pipeline_baslat(yeni_kamera)
    return _kamera_guvenli_gorunum(yeni_kamera)


@app.delete("/kameralar/{kamera_id}")
def kamera_sil(kamera_id: str, _: models.Kullanici = Depends(_giris_gerekli)):
    kameralar = _kameralari_oku()
    yeni_kameralar = [kamera for kamera in kameralar if kamera["id"] != kamera_id]
    if len(yeni_kameralar) == len(kameralar):
        raise HTTPException(404, "Kamera bulunamadı")
    _kameralari_yaz(yeni_kameralar)
    _pipeline_durdur(kamera_id)
    return {"mesaj": "Kamera silindi"}


# ==================================================================
# SİTE VE NOKTA YÖNETİMİ
# ==================================================================

@app.post("/siteler", response_model=schemas.SiteCevap)
def site_ekle(site: schemas.SiteOlustur, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    if db.query(models.Site).filter(models.Site.ad == site.ad.strip()).first():
        raise HTTPException(409, "Bu site zaten kayıtlı")
    yeni_site = models.Site(ad=site.ad.strip(), aciklama=site.aciklama)
    db.add(yeni_site)
    db.commit()
    db.refresh(yeni_site)
    return yeni_site


@app.get("/siteler", response_model=List[schemas.SiteCevap])
def siteleri_listele(db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    return db.query(models.Site).order_by(models.Site.ad).all()


@app.delete("/siteler/{site_id}")
def site_sil(site_id: int, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    site = db.query(models.Site).filter(models.Site.id == site_id).first()
    if not site:
        raise HTTPException(404, "Site bulunamadı")
    db.delete(site)
    db.commit()
    return {"mesaj": "Site silindi"}


@app.post("/noktalar", response_model=schemas.NoktaCevap)
def nokta_ekle(nokta: schemas.NoktaOlustur, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    if not db.query(models.Site).filter(models.Site.id == nokta.site_id).first():
        raise HTTPException(404, "Bağlı site bulunamadı")
    yeni_nokta = models.Nokta(**nokta.model_dump())
    db.add(yeni_nokta)
    db.commit()
    db.refresh(yeni_nokta)
    return yeni_nokta


@app.get("/noktalar", response_model=List[schemas.NoktaCevap])
def noktalari_listele(site_id: Optional[int] = None, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    sorgu = db.query(models.Nokta)
    if site_id is not None:
        sorgu = sorgu.filter(models.Nokta.site_id == site_id)
    return sorgu.order_by(models.Nokta.ad).all()


@app.delete("/noktalar/{nokta_id}")
def nokta_sil(nokta_id: int, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
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
def kisi_ekle(kisi: schemas.KisiOlustur, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    yeni_kisi = models.Kisi(**kisi.model_dump())
    db.add(yeni_kisi)
    db.commit()
    db.refresh(yeni_kisi)
    return yeni_kisi


@app.get("/kisiler", response_model=List[schemas.KisiCevap])
def kisileri_listele(
    tip: Optional[str] = None,
    aktif: Optional[bool] = None,
    arama: Optional[str] = None,
    db: Session = Depends(get_db),
    _: models.Kullanici = Depends(_giris_gerekli),
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
    return sorgu.order_by(desc(models.Kisi.olusturma_tarihi)).all()


@app.get("/kisiler/{kisi_id}", response_model=schemas.KisiCevap)
def kisi_getir(kisi_id: int, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    kisi = db.query(models.Kisi).filter(models.Kisi.id == kisi_id).first()
    if not kisi:
        raise HTTPException(404, "Kişi bulunamadı")
    return kisi


@app.put("/kisiler/{kisi_id}", response_model=schemas.KisiCevap)
def kisi_guncelle(kisi_id: int, degisiklik: schemas.KisiGuncelle, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    kisi = db.query(models.Kisi).filter(models.Kisi.id == kisi_id).first()
    if not kisi:
        raise HTTPException(404, "Kişi bulunamadı")
    for alan, deger in degisiklik.model_dump(exclude_unset=True).items():
        setattr(kisi, alan, deger)
    db.commit()
    db.refresh(kisi)
    return kisi


@app.delete("/kisiler/{kisi_id}")
def kisi_sil(kisi_id: int, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    kisi = db.query(models.Kisi).filter(models.Kisi.id == kisi_id).first()
    if not kisi:
        raise HTTPException(404, "Kişi bulunamadı")
    db.query(models.Kayit).filter(models.Kayit.kisi_id == kisi_id).update({"kisi_id": None})
    db.delete(kisi)
    db.commit()
    return {"mesaj": "Kişi silindi"}


@app.get("/kisiler/{kisi_id}/plakalar", response_model=List[schemas.KisiPlakaCevap])
def kisi_plakalarini_listele(kisi_id: int, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    if not db.query(models.Kisi).filter(models.Kisi.id == kisi_id).first():
        raise HTTPException(404, "Kişi bulunamadı")
    return db.query(models.KisiPlaka).filter(models.KisiPlaka.kisi_id == kisi_id).all()


@app.post("/kisiler/{kisi_id}/plakalar", response_model=schemas.KisiPlakaCevap)
def kisi_plaka_ekle(kisi_id: int, istek: schemas.KisiPlakaOlustur, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    if not db.query(models.Kisi).filter(models.Kisi.id == kisi_id).first():
        raise HTTPException(404, "Kişi bulunamadı")
    yeni = models.KisiPlaka(kisi_id=kisi_id, plaka_no=istek.plaka_no, aciklama=istek.aciklama)
    db.add(yeni)
    db.commit()
    db.refresh(yeni)
    return yeni


@app.delete("/kisiler/{kisi_id}/plakalar/{plaka_id}")
def kisi_plaka_sil(kisi_id: int, plaka_id: int, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    kayit = db.query(models.KisiPlaka).filter(models.KisiPlaka.id == plaka_id, models.KisiPlaka.kisi_id == kisi_id).first()
    if not kayit:
        raise HTTPException(404, "Plaka kaydı bulunamadı")
    db.delete(kayit)
    db.commit()
    return {"mesaj": "Plaka silindi"}


# ==================================================================
# KARA LİSTESİ
# ==================================================================

@app.get("/kara-listesi", response_model=List[schemas.KaraListesiCevap])
def kara_listesini_getir(db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    return db.query(models.KaraListesi).order_by(desc(models.KaraListesi.olusturma_tarihi)).all()


@app.post("/kara-listesi", response_model=schemas.KaraListesiCevap)
def kara_listeye_ekle(istek: schemas.KaraListesiOlustur, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_giris_gerekli)):
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
def kara_listeden_cikar(kayit_id: int, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    kayit = db.query(models.KaraListesi).filter(models.KaraListesi.id == kayit_id).first()
    if not kayit:
        raise HTTPException(404, "Kayıt bulunamadı")
    db.delete(kayit)
    db.commit()
    return {"mesaj": "Kara listeden çıkarıldı"}


def _plaka_normalize(plaka: str) -> str:
    return plaka.upper().replace(" ", "").strip()


def _plaka_yetki_kontrol(db: Session, plaka_no: str):
    """Önce kara liste, sonra aktif kişiler + saat/gün kısıtlaması kontrol edilir."""
    simdi = datetime.now()
    hedef = _plaka_normalize(plaka_no)

    kara = db.query(models.KaraListesi).filter(
        models.KaraListesi.aktif == True,  # noqa: E712
        models.KaraListesi.plaka_no == hedef,
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
            models.KisiPlaka.plaka_no == hedef,
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
    try:
        if kisi.giris_saati_baslangic and kisi.giris_saati_bitis:
            simdi_hm = simdi.strftime("%H:%M")
            if not (kisi.giris_saati_baslangic <= simdi_hm <= kisi.giris_saati_bitis):
                return "yetkisiz", None, None
    except Exception:
        pass

    # Gün kısıtlaması (0=Pazartesi … 6=Pazar)
    try:
        if kisi.izin_verilen_gunler:
            izin = {int(g.strip()) for g in kisi.izin_verilen_gunler.split(",") if g.strip().isdigit()}
            if simdi.weekday() not in izin:
                return "yetkisiz", None, None
    except Exception:
        pass

    return "yetkili", kisi.id, kisi.tip


def _kayit_olustur_ve_bildir(db: Session, plaka_no: str, kamera_id: str, yon: str,
                              guven_skoru: Optional[float], goruntu_yolu: Optional[str]):
    plaka_no = re.sub(r"[^A-Za-z0-9 ]", "", plaka_no).strip().upper() or "BILINMEYEN"
    kamera_id = re.sub(r"[^A-Za-z0-9 _.\-]", "", str(kamera_id)).strip()[:50] or "KAMERA-1"
    yetki, kisi_id, kisi_tip = _plaka_yetki_kontrol(db, plaka_no)

    kayit = models.Kayit(
        plaka_no=plaka_no.upper().strip(),
        kamera_id=kamera_id,
        yon=yon,
        guven_skoru=guven_skoru,
        goruntu_yolu=goruntu_yolu,
        yetki_durumu=yetki,
        kisi_id=kisi_id,
        kisi_tip_anlik=kisi_tip,
    )
    db.add(kayit)
    db.commit()
    db.refresh(kayit)

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
                    db.add(models.Alarm(
                        kayit_id=kayit.id,
                        plaka_no=plaka_no,
                        alarm_tipi="supheli_arac",
                        mesaj=f"ŞÜPHELİ ARAÇ: {plaka_no} son 1 saatte {red_sayisi} kez reddedildi",
                    ))
                    logger.warning("Şüpheli araç: %s (%d red/saat)", plaka_no, red_sayisi)
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
            asyncio.ensure_future(_sse_yayinla("kayit", sse_veri))
            asyncio.ensure_future(_webhook_bildir(db, yetki, sse_veri))
    except RuntimeError:
        pass

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


async def _webhook_bildir(db: Session, yetki_durumu: str, veri: dict) -> None:
    """Tetikleyiciye uyan aktif webhook kayıtlarına bildirim gönderir."""
    try:
        ayarlar = db.query(models.BildirimAyarlari).filter(
            models.BildirimAyarlari.aktif == True,  # noqa: E712
            models.BildirimAyarlari.tip == "webhook",
        ).all()
        loop = asyncio.get_event_loop()
        for a in ayarlar:
            tetik = a.tetikleyici
            if tetik != "hepsi" and tetik != yetki_durumu:
                continue
            loop.run_in_executor(None, _webhook_gonder_sync, a.hedef, a.http_metot, veri)
    except Exception as exc:
        logger.error("Webhook bildirim hatası: %s", exc)


@app.post("/kayitlar", response_model=schemas.KayitCevap)
def kayit_ekle_manuel(kayit: schemas.KayitManuel, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    """Elle / test amaçlı kayıt ekleme (görsel olmadan). Panel üzerindeki 'Test Kaydı Ekle' formu bunu kullanır."""
    return _kayit_olustur_ve_bildir(
        db, kayit.plaka_no, kayit.kamera_id, kayit.yon, kayit.guven_skoru, None
    )


@app.post("/kayitlar/otomatik", response_model=schemas.KayitCevap)
async def kayit_ekle_otomatik(
    plaka_no: str = Form(...),
    kamera_id: str = Form("KAMERA-1"),
    yon: str = Form("giris"),
    guven_skoru: Optional[float] = Form(None),
    gorsel: Optional[UploadFile] = File(None),
    x_pts_kamera_anahtari: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Gerçek kamera pipeline'ının veya harici bir sistemin görsel ile kayıt gönderdiği uç nokta.

    Kullanıcı oturumu gerektirmez (kameralar giriş yapamaz); bunun yerine PTS_KAMERA_ANAHTARI ortam
    değişkeni ayarlıysa X-PTS-Kamera-Anahtari başlığıyla eşleşmesi zorunlu tutulur.
    """
    beklenen_anahtar = os.getenv("PTS_KAMERA_ANAHTARI")
    if beklenen_anahtar and x_pts_kamera_anahtari != beklenen_anahtar:
        raise HTTPException(401, "Geçersiz kamera anahtarı")

    goruntu_yolu = None
    if gorsel is not None:
        # Dosya adı kullanıcı girdisinden (plaka_no) üretildiği için yalnızca güvenli karakterler bırakılır (path traversal önlemi).
        guvenli_plaka = re.sub(r"[^A-Za-z0-9]", "", plaka_no) or "PLAKA"
        dosya_adi = f"{guvenli_plaka}_{int(datetime.now().timestamp())}.jpg"
        goruntu_yolu = os.path.join(GORUNTU_KLASORU, dosya_adi)
        with open(goruntu_yolu, "wb") as f:
            shutil.copyfileobj(gorsel.file, f)

    return _kayit_olustur_ve_bildir(db, plaka_no, kamera_id, yon, guven_skoru, goruntu_yolu)


@app.get("/kayitlar", response_model=List[schemas.KayitCevap])
def kayitlari_listele(
    plaka: Optional[str] = None,
    baslangic: Optional[str] = None,
    bitis: Optional[str] = None,
    yetki_durumu: Optional[str] = None,
    kamera_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: models.Kullanici = Depends(_giris_gerekli),
):
    sorgu = db.query(models.Kayit)
    if plaka:
        sorgu = sorgu.filter(models.Kayit.plaka_no.ilike(f"%{plaka}%"))
    if yetki_durumu:
        sorgu = sorgu.filter(models.Kayit.yetki_durumu == yetki_durumu)
    if kamera_id:
        sorgu = sorgu.filter(models.Kayit.kamera_id.ilike(f"%{kamera_id}%"))
    if baslangic:
        sorgu = sorgu.filter(models.Kayit.tarih_saat >= datetime.fromisoformat(baslangic))
    if bitis:
        sorgu = sorgu.filter(
            models.Kayit.tarih_saat <= datetime.fromisoformat(bitis) + timedelta(days=1)
        )
    toplam = sorgu.count()
    kayitlar = sorgu.order_by(desc(models.Kayit.tarih_saat)).offset(max(0, offset)).limit(min(limit, 500)).all()
    return kayitlar


@app.get("/kayitlar/sayfa-bilgisi")
def kayitlar_sayfa_bilgisi(
    plaka: Optional[str] = None,
    baslangic: Optional[str] = None,
    bitis: Optional[str] = None,
    yetki_durumu: Optional[str] = None,
    kamera_id: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: models.Kullanici = Depends(_giris_gerekli),
):
    """Sayfalama için toplam kayıt sayısını döndürür."""
    sorgu = db.query(models.Kayit)
    if plaka:
        sorgu = sorgu.filter(models.Kayit.plaka_no.ilike(f"%{plaka}%"))
    if yetki_durumu:
        sorgu = sorgu.filter(models.Kayit.yetki_durumu == yetki_durumu)
    if kamera_id:
        sorgu = sorgu.filter(models.Kayit.kamera_id.ilike(f"%{kamera_id}%"))
    if baslangic:
        sorgu = sorgu.filter(models.Kayit.tarih_saat >= datetime.fromisoformat(baslangic))
    if bitis:
        sorgu = sorgu.filter(models.Kayit.tarih_saat <= datetime.fromisoformat(bitis) + timedelta(days=1))
    toplam = sorgu.count()
    sayfa_sayisi = max(1, -(-toplam // max(1, limit)))
    return {"toplam": toplam, "sayfa_sayisi": sayfa_sayisi, "limit": limit}


@app.get("/olaylar", response_model=List[schemas.KayitCevap])
def olaylari_getir(since_id: int = 0, limit: int = 100, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    """Canlı ekran için son olayları veya verilen ID'den sonrasını döndürür."""
    sorgu = db.query(models.Kayit).filter(models.Kayit.id > since_id)
    return sorgu.order_by(desc(models.Kayit.id)).limit(min(limit, 500)).all()


@app.get("/alarmlar", response_model=List[schemas.AlarmCevap])
def alarmlari_listele(
    sadece_acik: bool = False,
    alarm_tipi: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: models.Kullanici = Depends(_giris_gerekli),
):
    sorgu = db.query(models.Alarm)
    if sadece_acik:
        sorgu = sorgu.filter(models.Alarm.okundu == False)  # noqa: E712
    if alarm_tipi:
        sorgu = sorgu.filter(models.Alarm.alarm_tipi == alarm_tipi)
    return sorgu.order_by(desc(models.Alarm.tarih_saat)).limit(min(limit, 500)).all()


@app.patch("/alarmlar/{alarm_id}/okundu", response_model=schemas.AlarmCevap)
def alarmi_okundu_isaretle(alarm_id: int, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    alarm = db.query(models.Alarm).filter(models.Alarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(404, "Alarm bulunamadı")
    alarm.okundu = True
    db.commit()
    db.refresh(alarm)
    return alarm


@app.post("/alarmlar/tumu-okundu")
def tum_alarmlari_okundu_isaretle(db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    guncellenen = db.query(models.Alarm).filter(models.Alarm.okundu == False).update({"okundu": True})  # noqa: E712
    db.commit()
    return {"guncellenen": guncellenen}


@app.delete("/kayitlar/{kayit_id}")
def kayit_sil(kayit_id: int, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    kayit = db.query(models.Kayit).filter(models.Kayit.id == kayit_id).first()
    if not kayit:
        raise HTTPException(404, "Kayıt bulunamadı")
    # Alarm günlüğü korunur; sadece silinecek kayda olan bağlantı koparılır (FK ihlalini önler).
    db.query(models.Alarm).filter(models.Alarm.kayit_id == kayit_id).update({"kayit_id": None})
    db.delete(kayit)
    db.commit()
    return {"mesaj": "Kayıt silindi"}


@app.get("/kayitlar/istatistik")
def istatistikler(db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    bugun = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    toplam = db.query(models.Kayit).count()
    bugunku = db.query(models.Kayit).filter(models.Kayit.tarih_saat >= bugun).count()
    yetkisiz = db.query(models.Kayit).filter(models.Kayit.yetki_durumu == "yetkisiz").count()
    kara_liste_gecis = db.query(models.Kayit).filter(models.Kayit.yetki_durumu == "kara_liste").count()
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
def grafik_verisi(gun: int = 7, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    """Son N günlük istatistik — dashboard grafikleri için."""
    baslangic = datetime.now() - timedelta(days=max(1, min(gun, 90)))
    kayitlar = db.query(models.Kayit).filter(models.Kayit.tarih_saat >= baslangic).all()

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


@app.get("/kayitlar/analiz/{plaka_no}")
def plaka_analiz(plaka_no: str, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    """Bir plaka için geçiş geçmişi, kişi bilgisi ve kara liste durumu."""
    hedef = _plaka_normalize(plaka_no)
    kayitlar = (db.query(models.Kayit)
                .filter(models.Kayit.plaka_no == hedef)
                .order_by(desc(models.Kayit.tarih_saat))
                .limit(50).all())
    kisi = None
    for k in db.query(models.Kisi).filter(models.Kisi.aktif == True).all():  # noqa: E712
        if _plaka_normalize(k.plaka_no) == hedef:
            kisi = k
            break
    if not kisi:
        ek = db.query(models.KisiPlaka).filter(models.KisiPlaka.plaka_no == hedef, models.KisiPlaka.aktif == True).first()  # noqa: E712
        if ek:
            kisi = db.query(models.Kisi).filter(models.Kisi.id == ek.kisi_id).first()
    kara = db.query(models.KaraListesi).filter(models.KaraListesi.plaka_no == hedef, models.KaraListesi.aktif == True).first()  # noqa: E712
    return {
        "plaka_no": hedef,
        "toplam_gecis": len(kayitlar),
        "son_gecis": kayitlar[0].tarih_saat.isoformat() if kayitlar else None,
        "kisi": {"id": kisi.id, "ad_soyad": kisi.ad_soyad, "tip": kisi.tip, "telefon": kisi.telefon} if kisi else None,
        "kara_listesinde": kara is not None,
        "kara_sebep": kara.sebep if kara else None,
        "son_kayitlar": [
            {"id": k.id, "tarih_saat": k.tarih_saat.isoformat(), "yon": k.yon,
             "yetki_durumu": k.yetki_durumu, "kamera_id": k.kamera_id}
            for k in kayitlar[:15]
        ],
    }


@app.get("/olaylar/sse")
async def sse_baglantisi(request: Request, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """Server-Sent Events — yeni plaka geçişlerini anlık olarak istemciye iletir."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Bearer token gerekli")
    _token_coz(authorization[7:].strip())  # token geçerliliği kontrol edilir

    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _sse_istemcileri.append(q)

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
                _sse_istemcileri.remove(q)
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

@app.get("/disa-aktar/excel/kayitlar")
def kayitlari_excel_indir(
    plaka: Optional[str] = None, baslangic: Optional[str] = None,
    bitis: Optional[str] = None, db: Session = Depends(get_db),
):
    kayitlar = kayitlari_listele(
        plaka=plaka, baslangic=baslangic, bitis=bitis, yetki_durumu=None, limit=5000, db=db
    )
    dosya_yolu = os.path.join(DISA_AKTAR_KLASORU, f"pts_kayitlar_{int(datetime.now().timestamp())}.xlsx")
    excel_export.kayitlar_excel_olustur(kayitlar, dosya_yolu)
    return FileResponse(
        dosya_yolu, filename="pts_kayitlari.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/disa-aktar/pdf/kayitlar")
def kayitlari_pdf_indir(
    plaka: Optional[str] = None, baslangic: Optional[str] = None,
    bitis: Optional[str] = None, db: Session = Depends(get_db),
):
    kayitlar = kayitlari_listele(
        plaka=plaka, baslangic=baslangic, bitis=bitis, yetki_durumu=None, limit=2000, db=db
    )
    dosya_yolu = os.path.join(DISA_AKTAR_KLASORU, f"pts_kayitlar_{int(datetime.now().timestamp())}.pdf")
    pdf_export.kayitlar_pdf_olustur(kayitlar, dosya_yolu)
    return FileResponse(dosya_yolu, filename="pts_kayitlari.pdf", media_type="application/pdf")


@app.get("/disa-aktar/pdf/kayit/{kayit_id}")
def kayit_detay_pdf_indir(kayit_id: int, db: Session = Depends(get_db)):
    """Tek bir kaydı, araç görseliyle birlikte PDF olarak indirir."""
    kayit = db.query(models.Kayit).filter(models.Kayit.id == kayit_id).first()
    if not kayit:
        raise HTTPException(404, "Kayıt bulunamadı")
    dosya_yolu = os.path.join(DISA_AKTAR_KLASORU, f"kayit_{kayit_id}.pdf")
    pdf_export.kayit_detay_pdf_olustur(kayit, dosya_yolu)
    return FileResponse(dosya_yolu, filename=f"kayit_{kayit_id}.pdf", media_type="application/pdf")


@app.get("/disa-aktar/excel/kisiler")
def kisileri_excel_indir(tip: Optional[str] = None, db: Session = Depends(get_db)):
    kisiler = kisileri_listele(tip=tip, aktif=None, arama=None, db=db)
    dosya_yolu = os.path.join(DISA_AKTAR_KLASORU, f"pts_kisiler_{int(datetime.now().timestamp())}.xlsx")
    excel_export.kisiler_excel_olustur(kisiler, dosya_yolu)
    return FileResponse(
        dosya_yolu, filename="pts_kisiler.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ==================================================================
# LED PANEL AYARLARI
# ==================================================================

@app.get("/led/ayarlar")
def led_ayarlarini_getir(_: models.Kullanici = Depends(_giris_gerekli)):
    return led_panel.ayarlari_oku()


@app.put("/led/ayarlar")
def led_ayarlarini_guncelle(ayarlar: dict, _: models.Kullanici = Depends(_giris_gerekli)):
    mevcut = led_panel.ayarlari_oku()
    mevcut.update(ayarlar)
    led_panel.ayarlari_kaydet(mevcut)
    return mevcut


@app.post("/led/test")
def led_test_mesaji(mesaj: str = Query("PTS SİSTEMİ TEST MESAJI"), _: models.Kullanici = Depends(_giris_gerekli)):
    basarili = led_panel.led_mesaj_gonder(mesaj)
    return {"basarili": basarili, "mesaj": mesaj}


# ==================================================================
# KULLANICI YÖNETİMİ
# ==================================================================

@app.get("/auth/me", response_model=schemas.KullaniciCevap)
def beni_getir(kullanici: models.Kullanici = Depends(_giris_gerekli)):
    return kullanici


@app.get("/kullanicilar", response_model=List[schemas.KullaniciCevap])
def kullanicilari_listele(db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_giris_gerekli)):
    if kullanici.rol != "yonetici":
        raise HTTPException(403, "Sadece yönetici görebilir")
    return db.query(models.Kullanici).order_by(models.Kullanici.olusturma_tarihi).all()


@app.post("/kullanicilar", response_model=schemas.KullaniciCevap)
def kullanici_ekle(istek: schemas.KullaniciOlustur, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_giris_gerekli)):
    if kullanici.rol != "yonetici":
        raise HTTPException(403, "Sadece yönetici kullanıcı ekleyebilir")
    if db.query(models.Kullanici).filter(models.Kullanici.kullanici_adi == istek.kullanici_adi).first():
        raise HTTPException(409, "Bu kullanıcı adı zaten kullanımda")
    yeni = models.Kullanici(
        kullanici_adi=istek.kullanici_adi.strip(),
        parola_hash=_parola_hashle(istek.parola),
        rol=istek.rol,
    )
    db.add(yeni)
    db.commit()
    db.refresh(yeni)
    logger.info("Yeni kullanıcı oluşturuldu: %s (ekleyen: %s)", istek.kullanici_adi, kullanici.kullanici_adi)
    return yeni


@app.put("/kullanicilar/{kullanici_id}", response_model=schemas.KullaniciCevap)
def kullanici_guncelle(kullanici_id: int, istek: schemas.KullaniciGuncelle, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_giris_gerekli)):
    if kullanici.rol != "yonetici":
        raise HTTPException(403, "Sadece yönetici düzenleyebilir")
    hedef = db.query(models.Kullanici).filter(models.Kullanici.id == kullanici_id).first()
    if not hedef:
        raise HTTPException(404, "Kullanıcı bulunamadı")
    if istek.rol is not None:
        hedef.rol = istek.rol
    if istek.aktif is not None:
        if hedef.id == kullanici.id:
            raise HTTPException(400, "Kendinizi pasif yapamazsınız")
        hedef.aktif = istek.aktif
    if istek.parola:
        hedef.parola_hash = _parola_hashle(istek.parola)
    db.commit()
    db.refresh(hedef)
    return hedef


@app.delete("/kullanicilar/{kullanici_id}")
def kullanici_sil(kullanici_id: int, db: Session = Depends(get_db), kullanici: models.Kullanici = Depends(_giris_gerekli)):
    if kullanici.rol != "yonetici":
        raise HTTPException(403, "Sadece yönetici silebilir")
    hedef = db.query(models.Kullanici).filter(models.Kullanici.id == kullanici_id).first()
    if not hedef:
        raise HTTPException(404, "Kullanıcı bulunamadı")
    if hedef.id == kullanici.id:
        raise HTTPException(400, "Kendi hesabınızı silemezsiniz")
    db.delete(hedef)
    db.commit()
    return {"mesaj": "Kullanıcı silindi"}


# ==================================================================
# BARİYER KONTROLÜ
# ==================================================================

@app.get("/bariyer/ayarlar")
def bariyer_ayarlarini_getir(db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    return db.query(models.BariyerAyarlari).all()


@app.post("/bariyer/ayarlar")
def bariyer_ekle(istek: dict = Body(...), db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    yeni = models.BariyerAyarlari(
        ad=str(istek.get("ad", "Bariyer")).strip()[:80],
        mod=str(istek.get("mod", "simulate")),
        http_url=istek.get("http_url"),
        http_metot=str(istek.get("http_metot", "GET")),
        http_govde=istek.get("http_govde"),
        gpio_pin=istek.get("gpio_pin"),
    )
    db.add(yeni)
    db.commit()
    db.refresh(yeni)
    return yeni


@app.post("/bariyer/{bariyer_id}/ac")
def bariyer_ac(bariyer_id: int, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    bariyer = db.query(models.BariyerAyarlari).filter(models.BariyerAyarlari.id == bariyer_id, models.BariyerAyarlari.aktif == True).first()  # noqa: E712
    if not bariyer:
        raise HTTPException(404, "Bariyer bulunamadı")

    if bariyer.mod == "simulate":
        logger.info("Bariyer açıldı (simülasyon): %s", bariyer.ad)
        return {"basarili": True, "mod": "simulate", "mesaj": f"{bariyer.ad} açıldı (simülasyon)"}

    if bariyer.mod == "http":
        try:
            import urllib.request
            govde = (bariyer.http_govde or "").encode("utf-8") or None
            req = urllib.request.Request(bariyer.http_url, data=govde, method=bariyer.http_metot)
            with urllib.request.urlopen(req, timeout=5):
                pass
            logger.info("Bariyer HTTP komutu gönderildi: %s", bariyer.ad)
            return {"basarili": True, "mod": "http", "mesaj": f"{bariyer.ad} komutu gönderildi"}
        except Exception as exc:
            logger.error("Bariyer HTTP hatası %s: %s", bariyer.ad, exc)
            raise HTTPException(503, f"Bariyer komutuna yanıt alınamadı: {exc}")

    raise HTTPException(400, f"Desteklenmeyen bariyer modu: {bariyer.mod}")


@app.delete("/bariyer/ayarlar/{bariyer_id}")
def bariyer_sil(bariyer_id: int, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    b = db.query(models.BariyerAyarlari).filter(models.BariyerAyarlari.id == bariyer_id).first()
    if not b:
        raise HTTPException(404, "Bariyer bulunamadı")
    db.delete(b)
    db.commit()
    return {"mesaj": "Bariyer silindi"}


# ==================================================================
# SİSTEM SAĞLIĞI VE LOG
# ==================================================================

@app.get("/sistem/saglik")
async def sistem_sagligi(db: Session = Depends(get_db)):
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
        "surum": "2.0",
    }


@app.get("/sistem/loglar")
def son_loglari_getir(satir: int = 200, _: models.Kullanici = Depends(_giris_gerekli)):
    log_dosyasi = os.path.join(LOG_KLASORU, "pts.log")
    if not os.path.exists(log_dosyasi):
        return {"satirlar": []}
    try:
        with open(log_dosyasi, "r", encoding="utf-8", errors="replace") as f:
            tum = f.readlines()
        return {"satirlar": [s.rstrip() for s in tum[-min(satir, 500):]]}
    except OSError:
        return {"satirlar": []}


# ==================================================================
# BİLDİRİM AYARLARI (Webhook)
# ==================================================================

@app.get("/bildirim/ayarlar")
def bildirim_ayarlarini_getir(db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    return db.query(models.BildirimAyarlari).order_by(models.BildirimAyarlari.olusturma_tarihi).all()


@app.post("/bildirim/ayarlar")
def bildirim_ayari_ekle(istek: dict = Body(...), db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    ad = re.sub(r"[<>&\"']", "", str(istek.get("ad", "Bildirim"))).strip()[:80] or "Bildirim"
    hedef = str(istek.get("hedef", "")).strip()
    if not hedef:
        raise HTTPException(400, "Hedef URL boş olamaz")
    yeni = models.BildirimAyarlari(
        ad=ad,
        tip=str(istek.get("tip", "webhook")),
        hedef=hedef,
        tetikleyici=str(istek.get("tetikleyici", "hepsi")),
        http_metot=str(istek.get("http_metot", "POST")),
    )
    db.add(yeni)
    db.commit()
    db.refresh(yeni)
    return yeni


@app.patch("/bildirim/ayarlar/{ayar_id}/aktif")
def bildirim_aktif_toggle(ayar_id: int, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    ayar = db.query(models.BildirimAyarlari).filter(models.BildirimAyarlari.id == ayar_id).first()
    if not ayar:
        raise HTTPException(404, "Ayar bulunamadı")
    ayar.aktif = not ayar.aktif
    db.commit()
    return {"id": ayar.id, "aktif": ayar.aktif}


@app.delete("/bildirim/ayarlar/{ayar_id}")
def bildirim_ayari_sil(ayar_id: int, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    ayar = db.query(models.BildirimAyarlari).filter(models.BildirimAyarlari.id == ayar_id).first()
    if not ayar:
        raise HTTPException(404, "Ayar bulunamadı")
    db.delete(ayar)
    db.commit()
    return {"mesaj": "Bildirim ayarı silindi"}


@app.post("/bildirim/test/{ayar_id}")
async def bildirim_test_gonder(ayar_id: int, db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
    ayar = db.query(models.BildirimAyarlari).filter(models.BildirimAyarlari.id == ayar_id).first()
    if not ayar:
        raise HTTPException(404, "Ayar bulunamadı")
    test_veri = {"test": True, "mesaj": "PTS test bildirimi", "zaman": datetime.now().isoformat()}
    basarili = await asyncio.get_event_loop().run_in_executor(
        None, _webhook_gonder_sync, ayar.hedef, ayar.http_metot, test_veri
    )
    return {"basarili": basarili, "hedef": ayar.hedef}


# ==================================================================
# KAMERA SAĞLIK KONTROLÜ
# ==================================================================

@app.get("/kameralar/{kamera_id}/saglik")
async def kamera_saglik_kontrol(kamera_id: str, _: models.Kullanici = Depends(_giris_gerekli)):
    """Kameranın TCP portuna bağlanabilirliğini ve pipeline durumunu raporlar."""
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

    pipeline_calisiyor = kamera_id in _aktif_pipelineler and _aktif_pipelineler[kamera_id].calisiyor
    return {
        "id": kamera_id,
        "ad": kamera["ad"],
        "host": host,
        "port": port,
        "tcp_erisim": tcp_ok,
        "gecikme_ms": gecikme_ms,
        "pipeline_calisiyor": pipeline_calisiyor,
        "rtsp_url_maskelendi": _kamera_guvenli_gorunum(kamera)["rtsp_url"],
    }


@app.get("/kameralar/saglik/tumu")
async def tum_kameralar_saglik(_: models.Kullanici = Depends(_giris_gerekli)):
    """Tüm kameralar için sağlık kontrolü — toplu sorgu."""
    kameralar = _kameralari_oku()
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
        sonuclar.append({
            "id": k["id"],
            "ad": k["ad"],
            "tcp_erisim": tcp_ok,
            "gecikme_ms": gecikme_ms,
            "pipeline_calisiyor": k["id"] in _aktif_pipelineler and _aktif_pipelineler[k["id"]].calisiyor,
        })
    return sonuclar


# ==================================================================
# TOPLU İÇE AKTARMA (Excel'den kişi ekleme)
# ==================================================================

@app.post("/kisiler/toplu-import")
async def toplu_kisi_import(
    dosya: UploadFile = File(...),
    db: Session = Depends(get_db),
    kullanici: models.Kullanici = Depends(_giris_gerekli),
):
    """
    Excel (.xlsx) dosyasından toplu kişi içe aktarır.
    Beklenen sütunlar: ad_soyad, plaka_no, tip, telefon, daire_departman
    İlk satır başlık satırı olmalıdır.
    """
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
    hatalar = []
    GECERLI_TIPLER = ("abone", "personel", "ziyaretci")

    for satir_no, satir in enumerate(satirlar[1:], start=2):
        try:
            ad_soyad = str(satir[alan_indeksi["ad_soyad"]] or "").strip()
            plaka_no = str(satir[alan_indeksi["plaka_no"]] or "").strip().upper()
            tip = str(satir[alan_indeksi["tip"]] or "").strip().lower()

            if not ad_soyad or not plaka_no:
                hatalar.append(f"Satır {satir_no}: ad_soyad veya plaka_no boş")
                continue
            if tip not in GECERLI_TIPLER:
                tip = "abone"

            telefon = str(satir[alan_indeksi["telefon"]] or "").strip() if "telefon" in alan_indeksi else None
            daire = str(satir[alan_indeksi["daire_departman"]] or "").strip() if "daire_departman" in alan_indeksi else None

            # Plaka sütunundaki formül enjeksiyon karakterlerini temizle
            plaka_no = re.sub(r"[^A-Za-z0-9 ]", "", plaka_no)[:15]

            yeni = models.Kisi(
                ad_soyad=ad_soyad[:100],
                plaka_no=plaka_no,
                tip=tip,
                telefon=telefon[:20] if telefon else None,
                daire_departman=daire[:50] if daire else None,
            )
            db.add(yeni)
            eklendi += 1
        except Exception as exc:
            hatalar.append(f"Satır {satir_no}: {exc}")

    if eklendi:
        db.commit()
        logger.info("Toplu import: %d kişi eklendi (kullanıcı: %s)", eklendi, kullanici.kullanici_adi)

    return {"eklendi": eklendi, "hatalar": hatalar[:20]}


# ==================================================================
# SİSTEM AYARLARI
# ==================================================================

@app.get("/sistem/ayarlar")
def sistem_ayarlarini_getir(_: models.Kullanici = Depends(_giris_gerekli)):
    return _sistem_ayarlari_oku()


@app.put("/sistem/ayarlar")
def sistem_ayarlarini_guncelle(yeni: dict = Body(...), kullanici: models.Kullanici = Depends(_giris_gerekli)):
    if kullanici.rol != "yonetici":
        raise HTTPException(403, "Sadece yönetici değiştirebilir")
    mevcut = _sistem_ayarlari_oku()
    for k, v in yeni.items():
        if k in _VARSAYILAN_AYARLAR:
            mevcut[k] = v
    _sistem_ayarlari_yaz(mevcut)
    return mevcut


# ==================================================================
# ARAÇ İÇERİDE / DIŞARIDA TAKİBİ
# ==================================================================

@app.get("/araclar/iceridedurum")
def araclar_iceridedurum(db: Session = Depends(get_db), _: models.Kullanici = Depends(_giris_gerekli)):
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
def disk_kullanimi(_: models.Kullanici = Depends(_giris_gerekli)):
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
    return {"goruntu_mb": round(toplam_mb, 2), "goruntu_sayisi": dosya_sayisi}


@app.post("/sistem/goruntu-temizle")
def goruntu_temizle(gun: int = Query(30, ge=1, le=365), kullanici: models.Kullanici = Depends(_giris_gerekli), db: Session = Depends(get_db)):
    if kullanici.rol not in ("yonetici", "operatör"):
        raise HTTPException(403, "Yetki yetersiz")
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
            kayit.goruntu_yolu = None
        except OSError:
            pass
    db.commit()
    logger.info("Görüntü temizliği: %d dosya silindi (>%d gün)", silinen, gun)
    return {"silinen_goruntu": silinen, "sinir_tarihi": sinir.isoformat()}


@app.get("/sistem/yedek")
def veritabani_yedek(kullanici: models.Kullanici = Depends(_giris_gerekli)):
    if kullanici.rol != "yonetici":
        raise HTTPException(403, "Sadece yönetici indirebilir")
    if not SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        raise HTTPException(400, "Otomatik yedek sadece SQLite için desteklenir. SQL Server için veritabanı yönetim araçlarını kullanın.")
    from urllib.parse import urlparse
    db_yolu = urlparse(SQLALCHEMY_DATABASE_URL).path.lstrip("/")
    if not os.path.exists(db_yolu):
        raise HTTPException(404, "Veritabanı dosyası bulunamadı")
    zaman_damgasi = datetime.now().strftime("%Y%m%d_%H%M%S")
    dosya_adi = f"pts_yedek_{zaman_damgasi}.db"
    return FileResponse(db_yolu, filename=dosya_adi, media_type="application/octet-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
