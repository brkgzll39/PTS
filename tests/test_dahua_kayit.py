"""Dahua kameranın hafızasındaki geçişleri sonradan alma (backend/dahua_kayit.py) --
sahte bir Dahua HTTP sunucusuyla."""
import os
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from backend import dahua_kayit

os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
os.environ["no_proxy"] = os.environ.get("NO_PROXY", "127.0.0.1,localhost")

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 3000 + b"\xff\xd9"


@pytest.fixture(autouse=True)
def turkiye_saati():
    """Saat yorumu hataları UTC'de çalışan makinede görünmez (yerel = UTC): Türkiye saatiyle çalıştır."""
    import time
    eski = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Istanbul"
    time.tzset()
    yield
    if eski is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = eski
    time.tzset()


def _yoksayan_veri():
    """TPAO Lojman kamerasında görülen davranış (2026-10-31): 3000 kayıt, dakikada bir."""
    # Gün başına sabit: kamera verisi ile testin beklentisi ayrı anlarda üretilince saniye kaymasın.
    t0 = int((datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=3)).timestamp())
    return [(i + 1, t0 + 60 * i, f"34TPA{i:04d}") for i in range(3000)]


def _rf_metin(kayitlar):
    satirlar = [f"found={len(kayitlar)}"]
    for j, (rec, t, plaka) in enumerate(kayitlar):
        satirlar += [f"records[{j}].RecNo={rec}", f"records[{j}].Time={t}", f"records[{j}].PlateNumber={plaka}",
                     f"records[{j}].VehicleDirection=Tail"]
    return "\r\n".join(satirlar) + "\r\n"


