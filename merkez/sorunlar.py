"""Bir kurulumun son sağlık özetinden sorun listesi çıkarır (saf fonksiyon, test edilir).

Her sorun: {"kod": değişmez kimlik (bildirim tekrarını önler), "seviye": "kritik"|"uyari",
"mesaj": Türkçe açıklama}. Eşikler ortam değişkeniyle değil burada sabit; satıcı
ihtiyaca göre değiştirir.
"""
from datetime import datetime, timedelta
from typing import Optional

CEVRIMDISI_DK = 15          # bu kadar dakika (ya da 3 gönderim aralığı) haber gelmezse
DISK_UYARI, DISK_KRITIK = 85.0, 95.0
YEDEK_UYARI_SAAT, YEDEK_KRITIK_SAAT = 36, 72
LISANS_UYARI_GUN, LISANS_KRITIK_GUN = 30, 7
BAKIM_UYARI_GUN = 30
SERTIFIKA_UYARI_GUN = 14
MUTABAKAT_UYARI_ORAN = 90.0
MUTABAKAT_EN_AZ_GECIS = 20
KAYITSIZ_UYARI_DK = 24 * 60

SEVIYE_SIRA = {"kritik": 0, "uyari": 1}


def _s(kod: str, seviye: str, mesaj: str) -> dict:
    return {"kod": kod, "seviye": seviye, "mesaj": mesaj}


def _sure_metni(dk: float) -> str:
    dk = int(dk)
    if dk < 60:
        return f"{dk} dakika"
    if dk < 48 * 60:
        return f"{dk // 60} saat"
    return f"{dk // 1440} gün"


