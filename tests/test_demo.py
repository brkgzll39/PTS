"""2026-10-23: demo aracı (araclar/demo.py) -- gerçek sisteme dokunmadığını ve
görsel/plaka üretiminin çalıştığını denetler. Sunucu başlatılmaz."""
import importlib.util
import io
import os
import re

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def demo():
    spec = importlib.util.spec_from_file_location("pts_demo", os.path.join(KOK, "araclar", "demo.py"))
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_plaka_ve_gorsel(demo):
    import random
    from PIL import Image
    r = random.Random(1)
    for _ in range(50):
        assert re.fullmatch(r"\d{2} [A-Z]{1,3} \d{2,4}", demo.rastgele_plaka(r))
    jpeg = demo.arac_gorseli("34 ABC 123", gece=True, tohum=1, kamera="Ana Kapı Giriş")
    assert Image.open(io.BytesIO(jpeg)).size == (960, 540)


def test_ortam_yalniz_demo_klasorunu_gosterir(demo, tmp_path):
    onceki = dict(os.environ)
    try:
        demo._ortami_hazirla(str(tmp_path), "musteriler/ornek", 8100)
        yollar = [v for k, v in os.environ.items() if k.startswith("PTS_") and (os.sep in v or "/" in v)
                  and k != "PTS_MARKA_FILE"]
        assert yollar and all(str(tmp_path).replace("\\", "/") in v.replace("\\", "/") for v in yollar)
        assert os.environ["PTS_HOST"] == "127.0.0.1" and os.environ["PTS_ENV_DOSYASINI_ATLA"] == "1"
    finally:   # diğer testlerin ortamı bozulmasın
        os.environ.clear()
        os.environ.update(onceki)


def test_sifirla_demo_olmayan_klasoru_silmez(demo, tmp_path):
    (tmp_path / "onemli.txt").write_text("x")
    with pytest.raises(SystemExit, match="demo klasörü değil"):
        demo.main(["--klasor", str(tmp_path), "--sifirla"])
    assert (tmp_path / "onemli.txt").exists()
