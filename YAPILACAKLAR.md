# Yapılacaklar (hatırlatma listesi)

Kullanıcı "ne kaldı" diye sorduğunda bu liste hatırlatılır.

## Bekleyen
- [ ] **Kendi sisteminin lisansını yeni imzalı (PTS2) lisansa geçir** (2026-10-20).
  Kendi sistem (kaynak koddan çalışan, `pts_sistemi`) şimdilik eski PTS1/HMAC
  lisansı kabul ediyor (`backend/lisans.py::ESKI_LISANS_KABUL = True`).
  Yapılacak: `araclar/lisans_araci.py uret ...` ile kendi cihaz koduna PTS2 lisans
  üret → panelden etkinleştir → `ESKI_LISANS_KABUL = False` yap → `.env`'deki
  `PTS_LICENSE_SECRET` artık gereksiz. (Müşteriye giden derlenmiş pakette bu
  zaten kapalı.)
- [ ] Lisans verenin açık anahtarını `backend/lisans.py::ACIK_ANAHTAR_HEX`'e yaz
  (kullanıcı `araclar/lisans_araci.py anahtar-olustur` çıktısını gönderecek);
  sonra `[derle]` ile müşteri paketini derle.
- [ ] Yönetici oturum süresi: "kullandıkça uzasın" mı, süre uzatma mı? (karar bekleniyor)
- [ ] Güvenlik: `guvenlik_duvari.ps1 -EkIpler "<Tailscale IP'leri>"` uygulandı mı;
  SQL Server 1433 kuralı kapatıldı mı; Telegram bot anahtarı iptal edildi mi.
- [ ] Huidu tabela yazma süresi (~0,8 sn): iki bölgeyi tek bağlantıda gönderme --
  canlı panelde deneme gerektirir, kullanıcı onayıyla.
- [ ] Panel arayüzü Bootstrap/Chart.js'i internetten (CDN) yüklüyor; internetsiz
  müşteri kurulumunda arayüz bozulur -- kütüphaneleri pakete gömmek.
