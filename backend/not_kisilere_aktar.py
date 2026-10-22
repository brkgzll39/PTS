"""Geçiş notlarındaki TPIC / Servis araçlarını kişi olarak kaydeder (2026-10-22).

Kullanıcı isteği: "şimdiye kadar notlara kaydedilmiş TPIC, TPİC, Servis,
Personel servislerini tarayıp bunları bir daha not yazılmayacak şekilde
sisteme entegre edelim. TPIC ile ilgili araçları TPIC isimli kişiye, servisi
de aynı şekilde; araç giriş yaptığı zaman TPIC veya Servis olarak notları
otomatik gelsin."

Ne yapar:
  * Tüm geçiş kayıtlarının notlarını (ve misafir adını) tarar:
      "TPIC" / "TPİC" / "tpıc" ...           -> TPIC
      "Servis", "Personel servisi", "SERVİS" -> Servis
    (İkisi birden geçen notta TPIC kazanır.)
  * Her plakayı en çok hangi grupta görüldüyse o gruba koyar.
  * "TPIC" ve "Servis" adlı kişileri bulur ya da oluşturur (tip: alt işveren --
    geçiş izni var, LED tabelada ZİYARETÇİ, panelde "Alt İşveren" yazar;
    otomatik not: "TPIC" / "Servis") ve plakaları bu kişilere araç olarak
    ekler. Bu araçlar geçince nota otomatik "TPIC" / "Servis" yazılır.
    Bu adlarla daha önce "personel" olarak açılmış kişi varsa tipi alt
    işverene çevrilir.
  * Plaka zaten BAŞKA bir kişiye kayıtlıysa o kişiye dokunulmaz, araç
    taşınmaz; yalnızca o kişinin "otomatik not" alanı boşsa doldurulur
    (--mevcut-kisilere-dokunma ile bu da kapatılır).
  * Bu plakaların daha önce "yetkisiz" kalmış geçmiş geçişleri, kişi panelden
    eklenmiş gibi bu kişiye bağlanır.

KULLANIM (proje klasöründen, PowerShell):

  .venv\\Scripts\\python.exe -m backend.not_kisilere_aktar
      Yalnızca RAPOR. Hiçbir şeyi değiştirmez.

  .venv\\Scripts\\python.exe -m backend.not_kisilere_aktar --uygula
      Rapordakileri kaydeder; önce "EVET" yazmanız istenir.

  --haric "34 ABC 123" --haric "06 XY 45"   bu plakalar atlanır (tekrarlanabilir;
                                           ör. "teknik servis" gibi yanlış eşleşmeler)
  --min-adet 2                             en az bu kadar notlu geçişi olan plakalar

ÖNCE YEDEK ALIN.
"""
import argparse
import re
import sys
from collections import Counter, defaultdict

GRUPLAR = {
    # grup: (kişi adı, departman, otomatik not)
    "TPIC": ("TPIC", "TPIC", "TPIC"),
    "SERVIS": ("Servis", "Personel Servisi", "Servis"),
}
ALT_ISVEREN = "alt_isveren"
_TR = str.maketrans({"İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s", "Ç": "c", "ç": "c",
                     "Ğ": "g", "ğ": "g", "Ö": "o", "ö": "o", "Ü": "u", "ü": "u"})
_PLAKA = re.compile(r"^\d{2} ?[A-Z]{1,3} ?\d{2,5}$")


def notun_grubu(metin) -> str:
    """Notun ait olduğu grup ("TPIC", "SERVIS") ya da None."""
    if not metin:
        return None
    sade = metin.translate(_TR).lower()
    if re.search(r"t\s*\.?\s*p\s*\.?\s*i\s*\.?\s*c", sade):
        return "TPIC"
    if "servis" in sade:
        return "SERVIS"
    return None


def _norm(plaka: str) -> str:
    return (plaka or "").upper().replace(" ", "").strip()


