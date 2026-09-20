"""frontend/index.html + frontend/app.js için statik testler: "Güvenlik
Personeli" rolü ve ÖZ-HİZMET vardiya oturumu arayüzü (bkz. 2026-09-18
"Güvenlik Personeli Vardiya Filtresi" ve 2026-09-20 "Öz-Hizmet Vardiya
Oturumları" notları, README).

Bu dosya (main.py testlerinin aksine) fastapi/sqlalchemy'ye bağımlı DEĞİL --
yalnızca ham HTML/JS metnini ayrıştırıyor, bu yüzden GERÇEKTEN çalıştırılıp
doğrulanabildi.

Kullanıcı talebi (2026-09-18, özetle): güvenlik personeli için "Kullanıcılar"
sekmesinden yeni kullanıcı oluşturma ekranı; bu personel yalnızca Canlı
İzleme/Ana Sayfa/Kayıtlar/Kişiler/Kara Liste alanlarını görebilmeli (zaten
"operatör" rolüyle aynı 5 alan); ve kayıtlar listesi/raporları kendi
vardiyasına göre filtrelenmeli.

GÜNCELLEME (2026-09-20, birebir): "bunu sürekli ben yapamam vardiyaya gelen
personel kendisi vardiya başlangıcını kendisi yapabilsin ... kullanıcı giriş
yapınca çıkış yapana kadar onun vardiyası devam etsin" -- yöneticinin elle
gün-bazlı vardiya ataması yaptığı eski ekran (Vardiya Ata formu) tamamen
kaldırıldı; vardiya artık giriş/çıkışa bağlı, otomatik açılıp kapanan bir
"Vardiya Oturumu"dur. Yönetici yalnızca İZLER ve gerekirse açık kalmış bir
oturumu sonlandırır.
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
    # 2026-09-20: bu açıklama artık ELLE atama YERİNE giriş/çıkışa bağlı
    # öz-hizmet vardiyasını anlatmalı (eski "Vardiya Planlama" adı geçmemeli).
    metin = form.get_text(" ", strip=True).lower()
    assert "giriş yapıldığı an" in metin or "giriş yapıldığı" in metin
    assert "vardiya planlama" not in metin


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


def test_eski_vardiya_ata_formu_kaldirildi():
    """2026-09-20: elle/gün-bazlı "Vardiya Ata" formu (ve onun alanları),
    öz-hizmet (giriş/çıkış tabanlı) sistemin YERİNE geçmesiyle kaldırıldı --
    bu form artık DOM'da bulunmamalı."""
    corba = _corba()
    assert corba.find(id="vardiyaForm") is None
    for eski_alan_id in ("vardiyaKullanici", "vardiyaTarih", "vardiyaBaslangic", "vardiyaBitis"):
        assert corba.find(id=eski_alan_id) is None, f"#{eski_alan_id} hâlâ DOM'da -- kaldırılmış olmalıydı"


def test_vardiya_oturumlari_izleme_tablosu_var():
    """Yönetici, artık vardiya OLUŞTURMAZ -- yalnızca güvenlik personelinin
    giriş/çıkışıyla otomatik açılıp kapanan oturumları İZLER ve gerekirse
    açık kalmış birini sonlandırır (bkz. /vardiya-oturumlari)."""
    corba = _corba()
    tablo = corba.find(id="vardiyaOturumlariTablo")
    assert tablo is not None, "#vardiyaOturumlariTablo bulunamadı"
    # Yenileme butonu, yeni izleme fonksiyonunu çağırmalı.
    assert corba.find(attrs={"onclick": "vardiyaOturumlariniYukle()"}) is not None


def test_guvenlik_banner_kayitlar_sekmesinde_var_ve_varsayilan_gizli():
    corba = _corba()
    kayitlar_sekme = corba.find(id="kayitlar-sekme")
    assert kayitlar_sekme is not None
    banner = kayitlar_sekme.find(id="guvenlikVardiyaBilgisi")
    assert banner is not None
    assert "d-none" in (banner.get("class") or [])


def test_guvenlik_banner_teshis_alt_alani_var():
    """2026-09-18 kullanıcı geri bildirimi ("vardiya atadım ama canlı geçişler
    Kayıtlar sekmesinde gözükmüyor") sonrası eklenen teşhis alanı: banner artık
    yalnızca statik uyarı metni değil, sunucunun kendi "şu an" bilgisini ve
    kullanıcının vardiya oturumlarını da gösteren bir alt bölüm içermeli."""
    corba = _corba()
    banner = corba.find(id="guvenlikVardiyaBilgisi")
    assert banner is not None
    durum_alani = banner.find(id="guvenlikVardiyaDurumu")
    assert durum_alani is not None, "#guvenlikVardiyaDurumu teşhis alanı banner içinde bulunamadı"


def test_vardiya_oturumu_fonksiyonlari_ve_banner_kontrolu_app_js_icinde():
    js = _js_metni()
    for fonksiyon in ("vardiyaOturumlariniYukle", "vardiyaOturumunuSonlandir"):
        assert f"function {fonksiyon}" in js or f"async function {fonksiyon}" in js
    # Eski elle-atama fonksiyonları ve formu ARTIK olmamalı.
    assert "function vardiyalariYukle" not in js
    assert "function vardiyaSil" not in js
    assert '"vardiyaForm"' not in js
    assert "guvenlikVardiyaBilgisi" in js
    # Banner yalnızca mevcutRol tam olarak "güvenlik" iken gösterilmeli.
    assert 'mevcutRol !== "güvenlik"' in js


def test_vardiya_oturumlarini_yukle_baslangic_veri_yuklemesine_baglandi():
    js = _js_metni()
    eslesme = re.search(r"async function uygulamaVerileriniYukle\(\) \{(.*?)\n\}", js, re.DOTALL)
    assert eslesme is not None
    assert "vardiyaOturumlariniYukle()" in eslesme.group(1)


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
    assert '"/vardiya-oturumlari/durumum"' in govde
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


def test_oturum_kapat_cikis_ucunu_cagirir_token_silinmeden_once():
    """2026-09-20: "kullanıcı giriş yapınca çıkış yapana kadar onun vardiyası
    devam etsin" -- vardiyanın GERÇEKTEN bitmesi için "Çıkış" butonuna
    basıldığında sunucudaki açık oturum kapatılmalı (bkz. backend/main.py::
    cikis_yap). Bu, token sessionStorage'dan SİLİNMEDEN ÖNCE çağrılmalı
    (aksi halde apiCagir() isteği kimliksiz gider ve sunucu hangi kullanıcının
    çıkış yaptığını bilemez)."""
    js = _js_metni()
    eslesme = re.search(r"async function oturumKapat\(\) \{(.*?)\n\}", js, re.DOTALL)
    assert eslesme is not None, "oturumKapat artık async olmalı (sunucuya istek atıyor)"
    govde = eslesme.group(1)
    assert '"/auth/cikis"' in govde
    cikis_konumu = govde.index('"/auth/cikis"')
    token_silme_konumu = govde.index('sessionStorage.removeItem("pts_token")')
    assert cikis_konumu < token_silme_konumu, (
        "/auth/cikis çağrısı, token silinmeden ÖNCE yapılmalı"
    )
