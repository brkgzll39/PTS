"""PTS yük testi (2026-11-09): kütüphane yükseltmelerinden ÖNCE çalıştırılacak kapı.

Neden: 2026-11-06'daki web katmanı yükseltmesi (fastapi 0.162, starlette 1.10) testlerin
hepsinden geçti ama sahada iki sorun çıkardı: kapanan sekmelerin canlı akışları
sunucuda "hayalet" olarak kaldı ve veritabanı bağlantı havuzu tükendi; sayfalar ~30
sn'de açıldı. Testler birden çok paneli, canlı görüntüyü ve dolu işlemciyi
taklit etmiyordu. Bu araç ediyor.

Gerçek sisteme dokunmaz: ayrı bir klasörde demo verisiyle ayrı bir PTS açar
(araclar/demo.py), sahte kameralar görüntü üretir. Taklit edilen yük:
  * her panel: 1 canlı bildirim (SSE) + her kamera için 1 canlı görüntü (MJPEG) +
    5 sn'de bir veri yenileme (kayıtlar, istatistik, içeridekiler, alarmlar, ...)
  * paneller ara sıra sayfayı yeniler gibi bağlantılarını ANİDEN keser
  * isteğe bağlı: her sorguya gecikme (SQL Server gibi), işlemciyi dolduran süreçler

Kullanım (proje klasöründen):
    python araclar/yuk_testi.py                        # bu Python ile, 4 panel, 90 sn
    python araclar/yuk_testi.py --python .venv-yeni/bin/python --panel 6 --cpu 4
Çıkış kodu 0 = GEÇTİ, 1 = KALDI. Ölçütler aşağıda (KRITERLER).
"""
import argparse
import json
import multiprocessing
import os
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KRITERLER = {
    "sayfa_p95_ms": 2000,      # veri yenileme isteklerinin %95'i bu sürede
    "hata_orani": 0.01,         # isteklerin en fazla %1'i hata/zaman aşımı
    "havuz_kullanim": 0.8,      # bekçinin gördüğü en yüksek havuz doluluğu
    "hayalet_akis": 0,          # tüm paneller kapandıktan sonra açık kalan akış
}
VERI_YOLLARI = ("/kayitlar?limit=50", "/kayitlar/istatistik", "/araclar/iceridedurum",
                "/alarmlar?sadece_acik=true&limit=8", "/kameralar", "/kisiler?limit=50", "/saglik")


def _bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _iste(taban, yol, token=None, zaman_asimi=60, veri=None):
    basliklar = {"Authorization": f"Bearer {token}"} if token else {}
    if veri is not None:
        basliklar["Content-Type"] = "application/json"
    istek = urllib.request.Request(taban + yol, data=json.dumps(veri).encode() if veri is not None else None,
                                   headers=basliklar)
    with urllib.request.urlopen(istek, timeout=zaman_asimi) as y:
        return y.status, y.read()


def _cpu_yaz(bitis):
    while time.time() < bitis:
        sum(i * i for i in range(10000))


