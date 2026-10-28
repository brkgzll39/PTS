// Kapı Kutusu mantığının bilgisayarda çalışan testleri.
//   g++ -std=c++17 -Wall -Wextra -Werror -I src test/test_mantik.cpp src/mantik.cpp -o /tmp/t && /tmp/t
#include <cassert>
#include <cstdio>
#include <string>

#include "mantik.h"

using namespace kutu;

static int basarili = 0;
#define KONTROL(x)                                                       \
  do {                                                                   \
    if (!(x)) {                                                          \
      std::fprintf(stderr, "BAŞARISIZ %s:%d: %s\n", __FILE__, __LINE__, #x); \
      return 1;                                                          \
    }                                                                    \
    ++basarili;                                                          \
  } while (0)

static int filtre() {
  GirisFiltresi f(300);
  KONTROL(f.guncelle(0b0001, 0) == 0);  // ilk okuma: olay yok, durum kabul
  KONTROL(f.kararli() == 0b0001);
  // 100 ms süren titreşim kabul edilmez
  KONTROL(f.guncelle(0b0011, 1000) == 0);
  KONTROL(f.guncelle(0b0001, 1100) == 0);
  KONTROL(f.guncelle(0b0001, 1500) == 0);
  KONTROL(f.kararli() == 0b0001);
  // 300 ms kararlı kalan değişiklik kabul edilir
  KONTROL(f.guncelle(0b0011, 2000) == 0);
  KONTROL(f.guncelle(0b0011, 2299) == 0);
  KONTROL(f.guncelle(0b0011, 2300) == 0b0010);
  KONTROL(f.kararli() == 0b0011);
  // millis() taşması
  GirisFiltresi t(300);
  t.baslat(0);
  KONTROL(t.guncelle(0b1000'0000, 0xFFFFFF00u) == 0);
  KONTROL(t.guncelle(0b1000'0000, 0x00000050u) == 0b1000'0000);
  return 0;
}

static int kuyruk() {
  OlayKuyrugu k(3);
  Olay o;
  o.giris = 1;
  KONTROL(k.ekle(o, 10) == 1);
  KONTROL(k.ekle(o, 20) == 2);
  KONTROL(k.ekle(o, 30) == 3);
  KONTROL(k.ekle(o, 40) == 4);  // dolu: en eski (1) atılır
  KONTROL(k.boyut() == 3 && k.dusen() == 1);
  auto ilk = k.ilkler(2);
  KONTROL(ilk.size() == 2 && ilk[0].sira == 2 && ilk[1].sira == 3 && ilk[0].zaman_ms == 20);
  // Gönderim sırasında yeni olay geldi: yalnızca gönderilenler silinir
  k.ekle(o, 50);
  k.sil(3);
  KONTROL(k.boyut() == 2 && k.ilkler(5)[0].sira == 4);
  k.sil(100);
  KONTROL(k.boyut() == 0);
  return 0;
}

static int role() {
  RoleDarbe r;
  r.baslat(1, 800, 1000);
  r.baslat(3, 200, 1000);
  KONTROL(r.guncelle(1100) == 0b101);
  KONTROL(r.guncelle(1200) == 0b001);
  KONTROL(r.guncelle(1799) == 0b001);
  KONTROL(r.guncelle(1800) == 0);
  r.baslat(9, 100, 0);  // geçersiz röle yok sayılır
  r.baslat(0, 100, 0);
  KONTROL(r.guncelle(0) == 0);
  r.baslat(8, 500, 0xFFFFFF00u);  // taşma
  KONTROL(r.guncelle(0x00000010u) == 0x80);
  KONTROL(r.guncelle(0x00000200u) == 0);
  return 0;
}

static int geri_cekilme() {
  GeriCekilme g;
  KONTROL(g.hazir(0));
  g.basarisiz(0);
  KONTROL(!g.hazir(999) && g.hazir(1000));
  g.basarisiz(1000);
  KONTROL(g.bekleme() == 2000 && !g.hazir(2999) && g.hazir(3000));
  for (int i = 0; i < 10; ++i) g.basarisiz(5000);
  KONTROL(g.bekleme() == 30000);
  g.basarili();
  KONTROL(g.hazir(5001) && g.bekleme() == 1000);
  return 0;
}

static int json() {
  std::vector<Olay> v(2);
  v[0].sira = 7; v[0].giris = 2; v[0].durum = true; v[0].zaman_ms = 900;
  v[1].sira = 8; v[1].tur = OlayTuru::Acma; v[1].giris = 1; v[1].kaynak = 'b'; v[1].zaman_ms = 950;
  const std::string j = olayJson("Ana \"Kapı\"", "1.0.0", 42, 1000, v, 3, 0b10);
  KONTROL(j == "{\"kutu\":\"Ana \\\"Kapı\\\"\",\"surum\":\"1.0.0\",\"acilis\":42,\"calisma_ms\":1000,"
               "\"dusen\":3,\"girisler\":2,\"olaylar\":[{\"sira\":7,\"tur\":\"giris\",\"giris\":2,"
               "\"durum\":\"var\",\"once_ms\":100},{\"sira\":8,\"tur\":\"acma\",\"giris\":1,\"durum\":"
               "\"yok\",\"once_ms\":50,\"kaynak\":\"buton\"}]}");
  KONTROL(olayJson("k", "1", 1, 5, {}, 0, 0).find("\"olaylar\":[]") != std::string::npos);
  KONTROL(jsonKacis(std::string("a\nb\x01", 4)) == "a\\nb\\u0001");
  return 0;
}

static int yardimcilar() {
  KONTROL(htmlKacis("<a href=\"x\">'&") == "&lt;a href=&quot;x&quot;&gt;&#39;&amp;");
  KONTROL(anahtarEsit("abc123", "abc123"));
  KONTROL(!anahtarEsit("abc123", "abc124"));
  KONTROL(!anahtarEsit("abc123", "abc12"));
  KONTROL(!anahtarEsit("abc123", "abc1234"));
  KONTROL(!anahtarEsit("", ""));
  KONTROL(urlBirlestir("https://10.0.0.5:8000/", "/kapi-kutusu/olay") == "https://10.0.0.5:8000/kapi-kutusu/olay");
  KONTROL(urlBirlestir("http://a", "b") == "http://a/b");
  KONTROL(urlCoz("a+b%2Fc%3d%") == "a b/c=%");
  KONTROL(urlCoz("%zz") == "%zz");
  uint8_t ip[4];
  KONTROL(ipGecerli("192.168.1.50", ip) && ip[0] == 192 && ip[3] == 50);
  KONTROL(!ipGecerli("192.168.1"));
  KONTROL(!ipGecerli("192.168.1.256"));
  KONTROL(!ipGecerli("1..2.3"));
  KONTROL(!ipGecerli("a.b.c.d"));
  KONTROL(!ipGecerli("1.2.3.4.5"));
  return 0;
}

int main() {
  if (filtre() || kuyruk() || role() || geri_cekilme() || json() || yardimcilar()) return 1;
  std::printf("Tüm testler geçti (%d kontrol)\n", basarili);
  return 0;
}
