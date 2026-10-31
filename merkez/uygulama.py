"""PTS Merkezi İzleme sunucusu (2026-10-31).

Müşteri kurulumları birkaç dakikada bir sağlık özetini `POST /api/nabiz`'e
gönderir (başlıkta `X-Kurulum-Anahtari`). Pano (`/`) tüm kurulumları sorun
önceliğine göre listeler; yeni çıkan ya da düzelen sorunlar Telegram/e-postayla
bildirilir. Plaka/kişi verisi gelmez; gelirse kaydedilmez (bkz. _YASAKLI).

Çalıştırma (ayrıntı: merkez/README.md):
  MERKEZ_YONETICI_PAROLA=... uvicorn merkez.uygulama:app --host 127.0.0.1 --port 8100
"""
import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse

from merkez import bildirim
from merkez.sorunlar import genel_durum, sorunlari_hesapla

logger = logging.getLogger("merkez")
KLASOR = os.path.dirname(os.path.abspath(__file__))
EN_BUYUK_OZET = 256 * 1024
NABIZ_SAKLAMA_GUN = 8
ERISIM_DILIM_SN = 300
BILDIRIM_ARALIK_SN = 60
_YASAKLI = {"plaka", "plaka_no", "kisi", "kisi_adi", "ad_soyad", "misafir_adi", "telefon", "tc", "tc_no",
            "foto", "fotograf", "goruntu_yolu", "jpeg", "not_metni", "kayitlar"}

app = FastAPI(title="PTS Merkezi İzleme", docs_url=None, redoc_url=None, openapi_url=None)
_db_kilit = threading.Lock()


# ------------------------------------------------------------------ veritabanı
def _db_yolu() -> str:
    return os.getenv("MERKEZ_VERITABANI") or os.path.join(KLASOR, "merkez.db")


_SEMA = """
CREATE TABLE IF NOT EXISTS kurulumlar (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ad TEXT NOT NULL,
  anahtar_ozeti TEXT NOT NULL UNIQUE,
  etkin INTEGER NOT NULL DEFAULT 1,
  iletisim TEXT DEFAULT '',
  bakim_bitis TEXT DEFAULT '',
  notlar TEXT DEFAULT '',
  olusturma REAL NOT NULL,
  son_nabiz REAL,
  ilk_nabiz REAL,
  son_ip TEXT,
  son_ozet TEXT,
  bildirim_durumu TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS nabizlar (
  kurulum_id INTEGER NOT NULL,
  zaman REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_nabiz ON nabizlar(kurulum_id, zaman);
CREATE TABLE IF NOT EXISTS olaylar (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kurulum_id INTEGER NOT NULL,
  zaman REAL NOT NULL,
  tur TEXT NOT NULL,
  seviye TEXT,
  mesaj TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_olay ON olaylar(kurulum_id, zaman);
"""


@contextmanager
def _db():
    with _db_kilit:
        bag = sqlite3.connect(_db_yolu())
        bag.row_factory = sqlite3.Row
        try:
            bag.executescript(_SEMA)
            yield bag
            bag.commit()
        finally:
            bag.close()


def _ozet_al(anahtar: str) -> str:
    return hashlib.sha256(anahtar.encode()).hexdigest()


# ------------------------------------------------------------------ yönetici girişi
_hatali_giris: dict = {}   # ip -> (sayı, ilk zaman)
_KILIT_SAYI, _KILIT_SN = 10, 900


def yonetici(request: Request, authorization: Optional[str] = Header(None)) -> str:
    """HTTP Basic: kullanıcı MERKEZ_YONETICI_KULLANICI (varsayılan "yonetici"),
    parola MERKEZ_YONETICI_PAROLA. Aynı adresten 10 hatalı denemede 15 dk kilit."""
    parola = os.getenv("MERKEZ_YONETICI_PAROLA") or ""
    if len(parola) < 10:
        raise HTTPException(503, "MERKEZ_YONETICI_PAROLA ortam değişkeni ayarlanmamış (en az 10 karakter).")
    ip = request.client.host if request.client else "?"
    sayi, ilk = _hatali_giris.get(ip, (0, time.time()))
    if time.time() - ilk > _KILIT_SN:
        sayi, ilk = 0, time.time()
    if sayi >= _KILIT_SAYI:
        raise HTTPException(429, "Çok fazla hatalı giriş; 15 dakika sonra deneyin.")
    kullanici, verilen = "", ""
    if authorization and authorization.lower().startswith("basic "):
        try:
            kullanici, _, verilen = base64.b64decode(authorization[6:]).decode("utf-8").partition(":")
        except (ValueError, UnicodeDecodeError):
            pass
    beklenen_kullanici = os.getenv("MERKEZ_YONETICI_KULLANICI") or "yonetici"
    if not (secrets.compare_digest(kullanici.encode(), beklenen_kullanici.encode())
            and secrets.compare_digest(verilen.encode(), parola.encode())):
        if authorization:
            _hatali_giris[ip] = (sayi + 1, ilk)
        raise HTTPException(401, "Giriş gerekli", headers={"WWW-Authenticate": 'Basic realm="PTS Merkez", charset="UTF-8"'})
    _hatali_giris.pop(ip, None)
    return kullanici


