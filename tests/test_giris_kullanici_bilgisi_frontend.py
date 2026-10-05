"""2026-10-05 gerçek kullanıcı geri bildirimi: "yönetici hesabıyla giriş
yaptığımda F5 yapmadan yönetici ekranları gelmiyor". Kök neden POST
/auth/giris yanıtındaki `kullanici` nesnesinin boş dönmesiydi (backend);
frontend ise o yanıta körü körüne güveniyordu. Bu dosya fastapi/sqlalchemy'ye
bağımlı DEĞİL (statik kaynak taraması) -- gerçekten çalıştırılabilir.
"""
import re
from pathlib import Path

_KOK = Path(__file__).resolve().parent.parent
_APP_JS = (_KOK / "frontend" / "app.js").read_text(encoding="utf-8")
_MAIN_PY = (_KOK / "backend" / "main.py").read_text(encoding="utf-8")


def _fonksiyon_govdesi(kaynak: str, ad: str) -> str:
    m = re.search(rf"async function {ad}\(.*?\n}}\n", kaynak, re.S)
    assert m, f"{ad} bulunamadı"
    return m.group(0)


def test_giris_formu_kullaniciyi_auth_me_den_alir():
    govde = _fonksiyon_govdesi(_APP_JS, "authFormGonder")
    assert 'apiCagir("/auth/me")' in govde
    assert "authBasarili(cevap.kullanici)" not in govde, (
        "giriş yanıtındaki kullanici nesnesine güvenilmemeli (F5 yoluyla aynı /auth/me kullanılmalı)"
    )
    assert "authBasarili(kullanici)" in govde


def test_giris_formu_eksik_kullanici_bilgisiyle_arayuze_gecmez():
    govde = _fonksiyon_govdesi(_APP_JS, "authFormGonder")
    assert "!kullanici.rol" in govde
    assert 'sessionStorage.removeItem("pts_token")' in govde


def test_backend_giris_ham_orm_nesnesi_donmez():
    m = re.search(r"def giris_yap\(.*?\n\n\n@app", _MAIN_PY, re.S)
    assert m
    govde = m.group(0)
    assert '"kullanici": kullanici}' not in govde, "ham ORM nesnesi (expire edilmiş) dönmemeli"
    assert "KullaniciCevap.model_validate(kullanici)" in govde
    # Serileştirme, commit eden _token_uret'ten ÖNCE yapılmalı.
    assert govde.index("KullaniciCevap.model_validate") < govde.index("_token_uret(kullanici.id")


def test_alarm_otomatik_okundu_ayari_ve_yardimci_mevcut():
    assert '"alarm_otomatik_okundu": True' in _MAIN_PY
    assert '"alarm_otomatik_okundu": _ayar_bool_dogrula' in _MAIN_PY
    assert "_gecis_alarmlarini_otomatik_okundu_isaretle(db)" in _MAIN_PY
    # Kritik alarm tipleri otomatik okundu kapsamında OLMAMALI.
    m = re.search(r"_OTOMATIK_OKUNDU_ALARM_TIPLERI = \((.*?)\)", _MAIN_PY)
    assert m
    assert "kara_liste" not in m.group(1) and "supheli_arac" not in m.group(1)


def test_sistem_ayarlari_panelinde_otomatik_okundu_onay_kutusu_var():
    assert "ayar_alarm_otomatik_okundu" in _APP_JS
    assert "guncel.alarm_otomatik_okundu" in _APP_JS
