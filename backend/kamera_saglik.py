"""Kamera sağlık bekçisi (2026-11-06, kullanıcı isteği).

Kamera teşhisinde (2026-11-03) elle bulunan sorunlar kendiliğinden yakalansın diye
her gün Dahua kameralara YALNIZ OKUYAN üç soru sorulur ve gece mutabakatının
sonucuna bakılır:

  * Saat:   global.cgi?action=getCurrentTime  -> sunucu saatinden kaç sn sapmış?
  * NTP:    configManager.cgi?action=getConfig&name=NTP -> saat eşitleme açık mı?
  * Yön:    configManager.cgi?action=getConfig&name=VideoAnalyseRule -> ANPR kuralı
            iki yönü de (Obverse + Reverse) okuyor mu? Sahada yalnız "Obverse"
            okuyan kameralar karşıdan gelen araçları kaçırıyordu.
  * Kaçırma: dünkü mutabakatta kameranın okuyup PTS'in kaçırdığı geçiş oranı.

Kameraya hiçbir ayar YAZILMAZ. Bu modülde ağ dışında yan etki yoktur;
`sorunlari_bul` saf fonksiyondur (testlenebilir).
"""
from datetime import datetime
from typing import Optional

SAAT_ESIK_SN = 30            # bundan büyük sapma sorun sayılır
KACIRMA_ESIK = 0.05          # dünkü geçişlerin %5'inden fazlası kaçırıldıysa
KACIRMA_EN_AZ_GECIS = 20     # daha az geçişle oran rastlantıya açık


def _kv(metin: str) -> dict:
    sonuc = {}
    for satir in (metin or "").splitlines():
        anahtar, esit, deger = satir.strip().partition("=")
        if esit:
            sonuc[anahtar.strip()] = deger.strip()
    return sonuc


def yonleri_ayikla(metin: str) -> Optional[list]:
    """VideoAnalyseRule yanıtından AÇIK kuralların okuduğu yönler (ör. ["Obverse"]).
    Yön bilgisi olan açık kural yoksa None."""
    kv = _kv(metin)
    kurallar = {}
    for anahtar, deger in kv.items():
        if ".Config.Direction[" in anahtar and deger:
            kural = anahtar.split(".Config.Direction[")[0]
            kurallar.setdefault(kural, set()).add(deger)
    yonler = set()
    for kural, kume in kurallar.items():
        if kv.get(kural + ".Enable", "true").lower() == "true":
            yonler |= kume
    return sorted(yonler) if yonler else None


def kameraya_sor(rtsp_url: str, http_port: Optional[int] = None, simdi=None) -> dict:
    """Kameraya bağlanıp saat/NTP/yön bilgisini okur. Hata kamera başına sonuca yazılır."""
    from backend.dahua_kayit import _Baglanti
    sonuc = {"ulasildi": False, "saat_farki_sn": None, "ntp_acik": None, "yonler": None, "hata": None}
    try:
        bag = _Baglanti(rtsp_url, http_port)
        r = bag.getir("/cgi-bin/global.cgi?action=getCurrentTime")
        if r.status_code == 401:
            sonuc["hata"] = "Kamera kullanıcı adı/parolası kabul etmedi"
            return sonuc
        r.raise_for_status()
        sonuc["ulasildi"] = True
        deger = _kv(r.text).get("result")
        if deger:
            kamera_saati = datetime.strptime(deger, "%Y-%m-%d %H:%M:%S")
            sonuc["saat_farki_sn"] = round((kamera_saati - (simdi or datetime.now())).total_seconds())
        r = bag.getir("/cgi-bin/configManager.cgi?action=getConfig&name=NTP")
        if r.ok:
            ntp = _kv(r.text).get("table.NTP.Enable")
            if ntp is not None:
                sonuc["ntp_acik"] = ntp.lower() == "true"
        r = bag.getir("/cgi-bin/configManager.cgi?action=getConfig&name=VideoAnalyseRule")
        if r.ok:
            sonuc["yonler"] = yonleri_ayikla(r.text)
    except Exception as exc:  # ağ hatası, zaman aşımı, beklenmeyen yanıt
        sonuc["hata"] = sonuc["hata"] or f"Kameraya ulaşılamadı: {type(exc).__name__}"
    return sonuc


def sorunlari_bul(bilgi: Optional[dict], mutabakat: Optional[dict]) -> list:
    """[{kod, mesaj, oneri}] -- `bilgi` kameraya_sor'un sonucu (Dahua değilse None),
    `mutabakat` dünkü {kamera_gecis, eklenen, hata} (yoksa None)."""
    sorunlar = []
    if bilgi is not None:
        if not bilgi.get("ulasildi"):
            sorunlar.append({"kod": "ulasilamadi", "mesaj": bilgi.get("hata") or "Kameranın web arayüzüne ulaşılamadı",
                             "oneri": "Kameranın ağ bağlantısını ve kullanıcı adı/parolasını kontrol edin."})
        else:
            fark = bilgi.get("saat_farki_sn")
            if fark is not None and abs(fark) > SAAT_ESIK_SN:
                yon = "ileride" if fark > 0 else "geride"
                sorunlar.append({"kod": "saat", "mesaj": f"Kamera saati sunucudan {_sure(abs(fark))} {yon}",
                                 "oneri": "Kamerada NTP'yi açın ya da saati sunucuyla eşitleyin; geçiş saatleri yanlış görünür."})
            if bilgi.get("ntp_acik") is False:
                sorunlar.append({"kod": "ntp", "mesaj": "Saat eşitleme (NTP) kapalı",
                                 "oneri": "Kamerada Ayarlar > Sistem > Tarih/Saat'ten NTP'yi açın (kurumun saat sunucusu)."})
            yonler = bilgi.get("yonler")
            if yonler and not {"Obverse", "Reverse"} <= set(yonler):
                sorunlar.append({"kod": "yon", "mesaj": "Kamera plakayı yalnız tek yönde okuyor (" + ", ".join(yonler) + ")",
                                 "oneri": "ANPR kuralında yönü \"her iki yön\" yapın; karşı yönden gelen araçlar kaçırılıyor olabilir."})
    if mutabakat and not mutabakat.get("hata"):
        gecis, eklenen = mutabakat.get("kamera_gecis") or 0, mutabakat.get("eklenen") or 0
        if gecis >= KACIRMA_EN_AZ_GECIS and eklenen / gecis > KACIRMA_ESIK:
            sorunlar.append({"kod": "kacirma", "mesaj": f"Dün {gecis} geçişin {eklenen} tanesini (%{round(100 * eklenen / gecis)}) "
                                                        "PTS kaçırdı (gece mutabakatıyla eklendi)",
                             "oneri": "Görüntü akışını, okuma alanını (ROI) ve kamera açısını kontrol edin."})
    return sorunlar


def _sure(sn: int) -> str:
    if sn < 120:
        return f"{sn} sn"
    if sn < 7200:
        return f"{round(sn / 60)} dk"
    return f"{round(sn / 3600, 1)} saat"
