"""2026-10-22: HTTPS -- sertifika üretimi, sunucu ayarı, kamera iç adresi."""
import socket
import ssl
import threading

import pytest

pytest.importorskip("cryptography")

from backend import camera_reader, sertifika_olustur, sunucu  # noqa: E402


def test_sertifika_zinciri_ca_ile_dogrulanir_ve_ca_korunur(tmp_path):
    klasor = str(tmp_path / "sertifika")
    ilk = sertifika_olustur.olustur(klasor, ["127.0.0.1", "172.17.1.254"], ["localhost"])
    assert ilk["yeni_ca"] is True
    ca_ilk = (tmp_path / "sertifika" / "pts-ca.crt").read_bytes()

    # Gerçek bir TLS el sıkışmasıyla: sunucu sertifikası CA ile doğrulanmalı (IP SAN dahil).
    sunucu_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    sunucu_ctx.load_cert_chain(f"{klasor}/sunucu.crt", f"{klasor}/sunucu.key")
    dinleyici = socket.socket()
    dinleyici.bind(("127.0.0.1", 0))
    dinleyici.listen(1)
    port = dinleyici.getsockname()[1]

    def kabul():
        baglanti, _ = dinleyici.accept()
        try:
            with sunucu_ctx.wrap_socket(baglanti, server_side=True) as s:
                s.recv(1)
        except (ssl.SSLError, OSError):
            pass

    t = threading.Thread(target=kabul, daemon=True)
    t.start()
    istemci_ctx = ssl.create_default_context(cafile=f"{klasor}/pts-ca.crt")
    with socket.create_connection(("127.0.0.1", port)) as ham:
        with istemci_ctx.wrap_socket(ham, server_hostname="127.0.0.1") as s:
            assert s.version() is not None
            s.sendall(b"x")
    t.join(5)
    dinleyici.close()

    ikinci = sertifika_olustur.olustur(klasor, ["127.0.0.1"], ["localhost"])
    assert ikinci["yeni_ca"] is False
    assert (tmp_path / "sertifika" / "pts-ca.crt").read_bytes() == ca_ilk   # bilgisayarlara yeniden yükleme gerekmez


def test_https_ayari(monkeypatch, tmp_path):
    monkeypatch.delenv("PTS_HTTPS", raising=False)
    assert sunucu.https_ayari() == {}
    monkeypatch.setenv("PTS_HTTPS", "1")
    monkeypatch.setenv("PTS_HTTPS_SERTIFIKA", str(tmp_path / "yok.crt"))
    monkeypatch.setenv("PTS_HTTPS_ANAHTAR", str(tmp_path / "yok.key"))
    with pytest.raises(SystemExit, match="sertifika bulunamadı"):
        sunucu.https_ayari()
    (tmp_path / "yok.crt").write_text("x")
    (tmp_path / "yok.key").write_text("x")
    assert sunucu.https_ayari() == {"ssl_certfile": str(tmp_path / "yok.crt"), "ssl_keyfile": str(tmp_path / "yok.key")}


def test_kamera_api_adresi_https_ic_portuna_yonlenir(monkeypatch):
    monkeypatch.setenv("PTS_KAMERA_API_URL", "http://127.0.0.1:8001/kayitlar/otomatik")
    assert camera_reader.varsayilan_api_url() == "http://127.0.0.1:8001/kayitlar/otomatik"
    monkeypatch.delenv("PTS_KAMERA_API_URL")
    monkeypatch.delenv("PTS_PORT", raising=False)
    assert camera_reader.varsayilan_api_url() == "http://127.0.0.1:8000/kayitlar/otomatik"


def _san_ipleri(yol):
    from cryptography import x509

    with open(yol, "rb") as f:
        crt = x509.load_pem_x509_certificate(f.read())
    san = crt.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}


