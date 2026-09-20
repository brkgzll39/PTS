"""frontend/index.html + frontend/app.js için statik testler: iki ayrı
2026-09-20 kullanıcı isteği.

Bu dosya (main.py testlerinin aksine) fastapi/sqlalchemy'ye bağımlı DEĞİL --
yalnızca ham HTML/JS metnini ayrıştırıyor, bu yüzden GERÇEKTEN çalıştırılıp
doğrulanabildi.

1) "Giriş veya çıkış olduğunda panel ekranında sağ üstte 34 MRU 800 giriş
   yaptı gibi bir bildirim geliyor bu bildirim geldiğinde son geçişler de
   olduğu gibi direkt olarak onun üstüne tıklayıp not ve onay ekranının
   açılmasını istiyorum" -- SSE ile gelen canlı geçiş toast'ı artık
   tıklanabilir ve "Son Geçişler" panelindeki satırlarla AYNI şekilde
   olayDetayAc(id) çağırıp not/onay modalını açıyor.

2) "bir de alan sınırı eklemiştik bu alan sınırına serbest çizim ekleme
   şansımız var mı kare seçimde bazen farklı yönden geçen araçları da tespit
   ediyor bunu istemiyorum" -- kamera tespit alanı (ROI) modalına, mevcut
   dikdörtgen (Kare) seçiminin YANINA, görüntü üzerine tıklayarak keyfi bir
   çokgen çizilebilen "Serbest Çizim" modu eklendi.
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


# ------------------------------------------------------------------
# 1) Bildirime (toast) tıklayınca not/onay ekranının açılması
# ------------------------------------------------------------------

def test_toastgoster_opsiyonel_tikla_parametresi_kabul_ediyor():
    js = _js_metni()
    eslesme = re.search(r"function toastGoster\(([^)]*)\) \{", js)
    assert eslesme is not None, "toastGoster fonksiyonu bulunamadı"
    parametreler = eslesme.group(1)
    assert "tikla" in parametreler, "toastGoster artık opsiyonel bir 'tikla' parametresi almalı"


def test_toastgoster_tiklanabilirse_govdeye_tiklama_dinleyicisi_ekliyor():
    govde = _fonksiyon_govdesi(_js_metni(), r"function toastGoster\(mesaj, tip = \"bilgi\", tikla = null\)")
    assert "addEventListener(\"click\"" in govde
    assert "tikla()" in govde
    # Kapatma (X) butonu tıklamayı TETİKLEMEMELİ -- bkz. toast-body'e ayrı
    # dinleyici eklenmesi (btn-close, data-bs-dismiss ile ayrı çalışır).
    assert 'querySelector(".toast-body")' in govde


def test_sse_kayit_toastu_olay_detayini_acan_bir_tikla_ile_cagriliyor():
    """"bildirim geldiğinde son geçişler de olduğu gibi direkt olarak onun
    üstüne tıklayıp not ve onay ekranının açılmasını istiyorum" -- SSE
    toast'ı, "Son Geçişler" panelinin kullandığı AYNI olayDetayAc(id)
    fonksiyonunu çağırmalı."""
    govde = _fonksiyon_govdesi(_js_metni(), r"function _sseKayitAl\(kayit\)")
    eslesme = re.search(r"toastGoster\(`[^`]*`,\s*tip,\s*\(\)\s*=>\s*olayDetayAc\(kayit\.id\)\)", govde)
    assert eslesme is not None, (
        "_sseKayitAl artık toastGoster'ı () => olayDetayAc(kayit.id) callback'iyle çağırmalı"
    )


def test_toast_konteyneri_tiklanabilir_toast_icin_pointer_imleci_kullaniyor():
    js = _js_metni()
    assert 'cursor:pointer' in js and 'toast-tiklanabilir' in js


# ------------------------------------------------------------------
# 2) Tespit alanı (ROI) -- Kare (dikdörtgen) / Serbest Çizim (polygon) modu
# ------------------------------------------------------------------

def test_roi_modalinda_kare_ve_serbest_cizim_secenekleri_var():
    corba = _corba()
    modal = corba.find(id="kameraRoiModal")
    assert modal is not None
    kare_radio = modal.find(id="roiModKare")
    poligon_radio = modal.find(id="roiModPoligon")
    assert kare_radio is not None and poligon_radio is not None
    assert kare_radio.get("checked") is not None, "Varsayılan mod Kare (dikdörtgen) olmalı"


def test_roi_modalinda_poligon_cizim_katmani_ve_alan_grupları_var():
    corba = _corba()
    modal = corba.find(id="kameraRoiModal")
    assert modal.find(id="roiPoligonSvg") is not None, "#roiPoligonSvg (tıklanabilir çizim katmanı) bulunamadı"
    assert modal.find(id="roiKareAlanlari") is not None
    assert modal.find(id="roiPoligonAlanlari") is not None
    # Poligon alanları başlangıçta gizli olmalı (varsayılan mod Kare).
    assert "d-none" in (modal.find(id="roiPoligonAlanlari").get("class") or [])


def test_roi_poligon_svg_viewbox_yuzdelik_koordinat_sistemini_kullaniyor():
    """viewBox="0 0 100 100" + preserveAspectRatio="none": böylece bir
    tıklamanın kapsayıcıya göre yüzdesi, SVG koordinat uzayıyla BİREBİR
    örtüşür (0-100 aralığı, tıpkı dikdörtgen ROI'nin x1/y1/x2/y2 yüzdeleri
    gibi) -- ekstra bir dönüşüm gerekmez."""
    corba = _corba()
    svg = corba.find(id="roiPoligonSvg")
    assert svg is not None
    assert svg.get("viewbox") == "0 0 100 100"
    assert svg.get("preserveaspectratio") == "none"
    assert svg.get("onclick") == "roiPoligonTiklandi(event)"


def test_roi_poligon_js_fonksiyonlari_tanimli():
    js = _js_metni()
    for fonksiyon in (
        "roiModuDegisti", "roiPoligonTiklandi", "roiPoligonSonNoktayiSil",
        "roiPoligonTemizle", "_roiPoligonOnizlemeGuncelle",
    ):
        assert f"function {fonksiyon}" in js, f"{fonksiyon} bulunamadı"


def test_roi_modu_degisti_dogru_alanlari_gizleyip_gosteriyor():
    govde = _fonksiyon_govdesi(_js_metni(), r"function roiModuDegisti\(\)")
    assert '"roiModPoligon"' in govde
    assert 'getElementById("roiKareAlanlari").classList.toggle("d-none", poligonSecili)' in govde
    assert 'getElementById("roiPoligonAlanlari").classList.toggle("d-none", !poligonSecili)' in govde


def test_roi_poligon_tiklandi_moda_gore_calisiyor_ve_yuzdeye_ceviriyor():
    """Sadece "Serbest Çizim" modu seçiliyken tıklama noktaları eklemeli;
    kare modundayken bu fonksiyon hiçbir şey yapmamalı (erken çıkış)."""
    govde = _fonksiyon_govdesi(_js_metni(), r"function roiPoligonTiklandi\(event\)")
    assert 'getElementById("roiModPoligon")?.checked !== true' in govde
    assert "return;" in govde
    assert "getBoundingClientRect()" in govde
    assert "_roiPoligonNoktalari.push(" in govde


def test_roi_poligon_kaydet_en_az_3_nokta_gerektiriyor_ve_polygon_govdesi_gonderiyor():
    govde = _fonksiyon_govdesi(_js_metni(), r"async function kameraRoiKaydet\(\)")
    assert "_roiPoligonNoktalari.length < 3" in govde
    assert "{ polygon: _roiPoligonNoktalari }" in govde


def test_kamera_roi_ac_polygon_tipini_dogru_yukluyor():
    """Var olan bir kamera polygon ROI'ye sahipse (kamera.roi.tip ===
    "polygon"), modal açılırken hem doğru radyo butonu seçili gelmeli hem de
    var olan köşe noktaları önizlemeye yüklenmeli -- kullanıcı daha önce
    çizdiği şekli sıfırdan yeniden çizmek zorunda kalmamalı."""
    govde = _fonksiyon_govdesi(_js_metni(), r"async function kameraRoiAc\(id\)")
    assert 'kamera.roi && kamera.roi.tip === "polygon"' in govde
    assert "_roiPoligonNoktalari = poligonMi ? kamera.roi.noktalar.map(" in govde


def test_roi_rozeti_polygon_tipini_de_dogru_etiketliyor():
    """Kamera listesindeki "Alan sınırlı" rozeti, artık iki farklı ROI
    tipiyle de (dikdörtgen/polygon) çalışmalı -- polygon'da x1/x2/y1/y2
    alanları HİÇ olmadığı için eski kod burada sessizce 'undefined'
    yazardı."""
    js = _js_metni()
    assert 'k.roi.tip === "polygon"' in js
    assert "k.roi.noktalar.length" in js
