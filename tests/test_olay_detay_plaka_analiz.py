"""frontend/index.html + frontend/app.js için statik test: "Son Geçişler"
panelinden (Canlı İzleme ekranı) açılan tekil geçiş modalının (olayDetayAc /
#olayDetayModal), plaka bazlı tam geçmiş + manuel kayıt ekranına
(plakaAnalizAc / #plakaAnalizModal) da bir düğmeyle erişim sağladığını
doğrular.

Bu dosya (main.py testlerinin aksine) fastapi/sqlalchemy'ye bağımlı DEĞİL --
yalnızca ham HTML/JS metnini ayrıştırıyor, bu yüzden GERÇEKTEN çalıştırılıp
doğrulanabildi.

Kullanıcı talebi (2026-09-18): "bu ekranda son geçişlerde gözüken plakalara
da tıklandığında ziyaretçi ekleme aracın resmini görme kayıt etme gibi
şeylerin aynısını görmek istiyorum." -- "Son Geçişler" paneli zaten
olayDetayAc() modalını açıyordu (görsel + ziyaretçi girişi onayı zaten
vardı) ama bu modalda; Kayıtlar/Kara Liste/Kişiler sekmelerinde
data-plaka-analiz ile açılan plakaAnalizAc() ekranının sunduğu TAM geçiş
GEÇMİŞİ ve "+ Manuel Kayıt Ekle" formu YOKTU. Çözüm: olayDetayModal'a yeni
bir "Plaka Geçmişi / Manuel Kayıt" düğmesi eklendi; bu düğme mevcut modalı
kapatıp plakaAnalizAc(plaka) ile diğer modalı açıyor -- böylece iki modal da
(bariyer açma + ziyaretçi girişi hızlı onayı olan olayDetayModal VE tam
geçmiş + manuel kayıt olan plakaAnalizModal) aynı tıklamadan erişilebilir
hale geldi.
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


def test_olay_detay_modalinda_plaka_analiz_dugmesi_var():
    corba = _corba()
    modal = corba.find(id="olayDetayModal")
    assert modal is not None, "#olayDetayModal HTML'de bulunamadı"
    btn = modal.find(id="olayModalAnalizBtn")
    assert btn is not None, (
        "olayDetayModal içinde #olayModalAnalizBtn (Plaka Geçmişi / Manuel "
        "Kayıt düğmesi) bulunamadı"
    )
    # Güvenlik: plaka gibi kullanıcı/kamera kaynaklı bir değer HTML
    # attribute'una (onclick=... veya data-*) statik olarak gömülmemeli --
    # düğmenin onclick'i JS tarafında dinamik olarak (kayit.plaka_no
    # kapanışıyla) kurulmalı, bkz. _olayModalAnalizButonunuAyarla.
    assert btn.get("onclick") is None
    assert btn.get("data-plaka-analiz") is None


def test_olay_detay_ac_yeni_butonu_kuruyor():
    js = _js_metni()
    # olayDetayAc() fonksiyonu, modalı göstermeden önce yeni yardımcıyı
    # çağırmalı (böylece her açılışta doğru plakaya bağlanıyor).
    fonksiyon_govdesi_paterni = re.search(
        r"async function olayDetayAc\(id\) \{(.*?)\n\}", js, re.DOTALL
    )
    assert fonksiyon_govdesi_paterni is not None, "olayDetayAc fonksiyonu bulunamadı"
    govde = fonksiyon_govdesi_paterni.group(1)
    assert "_olayModalAnalizButonunuAyarla(kayit)" in govde


def test_analiz_butonu_yardimcisi_dogru_modallari_yonetiyor():
    js = _js_metni()
    yardimci_paterni = re.search(
        r"function _olayModalAnalizButonunuAyarla\(kayit\) \{(.*?)\n\}", js, re.DOTALL
    )
    assert yardimci_paterni is not None, "_olayModalAnalizButonunuAyarla fonksiyonu bulunamadı"
    govde = yardimci_paterni.group(1)
    # Tıklanınca: mevcut tekil-kayıt modalı kapanmalı ve plaka bazlı tam
    # geçmiş/manuel-kayıt modalı (plakaAnalizAc) kayıt.plaka_no ile açılmalı.
    assert 'getElementById("olayDetayModal")' in govde
    assert "?.hide()" in govde
    assert "plakaAnalizAc(kayit.plaka_no)" in govde


def test_canli_izleme_panelindeki_satirlar_hala_olay_detay_ac_cagiriyor():
    # "Son Geçişler" (#canliOlaylar) panelindeki satırlar (hem ilk yükleme
    # hem de SSE ile canlı eklenen satırlar) olayDetayAc(id) çağırmaya devam
    # etmeli -- yeni "Plaka Geçmişi" erişimi bu modalın İÇİNDE bir düğme
    # olarak eklendi, satırın kendi tıklama davranışı DEĞİŞMEDİ.
    js = _js_metni()
    assert js.count('onclick="olayDetayAc(${k.id})"') >= 1
    assert js.count('onclick="olayDetayAc(${kayit.id})"') >= 1
