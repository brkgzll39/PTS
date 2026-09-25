"""Araç görselleri için küçük resim (thumbnail) üretimi ve disk önbelleği.

2026-09-25 (kullanıcı geri bildirimi: "PDF ve Excel indirirken, kayıtlarda
araç arattığımda işlem yavaş ilerliyor ... her an çökecekmiş gibi"):

Kamera kareleri diskte TAM çözünürlükte (tipik 1920x1080, 150-400 KB)
saklanıyor. Buna rağmen:

  * Kayıtlar tablosu, Son Geçişler kartları ve Plaka Analizi penceresi her
    satırın 96x68 px'lik küçük resmi için bu TAM dosyayı indiriyordu -- 50
    satırlık bir sayfa, her yenilemede ~10-20 MB veri demekti (ve tablo,
    her yeni geçişte yeniden çiziliyor).
  * PDF raporu her satır için tam dosyayı açıp TAM çözünürlükte çözüyor,
    sonra 240x160'a küçültüyordu -- ölçümde rapor süresinin ~%75'i buydu.

Bu modül iki şeyi sağlar:

  1) JPEG "draft" modu: libjpeg görseli açarken doğrudan 1/2, 1/4 veya 1/8
     ölçekte çözebilir (hedef boyuttan küçük olmamak kaydıyla). 1920x1080 bir
     kareden 480x320'lik küçük resim üretmek, tam çözüp küçültmekten ~8-10
     kat daha hızlıdır ve sonuç küçük resim için görsel olarak aynıdır.
  2) Disk önbelleği: üretilen küçük resim `<görsel klasörü>/.kucuk/<ad>`
     altına yazılır ve bir sonraki istekte doğrudan oradan servis edilir.
     Orijinal silindiğinde (görüntü saklama süresi, kayıt silme) karşılığı
     olan küçük resim `yetim_kucuk_gorselleri_temizle` ile temizlenir.

Hiçbir fonksiyon istisna fırlatmaz: küçük resim üretilemezse (dosya yok/
bozuk/disk dolu) `None` döner ve çağıran taraf orijinal görsele düşer --
bir performans iyileştirmesi hiçbir zaman bir görselin HİÇ görünmemesine
yol açmamalı.
"""
import io
import logging
import os
import tempfile
import time
from typing import Optional

logger = logging.getLogger("pts.kucuk_gorsel")

KUCUK_KLASOR_ADI = ".kucuk"
# Arayüzdeki en büyük küçük-resim kullanımı (Son Geçişler kartları) için
# yeterli; 1920x1080 bir kareden JPEG draft ile tam 1/4 ölçekte çözülür.
VARSAYILAN_MAKS_BOYUT = (480, 320)
VARSAYILAN_KALITE = 72


def _kucuk_yolu(goruntu_yolu: str) -> str:
    klasor = os.path.join(os.path.dirname(goruntu_yolu), KUCUK_KLASOR_ADI)
    return os.path.join(klasor, os.path.basename(goruntu_yolu))


def _hizli_ac_ve_kucult(goruntu_yolu: str, maks_boyut: tuple):
    """Görseli (JPEG ise draft moduyla) açıp `maks_boyut`a sığacak şekilde
    küçültülmüş bir RGB PIL görseli döner."""
    from PIL import Image as PILImage

    with PILImage.open(goruntu_yolu) as img:
        if img.format == "JPEG":
            # draft(), İSTENEN boyutun her iki kenarından da küçük olmayan en
            # büyük 1/2-1/4-1/8 ölçeği seçer. `maks_boyut` yerine görselin en
            # boy oranına göre SIĞDIRILMIŞ hedef boyutu veriyoruz -- aksi
            # halde 16:9 bir karede (ör. 480x270 -> 240x160 kutusu) yükseklik
            # kısıtı yüzünden hiç küçültme yapılamayıp tam boyut çözülürdü.
            oran = min(maks_boyut[0] / img.width, maks_boyut[1] / img.height, 1.0)
            img.draft("RGB", (max(1, int(img.width * oran)), max(1, int(img.height * oran))))
        img = img.convert("RGB")
        img.thumbnail(maks_boyut)
        return img


