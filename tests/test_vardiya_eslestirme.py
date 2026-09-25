"""backend/vardiya_eslestirme.py testleri (fastapi/sqlalchemy'den bağımsız --
bu dosya GERÇEKTEN çalıştırılıp doğrulandı).

Asıl güvence, rastgele üretilmiş binlerce senaryoda yeni süpürme
algoritmasının, main.py'deki eski "her kaydı her oturumla karşılaştır"
yaklaşımıyla (bkz. main.py::_pencere_icinde_mi) BİREBİR aynı sonucu
vermesidir -- yani performans düzeltmesi rapordaki/Kayıtlar ekranındaki
Vardiya sütununu hiçbir şekilde değiştirmez.
"""
import random
import time
from datetime import datetime, timedelta

from backend.vardiya_eslestirme import kayitlari_oturumlarla_eslestir


def _pencere_icinde_mi(zaman, baslangic, bitis):
    # main.py::_pencere_icinde_mi'nin birebir kopyası (main.py fastapi
    # gerektirdiği için burada import edilemiyor).
    if zaman < baslangic:
        return False
    return bitis is None or zaman < bitis


def _kaba_kuvvet(kayitlar, oturumlar):
    return {
        anahtar: [veri for giris, cikis, veri in oturumlar if _pencere_icinde_mi(zaman, giris, cikis)]
        for anahtar, zaman in kayitlar
    }


def test_rastgele_senaryolarda_eski_yontemle_birebir_ayni_sonuc():
    rnd = random.Random(20260925)
    t0 = datetime(2026, 1, 1)
    for _ in range(400):
        oturumlar = []
        for s in range(rnd.randint(0, 30)):
            giris = t0 + timedelta(minutes=rnd.randint(0, 5000))
            r = rnd.random()
            if r < 0.15:
                cikis = None  # hâlâ açık
            elif r < 0.2:
                cikis = giris  # sıfır uzunluk -- hiçbir kayıt eşleşmemeli
            elif r < 0.23:
                cikis = giris - timedelta(minutes=5)  # bozuk veri
            else:
                cikis = giris + timedelta(minutes=rnd.randint(1, 900))
            oturumlar.append((giris, cikis, f"oturum{s}"))
        kayitlar = []
        for k in range(rnd.randint(0, 40)):
            if oturumlar and rnd.random() < 0.3:
                # Sınır değerleri (tam giriş/çıkış anı) özellikle dene.
                g, c, _ = rnd.choice(oturumlar)
                zaman = rnd.choice([g, c or g])
            else:
                zaman = t0 + timedelta(minutes=rnd.randint(-100, 5100))
            kayitlar.append((k, zaman))
        assert kayitlari_oturumlarla_eslestir(kayitlar, oturumlar) == _kaba_kuvvet(kayitlar, oturumlar)


def test_sonuc_sirasi_oturumlarin_verilis_sirasidir():
    t = datetime(2026, 9, 25, 12, 0)
    oturumlar = [
        (t - timedelta(hours=1), None, "B"),   # daha geç başlamış ama önce verilmiş
        (t - timedelta(hours=5), None, "A"),
    ]
    assert kayitlari_oturumlarla_eslestir([(1, t)], oturumlar) == {1: ["B", "A"]}


def test_bos_girdiler():
    assert kayitlari_oturumlarla_eslestir([], []) == {}
    assert kayitlari_oturumlarla_eslestir([(1, datetime(2026, 1, 1))], []) == {1: []}


def test_buyuk_veride_hizli():
    """5000 kayıt x 3000 oturum: eski yöntem 15 milyon karşılaştırma
    demekti; yeni yöntem bunu bir saniyenin çok altında yapmalı."""
    rnd = random.Random(1)
    t0 = datetime(2025, 1, 1)
    oturumlar = []
    for g in range(3000):
        giris = t0 + timedelta(hours=8 * g)
        oturumlar.append((giris, giris + timedelta(hours=8, minutes=rnd.randint(0, 30)), f"v{g % 4}"))
    kayitlar = [(i, t0 + timedelta(minutes=rnd.randint(0, 8 * 60 * 3000))) for i in range(5000)]
    bas = time.perf_counter()
    sonuc = kayitlari_oturumlarla_eslestir(kayitlar, oturumlar)
    sure = time.perf_counter() - bas
    assert sure < 1.0, f"çok yavaş: {sure:.2f} sn"
    ornek = kayitlar[:200]
    assert {a: sonuc[a] for a, _ in ornek} == _kaba_kuvvet(ornek, oturumlar)
