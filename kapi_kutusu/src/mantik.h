// PTS Kapı Kutusu -- donanımdan bağımsız mantık (2026-10-28).
//
// Bu dosyadaki her şey yalnızca standart C++ kullanır: hem ESP32'de hem de
// bilgisayarda (test/test_mantik.cpp, g++) derlenir. Donanım (I2C, ağ, web
// sunucusu) main.cpp'dedir; orada hata ayıklamak zor olduğu için karar veren
// her parça buradadır ve bilgisayarda test edilir.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace kutu {

constexpr int GIRIS_SAYISI = 8;
constexpr int ROLE_SAYISI = 8;

enum class OlayTuru : uint8_t {
  Giris,  // bir girişin kararlı durumu değişti (döngü dedektörü, ışık bariyeri)
  Buton,  // kutuya bağlı görevli düğmesine basıldı (bariyer yerelde açıldı)
  Acma,   // bariyer rölesi çekildi (PTS komutu ya da düğme)
};

struct Olay {
  uint32_t sira = 0;      // açılıştan beri artan numara: sunucu çift kaydı bununla eler
  OlayTuru tur = OlayTuru::Giris;
  uint8_t giris = 0;      // 1..8 (Acma'da röle numarası)
  bool durum = false;     // Giris: true = araç var / sinyal aktif
  uint32_t zaman_ms = 0;  // millis() değeri
  char kaynak = 0;        // Acma: 'p' = PTS komutu, 'b' = düğme
};

// Girişleri titreşimden arındırır: bir giriş ancak `kararlilik_ms` boyunca
// aynı kalırsa yeni durumu kabul edilir. Bit i = giriş i+1, 1 = aktif.
class GirisFiltresi {
 public:
  explicit GirisFiltresi(uint32_t kararlilik_ms = 300) : esik_(kararlilik_ms) {}
  void esikAyarla(uint32_t ms) { esik_ = ms; }
  // İlk okuma: kararlı durumu doğrudan kabul eder (açılışta sahte olay üretmez).
  void baslat(uint8_t ham);
  // Değişen bitleri döndürür; yeni durum kararli()'dadır.
  uint8_t guncelle(uint8_t ham, uint32_t simdi_ms);
  uint8_t kararli() const { return kararli_; }

 private:
  uint32_t esik_;
  uint8_t kararli_ = 0;
  uint8_t aday_ = 0;
  uint32_t aday_zaman_[GIRIS_SAYISI] = {};
  bool basladi_ = false;
};

// Sabit kapasiteli olay kuyruğu. Ağ yokken olaylar burada birikir; dolarsa
// en eskisi atılır ve `dusen()` artar (sunucuya bildirilir).
class OlayKuyrugu {
 public:
  explicit OlayKuyrugu(size_t kapasite = 300) : kapasite_(kapasite) {}
  uint32_t ekle(Olay o, uint32_t simdi_ms);  // sira'yı atar, döndürür
  std::vector<Olay> ilkler(size_t en_fazla) const;
  // Gönderilen ilk `adet` olayı siler; araya düşme girdiyse (kuyruk dolup
  // eskiler atıldıysa) yalnızca sira'sı `son_sira`ya kadar olanları siler.
  void sil(uint32_t son_sira);
  size_t boyut() const { return olaylar_.size(); }
  uint32_t dusen() const { return dusen_; }
  void dusenSifirla() { dusen_ = 0; }

 private:
  size_t kapasite_;
  std::vector<Olay> olaylar_;
  uint32_t sonraki_sira_ = 1;
  uint32_t dusen_ = 0;
};

// Rölelere süreli darbe (bariyer "aç" girişi kısa bir kontak ister).
class RoleDarbe {
 public:
  void baslat(int role, uint32_t sure_ms, uint32_t simdi_ms);  // role: 1..8
  // Şu an çekili olması gereken röleler (bit i = röle i+1).
  uint8_t guncelle(uint32_t simdi_ms);

 private:
  uint32_t bitis_[ROLE_SAYISI] = {};
  uint8_t aktif_ = 0;
};

// Başarısız gönderimden sonra artan bekleme: 1 sn, 2 sn, 4 sn ... en çok 30 sn.
class GeriCekilme {
 public:
  bool hazir(uint32_t simdi_ms) const { return !bekliyor_ || simdi_ms - son_ms_ >= bekleme_ms_; }
  void basarili() { bekliyor_ = false; bekleme_ms_ = 1000; }
  void basarisiz(uint32_t simdi_ms);
  uint32_t bekleme() const { return bekleme_ms_; }

 private:
  bool bekliyor_ = false;
  uint32_t son_ms_ = 0;
  uint32_t bekleme_ms_ = 1000;
};

// PTS'ye gönderilen gövde (bkz. backend/main.py::kapi_kutusu_olay).
std::string olayJson(const std::string& kutu_adi, const std::string& surum, uint32_t acilis,
                     uint32_t simdi_ms, const std::vector<Olay>& olaylar, uint32_t dusen,
                     uint8_t giris_durumu);

std::string jsonKacis(const std::string& s);
std::string htmlKacis(const std::string& s);
// Sabit zamanlı karşılaştırma: anahtarın kaç karakterinin doğru olduğu yanıt
// süresinden anlaşılamasın. Boş beklenen anahtar hiçbir şeyle eşleşmez.
bool anahtarEsit(const std::string& beklenen, const std::string& gelen);
// "http://a:8000/" + "/kapi-kutusu/olay" -> "http://a:8000/kapi-kutusu/olay"
std::string urlBirlestir(const std::string& taban, const std::string& yol);
// application/x-www-form-urlencoded değer çözümü (%XX ve +).
std::string urlCoz(const std::string& s);
// "192.168.1.50" -> true, dört sayı 0..255.
bool ipGecerli(const std::string& s, uint8_t cikti[4] = nullptr);

}  // namespace kutu
