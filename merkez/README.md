# PTS Merkezi İzleme

Tüm müşteri kurulumlarını tek ekrandan izlemek için küçük, ayrı bir sunucu.
Her PTS kurulumu birkaç dakikada bir **sağlık özetini** buraya gönderir; pano
hangi kurulumun çalıştığını, hangi kameranın sustuğunu, diskin dolduğunu,
yedeğin alınmadığını, lisansın ya da bakım sözleşmesinin bittiğini gösterir.
Sorun çıkınca (ve düzelince) Telegram ya da e-postayla haber verir.

**Kişisel veri gelmez.** Özette plaka, kişi adı, fotoğraf, geçiş kaydı yoktur;
yalnız sayılar ve durumlar vardır. Müşteri PTS'inde *Sistem → Merkezi İzleme →
"Gönderilen veri"* ile gidenin tamamını görebilir. Merkez yine de
bilinen kişisel veri alanlarını kaydetmeden siler.

Bağlantıyı hep müşterideki PTS başlatır (dışarı giden HTTPS). Müşterinin
güvenlik duvarında port açmaya gerek yoktur; yalnız merkezin adresine çıkış izni
gerekir.

## Neler izlenir

| Durum | Ne zaman |
|---|---|
| 🟣 Çevrimdışı | 15 dakikadır (ya da 3 gönderim aralığıdır) haber yok |
| 🔴 Kritik | kameradan görüntü gelmiyor · disk %95 · son yedek 3+ gün önce · lisans aktif değil ya da ≤7 gün · veritabanı hatası |
| 🟠 Uyarı | kameranın plaka okuma bağlantısı kopuk · gece mutabakatında yakalama < %90 · sessiz kamera · bildirimler gitmiyor · disk %85 · yedek 36+ saat · lisans ≤30 gün · son 24 saatte sunucu kesintisi · HTTPS sertifikası ≤14 gün · bakım sözleşmesi ≤30 gün ya da bitmiş |

Eşikler `merkez/sorunlar.py` başında. Bir sorun 10 dakika sürerse bildirilir
(`MERKEZ_BILDIRIM_BEKLEME_SN`), aynı sorun düzelene kadar tekrar bildirilmez;
düzelince "✅ Düzeldi" mesajı gelir.

## VPS'e kurulum (Ubuntu 22.04/24.04)

En küçük VPS yeter (1 vCPU, 1 GB RAM). Bir alan adı ya da alt alan adı
(ör. `izleme.firmaniz.com.tr`) VPS'in IP adresini göstermeli.

```bash
sudo adduser --system --group --home /opt/pts-merkez ptsmerkez
sudo apt install -y python3-venv git caddy
sudo -u ptsmerkez bash -c '
  cd /opt/pts-merkez
  git clone --depth 1 <PTS deposu> kaynak && cp -r kaynak/merkez . && rm -rf kaynak
  python3 -m venv .venv && .venv/bin/pip install -r merkez/requirements.txt
  mkdir -p veri && cp merkez/merkez.env.ornek merkez.env && chmod 600 merkez.env'
sudo nano /opt/pts-merkez/merkez.env          # parola, Telegram bilgileri
sudo cp /opt/pts-merkez/merkez/pts-merkez.service /etc/systemd/system/
sudo systemctl enable --now pts-merkez
# HTTPS: Caddy sertifikayı kendisi alır
sudo cp /opt/pts-merkez/merkez/Caddyfile.ornek /etc/caddy/Caddyfile   # alan adını düzeltin
sudo systemctl reload caddy
```

Tarayıcıda `https://izleme.firmaniz.com.tr` → kullanıcı `yonetici`, parola
`merkez.env`'deki. Aynı adresten 10 hatalı denemede 15 dakika kilitlenir.

Telegram sohbet kimliği: bota bir mesaj yazın, sonra
`https://api.telegram.org/bot<TOKEN>/getUpdates` adresinde `"chat":{"id":…}`
değerini alın. Panodaki **Bildirimi dene** düğmesi ayarı sınar.

Yedek: tek dosya, `veri/merkez.db`.

## Yeni müşteri bağlama

1. Panoda **+ Kurulum ekle** → ad, iletişim, bakım sözleşmesi bitişi → anahtar üretilir
   (yalnız bir kez gösterilir; kaybolursa *Anahtarı yenile*).
2. Müşterinin PTS'inde yönetici olarak: **Sistem → Merkezi İzleme** → *Gönderim açık*,
   adres `https://izleme.firmaniz.com.tr`, anahtar → **Kaydet ve gönder**.
3. Birkaç saniye içinde panoda görünür.

Kurulum betiğiyle ayarlamak için PTS'in `.env` dosyasına `PTS_MERKEZ_URL` ve
`PTS_MERKEZ_ANAHTARI` de yazılabilir (paneldeki ayar varsa o geçerlidir).

Kurumsal ağlarda (TPAO gibi) PTS sunucusunun merkez adresine HTTPS (443) çıkışına
izin verilmesi gerekebilir; PTS'teki kart "merkeze ulaşılamadı" diyorsa bilgi
işlemden bu izni isteyin.

## Yerelde deneme

```bash
pip install -r merkez/requirements.txt
MERKEZ_YONETICI_PAROLA=deneme-parolasi uvicorn merkez.uygulama:app --port 8100
```

PTS'te adres olarak `http://127.0.0.1:8100` girilebilir (yerel ağ adreslerinde
http kabul edilir; internet üzerinden yalnız https).
