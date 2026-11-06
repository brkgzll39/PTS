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
    # 2026-10-30: resmi araç sekmesi (lisans modülü açıksa görünür, bkz. app.js::resmiModulHazirla).
    "#resmi-sekme",
    # 2026-09-22 kullanıcı isteği: "Yönetici Profili ve diğer profillerde
    # Arıza Bildirim ya da iletişim gibi bir sayfa eklemeni istiyorum" --
    # bu sekmenin data-rol-min'i YOK, yani tüm roller (operatör dahil)
    # görebilmeli.
    "#iletisim-sekme",
    # 2026-09-23 kullanıcı isteği: eski tek "Panel" (#panel-sekme) sekmesi
    # ikiye ayrıldı -- istatistik/grafik/nizamiye durumu içeriği bu yeni
    # "Kontrol Merkezi" sekmesine taşındı (bkz. index.html, app.js::
    # sonGecislerYukle'nin üstündeki not). Eski #panel-sekme'nin data-rol-min'i
    # HİÇ olmadığı (operatöre açık) için bu yeni sekme de aynı şekilde açık
    # kalmalı -- yalnızca içerik taşındı, yetki modeli DEĞİŞMEDİ.
    "#kontrol-sekme",
    # 2026-10-12 kullanıcı isteği: "İçerideki Araçlar" -- güvenlik personelinin
    # vardiya devrinde "içeride kim kaldı" sorusu için; tüm personel rollerine açık.
    "#iceride-sekme",
    # 2026-10-12: "Nöbet Defteri" (vardiya devir-teslim notları) -- tüm personel.
    "#nobet-sekme",
}
# "Yönetim"e dair, operatörden HER giriş noktasından gizlenmesi gereken sekmeler.
_OPERATOR_GORMEMELI = {
    "#kamera-sekme", "#bariyer-sekme", "#bildirim-sekme", "#lisans-sekme",
    "#led-sekme", "#site-sekme", "#kullanicilar-sekme", "#sistem-sekme", "#test-sekme",
    # 2026-09-20: Denetim Kayıtları -- hesap yönetimiyle ilgili hassas bilgi
    # taşıdığı için (bkz. main.py::denetim_kayitlarini_listele) yalnızca
    # yönetici görebilir.
    "#denetim-sekme",
    # 2026-11-06: Yazılım Güncellemeleri -- kütüphane güncelleme/geri alma.
    "#guncelleme-sekme",
    # 2026-11-02: Yönetim Paneli'nin açılış sayfası (Genel Bakış).
    "#yonetim-sekme",
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
# Kontrol Merkezi'ndeki (`#kontrol-sekme`) hızlı erişim kutucukları
# (`.quick-tile`) -- KÖK NEDEN (bu özellik eklenirken bulundu): bu kutucuklar
# sidebar/navtabs ile AYNI data-target mekanizmasını kullanıyor ama TAMAMEN
# AYRI bir DOM konumunda duruyorlar -- sidebar'ı gizlemek bunları GİZLEMEZ,
# ayrı ayrı işaretlenmeleri gerekiyordu (Kamera Yönetimi + Lisans kutucukları).
#
# 2026-09-23: bu kutucuklar, eski tek "Panel" (#panel-sekme) sekmesi ikiye
# ayrılırken (bkz. index.html, app.js::sonGecislerYukle'nin üstündeki not)
# değişmeden yeni "Kontrol Merkezi" (#kontrol-sekme) sekmesine taşındı --
# bu testler de o taşınmayı takip ediyor.
# ------------------------------------------------------------------

def test_kontrol_merkezinde_hizli_erisim_kutulari_yok():
    """2026-11-02: renkli "Hızlı Erişim" kutuları sol menüyü tekrarladığı için kaldırıldı."""
    panel = _corba().select_one("#kontrol-sekme")
    assert panel is not None
    assert panel.select(".quick-tile") == []


def test_her_ekranin_sol_menude_karsiligi_var_ve_yetkisi_ayni():
    """2026-11-02: üstteki sekme çubuğu gizlendi; gezinme yalnız sol menüden. Her sekmenin
    menüde bir bağlantısı olmalı ve yönetici sınırlaması sekmeyle aynı olmalı."""
    corba = _corba()
    for sekme in corba.select("#anaSekme [data-bs-target]"):
        hedef = sekme["data-bs-target"]
        baglanti = corba.select_one(f'.pts-sidebar .side-link[data-target="{hedef}"]')
        assert baglanti is not None, f"{hedef} sol menüde yok; üst çubuk gizli olduğu için açılamaz"
        assert _yonetici_ile_sinirli_mi(baglanti) == _yonetici_ile_sinirli_mi(sekme.find_parent("li")), \
            f"{hedef}: sol menü ve sekme yetkisi farklı"


# ------------------------------------------------------------------
# Kayıtlar tablosundaki "Doğrulama" sütunu -- 2026-09-23 kullanıcı isteği:
# "bu doğrulama sutununa yönetici dışında kimsenin görmesine gerek yok".
# Yalnızca başlık (<th>) burada test edilebilir -- satır hücreleri
# app.js::kayitlariYukle'de rolYeterli("yonetici") koşuluyla dinamik olarak
# ÜRETİLİYOR (statik HTML'de yer almıyorlar), bu yüzden JS çalıştırmayan bu
# statik test dosyasıyla doğrulanamazlar.
# ------------------------------------------------------------------

def test_kayitlar_dogrulama_sutun_basligi_yoneticiyle_sinirli():
    th = _corba().select_one("#kayitlar-sekme thead th[title*='Bu okuma kaç farklı karede']")
    assert th is not None, "Kayıtlar tablosunda 'Doğrulama' sütun başlığı bulunamadı"
    assert _yonetici_ile_sinirli_mi(th), "'Doğrulama' sütun başlığı operatörden gizlenmemiş"


def test_her_ekranin_sayfa_basligi_tanimli():
    """2026-11-02: sayfa başlığı şeridi app.js::SAYFA_BASLIKLARI'ndan doldurulur."""
    import re
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "frontend" / "app.js").read_text(encoding="utf-8")
    blok = js[js.index("const SAYFA_BASLIKLARI = {"):]
    blok = blok[:blok.index("};")]
    tanimli = set(re.findall(r'"(#[a-z]+-sekme)"', blok))
    hedefler = {b["data-bs-target"] for b in _corba().select("#anaSekme [data-bs-target]")}
    assert hedefler - tanimli == set()


def test_yonetim_grubu_operatorden_gizli():
    grup = _corba().select_one("aside.pts-sidebar #yonetimGrubu")
    assert grup is not None and _yonetici_ile_sinirli_mi(grup)
