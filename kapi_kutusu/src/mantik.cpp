#include "mantik.h"

#include <cstdio>

namespace kutu {

void GirisFiltresi::baslat(uint8_t ham) {
  kararli_ = aday_ = ham;
  basladi_ = true;
}

uint8_t GirisFiltresi::guncelle(uint8_t ham, uint32_t simdi_ms) {
  if (!basladi_) {
    baslat(ham);
    return 0;
  }
  uint8_t degisen = 0;
  for (int i = 0; i < GIRIS_SAYISI; ++i) {
    const uint8_t bit = 1u << i;
    const bool h = ham & bit;
    if (h == bool(kararli_ & bit)) {
      // Kararlı durumla aynı: yarım kalan bir değişiklik adayı varsa iptal.
      aday_ = (aday_ & ~bit) | (kararli_ & bit);
      continue;
    }
    if (h != bool(aday_ & bit)) {
      aday_ = h ? (aday_ | bit) : (aday_ & ~bit);
      aday_zaman_[i] = simdi_ms;
    }
    if (simdi_ms - aday_zaman_[i] >= esik_) {  // millis() taşmasında da doğru
      kararli_ = h ? (kararli_ | bit) : (kararli_ & ~bit);
      degisen |= bit;
    }
  }
  return degisen;
}

uint32_t OlayKuyrugu::ekle(Olay o, uint32_t simdi_ms) {
  o.sira = sonraki_sira_++;
  if (o.zaman_ms == 0) o.zaman_ms = simdi_ms;
  if (olaylar_.size() >= kapasite_) {
    olaylar_.erase(olaylar_.begin());
    ++dusen_;
  }
  olaylar_.push_back(o);
  return o.sira;
}

std::vector<Olay> OlayKuyrugu::ilkler(size_t en_fazla) const {
  const size_t n = olaylar_.size() < en_fazla ? olaylar_.size() : en_fazla;
  return std::vector<Olay>(olaylar_.begin(), olaylar_.begin() + n);
}

void OlayKuyrugu::sil(uint32_t son_sira) {
  size_t n = 0;
  while (n < olaylar_.size() && olaylar_[n].sira <= son_sira) ++n;
  olaylar_.erase(olaylar_.begin(), olaylar_.begin() + n);
}

void RoleDarbe::baslat(int role, uint32_t sure_ms, uint32_t simdi_ms) {
  if (role < 1 || role > ROLE_SAYISI || sure_ms == 0) return;
  bitis_[role - 1] = simdi_ms + sure_ms;
  aktif_ |= 1u << (role - 1);
}

uint8_t RoleDarbe::guncelle(uint32_t simdi_ms) {
  for (int i = 0; i < ROLE_SAYISI; ++i) {
    const uint8_t bit = 1u << i;
    // (int32_t) farkı: millis() 49 günde bir taştığında da doğru çalışır.
    if ((aktif_ & bit) && int32_t(simdi_ms - bitis_[i]) >= 0) aktif_ &= ~bit;
  }
  return aktif_;
}

void GeriCekilme::basarisiz(uint32_t simdi_ms) {
  if (bekliyor_) bekleme_ms_ = bekleme_ms_ * 2 > 30000 ? 30000 : bekleme_ms_ * 2;
  bekliyor_ = true;
  son_ms_ = simdi_ms;
}

std::string jsonKacis(const std::string& s) {
  std::string c;
  c.reserve(s.size() + 2);
  for (unsigned char ch : s) {
    switch (ch) {
      case '"': c += "\\\""; break;
      case '\\': c += "\\\\"; break;
      case '\n': c += "\\n"; break;
      case '\r': c += "\\r"; break;
      case '\t': c += "\\t"; break;
      default:
        if (ch < 0x20) {
          char b[8];
          snprintf(b, sizeof b, "\\u%04x", ch);
          c += b;
        } else {
          c += char(ch);  // UTF-8 baytları olduğu gibi
        }
    }
  }
  return c;
}

std::string htmlKacis(const std::string& s) {
  std::string c;
  c.reserve(s.size());
  for (char ch : s) {
    switch (ch) {
      case '&': c += "&amp;"; break;
      case '<': c += "&lt;"; break;
      case '>': c += "&gt;"; break;
      case '"': c += "&quot;"; break;
      case '\'': c += "&#39;"; break;
      default: c += ch;
    }
  }
  return c;
}

static const char* turAdi(OlayTuru t) {
  switch (t) {
    case OlayTuru::Giris: return "giris";
    case OlayTuru::Buton: return "buton";
    case OlayTuru::Acma: return "acma";
  }
  return "?";
}

std::string olayJson(const std::string& kutu_adi, const std::string& surum, uint32_t acilis,
                     uint32_t simdi_ms, const std::vector<Olay>& olaylar, uint32_t dusen,
                     uint8_t giris_durumu) {
  char b[160];
  std::string j = "{\"kutu\":\"" + jsonKacis(kutu_adi) + "\",\"surum\":\"" + jsonKacis(surum) + "\"";
  snprintf(b, sizeof b, ",\"acilis\":%lu,\"calisma_ms\":%lu,\"dusen\":%lu,\"girisler\":%u,\"olaylar\":[",
           (unsigned long)acilis, (unsigned long)simdi_ms, (unsigned long)dusen, unsigned(giris_durumu));
  j += b;
  for (size_t i = 0; i < olaylar.size(); ++i) {
    const Olay& o = olaylar[i];
    snprintf(b, sizeof b, "%s{\"sira\":%lu,\"tur\":\"%s\",\"giris\":%u,\"durum\":\"%s\",\"once_ms\":%lu",
             i ? "," : "", (unsigned long)o.sira, turAdi(o.tur), unsigned(o.giris), o.durum ? "var" : "yok",
             (unsigned long)(simdi_ms - o.zaman_ms));
    j += b;
    if (o.tur == OlayTuru::Acma) j += o.kaynak == 'b' ? ",\"kaynak\":\"buton\"" : ",\"kaynak\":\"pts\"";
    j += "}";
  }
  j += "]}";
  return j;
}

bool anahtarEsit(const std::string& beklenen, const std::string& gelen) {
  if (beklenen.empty()) return false;
  unsigned char fark = beklenen.size() == gelen.size() ? 0 : 1;
  for (size_t i = 0; i < beklenen.size(); ++i) {
    fark |= (unsigned char)beklenen[i] ^ (unsigned char)(i < gelen.size() ? gelen[i] : 0);
  }
  return fark == 0;
}

std::string urlBirlestir(const std::string& taban, const std::string& yol) {
  std::string t = taban;
  while (!t.empty() && t.back() == '/') t.pop_back();
  if (yol.empty()) return t;
  return t + (yol[0] == '/' ? yol : "/" + yol);
}

static int onaltilik(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

std::string urlCoz(const std::string& s) {
  std::string c;
  for (size_t i = 0; i < s.size(); ++i) {
    if (s[i] == '+') {
      c += ' ';
    } else if (s[i] == '%' && i + 2 < s.size() && onaltilik(s[i + 1]) >= 0 && onaltilik(s[i + 2]) >= 0) {
      c += char(onaltilik(s[i + 1]) * 16 + onaltilik(s[i + 2]));
      i += 2;
    } else {
      c += s[i];
    }
  }
  return c;
}

bool ipGecerli(const std::string& s, uint8_t cikti[4]) {
  int parca = 0, deger = -1;
  uint8_t gecici[4] = {};
  for (size_t i = 0; i <= s.size(); ++i) {
    const char ch = i < s.size() ? s[i] : '.';
    if (ch >= '0' && ch <= '9') {
      deger = (deger < 0 ? 0 : deger) * 10 + (ch - '0');
      if (deger > 255) return false;
    } else if (ch == '.') {
      if (deger < 0 || parca >= 4) return false;
      gecici[parca++] = uint8_t(deger);
      deger = -1;
    } else {
      return false;
    }
  }
  if (parca != 4) return false;
  if (cikti) for (int i = 0; i < 4; ++i) cikti[i] = gecici[i];
  return true;
}

std::string guncellemeDosyasiKontrol(const uint8_t* ilk, size_t n) {
  if (n == 0) return "Dosya boş.";
  if (ilk[0] == 0xFF)
    return "Bu ilk kurulum dosyası (pts-kapi-kutusu-tam.bin). Ağdan güncellemede firmware.bin dosyasını yükleyin.";
  if (ilk[0] != 0xE9) return "Bu bir ESP32 yazılım dosyası değil. firmware.bin dosyasını yükleyin.";
  // esp_image_header_t: 12. bayttan itibaren 2 baytlık çip kimliği (ESP32 = 0).
  if (n >= 14 && (ilk[12] | (ilk[13] << 8)) != 0)
    return "Bu dosya başka bir çip için derlenmiş (ESP32 değil).";
  return "";
}

}  // namespace kutu
