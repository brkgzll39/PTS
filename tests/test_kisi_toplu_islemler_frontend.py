"""2026-10-05 Kişiler toplu işlemleri / yeniden bağlama / içe aktarma modu için
statik ön yüz testleri (fastapi/sqlalchemy gerektirmez)."""
import re
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

_KOK = Path(__file__).resolve().parent.parent
_HTML = (_KOK / "frontend" / "index.html").read_text(encoding="utf-8")
_JS = (_KOK / "frontend" / "app.js").read_text(encoding="utf-8")
_SOUP = BeautifulSoup(_HTML, "html.parser")


def test_html_tekrarlanan_id_yok():
    ids = [t["id"] for t in _SOUP.find_all(id=True)]
    assert [i for i, c in Counter(ids).items() if c > 1] == []


def test_toplu_islem_cubugu_ve_secim_kutulari_var():
    cubuk = _SOUP.find(id="kisiTopluCubuk")
    assert cubuk is not None and "d-none" in cubuk["class"]  # seçim yokken gizli
    for islem in ("aktif", "pasif", "sil"):
        assert cubuk.find("button", onclick=f"kisiTopluIslem('{islem}')") is not None, islem
    assert cubuk.find(id="kisiTopluTip") is not None
    assert _SOUP.find(id="kisiTumunuSec") is not None
    # Silme yalnızca yönetici (backend de 403 verir)
    sil = cubuk.find("button", onclick="kisiTopluIslem('sil')")
    assert sil["data-rol-min"] == "yonetici" and sil["data-rol-davranis"] == "gizle"


def test_tablo_basligi_sutun_sayisi_satirlarla_uyumlu():
    basliklar = _SOUP.select("#kisilerTablo")[0].find_parent("table").select("thead th")
    assert len(basliklar) == 11  # seçim + 9 veri sütunu + işlem
    assert 'colspan="11"' in _JS


def test_ice_aktarma_modu_secimi_ve_istege_eklenir():
    secim = _SOUP.find(id="topluImportMod")
    assert [o["value"] for o in secim.find_all("option")] == ["atla", "guncelle"]
    assert "/kisiler/toplu-import?mod=" in _JS
    assert "sonuc.atlandi" in _JS and "sonuc.guncellendi" in _JS


def test_yeniden_bagla_dugmesi_yalnizca_yonetici_ve_onizleme_sonrasi_onay():
    dugme = _SOUP.find("button", onclick="gecmisKayitlariYenidenBagla()")
    assert dugme["data-rol-min"] == "yonetici"
    govde = _JS[_JS.index("async function gecmisKayitlariYenidenBagla"):]
    govde = govde[:govde.index("\nasync function kisileriYukle")]
    # önizleme (uygula yok) -> onay -> uygula=true sırası
    assert govde.index("onayAl(") < govde.index("uygula=true")


def test_secim_gorunmeyen_kisiler_icin_temizlenir_ve_sekmeden_cikinca_birakilir():
    yukle = _JS[_JS.index("async function kisileriYukle"):]
    yukle = yukle[:yukle.index("\ndocument.getElementById(\"kisiForm\")")]
    assert "_kisiSecimi.delete(id)" in yukle  # listede olmayanlar seçimden çıkar
    cikis = _JS[_JS.index('document.addEventListener("hidden.bs.tab"'):]
    assert "_kisiSecimi.clear()" in cikis[:900]


def test_onay_modali_cok_satirli_metni_gosterir():
    assert "white-space: pre-line" in _SOUP.find(id="onayModalMetin")["style"]