# ------------------------------------------------------------------ nabız
def _yasakli_temizle(veri):
    if isinstance(veri, dict):
        return {k: _yasakli_temizle(v) for k, v in veri.items() if str(k).lower() not in _YASAKLI}
    if isinstance(veri, list):
        return [_yasakli_temizle(v) for v in veri]
    return veri


@app.post("/api/nabiz")
async def nabiz(request: Request, x_kurulum_anahtari: Optional[str] = Header(None)):
    if not x_kurulum_anahtari:
        raise HTTPException(401, "Kurulum anahtarı yok")
    govde = await request.body()
    if len(govde) > EN_BUYUK_OZET:
        raise HTTPException(413, "Özet çok büyük")
    try:
        ozet = json.loads(govde)
    except ValueError:
        raise HTTPException(400, "Geçersiz JSON")
    if not isinstance(ozet, dict):
        raise HTTPException(400, "Özet bir nesne olmalı")
    ozet = _yasakli_temizle(ozet)
    simdi = time.time()
    with _db() as db:
        k = db.execute("SELECT id, etkin FROM kurulumlar WHERE anahtar_ozeti=?", (_ozet_al(x_kurulum_anahtari),)).fetchone()
        if k is None:
            raise HTTPException(401, "Kurulum anahtarı tanınmıyor")
        if not k["etkin"]:
            raise HTTPException(403, "Kurulum devre dışı")
        db.execute("UPDATE kurulumlar SET son_nabiz=?, ilk_nabiz=COALESCE(ilk_nabiz, ?), son_ip=?, son_ozet=? WHERE id=?",
                   (simdi, simdi, request.client.host if request.client else None,
                    json.dumps(ozet, ensure_ascii=False), k["id"]))
        db.execute("INSERT INTO nabizlar (kurulum_id, zaman) VALUES (?, ?)", (k["id"], simdi))
        if secrets.randbelow(200) == 0:
            db.execute("DELETE FROM nabizlar WHERE zaman < ?", (simdi - NABIZ_SAKLAMA_GUN * 86400,))
    return {"tamam": True, "sunucu_zamani": datetime.fromtimestamp(simdi).isoformat(timespec="seconds")}


