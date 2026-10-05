"""2026-10-05 SQL Server yedek arayüzü için statik testler (fastapi/sqlalchemy
gerektirmez)."""
import re
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

_KOK = Path(__file__).resolve().parent.parent
_HTML = (_KOK / "frontend" / "index.html").read_text(encoding="utf-8")
_JS = (_KOK / "frontend" / "app.js").read_text(encoding="utf-8")
_MAIN = (_KOK / "backend" / "main.py").read_text(encoding="utf-8")
_SOUP = BeautifulSoup(_HTML, "html.parser")


def test_html_tekrarlanan_id_yok():
    ids = [t["id"] for t in _SOUP.find_all(id=True)]
    assert [i for i, c in Counter(ids).items() if c > 1] == []


def test_bildirim_tetikleyicisi_yedek_hatasi_secenegi_var():
    degerler = [o.get("value") for o in _SOUP.select("option")]
    assert "yedek_hatasi" in degerler and "yedek_bozuk" in degerler
    assert re.search(r'yedek_hatasi:\s*"', _JS)


def test_ayarlar_formu_mssql_klasor_alani_ve_kaydi_var():
    assert 'id="ayar_mssql_yedek_klasoru"' in _JS
    assert "guncel.mssql_yedek_klasoru" in _JS
    assert 'id="mssqlYedekKlasoruAlani"' in _JS and 'id="sqliteYedekKlasoruAlani"' in _JS


def test_yedek_paneli_mssql_dalini_ayri_cizer():
    assert "function _mssqlYedekDurumunuCiz" in _JS
    assert 'veri.mod === "mssql"' in _JS
    # Eski yanıltıcı "ilk yedek en geç 6 saat" mesajı yalnızca SQLite dalında kalır.
    govde = _JS[_JS.index("async function otomatikYedekDurumunuYukle"):]
    assert govde.index('veri.mod === "mssql") { _mssqlYedekDurumunuCiz') < govde.index("İlk yedek en geç 6 saat")


def test_db_yedek_butonu_json_cevabi_isler():
    govde = _JS[_JS.index("async function veritabaniIndir"):]
    govde = govde[:govde.index("\nasync function ", 10)] if "\nasync function " in govde[10:] else govde
    assert "application/json" in govde and "SQL Server yedeği alındı" in govde
    assert "finally" in govde  # düğme her durumda yeniden etkinleşir


def test_dogrulama_belirsiz_sonucu_bozuk_gibi_gostermez():
    govde = _JS[_JS.index("async function otomatikYedekDogrula"):]
    assert "r.saglam === null" in govde[:600]


def test_backend_mssql_ve_sqlite_yollari_tanimli():
    assert "_mssql_otomatik_yedek_bir_tur" in _MAIN
    assert '"mssql_yedek_klasoru"' in _MAIN
    assert "Otomatik yedek sadece SQLite için desteklenir" not in _MAIN
