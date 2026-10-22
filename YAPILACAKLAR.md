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
- [ ] Derlenmiş müşteri kurulumunu (Actions "PTS-Kurulum") boş bir Windows'ta uçtan uca dene:
  kurulum, SYSTEM zamanlanmış görevi, klasör izinleri, lisans etkinleştirme.
- [ ] Yönetici oturum süresi: "kullandıkça uzasın" mı, süre uzatma mı? (karar bekleniyor)
- [ ] Güvenlik: `guvenlik_duvari.ps1 -EkIpler "<Tailscale IP'leri>"` uygulandı mı;
  SQL Server 1433 kuralı kapatıldı mı; Telegram bot anahtarı iptal edildi mi.
- [ ] **Güvenlik görevlisinin kayıt görünürlüğü** (karar bekleniyor, 2026-10-23):
  görevli yalnız giriş yaptığı andan sonraki geçişleri görüyor (23:28'de giren
  23:00-23:28 arasını göremiyor). Öneri: vardiya çizelgesindeki başlangıçtan itibaren göster.
- [ ] **SQL Server 1433** tüm ağ arayüzlerinde dinliyor; PTS aynı bilgisayardaysa
  yalnız 127.0.0.1'de dinlemesi yeterli (karar bekleniyor, 2026-10-23).
- [ ] **KVKK saklama süresini** kurum belirleyip Sistem ayarlarına girmeli
  (`kayit_anonimlestirme_gun`, şu an 0 = kapalı).
- [ ] **Ürünleştirme** (2026-10-23, altyapı hazır ve kapalı -- bkz. URUNLESTIRME.md):
  satıştan önce hukuki kontrol listesi (yazılım sahipliği FSEK md.18, YOLOv9 model
  lisansı, KVKK sözleşmeleri); sonra ilk açılış sihirbazı ve kapalı modül sekmelerinin
  gizlenmesi.
- [ ] Huidu tabela yazma süresi (~0,8 sn): iki bölgeyi tek bağlantıda gönderme --
  canlı panelde deneme gerektirir, kullanıcı onayıyla.
