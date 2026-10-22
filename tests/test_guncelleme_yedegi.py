"""2026-10-23: guncelle.ps1'in güncelleme öncesi aldığı veritabanı yedeği."""
import sqlite3

from backend import guncelleme_yedegi
from backend import main as pts_main  # noqa: F401 - tabloları oluşturur


def test_sqlite_yedegi_tutarli_ve_ayri_adla_alinir(monkeypatch, tmp_path):
    monkeypatch.setattr(guncelleme_yedegi, "_ayarlar", lambda: {})
    monkeypatch.setenv("PTS_YEDEK_KLASORU", str(tmp_path))
    yol = guncelleme_yedegi.yedek_al()
    assert yol.startswith(str(tmp_path)) and "pts_guncelleme_oncesi_" in yol
    with sqlite3.connect(yol) as baglanti:
        tablolar = {ad for (ad,) in baglanti.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "plaka_kayitlari" in tablolar and "kullanicilar" in tablolar
        assert baglanti.execute("PRAGMA journal_mode").fetchone()[0] == "delete"


def test_hata_olursa_sifirdan_farkli_cikar(monkeypatch, capsys):
    def patla():
        raise RuntimeError("disk yok")
    monkeypatch.setattr(guncelleme_yedegi, "yedek_al", patla)
    assert guncelleme_yedegi.main() == 1
    assert "disk yok" in capsys.readouterr().err
