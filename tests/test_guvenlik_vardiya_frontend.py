"""frontend/index.html + frontend/app.js için statik testler: "Güvenlik
Personeli" rolü ve vardiya planlama arayüzü (bkz. 2026-09-18 "Güvenlik
Personeli Vardiya Filtresi" notu, README).

Bu dosya (main.py testlerinin aksine) fastapi/sqlalchemy'ye bağımlı DEĞİL --
yalnızca ham HTML/JS metnini ayrıştırıyor, bu yüzden GERÇEKTEN çalıştırılıp
doğrulanabildi.

Kullanıcı talebi (2026-09-18, özetle): güvenlik personeli için "Kullanıcılar"
sekmesinden yeni kullanıcı oluşturma ekranı; bu personel yalnızca Canlı
İzleme/Ana Sayfa/Kayıtlar/Kişiler/Kara Liste alanlarını görebilmeli (zaten
"operatör" rolüyle aynı 5 alan); ve kayıtlar listesi/raporları kendi
vardiyasına göre filtrelenmeli. Vardiya saatleri günden güne değişebildiği
(4 vardiya/vardiya amiri rotasyonu) için GÜN BAZLI bir vardiya atama ekranı
gerekiyor.
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


def test_yeni_kullanici_formunda_guvenlik_rolu_secenegi_var():
    corba = _corba()
    form = corba.find(id="kullaniciForm")
    assert form is not None
    secim = form.find(id="yeniRol")
    assert secim is not None
    degerler = {opt.get("value") for opt in secim.find_all("option")}
    assert "güvenlik" in degerler
    # Bu form yönetici dışına kapalı olmalı (var olan RBAC deseni -- forma
    # `data-rol-davranis` verilmemişse rolBazliArayuzuUygula() alanları
    # DEVRE DIŞI bırakır, gizlemez; bu #kullaniciForm'un ZATEN var olan
    # davranışı, yeni rol seçeneği eklenirken bozulmamış olmalı).
    assert form.get("data-rol-min") == "yonetici"


def test_rol_seviye_guvenlik_operator_ile_ayni_kademede():
    js = _js_metni()
    eslesme = re.search(r'const ROL_SEVIYE = \{([^}]*)\}', js)
    assert eslesme is not None, "ROL_SEVIYE tanımı bulunamadı"
    govde = eslesme.group(1)
    operator_eslesme = re.search(r'"operatör":\s*(-?\d+)', govde)
    guvenlik_eslesme = re.search(r'"güvenlik":\s*(-?\d+)', govde)
    assert operator_eslesme is not None
    assert guvenlik_eslesme is not None
    assert operator_eslesme.group(1) == guvenlik_eslesme.group(1), (
        "'güvenlik' rolü frontend'de 'operatör' ile AYNI RBAC kademesinde "
        "olmalı (bkz. backend/main.py::_rol_dogrula'daki eşdeğerlik notu)"
    )


def test_vardiya_planlama_karti_ve_formu_var():
    corba = _corba()
    form = corba.find(id="vardiyaForm")
    assert form is not None, "#vardiyaForm (Vardiya Ata) bulunamadı"
    assert form.get("data-rol-min") == "yonetici"
    for alan_id in ("vardiyaKullanici", "vardiyaTarih", "vardiyaBaslangic", "vardiyaBitis"):
        assert form.find(id=alan_id) is not None, f"#{alan_id} vardiya formunda bulunamadı"
    assert corba.find(id="vardiyalarTablo") is not None


def test_guvenlik_banner_kayitlar_sekmesinde_var_ve_varsayilan_gizli():
    corba = _corba()
    kayitlar_sekme = corba.find(id="kayitlar-sekme")
    assert kayitlar_sekme is not None
    banner = kayitlar_sekme.find(id="guvenlikVardiyaBilgisi")
    assert banner is not None
    assert "d-none" in (banner.get("class") or [])


def test_vardiya_fonksiyonlari_ve_banner_kontrolu_app_js_icinde():
    js = _js_metni()
    for fonksiyon in ("vardiyalariYukle", "vardiyaSil"):
        assert f"function {fonksiyon}" in js or f"async function {fonksiyon}" in js
    assert '"vardiyaForm"' in js
    assert "guvenlikVardiyaBilgisi" in js
    # Banner yalnızca mevcutRol tam olarak "güvenlik" iken gösterilmeli.
    assert 'mevcutRol !== "güvenlik"' in js


def test_vardiyalari_yukle_baslangic_veri_yuklemesine_baglandi():
    js = _js_metni()
    eslesme = re.search(r"async function uygulamaVerileriniYukle\(\) \{(.*?)\n\}", js, re.DOTALL)
    assert eslesme is not None
    assert "vardiyalariYukle()" in eslesme.group(1)
