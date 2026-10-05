"""SQL Server için veritabanı yedekleme (BACKUP DATABASE) yardımcıları.

NEDEN BU MODÜL VAR (2026-10-05): PTS'nin otomatik/manuel yedekleme kodu
yalnızca SQLite için yazılmıştı (bkz. main.py::_sqlite_yedek_al). SQL Server
kullanan kurulumlarda otomatik yedek döngüsü SESSİZCE hiç çalışmıyor, panel
ise "Henüz otomatik yedek alınmadı, ilk yedek en geç 6 saat içinde alınır"
diyerek sonsuza dek yanıltıcı bir bekleme mesajı gösteriyordu -- yönetici
yedeklerin alındığını sanabilirdi. Bu modül, SQL Server'ın KENDİ
`BACKUP DATABASE ... WITH CHECKSUM` komutunu kullanarak aynı güvenceyi verir.

ÖNEMLİ KISITLAR (SQL Server'ın doğası gereği):
- `.bak` dosyasını PTS değil, SQL Server SERVİSİ yazar. Hedef klasör SQL
  Server servis hesabının (ör. `NT Service\\MSSQL$SQLEXPRESS`) yazabildiği
  bir klasör olmalıdır; varsayılan olarak SQL Server'ın kendi yedek klasörü
  (`SERVERPROPERTY('InstanceDefaultBackupPath')`) kullanılır.
- PTS'nin SQL kullanıcısının `db_backupoperator` rolünde olması gerekir
  (yoksa hata açıkça raporlanır, sessizce yutulmaz).
- Hiçbir yedek dosyası SİLİNMEZ (SQL Server klasörüne PTS'nin silme yetkisi
  olmayabilir); eski yedekler, dosya adındaki DÖNGÜSEL numara sayesinde
  (`pts_otomatik_yedek_<n>.bak`, `INIT` ile) en eskisinin üzerine yazılarak
  kendiliğinden "temizlenir".
- Yedek geçmişi (kimin aldığı fark etmez -- elle SSMS'ten alınan `pts.bak`
  dahil) dosya sistemine değil, SQL Server'ın kendi `msdb` kayıtlarına
  bakılarak listelenir; bu sayede PTS'nin yedek klasörünü okuma yetkisi
  olması gerekmez.

Bu modül `sqlalchemy`'ye import anında bağımlı DEĞİLDİR (yalnızca bir
`engine` nesnesi alır); bu sayede sahte bir engine ile birim testleri
SQLAlchemy/SQL Server olmadan çalıştırılabilir.
"""
import logging
import ntpath
import re
import time
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger("pts")

OTOMATIK_DOSYA_ONEKI = "pts_otomatik_yedek_"
MANUEL_DOSYA_ONEKI = "pts_manuel_yedek_"
# Döngüsel otomatik yedek dosyası sayısı (gün): en eski yedeğin üzerine
# yazılır. Express sürümde sıkıştırma olmadığı için disk dolmasın diye üst
# sınır bilinçli olarak düşük tutulur.
EN_FAZLA_DONGU_GUN = 14
# Son yedek bundan eskiyse (saat) bir "yedek eski" uyarısı verilir.
ESKI_YEDEK_UYARI_SAAT = 48
# Son yedek bundan YENİYSE (saat) otomatik yedek alınmaz (elle SSMS'ten
# alınmış yedek de sayılır).
YENI_YEDEK_ATLAMA_SAAT = 20


# Değişmeyen sunucu bilgileri (veri/yedek klasörü yolu) kısa süre önbelleğe
# alınır: disk izleme/sağlık gibi sık çağrılan yerlerde her seferinde SQL
# Server'a gidilmesin (ve SQL Server kapalıyken bağlantı zaman aşımı yüzünden
# olay döngüsü tekrar tekrar bekletilmesin).
_ONBELLEK_SURE_SN = 600
_onbellek: dict = {}


def _onbellekli(anahtar: str, uretici):
    simdi = time.monotonic()
    kayit = _onbellek.get(anahtar)
    if kayit and simdi - kayit[0] < _ONBELLEK_SURE_SN:
        return kayit[1]
    deger = uretici()
    # Başarısız (None) sonuç da kısa süre hatırlanır -- aksi halde SQL Server
    # erişilemezken her çağrıda yeniden denenir.
    _onbellek[anahtar] = (simdi, deger)
    return deger


class YedekHatasi(Exception):
    """SQL Server yedeği/doğrulaması başarısız oldu; mesaj kullanıcıya
    gösterilebilir (Türkçe, açıklayıcı)."""


