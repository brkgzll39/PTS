"""Performans bekçisi (2026-11-09, kullanıcı isteği).

AYNI GÜN SAHADA: sayfalar ~30 sn'de açılıyor, kameraların kayıt gönderimleri zaman
aşımına uğruyordu; güvenlik personeli şikâyet edene kadar kimse fark etmemişti.
İki sebep vardı (bkz. main.py _GuvenlikBasliklari notu ve web katmanı geri dönüşü):
günlerce biriken "hayalet" canlı akışlar ve tükenen veritabanı bağlantı havuzu.
Bu modül PTS'in kendini dakikada bir ölçmesini sağlar; sorun sistemi kullanılamaz
hale getirmeden alarm verilir.

Ölçülenler (her örnek bir dakikayı özetler):
  veritabani_ms    havuzdan bağlantı alıp "SELECT 1" çalıştırma süresi
  havuz_kullanim   ödünç verilmiş bağlantı / havuz kapasitesi (0..1)
  dongu_ms         sunucunun iç (asyncio) gecikmesi: boş bir işin sırası ne zaman geldi
  istek_p95_ms     son dakikadaki isteklerin %95'i bu sürede yanıtlandı (akışlar hariç)
  akis_sayisi      açık canlı görüntü (MJPEG) + bildirim (SSE) akışı
  kayit_hatasi     kameranın PTS'e kayıt gönderemediği durum sayısı
  islemci_sistem   bilgisayarın toplam işlemci yükü (%)
  islemci_pts      PTS sürecinin işlemci payı (%)
  bellek_mb        PTS sürecinin bellek kullanımı

Bu modül saf hesaplama ve sayaçlardan ibarettir (fastapi/sqlalchemy'den bağımsız);
ölçüm döngüsü ve alarm main.py'dedir.
"""
import os
import sys
import threading
import time
from collections import deque
from typing import Optional

# Varsayılan eşikler: (sınır, kaç dakika ÜST ÜSTE aşılırsa sorun). Sahada normal
# değerler (2026-11-09 öğleden sonra): veritabanı ~40 ms, istek p95 < 200 ms,
# havuz birkaç bağlantı, işlemci %54, bellek ~540 MB.
ESIKLER = {
    "veritabani_ms": (2000, 3),
    "havuz_kullanim": (0.8, 3),
    "dongu_ms": (1000, 3),
    "istek_p95_ms": (3000, 3),
    "akis_sayisi": (80, 10),       # sahada normali 15-30 (3-6 panel x 5 akış)
    "islemci_sistem": (95, 10),
    "bellek_mb": (2500, 5),
}
KAYIT_HATASI_ESIK = (3, 5)      # son 5 dakikada en az 3 gönderim hatası
TEKRAR_BILDIRIM_SN = 3600       # aynı sorun için en fazla saatte bir bildirim


# ------------------------------------------------------------------ sayaçlar
class Sayaclar:
    """İstek süreleri ve açık akışlar. Her istek/akış için çağrılır; ucuz olmalı."""

    def __init__(self):
        self._kilit = threading.Lock()
        self._sureler = []
        self._akislar = {"mjpeg": 0, "sse": 0}
        self._kayit_hatasi = 0

    def istek_bitti(self, sure_sn: float) -> None:
        with self._kilit:
            if len(self._sureler) < 50000:
                self._sureler.append(sure_sn)

    def akis_acildi(self, tur: str) -> None:
        with self._kilit:
            self._akislar[tur] = self._akislar.get(tur, 0) + 1

    def akis_kapandi(self, tur: str) -> None:
        with self._kilit:
            self._akislar[tur] = max(0, self._akislar.get(tur, 0) - 1)

    def kayit_gonderim_hatasi(self) -> None:
        with self._kilit:
            self._kayit_hatasi += 1

    def akislar(self) -> dict:
        with self._kilit:
            return dict(self._akislar)

    def bosalt(self) -> dict:
        """Son ölçümden beri biriken istek süreleri ve kayıt hataları (sıfırlanır)."""
        with self._kilit:
            sureler, self._sureler = self._sureler, []
            hata, self._kayit_hatasi = self._kayit_hatasi, 0
            akislar = dict(self._akislar)
        sureler.sort()
        return {
            "istek_sayisi": len(sureler),
            "istek_p95_ms": round(1000 * sureler[int(0.95 * (len(sureler) - 1))]) if sureler else 0,
            "istek_en_uzun_ms": round(1000 * sureler[-1]) if sureler else 0,
            "akis_sayisi": sum(akislar.values()),
            "akislar": akislar,
            "kayit_hatasi": hata,
        }