class Panel:
    """Bir tarayıcı sekmesi: SSE + kamera başına MJPEG + düzenli veri yenileme."""

    def __init__(self, no, port, token, kamera_idleri, bitis, yenile_sn, sonuc):
        self.no, self.port, self.token, self.kameralar = no, port, token, kamera_idleri
        self.bitis, self.yenile_sn, self.sonuc = bitis, yenile_sn, sonuc
        self.soketler, self.kilit = [], threading.Lock()

    def _akis_ac(self, yol):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=30)
        s.sendall(f"GET {yol} HTTP/1.1\r\nHost: yuk\r\nAuthorization: Bearer {self.token}\r\n\r\n".encode())
        with self.kilit:
            self.soketler.append(s)

        def oku():
            try:
                while s.recv(65536):
                    with self.kilit:
                        self.sonuc["akis_bayt"] += 1
            except OSError:
                pass
        threading.Thread(target=oku, daemon=True).start()

    def akislari_ac(self):
        self._akis_ac("/olaylar/sse")
        for k in self.kameralar:
            self._akis_ac(f"/kameralar/{k}/akis")

    def akislari_kes(self):
        with self.kilit:
            soketler, self.soketler = self.soketler, []
        for s in soketler:
            try:
                # Tarayıcı sekmesi kapanır/yenilenir gibi: bağlantı ANİDEN kesilir. Yalnız close()
                # yetmez: okuyan iş parçacığı recv()'de beklerken Linux bağlantıyı kapatmaz.
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass

    def calis(self):
        taban = f"http://127.0.0.1:{self.port}"
        self.akislari_ac()
        son_yenileme = time.time()
        while time.time() < self.bitis:
            for yol in VERI_YOLLARI:
                bas = time.perf_counter()
                try:
                    _iste(taban, yol, self.token)
                    tamam = True
                except Exception:
                    tamam = False
                sure = (time.perf_counter() - bas) * 1000
                with self.kilit:
                    self.sonuc["sureler"].setdefault(yol.split("?")[0], []).append(sure)
                    if not tamam:
                        self.sonuc["hata"] += 1
            if self.yenile_sn and time.time() - son_yenileme > self.yenile_sn:   # Ctrl+F5
                self.akislari_kes()
                self.akislari_ac()
                son_yenileme = time.time()
            time.sleep(5)
        self.akislari_kes()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--python", default=sys.executable, help="sunucuyu çalıştıracak Python (denenecek kütüphanelerle)")
    ap.add_argument("--panel", type=int, default=4)
    ap.add_argument("--kamera", type=int, default=4, help="sahte kamera sayısı (demo'daki kamera sayısıyla sınırlı)")
    ap.add_argument("--sure", type=int, default=90, help="saniye")
    ap.add_argument("--yavas-db-ms", type=float, default=20, help="her sorguya eklenen gecikme")
    ap.add_argument("--cpu", type=int, default=0, help="işlemciyi dolduran süreç sayısı")
    ap.add_argument("--yenile-sn", type=int, default=30, help="panellerin sayfayı yenileme aralığı (0 = hiç)")
    ap.add_argument("--klasor", help="demo klasörü (varsayılan: geçici)")
    a = ap.parse_args(argv)

    klasor = a.klasor or tempfile.mkdtemp(prefix="pts-yuk-")
    port = _bos_port()
    surum = subprocess.run([a.python, "-c", "import fastapi, starlette, uvicorn; print(fastapi.__version__, starlette.__version__, uvicorn.__version__)"],
                           capture_output=True, text=True).stdout.split()
    print(f"Kütüphaneler: fastapi {surum[0]}, starlette {surum[1]}, uvicorn {surum[2]}" if len(surum) == 3 else "Kütüphane sürümü okunamadı")
    sunucu = subprocess.Popen([a.python, os.path.join(KOK, "araclar", "demo.py"), "--port", str(port), "--klasor", klasor,
                               "--canli-aralik", "5", "--sahte-kamera", str(a.kamera), "--yavas-db-ms", str(a.yavas_db_ms),
                               "--performans-aralik", "5"],
                              cwd=KOK, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    taban = f"http://127.0.0.1:{port}"
    try:
        for _ in range(240):
            try:
                _iste(taban, "/saglik", zaman_asimi=2)
                break
            except Exception:
                if sunucu.poll() is not None:
                    print("Sunucu açılamadı.")
                    return 1
                time.sleep(1)
        token = json.loads(_iste(taban, "/auth/giris", veri={"kullanici_adi": "demo", "parola": "Demo12345"})[1])["token"]
        kameralar = [k["id"] for k in json.loads(_iste(taban, "/kameralar", token)[1])][:a.kamera]
        time.sleep(6)
        bitis = time.time() + a.sure
        cpu = [multiprocessing.Process(target=_cpu_yaz, args=(bitis,), daemon=True) for _ in range(a.cpu)]
        for c in cpu:
            c.start()
        sonuc = {"sureler": {}, "hata": 0, "akis_bayt": 0}
        paneller = [Panel(i, port, token, kameralar, bitis, a.yenile_sn, sonuc) for i in range(a.panel)]
        print(f"{a.panel} panel x (1 SSE + {len(kameralar)} canlı görüntü), {a.sure} sn, sorgu gecikmesi {a.yavas_db_ms} ms, "
              f"işlemci yükü {a.cpu} süreç, sayfa yenileme {a.yenile_sn or 'yok'} sn ...", flush=True)
        is_parcaciklari = [threading.Thread(target=p.calis) for p in paneller]
        for t in is_parcaciklari:
            t.start()
        for t in is_parcaciklari:
            t.join()
        for c in cpu:
            c.join(timeout=5)
        time.sleep(12)     # kapanan akışların sunucuda temizlenmesine süre (SSE 2 sn'de bir denetler)
        perf = json.loads(_iste(taban, "/performans", token)[1])
    finally:
        sunucu.terminate()
        try:
            sunucu.wait(timeout=10)
        except subprocess.TimeoutExpired:
            sunucu.kill()
        if not a.klasor:
            shutil.rmtree(klasor, ignore_errors=True)

    tum = sorted(x for v in sonuc["sureler"].values() for x in v)
    istek = len(tum)
    p95 = tum[int(0.95 * (istek - 1))] if tum else 0
    hata_orani = sonuc["hata"] / istek if istek else 1
    gecmis = perf.get("gecmis") or []
    havuz = max([g.get("havuz_kullanim") or 0 for g in gecmis] + [0])
    hayalet = (perf.get("son") or {}).get("akis_sayisi", 0)
    print("\nİstek süreleri (ms): ortanca / %95 / en uzun")
    for yol, v in sorted(sonuc["sureler"].items()):
        v.sort()
        print(f"  {yol:24} {statistics.median(v):7.0f} / {v[int(0.95 * (len(v) - 1))]:7.0f} / {v[-1]:7.0f}   ({len(v)} istek)")
    print(f"\nToplam {istek} istek, {sonuc['hata']} hata/zaman aşımı; canlı akışlardan {sonuc['akis_bayt']} veri parçası alındı")
    print(f"Bekçi: en yüksek havuz doluluğu %{round(100 * havuz)}, en kötü veritabanı {max([g.get('veritabani_ms') or 0 for g in gecmis] + [0])} ms, "
          f"en kötü iç gecikme {max([g.get('dongu_ms') or 0 for g in gecmis] + [0])} ms, en yüksek akış {max([g.get('akis_sayisi') or 0 for g in gecmis] + [0])}")
    if perf.get("sorunlar"):
        print("Bekçinin gördüğü sorunlar: " + " · ".join(s["mesaj"] for s in perf["sorunlar"]))
    kontroller = [
        ("Sayfa yanıtı %95", p95 <= KRITERLER["sayfa_p95_ms"], f"{p95:.0f} ms (sınır {KRITERLER['sayfa_p95_ms']})"),
        ("Hata oranı", hata_orani <= KRITERLER["hata_orani"], f"%{100 * hata_orani:.1f} (sınır %{100 * KRITERLER['hata_orani']:.0f})"),
        ("Bağlantı havuzu", havuz <= KRITERLER["havuz_kullanim"], f"en yüksek %{round(100 * havuz)} (sınır %{round(100 * KRITERLER['havuz_kullanim'])})"),
        ("Hayalet akış", hayalet <= KRITERLER["hayalet_akis"], f"paneller kapandıktan sonra açık kalan: {hayalet}"),
    ]
    print()
    for ad, gecti, aciklama in kontroller:
        print(f"  [{'GEÇTİ' if gecti else 'KALDI'}] {ad}: {aciklama}")
    sonuc_ok = all(g for _, g, _ in kontroller)
    print("\nSONUÇ:", "GEÇTİ" if sonuc_ok else "KALDI")
    return 0 if sonuc_ok else 1


if __name__ == "__main__":
    sys.exit(main())
