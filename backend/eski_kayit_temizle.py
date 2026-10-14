"""Eski / tanımsız kamera adlı geçiş kayıtlarını listeler ve (onayla) siler.

2026-10-14 kullanıcı isteği: "eski adları da kullanma, hatta veritabanında
eskiden kaydettiğim cacheler varsa onları da ayıklayabilirsin". Kayıtlarda
şu an tanımlı olmayan kamera adları kalmış: eski bir sürüm Türkçe harfleri
sildiği için kırpılmış adlar ("Nizamiye Giri", "Nizamiye k", "Lojman C",
"giri") ve test/elle giriş adları ("GIRIS-KAMERA", "PANEL-MANUEL").

KULLANIM (proje klasöründen, PowerShell):

  .venv\\Scripts\\python.exe -m backend.eski_kayit_temizle
      Yalnızca RAPOR: hangi eski ad, kaç kayıt, hangi tarihler arası.
      Hiçbir şeyi değiştirmez.

  .venv\\Scripts\\python.exe -m backend.eski_kayit_temizle --sil
      Rapordaki OTOMATİK (kamera) kayıtlarını siler; önce "EVET" yazmanız
      istenir. Elle girilmiş kayıtlar (görevlinin panelden girdiği) KORUNUR;
      onları da silmek için --manuel-dahil ekleyin.

  --ad "GIRIS-KAMERA" --ad "giri"   yalnızca bu adlardaki kayıtlar
                                    (tekrarlanabilir; ad tam yazılmalı)

Silinen kaydın araç fotoğrafı ve küçük resmi de diskten silinir; kayda
bağlı alarmlar korunur (yalnızca kayıtla bağlantıları koparılır, panelin
kayıt silme düğmesiyle aynı davranış). İşlem Denetim Kayıtları'na yazılır.

ÖNCE YEDEK ALIN: silme geri alınamaz.
"""
import argparse
import json
import os
import sys
from datetime import datetime

from sqlalchemy import func

from backend import kucuk_gorsel, models
from backend.database import SessionLocal

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
GORUNTU_KLASORU = os.path.join(os.path.dirname(BACKEND_DIR), "goruntuler")
KAMERA_DOSYASI = os.getenv("PTS_CAMERAS_FILE") or os.path.join(BACKEND_DIR, "cameras.json")


def tanimli_kamera_adlari() -> set:
    try:
        with open(KAMERA_DOSYASI, encoding="utf-8") as f:
            return {k.get("ad") for k in json.load(f) if k.get("ad")}
    except (OSError, ValueError):
        return set()


def eski_ad_raporu(db, tanimli: set) -> list:
    """[(ad, toplam, manuel, ilk_tarih, son_tarih)] -- tanımlı olmayan adlar, çoktan aza."""
    K = models.Kayit
    satirlar = (
        db.query(K.kamera_id, func.count(K.id), func.min(K.tarih_saat), func.max(K.tarih_saat))
        .group_by(K.kamera_id).all()
    )
    rapor = []
    for ad, toplam, ilk, son in satirlar:
        if ad in tanimli:
            continue
        manuel = db.query(func.count(K.id)).filter(K.kamera_id == ad, K.manuel_giris == True).scalar()  # noqa: E712
        rapor.append((ad, toplam, manuel or 0, ilk, son))
    return sorted(rapor, key=lambda r: -r[1])


def _tarih(d) -> str:
    return d.strftime("%d.%m.%Y") if d else "-"


def _gorseli_sil(yol) -> None:
    if not yol:
        return
    tam = yol if os.path.isabs(yol) else os.path.join(GORUNTU_KLASORU, os.path.basename(yol))
    # Yalnızca görüntü klasöründeki dosyalar silinir.
    if os.path.dirname(os.path.abspath(tam)) != os.path.abspath(GORUNTU_KLASORU):
        return
    try:
        os.remove(tam)
    except OSError:
        pass
    kucuk_gorsel.kucuk_gorseli_sil(tam)


