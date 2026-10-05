"""backend/mssql_yedek.py için birim testleri -- sahte (fake) bir engine ile
çalışır; SQLAlchemy/SQL Server/FastAPI GEREKTİRMEZ (gerçekten çalıştırılabilir)."""
from datetime import date, datetime, timedelta

import pytest

from backend import mssql_yedek as my


class SahteImlec:
    def __init__(self, dbapi):
        self.dbapi = dbapi
        self.kalan_nextset = 2

    def execute(self, sql):
        self.dbapi.calistirilan.append(sql)
        self.dbapi.autocommit_calisirken.append(self.dbapi.autocommit)
        if self.dbapi.hata:
            raise self.dbapi.hata

    def nextset(self):
        self.dbapi.nextset_sayisi += 1
        self.kalan_nextset -= 1
        return self.kalan_nextset > 0

    def close(self):
        self.dbapi.imlec_kapandi = True


class SahteDbapi:
    def __init__(self, hata=None):
        self.autocommit = False
        self.calistirilan = []
        self.autocommit_calisirken = []
        self.nextset_sayisi = 0
        self.imlec_kapandi = False
        self.hata = hata

    def cursor(self):
        return SahteImlec(self)


class SahteHam:
    def __init__(self, dbapi):
        self.driver_connection = dbapi
        self.kapandi = False

    def close(self):
        self.kapandi = True


class SahteSonuc:
    def __init__(self, deger=None, satirlar=None):
        self._deger, self._satirlar = deger, satirlar or []

    def scalar(self):
        return self._deger

    def fetchall(self):
        return self._satirlar


class SahteBaglanti:
    def __init__(self, engine):
        self.engine = engine

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        s = str(sql)
        self.engine.sorgular.append(s)
        for anahtar, sonuc in self.engine.yanitlar.items():
            if anahtar in s:
                if isinstance(sonuc, Exception):
                    raise sonuc
                return sonuc
        return SahteSonuc(None)


class SahteEngine:
    def __init__(self, dbapi=None, yanitlar=None):
        self.dbapi = dbapi or SahteDbapi()
        self.ham = SahteHam(self.dbapi)
        self.yanitlar = yanitlar or {}
        self.sorgular = []

    def raw_connection(self):
        return self.ham

    def connect(self):
        return SahteBaglanti(self)


@pytest.fixture(autouse=True)
def _onbellegi_temizle():
    my._onbellek.clear()
    yield
    my._onbellek.clear()


def test_sql_degismezi_ve_kose_parantez_kacisi():
    assert my.sql_metin_degismezi("C:\\Yedek\\o'brien") == "N'C:\\Yedek\\o''brien'"
    assert my.koseli_parantez_kacisi("PTS") == "[PTS]"
    assert my.koseli_parantez_kacisi("a]b; DROP") == "[a]]b; DROP]"


def test_dongusel_dosya_adi_sinirlari_ve_donusum():
    g1 = date(2026, 10, 5)
    ad = my.dongusel_dosya_adi(14, g1)
    assert ad == f"pts_otomatik_yedek_{g1.toordinal() % 14}.bak"
    # 14 ardışık gün 14 FARKLI dosya adı üretir; 15. gün ilkinin üzerine yazar
    adlar = [my.dongusel_dosya_adi(14, g1 + timedelta(days=i)) for i in range(15)]
    assert len(set(adlar[:14])) == 14 and adlar[14] == adlar[0]
    # üst sınır / geçersiz değerler 14'e indirgenir
    assert my.dongusel_dosya_adi(30, g1) == ad
    assert my.dongusel_dosya_adi(0, g1) == ad
    assert my.dongusel_dosya_adi("bozuk", g1) == ad
    # küçük saklama: yalnızca 3 farklı dosya
    assert len({my.dongusel_dosya_adi(3, g1 + timedelta(days=i)) for i in range(10)}) == 3


def test_manuel_dosya_adi_ve_tam_yol_ters_egik_cizgi():
    assert my.manuel_dosya_adi(datetime(2026, 10, 5, 8, 9, 10)) == "pts_manuel_yedek_20261005_080910.bak"
    assert my.tam_yol("C:\\SQL\\Backup", "a.bak") == "C:\\SQL\\Backup\\a.bak"
    assert my.tam_yol("C:\\SQL\\Backup\\", "a.bak") == "C:\\SQL\\Backup\\a.bak"


