"""backend/dahua_olay.py testleri -- GERÇEKTEN çalıştırıldı (fastapi'den
bağımsız). Gerçek bir Dahua kamera yerine, Dahua'nın HTTP API belgesindeki
`snapManager.cgi attachFileProc` yanıt biçimini (multipart/x-mixed-replace:
text/plain olay metni + image/jpeg + "Heartbeat") taklit eden yerel bir HTTP
sunucusu kullanılır."""
import http.server
import random
import socketserver
import threading
import time

import pytest

from backend import dahua_olay as d

_OLAY_METNI = (
    "Events[0].Code=TrafficJunction\r\n"
    "Events[0].CountInGroup=1\r\n"
    "Events[0].Lane=1\r\n"
    "Events[0].TrafficCar.PlateNumber=39AES145\r\n"
    "Events[0].TrafficCar.PlateColor=White\r\n"
)
_JPEG = b"\xff\xd8\xff\xe0" + b"sahte-foto" * 50 + b"\xff\xd9"


def _parca(tur: str, govde: bytes, uzunluk=True) -> bytes:
    basliklar = f"--myboundary\r\nContent-Type: {tur}\r\n"
    if uzunluk:
        basliklar += f"Content-Length: {len(govde)}\r\n"
    return basliklar.encode() + b"\r\n" + govde + b"\r\n"


# ------------------------------------------------------------------ yardımcılar

def test_rtsp_adresinden_baglanti_ve_olay_adresi():
    b = d.rtsp_adresinden_baglanti("rtsp://admin:Par%40la1@192.168.1.64:554/cam/realmonitor?channel=1&subtype=0")
    assert b == {"host": "192.168.1.64", "port": 80, "kullanici": "admin", "parola": "Par@la1"}
    assert d.rtsp_adresinden_baglanti("rtsp://a:b@10.0.0.5/x", 8080)["port"] == 8080
    adres = d.olay_adresi("192.168.1.64", 80, "TrafficJunction")
    assert adres == ("http://192.168.1.64/cgi-bin/snapManager.cgi?action=attachFileProc"
                     "&Flags[0]=Event&Events=[TrafficJunction]&heartbeat=5")
    assert d.olay_adresi("10.0.0.5", 8080, "A,B").startswith("http://10.0.0.5:8080/")
    with pytest.raises(ValueError, match="kullanıcı adı"):
        d.rtsp_adresinden_baglanti("rtsp://192.168.1.64:554/stream")


def test_olay_adi_dogrulama_url_enjeksiyonunu_engeller():
    assert d.olaylari_dogrula(None) == "TrafficJunction"
    assert d.olaylari_dogrula("TrafficJunction, TrafficParkingSpace") == "TrafficJunction,TrafficParkingSpace"
    for kotu in ("Traffic]&action=x", "a b/c", "../x"):
        with pytest.raises(ValueError):
            d.olaylari_dogrula(kotu)


@pytest.mark.parametrize("metin,beklenen", [
    (_OLAY_METNI, "39AES145"),
    ('Code=TrafficJunction;data={ "TrafficCar" : { "PlateNumber" : "34 ABC 123" } }', "34ABC123"),
    ("Events[0].Object.Text=06XYZ42\r\n", "06XYZ42"),
    ("Events[0].TrafficCar.PlateNumber=\r\n", None),
    ("Events[0].TrafficCar.PlateNumber=Unknown\r\n", None),
    ("Heartbeat", None),
])
def test_olay_metninden_plaka(metin, beklenen):
    assert d.olay_metninden_plaka(metin) == beklenen


def test_multipart_parca_parca_gelse_de_dogru_ayristirilir_ve_foto_eslesir():
    akis = (
        _parca("text/plain", b"Heartbeat")
        + _parca("text/plain", _OLAY_METNI.encode())
        + _parca("image/jpeg", _JPEG)
        + _parca("image/jpeg", b"\xff\xd8plaka-kirpintisi\xff\xd9")  # aynı olayın 2. fotoğrafı
        + _parca("text/plain", b"Heartbeat", uzunluk=False)
        + _parca("text/plain", b"Events[0].TrafficCar.PlateNumber=06XYZ42\r\n")
        + _parca("text/plain", b"Heartbeat")  # fotoğrafsız olay bir sonraki metinle kapanır
        + b"--myboundary\r\n"
    )
    rnd = random.Random(7)
    for _ in range(20):  # rastgele parça boyutlarıyla
        ayr = d.MultipartAyristirici("myboundary")
        bir = d.OlayBirlestirici()
        olaylar = []
        i = 0
        while i < len(akis):
            n = rnd.randint(1, 300)
            for tur, govde in ayr.besle(akis[i:i + n]):
                olaylar += bir.parca(tur, govde)
            i += n
        assert [o["plaka"] for o in olaylar] == ["39AES145", "06XYZ42"]
        assert olaylar[0]["jpeg"] == _JPEG
        assert olaylar[0]["kod"] == "TrafficJunction"
        assert olaylar[1]["jpeg"] is None
        assert bir.kalp_atisi_sayisi == 3


# ------------------------------------------------------------------ sahte kamera