def sorunlari_hesapla(ozet: Optional[dict], son_nabiz: Optional[float], simdi: float,
                      aralik_sn: int = 300, bakim_bitis: Optional[str] = None) -> list:
    """`son_nabiz`/`simdi`: merkezin saatine göre epoch saniye."""
    sorunlar = []
    bugun = datetime.fromtimestamp(simdi).date()
    if bakim_bitis:
        try:
            kalan = (datetime.fromisoformat(bakim_bitis).date() - bugun).days
            if kalan < 0:
                sorunlar.append(_s("bakim_bitti", "uyari", f"Bakım sözleşmesi {-kalan} gün önce bitti"))
            elif kalan <= BAKIM_UYARI_GUN:
                sorunlar.append(_s("bakim_bitiyor", "uyari", f"Bakım sözleşmesinin bitişine {kalan} gün kaldı"))
        except ValueError:
            pass
    if son_nabiz is None:
        sorunlar.append(_s("hic_baglanmadi", "uyari", "Kurulum henüz merkeze hiç bağlanmadı"))
        return _sirala(sorunlar)
    sessizlik_dk = (simdi - son_nabiz) / 60
    if sessizlik_dk > max(CEVRIMDISI_DK, 3 * aralik_sn / 60):
        sorunlar.append(_s("cevrimdisi", "kritik",
                           f"{_sure_metni(sessizlik_dk)}dır haber yok (sunucu kapalı, PTS durmuş ya da internet yok)"))
    if not ozet:
        return _sirala(sorunlar)

    if ozet.get("veritabani") not in (None, "tamam"):
        sorunlar.append(_s("veritabani", "kritik", "Veritabanına ulaşılamıyor"))

    aktif_kamera = 0
    for k in ozet.get("kameralar") or []:
        if not k.get("aktif", True):
            continue
        aktif_kamera += 1
        ad = str(k.get("ad") or "?")
        if k.get("goruntu") in ("durdu", "donmus"):
            sorunlar.append(_s(f"kamera_goruntu:{ad}", "kritik", f"{ad}: kameradan görüntü gelmiyor"))
        if k.get("dahua_bagli") is False:
            sorunlar.append(_s(f"kamera_okuma:{ad}", "uyari", f"{ad}: kameranın plaka okuma bağlantısı kopuk"))
        m = k.get("mutabakat") or {}
        if m.get("hata"):
            sorunlar.append(_s(f"mutabakat_hata:{ad}", "uyari", f"{ad}: gece mutabakatı yapılamadı ({m.get('gun')})"))
        elif m.get("oran") is not None and (m.get("kamera_gecis") or 0) >= MUTABAKAT_EN_AZ_GECIS \
                and m["oran"] < MUTABAKAT_UYARI_ORAN:
            sorunlar.append(_s(f"mutabakat:{ad}", "uyari",
                               f"{ad}: PTS kameranın okuduğu geçişlerin %{m['oran']:.0f}'ini yakaladı ({m.get('gun')})"))

    son_kayit = ozet.get("son_kayit_dk")
    if aktif_kamera and son_kayit is not None and son_kayit >= KAYITSIZ_UYARI_DK:
        sorunlar.append(_s("kayit_yok", "uyari", f"{_sure_metni(son_kayit)}dır hiç geçiş kaydedilmedi"))

    disk = ozet.get("disk") or {}
    for y in disk.get("yollar") or []:
        yuzde = y.get("yuzde")
        if yuzde is None:
            continue
        if yuzde >= DISK_KRITIK:
            sorunlar.append(_s(f"disk:{y.get('ad')}", "kritik", f"Disk %{yuzde:.0f} dolu ({y.get('ad')})"))
        elif yuzde >= DISK_UYARI:
            sorunlar.append(_s(f"disk:{y.get('ad')}", "uyari", f"Disk %{yuzde:.0f} dolu ({y.get('ad')})"))

    yedek = ozet.get("yedek") or {}
    if yedek.get("otomatik_acik") is False:
        sorunlar.append(_s("yedek_kapali", "uyari", "Otomatik yedek kapalı"))
    elif yedek.get("yas_saat") is not None:
        yas = float(yedek["yas_saat"])
        if yas >= YEDEK_KRITIK_SAAT:
            sorunlar.append(_s("yedek", "kritik", f"Son yedek {_sure_metni(yas * 60)} önce alınmış"))
        elif yas >= YEDEK_UYARI_SAAT:
            sorunlar.append(_s("yedek", "uyari", f"Son yedek {_sure_metni(yas * 60)} önce alınmış"))

    lisans = ozet.get("lisans") or {}
    if lisans.get("aktif") is False:
        sorunlar.append(_s("lisans", "kritik", "Lisans aktif değil (süresi dolmuş ya da girilmemiş)"))
    elif lisans.get("kalan_gun") is not None:
        kalan = int(lisans["kalan_gun"])
        if kalan <= LISANS_KRITIK_GUN:
            sorunlar.append(_s("lisans", "kritik", f"Lisansın bitişine {kalan} gün kaldı"))
        elif kalan <= LISANS_UYARI_GUN:
            sorunlar.append(_s("lisans", "uyari", f"Lisansın bitişine {kalan} gün kaldı"))

    sertifika = ozet.get("sertifika_kalan_gun")
    if sertifika is not None and sertifika <= SERTIFIKA_UYARI_GUN:
        sorunlar.append(_s("sertifika", "uyari", f"HTTPS sertifikasının bitişine {sertifika} gün kaldı"))

    alarmlar = ozet.get("alarmlar_24s") or {}
    if alarmlar.get("sessiz_kamera"):
        sorunlar.append(_s("sessiz_kamera", "uyari", "Son 24 saatte sessiz kalan kamera oldu (plaka okumuyor)"))
    if alarmlar.get("bildirim_hatasi"):
        sorunlar.append(_s("bildirim_hatasi", "uyari", "Kurulumun bildirimleri (Telegram/e-posta) gitmiyor"))
    for tip, mesaj in (("kamera_arizasi", "Son 24 saatte kamera arıza alarmı oluştu"),
                       ("bariyer_hatasi", "Son 24 saatte bariyer açılamadı"),
                       ("disk_hatasi", "Son 24 saatte disk yazma hatası oldu"),
                       ("yedek_bozuk", "Son alınan yedek bozuk çıktı")):
        if alarmlar.get(tip):
            sorunlar.append(_s(f"alarm:{tip}", "uyari", f"{mesaj} ({alarmlar[tip]} kez)"))

    try:
        ozet_zamani = datetime.fromisoformat(ozet.get("zaman") or "")
    except ValueError:
        ozet_zamani = None
    for k in ozet.get("kesintiler_7g") or []:
        try:
            bitis = datetime.fromisoformat(k["bitis"])
        except (KeyError, ValueError):
            continue
        if ozet_zamani and ozet_zamani - bitis <= timedelta(hours=24):
            sorunlar.append(_s(f"kesinti:{k['bitis']}", "uyari",
                               f"Sunucu {_sure_metni(k.get('sure_dk') or 0)} kapalı kaldı ({k.get('baslangic', '')[:16].replace('T', ' ')})"))
    return _sirala(sorunlar)


def _sirala(sorunlar: list) -> list:
    return sorted(sorunlar, key=lambda s: SEVIYE_SIRA.get(s["seviye"], 9))


def genel_durum(sorunlar: list) -> str:
    """kritik | uyari | iyi | cevrimdisi"""
    kodlar = {s["kod"] for s in sorunlar}
    if "cevrimdisi" in kodlar:
        return "cevrimdisi"
    if any(s["seviye"] == "kritik" for s in sorunlar):
        return "kritik"
    if sorunlar:
        return "uyari"
    return "iyi"
