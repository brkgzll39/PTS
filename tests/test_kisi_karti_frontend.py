"""2026-10-05 "Kişi Kartı" (çoklu araç yönetimi) için statik testler --
fastapi/sqlalchemy'ye bağımlı DEĞİL, gerçekten çalıştırılabilir."""
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


def test_kisi_karti_gerekli_alanlari_var():
    modal = _SOUP.find(id="kisiDuzenleModal")
    assert modal is not None
    for alan in (
        "duzenleId", "duzenleTip", "duzenleAdSoyad", "duzenlePlaka", "duzenleTelefon", "duzenleDaire",
        "duzenleAciklama", "duzenleBitisTarihi", "kartAracTablosu", "kartAracSayisi", "duzenleYeniEkPlaka",
        "duzenleYeniEkAciklama", "duzenleEkPlakaSonuc", "duzenleSaatBaslangic", "duzenleSaatBitis", "duzenleGunler",
    ):
        assert modal.find(id=alan) is not None, alan
    assert "modal-xl" in " ".join(modal.find(class_="modal-dialog")["class"])
    assert len(modal.select("#duzenleGunler input[type=checkbox]")) == 7


def test_kisi_karti_sekmeleri_form_icindeki_button_olarak_kilitlenmez():
    # rolBazliArayuzuUygula FORM içindeki TÜM <button>'ları izleyici için
    # disable eder; sekme başlıkları <a> olmalı ki izleyici de gezebilsin.
    modal = _SOUP.find(id="kisiDuzenleModal")
    sekmeler = modal.select(".kart-sekmeler .nav-link")
    assert len(sekmeler) == 2 and all(s.name == "a" for s in sekmeler)


def test_yeni_kisi_formunda_ek_arac_alani_var():
    assert _SOUP.find(id="kisiEkPlakalar") is not None
    assert 'getElementById("kisiEkPlakalar")' in _JS


def test_js_kart_fonksiyonlari_tanimli_ve_dogru_uclari_kullanir():
    for fn in ("kisiDuzenleAc", "_kartAraclariCiz", "kisiEkPlakaEkle", "kisiEkPlakaSil", "kartPlakaDuzenle",
               "kartPlakaKaydet", "kartPlakaAktifDegistir", "kartPlakaAnaYap", "_kartKisiyiYenile"):
        assert re.search(rf"function {fn}\(", _JS), fn
    assert "/plakalar/${plakaId}/ana-yap" in _JS
    assert 'method: "PUT"' in _JS and "/plakalar/${plakaId}" in _JS
    assert "_duzenleEkPlakalarGoster" not in _JS


def test_js_dinamik_plaka_satirlari_xss_guvenli():
    govde = re.search(r"function _kartAraclariCiz\(\).*?\n}\n", _JS, re.S).group(0)
    assert "escapeHtml(p.plaka_no)" in govde and "escapeHtml(p.aciklama" in govde
    # onclick'lere yalnızca sayısal id gömülür, plaka metni ASLA gömülmez.
    for m in re.finditer(r'onclick="([^"]*)"', govde):
        assert "plaka_no" not in m.group(1) and "aciklama" not in m.group(1), m.group(1)
    # Kart içindeki satırlar data-plaka-analiz kullanmaz (modal üstüne modal açılmasın).
    assert "data-plaka-analiz" not in govde


def test_backend_yeni_uclar_ve_cakisma_kontrolu():
    assert '@app.put("/kisiler/{kisi_id}/plakalar/{plaka_id}"' in _MAIN
    assert '@app.post("/kisiler/{kisi_id}/plakalar/{plaka_id}/ana-yap"' in _MAIN
    assert "_plaka_cakisma_kontrol(db, istek.plaka_no, kisi_id)" in _MAIN


def test_kisi_listesinde_ek_plakalar_plakanin_altinda_listelenmez():
    # Kullanıcı isteği (2026-10-05): ek araçlar listede satırı uzatmasın; yalnızca
    # küçük "+N" rozeti olsun, tüm araçlar Kişi Kartı'nda görünsün.
    govde = re.search(r"async function kisileriYukle\(\).*?\n}\n", _JS, re.S).group(0)
    assert "ek-plaka-chip" not in govde
    assert "slice(0, 2)" not in govde
    assert "ek-plaka-rozeti" in govde
    assert 'class="kisi-ad-link" onclick="kisiDuzenleAc(' in govde


def test_kisiler_arac_cubugunda_arama_kutusu_ve_yan_yana_butonlar():
    arama = _SOUP.find(id="kisiArama")
    assert arama is not None and arama.get("type") == "search"
    cubuk = arama.find_parent(class_="kisi-arac-cubugu")
    assert cubuk is not None
    sablon = cubuk.find("button", onclick=re.compile("kisiIceAktarmaSablonuIndir"))
    ice_aktar = cubuk.find("input", id="topluImportDosya")
    assert sablon is not None and ice_aktar is not None
    # Şablon İndir ve Excel İçe Aktar AYNI sarmalayıcıda (yan yana) olmalı.
    assert sablon.parent is ice_aktar.find_parent("label").parent


def test_kisi_arama_js_debounce_ve_eski_istek_korumasi():
    assert 'getElementById("kisiArama")' in _JS
    assert "setTimeout(kisileriYukle, 300)" in _JS
    govde = re.search(r"async function kisileriYukle\(\).*?\n}\n", _JS, re.S).group(0)
    assert 'params.set("arama"' in govde
    assert "istekNo !== _kisiListeIstekNo" in govde
    assert 'params.set("arama"' in re.search(r"function kisilerExcelIndir\(\).*?\n}\n", _JS, re.S).group(0)


def test_kisiler_sekmesinden_cikinca_arama_sifirlanir():
    m = re.search(r'document\.addEventListener\("hidden\.bs\.tab".*?\n}\);', _JS, re.S)
    assert m, "hidden.bs.tab dinleyicisi yok"
    govde = m.group(0)
    assert '"#kisiler-sekme"' in govde
    assert 'kutu.value = ""' in govde
    assert "kisileriYukle()" in govde