def test_ek_ip_otomatik_ve_onceki_ipleri_dusurmez(monkeypatch, tmp_path, capsys):
    """2026-10-22: `--ip <Tailscale>` ile yenilenen sertifikada LAN IP'si kalmamıştı."""
    klasor = str(tmp_path / "sertifika")
    monkeypatch.setattr(sertifika_olustur, "_yerel_ipler", lambda: ["127.0.0.1", "172.17.1.254"])
    assert sertifika_olustur.main(["--klasor", klasor, "--ip", "100.108.27.27"]) == 0
    assert _san_ipleri(f"{klasor}/sunucu.crt") == {"127.0.0.1", "172.17.1.254", "100.108.27.27"}

    # Sunucunun ağ adresi değişse (ya da o an bulunamasa) bile önceki IP'ler korunur.
    monkeypatch.setattr(sertifika_olustur, "_yerel_ipler", lambda: ["127.0.0.1"])
    assert sertifika_olustur.main(["--klasor", klasor, "--ip", "fd00::1"]) == 0
    assert _san_ipleri(f"{klasor}/sunucu.crt") == {"127.0.0.1", "172.17.1.254", "100.108.27.27", "fd00::1"}
    capsys.readouterr()


def test_ayni_porta_duz_http_https_e_yonlendirilir(tmp_path):
    """2026-10-23: http:// yer imleri HTTPS'e geçince açılmıyordu."""
    import time

    async def uygulama(scope, receive, send):
        assert scope["type"] == "http"
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"tamam"})

    klasor = str(tmp_path)
    sertifika_olustur.olustur(klasor, ["127.0.0.1"], ["localhost"])
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    sunucu_nesnesi = sunucu._Sunucu(sunucu._Ayar(uygulama, host="127.0.0.1", port=port, lifespan="off",
                                                 log_level="warning", ssl_certfile=f"{klasor}/sunucu.crt",
                                                 ssl_keyfile=f"{klasor}/sunucu.key"))
    t = threading.Thread(target=sunucu_nesnesi.run, daemon=True)
    t.start()
    for _ in range(100):
        if sunucu_nesnesi.started:
            break
        time.sleep(0.05)
    try:
        # Düz HTTP -> 302 https://
        with socket.create_connection(("127.0.0.1", port), timeout=5) as ham:
            ham.sendall(f"GET /kayitlar?sayfa=2 HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUser-Agent: test\r\n\r\n".encode())
            yanit = b""
            while b"\r\n\r\n" not in yanit:
                parca = ham.recv(4096)
                if not parca:
                    break
                yanit += parca
        assert yanit.startswith(b"HTTP/1.1 302")
        assert f"Location: https://127.0.0.1:{port}/kayitlar?sayfa=2\r\n".encode() in yanit

        # HTTPS aynen çalışır.
        ctx = ssl.create_default_context(cafile=f"{klasor}/pts-ca.crt")
        with socket.create_connection(("127.0.0.1", port), timeout=5) as ham:
            with ctx.wrap_socket(ham, server_hostname="127.0.0.1") as tls:
                tls.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
                cevap = b""
                while True:
                    parca = tls.recv(4096)
                    if not parca:
                        break
                    cevap += parca
        assert cevap.startswith(b"HTTP/1.1 200") and b"tamam" in cevap
    finally:
        sunucu_nesnesi.should_exit = True
        t.join(10)


def test_http_yonlendirme_yaniti_basliklari_temizler():
    assert sunucu.http_yonlendirme_yaniti(b"\x16\x03\x01...") is None
    yanit = sunucu.http_yonlendirme_yaniti(b"GET http://x/ HTTP/1.1\r\nHost: 172.17.1.254:8787\r\n\r\n")
    assert b"Location: https://172.17.1.254:8787/\r\n" in yanit
    # Başlık enjeksiyonu: geçersiz Host -> yönlendirme yok, 400.
    assert sunucu.http_yonlendirme_yaniti(b"GET / HTTP/1.1\r\nHost: a\x00b\r\n\r\n").startswith(b"HTTP/1.1 400")
