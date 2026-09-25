"""Geçiş kayıtlarını, kaydın gerçekleştiği anda AÇIK olan vardiya
oturumlarıyla eşleştiren saf (veritabanından/fastapi'den bağımsız) algoritma.

2026-09-25 (kullanıcı: "PDF ve Excel indirirken, kayıtlarda araç
arattığımda ... her an çökecekmiş gibi yavaş"): `main.py`'deki
`_kayitlarin_vardiya_adlarini_ekle` ve `_vardiya_etiketleri_haritasi`
eskiden HER kaydı TÜM vardiya oturumlarıyla (sistemin kurulduğu günden beri
açılmış her oturum) tek tek karşılaştırıyordu: kayıt sayısı x oturum sayısı.
Bir Excel raporunda (5000 kayıt) bu iki fonksiyon birlikte, birkaç yüz
oturumla bile milyonlarca karşılaştırma demekti ve oturum tablosu her
vardiya girişiyle büyüdüğü için sistem ZAMANLA yavaşlıyordu. Ayrıca tek bir
kaydın detayını açmak (olay detayı, kayıt düzenleme) bile tüm oturum
tablosunu belleğe yüklüyordu.

Bu modül iki şeyle çözer (main.py tarafı ayrıca yalnızca kayıtların zaman
aralığıyla ÇAKIŞAN oturumları veritabanından çeker):

  * Süpürme (sweep) algoritması: kayıtlar ve oturumlar zamana göre sıralanır;
    kayıtlar sırayla gezilirken yalnızca o an "açık" olan oturumlar küçük bir
    listede tutulur. Karmaşıklık ~ O((K + O) log(K + O) + K x eşzamanlı açık
    oturum sayısı) -- eşzamanlı açık oturum sayısı pratikte birkaç taneyle
    sınırlıdır.
  * Anlam `_pencere_icinde_mi` ile BİREBİR aynı: giriş <= zaman VE (çıkış
    YOK ya da zaman < çıkış). Sonuç listelerindeki sıra, oturumların
    verildiği sıradır (eski kodun "görülme sırası" davranışı korunur).
"""
from datetime import datetime
from typing import Any, Dict, Hashable, List, Optional, Sequence, Tuple

Oturum = Tuple[datetime, Optional[datetime], Any]


def kayitlari_oturumlarla_eslestir(
    kayitlar: Sequence[Tuple[Hashable, datetime]],
    oturumlar: Sequence[Oturum],
) -> Dict[Hashable, List[Any]]:
    """`kayitlar`: (anahtar, zaman) çiftleri. `oturumlar`: (giriş, çıkış veya
    None, veri) üçlüleri. Her kayıt anahtarı için, o an açık olan oturumların
    `veri`lerini (oturumların `oturumlar` içindeki sırasıyla) döner. Hiçbir
    oturumla eşleşmeyen kayıt için boş liste döner."""
    sonuc: Dict[Hashable, List[Any]] = {anahtar: [] for anahtar, _ in kayitlar}
    if not kayitlar or not oturumlar:
        return sonuc

    # (giriş, orijinal sıra, çıkış, veri)
    sirali_oturumlar = sorted(
        ((giris, sira, cikis, veri) for sira, (giris, cikis, veri) in enumerate(oturumlar) if giris is not None),
        key=lambda o: (o[0], o[1]),
    )
    sirali_kayitlar = sorted(kayitlar, key=lambda k: k[1])

    acik: list = []  # (sira, cikis, veri)
    i = 0
    n = len(sirali_oturumlar)
    for anahtar, zaman in sirali_kayitlar:
        if zaman is None:
            continue
        while i < n and sirali_oturumlar[i][0] <= zaman:
            _, sira, cikis, veri = sirali_oturumlar[i]
            acik.append((sira, cikis, veri))
            i += 1
        # Kayıtlar artan zamanda gezildiği için, bu zamanda kapanmış bir
        # oturum sonraki kayıtlar için de kapalıdır -- kalıcı olarak çıkar.
        acik = [o for o in acik if o[1] is None or zaman < o[1]]
        if acik:
            sonuc[anahtar] = [veri for _, _, veri in sorted(acik, key=lambda o: o[0])]
    return sonuc