# ------------------------------------------------------------------ pano verisi
def _erisim_yuzdesi(db, kurulum_id: int, ilk_nabiz: Optional[float], simdi: float, gun: int = 7) -> Optional[float]:
    """Son `gun` günde (ya da ilk bağlantıdan beri) 5 dakikalık dilimlerin kaçında nabız geldi."""
    if not ilk_nabiz:
        return None
    bas = max(simdi - gun * 86400, ilk_nabiz)
    toplam = max(1, int((simdi - bas) // ERISIM_DILIM_SN) + 1)
    dolu = db.execute(f"SELECT COUNT(DISTINCT CAST(zaman / {ERISIM_DILIM_SN} AS INTEGER)) FROM nabizlar "
                      "WHERE kurulum_id=? AND zaman >= ?", (kurulum_id, bas)).fetchone()[0]
    return round(min(100.0, dolu / toplam * 100), 1)


def _kurulum_ozeti(db, r, simdi: float, ayrinti: bool = False) -> dict:
    ozet = json.loads(r["son_ozet"]) if r["son_ozet"] else None
    sorunlar = sorunlari_hesapla(ozet, r["son_nabiz"], simdi, bakim_bitis=r["bakim_bitis"] or None)
    kameralar = [k for k in (ozet or {}).get("kameralar") or [] if k.get("aktif", True)]
    sonuc = {
        "id": r["id"], "ad": r["ad"], "etkin": bool(r["etkin"]), "iletisim": r["iletisim"] or "",
        "bakim_bitis": r["bakim_bitis"] or "", "notlar": r["notlar"] or "",
        "son_nabiz": r["son_nabiz"], "son_ip": r["son_ip"],
        "durum": genel_durum(sorunlar) if r["etkin"] else "pasif", "sorunlar": sorunlar,
        "kurum": (ozet or {}).get("kurum"), "surum": (ozet or {}).get("surum"),
        "kamera_toplam": len(kameralar),
        "kamera_calisan": sum(1 for k in kameralar if k.get("goruntu") not in ("durdu", "donmus")),
        "bugun_okuma": sum(int(k.get("bugun_okuma") or 0) for k in kameralar),
        "disk_yuzde": ((ozet or {}).get("disk") or {}).get("en_dolu_yuzde"),
        "yedek_saat": ((ozet or {}).get("yedek") or {}).get("yas_saat"),
        "lisans_kalan_gun": ((ozet or {}).get("lisans") or {}).get("kalan_gun"),
        "erisim_7g": _erisim_yuzdesi(db, r["id"], r["ilk_nabiz"], simdi),
    }
    if ayrinti:
        sonuc["ozet"] = ozet
        sonuc["olaylar"] = [dict(o) for o in db.execute(
            "SELECT zaman, tur, seviye, mesaj FROM olaylar WHERE kurulum_id=? ORDER BY zaman DESC LIMIT 50", (r["id"],))]
    return sonuc


_DURUM_SIRA = {"cevrimdisi": 0, "kritik": 1, "uyari": 2, "iyi": 3, "pasif": 4}


@app.get("/api/kurulumlar")
def kurulumlar(_: str = Depends(yonetici)):
    simdi = time.time()
    with _db() as db:
        liste = [_kurulum_ozeti(db, r, simdi) for r in db.execute("SELECT * FROM kurulumlar")]
    liste.sort(key=lambda k: (_DURUM_SIRA.get(k["durum"], 9), k["ad"].lower()))
    sayac = {d: sum(1 for k in liste if k["durum"] == d) for d in _DURUM_SIRA}
    return {"kurulumlar": liste, "sayac": sayac, "sunucu_zamani": simdi, "bildirim_kanallari": bildirim.kanallar()}


def _kurulum_bul(db, kurulum_id: int):
    r = db.execute("SELECT * FROM kurulumlar WHERE id=?", (kurulum_id,)).fetchone()
    if r is None:
        raise HTTPException(404, "Kurulum yok")
    return r


@app.get("/api/kurulumlar/{kurulum_id}")
def kurulum_ayrinti(kurulum_id: int, _: str = Depends(yonetici)):
    with _db() as db:
        return _kurulum_ozeti(db, _kurulum_bul(db, kurulum_id), time.time(), ayrinti=True)


def _alanlar(veri: dict) -> dict:
    alanlar = {}
    for ad, uzunluk in (("ad", 120), ("iletisim", 300), ("notlar", 2000), ("bakim_bitis", 10)):
        if ad in veri:
            alanlar[ad] = str(veri[ad] or "").strip()[:uzunluk]
    if alanlar.get("bakim_bitis"):
        try:
            datetime.fromisoformat(alanlar["bakim_bitis"])
        except ValueError:
            raise HTTPException(400, "Bakım bitişi YYYY-AA-GG biçiminde olmalı")
    if "ad" in alanlar and not alanlar["ad"]:
        raise HTTPException(400, "Kurulum adı boş olamaz")
    if "etkin" in veri:
        alanlar["etkin"] = 1 if veri["etkin"] else 0
    return alanlar


@app.post("/api/kurulumlar")
def kurulum_ekle(veri: dict = Body(...), _: str = Depends(yonetici)):
    alanlar = _alanlar(veri)
    if not alanlar.get("ad"):
        raise HTTPException(400, "Kurulum adı gerekli")
    anahtar = secrets.token_urlsafe(24)
    with _db() as db:
        imlec = db.execute("INSERT INTO kurulumlar (ad, iletisim, notlar, bakim_bitis, anahtar_ozeti, olusturma) "
                           "VALUES (?, ?, ?, ?, ?, ?)",
                           (alanlar["ad"], alanlar.get("iletisim", ""), alanlar.get("notlar", ""),
                            alanlar.get("bakim_bitis", ""), _ozet_al(anahtar), time.time()))
        kurulum_id = imlec.lastrowid
    return {"id": kurulum_id, "anahtar": anahtar}


@app.patch("/api/kurulumlar/{kurulum_id}")
def kurulum_guncelle(kurulum_id: int, veri: dict = Body(...), _: str = Depends(yonetici)):
    alanlar = _alanlar(veri)
    with _db() as db:
        _kurulum_bul(db, kurulum_id)
        if alanlar:
            db.execute(f"UPDATE kurulumlar SET {', '.join(f'{k}=?' for k in alanlar)} WHERE id=?",
                       (*alanlar.values(), kurulum_id))
    return {"tamam": True}


@app.post("/api/kurulumlar/{kurulum_id}/anahtar-yenile")
def anahtar_yenile(kurulum_id: int, _: str = Depends(yonetici)):
    anahtar = secrets.token_urlsafe(24)
    with _db() as db:
        _kurulum_bul(db, kurulum_id)
        db.execute("UPDATE kurulumlar SET anahtar_ozeti=? WHERE id=?", (_ozet_al(anahtar), kurulum_id))
    return {"id": kurulum_id, "anahtar": anahtar}


@app.delete("/api/kurulumlar/{kurulum_id}")
def kurulum_sil(kurulum_id: int, _: str = Depends(yonetici)):
    with _db() as db:
        _kurulum_bul(db, kurulum_id)
        for tablo, alan in (("nabizlar", "kurulum_id"), ("olaylar", "kurulum_id"), ("kurulumlar", "id")):
            db.execute(f"DELETE FROM {tablo} WHERE {alan}=?", (kurulum_id,))
    return {"tamam": True}


@app.post("/api/bildirim-dene")
def bildirim_dene(_: str = Depends(yonetici)):
    if not bildirim.kanallar():
        raise HTTPException(400, "Bildirim kanalı ayarlı değil (MERKEZ_TELEGRAM_* ya da MERKEZ_SMTP_* ortam değişkenleri).")
    hatalar = bildirim.gonder("PTS Merkez: deneme bildirimi", "Bu mesaj geldiyse merkez bildirimleri çalışıyor.")
    if hatalar:
        raise HTTPException(502, "; ".join(hatalar))
    return {"tamam": True}


@app.get("/")
def pano(_: str = Depends(yonetici)):
    return FileResponse(os.path.join(KLASOR, "pano.html"), headers={"Cache-Control": "no-store"})


@app.get("/saglik")
def saglik():
    return {"durum": "calisiyor"}


# ------------------------------------------------------------------ bildirim döngüsü
BEKLEME_SN = int(os.getenv("MERKEZ_BILDIRIM_BEKLEME_SN") or 600)   # sorun bu kadar sürerse bildir


def bildirim_turu(simdi: Optional[float] = None) -> list:
    """Her kurulumun sorunlarını önceki turla karşılaştırır: en az BEKLEME_SN süren yeni
    sorunlar ve düzelen (bildirilmiş) sorunlar için tek mesaj gönderir. Gönderilen
    mesajları döner (test için)."""
    simdi = simdi or time.time()
    giden = []
    with _db() as db:
        for r in db.execute("SELECT * FROM kurulumlar WHERE etkin=1").fetchall():
            ozet = json.loads(r["son_ozet"]) if r["son_ozet"] else None
            sorunlar = {s["kod"]: s for s in sorunlari_hesapla(ozet, r["son_nabiz"], simdi,
                                                               bakim_bitis=r["bakim_bitis"] or None)}
            sorunlar.pop("hic_baglanmadi", None)
            durum = json.loads(r["bildirim_durumu"] or "{}")
            gorulen = {k: v for k, v in (durum.get("gorulen") or {}).items() if k in sorunlar}
            bildirilen = durum.get("bildirilen") or {}
            yeni, duzelen = [], []
            for kod, s in sorunlar.items():
                gorulen.setdefault(kod, simdi)
                bekleme = 0 if kod == "cevrimdisi" else BEKLEME_SN   # çevrimdışı zaten 15 dk gecikmeli
                if kod not in bildirilen and simdi - gorulen[kod] >= bekleme:
                    yeni.append(s)
                    bildirilen[kod] = s["mesaj"]
            for kod in list(bildirilen):
                if kod not in sorunlar:
                    duzelen.append(bildirilen.pop(kod))
            for s in yeni:
                db.execute("INSERT INTO olaylar (kurulum_id, zaman, tur, seviye, mesaj) VALUES (?, ?, 'sorun', ?, ?)",
                           (r["id"], simdi, s["seviye"], s["mesaj"]))
            for m in duzelen:
                db.execute("INSERT INTO olaylar (kurulum_id, zaman, tur, seviye, mesaj) VALUES (?, ?, 'duzeldi', NULL, ?)",
                           (r["id"], simdi, m))
            db.execute("UPDATE kurulumlar SET bildirim_durumu=? WHERE id=?",
                       (json.dumps({"gorulen": gorulen, "bildirilen": bildirilen}, ensure_ascii=False), r["id"]))
            if yeni or duzelen:
                satirlar = [("🔴 " if s["seviye"] == "kritik" else "🟠 ") + s["mesaj"] for s in yeni]
                satirlar += ["✅ Düzeldi: " + m for m in duzelen]
                giden.append((f"PTS · {r['ad']}", "\n".join(satirlar)))
    for konu, metin in giden:
        bildirim.gonder(konu, metin)
    return giden


async def _bildirim_dongu():
    while True:
        await asyncio.sleep(BILDIRIM_ARALIK_SN)
        try:
            await asyncio.to_thread(bildirim_turu)
        except Exception:  # noqa: BLE001
            logger.exception("Bildirim turunda hata")


@app.on_event("startup")
async def _baslangic():
    if os.getenv("MERKEZ_BILDIRIM_DONGUSU", "1") != "0":
        asyncio.ensure_future(_bildirim_dongu())
