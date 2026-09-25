"""Rapor üretiminin AYRI bir süreçte ("spawn") çalışabildiğini doğrular
(2026-09-25, bkz. main.py::_raporu_uret). main.py fastapi gerektirdiği için
burada doğrudan main'deki havuz kullanılamıyor; ama main.py'nin yaptığıyla
BİREBİR aynı şeyi yapıyoruz: spawn bağlamlı bir ProcessPoolExecutor'a
`backend.pdf_export.kayitlar_pdf_olustur` / `backend.excel_export.
kayitlar_excel_olustur` fonksiyonlarını, `_kayitlari_rapor_satirlari`nın
ürettiği biçimde (datetime içeren düz sözlükler) satırlarla gönderiyoruz.
Bu, Windows'taki (tek seçenek spawn) davranışın -- modüllerin çocuk süreçte
yeniden içe aktarılabilmesi, argümanların pickle'lanabilmesi -- Linux'ta da
sınanmasını sağlar."""
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime

from backend import excel_export, pdf_export


def _satirlar(n, goruntu_yolu=None):
    return [{
        "id": i, "plaka_no": "34 ABC 123", "ad": "Ahmet", "soyad": "Yılmaz", "site": "LOJMAN", "blok": "",
        "daire": "PERSONEL", "otopark": "", "nokta": "NİZAMİYE", "gecis_tipi": "Giriş", "arac_tipi": "Tanımlı",
        "tarih_saat": datetime(2026, 9, 25, 8, 4, 7), "notlar": "not", "goruntu_yolu": goruntu_yolu,
        "vardiya": "ahmet (08:00-16:00)",
    } for i in range(n)]


def test_pdf_ve_excel_spawn_surecinde_uretilebilir(tmp_path):
    from PIL import Image
    gorsel = tmp_path / "kare.jpg"
    Image.new("RGB", (1920, 1080), (90, 120, 150)).save(gorsel, quality=80)

    pdf_yolu = str(tmp_path / "rapor.pdf")
    xlsx_yolu = str(tmp_path / "rapor.xlsx")
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as havuz:
        havuz.submit(pdf_export.kayitlar_pdf_olustur, _satirlar(30, str(gorsel)), pdf_yolu,
                     tarih_araligi_metni="test").result(timeout=120)
        havuz.submit(excel_export.kayitlar_excel_olustur, _satirlar(30), xlsx_yolu).result(timeout=120)

    with open(pdf_yolu, "rb") as f:
        assert f.read(5) == b"%PDF-"
    assert os.path.getsize(xlsx_yolu) > 0