def tara(db, haric=(), min_adet=1) -> dict:
    """{grup: [(plaka, adet, ornek_notlar)]} ve atlananlar."""
    from backend import models
    sayac = defaultdict(Counter)       # norm plaka -> Counter(grup)
    gosterim = {}                      # norm plaka -> ilk görülen yazım
    ornekler = defaultdict(set)
    sorgu = db.query(models.Kayit.plaka_no, models.Kayit.not_metni, models.Kayit.misafir_adi).filter(
        (models.Kayit.not_metni.isnot(None)) | (models.Kayit.misafir_adi.isnot(None)))
    for plaka, notu, misafir in sorgu.yield_per(2000):
        grup = notun_grubu(notu) or notun_grubu(misafir)
        if not grup:
            continue
        n = _norm(plaka)
        sayac[n][grup] += 1
        gosterim.setdefault(n, plaka.strip().upper())
        if len(ornekler[n]) < 3:
            ornekler[n].add((notu or misafir).strip()[:40])
    haric_n = {_norm(h) for h in haric}
    sonuc = {g: [] for g in GRUPLAR}
    atlanan = []
    for n, c in sayac.items():
        grup, adet = c.most_common(1)[0]
        toplam = sum(c.values())
        if n in haric_n:
            atlanan.append((gosterim[n], toplam, "hariç tutuldu"))
        elif not _PLAKA.match(gosterim[n]):
            atlanan.append((gosterim[n], toplam, "geçerli plaka biçimi değil"))
        elif toplam < min_adet:
            atlanan.append((gosterim[n], toplam, f"{min_adet} adetten az"))
        else:
            sonuc[grup].append((gosterim[n], toplam, sorted(ornekler[n])))
    for g in sonuc:
        sonuc[g].sort(key=lambda r: -r[1])
    return {"gruplar": sonuc, "atlanan": sorted(atlanan)}


def _sahipler(db) -> dict:
    from backend import models
    kisiler = {k.id: k for k in db.query(models.Kisi).all()}
    harita = {}
    for k in kisiler.values():
        harita.setdefault(_norm(k.plaka_no), k)
    for ek in db.query(models.KisiPlaka).all():
        if ek.kisi_id in kisiler:
            harita.setdefault(_norm(ek.plaka_no), kisiler[ek.kisi_id])
    return harita


def planla(db, tarama: dict) -> list:
    """[(grup, plaka, eylem, ayrinti)] -- eylem: 'ekle' | 'zaten' | 'baska_kiside'."""
    sahipler = _sahipler(db)
    plan = []
    for grup, satirlar in tarama["gruplar"].items():
        ad = GRUPLAR[grup][0]
        for plaka, _, _ in satirlar:
            sahip = sahipler.get(_norm(plaka))
            if sahip is None:
                plan.append((grup, plaka, "ekle", ""))
            elif sahip.ad_soyad.strip().casefold() == ad.casefold():
                plan.append((grup, plaka, "zaten", ""))
            else:
                plan.append((grup, plaka, "baska_kiside", f"{sahip.ad_soyad} (id={sahip.id})"))
    return plan


