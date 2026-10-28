// PTS Kapı Kutusu -- KC868-A8 yazılımı (2026-10-28).
//
// Görevi:
//   * Yerdeki döngü dedektörünün / ışık bariyerinin sinyalini anında PTS'ye
//     bildirmek ("araç geçti"). Kamera plakayı okuyamazsa PTS bu sinyalden
//     "okunamayan geçiş" kaydı açar (bkz. backend/main.py "KAPI KUTUSU").
//   * PTS'nin "aç" komutuyla bariyer rölesini kısa süre çekmek (kuru kontak).
//   * Görevli düğmesine basılınca bariyeri yerelde açmak (PTS kapalı olsa da).
//   * Ağ yokken olayları biriktirip bağlantı gelince göndermek.
//
// Ayarlar kutunun web sayfasından yapılır: http://<kutu-ip>/
// Karar veren mantık mantik.cpp'dedir ve bilgisayarda test edilir.

#include <Arduino.h>
#include <ETH.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <esp_task_wdt.h>

#include <string>

#include "kart.h"
#include "mantik.h"

#define SURUM "1.0.0"

using kutu::Olay;
using kutu::OlayTuru;

// ------------------------------------------------------------------ ayarlar
struct Ayarlar {
  std::string ad = "Kapi Kutusu";
  std::string pts_url;       // ör. https://192.168.1.10:8000
  std::string anahtar;       // PTS'deki "Kapı Kutuları" ekranının verdiği anahtar
  std::string parola;        // bu sayfanın yönetici parolası (kullanıcı: admin)
  std::string ca;            // PTS kök sertifikası (PEM). Boşsa sertifika doğrulanmaz.
  bool dhcp = true;
  std::string ip, gecit, maske = "255.255.255.0", dns;
  int bariyer_role = 1;      // 1..8
  int darbe_ms = 800;
  int buton_giris = 0;       // 0 = yok, 1..8
  int kararlilik_ms = 300;
  int bildirilen = 0xFF;     // PTS'ye bildirilecek girişler (bit maskesi)
};

static Ayarlar ayar;
static Preferences tercih;

static void ayarlariYukle() {
  tercih.begin("kutu", true);
  auto oku = [](const char* k, const std::string& v) { return std::string(tercih.getString(k, v.c_str()).c_str()); };
  ayar.ad = oku("ad", ayar.ad);
  ayar.pts_url = oku("url", "");
  ayar.anahtar = oku("anahtar", "");
  ayar.parola = oku("parola", "");
  ayar.ca = oku("ca", "");
  ayar.dhcp = tercih.getBool("dhcp", true);
  ayar.ip = oku("ip", "");
  ayar.gecit = oku("gecit", "");
  ayar.maske = oku("maske", ayar.maske);
  ayar.dns = oku("dns", "");
  ayar.bariyer_role = tercih.getInt("brole", 1);
  ayar.darbe_ms = tercih.getInt("darbe", 800);
  ayar.buton_giris = tercih.getInt("buton", 0);
  ayar.kararlilik_ms = tercih.getInt("kararli", 300);
  ayar.bildirilen = tercih.getInt("bildir", 0xFF);
  tercih.end();
}

static void ayarlariKaydet() {
  tercih.begin("kutu", false);
  tercih.putString("ad", ayar.ad.c_str());
  tercih.putString("url", ayar.pts_url.c_str());
  tercih.putString("anahtar", ayar.anahtar.c_str());
  tercih.putString("parola", ayar.parola.c_str());
  tercih.putString("ca", ayar.ca.c_str());
  tercih.putBool("dhcp", ayar.dhcp);
  tercih.putString("ip", ayar.ip.c_str());
  tercih.putString("gecit", ayar.gecit.c_str());
  tercih.putString("maske", ayar.maske.c_str());
  tercih.putString("dns", ayar.dns.c_str());
  tercih.putInt("brole", ayar.bariyer_role);
  tercih.putInt("darbe", ayar.darbe_ms);
  tercih.putInt("buton", ayar.buton_giris);
  tercih.putInt("kararli", ayar.kararlilik_ms);
  tercih.putInt("bildir", ayar.bildirilen);
  tercih.end();
}

