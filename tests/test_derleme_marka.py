"""2026-10-23: müşteri paketinde TPAO adı/logosu/iletişimi kalmasın."""
import glob
import importlib.util
import json
import os
import re
import shutil

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _derle():
    spec = importlib.util.spec_from_file_location("derle_windows", os.path.join(KOK, "installer", "derle_windows.py"))
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _paket_frontend(tmp_path):
    """Derlemedeki gibi: HTML/CSS yorumları silinir; JS'te terser yerine yorum satırları atılır."""
    derle = _derle()
    hedef = str(tmp_path / "frontend")
    shutil.copytree(os.path.join(KOK, "frontend"), hedef)
    for yol in glob.glob(os.path.join(hedef, "*.css")):
        derle._css_html_yorumsuz(yol, r"/\*.*?\*/")
    for yol in glob.glob(os.path.join(hedef, "*.html")):
        derle._css_html_yorumsuz(yol, r"<!--.*?-->")
    for yol in glob.glob(os.path.join(hedef, "*.js")):
        with open(yol, encoding="utf-8") as f:
            metin = re.sub(r"/\*.*?\*/", "", f.read(), flags=re.S)
        satirlar = [s for s in metin.splitlines() if not s.strip().startswith("//")]
        with open(yol, "w", encoding="utf-8") as f:
            f.write("\n".join(re.sub(r"\s//\s.*$", "", s) for s in satirlar))
    return derle, hedef


def test_musteri_paketinde_tpao_izi_kalmaz(tmp_path):
    derle, hedef = _paket_frontend(tmp_path)
    derle.tpao_izlerini_temizle(hedef)
    assert not os.path.exists(os.path.join(hedef, "img", "tpao-logo.png"))
    with open(os.path.join(hedef, "index.html"), encoding="utf-8") as f:
        html = f.read()
    assert 'src="/marka/logo"' in html and "PLAKA TANIMA SİSTEMİ" in html
    with open(os.path.join(hedef, "sw.js"), encoding="utf-8") as f:
        assert '"/static/img/pts-logo.svg"' in f.read()
    with open(os.path.join(hedef, "manifest.json"), encoding="utf-8") as f:
        assert json.load(f)["short_name"] == "PTS"


def test_iz_kalirsa_derleme_durur(tmp_path):
    derle = _derle()
    (tmp_path / "x.js").write_text('const kurum = "TPAO Trakya";', encoding="utf-8")
    with pytest.raises(SystemExit, match="TPAO izi"):
        derle.tpao_izlerini_temizle(str(tmp_path))


def test_marka_kopyalama(tmp_path):
    derle = _derle()
    cikti = tmp_path / "paket"
    cikti.mkdir()
    derle.marka_kopyala(str(cikti), None)
    assert (cikti / "marka.json").read_text(encoding="utf-8").strip() == "{}"
    musteri = tmp_path / "acme"
    musteri.mkdir()
    (musteri / "marka.json").write_text(json.dumps({"kurum_adi": "ACME", "logo_dosyasi": "logo.png"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="logo dosyası yok"):
        derle.marka_kopyala(str(cikti), str(musteri))
    (musteri / "logo.png").write_bytes(b"png")
    derle.marka_kopyala(str(cikti), str(musteri))
    assert json.loads((cikti / "marka.json").read_text(encoding="utf-8"))["kurum_adi"] == "ACME"
    assert (cikti / "logo.png").read_bytes() == b"png"