def test_yedek_al_dogru_komutu_autocommit_ile_calistirir_ve_eski_haline_dondurur():
    eng = SahteEngine()
    yol = my.yedek_al(eng, "C:\\SQL\\Backup", "pts_otomatik_yedek_3.bak", veritabani="PTS")
    assert yol == "C:\\SQL\\Backup\\pts_otomatik_yedek_3.bak"
    sql = eng.dbapi.calistirilan[0]
    assert sql.startswith("BACKUP DATABASE [PTS] TO DISK = N'C:\\SQL\\Backup\\pts_otomatik_yedek_3.bak'")
    assert "WITH CHECKSUM, INIT, FORMAT" in sql
    assert eng.dbapi.autocommit_calisirken == [True], "BACKUP transaction DIŞINDA (autocommit) çalışmalı"
    assert eng.dbapi.autocommit is False, "havuza autocommit açık bağlantı bırakılmamalı"
    assert eng.dbapi.nextset_sayisi >= 1, "bilgi mesajı sonuç kümeleri tüketilmeli"
    assert eng.dbapi.imlec_kapandi and eng.ham.kapandi


def test_yedek_al_gecersiz_dosya_adini_reddeder():
    eng = SahteEngine()
    for kotu in ("../x.bak", "a b.bak", "x.db", "x.bak; DROP"):
        with pytest.raises(my.YedekHatasi):
            my.yedek_al(eng, "C:\\B", kotu, veritabani="PTS")
    assert eng.dbapi.calistirilan == []


def test_yedek_al_hatayi_anlasilir_sarar_ve_bagi_geri_birakir():
    eng = SahteEngine(SahteDbapi(hata=Exception("The user does not have permission to perform this action. (262)")))
    with pytest.raises(my.YedekHatasi) as e:
        my.yedek_al(eng, "C:\\B", "pts_x.bak", veritabani="PTS")
    assert "db_backupoperator" in str(e.value)
    assert eng.dbapi.autocommit is False and eng.ham.kapandi

    eng = SahteEngine(SahteDbapi(hata=Exception("Cannot open backup device. Operating system error 5(Access is denied.)")))
    with pytest.raises(my.YedekHatasi) as e:
        my.yedek_al(eng, "C:\\B", "pts_x.bak", veritabani="PTS")
    assert "servis hesabı" in str(e.value)


def test_yedegi_dogrula_siniflandirir():
    assert my.yedegi_dogrula(SahteEngine(), "C:\\B\\a.bak") == (True, None)
    sql = SahteEngine().dbapi  # sadece tip kontrolü için
    eng = SahteEngine()
    my.yedegi_dogrula(eng, "C:\\B\\a.bak")
    assert eng.dbapi.calistirilan[0] == "RESTORE VERIFYONLY FROM DISK = N'C:\\B\\a.bak' WITH CHECKSUM"
    # yetki yok -> None (BOZUK DEĞİL)
    saglam, mesaj = my.yedegi_dogrula(SahteEngine(SahteDbapi(hata=Exception("permission denied (229)"))), "x")
    assert saglam is None and mesaj
    # gerçek bozulma -> False
    saglam, mesaj = my.yedegi_dogrula(SahteEngine(SahteDbapi(hata=Exception("The backup set is corrupt"))), "x")
    assert saglam is False and "corrupt" in mesaj


def test_varsayilan_klasor_veri_klasoru_ve_etkin_klasor_ve_onbellek():
    eng = SahteEngine(yanitlar={
        "InstanceDefaultBackupPath": SahteSonuc("C:\\Program Files\\SQL\\Backup"),
        "sys.database_files": SahteSonuc("C:\\Program Files\\SQL\\DATA\\PTS.mdf"),
    })
    assert my.varsayilan_yedek_klasoru(eng) == "C:\\Program Files\\SQL\\Backup"
    assert my.veri_dosyasi_klasoru(eng) == "C:\\Program Files\\SQL\\DATA"
    n = len(eng.sorgular)
    assert my.varsayilan_yedek_klasoru(eng) == "C:\\Program Files\\SQL\\Backup"  # önbellekten
    assert len(eng.sorgular) == n
    assert my.etkin_yedek_klasoru(eng, {"mssql_yedek_klasoru": "D:\\Yedek"}) == "D:\\Yedek"
    assert my.etkin_yedek_klasoru(eng, {"mssql_yedek_klasoru": "  "}) == "C:\\Program Files\\SQL\\Backup"