// ------------------------------------------------------------------ durum
static SemaphoreHandle_t kilit;  // kuyruk ve aşağıdaki durum alanları
static kutu::OlayKuyrugu kuyruk(300);
static kutu::GirisFiltresi filtre;
static kutu::RoleDarbe darbe;
static kutu::GeriCekilme geri;
static uint32_t acilis_id = 0;
static volatile bool ag_bagli = false;
static uint8_t giris_durumu = 0;
static uint8_t role_durumu = 0;
static uint32_t i2c_hata = 0;
static uint32_t son_basarili_ms = 0;  // 0 = hiç
static std::string son_hata = "henüz gönderilmedi";
static bool yeniden_baslat = false;
static uint32_t yeniden_baslat_ms = 0;

static WebServer sunucu(80);

struct Kilit {
  Kilit() { xSemaphoreTake(kilit, portMAX_DELAY); }
  ~Kilit() { xSemaphoreGive(kilit); }
};

static void olayEkle(Olay o) {
  Kilit k;
  kuyruk.ekle(o, millis());
}

// ------------------------------------------------------------------ G/Ç
static bool girisleriOku(uint8_t& aktif) {
  if (Wire.requestFrom(uint8_t(KART_GIRIS_ADRES), uint8_t(1)) != 1) {
    ++i2c_hata;
    return false;
  }
  const uint8_t ham = Wire.read();
  aktif = KART_GIRIS_TERS ? uint8_t(~ham) : ham;
  return true;
}

static void roleleriYaz(uint8_t aktif) {
  Wire.beginTransmission(uint8_t(KART_ROLE_ADRES));
  Wire.write(KART_ROLE_TERS ? uint8_t(~aktif) : aktif);
  if (Wire.endTransmission() != 0) ++i2c_hata;
}

static void bariyerAc(char kaynak, int role, int sure_ms) {
  if (role < 1 || role > kutu::ROLE_SAYISI) role = ayar.bariyer_role;
  darbe.baslat(role, uint32_t(sure_ms > 0 ? sure_ms : ayar.darbe_ms), millis());
  Olay o;
  o.tur = OlayTuru::Acma;
  o.giris = uint8_t(role);
  o.durum = true;
  o.kaynak = kaynak;
  olayEkle(o);
}

// ------------------------------------------------------------------ ağ
static void agOlayi(WiFiEvent_t olay) {
  switch (olay) {
    case ARDUINO_EVENT_ETH_START: ETH.setHostname("pts-kapi-kutusu"); break;
    case ARDUINO_EVENT_ETH_GOT_IP:
      ag_bagli = true;
      Serial.printf("Ağ hazır: %s\n", ETH.localIP().toString().c_str());
      break;
    case ARDUINO_EVENT_ETH_DISCONNECTED:
    case ARDUINO_EVENT_ETH_STOP: ag_bagli = false; break;
    default: break;
  }
}

static void agiBaslat() {
  WiFi.onEvent(agOlayi);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ETH.begin(ETH_PHY_LAN8720, KART_ETH_PHY_ADDR, KART_ETH_MDC, KART_ETH_MDIO, KART_ETH_POWER, KART_ETH_CLK);
#else
  ETH.begin(KART_ETH_PHY_ADDR, KART_ETH_POWER, KART_ETH_MDC, KART_ETH_MDIO, ETH_PHY_LAN8720, KART_ETH_CLK);
#endif
  uint8_t ip[4], gw[4], mask[4], dns[4];
  if (!ayar.dhcp && kutu::ipGecerli(ayar.ip, ip) && kutu::ipGecerli(ayar.gecit, gw) &&
      kutu::ipGecerli(ayar.maske, mask)) {
    IPAddress d = kutu::ipGecerli(ayar.dns, dns) ? IPAddress(dns[0], dns[1], dns[2], dns[3])
                                                : IPAddress(gw[0], gw[1], gw[2], gw[3]);
    ETH.config(IPAddress(ip[0], ip[1], ip[2], ip[3]), IPAddress(gw[0], gw[1], gw[2], gw[3]),
               IPAddress(mask[0], mask[1], mask[2], mask[3]), d);
  }
}

