"""Güncellemeden ÖNCE veritabanı yedeği (2026-10-23) -- guncelle.ps1 çağırır.

Kullanım (proje klasöründe): python -m backend.guncelleme_yedegi
Başarılıysa yedeğin tam yolunu yazar ve 0 ile çıkar; değilse 1.

SQLite: sqlite3 backup API'siyle tutarlı kopya (PTS çalışırken de güvenli),
otomatik yedek klasörüne. SQL Server: `BACKUP DATABASE` (bkz. mssql_yedek),
SQL Server yedek klasörüne. Dosya adı "pts_guncelleme_oncesi_" ile başlar;
otomatik yedeklerin saklama süresi temizliği bu dosyalara dokunmaz.
"""
import datetime
import json
import os
import sqlite3
import sys

from backend import mssql_yedek
from backend.database import SQLALCHEMY_DATABASE_URL, engine, sqlite_dosya_yolu

_BACKEND = os.path.dirname(os.path.abspath(__file__))
_KOK = os.path.dirname(_BACKEND)


def _ayarlar() -> dict:
    yol = os.getenv("PTS_SISTEM_AYARLARI_FILE") or os.path.join(_BACKEND, "sistem_ayarlari.json")
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def yedek_al() -> str:
    zaman = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    ayarlar = _ayarlar()
    if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        klasor = (str(ayarlar.get("otomatik_yedek_klasoru") or "").strip() or os.getenv("PTS_YEDEK_KLASORU")
                  or os.path.join(_KOK, "yedekler"))
        os.makedirs(klasor, exist_ok=True)
        hedef_yol = os.path.join(klasor, f"pts_guncelleme_oncesi_{zaman}.db")
        kaynak = sqlite3.connect(sqlite_dosya_yolu())
        try:
            hedef = sqlite3.connect(hedef_yol)
            try:
                kaynak.backup(hedef)
                hedef.execute("PRAGMA journal_mode=DELETE")
                if hedef.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("yedeğin bütünlük kontrolü başarısız")
            finally:
                hedef.close()
        finally:
            kaynak.close()
        return hedef_yol
    klasor = mssql_yedek.etkin_yedek_klasoru(engine, ayarlar)
    return mssql_yedek.yedek_al(engine, klasor, f"pts_guncelleme_oncesi_{zaman}.bak")


def main() -> int:
    try:
        print(yedek_al())
        return 0
    except Exception as exc:  # noqa: BLE001 - betik çıktısı için
        print(f"HATA: veritabanı yedeği alınamadı: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
