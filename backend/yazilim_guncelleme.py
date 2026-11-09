"""Yazılım (Python kütüphanesi) güncellemeleri: tarama, plan, uygulama, geri alma.

2026-11-06 kullanıcı isteği: "güncellemem gereken kütüphaneler olduğunda bilgi
verecek bir ekran ... haftalık ya da aylık arka planda tarama ... güncellemeleri
gerçekleştir butonu".

AYNI GÜN SAHADA YAŞANANLAR bu modülün kurallarını belirledi:
  * fastapi 0.115 -> 0.162 yükseltmesi uzun akışların veritabanı bağlantısını
    tutmasına yol açtı; panel dakikalarca açılmadı.
  * Kurulum listesi onnxruntime CPU paketini onnxruntime-directml'in üzerine
    yazdı; plaka motoru sessizce ekran kartından işlemciye düştü.
Bu yüzden:
  1. Yalnız BİLİNEN GÜVENLİK AÇIĞI olan paketler yükseltilir, "en yeni"ye değil
     açığı kapatan EN DÜŞÜK sürüme (en az değişiklik).
  2. Plaka motoru paketleri (TUTULAN) hiçbir zaman otomatik yükseltilmez.
  3. Uygulamadan önce kurulu sürümlerin yedeği alınır; geri alma yalnız
     değişen paketleri eski sürümüne döndürür.
  4. Ekran kartı motoru (onnxruntime-directml) kuruluysa her işlemden sonra
     DirectML'in hâlâ çalıştığı doğrulanır, bozulduysa onarılır.
Servisi yeniden başlatma ve sonrasında izleme kutuphane_guncelle.ps1'dedir.

Komut satırı (kutuphane_guncelle.ps1 çağırır; proje klasöründen):
    python -m backend.yazilim_guncelleme uygula     -> plan dosyasını uygular
    python -m backend.yazilim_guncelleme geri-al    -> son yedeğe döner
    python -m backend.yazilim_guncelleme dogrula    -> uygulama içe aktarılabiliyor mu
"""
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable, Optional

from packaging.version import InvalidVersion, Version

PYPI = "https://pypi.org/pypi"
# Plaka motoru zinciri: sürümü okuma kalitesini doğrudan etkiler ve ekran kartı
# paketleriyle çakışır; otomatik yükseltilmez, ekranda "elle" diye gösterilir.
_PLAKA_MOTORU = "Plaka motoru: okuma kalitesini etkiler, otomatik güncellenmez"
_WEB_KATMANI = ("Web katmanı: 2026-11 sahada yeni sürümler sayfaların açılmamasına yol açtı; "
                "test edilmiş bir yazılım güncellemesiyle (yama) yükseltilecek")
# Otomatik yükseltilmeyen paketler ve nedeni (ekranda gösterilir).
TUTULAN_NEDEN = {
    **{ad: _PLAKA_MOTORU for ad in ("onnxruntime", "onnxruntime-directml", "onnxruntime-gpu", "opencv-python",
                                    "opencv-python-headless", "numpy", "fast-alpr", "fast-plate-ocr", "open-image-models")},
    # 2026-11-09: fastapi 0.118+ veritabanı bağlantısını yanıt tamamen gönderilene kadar
    # tutuyor; yoğun sunucuda havuz tükendi (bkz. main.py _GuvenlikBasliklari notu).
    **{ad: _WEB_KATMANI for ad in ("fastapi", "starlette", "uvicorn")},
}
TUTULAN = tuple(TUTULAN_NEDEN)
# PTS çalışırken HİÇ kullanılmayan kurulum araçları: yalnız bunlar güncellenecekse PTS
# yeniden başlatılmaz. pip ayrıca planın BAŞINA alınır -- diğer paketleri o kurar.
# (setuptools bu listede DEĞİL: bazı kütüphaneler çalışırken pkg_resources'ını kullanır.)
YENIDEN_BASLATMASIZ = ("pip", "wheel")
_AD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_SURUM = re.compile(r"^[0-9][0-9A-Za-z.+!-]{0,40}$")