// Ağ görevi (çekirdek 0): kuyruktaki olayları PTS'ye gönderir; olay yoksa
// 30 sn'de bir boş "kalp atışı" gönderir (PTS kutunun çevrimiçi olduğunu görür).
static void gonderGorevi(void*) {
  uint32_t son_kalp = 0;
  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(50));
    if (!ag_bagli || ayar.pts_url.empty() || ayar.anahtar.empty()) continue;
    const uint32_t simdi = millis();
    std::vector<Olay> paket;
    uint32_t dusen;
    uint8_t girisler;
    {
      Kilit k;
      if (!geri.hazir(simdi)) continue;
      paket = kuyruk.ilkler(20);
      dusen = kuyruk.dusen();
      girisler = giris_durumu;
    }
    if (paket.empty() && son_kalp != 0 && simdi - son_kalp < 30000) continue;

    const std::string govde = kutu::olayJson(ayar.ad, SURUM, acilis_id, simdi, paket, dusen, girisler);
    const std::string url = kutu::urlBirlestir(ayar.pts_url, "/kapi-kutusu/olay");
    HTTPClient http;
    WiFiClient duz;
    WiFiClientSecure guvenli;
    bool basladi;
    if (url.rfind("https://", 0) == 0) {
      if (ayar.ca.empty()) guvenli.setInsecure();  // web sayfası bu durumda uyarı gösterir
      else guvenli.setCACert(ayar.ca.c_str());
      basladi = http.begin(guvenli, url.c_str());
    } else {
      basladi = http.begin(duz, url.c_str());
    }
    int kod = -1;
    if (basladi) {
      http.setTimeout(4000);
      http.addHeader("Content-Type", "application/json");
      http.addHeader("X-Kutu-Anahtar", ayar.anahtar.c_str());
      kod = http.POST(reinterpret_cast<uint8_t*>(const_cast<char*>(govde.data())), govde.size());
      http.end();
    }
    Kilit k;
    if (kod == 200) {
      if (!paket.empty()) kuyruk.sil(paket.back().sira);
      kuyruk.dusenSifirla();
      geri.basarili();
      son_basarili_ms = millis();
      son_kalp = son_basarili_ms;
      son_hata.clear();
    } else {
      geri.basarisiz(millis());
      son_hata = kod == 401 || kod == 403 ? "PTS anahtarı reddetti (HTTP " + std::to_string(kod) + ")"
                 : kod < 0            ? "PTS'ye bağlanılamadı (" + std::string(HTTPClient::errorToString(kod).c_str()) + ")"
                                      : "PTS hata döndü: HTTP " + std::to_string(kod);
    }
  }
}

// ------------------------------------------------------------------ web
static std::string arg(const char* ad) { return std::string(sunucu.arg(ad).c_str()); }

static bool yoneticiMi() {
  if (ayar.parola.empty()) return true;  // ilk kurulum: parola belirlenene kadar açık
  if (sunucu.authenticate("admin", ayar.parola.c_str())) return true;
  sunucu.requestAuthentication(BASIC_AUTH, "PTS Kapi Kutusu");
  return false;
}

static bool anahtarDogru() {
  std::string gelen = std::string(sunucu.header("X-Kutu-Anahtar").c_str());
  if (gelen.empty()) gelen = arg("anahtar");
  return kutu::anahtarEsit(ayar.anahtar, gelen);
}

static std::string secenekler(int secili, int bas, int son, const char* sifir_adi) {
  std::string s;
  for (int i = bas; i <= son; ++i) {
    s += "<option value=\"" + std::to_string(i) + "\"" + (i == secili ? " selected" : "") + ">" +
         (i == 0 && sifir_adi ? sifir_adi : std::to_string(i)) + "</option>";
  }
  return s;
}