def test_etkin_klasor_bulunamazsa_acik_hata():
    eng = SahteEngine(yanitlar={"InstanceDefaultBackupPath": Exception("boom")})
    with pytest.raises(my.YedekHatasi) as e:
        my.etkin_yedek_klasoru(eng, {})
    assert "elle girin" in str(e.value)


def test_yedek_gecmisi_ve_yas_hesaplari():
    simdi = datetime(2026, 10, 5, 12, 0, 0)
    satirlar = [
        (simdi - timedelta(hours=5), 5 * 1024 * 1024, "C:\\B\\pts.bak", 0),
        (simdi - timedelta(days=3), 1024, "C:\\B\\eski.bak", 1),
    ]
    eng = SahteEngine(yanitlar={"msdb.dbo.backupset": SahteSonuc(satirlar=satirlar)})
    g = my.yedek_gecmisi(eng, 30)
    assert [y["dosya_adi"] for y in g] == ["pts.bak", "eski.bak"]
    assert g[0]["boyut_bayt"] == 5 * 1024 * 1024 and g[1]["sadece_kopya"] is True
    assert "TOP 30" in eng.sorgular[0] and "type = 'D'" in eng.sorgular[0]
    assert abs(my.son_yedek_yasi_saat(g, simdi) - 5.0) < 1e-6
    assert my.otomatik_yedek_gerekli_mi(g, simdi) is False   # 5 saat önce yedek var -> atla
    assert my.yedek_yasi_uyarisi(g, simdi) is None
    # 3 gün önceki tek yedek: otomatik gerekli + uyarı
    eski = [dict(g[1])]
    assert my.otomatik_yedek_gerekli_mi(eski, simdi) is True
    assert "yedek eski" in my.yedek_yasi_uyarisi(eski, simdi)
    # hiç yedek yok
    assert my.otomatik_yedek_gerekli_mi([], simdi) is True
    assert "HİÇ yedek" in my.yedek_yasi_uyarisi([], simdi)
    assert my.son_yedek_yasi_saat([], simdi) is None


def test_yedek_gecmisi_adet_sinirlanir():
    eng = SahteEngine(yanitlar={"msdb.dbo.backupset": SahteSonuc(satirlar=[])})
    my.yedek_gecmisi(eng, 99999)
    assert "TOP 100" in eng.sorgular[0]
    my.yedek_gecmisi(eng, -5)
    assert "TOP 1 " in eng.sorgular[1]


def test_son_yedek_ozeti_onbellekler_ve_gecikmeyi_hesaplar(monkeypatch):
    from backend import mssql_yedek as m

    m._ozet_onbellek.clear()
    cagri = {"n": 0}

    def sahte_gecmis(engine, adet=30):
        cagri["n"] += 1
        return [{"tarih_saat": "2026-01-01T10:00:00", "dosya_adi": "pts.bak", "yol": "C:\\pts.bak"}]

    monkeypatch.setattr(m, "yedek_gecmisi", sahte_gecmis)
    from datetime import datetime
    ozet = m.son_yedek_ozeti(object(), simdi=datetime(2026, 1, 1, 12, 0, 0))
    assert ozet == {"basarili": True, "son_yedek_zamani": "2026-01-01T10:00:00", "gecikmis": False}
    m.son_yedek_ozeti(object())
    assert cagri["n"] == 1  # ikinci çağrı önbellekten
    m._ozet_onbellek.clear()


def test_son_yedek_ozeti_msdb_okunamazsa_basarisiz_doner(monkeypatch):
    from backend import mssql_yedek as m

    m._ozet_onbellek.clear()

    def patlat(engine, adet=30):
        raise RuntimeError("msdb yok")

    monkeypatch.setattr(m, "yedek_gecmisi", patlat)
    assert m.son_yedek_ozeti(object())["basarili"] is False
    m._ozet_onbellek.clear()
