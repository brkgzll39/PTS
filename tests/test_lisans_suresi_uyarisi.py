"""frontend/app.js + frontend/style.css için statik testler: 2026-09-20
tarihinde, kullanıcının "eksik gördüğün neyse ekle" isteği üzerine yapılan
ikinci denetim turunda eklenen "lisans süresi dolmadan önce uyarı" özelliği.

Bu dosya (main.py testlerinin aksine) fastapi/sqlalchemy'ye bağımlı DEĞİL --
yalnızca ham JS/CSS metnini ayrıştırıyor, bu yüzden GERÇEKTEN çalıştırılıp
doğrulanabildi.

KÖK NEDEN: lisans süresi kontrolü tamamen ikiliydi (aktif/pasif). Süre
dolduğu anda (`_kamera_bekcisi` döngüsü, main.py) TÜM kamera pipeline'ları
hiçbir önceden uyarı olmadan aniden durduruluyordu -- sahada bu, müşteriye
haber verilmeden "sistem birden çalışmayı kesti" şikayetine dönüşecek bir
senaryo. Backend'e eklenen `_lisans_kalan_gun_ekle` (bkz. main.py, yalnızca
py_compile ile doğrulanabildi -- fastapi'ye bağımlı) `/lisans` yanıtına
`kalan_gun`/`yakinda_doluyor` alanlarını ekliyor; bu dosya frontend'in bu
alanları doğru şekilde üçüncü bir görsel duruma ("aktif" ile "aktivasyon
bekliyor" arasında, turuncu bir "yakında dolacak" uyarısı) çevirdiğini
doğruluyor.
"""
import re
from pathlib import Path

_KOK = Path(__file__).resolve().parent.parent
_JS_YOLU = _KOK / "frontend" / "app.js"
_CSS_YOLU = _KOK / "frontend" / "style.css"


def _js_metni() -> str:
    return _JS_YOLU.read_text(encoding="utf-8")


def _css_metni() -> str:
    return _CSS_YOLU.read_text(encoding="utf-8")


def _fonksiyon_govdesi(js: str, imza_paterni: str) -> str:
    eslesme = re.search(imza_paterni + r" \{(.*?)\n\}", js, re.DOTALL)
    assert eslesme is not None, f"'{imza_paterni}' bulunamadı"
    return eslesme.group(1)


def test_lisans_pill_warning_css_kurali_var():
    css = _css_metni()
    assert ".license-pill.warning" in css
    assert ".license-icon.warning" in css


def test_lisans_yukle_yakinda_doluyor_kontrolu_var():
    govde = _fonksiyon_govdesi(_js_metni(), r"async function lisansYukle\(\)")
    assert "lisans.yakinda_doluyor" in govde
    assert "lisans.kalan_gun" in govde


def test_lisans_yukle_uc_ayri_gorsel_durum_var():
    """Lisans kartı/pill'i üç ayrı görsel duruma sahip olmalı: aktivasyon
    bekliyor (pending), aktif (active), ve aktif-ama-yakında-dolacak
    (warning) -- ikisi asla aynı anda gösterilmemeli."""
    govde = _fonksiyon_govdesi(_js_metni(), r"async function lisansYukle\(\)")
    assert '"pending"' in govde
    assert '"active"' in govde or "'active'" in govde
    assert '"warning"' in govde


def test_lisans_mini_durum_active_ve_warning_karsilikli_disliyor():
    """`active` class'ı YAKINDA DOLACAKSA eklenmemeli (aksi halde pill hem
    yeşil hem turuncu gibi çelişkili bir görünüm için iki class de aktif
    olurdu)."""
    govde = _fonksiyon_govdesi(_js_metni(), r"async function lisansYukle\(\)")
    eslesme = re.search(r'classList\.toggle\("active", ([^)]*)\)', govde)
    assert eslesme is not None
    assert "yakindaDoluyor" in eslesme.group(1)


def test_lisans_uyari_mesaji_kalan_gunu_gosteriyor():
    govde = _fonksiyon_govdesi(_js_metni(), r"async function lisansYukle\(\)")
    assert "gün içinde dolacak" in govde
    assert "gün kaldı" in govde
