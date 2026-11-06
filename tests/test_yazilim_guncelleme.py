"""Yazılım güncellemeleri (2026-11-06, backend/yazilim_guncelleme.py)."""
import json
from types import SimpleNamespace

import pytest

from backend import yazilim_guncelleme as yg


@pytest.fixture(autouse=True)
def ayri_klasor(tmp_path, monkeypatch):
    monkeypatch.setenv("PTS_GUNCELLEME_KLASORU", str(tmp_path / "yg"))
    return tmp_path / "yg"


def test_onerilen_surum_en_dusuk_kapatan():
    aciklar = [{"duzelten": ["0.0.18"]}, {"duzelten": ["0.0.22"]}, {"duzelten": ["0.0.31", "1.0.0"]}]
    assert yg.onerilen_surum("0.0.9", aciklar) == "0.0.31"
    assert yg.onerilen_surum("0.0.9", [{"duzelten": []}]) is None          # düzeltmesi yok
    assert yg.onerilen_surum("2.0", [{"duzelten": ["1.5", "2.1"]}]) == "2.1"  # eski dal düzeltmesi atlanır


def test_aciklar_tekillesir():
    ham = [{"id": "GHSA-1", "aliases": ["CVE-2026-1", "PYSEC-9"], "fixed_in": ["1.2"], "summary": "x"},
           {"id": "PYSEC-9", "aliases": ["CVE-2026-1"], "fixed_in": ["1.2"]},
           {"id": "GHSA-2", "aliases": [], "fixed_in": ["1.3"]}]
    t = yg._aciklari_tekillestir(ham)
    assert [a["id"] for a in t] == ["CVE-2026-1", "GHSA-2"]


def _sahte_pypi(veriler):
    def getir(url):
        parca = url.split("/pypi/")[1].rstrip("/").split("/")
        ad = parca[0]
        if ad not in veriler:
            return None
        if len(parca) == 3:      # /ad/sürüm/json
            return {"vulnerabilities": veriler[ad]["aciklar"]}
        return {"info": {"version": veriler[ad]["en_yeni"]}}
    return getir


def test_tara_ve_plan():
    paketler = {"pillow": ("pillow", "11.0.0"), "onnxruntime": ("onnxruntime", "1.29.0"),
                "requests": ("requests", "2.34.2"), "yerel-paket": ("yerel-paket", "1.0")}
    veriler = {
        "pillow": {"en_yeni": "13.0.0", "aciklar": [{"id": "CVE-A", "fixed_in": ["12.1.1"]}, {"id": "CVE-B", "fixed_in": ["11.3.0"]}]},
        "onnxruntime": {"en_yeni": "1.31.0", "aciklar": [{"id": "CVE-C", "fixed_in": ["1.30.0"]}]},
        "requests": {"en_yeni": "2.34.2", "aciklar": []},
    }
    t = yg.tara(paketler, getir=_sahte_pypi(veriler))
    ad = {p["ad"]: p for p in t["paketler"]}
    assert "yerel-paket" not in ad                       # PyPI'de olmayan atlanır
    assert ad["pillow"]["onerilen"] == "12.1.1" and ad["pillow"]["guncel_degil"]
    assert ad["onnxruntime"]["tutulan"] is True
    assert ad["requests"]["aciklar"] == [] and not ad["requests"]["guncel_degil"]
    assert t["acik_paket"] == 2 and t["acik_sayisi"] == 3
    assert t["paketler"][0]["ad"] in ("pillow", "onnxruntime")    # açıklılar önce
    # Plaka motoru paketi plana girmez; en yeniye değil açığı kapatan sürüme.
    assert yg.plan_olustur(t) == [{"ad": "pillow", "eski": "11.0.0", "yeni": "12.1.1"}]


def test_plan_supheli_ad_ve_surumu_almaz():
    t = {"paketler": [{"ad": "kotu; rm -rf", "surum": "1", "aciklar": [{}], "onerilen": "2", "tutulan": False},
                      {"ad": "iyi", "surum": "1", "aciklar": [{}], "onerilen": "2 && x", "tutulan": False}]}
    assert yg.plan_olustur(t) == []


class SahtePip:
    """subprocess.run yerine: pip install/uninstall çağrılarını kaydeder, kurulu paketleri günceller."""
    def __init__(self, kurulu, basarisiz=(), dml_calisiyor=True, ice_aktarma_ok=True, uyumsuzluk=None):
        self.kurulu, self.basarisiz, self.dml, self.ice = dict(kurulu), basarisiz, dml_calisiyor, ice_aktarma_ok
        self.uyumsuzluk = uyumsuzluk     # (paket, sürüm) kurulunca pip check'in vereceği satır
        self.cagrilar = []

    def paketler(self):
        return dict(self.kurulu)

    def __call__(self, arg, **kw):
        self.cagrilar.append(arg)
        if arg[1] == "-c":
            kod = arg[2]
            ok = self.dml if "Dml" in kod else self.ice
            return SimpleNamespace(returncode=0 if ok else 3, stdout="", stderr="" if ok else "ImportError: x")
        islem = arg[4]
        if islem == "check":
            satir = ""
            if self.uyumsuzluk and self.kurulu.get(self.uyumsuzluk[0], (None, None))[1] == self.uyumsuzluk[1]:
                satir = self.uyumsuzluk[2]
            return SimpleNamespace(returncode=1 if satir else 0, stdout=satir, stderr="")
        ozellikler = [a for a in arg[5:] if not a.startswith("-") and a != "only-if-needed"]
        if islem == "install":
            if any(o.split("==")[0] in self.basarisiz for o in ozellikler):
                return SimpleNamespace(returncode=1, stdout="", stderr="ERROR")
            for o in ozellikler:
                ad, surum = o.split("==")
                self.kurulu[yg.normalize(ad)] = (ad, surum)
                if ad == "onnxruntime-directml":
                    self.dml = True
        else:
            for ad in ozellikler:
                self.kurulu.pop(yg.normalize(ad), None)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")