def _sql(metin: str):
    """`sqlalchemy.text` (varsa); yoksa (yalnızca sahte-engine testleri) düz
    metin."""
    try:
        from sqlalchemy import text
        return text(metin)
    except ImportError:  # pragma: no cover - yalnızca testlerde
        return metin


def koseli_parantez_kacisi(ad: str) -> str:
    """T-SQL tanımlayıcısını `[...]` içine güvenle koymak için `]` karakterini
    ikiler (SQL enjeksiyonu / özel karakterli veritabanı adı koruması)."""
    return "[" + str(ad).replace("]", "]]") + "]"


def sql_metin_degismezi(deger: str) -> str:
    """T-SQL unicode metin değişmezi (`N'...'`): tek tırnaklar ikilenir. BACKUP/
    RESTORE komutlarında dosya yolu parametre yerine değişmez olarak gömülür
    (bu komutlar her ODBC sürücüsünde parametre bağlamayı desteklemeyebilir);
    değerler yalnızca yönetici ayarından / doğrulanmış dosya adından gelir."""
    return "N'" + str(deger).replace("'", "''") + "'"


def hata_mesajini_sadelestir(exc: Exception) -> str:
    """ODBC/SQL Server hatasından okunabilir bir Türkçe açıklama çıkarır.
    Parola içerebilecek bağlantı bilgilerini ASLA içermez (yalnızca istisna
    metni kullanılır, bağlantı dizesi hiç dahil edilmez)."""
    ham = str(exc)
    kucuk = ham.lower()
    if "operating system error 5" in kucuk or "access is denied" in kucuk:
        return (
            "SQL Server servis hesabı yedek klasörüne YAZAMIYOR. Yedek klasörünü SQL Server'ın "
            "kendi yedek klasörüne alın (ayar boş bırakılırsa otomatik kullanılır) ya da klasöre "
            f"servis hesabına yazma izni verin. Ayrıntı: {ham[:300]}"
        )
    if "permission" in kucuk or "izni" in kucuk or "(229)" in ham or "(262)" in ham:
        return (
            "SQL Server yedek alma/doğrulama izni vermedi. PTS'nin SQL kullanıcısını "
            "`db_backupoperator` rolüne ekleyin (SSMS > Security > Logins > User Mapping). "
            f"Ayrıntı: {ham[:300]}"
        )
    if "operating system error 3" in kucuk or "cannot open backup device" in kucuk:
        return f"Yedek klasörü SQL Server makinesinde bulunamadı veya açılamadı. Ayrıntı: {ham[:300]}"
    return ham[:400]


def _calistir_tek_deger(engine, sql: str, params: Optional[dict] = None):
    with engine.connect() as con:
        return con.execute(_sql(sql), params or {}).scalar()


def veritabani_adi(engine) -> str:
    ad = _calistir_tek_deger(engine, "SELECT DB_NAME()")
    if not ad:
        raise YedekHatasi("Veritabanı adı SQL Server'dan alınamadı")
    return str(ad)


def varsayilan_yedek_klasoru(engine) -> Optional[str]:
    """SQL Server'ın kendi varsayılan yedek klasörü (SQL Server 2012+);
    alınamazsa None."""
    return _onbellekli("varsayilan_yedek_klasoru", lambda: _varsayilan_yedek_klasoru_oku(engine))


def _varsayilan_yedek_klasoru_oku(engine) -> Optional[str]:
    try:
        yol = _calistir_tek_deger(
            engine, "SELECT CAST(SERVERPROPERTY('InstanceDefaultBackupPath') AS NVARCHAR(4000))"
        )
        return str(yol).strip() if yol else None
    except Exception as exc:
        logger.warning("[mssql-yedek] varsayılan yedek klasörü alınamadı: %s", exc)
        return None


def veri_dosyasi_klasoru(engine) -> Optional[str]:
    """Veritabanının veri (.mdf) dosyasının bulunduğu klasör (disk doluluk
    izlemesi için); alınamazsa None."""
    return _onbellekli("veri_dosyasi_klasoru", lambda: _veri_dosyasi_klasoru_oku(engine))


def _veri_dosyasi_klasoru_oku(engine) -> Optional[str]:
    try:
        yol = _calistir_tek_deger(
            engine, "SELECT TOP 1 physical_name FROM sys.database_files WHERE type = 0 ORDER BY file_id"
        )
        return ntpath.dirname(str(yol)) if yol else None
    except Exception as exc:
        logger.warning("[mssql-yedek] veri dosyası klasörü alınamadı: %s", exc)
        return None