static void anaSayfa() {
  if (!yoneticiMi()) return;
  uint8_t gd, rd;
  size_t kb;
  uint32_t dus, sb;
  std::string hata;
  {
    Kilit k;
    gd = giris_durumu;
    rd = role_durumu;
    kb = kuyruk.boyut();
    dus = kuyruk.dusen();
    sb = son_basarili_ms;
    hata = son_hata;
  }
  const auto h = kutu::htmlKacis;
  std::string p;
  p.reserve(9000);
  p += "<!doctype html><html lang=tr><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
       "<title>PTS Kapı Kutusu</title><style>body{font-family:system-ui,sans-serif;max-width:760px;margin:16px auto;padding:0 12px;color:#1b2433}"
       "h1{font-size:22px}fieldset{border:1px solid #dfe3ea;border-radius:10px;margin:12px 0;padding:10px 14px}"
       "label{display:block;margin:8px 0 2px;font-size:14px}input,select,textarea{width:100%;box-sizing:border-box;padding:7px;font-size:15px}"
       "input[type=checkbox]{width:auto}.g{display:inline-block;width:38px;text-align:center;padding:6px 0;margin:2px;border-radius:6px;background:#eceef2}"
       ".a{background:#12805c;color:#fff}.u{background:#fff4d6;border:1px solid #f3c552;padding:8px;border-radius:8px}"
       ".h{color:#c8102e}button{padding:9px 16px;font-size:15px;margin-top:10px}small{color:#667085}</style></head><body>";
  p += "<h1>PTS Kapı Kutusu <small>" + h(ayar.ad) + " · v" SURUM " · " KART_ADI "</small></h1>";
  if (ayar.parola.empty()) p += "<p class=u>İlk kurulum: bu sayfa şu an parolasız. Aşağıdan bir yönetici parolası belirleyin.</p>";
  if (ayar.pts_url.rfind("https://", 0) == 0 && ayar.ca.empty())
    p += "<p class=u>PTS sertifikası girilmedi: bağlantı şifreli ama sunucunun kimliği doğrulanmıyor. "
         "PTS'nin <b>/pts-ca.crt</b> dosyasının içeriğini aşağıya yapıştırın.</p>";

  p += "<fieldset><legend>Durum</legend>";
  p += "Ağ: " + std::string(ag_bagli ? "bağlı, " + std::string(ETH.localIP().toString().c_str()) : "<b class=h>bağlı değil</b>");
  p += " · MAC " + std::string(ETH.macAddress().c_str()) + " · açık kalma " + std::to_string(millis() / 60000) + " dk<br>";
  p += "PTS: ";
  if (ayar.pts_url.empty() || ayar.anahtar.empty()) p += "<b class=h>adres ya da anahtar girilmedi</b>";
  else if (hata.empty()) p += "bağlı (son başarılı gönderim " + std::to_string((millis() - sb) / 1000) + " sn önce)";
  else p += "<b class=h>" + h(hata) + "</b>";
  p += "<br>Bekleyen olay: " + std::to_string(kb) + (dus ? " · <b class=h>" + std::to_string(dus) + " olay sığmadığı için atıldı</b>" : "");
  p += " · I2C hatası: " + std::to_string(i2c_hata) + "<br>Girişler: ";
  for (int i = 0; i < 8; ++i) p += std::string("<span class='g") + ((gd >> i) & 1 ? " a" : "") + "'>" + std::to_string(i + 1) + "</span>";
  p += "<br>Röleler: ";
  for (int i = 0; i < 8; ++i) p += std::string("<span class='g") + ((rd >> i) & 1 ? " a" : "") + "'>" + std::to_string(i + 1) + "</span>";
  p += "<form method=post action=/test-ac><button>Bariyeri şimdi aç (deneme)</button></form></fieldset>";

  p += "<form method=post action=/ayar><fieldset><legend>PTS bağlantısı</legend>";
  p += "<label>Kutu adı</label><input name=ad maxlength=60 value=\"" + h(ayar.ad) + "\">";
  p += "<label>PTS adresi</label><input name=url placeholder='https://192.168.1.10:8000' value=\"" + h(ayar.pts_url) + "\">";
  p += "<label>Kutu anahtarı <small>(PTS → Bariyer → Kapı Kutuları ekranından)</small></label><input name=anahtar autocomplete=off value=\"" + h(ayar.anahtar) + "\">";
  p += "<label>PTS kök sertifikası (PEM, isteğe bağlı)</label><textarea name=ca rows=4 placeholder='-----BEGIN CERTIFICATE-----'>" + h(ayar.ca) + "</textarea></fieldset>";

  p += "<fieldset><legend>Bariyer ve girişler</legend>";
  p += "<label>Bariyer rölesi</label><select name=brole>" + secenekler(ayar.bariyer_role, 1, 8, nullptr) + "</select>";
  p += "<label>Röle çekme süresi (ms)</label><input name=darbe type=number min=100 max=10000 value=" + std::to_string(ayar.darbe_ms) + ">";
  p += "<label>Görevli düğmesi girişi</label><select name=buton>" + secenekler(ayar.buton_giris, 0, 8, "yok") + "</select>";
  p += "<label>Kararlılık süresi (ms) <small>sinyal bu kadar sürmezse sayılmaz</small></label><input name=kararli type=number min=20 max=5000 value=" + std::to_string(ayar.kararlilik_ms) + ">";
  p += "<label>PTS'ye bildirilecek girişler</label>";
  for (int i = 0; i < 8; ++i)
    p += "<label style='display:inline-block;margin-right:12px'><input type=checkbox name=b" + std::to_string(i + 1) +
         ((ayar.bildirilen >> i) & 1 ? " checked" : "") + "> " + std::to_string(i + 1) + "</label>";
  p += "</fieldset><fieldset><legend>Ağ</legend>";
  p += std::string("<label><input type=checkbox name=dhcp") + (ayar.dhcp ? " checked" : "") + "> Adresi otomatik al (DHCP)</label>";
  p += "<label>Sabit IP</label><input name=ip value=\"" + h(ayar.ip) + "\">";
  p += "<label>Ağ geçidi</label><input name=gecit value=\"" + h(ayar.gecit) + "\">";
  p += "<label>Alt ağ maskesi</label><input name=maske value=\"" + h(ayar.maske) + "\">";
  p += "<label>DNS</label><input name=dns value=\"" + h(ayar.dns) + "\"></fieldset>";
  p += "<fieldset><legend>Bu sayfanın parolası (kullanıcı: admin)</legend><label>Yeni parola <small>(değiştirmeyecekseniz boş bırakın)</small></label>"
       "<input name=parola type=password autocomplete=new-password minlength=8></fieldset>";
  p += "<button>Kaydet ve yeniden başlat</button></form>";
  p += "<form method=post action=/sifirla onsubmit=\"return confirm('Tüm ayarlar silinsin mi?')\"><button>Fabrika ayarlarına dön</button></form></body></html>";
  sunucu.send(200, "text/html; charset=utf-8", p.c_str());
}

