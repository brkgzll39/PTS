"""frontend/index.html'deki rol bazlı arayüz (RBAC) sekme görünürlüğü için
statik testler.

Bu dosya (main.py testlerinin aksine) fastapi/sqlalchemy'ye bağımlı DEĞİL --
yalnızca BeautifulSoup ile ham HTML'i ayrıştırıyor, bu yüzden bu dosya da
(depodaki bazı testlerin aksine) GERÇEKTEN çalıştırılıp doğrulanabildi.

Kullanıcı talebi (2026-09-18): "operatör" rolündeki bir kullanıcı panele
giriş yaptığında SADECE şu 5 alanı tam erişimle görebilmeli: Canlı İzleme,
Ana Sayfa, Geçiş Kayıtları, Aboneler ve Kişiler, Kara Liste. "Yönetim"e dair
her şey (Kameralar, Bariyer Kontrolü, Webhook Bildirimleri, Lisans Yönetimi,
LED Paneller, Site/Erişim Noktası, Kullanıcılar, Sistem/Log, ve isimsiz
"Test" sekmesi) ekranının HİÇBİR yerinde görünmemeli -- yalnızca ana sekmede
değil, kenar çubuğunda (`.pts-sidebar`), ikinci/eski sekme çubuğunda
(`#anaSekme`) VE Ana Sayfa'daki hızlı erişim kutucuklarında (`.quick-tile`)
da.

Bu, mevcut `data-rol-min`/`data-rol-davranis="gizle"` mekanizmasıyla
uygulandı (bkz. frontend/app.js::rolBazliArayuzuUygula) -- backend'de zaten
var olan yetki kontrolünü DEĞİŞTİRMEZ (bkz. backend/main.py::_rol_dogrula),
yalnızca ekrandaki GÖRÜNÜRLÜĞÜ kısıtlar. `data-rol-min="yonetici"` olan bir
öğe yalnızca yönetici rolünde görünür kalır (operatör/izleyici/sakin için
gizlenir).
"""
from pathlib import Path

from bs4 import BeautifulSoup

_HTML_YOLU = Path(__file__).resolve().parent.parent / "frontend" / "index.html"

# Kullanıcının "operatör bu alanlara tam erişim sağlayabilmeli" dediği 5 sekme.
_OPERATOR_GORMELI = {
    "#canli-sekme", "#panel-sekme", "#kayitlar-sekme", "#kisiler-sekme", "#karaliste-sekme",
}
# "Yönetim"e dair, operatörden HER giriş noktasından gizlenmesi gereken sekmeler.
_OPERATOR_GORMEMELI = {
    "#kamera-sekme", "#bariyer-sekme", "#bildirim-sekme", "#lisans-sekme",
    "#led-sekme", "#site-sekme", "#kullanicilar-sekme", "#sistem-sekme", "#test-sekme",
    # 2026-09-20: Denetim Kayıtları -- hesap yönetimiyle ilgili hassas bilgi
    # taşıdığı için (bkz. main.py::denetim_kayitlarini_listele) yalnızca
    # yönetici görebilir.
    "#denetim-sekme",
}
# "#test-sekme" kenar çubuğunda (sidebar) HİÇ bulunmuyor -- yalnızca ikinci/eski
# sekme çubuğunda (#anaSekme) bir <li> olarak var (bkz. index.html civarı 347.
# satır). Bu yüzden kenar çubuğu testlerinde bu tek sekmeyi ayrı tutuyoruz;
# kenar çubuğunda mevcut olmayan bir düğmenin "gizli" olup olmadığını test
# etmek anlamsız/yanlış pozitif üretir.
_OPERATOR_GORMEMELI_SIDEBAR = _OPERATOR_GORMEMELI - {"#test-sekme"}


def _corba() -> BeautifulSoup:
    with open(_HTML_YOLU, encoding="utf-8") as f:
        return BeautifulSoup(f.read(), "html.parser")


def _yonetici_ile_sinirli_mi(el) -> bool:
    return el.get("data-rol-min") == "yonetici" and el.get("data-rol-davranis") == "gizle"


# ------------------------------------------------------------------
# Kenar çubuğu (`.pts-sidebar`) -- panelin ana/görünür gezinme öğesi
# ------------------------------------------------------------------

def test_sidebar_yonetim_sekmeleri_operatorden_gizli():
    sidebar = _corba().select_one("aside.pts-sidebar")
    assert sidebar is not None, "kenar çubuğu bulunamadı -- index.html yapısı değişmiş olabilir"
    for hedef in _OPERATOR_GORMEMELI_SIDEBAR:
        buton = sidebar.select_one(f'[data-target="{hedef}"]')
        assert buton is not None, f"kenar çubuğunda {hedef} düğmesi bulunamadı"
        assert _yonetici_ile_sinirli_mi(buton), f"kenar çubuğundaki {hedef} düğmesi operatörden gizlenmemiş"


def test_sidebar_calisma_alani_sekmeleri_operatore_acik():
    """Kullanıcı talebi: bu 5 alana operatör TAM ERİŞİM sağlayabilmeli --
    yanlışlıkla gereksiz bir kısıtlama eklenmediğini doğrular."""
    sidebar = _corba().select_one("aside.pts-sidebar")
    for hedef in _OPERATOR_GORMELI:
        buton = sidebar.select_one(f'[data-target="{hedef}"]')
        assert buton is not None, f"kenar çubuğunda {hedef} düğmesi bulunamadı"
        assert not _yonetici_ile_sinirli_mi(buton), f"kenar çubuğundaki {hedef} düğmesi operatöre GEREKSİZ yere gizlenmiş"