def etkin_yedek_klasoru(engine, ayarlar: dict) -> str:
    """Önce panel ayarı (`mssql_yedek_klasoru`), yoksa SQL Server varsayılanı."""
    ozel = str(ayarlar.get("mssql_yedek_klasoru") or "").strip()
    if ozel:
        return ozel
    varsayilan = varsayilan_yedek_klasoru(engine)
    if not varsayilan:
        raise YedekHatasi(
            "SQL Server'ın varsayılan yedek klasörü alınamadı. Sistem ayarlarından "
            "'SQL Server yedek klasörü'nü (SQL Server makinesindeki bir yol) elle girin."
        )
    return varsayilan


def dongusel_dosya_adi(saklama_gun: int, gun: Optional[date] = None) -> str:
    """`pts_otomatik_yedek_<n>.bak` -- n, bugünün sıra numarasından türetilir;
    böylece en fazla `N` farklı dosya olur ve en eskisinin üzerine yazılır."""
    try:
        n = int(saklama_gun)
    except (TypeError, ValueError):
        n = EN_FAZLA_DONGU_GUN
    if n <= 0 or n > EN_FAZLA_DONGU_GUN:
        n = EN_FAZLA_DONGU_GUN
    gun = gun or date.today()
    return f"{OTOMATIK_DOSYA_ONEKI}{gun.toordinal() % n}.bak"


def manuel_dosya_adi(simdi: Optional[datetime] = None) -> str:
    simdi = simdi or datetime.now()
    return f"{MANUEL_DOSYA_ONEKI}{simdi:%Y%m%d_%H%M%S}.bak"


def tam_yol(klasor: str, dosya_adi: str) -> str:
    """SQL Server (Windows) makinesindeki yol: ters eğik çizgiyle birleştirilir
    (PTS Linux'ta test edilse bile)."""
    return ntpath.join(klasor.rstrip("\\/") or klasor, dosya_adi)


def _tek_komut_calistir(engine, sql: str) -> None:
    """BACKUP/RESTORE VERIFYONLY bir işlem (transaction) İÇİNDE çalışamaz ve
    pyodbc'de bilgi mesajlarının (sonuç kümeleri) sonuna kadar tüketilmesi
    gerekir -- aksi halde komut tamamlanmadan bağlantı kapanabilir. Bu yüzden
    havuzdan alınan ham DBAPI bağlantısı geçici olarak autocommit'e alınır,
    `nextset()` ile tüketilir ve autocommit eski haline GERİ ALINIR (havuza
    autocommit açık bağlantı bırakılmaz)."""
    raw = engine.raw_connection()
    dbapi = getattr(raw, "driver_connection", None) or getattr(raw, "connection", raw)
    eski_autocommit = getattr(dbapi, "autocommit", False)
    try:
        dbapi.autocommit = True
        cur = dbapi.cursor()
        try:
            cur.execute(sql)
            while cur.nextset():
                pass
        finally:
            cur.close()
    finally:
        try:
            dbapi.autocommit = eski_autocommit
        finally:
            raw.close()


def yedek_al(engine, klasor: str, dosya_adi: str, veritabani: Optional[str] = None) -> str:
    """Tam yedek alır; tam `.bak` yolunu döner. `WITH CHECKSUM` yedeklenen
    sayfaların sağlamlığını yedekleme SIRASINDA doğrular (bozuk sayfa varsa
    komut hata verir -- sessiz bozuk yedek üretilmez). `INIT, FORMAT` aynı
    adlı eski dosyanın üzerine YAZAR (döngüsel saklama için)."""
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+\.bak", dosya_adi):
        raise YedekHatasi(f"Geçersiz yedek dosya adı: {dosya_adi!r}")
    veritabani = veritabani or veritabani_adi(engine)
    yol = tam_yol(klasor, dosya_adi)
    sql = (
        f"BACKUP DATABASE {koseli_parantez_kacisi(veritabani)} TO DISK = {sql_metin_degismezi(yol)} "
        f"WITH CHECKSUM, INIT, FORMAT, NAME = {sql_metin_degismezi(f'PTS tam yedek {datetime.now():%Y-%m-%d %H:%M}')}"
    )
    try:
        _tek_komut_calistir(engine, sql)
    except Exception as exc:
        raise YedekHatasi(hata_mesajini_sadelestir(exc)) from exc
    return yol


def yedegi_dogrula(engine, yol: str) -> "tuple[Optional[bool], Optional[str]]":
    """`RESTORE VERIFYONLY ... WITH CHECKSUM`. Döner: (True, None) sağlam;
    (False, hata) BOZUK; (None, açıklama) doğrulanamadı (ör. yetki yok --
    bu BOZUK anlamına GELMEZ, yedeğin kendisi `WITH CHECKSUM` ile zaten
    alınmıştır)."""
    try:
        _tek_komut_calistir(engine, f"RESTORE VERIFYONLY FROM DISK = {sql_metin_degismezi(yol)} WITH CHECKSUM")
        return True, None
    except Exception as exc:
        mesaj = hata_mesajini_sadelestir(exc)
        kucuk = str(exc).lower()
        if "permission" in kucuk or "denied" in kucuk or "(229)" in str(exc) or "(262)" in str(exc) \
                or "operating system error 5" in kucuk:
            return None, mesaj
        return False, mesaj


