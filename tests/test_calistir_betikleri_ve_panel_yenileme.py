"""Operasyonel iyileştirmeler (2026-09-25, sistem taraması, Patch #103) için
testler.

1) calistir.sh / calistir.bat: eskiden art arda 5 KISA çökmeden sonra betik
   KALICI olarak duruyordu ("otomatik yeniden başlatma DURDURULDU" + exit).
   Gözetimsiz çalışan bir nizamiye sisteminde bu, geçici ama birkaç dakika
   süren bir sorunun (veritabanına henüz ulaşılamaması vb.) PTS'i biri fark
   edene kadar kapalı bırakması demekti. Artık betik durmuyor, bekleme süresi
   artırılıyor (5 sn -> 60 sn -> 5 dk).

   calistir.sh için bu GERÇEKTEN çalıştırılarak doğrulanıyor: `uvicorn`,
   `pip`, `ss` ve `sleep` sahte betiklerle PATH'te gölgeleniyor (uvicorn her
   seferinde hata koduyla çıkıyor, sleep gerçekten beklemeden yalnızca süreyi
   kaydediyor) ve betiğin 12 çökmeden sonra HÂLÂ denemeye devam ettiği ve
   bekleme sürelerinin beklenen sırayla arttığı kontrol ediliyor.
   calistir.bat için Linux'ta cmd.exe olmadığından yalnızca statik kontrol
   yapılabiliyor.

2) `panel_yenileme_sn` ayarı: Ayarlar ekranında gösterilip kaydedilebiliyor
   ama hiçbir yerde kullanılmıyordu (yedek yenileme aralığı app.js'te 15 sn
   olarak sabit kodluydu). Statik kontrol: sabit kodlu çağrı kalktı ve ayar
   gerçekten okunuyor.

Bu dosya fastapi'ye bağımlı DEĞİL.
"""
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
_APP_JS = (_KOK / "frontend" / "app.js").read_text(encoding="utf-8")


def _calistirilabilir_yaz(yol: Path, icerik: str) -> None:
    yol.write_text(icerik, encoding="utf-8")
    yol.chmod(yol.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@pytest.mark.skipif(sys.platform.startswith("win") or shutil.which("bash") is None,
                    reason="calistir.sh yalnızca bash bulunan sistemlerde çalıştırılabilir")
def test_calistir_sh_ardisik_cokmelerde_durmaz_bekleme_suresini_artirir(tmp_path):
    calisma = tmp_path / "pts"
    (calisma / "backend").mkdir(parents=True)
    (calisma / "backend" / "requirements.txt").write_text("", encoding="utf-8")
    shutil.copy(_KOK / "calistir.sh", calisma / "calistir.sh")

    sahte_bin = tmp_path / "bin"
    sahte_bin.mkdir()
    kayit = tmp_path / "kayit.log"
    kayit.write_text("", encoding="utf-8")

    _calistirilabilir_yaz(sahte_bin / "uvicorn", '#!/bin/bash\necho uvicorn >> "$KAYIT"\nexit 1\n')
    _calistirilabilir_yaz(sahte_bin / "pip", "#!/bin/bash\nexit 0\n")
    _calistirilabilir_yaz(sahte_bin / "ss", "#!/bin/bash\nexit 0\n")  # port boş
    # sleep gerçekten beklemez; 12. çökmeden sonra betiği (ebeveyn süreci)
    # sonlandırır -- eski davranışta betik 5. çökmede kendisi çıkardı.
    _calistirilabilir_yaz(
        sahte_bin / "sleep",
        '#!/bin/bash\necho "sleep $1" >> "$KAYIT"\n'
        'n=$(grep -c uvicorn "$KAYIT")\n'
        '[ "$n" -ge 12 ] && kill -TERM $PPID\nexit 0\n',
    )

    ortam = dict(os.environ)
    ortam["PATH"] = f"{sahte_bin}{os.pathsep}{ortam.get('PATH', '')}"
    ortam["KAYIT"] = str(kayit)
    sonuc = subprocess.run(
        ["bash", str(calisma / "calistir.sh")],
        cwd=calisma, env=ortam, capture_output=True, text=True, timeout=60,
    )

    satirlar = kayit.read_text(encoding="utf-8").split()
    uvicorn_sayisi = kayit.read_text(encoding="utf-8").count("uvicorn")
    assert uvicorn_sayisi == 12, (
        f"Betik 12 çökmeye kadar yeniden denemeye devam etmeliydi, {uvicorn_sayisi} kez denedi.\n"
        f"stdout:\n{sonuc.stdout}"
    )
    beklemeler = [int(satirlar[i + 1]) for i, s in enumerate(satirlar) if s == "sleep"]
    assert beklemeler[:4] == [5, 5, 5, 5]
    assert beklemeler[4:9] == [60] * 5
    assert all(b == 300 for b in beklemeler[9:])
    assert "DURDURULMUYOR" in sonuc.stdout


def test_calistir_bat_artik_kalici_olarak_durmuyor():
    bat = (_KOK / "calistir.bat").read_text(encoding="utf-8")
    assert "otomatik yeniden baslatma DURDURULDU" not in bat
    assert "if %deneme% GEQ 5 set /a bekleme_sn=60" in bat
    assert "if %deneme% GEQ 10 set /a bekleme_sn=300" in bat
    assert "timeout /t %bekleme_sn% /nobreak" in bat
    # Port kontrolü: yalnızca İLK başlatmada durup kullanıcıya sorar.
    assert 'if defined port_pid if not "%ilk_baslatma%" == "1" (' in bat


def test_panel_yenileme_sn_artik_sabit_kodlu_degil_ve_ayar_okunuyor():
    assert "setInterval(_canliYenilemeVeZombiSseKontrolu, 15000)" not in _APP_JS
    assert "function _panelYenilemeAraliginiUygula(" in _APP_JS
    assert "ayarlar.panel_yenileme_sn" in _APP_JS
    # Ayarlar kaydedilince sayfa yenilenmeden yeni aralık uygulanmalı.
    assert "_panelYenilemeAraliginiUygula(guncel.panel_yenileme_sn)" in _APP_JS
    # Zombi-SSE kontrolü ayardan bağımsız olarak en geç 15 sn'de bir çalışmalı.
    assert "const _CANLI_KONTROL_MAKS_ARALIK_MS = 15000;" in _APP_JS