static void ayarKaydet() {
  if (!yoneticiMi()) return;
  Ayarlar y = ayar;
  y.ad = arg("ad").substr(0, 60);
  y.pts_url = arg("url");
  y.anahtar = arg("anahtar");
  y.ca = arg("ca");
  y.dhcp = sunucu.hasArg("dhcp");
  y.ip = arg("ip");
  y.gecit = arg("gecit");
  y.maske = arg("maske");
  y.dns = arg("dns");
  y.bariyer_role = constrain(sunucu.arg("brole").toInt(), 1, 8);
  y.darbe_ms = constrain(sunucu.arg("darbe").toInt(), 100, 10000);
  y.buton_giris = constrain(sunucu.arg("buton").toInt(), 0, 8);
  y.kararlilik_ms = constrain(sunucu.arg("kararli").toInt(), 20, 5000);
  y.bildirilen = 0;
  for (int i = 0; i < 8; ++i) if (sunucu.hasArg(("b" + std::to_string(i + 1)).c_str())) y.bildirilen |= 1 << i;
  const std::string yeni_parola = arg("parola");
  std::string hata;
  if (!y.pts_url.empty() && y.pts_url.rfind("http://", 0) != 0 && y.pts_url.rfind("https://", 0) != 0)
    hata = "PTS adresi http:// ya da https:// ile başlamalı.";
  else if (!y.dhcp && !(kutu::ipGecerli(y.ip) && kutu::ipGecerli(y.gecit) && kutu::ipGecerli(y.maske)))
    hata = "Sabit IP için IP, ağ geçidi ve maske geçerli olmalı.";
  else if (!yeni_parola.empty() && yeni_parola.size() < 8)
    hata = "Parola en az 8 karakter olmalı.";
  else if (ayar.parola.empty() && yeni_parola.empty())
    hata = "İlk kurulumda bir yönetici parolası belirleyin.";
  if (!hata.empty()) {
    sunucu.send(400, "text/html; charset=utf-8", ("<meta charset=utf-8><p>" + kutu::htmlKacis(hata) + "</p><a href=/>Geri</a>").c_str());
    return;
  }
  if (!yeni_parola.empty()) y.parola = yeni_parola;
  ayar = y;
  ayarlariKaydet();
  sunucu.send(200, "text/html; charset=utf-8",
              "<meta charset=utf-8><meta http-equiv=refresh content='8;url=/'><p>Kaydedildi. Kutu yeniden başlıyor…</p>");
  yeniden_baslat = true;
  yeniden_baslat_ms = millis();
}