def test_sidebar_yonetim_bolum_etiketi_operatorden_gizli():
    """"YÖNETİM" başlığının kendisi de gizlenmeli -- aksi halde operatör
    altı boş bir bölüm başlığı görür."""
    sidebar = _corba().select_one("aside.pts-sidebar")
    etiketler = sidebar.select(".sidebar-section-label")
    yonetim = next((e for e in etiketler if e.get_text(strip=True) == "YÖNETİM"), None)
    assert yonetim is not None, "'YÖNETİM' bölüm etiketi bulunamadı"
    assert _yonetici_ile_sinirli_mi(yonetim)


def test_sidebar_tum_hedefler_kategorize_edilmis():
    """Gelecekte kenar çubuğuna yeni bir sekme eklenirse bu test
    başarısız olup hatırlatmalı -- aksi halde yeni bir Yönetim sekmesi
    sessizce operatöre açık kalabilir."""
    sidebar = _corba().select_one("aside.pts-sidebar")
    tum_hedefler = {b["data-target"] for b in sidebar.select("[data-target]")}
    bilinmeyen = tum_hedefler - (_OPERATOR_GORMELI | _OPERATOR_GORMEMELI)
    assert not bilinmeyen, f"kenar çubuğunda bu testin bilmediği yeni sekme(ler) var: {bilinmeyen} -- RBAC listesini güncelleyin"


# ------------------------------------------------------------------
# İkinci/eski sekme çubuğu (`#anaSekme`, Bootstrap nav-tabs) -- sidebar'daki
# `sekmeAc()` bile ASLINDA bu çubuktaki gizli düğmeleri tıklayarak sekme
# değiştiriyor (bkz. frontend/app.js::sekmeAc) -- bu yüzden bu çubuk da
# görsel olarak render ediliyor ve AYRICA gizlenmesi gerekiyor.
# ------------------------------------------------------------------

def test_navtabs_yonetim_sekmeleri_operatorden_gizli():
    navtabs = _corba().select_one("ul#anaSekme")
    assert navtabs is not None, "ikinci sekme çubuğu (#anaSekme) bulunamadı"
    for hedef in _OPERATOR_GORMEMELI:
        buton = navtabs.select_one(f'[data-bs-target="{hedef}"]')
        assert buton is not None, f"ikinci sekme çubuğunda {hedef} bulunamadı"
        li = buton.find_parent("li")
        assert li is not None
        assert _yonetici_ile_sinirli_mi(li), f"ikinci sekme çubuğundaki {hedef} li'si operatörden gizlenmemiş"


def test_navtabs_calisma_alani_sekmeleri_operatore_acik():
    navtabs = _corba().select_one("ul#anaSekme")
    for hedef in _OPERATOR_GORMELI:
        buton = navtabs.select_one(f'[data-bs-target="{hedef}"]')
        assert buton is not None, f"ikinci sekme çubuğunda {hedef} bulunamadı"
        li = buton.find_parent("li")
        assert li is not None
        assert not _yonetici_ile_sinirli_mi(li), f"ikinci sekme çubuğundaki {hedef} li'si operatöre GEREKSİZ yere gizlenmiş"


def test_navtabs_tum_hedefler_kategorize_edilmis():
    navtabs = _corba().select_one("ul#anaSekme")
    tum_hedefler = {b["data-bs-target"] for b in navtabs.select("[data-bs-target]")}
    bilinmeyen = tum_hedefler - (_OPERATOR_GORMELI | _OPERATOR_GORMEMELI)
    assert not bilinmeyen, f"ikinci sekme çubuğunda bu testin bilmediği yeni sekme(ler) var: {bilinmeyen} -- RBAC listesini güncelleyin"


# ------------------------------------------------------------------
# Ana Sayfa'daki (`#panel-sekme`) hızlı erişim kutucukları (`.quick-tile`)
# -- KÖK NEDEN (bu özellik eklenirken bulundu): bu kutucuklar sidebar/navtabs
# ile AYNI data-target mekanizmasını kullanıyor ama TAMAMEN AYRI bir DOM
# konumunda duruyorlar -- sidebar'ı gizlemek bunları GİZLEMEZ, ayrı ayrı
# işaretlenmeleri gerekiyordu (Kamera Yönetimi + Lisans kutucukları).
# ------------------------------------------------------------------

def test_anasayfa_hizli_erisim_kutulari_yonetime_gidenler_gizli():
    panel = _corba().select_one("#panel-sekme")
    assert panel is not None
    yonetime_giden = {"#kamera-sekme", "#lisans-sekme"}
    for hedef in yonetime_giden:
        kutu = panel.select_one(f'.quick-tile[data-target="{hedef}"]')
        assert kutu is not None, f"Ana Sayfa hızlı erişim kutularında {hedef} bulunamadı"
        assert _yonetici_ile_sinirli_mi(kutu), f"Ana Sayfa hızlı erişim kutusu {hedef} operatörden gizlenmemiş"


def test_anasayfa_hizli_erisim_kutulari_calisma_alani_olanlar_acik():
    panel = _corba().select_one("#panel-sekme")
    calisma_alani = {"#canli-sekme", "#kayitlar-sekme", "#kisiler-sekme"}
    for hedef in calisma_alani:
        kutu = panel.select_one(f'.quick-tile[data-target="{hedef}"]')
        assert kutu is not None, f"Ana Sayfa hızlı erişim kutularında {hedef} bulunamadı"
        assert not _yonetici_ile_sinirli_mi(kutu), f"Ana Sayfa hızlı erişim kutusu {hedef} operatöre GEREKSİZ yere gizlenmiş"
