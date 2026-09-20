"""frontend/index.html + frontend/app.js için statik testler: 2026-09-20
tarihinde eklenen "Denetim Kayıtları" ekranı (kullanıcı talebi: "kalıcı bir
veritabanı tablosu + panelde ayrı bir Denetim Kayıtları ekranı olan tam bir
audit-trail sistemi kurabilirim -- bunu yapabilirsin").

Bu dosya (main.py testlerinin aksine) fastapi/sqlalchemy'ye bağımlı DEĞİL --
yalnızca ham HTML/JS metnini ayrıştırıyor, bu yüzden GERÇEKTEN çalıştırılıp
doğrulanabildi. Backend tarafı (models.DenetimKaydi, GET /denetim-kayitlari,
_denetim_kaydet çağrı noktaları) tests/test_api.py'de (yalnızca py_compile ile
doğrulandı) test edildi.
"""
import re
from pathlib import Path

from bs4 import BeautifulSoup

_KOK = Path(__file__).resolve().parent.parent
_HTML_YOLU = _KOK / "frontend" / "index.html"
_JS_YOLU = _KOK / "frontend" / "app.js"


def _corba() -> BeautifulSoup:
    with open(_HTML_YOLU, encoding="utf-8") as f:
        return BeautifulSoup(f.read(), "html.parser")


def _js_metni() -> str:
    return _JS_YOLU.read_text(encoding="utf-8")


def _fonksiyon_govdesi(js: str, imza_paterni: str) -> str:
    eslesme = re.search(imza_paterni + r" \{(.*?)\n\}", js, re.DOTALL)
    assert eslesme is not None, f"'{imza_paterni}' bulunamadı"
    return eslesme.group(1)


def test_denetim_sekmesi_html_de_var():
    corba = _corba()
    assert corba.find(id="denetim-sekme") is not None
    assert corba.find(id="denetimKayitlariTablo") is not None
    assert corba.find(id="denetimFiltreKullanici") is not None
    assert corba.find(id="denetimFiltreEylem") is not None
    assert corba.find(id="denetimFiltreBaslangic") is not None
    assert corba.find(id="denetimFiltreBitis") is not None


def test_denetim_sekmesi_nav_ve_sidebar_da_yonetici_ile_sinirli():
    """Hesap yönetimiyle ilgili hassas bilgi taşıdığı için (kimin parolası
    sıfırlandı vb.) yalnızca yönetici görebilmeli -- operatöre AÇIK
    KALMAMALI. `tests/test_frontend_rbac.py`'deki genel RBAC testi zaten bu
    sekmeyi kapsıyor (bkz. _OPERATOR_GORMEMELI); burada spesifik olarak
    `data-rol-min="yonetici"` + `data-rol-davranis="gizle"` ikilisinin HER
    İKİ giriş noktasında (nav-tab + sidebar) da var olduğunu doğruluyoruz."""
    corba = _corba()
    nav_dugmesi = corba.select_one('#anaSekme [data-bs-target="#denetim-sekme"]')
    assert nav_dugmesi is not None
    nav_li = nav_dugmesi.find_parent("li")
    assert nav_li.get("data-rol-min") == "yonetici"
    assert nav_li.get("data-rol-davranis") == "gizle"

    sidebar_dugmesi = corba.select_one('aside.pts-sidebar [data-target="#denetim-sekme"]')
    assert sidebar_dugmesi is not None
    assert sidebar_dugmesi.get("data-rol-min") == "yonetici"
    assert sidebar_dugmesi.get("data-rol-davranis") == "gizle"


def test_denetim_kayitlarini_yukle_fonksiyonu_dogru_uc_noktayi_cagiriyor():
    govde = _fonksiyon_govdesi(_js_metni(), r"async function denetimKayitlariniYukle\(\)")
    assert "/denetim-kayitlari?" in govde
    assert "denetimKayitlariTablo" in govde


def test_denetim_kayitlarini_yukle_filtreleri_gonderiyor():
    """Kullanıcı adı, eylem ve tarih aralığı filtrelerinin HER BİRİNİN
    query parametresine eklendiğini doğrular -- biri unutulursa filtre
    sessizce etkisiz kalırdı."""
    govde = _fonksiyon_govdesi(_js_metni(), r"async function denetimKayitlariniYukle\(\)")
    assert 'params.set("kullanici_adi"' in govde
    assert 'params.set("eylem"' in govde
    assert 'params.set("baslangic"' in govde
    assert 'params.set("bitis"' in govde


def test_denetim_kayitlarini_yukle_aciklamayi_escape_ediyor():
    """`aciklama` alanı (ör. bir kamera adı ya da kullanıcı adı içerebilir)
    ham HTML olarak gömülürse stored XSS riski taşır -- escapeHtml
    kullanılmalı (bkz. projedeki yerleşik "asla ham veri gömme" kuralı)."""
    govde = _fonksiyon_govdesi(_js_metni(), r"async function denetimKayitlariniYukle\(\)")
    assert "escapeHtml(k.aciklama)" in govde
    assert "escapeHtml(k.kullanici_adi)" in govde
    assert "escapeHtml(k.eylem)" in govde


def test_denetim_sekmesi_acilinca_otomatik_yukleniyor():
    js = _js_metni()
    assert '[data-bs-target="#denetim-sekme"]' in js
    assert "denetimKayitlariniYukle" in js


def test_eylem_listesi_doldurma_fonksiyonu_var():
    govde = _fonksiyon_govdesi(_js_metni(), r"async function _denetimEylemListesiniDoldur\(\)")
    assert "/denetim-kayitlari/eylem-listesi" in govde