// PTS (Bariyer ayarlarında "HTTP" modu) bariyeri açtırmak için bunu çağırır:
//   POST (ya da GET) http://<kutu-ip>/ac?anahtar=<anahtar>[&role=1][&ms=800]
static void acKomutu() {
  if (ayar.anahtar.empty()) { sunucu.send(403, "application/json", "{\"ok\":false,\"hata\":\"anahtar ayarlanmadi\"}"); return; }
  if (!anahtarDogru()) { sunucu.send(401, "application/json", "{\"ok\":false,\"hata\":\"anahtar yanlis\"}"); return; }
  const int role = sunucu.hasArg("role") ? sunucu.arg("role").toInt() : ayar.bariyer_role;
  const int ms = sunucu.hasArg("ms") ? constrain(sunucu.arg("ms").toInt(), 100, 10000) : ayar.darbe_ms;
  bariyerAc('p', role, ms);
  sunucu.send(200, "application/json", "{\"ok\":true}");
}

static void durumJson() {
  if (!anahtarDogru() && !(ayar.parola.empty() || sunucu.authenticate("admin", ayar.parola.c_str()))) {
    sunucu.send(401, "application/json", "{\"ok\":false}");
    return;
  }
  char b[256];
  Kilit k;
  snprintf(b, sizeof b,
           "{\"ok\":true,\"surum\":\"" SURUM "\",\"girisler\":%u,\"roleler\":%u,\"bekleyen\":%u,\"dusen\":%lu,"
           "\"i2c_hata\":%lu,\"calisma_ms\":%lu,\"pts_hata\":\"%s\"}",
           unsigned(giris_durumu), unsigned(role_durumu), unsigned(kuyruk.boyut()), (unsigned long)kuyruk.dusen(),
           (unsigned long)i2c_hata, (unsigned long)millis(), kutu::jsonKacis(son_hata).c_str());
  sunucu.send(200, "application/json", b);
}

static void webiBaslat() {
  static const char* basliklar[] = {"X-Kutu-Anahtar"};
  sunucu.collectHeaders(basliklar, 1);
  sunucu.on("/", HTTP_GET, anaSayfa);
  sunucu.on("/ayar", HTTP_POST, ayarKaydet);
  sunucu.on("/ac", HTTP_ANY, acKomutu);  // PTS bariyer ayarındaki metot GET de olabilir
  sunucu.on("/durum", HTTP_GET, durumJson);
  sunucu.on("/test-ac", HTTP_POST, [] {
    if (!yoneticiMi()) return;
    bariyerAc('b', ayar.bariyer_role, ayar.darbe_ms);
    sunucu.sendHeader("Location", "/");
    sunucu.send(303);
  });
  sunucu.on("/sifirla", HTTP_POST, [] {
    if (!yoneticiMi()) return;
    tercih.begin("kutu", false);
    tercih.clear();
    tercih.end();
    sunucu.send(200, "text/html; charset=utf-8", "<meta charset=utf-8><p>Ayarlar silindi, kutu yeniden başlıyor.</p>");
    yeniden_baslat = true;
    yeniden_baslat_ms = millis();
  });
  sunucu.onNotFound([] { sunucu.send(404, "text/plain", "Bulunamadi"); });
  sunucu.begin();
}