SAYACLAR = Sayaclar()


# ------------------------------------------------------------------ işlemci / bellek
def _sistem_islemci_zamanlari() -> Optional[tuple]:
    """(boşta, toplam) işlemci zamanı; desteklenmiyorsa None."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            bos, cekirdek, kullanici = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
            if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(bos), ctypes.byref(cekirdek), ctypes.byref(kullanici)):
                return None
            deger = lambda f: (f.dwHighDateTime << 32) | f.dwLowDateTime  # noqa: E731
            # Windows'ta çekirdek zamanı boşta zamanı da içerir.
            return deger(bos), deger(cekirdek) + deger(kullanici)
        except Exception:
            return None
    try:
        with open("/proc/stat") as f:
            alanlar = [int(x) for x in f.readline().split()[1:]]
        return alanlar[3] + (alanlar[4] if len(alanlar) > 4 else 0), sum(alanlar)
    except (OSError, ValueError, IndexError):
        return None


def bellek_mb() -> Optional[int]:
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class SAYAC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            s = SAYAC()
            s.cb = ctypes.sizeof(SAYAC)
            surec = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(surec, ctypes.byref(s), s.cb):
                return round(s.WorkingSetSize / 1048576)
        except Exception:
            return None
        return None
    try:
        with open("/proc/self/status") as f:
            for satir in f:
                if satir.startswith("VmRSS:"):
                    return round(int(satir.split()[1]) / 1024)
    except (OSError, ValueError):
        return None
    return None


class IslemciOlcer:
    """İki çağrı arasındaki işlemci yükü: (sistem %, PTS süreci %)."""

    def __init__(self):
        self._onceki = (time.monotonic(), time.process_time(), _sistem_islemci_zamanlari())

    def olc(self) -> tuple:
        simdi = (time.monotonic(), time.process_time(), _sistem_islemci_zamanlari())
        (d0, p0, s0), (d1, p1, s1) = self._onceki, simdi
        self._onceki = simdi
        duvar = max(d1 - d0, 1e-6)
        pts = round(100 * (p1 - p0) / duvar / (os.cpu_count() or 1), 1)
        sistem = None
        if s0 and s1 and s1[1] > s0[1]:
            sistem = round(100 * (1 - (s1[0] - s0[0]) / (s1[1] - s0[1])), 1)
        return sistem, max(0.0, pts)


# ------------------------------------------------------------------ değerlendirme
def _sure(ms: float) -> str:
    return f"{ms / 1000:.1f} sn".replace(".", ",") if ms >= 1000 else f"{round(ms)} ms"


def _mesaj(kod: str, deger, ornek: dict) -> str:
    if kod == "veritabani_ms":
        return f"Veritabanı yavaş yanıt veriyor: {_sure(deger)} (normali 0,1 sn'nin altı)"
    if kod == "havuz_kullanim":
        return (f"Veritabanı bağlantı havuzu %{round(100 * deger)} dolu "
                f"({ornek.get('havuz_dolu')}/{ornek.get('havuz_kapasite')}); sayfalar yavaşlayabilir")
    if kod == "dongu_ms":
        return f"Sunucu meşgul: iç gecikme {_sure(deger)}"
    if kod == "istek_p95_ms":
        return f"Sayfalar yavaş: isteklerin %95'i {_sure(deger)} içinde yanıtlanıyor"
    if kod == "akis_sayisi":
        return f"Açık canlı akış sayısı {deger}: kapanmayan bağlantılar birikiyor olabilir"
    if kod == "islemci_sistem":
        return f"İşlemci uzun süredir %{round(deger)} dolu"
    if kod == "bellek_mb":
        return f"PTS {deger} MB bellek kullanıyor"
    if kod == "kayit_hatasi":
        return f"Kameralar PTS'e kayıt gönderemiyor: son 5 dakikada {deger} kez (geçişler kaçabilir)"
    return f"{kod}: {deger}"


def degerlendir(ornekler: list, esikler: Optional[dict] = None, kayit_esigi: tuple = KAYIT_HATASI_ESIK) -> list:
    """Son örneklere göre süren sorunlar: [{kod, mesaj, deger}]. Bir eşik `n` dakika
    ÜST ÜSTE aşılmadıkça sorun sayılmaz (tek bir yavaş dakika alarm üretmesin)."""
    esikler = esikler or ESIKLER
    sorunlar = []
    for kod, (sinir, n) in esikler.items():
        son = [o.get(kod) for o in ornekler[-n:]]
        if len(son) == n and all(d is not None and d > sinir for d in son):
            sorunlar.append({"kod": kod, "deger": son[-1], "mesaj": _mesaj(kod, son[-1], ornekler[-1])})
    esik, pencere = kayit_esigi
    toplam = sum(o.get("kayit_hatasi") or 0 for o in ornekler[-pencere:])
    if toplam >= esik:
        sorunlar.append({"kod": "kayit_hatasi", "deger": toplam, "mesaj": _mesaj("kayit_hatasi", toplam, ornekler[-1])})
    return sorunlar


class Bekci:
    """Örnek geçmişi (24 saat) ve bildirim kararları (hangi sorun yeni, hangisi düzeldi)."""

    def __init__(self, esikler: Optional[dict] = None, saat=time.time):
        self.ornekler: deque = deque(maxlen=1440)
        self.esikler = esikler or ESIKLER
        self.aktif: dict = {}            # kod -> sorun
        self._son_bildirim: dict = {}    # kod -> zaman
        self._saat = saat

    def ekle(self, ornek: dict) -> tuple:
        """Örneği ekler; (yeni_sorunlar, duzelenler, sorunlar) döner. `yeni_sorunlar`
        bildirilecek olanlardır (aynı sorun saatte bir defadan sık bildirilmez)."""
        self.ornekler.append(ornek)
        sorunlar = degerlendir(list(self.ornekler), self.esikler)
        simdi = self._saat()
        kodlar = {s["kod"] for s in sorunlar}
        yeni = [s for s in sorunlar if s["kod"] not in self.aktif
                and (s["kod"] not in self._son_bildirim or simdi - self._son_bildirim[s["kod"]] >= TEKRAR_BILDIRIM_SN)]
        for s in yeni:
            self._son_bildirim[s["kod"]] = simdi
        duzelen = [s for k, s in self.aktif.items() if k not in kodlar]
        self.aktif = {s["kod"]: s for s in sorunlar}
        return yeni, duzelen, sorunlar

    def ozet(self, adim: int = 5) -> list:
        """Grafik için: `adim` dakikalık gruplarda en kötü değerler."""
        liste = list(self.ornekler)
        sonuc = []
        for i in range(0, len(liste), adim):
            grup = liste[i:i + adim]
            sonuc.append({"zaman": grup[-1]["zaman"],
                          **{k: max((o.get(k) or 0) for o in grup) for k in
                             ("veritabani_ms", "istek_p95_ms", "dongu_ms", "havuz_kullanim", "akis_sayisi",
                              "islemci_sistem", "bellek_mb", "kayit_hatasi")}})
        return sonuc