class _SahteDahua:
    def __init__(self, durum=200, akis=b"", bekle_sn=3.0, digest=True):
        sunucu = self
        self.digest = digest

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                sunucu.yollar.append(self.path)
                if sunucu.digest and not sunucu._digest_dogru(self.headers.get("Authorization"), self.path):
                    # Gerçek Dahua gibi Digest kimlik doğrulaması iste.
                    self.send_response(401)
                    self.send_header("WWW-Authenticate",
                                     'Digest realm="Login to 4L0000PAZ", qop="auth", nonce="1234abcd", opaque="op1"')
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(durum)
                if durum != 200:
                    self.end_headers()
                    return
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=myboundary")
                self.end_headers()
                try:
                    self.wfile.write(akis)
                    self.wfile.flush()
                    son = time.time() + bekle_sn
                    while time.time() < son and not sunucu.kapat_istegi:
                        self.wfile.write(_parca("text/plain", b"Heartbeat"))
                        self.wfile.flush()
                        time.sleep(0.3)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True

        self.yollar = []
        self.kapat_istegi = False
        self.httpd = S(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @staticmethod
    def _digest_dogru(baslik, yol):
        """RFC 2617 Digest yanıtını gerçekten doğrular (kullanıcı admin, parola gizli)."""
        import hashlib
        import re as _re
        if not baslik or not baslik.startswith("Digest "):
            return False
        alan = dict(_re.findall(r'(\w+)="?([^",]+)"?', baslik))
        md5 = lambda x: hashlib.md5(x.encode()).hexdigest()
        ha1 = md5(f"admin:{'Login to 4L0000PAZ'}:gizli")
        ha2 = md5(f"GET:{alan.get('uri')}")
        beklenen = md5(f"{ha1}:1234abcd:{alan.get('nc')}:{alan.get('cnonce')}:auth:{ha2}")
        return alan.get("username") == "admin" and alan.get("response") == beklenen and alan.get("uri") == yol

    def rtsp(self):
        return "rtsp://admin:gizli@127.0.0.1:554/cam/realmonitor?channel=1"

    def kapat(self):
        self.kapat_istegi = True
        self.httpd.shutdown()


def test_dinleyici_kameradan_plakayi_ve_fotoyu_alir():
    kamera = _SahteDahua(akis=_parca("text/plain", _OLAY_METNI.encode()) + _parca("image/jpeg", _JPEG))
    alinan = []
    dinleyici = d.DahuaOlayDinleyici(kamera.rtsp(), "TEST", lambda p, j: alinan.append((p, j)),
                                     http_port=kamera.port)
    dinleyici.baslat()
    try:
        son = time.time() + 5
        while not alinan and time.time() < son:
            time.sleep(0.05)
        assert alinan == [("39AES145", _JPEG)]
        durum = dinleyici.durum()
        assert durum["bagli"] is True and durum["olay_sayisi"] == 1 and durum["son_plaka"] == "39AES145"
        assert any("PlateNumber=39AES145" in o["metin"] for o in durum["ham_ornekler"])
        from urllib.parse import unquote
        # (HTTP kütüphanesi köşeli parantezleri %5B/%5D olarak kodlayabilir;
        # Dahua CGI'si bunu standart URL çözmesiyle kabul eder.)
        assert "Events=[TrafficJunction]" in unquote(kamera.yollar[0]) and "heartbeat=5" in kamera.yollar[0]
        assert "gizli" not in str(durum), "Parola durum bilgisinde görünmemeli"
    finally:
        dinleyici.durdur()
        kamera.kapat()


def test_baglanti_testi_basarili_ve_yetkisiz():
    kamera = _SahteDahua(akis=_parca("text/plain", _OLAY_METNI.encode()) + _parca("image/jpeg", _JPEG))
    try:
        s = d.baglanti_testi(kamera.rtsp(), http_port=kamera.port, sure_sn=1.5)
        assert s["basarili"] is True, s
        assert s["olaylar"] == [{"plaka": "39AES145", "kod": "TrafficJunction", "fotograf": True}]
        assert s["kalp_atisi_sayisi"] >= 1
    finally:
        kamera.kapat()

    kamera = _SahteDahua(durum=401)
    try:
        s = d.baglanti_testi(kamera.rtsp(), http_port=kamera.port, sure_sn=1)
        assert s["basarili"] is False and s["http_durum"] == 401
        assert "Kimlik doğrulama" in s["hata"]
    finally:
        kamera.kapat()


def test_baglanti_testi_kameraya_ulasilamazsa_anlasilir_hata():
    s = d.baglanti_testi("rtsp://a:b@127.0.0.1/x", http_port=1, sure_sn=1)
    assert s["basarili"] is False and "bağlanılamadı" in s["hata"]


def test_digest_kimlik_dogrulamasi_yanlis_parolada_anlasilir_hata():
    kamera = _SahteDahua()
    try:
        s = d.baglanti_testi("rtsp://admin:YANLIS@127.0.0.1:554/x", http_port=kamera.port, sure_sn=1)
        assert s["basarili"] is False and s["http_durum"] == 401 and "Kimlik doğrulama" in s["hata"]
    finally:
        kamera.kapat()