def bellekte_kucuk_jpeg(goruntu_yolu: Optional[str], maks_boyut: tuple, kalite: int) -> Optional[io.BytesIO]:
    """Disk önbelleğine dokunmadan, küçültülmüş JPEG'i bellekte döner.
    Önbellekte daha büyük bir küçük resim varsa kaynak olarak onu kullanır
    (çok daha hızlı)."""
    if not goruntu_yolu:
        return None
    kaynak = goruntu_yolu
    onbellek = _kucuk_yolu(goruntu_yolu)
    try:
        if os.path.isfile(onbellek) and os.path.getmtime(onbellek) >= os.path.getmtime(goruntu_yolu):
            kaynak = onbellek
    except OSError:
        pass
    if not os.path.isfile(kaynak):
        return None
    try:
        img = _hizli_ac_ve_kucult(kaynak, maks_boyut)
        akis = io.BytesIO()
        img.save(akis, format="JPEG", quality=kalite)
        akis.seek(0)
        return akis
    except Exception:
        return None


def kucuk_gorsel_yolu(goruntu_yolu: Optional[str], maks_boyut: tuple = VARSAYILAN_MAKS_BOYUT,
                      kalite: int = VARSAYILAN_KALITE) -> Optional[str]:
    """Önbellekteki küçük resmin yolunu döner; yoksa (ya da orijinalden
    eskiyse) üretip atomik olarak yazar. Üretilemezse `None`."""
    if not goruntu_yolu or not os.path.isfile(goruntu_yolu):
        return None
    hedef = _kucuk_yolu(goruntu_yolu)
    try:
        if os.path.isfile(hedef) and os.path.getmtime(hedef) >= os.path.getmtime(goruntu_yolu):
            return hedef
    except OSError:
        pass
    try:
        img = _hizli_ac_ve_kucult(goruntu_yolu, maks_boyut)
        os.makedirs(os.path.dirname(hedef), exist_ok=True)
        # Aynı anda iki istek aynı küçük resmi üretirse biri yarım dosya
        # okumasın diye: geçici dosyaya yaz, sonra atomik olarak taşı.
        fd, gecici = tempfile.mkstemp(dir=os.path.dirname(hedef), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                img.save(f, format="JPEG", quality=kalite)
            os.replace(gecici, hedef)
        except Exception:
            try:
                os.remove(gecici)
            except OSError:
                pass
            raise
        return hedef
    except Exception as exc:
        logger.warning("Küçük resim üretilemedi (%s): %s", os.path.basename(goruntu_yolu), exc)
        return None


def kucuk_gorseli_sil(goruntu_yolu: Optional[str]) -> None:
    if not goruntu_yolu:
        return
    try:
        os.remove(_kucuk_yolu(goruntu_yolu))
    except OSError:
        pass


def yetim_kucuk_gorselleri_temizle(goruntu_klasoru: str) -> int:
    """Orijinali artık bulunmayan küçük resimleri (ve yarım kalmış .tmp
    dosyalarını) siler; silinen dosya sayısını döner."""
    klasor = os.path.join(goruntu_klasoru, KUCUK_KLASOR_ADI)
    if not os.path.isdir(klasor):
        return 0
    silinen = 0
    for ad in os.listdir(klasor):
        yol = os.path.join(klasor, ad)
        if ad.endswith(".tmp"):
            # Başka bir istek o an bu dosyayı yazıyor olabilir -- yalnızca
            # açıkça yarım kalmış (1 dakikadan eski) geçici dosyaları sil.
            try:
                if time.time() - os.path.getmtime(yol) < 60:
                    continue
            except OSError:
                continue
        if ad.endswith(".tmp") or not os.path.isfile(os.path.join(goruntu_klasoru, ad)):
            try:
                os.remove(yol)
                silinen += 1
            except OSError:
                pass
    return silinen