def yedek_gecmisi(engine, adet: int = 30) -> "list[dict]":
    """SQL Server'ın `msdb` kayıtlarından bu veritabanının TAM yedek geçmişi
    (elle SSMS'ten alınanlar dahil). En yeni başta."""
    adet = max(1, min(int(adet), 100))
    sql = (
        f"SELECT TOP {adet} bs.backup_finish_date, bs.backup_size, bmf.physical_device_name, bs.is_copy_only "
        "FROM msdb.dbo.backupset bs "
        "JOIN msdb.dbo.backupmediafamily bmf ON bs.media_set_id = bmf.media_set_id "
        "WHERE bs.database_name = DB_NAME() AND bs.type = 'D' "
        "ORDER BY bs.backup_finish_date DESC"
    )
    with engine.connect() as con:
        satirlar = con.execute(_sql(sql)).fetchall()
    sonuc = []
    for bitis, boyut, yol, kopya in satirlar:
        sonuc.append({
            "dosya_adi": ntpath.basename(str(yol)),
            "yol": str(yol),
            "boyut_bayt": int(boyut or 0),
            "tarih_saat": bitis.isoformat() if hasattr(bitis, "isoformat") else str(bitis),
            "sadece_kopya": bool(kopya),
        })
    return sonuc


def son_yedek_yasi_saat(gecmis: "list[dict]", simdi: Optional[datetime] = None) -> Optional[float]:
    """En yeni yedeğin yaşı (saat); hiç yedek yoksa None."""
    if not gecmis:
        return None
    simdi = simdi or datetime.now()
    try:
        son = datetime.fromisoformat(gecmis[0]["tarih_saat"])
    except (ValueError, KeyError):
        return None
    return max(0.0, (simdi - son).total_seconds() / 3600.0)


def otomatik_yedek_gerekli_mi(gecmis: "list[dict]", simdi: Optional[datetime] = None) -> bool:
    yas = son_yedek_yasi_saat(gecmis, simdi)
    return yas is None or yas >= YENI_YEDEK_ATLAMA_SAAT


def yedek_yasi_uyarisi(gecmis: "list[dict]", simdi: Optional[datetime] = None) -> Optional[str]:
    """Son yedek `ESKI_YEDEK_UYARI_SAAT`'ten eskiyse (ya da hiç yoksa) panelde
    gösterilecek Türkçe uyarı; sorun yoksa None."""
    yas = son_yedek_yasi_saat(gecmis, simdi)
    if yas is None:
        return "Bu veritabanı için SQL Server'da HİÇ yedek kaydı bulunamadı."
    if yas >= ESKI_YEDEK_UYARI_SAAT:
        return f"Son yedek {int(yas // 24)} gün {int(yas % 24)} saat önce alınmış -- yedek eski!"
    return None


_OZET_ONBELLEK_SN = 120
_ozet_onbellek: dict = {}


def son_yedek_ozeti(engine, simdi: Optional[datetime] = None) -> dict:
    """/sistem/saglik için kısa özet: {"basarili": bool, "son_yedek_zamani":
    iso|None, "gecikmis": bool|None}. msdb sorgusu 2 dk önbelleğe alınır
    (sağlık ucu sık yoklanır). msdb okunamıyorsa `basarili=False`."""
    simdi_mono = time.monotonic()
    kayit = _ozet_onbellek.get("ozet")
    if kayit and simdi_mono - kayit[0] < _OZET_ONBELLEK_SN:
        return kayit[1]
    try:
        gecmis = yedek_gecmisi(engine, 1)
    except Exception as exc:
        logger.warning("[mssql-yedek] sağlık özeti için yedek geçmişi okunamadı: %s", exc)
        ozet = {"basarili": False, "son_yedek_zamani": None, "gecikmis": None}
    else:
        yas = son_yedek_yasi_saat(gecmis, simdi)
        ozet = {
            "basarili": True,
            "son_yedek_zamani": gecmis[0]["tarih_saat"] if gecmis else None,
            "gecikmis": yas is None or yas >= ESKI_YEDEK_UYARI_SAAT,
        }
    _ozet_onbellek["ozet"] = (simdi_mono, ozet)
    return ozet