def _klasor() -> str:
    if os.getenv("PTS_GUNCELLEME_KLASORU"):
        return os.environ["PTS_GUNCELLEME_KLASORU"]
    from backend.database import DB_KLASORU
    return os.path.join(DB_KLASORU, "yazilim_guncelleme")


def yol(ad: str) -> str:
    """tarama.json | plan.json | durum.json | yedekler/"""
    os.makedirs(os.path.join(_klasor(), "yedekler"), exist_ok=True)
    return os.path.join(_klasor(), ad)


def normalize(ad: str) -> str:
    return re.sub(r"[-_.]+", "-", ad).lower()


def json_oku(ad: str, varsayilan=None):
    try:
        with open(yol(ad), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return varsayilan


def json_yaz(ad: str, veri) -> None:
    hedef = yol(ad)
    with open(hedef + ".tmp", "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=2)
    os.replace(hedef + ".tmp", hedef)


# ------------------------------------------------------------------ tarama
def kurulu_paketler() -> dict:
    """{normalize_ad: (görünen_ad, sürüm)} -- bu Python ortamında kurulu olanlar."""
    from importlib import metadata
    sonuc = {}
    for d in metadata.distributions():
        ad = d.metadata["Name"]
        if ad and d.version:
            sonuc[normalize(ad)] = (ad, d.version)
    return sonuc


def _v(s: str) -> Optional[Version]:
    try:
        return Version(s)
    except (InvalidVersion, TypeError):
        return None


def onerilen_surum(kurulu: str, aciklar: list) -> Optional[str]:
    """Tüm açıkları kapatan EN DÜŞÜK sürüm; düzeltmesi olmayan açık varsa None."""
    simdiki, gerekli = _v(kurulu), []
    for a in aciklar:
        adaylar = sorted(v for v in (_v(x) for x in a.get("duzelten") or []) if v and (simdiki is None or v > simdiki))
        if not adaylar:
            return None
        gerekli.append(adaylar[0])
    return str(max(gerekli)) if gerekli else None


def _aciklari_tekillestir(ham: list) -> list:
    """Aynı açık GHSA/PYSEC/CVE kimlikleriyle birden çok kez gelebilir."""
    gruplar = []
    for a in ham:
        kimlikler = {a.get("id")} | set(a.get("aliases") or [])
        kimlikler.discard(None)
        grup = next((g for g in gruplar if g["kimlikler"] & kimlikler), None)
        if grup:
            grup["kimlikler"] |= kimlikler
            grup["duzelten"] |= set(a.get("fixed_in") or [])
            grup["ozet"] = grup["ozet"] or (a.get("summary") or "")
        else:
            gruplar.append({"kimlikler": kimlikler, "duzelten": set(a.get("fixed_in") or []),
                            "ozet": a.get("summary") or "", "link": a.get("link")})
    sonuc = []
    for g in gruplar:
        cve = sorted(k for k in g["kimlikler"] if k.startswith("CVE-"))
        sonuc.append({"id": (cve or sorted(g["kimlikler"]))[0], "ozet": g["ozet"][:200],
                      "duzelten": sorted(g["duzelten"], key=lambda s: _v(s) or Version("0")), "link": g["link"]})
    return sonuc


def _pypi_getir(url: str):
    import requests
    r = requests.get(url, timeout=15, headers={"User-Agent": "PTS-guncelleme-denetimi"})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def tara(paketler: Optional[dict] = None, getir: Callable = _pypi_getir, es_zamanli: int = 8) -> dict:
    """Kurulu her paket için PyPI'den: bu sürümün bilinen açıkları ve en yeni sürüm."""
    paketler = paketler if paketler is not None else kurulu_paketler()

    def bir(anahtar):
        ad, surum = paketler[anahtar]
        try:
            bu = getir(f"{PYPI}/{ad}/{surum}/json")
            genel = getir(f"{PYPI}/{ad}/json")
        except Exception as exc:
            return {"ad": ad, "surum": surum, "hata": f"{type(exc).__name__}"}
        if bu is None and genel is None:
            return None          # PyPI'de olmayan (yerel) paket
        aciklar = _aciklari_tekillestir((bu or {}).get("vulnerabilities") or [])
        en_yeni = ((genel or {}).get("info") or {}).get("version")
        tutulan = anahtar in TUTULAN
        tutulma_nedeni = TUTULAN_NEDEN.get(anahtar)
        onerilen = onerilen_surum(surum, aciklar) if aciklar else None
        return {"ad": ad, "surum": surum, "en_yeni": en_yeni, "aciklar": aciklar, "onerilen": onerilen,
                "tutulan": tutulan, "tutulma_nedeni": tutulma_nedeni, "yeniden_baslatma": anahtar not in YENIDEN_BASLATMASIZ,
                "guncel_degil": bool(en_yeni and _v(en_yeni) and _v(surum) and _v(en_yeni) > _v(surum))}

    with ThreadPoolExecutor(max_workers=es_zamanli) as havuz:
        sonuclar = [s for s in havuz.map(bir, sorted(paketler)) if s]
    sonuclar.sort(key=lambda p: (not p.get("aciklar"), not p.get("guncel_degil"), p["ad"].lower()))
    return {
        "zaman": datetime.now().isoformat(timespec="seconds"),
        "paketler": sonuclar,
        "acik_paket": sum(1 for p in sonuclar if p.get("aciklar")),
        "tutulan_acik_paket": sum(1 for p in sonuclar if p.get("aciklar") and p.get("tutulan")),
        "acik_sayisi": sum(len(p.get("aciklar") or []) for p in sonuclar),
        "hata": sum(1 for p in sonuclar if p.get("hata")),
    }


def plan_olustur(tarama: dict) -> list:
    """Otomatik uygulanacaklar: açığı olan, tutulmayan ve düzeltmesi olan paketler (pip önce)."""
    plan = []
    for p in (tarama or {}).get("paketler", []):
        if p.get("aciklar") and p.get("onerilen") and not p.get("tutulan"):
            if _AD.match(p["ad"]) and _SURUM.match(p["onerilen"]):
                plan.append({"ad": p["ad"], "eski": p["surum"], "yeni": p["onerilen"],
                             "yeniden_baslatma": normalize(p["ad"]) not in YENIDEN_BASLATMASIZ})
    plan.sort(key=lambda x: normalize(x["ad"]) != "pip")
    return plan


def yeniden_baslatma_gerekir(plan: list) -> bool:
    return any(normalize(p["ad"]) not in YENIDEN_BASLATMASIZ for p in plan)


# ------------------------------------------------------------------ uygulama
def _pip(argumanlar: list, calistir: Callable = subprocess.run) -> tuple:
    r = calistir([sys.executable, "-m", "pip", "--disable-pip-version-check", *argumanlar],
                 capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode == 0, (r.stdout or "")[-2000:] + (r.stderr or "")[-2000:]


def uyumsuzluklar(calistir: Callable = subprocess.run) -> set:
    """`pip check` satırları: "fastapi 0.115.0 has requirement starlette<0.39 ..." gibi.
    pip, kurulumda bir bağımlılığın sürüm şartını çiğnese de yalnız UYARI verip kurar;
    bu yüzden güncellemeden önce ve sonra karşılaştırılır."""
    _, cikti = _pip(["check"], calistir)
    return {s.strip() for s in cikti.splitlines() if " requires " in s or " has requirement " in s}


def dml_kontrol_ve_onar(onceki: dict, calistir: Callable = subprocess.run) -> Optional[str]:
    """onnxruntime-directml önceden kuruluysa DirectML hâlâ çalışıyor mu; değilse onar.
    Ayrı süreçte denetler (bu süreç eski onnxruntime'ı bellekte tutuyor olabilir)."""
    dml = onceki.get("onnxruntime-directml")
    if not dml:
        return None
    kod = "import onnxruntime as o; import sys; sys.exit(0 if 'DmlExecutionProvider' in o.get_available_providers() else 3)"
    if calistir([sys.executable, "-c", kod], capture_output=True).returncode == 0:
        return None
    _pip(["uninstall", "-y", "onnxruntime", "onnxruntime-directml"], calistir)
    ok, cikti = _pip(["install", f"onnxruntime-directml=={dml[1]}"], calistir)
    return f"Ekran kartı motoru onarıldı (onnxruntime-directml {dml[1]})" if ok else f"Ekran kartı motoru ONARILAMADI: {cikti[-300:]}"


def dogrula(calistir: Callable = subprocess.run) -> tuple:
    """Uygulama yeni kütüphanelerle içe aktarılabiliyor mu (ayrı süreçte)."""
    r = calistir([sys.executable, "-c", "import backend.main"], capture_output=True, text=True,
                 encoding="utf-8", errors="replace")
    return r.returncode == 0, (r.stderr or "")[-800:]


def _durum_yaz(**alanlar) -> None:
    durum = json_oku("durum.json", {}) or {}
    durum.update(alanlar)
    json_yaz("durum.json", durum)


def uygula(calistir: Callable = subprocess.run, paketler: Optional[Callable] = None) -> dict:
    """plan.json'daki paketleri yükseltir. Başarısızlıkta kendisi geri alır."""
    paketler = paketler or kurulu_paketler
    plan = json_oku("plan.json", []) or []
    adimlar = []
    zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
    _durum_yaz(islem="uygula", baslangic=datetime.now().isoformat(timespec="seconds"), bitis=None,
               basarili=None, adimlar=adimlar, plan=plan, izleme=None, izleme_bitti=False, mesaj=None)
    if not plan:
        _durum_yaz(bitis=datetime.now().isoformat(timespec="seconds"), basarili=True, mesaj="Uygulanacak güncelleme yok")
        return json_oku("durum.json")
    onceki = paketler()
    yedek_adi = f"yedekler/{zaman}.json"
    json_yaz(yedek_adi, {k: list(v) for k, v in onceki.items()})
    adimlar.append(f"Kurulu {len(onceki)} paketin sürümleri yedeklendi ({zaman})")
    # Her paket AYRI denenir: biri kurulamaz ya da başka bir paketle uyumsuz hale
    # gelirse yalnız o geri alınır ve atlanır, diğerleri uygulanır.
    uygulanan, atlanan = [], []
    for p in plan:
        if not (_AD.match(p["ad"]) and _SURUM.match(p["yeni"])):
            continue
        ozellik = f"{p['ad']}=={p['yeni']}"
        oncesi, onceki_uyumsuz = paketler(), uyumsuzluklar(calistir)
        kuruldu, cikti = _pip(["install", "--upgrade-strategy", "only-if-needed", ozellik], calistir)
        neden = None if kuruldu else "kurulamadı: " + cikti.strip().splitlines()[-1][:200] if cikti.strip() else "kurulamadı"
        if kuruldu:
            yeni_uyumsuz = sorted(uyumsuzluklar(calistir) - onceki_uyumsuz)
            if yeni_uyumsuz:
                neden = ("başka bir kütüphaneyle uyumsuz (" + "; ".join(yeni_uyumsuz)[:300]
                         + "); birlikte yükseltilmesi gerekiyor, yazılım güncellemesiyle (yama) yapılmalı")
        if neden:
            _geri_don(oncesi, paketler(), calistir)
            atlanan.append({"ad": p["ad"], "yeni": p["yeni"], "neden": neden})
            adimlar.append(f"Atlandı: {ozellik} -- {neden}")
        else:
            uygulanan.append(ozellik)
            adimlar.append(f"Kuruldu: {ozellik}")
    ok = bool(uygulanan)
    if ok:
        mesaj = dml_kontrol_ve_onar(onceki, calistir)
        if mesaj:
            adimlar.append(mesaj)
        ok, hata = dogrula(calistir)
        adimlar.append("Uygulama yeni kütüphanelerle açılabiliyor" if ok else f"Uygulama AÇILAMIYOR: {hata[-300:]}")
        if not ok:
            adimlar.append("Otomatik geri alınıyor")
            geri_al(yedek_adi, calistir, paketler, kaydet=False, adimlar=adimlar)
    elif not atlanan:
        adimlar.append("Uygulanacak geçerli paket yok")
    if ok:
        _yeniden_tara(adimlar)
        mesaj = f"{len(uygulanan)} kütüphane güncellendi" + (f", {len(atlanan)} tanesi atlandı" if atlanan else "") \
            + "; PTS yeniden başlatılıp izlenecek"
    else:
        mesaj = "Güncelleme uygulanamadı" + (", eski sürümler yerinde" if atlanan or uygulanan else "")
    _durum_yaz(bitis=datetime.now().isoformat(timespec="seconds"), basarili=ok, adimlar=adimlar, yedek=yedek_adi,
               uygulanan=uygulanan, atlanan=atlanan, mesaj=mesaj)
    return json_oku("durum.json")


def _yeniden_tara(adimlar: list) -> None:
    """Güncelleme/geri alma sonrası tablo eski taramayı göstermesin (2026-11-06 sahada:
    pip 26.2'ye güncellendiği halde tablo 25.0.1 ve 6 açık göstermeye devam etti)."""
    try:
        t = tara()
        json_yaz("tarama.json", t)
        adimlar.append(f"Yeniden tarandı: {t['acik_paket']} kütüphanede açık kaldı" if t["acik_paket"]
                       else "Yeniden tarandı: bilinen güvenlik açığı kalmadı")
    except Exception as exc:  # internet yoksa güncelleme yine başarılıdır
        adimlar.append(f"Yeniden taranamadı ({type(exc).__name__}); ekranda 'Şimdi tara' ile tarayın")


def _geri_don(eski: dict, simdi: dict, calistir: Callable, adimlar: Optional[list] = None) -> bool:
    """`simdi`yi `eski`ye döndürür: değişenler eski sürüme, yeni eklenenler kaldırılır.
    Ekran kartı motoru paketlerine dokunulmaz (dml_kontrol_ve_onar ayrıca bakar)."""
    adimlar = adimlar if adimlar is not None else []
    motor = ("onnxruntime", "onnxruntime-directml")
    degisen = [f"{eski[k][0]}=={eski[k][1]}" for k in eski if k in simdi and simdi[k][1] != eski[k][1] and k not in motor]
    eklenen = [simdi[k][0] for k in simdi if k not in eski and k not in (*motor, "pip")]
    ok = True
    if degisen:
        ok, cikti = _pip(["install", "--no-deps", *degisen], calistir)
        adimlar.append(("Eski sürümlere dönüldü: " if ok else f"Geri dönüş BAŞARISIZ ({cikti[-300:]}): ") + ", ".join(degisen))
    if eklenen:
        _pip(["uninstall", "-y", *eklenen], calistir)
        adimlar.append("Sonradan eklenenler kaldırıldı: " + ", ".join(eklenen))
    if not degisen and not eklenen:
        adimlar.append("Yedekle aynı sürümler kurulu; değişiklik yok")
    return ok


def son_yedek() -> Optional[str]:
    yedekler = sorted(f for f in os.listdir(yol("yedekler")) if f.endswith(".json"))
    return f"yedekler/{yedekler[-1]}" if yedekler else None


def geri_al(yedek_adi: Optional[str] = None, calistir: Callable = subprocess.run, paketler: Optional[Callable] = None,
            kaydet: bool = True, adimlar: Optional[list] = None) -> dict:
    """Yedekteki sürümlere döner: yalnız DEĞİŞEN paketler eski sürüme, yeni eklenenler kaldırılır."""
    paketler = paketler or kurulu_paketler
    adimlar = adimlar if adimlar is not None else []
    yedek_adi = yedek_adi or son_yedek()
    eski = {k: tuple(v) for k, v in (json_oku(yedek_adi, {}) or {}).items()} if yedek_adi else {}
    if kaydet:
        _durum_yaz(islem="geri_al", baslangic=datetime.now().isoformat(timespec="seconds"), bitis=None,
                   basarili=None, adimlar=adimlar, yedek=yedek_adi, izleme=None, izleme_bitti=False, mesaj=None)
    if not eski:
        adimlar.append("Geri dönülecek yedek bulunamadı")
        if kaydet:
            _durum_yaz(bitis=datetime.now().isoformat(timespec="seconds"), basarili=False, mesaj="Yedek yok")
        return json_oku("durum.json") or {}
    ok = _geri_don(eski, paketler(), calistir, adimlar)
    mesaj = dml_kontrol_ve_onar(eski, calistir)
    if mesaj:
        adimlar.append(mesaj)
    if kaydet:
        if ok:
            _yeniden_tara(adimlar)
        _durum_yaz(bitis=datetime.now().isoformat(timespec="seconds"), basarili=ok, adimlar=adimlar,
                   mesaj="Eski sürümlere dönüldü" if ok else "Geri dönüş tamamlanamadı")
    return json_oku("durum.json") or {}


_IZLEME_METINLERI = {
    "ok": "PTS yeniden başlatıldı; {sn} sn izleme sorunsuz",
    "kurulum": "Kurulum aşamasında eski sürümlere dönüldü; PTS yeniden başlatılmadı",
    "geri_donuldu": "Yeni sürümlerle PTS sağlıklı çalışmadı; eski sürümlere dönüldü ve PTS yeniden başlatıldı",
    "eski_de_yanit_yok": "Yeni sürümlerle PTS sağlıklı çalışmadı; eski sürümlere dönüldü ama PTS yine yanıt vermiyor -- loglar\\pts.log dosyasına bakın",
    "geri_al_yanit_yok": "Geri alma sonrası PTS yanıt vermiyor -- loglar\\pts.log dosyasına bakın",
    "servis_yok": "PTS servisi bulunamadı; PTS'i elle yeniden başlatın",
    "geri_al_basarisiz": "Geri alma tamamlanamadı; PTS yeniden başlatılmadı (ayrıntı yukarıda)",
    "yeniden_baslatmasiz": "PTS'in yeniden başlatılması gerekmedi (yalnız kurulum aracı güncellendi)",
}


# 2026-11-06 saha hatası: "yeniden_baslatmasiz" başarı sayılmıyordu; pip başarıyla
# güncellendiği halde ekranda "Başarısız" görünüyordu.
_BASARILI_IZLEME_KODLARI = ("ok", "yeniden_baslatmasiz")


def main(argv=None) -> int:
    komut = (argv or sys.argv[1:] or [""])[0]
    if komut == "uygula":
        return 0 if uygula().get("basarili") else 1
    if komut == "geri-al":
        return 0 if geri_al().get("basarili") else 1
    if komut == "dogrula":
        ok, hata = dogrula()
        print(hata)
        return 0 if ok else 1
    if komut == "izleme-sonucu":   # kutuphane_guncelle.ps1: "izleme-sonucu <kod> [sn]"
        argumanlar = (argv or sys.argv[1:])[1:] + ["", ""]
        kod, sn = argumanlar[0], argumanlar[1]
        metin = _IZLEME_METINLERI.get(kod, kod)[:300].format(sn=sn)
        alanlar = {"izleme": metin, "izleme_bitti": True, "izleme_zamani": datetime.now().isoformat(timespec="seconds")}
        durum = json_oku("durum.json", {}) or {}
        if kod in _BASARILI_IZLEME_KODLARI:
            alanlar["mesaj"] = (durum.get("mesaj") or "").replace("; PTS yeniden başlatılıp izlenecek", "")
        else:
            alanlar["basarili"] = False
            if kod not in ("kurulum", "geri_al_basarisiz"):
                alanlar["mesaj"] = "Yeniden başlatma sonrası sorun görüldü"
        _durum_yaz(**alanlar)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