// ------------------------------------------------------------------ seri komutlar
static void seriKomut() {
  static std::string satir;
  while (Serial.available()) {
    const char c = char(Serial.read());
    if (c != '\n' && c != '\r') { if (satir.size() < 40) satir += c; continue; }
    if (satir == "SIFIRLA") {
      tercih.begin("kutu", false);
      tercih.clear();
      tercih.end();
      Serial.println("Ayarlar silindi, yeniden başlıyor.");
      delay(200);
      ESP.restart();
    } else if (satir == "DURUM") {
      Serial.printf("IP %s, girişler %02X, röleler %02X, bekleyen %u, hata: %s\n",
                    ETH.localIP().toString().c_str(), giris_durumu, role_durumu, unsigned(kuyruk.boyut()), son_hata.c_str());
    } else if (!satir.empty()) {
      Serial.println("Komutlar: DURUM, SIFIRLA");
    }
    satir.clear();
  }
}

// ------------------------------------------------------------------ ana döngü
void setup() {
  Serial.begin(115200);
  Wire.begin(KART_I2C_SDA, KART_I2C_SCL);
  roleleriYaz(0);  // açılışta tüm röleler bırakılmış olsun
  kilit = xSemaphoreCreateMutex();
  acilis_id = esp_random();
  ayarlariYukle();
  filtre.esikAyarla(uint32_t(ayar.kararlilik_ms));
  uint8_t ilk = 0;
  if (girisleriOku(ilk)) filtre.baslat(ilk);
  giris_durumu = filtre.kararli();
  Serial.printf("PTS Kapı Kutusu v%s (%s)\n", SURUM, KART_ADI);
  agiBaslat();
  webiBaslat();
  xTaskCreatePinnedToCore(gonderGorevi, "gonder", 12288, nullptr, 1, nullptr, 0);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  esp_task_wdt_config_t wdt = {.timeout_ms = 15000, .idle_core_mask = 0, .trigger_panic = true};
  esp_task_wdt_reconfigure(&wdt);
#else
  esp_task_wdt_init(15, true);
#endif
  esp_task_wdt_add(nullptr);
}

void loop() {
  esp_task_wdt_reset();
  sunucu.handleClient();
  seriKomut();

  static uint32_t son_okuma = 0;
  const uint32_t simdi = millis();
  if (simdi - son_okuma >= 10) {
    son_okuma = simdi;
    uint8_t ham;
    if (girisleriOku(ham)) {
      const uint8_t degisen = filtre.guncelle(ham, simdi);
      const uint8_t kararli = filtre.kararli();
      {
        Kilit k;
        giris_durumu = kararli;
      }
      for (int i = 0; i < kutu::GIRIS_SAYISI; ++i) {
        if (!((degisen >> i) & 1)) continue;
        const bool aktif = (kararli >> i) & 1;
        if (i + 1 == ayar.buton_giris) {
          if (aktif) {
            Olay o;
            o.tur = OlayTuru::Buton;
            o.giris = uint8_t(i + 1);
            o.durum = true;
            olayEkle(o);
            bariyerAc('b', ayar.bariyer_role, ayar.darbe_ms);
          }
          continue;
        }
        if (!((ayar.bildirilen >> i) & 1)) continue;
        Olay o;
        o.tur = OlayTuru::Giris;
        o.giris = uint8_t(i + 1);
        o.durum = aktif;
        olayEkle(o);
      }
    }
  }

  const uint8_t roleler = darbe.guncelle(millis());
  if (roleler != role_durumu) {
    roleleriYaz(roleler);
    Kilit k;
    role_durumu = roleler;
  }

  if (yeniden_baslat && millis() - yeniden_baslat_ms > 800) ESP.restart();
  delay(1);
}
