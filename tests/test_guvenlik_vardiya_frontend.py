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


def test_guvenlik_banner_teshis_alt_alani_var():
    """2026-09-18 kullanıcı geri bildirimi ("vardiya atadım ama canlı geçişler
    Kayıtlar sekmesinde gözükmüyor") sonrası eklenen teşhis alanı: banner artık
    yalnızca statik uyarı metni değil, sunucunun kendi "şu an" bilgisini ve
    kullanıcının vardiya pencerelerini de gösteren bir alt bölüm içermeli."""
    corba = _corba()
    banner = corba.find(id="guvenlikVardiyaBilgisi")
    assert banner is not None
    durum_alani = banner.find(id="guvenlikVardiyaDurumu")
    assert durum_alani is not None, "#guvenlikVardiyaDurumu teşhis alanı banner içinde bulunamadı"


def test_guvenlik_vardiya_durumunu_guncelle_fonksiyonu_dogru_uca_bagli():
    js = _js_metni()
    assert (
        "async function guvenlikVardiyaDurumunuGuncelle" in js
    ), "guvenlikVardiyaDurumunuGuncelle fonksiyonu bulunamadı"
    eslesme = re.search(
        r"async function guvenlikVardiyaDurumunuGuncelle\(\) \{(.*?)\n\}", js, re.DOTALL
    )
    assert eslesme is not None
    govde = eslesme.group(1)
    assert '"/vardiyalar/durumum"' in govde
    assert "guvenlikVardiyaDurumu" in govde
    # Sunucu/istemci saat karşılaştırması: teşhisin asıl amacı bu.
    assert "sunucu_simdiki_zaman" in govde
    assert "su_an_aktif_vardiya_var_mi" in govde


def test_guvenlik_vardiya_durumunu_guncelle_cagrilariyla_baglanti():
    js = _js_metni()
    # Girişte hemen (rolBazliArayuzuUygula içinde) ve periyodik panel
    # yenilemesinde (panelYenile içinde) tetiklenmeli -- kullanıcı girişten
    # hemen sonra teşhisi görebilsin, ayrıca zaman geçtikçe güncellensin.
    rol_fonk = re.search(r"function rolBazliArayuzuUygula\(\) \{(.*?)\n\}", js, re.DOTALL)
    assert rol_fonk is not None
    assert "guvenlikVardiyaDurumunuGuncelle()" in rol_fonk.group(1)
    panel_fonk = re.search(r"async function panelYenile\(\) \{(.*?)\n\}", js, re.DOTALL)
    assert panel_fonk is not None
    assert "guvenlikVardiyaDurumunuGuncelle()" in panel_fonk.group(1)