def uygula(db, plan: list, mevcut_kisilere_not: bool, kullanici_adi: str = "not_kisilere_aktar") -> dict:
    from backend import main, models
    ozet = {"eklenen_arac": 0, "olusturulan_kisi": 0, "notu_doldurulan_kisi": 0, "baglanan_gecis": 0,
            "tipi_degisen_kisi": 0}
    hedefler = {}
    for grup in GRUPLAR:
        plakalar = [p for g, p, e, _ in plan if g == grup and e == "ekle"]
        ad, departman, otomatik = GRUPLAR[grup]
        kisi = (db.query(models.Kisi).filter(models.Kisi.ad_soyad == ad)
                .order_by(models.Kisi.id).first())
        if kisi is None and not plakalar:
            continue
        if kisi is None:
            kisi = models.Kisi(ad_soyad=ad, plaka_no=plakalar.pop(0), tip=ALT_ISVEREN,
                               daire_departman=departman, otomatik_not=otomatik,
                               aciklama="Geçiş notlarından otomatik oluşturuldu")
            db.add(kisi)
            db.flush()
            ozet["olusturulan_kisi"] += 1
            ozet["eklenen_arac"] += 1
        else:
            if not (kisi.otomatik_not or "").strip():
                kisi.otomatik_not = otomatik
            if kisi.tip == "personel":   # 2026-10-22: LED'de PERSONEL değil ZİYARETÇİ yazsın
                kisi.tip = ALT_ISVEREN
                ozet["tipi_degisen_kisi"] += 1
        for plaka in plakalar:
            db.add(models.KisiPlaka(kisi_id=kisi.id, plaka_no=plaka, aciklama="Notlardan aktarıldı"))
            ozet["eklenen_arac"] += 1
        hedefler[grup] = kisi
    if mevcut_kisilere_not:
        sahipler = _sahipler(db)
        for grup, plaka, eylem, _ in plan:
            if eylem != "baska_kiside":
                continue
            sahip = sahipler.get(_norm(plaka))
            if sahip is not None and not (sahip.otomatik_not or "").strip():
                sahip.otomatik_not = GRUPLAR[grup][2]
                ozet["notu_doldurulan_kisi"] += 1
    db.commit()
    for kisi in hedefler.values():
        ozet["baglanan_gecis"] += main._gecmis_kayitlari_kisiye_bagla(db, kisi, kullanici_adi)
    db.add(models.DenetimKaydi(
        kullanici_adi=kullanici_adi, eylem="not_kisilere_aktar",
        aciklama=(f"Notlardan aktarım: {ozet['eklenen_arac']} araç, {ozet['olusturulan_kisi']} yeni kişi, "
                  f"{ozet['notu_doldurulan_kisi']} kişiye otomatik not, {ozet['baglanan_gecis']} geçmiş geçiş bağlandı"),
    ))
    db.commit()
    return ozet


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Notlardaki TPIC / Servis araçlarını kişilere aktarır.")
    ap.add_argument("--uygula", action="store_true")
    ap.add_argument("--haric", action="append", default=[])
    ap.add_argument("--min-adet", type=int, default=1)
    ap.add_argument("--mevcut-kisilere-dokunma", action="store_true",
                    help="başka kişiye kayıtlı plakaların kişisine otomatik not yazma")
    ap.add_argument("--evet", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    from backend.database import SessionLocal
    import backend.main  # noqa: F401 -- veritabanı şema güncellemesi (otomatik_not sütunu)
    db = SessionLocal()
    try:
        tarama = tara(db, args.haric, args.min_adet)
        plan = planla(db, tarama)
        eylemler = {(g, p): (e, a) for g, p, e, a in plan}
        if not plan:
            print("Notlarda TPIC / Servis geçen geçiş bulunamadı.")
            return 0
        for grup, satirlar in tarama["gruplar"].items():
            ad = GRUPLAR[grup][0]
            print(f"\n=== {ad}: {len(satirlar)} araç ===")
            print(f"{'Plaka':<14}{'Geçiş':>6}   Durum / örnek notlar")
            for plaka, adet, ornek in satirlar:
                eylem, ayrinti = eylemler[(grup, plaka)]
                durum = {"ekle": f"'{ad}' kişisine eklenecek", "zaten": f"zaten '{ad}' kişisinde",
                         "baska_kiside": f"başka kişide: {ayrinti}"}[eylem]
                print(f"{plaka:<14}{adet:>6}   {durum}  |  {' / '.join(ornek)}")
        if tarama["atlanan"]:
            print(f"\nAtlanan ({len(tarama['atlanan'])}):")
            for plaka, adet, neden in tarama["atlanan"]:
                print(f"  {plaka:<14}{adet:>4}  {neden}")
        eklenecek = sum(1 for _, _, e, _ in plan if e == "ekle")
        baska = sum(1 for _, _, e, _ in plan if e == "baska_kiside")
        print(f"\nToplam: {eklenecek} araç eklenecek, {baska} araç başka kişide kayıtlı"
              + ("" if args.mevcut_kisilere_dokunma or not baska
                 else " (o kişilerin otomatik notu boşsa TPIC/Servis yazılacak)") + ".")
        if not args.uygula:
            print("\nBu yalnızca bir rapordu, hiçbir şey değiştirilmedi.")
            print("Yanlış eşleşen plaka varsa --haric \"PLAKA\" ile çıkarın. Kaydetmek için: --uygula")
            return 0
        if not args.evet:
            if input('\nKaydetmek için büyük harflerle EVET yazın: ').strip() != "EVET":
                print("İptal edildi, hiçbir şey değiştirilmedi.")
                return 1
        ozet = uygula(db, plan, not args.mevcut_kisilere_dokunma)
        print(f"Tamam: {ozet['eklenen_arac']} araç eklendi ({ozet['olusturulan_kisi']} yeni kişi, "
              f"{ozet['tipi_degisen_kisi']} kişi alt işverene çevrildi), "
              f"{ozet['notu_doldurulan_kisi']} mevcut kişiye otomatik not yazıldı, "
              f"{ozet['baglanan_gecis']} geçmiş geçiş bu kişilere bağlandı.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