def test_uygula_basarili_yedek_alir(ayri_klasor):
    pip = SahtePip({"pillow": ("pillow", "11.0.0"), "requests": ("requests", "2.0")})
    yg.json_yaz("plan.json", [{"ad": "pillow", "eski": "11.0.0", "yeni": "12.1.1"}])
    d = yg.uygula(calistir=pip, paketler=pip.paketler)
    assert d["basarili"] is True and pip.kurulu["pillow"][1] == "12.1.1"
    yedek = json.loads((ayri_klasor / d["yedek"]).read_text(encoding="utf-8"))
    assert yedek["pillow"] == ["pillow", "11.0.0"]
    # Geri al: yalnız değişen paket eski sürümüne döner.
    g = yg.geri_al(calistir=pip, paketler=pip.paketler)
    assert g["basarili"] is True and pip.kurulu["pillow"][1] == "11.0.0"
    assert any(c[4:] == ["install", "--no-deps", "pillow==11.0.0"] for c in pip.cagrilar)


def test_uygula_uygulama_acilamazsa_kendisi_geri_alir():
    pip = SahtePip({"starlette": ("starlette", "0.38.6")}, ice_aktarma_ok=False)
    yg.json_yaz("plan.json", [{"ad": "starlette", "eski": "0.38.6", "yeni": "1.1.0"}])
    d = yg.uygula(calistir=pip, paketler=pip.paketler)
    assert d["basarili"] is False and pip.kurulu["starlette"][1] == "0.38.6"
    assert any("Otomatik geri" in a for a in d["adimlar"])


def test_ekran_karti_motoru_bozulursa_onarilir():
    """2026-11-06 sahadaki olay: başka bir paket kurulurken DirectML kayboldu."""
    pip = SahtePip({"pillow": ("pillow", "11.0.0"), "onnxruntime-directml": ("onnxruntime-directml", "1.24.4")},
                   dml_calisiyor=False)
    yg.json_yaz("plan.json", [{"ad": "pillow", "eski": "11.0.0", "yeni": "12.1.1"}])
    d = yg.uygula(calistir=pip, paketler=pip.paketler)
    assert d["basarili"] is True and pip.dml is True
    assert any("Ekran kartı motoru onarıldı" in a for a in d["adimlar"])


def test_bos_plan_ve_yedeksiz_geri_al():
    assert yg.uygula(calistir=SahtePip({}), paketler=dict)["mesaj"] == "Uygulanacak güncelleme yok"
    assert yg.geri_al(calistir=SahtePip({}), paketler=dict)["basarili"] is False


def test_uyumsuz_hale_getiren_guncelleme_geri_alinir():
    """2026-11-06 demoda görüldü: starlette 0.38 -> 1.3 yükseltmesi fastapi 0.115'in şartını
    çiğner; pip yalnız uyarır. pip check'te yeni uyumsuzluk çıkarsa geri alınmalı."""
    satir = "fastapi 0.115.0 has requirement starlette<0.39.0,>=0.37.2, but you have starlette 1.3.1."
    pip = SahtePip({"starlette": ("starlette", "0.38.6"), "fastapi": ("fastapi", "0.115.0")},
                   uyumsuzluk=("starlette", "1.3.1", satir))
    yg.json_yaz("plan.json", [{"ad": "starlette", "eski": "0.38.6", "yeni": "1.3.1"}])
    d = yg.uygula(calistir=pip, paketler=pip.paketler)
    assert d["basarili"] is False and pip.kurulu["starlette"][1] == "0.38.6"
    assert any("uyumsuz" in a and "fastapi" in a for a in d["adimlar"])


def test_karisik_planda_uyumlu_olan_kalir_uyumsuz_olan_atlanir():
    satir = "fastapi 0.115.0 has requirement starlette<0.39.0,>=0.37.2, but you have starlette 1.3.1."
    pip = SahtePip({"starlette": ("starlette", "0.38.6"), "fastapi": ("fastapi", "0.115.0"),
                    "requests": ("requests", "2.31.0")}, uyumsuzluk=("starlette", "1.3.1", satir))
    yg.json_yaz("plan.json", [{"ad": "requests", "eski": "2.31.0", "yeni": "2.33.0"},
                              {"ad": "starlette", "eski": "0.38.6", "yeni": "1.3.1"}])
    d = yg.uygula(calistir=pip, paketler=pip.paketler)
    assert d["basarili"] is True
    assert pip.kurulu["requests"][1] == "2.33.0" and pip.kurulu["starlette"][1] == "0.38.6"
    assert d["uygulanan"] == ["requests==2.33.0"] and d["atlanan"][0]["ad"] == "starlette"
    assert "1 tanesi atlandı" in d["mesaj"]


def test_kurulum_araclari_plana_girmez():
    t = yg.tara({"pip": ("pip", "24.0")}, getir=_sahte_pypi({"pip": {"en_yeni": "26.2", "aciklar": [{"id": "CVE-P", "fixed_in": ["25.0"]}]}}))
    assert t["paketler"][0]["arac"] is True and yg.plan_olustur(t) == []
