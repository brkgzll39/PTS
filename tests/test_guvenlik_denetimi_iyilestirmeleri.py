"""frontend/index.html + frontend/app.js için statik testler: 2026-09-20
tarihinde yapılan geniş kapsamlı bir kod denetimi ("eksik gördüğün eklenmesi
ve geliştirilmesi gereken neler varsa yapar mısın") sonrası eklenen iki
frontend iyileştirmesi.

Bu dosya (main.py testlerinin aksine) fastapi/sqlalchemy'ye bağımlı DEĞİL --
yalnızca ham HTML/JS metnini ayrıştırıyor, bu yüzden GERÇEKTEN çalıştırılıp
doğrulanabildi.

1) KÜRESEL HATA YAKALAYICI: backend'in "sıfır sessiz hata" ilkesi (küresel
   exception handler'lar, ~90 try/except + loglama) frontend'de karşılıksızdı
   -- yakalanmamış bir JS hatası/promise reddi yalnızca tarayıcı konsoluna
   düşüp kullanıcıya hiç görünmeden kayboluyordu. Artık `window.onerror` ve
   `unhandledrejection` dinleyicileri, yakalanmamış her hatayı en azından bir
   toast ile bildiriyor (spam'i önlemek için 10 saniyede bir sınırlanarak).

2) "GÜVENLİK UYARILARI" BANNER'I: PTS_LICENSE_SECRET/PTS_KAMERA_ANAHTARI/
   PTS_CORS_ORIGINS gibi ayarlar varsayılana sessizce düşerse önceden bu
   yalnızca (kimsenin günlük okumadığı) loglar/pts.log'a bir kez yazılıyordu.
   /sistem/saglik yanıtına eklenen `guvenlik_uyarilari` alanı artık Sistem
   sekmesinde (yalnızca yönetici için) görünür bir uyarı olarak gösteriliyor.
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
# 1) Küresel hata yakalayıcı
# ------------------------------------------------------------------

def test_window_error_dinleyicisi_kayitli():
    js = _js_metni()
    assert 'window.addEventListener("error"' in js


def test_window_unhandledrejection_dinleyicisi_kayitli():
    js = _js_metni()
    assert 'window.addEventListener("unhandledrejection"' in js


def test_kaynak_yukleme_hatalari_gercek_js_hatalarindan_ayirt_ediliyor():
    """`event.error` yalnızca gerçek JS hatalarında dolu olur; başarısız bir
    <img>/<script> yüklemesi de "error" olayını tetikler ama `error` alanı
    o durumda null'dur -- bunları ayırt etmezsek her kırık resimde de
    kullanıcıya "beklenmeyen hata" toast'ı gösterirdik (yanlış pozitif)."""
    js = _js_metni()
    eslesme = re.search(r'window\.addEventListener\("error", \(olay\) => \{(.*?)\}\);', js, re.DOTALL)
    assert eslesme is not None
    govde = eslesme.group(1)
    assert "if (!olay.error) return;" in govde


def test_kuresel_hata_bildir_konsola_yaziyor_ve_toast_gosteriyor():
    govde = _fonksiyon_govdesi(_js_metni(), r"function _kuresekHataBildir\(mesaj\)")
    assert "console.error(mesaj)" in govde
    assert "toastGoster(" in govde
    assert '"hata"' in govde


def test_kuresel_hata_bildir_spam_korumasi_var():
    """Art arda patlayan bir döngü (örn. periyodik bir yenileme fonksiyonu
    her turda hata fırlatırsa) kullanıcıyı onlarca toast ile boğmamalı."""
    govde = _fonksiyon_govdesi(_js_metni(), r"function _kuresekHataBildir\(mesaj\)")
    assert "_sonKuresekHataToastZamani" in govde
    assert "10000" in govde


def test_unhandledrejection_dinleyicisi_kuresek_hata_bildiri_cagiriyor():
    js = _js_metni()
    eslesme = re.search(r'window\.addEventListener\("unhandledrejection", \(olay\) => \{(.*?)\}\);', js, re.DOTALL)
    assert eslesme is not None
    assert "_kuresekHataBildir(" in eslesme.group(1)


# ------------------------------------------------------------------
# 2) "Güvenlik uyarıları" banner'ı
# ------------------------------------------------------------------

def test_guvenlik_uyarilari_alani_html_de_var_ve_varsayilan_gizli():
    corba = _corba()
    alan = corba.find(id="guvenlikUyarilariAlani")
    assert alan is not None
    assert "d-none" in (alan.get("class") or [])
    assert corba.find(id="guvenlikUyarilariListesi") is not None


def test_sistem_sagligini_yukle_guvenlik_uyarilarini_gosterme_fonksiyonunu_cagiriyor():
    govde = _fonksiyon_govdesi(_js_metni(), r"async function sistemSagliginiYukle\(\)")
    assert "_guvenlikUyarilariniGoster(s.guvenlik_uyarilari)" in govde


def test_guvenlik_uyarilarini_goster_yalnizca_yoneticiye_gosteriyor():
    govde = _fonksiyon_govdesi(_js_metni(), r"function _guvenlikUyarilariniGoster\(uyarilar\)")
    assert 'mevcutRol !== "yonetici"' in govde


def test_guvenlik_uyarilarini_goster_ucteki_her_bayragi_kontrol_ediyor():
    """/sistem/saglik'in `guvenlik_uyarilari` alanındaki üç bayrağın (bkz.
    main.py::_guvenlik_uyarilarini_topla) HER BİRİ için ayrı bir uyarı
    metni üretilmeli -- biri eksik kalırsa o güvenlik borcu yine sessiz
    kalırdı."""
    govde = _fonksiyon_govdesi(_js_metni(), r"function _guvenlikUyarilariniGoster\(uyarilar\)")
    assert "uyarilar.lisans_secret_ayarli_mi" in govde
    assert "uyarilar.kamera_anahtari_ayarli_mi" in govde
    assert "uyarilar.cors_tum_originlere_acik" in govde


def test_guvenlik_uyarilarini_goster_hicbir_uyari_yoksa_alani_gizliyor():
    govde = _fonksiyon_govdesi(_js_metni(), r"function _guvenlikUyarilariniGoster\(uyarilar\)")
    assert "maddeler.length === 0" in govde
    assert govde.count('classList.add("d-none")') >= 2  # hem uyarılar yoksa hem rol yetersizse