def sil(db, adlar: list, manuel_dahil: bool) -> tuple:
    """Verilen adlardaki kayıtları siler; (silinen_kayit, korunan_manuel) döner."""
    K = models.Kayit
    sorgu = db.query(K).filter(K.kamera_id.in_(adlar))
    korunan = 0
    if not manuel_dahil:
        korunan = sorgu.filter(K.manuel_giris == True).count()  # noqa: E712
        sorgu = sorgu.filter((K.manuel_giris == False) | (K.manuel_giris.is_(None)))  # noqa: E712
    silinen = 0
    while True:
        parti = sorgu.limit(500).all()
        if not parti:
            break
        idler = [k.id for k in parti]
        db.query(models.Alarm).filter(models.Alarm.kayit_id.in_(idler)).update(
            {"kayit_id": None}, synchronize_session=False)
        for k in parti:
            _gorseli_sil(k.goruntu_yolu)
            db.delete(k)
        db.commit()
        silinen += len(parti)
    if silinen:
        db.add(models.DenetimKaydi(
            kullanici_adi="eski_kayit_temizle",
            eylem="eski_kayit_sil",
            aciklama=f"{silinen} eski/tanımsız kamera adlı kayıt silindi: {', '.join(adlar)}"[:1000],
        ))
        db.commit()
    return silinen, korunan


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Eski / tanımsız kamera adlı geçiş kayıtlarını listeler ve siler.")
    ap.add_argument("--sil", action="store_true", help="kayıtları sil (onay ister)")
    ap.add_argument("--ad", action="append", default=[], help="yalnızca bu kamera adı (tekrarlanabilir)")
    ap.add_argument("--manuel-dahil", action="store_true", help="elle girilmiş kayıtları da sil")
    ap.add_argument("--evet", action="store_true", help=argparse.SUPPRESS)  # testler için onay
    args = ap.parse_args(argv)

    tanimli = tanimli_kamera_adlari()
    if not tanimli:
        print("HATA: tanımlı kamera bulunamadı (cameras.json okunamadı) -- güvenlik için hiçbir şey yapılmadı.")
        return 2
    print("Tanımlı kameralar:", ", ".join(sorted(tanimli)))

    db = SessionLocal()
    try:
        rapor = eski_ad_raporu(db, tanimli)
        if args.ad:
            bilinmeyen = [a for a in args.ad if a not in {r[0] for r in rapor}]
            if bilinmeyen:
                print("UYARI: şu adlar eski adlar arasında yok (tanımlı bir kamera ya da yazım hatası):",
                      ", ".join(bilinmeyen))
            rapor = [r for r in rapor if r[0] in args.ad]
        if not rapor:
            print("Tanımsız kamera adlı kayıt yok -- temizlenecek bir şey bulunmadı.")
            return 0

        print()
        print(f"{'Eski kamera adı':<24}{'Kayıt':>8}{'Elle':>7}   Tarih aralığı")
        for ad, toplam, manuel, ilk, son in rapor:
            print(f"{(ad or '(boş)'):<24}{toplam:>8}{manuel:>7}   {_tarih(ilk)} - {_tarih(son)}")
        toplam = sum(r[1] for r in rapor)
        manuel = sum(r[2] for r in rapor)
        silinecek = toplam if args.manuel_dahil else toplam - manuel
        print(f"\nToplam {toplam} kayıt ({manuel} tanesi elle girilmiş).")

        if not args.sil:
            print("\nBu yalnızca bir rapordu, hiçbir şey değiştirilmedi.")
            print("Silmek için: .venv\\Scripts\\python.exe -m backend.eski_kayit_temizle --sil"
                  + ("" if not manuel else "   (elle girilenler korunur; onları da silmek için --manuel-dahil)"))
            return 0

        print(f"\n{silinecek} kayıt, fotoğraflarıyla birlikte KALICI olarak silinecek"
              + ("" if args.manuel_dahil or not manuel else f"; {manuel} elle girilmiş kayıt korunacak") + ".")
        if not args.evet:
            onay = input('Devam etmek için büyük harflerle EVET yazın: ').strip()
            if onay != "EVET":
                print("İptal edildi, hiçbir şey silinmedi.")
                return 1
        silinen, korunan = sil(db, [r[0] for r in rapor], args.manuel_dahil)
        print(f"Silindi: {silinen} kayıt." + (f" Korunan elle girilmiş kayıt: {korunan}." if korunan else ""))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
