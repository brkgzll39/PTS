"""Kamera başına plaka okuma kalitesi değerlendirmesi (saf fonksiyonlar --
fastapi/sqlalchemy'den bağımsız, bu yüzden gerçekten test edilebilir).

2026-09-25 (kullanıcı: "kameranın en doğru ve hatasız kayıt alması için ...
yazılım tarafında ekleyebileceklerini deneyelim"): hangi kameranın zayıf
okuma yaptığını görmenin tek yolu Kayıtlar ekranındaki "Doğrulama" sütununa
tek tek bakmaktı. Bu modül, `main.py::/kameralar/okuma-kalitesi` ucunun
veritabanından topladığı sayıları anlaşılır bir değerlendirmeye ve somut
önerilere çevirir.

Ölçütler (hepsi yalnızca OTOMATİK -- kamera kaynaklı -- kayıtlar üzerinden):

* Tek kare oranı: plaka yalnızca 1 karede okunup kaydedildiyse, oylamayla
  doğrulanacak başka okuma yoktur -- yanlış okuma riski en yüksek kayıtlar
  bunlardır. Yüksek oran genelde plakanın karede çok kısa/küçük/bulanık
  göründüğü anlamına gelir (açı, zoom, enstantane, işlemci yükü).
* Kararsız okuma oranı: aynı geçişte FARKLI metinler okunmuşsa (ör. "34 ABC
  123" ve "34 A8C 123"), OCR plakayı net göremiyor demektir.
* Bilinen plakaya göre düzeltme oranı: sistemin tek karakter hatalarını
  kayıtlı plakalara bakarak düzelttiği kayıtlar. Düzeltme doğru sonuç verse
  bile yüksek oran, ham okumanın zayıf olduğuna işaret eder.
"""
from typing import Optional

# Değerlendirme için gereken en az kayıt sayısı -- daha azıyla oranlar
# rastlantıya çok açık.
EN_AZ_KAYIT = 10

TEK_KARE_DIKKAT = 0.10
TEK_KARE_ZAYIF = 0.25
KARARSIZ_DIKKAT = 0.15
KARARSIZ_ZAYIF = 0.30
DUZELTME_DIKKAT = 0.10
DUZELTME_ZAYIF = 0.25

_SIRA = {"iyi": 0, "dikkat": 1, "zayif": 2}


def _oran(pay: int, payda: int) -> Optional[float]:
    return round(pay / payda, 3) if payda else None


def kalite_degerlendir(toplam: int, dogrulama_bilinen: int, tek_kare: int, kararsiz: int,
                       ocr_duzeltme: int, ortalama_kare: Optional[float],
                       ortalama_guven: Optional[float]) -> dict:
    """Bir kameranın ham sayılarından oranları, genel durumu ("iyi" /
    "dikkat" / "zayif" / "yetersiz_veri" / "kayit_yok") ve Türkçe önerileri
    üretir."""
    sonuc = {
        "toplam": toplam,
        "tek_kare_orani": _oran(tek_kare, dogrulama_bilinen),
        "kararsiz_okuma_orani": _oran(kararsiz, dogrulama_bilinen),
        "ocr_duzeltme_orani": _oran(ocr_duzeltme, toplam),
        "ortalama_kare": round(ortalama_kare, 1) if ortalama_kare is not None else None,
        "ortalama_guven": round(ortalama_guven, 3) if ortalama_guven is not None else None,
        "durum": "iyi",
        "oneriler": [],
    }
    if toplam == 0:
        sonuc["durum"] = "kayit_yok"
        sonuc["oneriler"].append(
            "Bu dönemde bu kameradan hiç otomatik kayıt gelmedi. Kamera bağlı ve bu yönde trafik varsa "
            "görüntüyü, tespit alanını (ROI) ve kameranın plakayı görüp görmediğini kontrol edin."
        )
        return sonuc
    if toplam < EN_AZ_KAYIT or dogrulama_bilinen < EN_AZ_KAYIT:
        sonuc["durum"] = "yetersiz_veri"
        sonuc["oneriler"].append(
            f"Değerlendirme için en az {EN_AZ_KAYIT} otomatik kayıt gerekiyor; daha uzun bir dönem seçin."
        )
        return sonuc

    durum = "iyi"

    def yukselt(yeni: str) -> None:
        nonlocal durum
        if _SIRA[yeni] > _SIRA[durum]:
            durum = yeni

    tk = sonuc["tek_kare_orani"] or 0.0
    if tk >= TEK_KARE_DIKKAT:
        yukselt("zayif" if tk >= TEK_KARE_ZAYIF else "dikkat")
        sonuc["oneriler"].append(
            f"Kayıtların %{tk * 100:.0f}'i yalnızca TEK karede okunmuş. Plaka karede çok kısa ya da çok küçük "
            "görünüyor olabilir: kamerayı aracın yavaşladığı noktaya çevirin, zoom ile plakanın en az "
            "130-150 piksel genişlikte görünmesini sağlayın, enstantaneyi 1/500 sn veya daha hızlı yapın. "
            "Birden çok kamera varsa işlemcinin sürekli dolu olmadığını Sistem Sağlığı'ndan kontrol edin."
        )
    ko = sonuc["kararsiz_okuma_orani"] or 0.0
    if ko >= KARARSIZ_DIKKAT:
        yukselt("zayif" if ko >= KARARSIZ_ZAYIF else "dikkat")
        sonuc["oneriler"].append(
            f"Geçişlerin %{ko * 100:.0f}'inde aynı plaka farklı karelerde FARKLI okunmuş. Görüntü net değil: "
            "odak, gece IR parlaması (yansıtıcı plaka beyaz 'patlıyor' olabilir), sıkıştırma kalitesi "
            "(ana yayın, H.264, en az 4 Mbps) kontrol edilmeli."
        )
    du = sonuc["ocr_duzeltme_orani"] or 0.0
    if du >= DUZELTME_DIKKAT:
        yukselt("zayif" if du >= DUZELTME_ZAYIF else "dikkat")
        sonuc["oneriler"].append(
            f"Kayıtların %{du * 100:.0f}'i ancak kayıtlı plakalara bakılarak düzeltilebilmiş. Ham okuma "
            "zayıf; Sistem > Toplu Doğruluk Testi ile daha büyük bir OCR modelini bu kameranın "
            "fotoğraflarıyla deneyin."
        )
    sonuc["durum"] = durum
    return sonuc