def _sahte_kamera(mod: str):
    """mod: 'record' (recordFinder süzgeci çalışır) | 'media' (yalnız mediaFileFind çalışır) |
    'yoksay' (süzgeç yok sayılır, en eskiden 1024 kayıt; doSeekFind çalışır)."""
    istekler = []
    veri = _yoksayan_veri()

    class Isleyici(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _yaz(self, kod, govde, tur="text/plain"):
            veri = govde if isinstance(govde, bytes) else govde.encode()
            self.send_response(kod)
            self.send_header("Content-Type", tur)
            self.send_header("Content-Length", str(len(veri)))
            self.end_headers()
            self.wfile.write(veri)

        def do_GET(self):
            istekler.append(self.path)
            u = urlsplit(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path == "/cgi-bin/recordFinder.cgi" and mod == "yoksay":
                if q.get("action") == "doSeekFind":
                    o, n = int(q.get("offset", 0)), int(q.get("count", 1))
                    return self._yaz(200, _rf_metin(veri[o:o + min(n, 1024)]))
                return self._yaz(200, _rf_metin(veri[:1024]))
            if u.path == "/cgi-bin/recordFinder.cgi":
                if mod != "record" or "condition.StartTime" not in q or not q["condition.StartTime"].isdigit():
                    return self._yaz(400, "Error\r\nBad Request!")
                t = int(q["condition.StartTime"]) + 600
                return self._yaz(200, "totalCount=3\r\nfound=3\r\n"
                                 f"records[0].RecNo=11\r\nrecords[0].CreateTime={t}\r\nrecords[0].PlateNumber=34ABC123\r\n"
                                 f"records[1].RecNo=12\r\nrecords[1].CreateTime={t + 5}\r\nrecords[1].PlateNumber=34ABC123\r\n"
                                 f"records[2].RecNo=13\r\nrecords[2].CreateTime={t + 900}\r\nrecords[2].PlateNumber=UNKNOWN\r\n")
            if u.path == "/cgi-bin/mediaFileFind.cgi":
                eylem = q.get("action")
                if eylem == "factory.create":
                    return self._yaz(200, "result=77\r\n")
                if eylem == "findFile":
                    self.server.bas = datetime.strptime(q["condition.StartTime"], "%Y-%m-%d %H:%M:%S")
                    return self._yaz(200, "OK\r\n")
                if eylem == "findNextFile":
                    if getattr(self.server, "verildi", False):
                        return self._yaz(200, "found=0\r\n")
                    self.server.verildi = True
                    z = (self.server.bas + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
                    return self._yaz(200, "found=1\r\n"
                                     f"items[0].Channel=0\r\nitems[0].StartTime={z}\r\nitems[0].EndTime={z}\r\n"
                                     "items[0].FilePath=/mnt/sd/2026-10-30/001/jpg/02/14/05[M][0@0][0].jpg\r\n"
                                     "items[0].Events[0]=TrafficJunction\r\n"
                                     "items[0].SummaryNew[0].Value.TrafficCar.PlateNumber=06XYZ789\r\n")
                return self._yaz(200, "OK\r\n")
            if u.path.startswith("/cgi-bin/RPC_Loadfile/"):
                return self._yaz(200, b"HDR" + JPEG, "image/jpeg")
            return self._yaz(404, "Error")

    sunucu = ThreadingHTTPServer(("127.0.0.1", 0), Isleyici)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    return sunucu, istekler


@pytest.fixture
def kamera_record():
    s, istekler = _sahte_kamera("record")
    yield f"rtsp://admin:parola@127.0.0.1:554/cam", s.server_address[1], istekler
    s.shutdown()


@pytest.fixture
def kamera_media():
    s, istekler = _sahte_kamera("media")
    yield f"rtsp://admin:parola@127.0.0.1:554/cam", s.server_address[1], istekler
    s.shutdown()


def test_alan_adlarindan_plaka_ve_zaman_tanir():
    k = dahua_kayit.kayitlari_grupla("found=1\nitems[0].StartTime=2026-10-30 02:14:05\n"
                                      "items[0].SummaryNew[0].Value.TrafficCar.PlateNumber=34 AB 1234\n")
    a = dahua_kayit.kayit_ayikla(k[0])
    assert a["plaka"] == "34 AB 1234" and a["zaman"] == datetime(2026, 10, 30, 2, 14, 5)
    assert dahua_kayit.kayit_ayikla({"PlateNumber": "UNKNOWN", "UTC": "1793300000"}) is None
    assert dahua_kayit.zaman_coz("1793300000") == datetime.fromtimestamp(1793300000)


def test_record_finder_ile_kayitlar_ve_tekrar_ayiklama(kamera_record):
    rtsp, port, istekler = kamera_record
    bas = datetime.now() - timedelta(hours=3)
    s = dahua_kayit.kayitlari_getir(rtsp, bas, datetime.now(), http_port=port)
    assert s["basarili"] and s["yontem"] == "recordFinder", s
    # 5 sn arayla iki fotoğraf satırı tek geçiş; UNKNOWN atlanır
    assert [k["plaka"] for k in s["kayitlar"]] == ["34ABC123"]
    assert any("recordFinder.cgi" in i for i in istekler)


def test_media_file_find_yedek_yontem_ve_fotograf(kamera_media):
    rtsp, port, istekler = kamera_media
    bas = datetime.now().replace(microsecond=0) - timedelta(hours=2)
    s = dahua_kayit.kayitlari_getir(rtsp, bas, datetime.now(), http_port=port, olaylar="TrafficJunction")
    assert s["basarili"] and s["yontem"] == "mediaFileFind", s
    assert len(s["ham"]) >= 3  # başarısız denemelerin ham yanıtları da görünür
    k = s["kayitlar"][0]
    assert k["plaka"] == "06XYZ789" and k["dosya"].startswith("/mnt/sd/")
    assert any("action=close" in i for i in istekler)
    assert dahua_kayit.goruntu_indir(rtsp, k["dosya"], http_port=port) == JPEG


def test_kameraya_ulasilamazsa_hata():
    s = dahua_kayit.kayitlari_getir("rtsp://a:b@127.0.0.1:554/x", datetime.now() - timedelta(hours=1), datetime.now(), http_port=9)
    assert not s["basarili"] and "bağlanılamadı" in s["hata"]


@pytest.fixture
def kamera_yoksay():
    s, istekler = _sahte_kamera("yoksay")
    yield f"rtsp://admin:parola@127.0.0.1:554/cam", s.server_address[1], istekler
    s.shutdown()


def test_suzgeci_yok_sayan_kamerada_sira_aramasi(kamera_yoksay):
    rtsp, port, istekler = kamera_yoksay
    veri = _yoksayan_veri()
    # 2000. kaydın saatinden itibaren 90 dakika (1024'lük ilk sayfanın çok ötesi)
    bas = datetime.fromtimestamp(veri[2000][1])
    s = dahua_kayit.kayitlari_getir(rtsp, bas, bas + timedelta(minutes=90), http_port=port)
    assert s["basarili"] and s["yontem"] == "recordFinder (sıra araması)", s
    plakalar = [k["plaka"] for k in s["kayitlar"]]
    assert plakalar[0] == "34TPA2000" and plakalar[-1] == "34TPA2090" and len(plakalar) == 91
    assert any("toplam 3000 kayıt" in h["ornek"] for h in s["ham"])
    assert sum("doSeekFind" in i for i in istekler) < 60  # ikili arama: binlerce kaydı tek tek okumaz
    # Aralık kayıtların sonundan sonra: boş ama başarılı
    s = dahua_kayit.kayitlari_getir(rtsp, datetime.now() + timedelta(days=1), datetime.now() + timedelta(days=2), http_port=port)
    assert s["basarili"] and s["kayitlar"] == []


def _yerel_epok_kamera():
    """TPAO Nizamiye kamerası gibi: yerel saati unix saniyesi gibi yazar, condition.StartTime
    süzgecini AYNI (yerel) saniyelerle uygular. Kayıtlar dün 06:00'dan itibaren saatte bir."""
    yerel = dahua_kayit.yerel_saat_farki()
    bugun = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    gercek = [bugun - timedelta(days=1) + timedelta(hours=6 + i) for i in range(20)]
    veri = [(i + 1, int((z - datetime(1970, 1, 1)).total_seconds()), f"39S{1000 + i}") for i, z in enumerate(gercek)]

    class Isleyici(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            u = urlsplit(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path == "/cgi-bin/recordFinder.cgi" and q.get("condition.StartTime", "").isdigit():
                a, b = int(q["condition.StartTime"]), int(q["condition.EndTime"])
                govde = _rf_metin([r for r in veri if a <= r[1] <= b]).encode()
                self.send_response(200)
            else:
                govde = b"Error\r\nBad Request!"
                self.send_response(400)
            self.send_header("Content-Length", str(len(govde)))
            self.end_headers()
            self.wfile.write(govde)

    sunucu = ThreadingHTTPServer(("127.0.0.1", 0), Isleyici)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    return sunucu, gercek, yerel


def test_yerel_saat_yazan_kamerada_aralik_dogru_sorgulanir():
    sunucu, gercek, yerel = _yerel_epok_kamera()
    try:
        rtsp, port = "rtsp://admin:parola@127.0.0.1:554/cam", sunucu.server_address[1]
        bas, bit = gercek[5] - timedelta(minutes=5), gercek[9] + timedelta(minutes=5)  # 5 kayıt
        s = dahua_kayit.kayitlari_getir(rtsp, bas, bit, http_port=port, kayma=timedelta(0))
        assert s["basarili"], s
        assert [k["zaman"] for k in s["kayitlar"]] == gercek[5:10]
        assert [k["plaka"] for k in s["kayitlar"]] == [f"39S{1005 + i}" for i in range(5)]
    finally:
        sunucu.shutdown()


def test_kamera_unix_zaman_coz_tersidir():
    an = datetime(2026, 10, 31, 8, 23, 0)
    for kayma in (None, timedelta(0), timedelta(hours=3)):
        assert dahua_kayit.zaman_coz(str(dahua_kayit.kamera_unix(an, kayma)), kayma) == an


def test_kaymis_aralikla_sorgu_reddedilmez_ve_en_cok_kayit_veren_yazim_secilir():
    """Sahada (2026-10-31): sorgu aralığı kameraya 3 saat kaymış gidince ±1 saat kuralı doğru
    yazımı eledi, 1 kayıt döndüren başka bir yazım kaldı ve saat ölçülemedi."""
    sunucu, gercek, yerel = _yerel_epok_kamera()
    try:
        rtsp, port = "rtsp://admin:parola@127.0.0.1:554/cam", sunucu.server_address[1]
        bas, bit = gercek[2] - timedelta(minutes=5), gercek[12] + timedelta(minutes=5)
        # Kamera yerel saat yazıyor ama UTC sanılarak (kayma 3 sa) sorgulanıyor: aralık 3 saat kayık gider.
        s = dahua_kayit.kayitlari_getir(rtsp, bas, bit, http_port=port, kayma=timedelta(hours=3))
        assert s["basarili"] and len(s["kayitlar"]) >= 7, s
    finally:
        sunucu.shutdown()
