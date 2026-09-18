const API = "";  // aynı sunucudan servis edildiği için boş bırakıldı
let sonKayitlarCache = [];

// ---------------------- ROL BAZLI ARAYÜZ (RBAC) ----------------------
// Backend'deki _rol_dogrula() politikasıyla birebir eşleşir (backend/main.py).
// izleyici: salt okunur | operatör: günlük işlemler | yonetici: tam yetki
// "sakin" bilinçli olarak -1: panel personeli hiyerarşisinin (izleyici/
// operatör/yönetici) DIŞINDadır, bu yüzden hiçbir data-rol-min eşiğini
// (en düşüğü "izleyici"=0 dahil) hiç sağlamamalı -- normalde sakin girişinde
// zaten authBasarili() erken dönüp rolBazliArayuzuUygula()'yı hiç
// çağırmıyor (bkz. sakinModunuBaslat), ama bu satır ek bir güvenlik katmanı.
const ROL_SEVIYE = { sakin: -1, izleyici: 0, "operatör": 1, yonetici: 2 };
let mevcutRol = null;

function rolYeterli(minRol) {
  return (ROL_SEVIYE[mevcutRol] ?? 0) >= (ROL_SEVIYE[minRol] ?? 0);
}

function rolBazliArayuzuUygula() {
  document.querySelectorAll("[data-rol-min]").forEach(el => {
    const izinli = rolYeterli(el.dataset.rolMin);
    if (el.dataset.rolDavranis === "gizle") {
      el.classList.toggle("d-none", !izinli);
      return;
    }
    if (el.tagName === "FORM") {
      el.querySelectorAll("input, select, textarea, button").forEach(f => { f.disabled = !izinli; });
    } else {
      el.disabled = !izinli;
    }
  });
}

function sekmeAc(target) {
  const sekme = document.querySelector(`[data-bs-target="${target}"]`);
  if (sekme && window.bootstrap) bootstrap.Tab.getOrCreateInstance(sekme).show();
  document.querySelectorAll(".side-link").forEach(link => link.classList.toggle("active", link.dataset.target === target));
}

document.querySelectorAll("[data-target]").forEach(link => link.addEventListener("click", () => sekmeAc(link.dataset.target)));

// GÜVENLİK: plaka numarası gibi kullanıcı/kamera kaynaklı metinleri asla
// `onclick="fonksiyon('${deger}')"` biçiminde bir HTML attribute'u içine JS
// string literali olarak GÖMME — tarayıcı attribute değerini JS'e vermeden
// ÖNCE HTML-decode ettiği için escapeHtml()'in eklediği `&#39;` gibi kaçışlar
// bu noktada işe yaramaz (decode edilip tekrar tek tırnak haline döner) ve
// değer içinde tek tırnak varsa JS string'inden çıkıp keyfi kod çalıştırabilir
// (stored XSS). Backend artık plaka_no'yu harf/rakam/boşluk dışındaki tüm
// karakterlerden arındırıyor (bkz. schemas.py::plaka_normalize) ama bu,
// SADECE bu alan için geçerli tek bir savunma katmanı; aynı hataya başka bir
// alanda tekrar düşülmesin diye burada da kök neden kapatılıyor: değer asla
// bir attribute'un İÇİNE JS kodu olarak gömülmüyor, yalnızca bir `data-*`
// attribute'unda düz veri olarak taşınıyor ve olay delegasyonuyla okunuyor.
document.addEventListener("click", (e) => {
  const analizEl = e.target.closest("[data-plaka-analiz]");
  if (analizEl) {
    plakaAnalizAc(analizEl.dataset.plakaAnaliz);
    return;
  }
  const karaEkleEl = e.target.closest("[data-kara-ekle]");
  if (karaEkleEl) {
    karaListeyeEkleModal(karaEkleEl.dataset.karaEkle);
    return;
  }
  // NOT (2026-09-17): burada eskiden `.thumb[data-goruntu-yolu]` seçiciydi.
  // Ancak korumaliGorselleriYukle() bir tabloyu doldurduktan HEMEN SONRA, o
  // görsel yüklenmeyi bile beklemeden `data-goruntu-yolu` attribute'unu DOM'dan
  // SİLİYOR (bkz. aşağısı) — yani bir kullanıcı fiziksel olarak tıklayana kadar
  // bu seçici zaten hiçbir şeye eşleşmiyordu. Küçük resimlere tıklayıp büyütme
  // özelliği UYGULAMANIN HER YERİNDE (Panel, Kayıtlar, Plaka Analizi) baştan
  // beri hiç çalışmamıştı. Artık kalıcı olan `.thumb`/`.zoomable-img`
  // sınıflarına göre eşleşiyor.
  const thumbEl = e.target.closest(".thumb, .zoomable-img");
  if (thumbEl) {
    buyukGorselAc(thumbEl);
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" && e.key !== " " && e.key !== "Spacebar") return;
  const thumbEl = e.target.closest && e.target.closest(".thumb, .zoomable-img");
  if (!thumbEl) return;
  e.preventDefault();
  buyukGorselAc(thumbEl);
});

// ERİŞİLEBİLİRLİK: küçük resim (thumbnail) önizlemeleri bir <img> üzerinde
// yalnızca `onclick` ile açılıyordu — bir <img> öntanımlı olarak klavyeyle
// odaklanamaz/tetiklenemez, yani klavye veya ekran okuyucu kullanan biri bu
// büyütülmüş görsele hiç erişemezdi. Şablonlarda artık `role="button"
// tabindex="0"` ekleniyor (bkz. panelYenile/kayıtlar tabloları ve
// olayModalGorsel); bu da o öğeleri Enter/Boşluk tuşuyla tetiklenebilir hale
// getiriyor.
//
// GÖRSEL BÜYÜTME (ZOOM/PAN) LIGHTBOX (2026-09-17): eskiden `window.open(imgEl.src)`
// yeni bir sekme açıyordu (blob: URL'leri için garip/tutarsız davranıyordu ve
// yakınlaştırma imkânı yoktu). Artık uygulama içinde, plakayı yakından
// görebilmek için yakınlaştırma/kaydırma (pan) destekli bir modal açılıyor.
let _gorselZoom = 1;
let _gorselPanX = 0;
let _gorselPanY = 0;
let _gorselSurukleniyor = false;
let _gorselSurukleBaslangic = { x: 0, y: 0, panX: 0, panY: 0 };
const GORSEL_ZOOM_MIN = 1;
const GORSEL_ZOOM_MAX = 6;
const GORSEL_ZOOM_ADIM = 0.5;

function _gorselTransformUygula() {
  const img = document.getElementById("gorselBuyutImg");
  if (!img) return;
  img.style.transform = `translate(${_gorselPanX}px, ${_gorselPanY}px) scale(${_gorselZoom})`;
  img.style.cursor = _gorselZoom > GORSEL_ZOOM_MIN ? (_gorselSurukleniyor ? "grabbing" : "grab") : "zoom-in";
  const yuzdeEl = document.getElementById("gorselBuyutYuzde");
  if (yuzdeEl) yuzdeEl.textContent = `${Math.round(_gorselZoom * 100)}%`;
}

// `odakX`/`odakY` verilirse (fare tekerleği ile yakınlaştırmada), imlecin
// altındaki nokta ekranda sabit kalacak şekilde pan orantılı olarak ölçeklenir.
function gorselZoomAyarla(yeniZoom, odakX, odakY) {
  const eskiZoom = _gorselZoom;
  _gorselZoom = Math.min(GORSEL_ZOOM_MAX, Math.max(GORSEL_ZOOM_MIN, yeniZoom));
  if (_gorselZoom === GORSEL_ZOOM_MIN) {
    _gorselPanX = 0;
    _gorselPanY = 0;
  } else if (typeof odakX === "number" && eskiZoom !== _gorselZoom) {
    const oran = _gorselZoom / eskiZoom;
    _gorselPanX = odakX - (odakX - _gorselPanX) * oran;
    _gorselPanY = odakY - (odakY - _gorselPanY) * oran;
  }
  _gorselTransformUygula();
}

function gorselZoomSifirla() {
  _gorselZoom = 1;
  _gorselPanX = 0;
  _gorselPanY = 0;
  _gorselTransformUygula();
}

function buyukGorselAc(imgEl) {
  if (!imgEl || !imgEl.src) return;
  const buyukImg = document.getElementById("gorselBuyutImg");
  if (!buyukImg) return;
  // Görsel zaten blob: URL olarak `imgEl.src`'de hazır (korumaliGorselAta ile
  // atanmış) — tekrar fetch etmeye gerek yok, aynı blob URL'i yeniden kullanılır.
  buyukImg.src = imgEl.src;
  gorselZoomSifirla();
  bootstrap.Modal.getOrCreateInstance(document.getElementById("gorselBuyutModal")).show();
}

(function () {
  const modalEl = document.getElementById("gorselBuyutModal");
  const kapsayici = document.getElementById("gorselBuyutKapsayici");
  if (!modalEl || !kapsayici) return;

  // Modal kapanınca zoom/pan durumu ve src sıfırlanır ki bir sonraki açılışta
  // önceki görselin büyütülmüş hali bir an için görünmesin.
  modalEl.addEventListener("hidden.bs.modal", () => {
    gorselZoomSifirla();
    const img = document.getElementById("gorselBuyutImg");
    if (img) img.removeAttribute("src");
  });

  document.getElementById("gorselBuyutBtn")?.addEventListener("click", () => gorselZoomAyarla(_gorselZoom + GORSEL_ZOOM_ADIM));
  document.getElementById("gorselKucultBtn")?.addEventListener("click", () => gorselZoomAyarla(_gorselZoom - GORSEL_ZOOM_ADIM));
  document.getElementById("gorselSifirlaBtn")?.addEventListener("click", gorselZoomSifirla);

  kapsayici.addEventListener("wheel", (e) => {
    e.preventDefault();
    const rect = kapsayici.getBoundingClientRect();
    const odakX = e.clientX - rect.left - rect.width / 2;
    const odakY = e.clientY - rect.top - rect.height / 2;
    gorselZoomAyarla(_gorselZoom + (e.deltaY < 0 ? GORSEL_ZOOM_ADIM : -GORSEL_ZOOM_ADIM), odakX, odakY);
  }, { passive: false });

  // Çift tık: yakınlaştırılmamışsa 2.5x'e yakınlaştır, yakınlaştırılmışsa sıfırla.
  kapsayici.addEventListener("dblclick", () => {
    gorselZoomAyarla(_gorselZoom > GORSEL_ZOOM_MIN ? GORSEL_ZOOM_MIN : 2.5);
  });

  kapsayici.addEventListener("pointerdown", (e) => {
    if (_gorselZoom <= GORSEL_ZOOM_MIN) return;
    _gorselSurukleniyor = true;
    _gorselSurukleBaslangic = { x: e.clientX, y: e.clientY, panX: _gorselPanX, panY: _gorselPanY };
    kapsayici.setPointerCapture(e.pointerId);
    _gorselTransformUygula();
  });
  kapsayici.addEventListener("pointermove", (e) => {
    if (!_gorselSurukleniyor) return;
    _gorselPanX = _gorselSurukleBaslangic.panX + (e.clientX - _gorselSurukleBaslangic.x);
    _gorselPanY = _gorselSurukleBaslangic.panY + (e.clientY - _gorselSurukleBaslangic.y);
    _gorselTransformUygula();
  });
  ["pointerup", "pointercancel", "pointerleave"].forEach(evtAdi =>
    kapsayici.addEventListener(evtAdi, () => { _gorselSurukleniyor = false; _gorselTransformUygula(); })
  );
})();

// ---------------------- YARDIMCI FONKSİYONLAR ----------------------

function gorselAdiAl(yol) {
  // Windows ("\") ve Linux/Mac ("/") yol ayırıcılarının ikisini de destekler
  return yol.split(/[\\/]/).pop();
}

// GÜVENLİK: /goruntuler artık kimlik doğrulaması gerektiriyor (araç/sürücü
// görselleri KVKK kapsamında kişisel veridir — bkz. backend/main.py::gorsel_getir).
// `<img src="...">` Authorization header TAŞIYAMADIĞI için (canlı kamera
// akışında ve DB yedek indirmede olduğu gibi), görseller token'lı bir
// fetch() ile alınıp blob URL'ine çevrilerek gösteriliyor. Bir img elemanına
// önceden atanmış blob URL'i varsa, bellek sızıntısı olmasın diye önce
// serbest bırakılır (revokeObjectURL).
const _korumaliGorselBlobURLleri = new WeakMap();

async function korumaliGorselAta(imgEl, goruntuYolu) {
  if (!imgEl || !goruntuYolu) return;
  const token = sessionStorage.getItem("pts_token");
  if (!token) return;
  try {
    const yanit = await fetch(`/goruntuler/${encodeURIComponent(gorselAdiAl(goruntuYolu))}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!yanit.ok) return;
    const blob = await yanit.blob();
    const eskiUrl = _korumaliGorselBlobURLleri.get(imgEl);
    if (eskiUrl) URL.revokeObjectURL(eskiUrl);
    const url = URL.createObjectURL(blob);
    _korumaliGorselBlobURLleri.set(imgEl, url);
    imgEl.src = url;
  } catch (e) {
    console.error("Görsel yüklenemedi:", e);
  }
}

// Bir tabloyu innerHTML ile doldurduktan HEMEN SONRA çağrılır: içindeki tüm
// `data-goruntu-yolu` taşıyan (henüz src'siz) <img> etiketlerine korumalı
// görseli asenkron olarak atar.
function korumaliGorselleriYukle(kapsayici) {
  kapsayici.querySelectorAll("img[data-goruntu-yolu]").forEach(img => {
    korumaliGorselAta(img, img.dataset.goruntuYolu);
    img.removeAttribute("data-goruntu-yolu");
  });
}

function escapeHtml(deger) {
  // Kamera/kullanıcı kaynaklı verileri innerHTML'e basmadan önce kaçış karakterlerine çevirir (XSS önlemi).
  return String(deger ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function tarihFormatla(iso) {
  const d = new Date(iso);
  return d.toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function durumRozeti(durum) {
  const etiketler = { yetkili: "Yetkili", yetkisiz: "Yetkisiz", suresi_dolmus: "Süresi Dolmuş", bilinmiyor: "Bilinmiyor", kara_liste: "Kara Liste", ziyaretci_onayli: "Ziyaretçi Girişi Onaylandı" };
  return `<span class="badge badge-${durum}">${etiketler[durum] || escapeHtml(durum)}</span>`;
}

function alarmTipiEtiketi(tip) {
  const etiketler = {
    yetkisiz_arac: "Yetkisiz araç",
    suresi_dolmus: "Süresi dolmuş ziyaretçi",
    kara_liste: "Kara liste geçişi",
    supheli_arac: "Şüpheli araç (tekrarlı red)",
    kamera_arizasi: "Kamera arızası / bağlantı sorunu",
  };
  return etiketler[tip] || escapeHtml(tip || "Bilinmeyen alarm");
}

function tipRozeti(tip) {
  if (!tip) return '<span class="text-muted">-</span>';
  const etiketler = { abone: "Abone", personel: "Personel", ziyaretci: "Ziyaretçi" };
  return `<span class="badge badge-${tip}">${etiketler[tip] || escapeHtml(tip)}</span>`;
}

// Bu okumanın kaç farklı karede tekrarlanıp oy aldığını gösterir (bkz.
// backend/camera_reader.py::PlakaOyBirikimi.toplam_kare_sayisi ve
// README.md'deki 2026-09-17 notu). null/undefined: kamera pipeline'ından
// gelmeyen (manuel giriş, eski) kayıt -- uygulanamaz. 1: bu okuma başka
// HİÇBİR karede doğrulanmadan tek başına kesinleşmiş -- yanlış okuma riski
// daha yüksek, operatör dikkat etsin diye ayrıca işaretlenir. >=2: birden
// fazla karenin oydaşmasıyla kesinleşmiş, daha güvenilir.
function dogrulamaRozeti(kareSayisi, farkliOkumaSayisi) {
  if (kareSayisi === null || kareSayisi === undefined) return '<span class="text-muted small">-</span>';
  if (kareSayisi <= 1) {
    return `<span class="badge badge-dogrulama-zayif" title="Bu okuma yalnızca TEK bir karede yapıldı, başka hiçbir karede doğrulanmadı -- yanlış okuma ihtimali daha yüksektir.">⚠ 1 kare</span>`;
  }
  // 2026-09-18: "N kare" oydaşması TEK BAŞINA garanti değildir -- kazanan,
  // azınlıkta kalan farklı bir okumaya rağmen seçilmiş olabilir (örn. kamera
  // kutuyu kenar boşluksuz kırptığı için bazı karelerde son karakter hiç
  // görülmemiş olabilir). farkli_okuma_sayisi > 1 ise bunu operatöre ayrıca
  // (yeşil değil, uyarı rengiyle) işaretliyoruz -- bkz. README.md'deki ilgili
  // not ve backend/camera_reader.py::PlakaOyBirikimi.kazanan.
  if (farkliOkumaSayisi && farkliOkumaSayisi > 1) {
    return `<span class="badge badge-dogrulama-zayif" title="Bu ${kareSayisi} karede OCR ${farkliOkumaSayisi} FARKLI metin önerdi; gösterilen yalnızca en çok oyu alan okumadır. Özellikle plakanın son karakterini elle kontrol edin (kamera kutuyu dar kırpınca son karakter OCR'a hiç ulaşmayabilir).">⚠ ${kareSayisi} kare (çelişkili)</span>`;
  }
  return `<span class="badge badge-dogrulama-guclu" title="Bu okuma ${kareSayisi} farklı karenin TAMAMEN AYNI metni üreterek oydaşmasıyla kesinleşti.">✓ ${kareSayisi} kare</span>`;
}

function saatiGuncelle() {
  const el = document.getElementById("saatGosterge");
  if (el) el.textContent = new Date().toLocaleString("tr-TR");
}
setInterval(saatiGuncelle, 1000);
saatiGuncelle();

async function apiCagir(yol, secenekler = {}) {
  const token = sessionStorage.getItem("pts_token");
  secenekler.headers = { ...(secenekler.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
  const cevap = await fetch(API + yol, secenekler);
  if (!cevap.ok) {
    const hata = await cevap.json().catch(() => ({ detail: "Bilinmeyen hata" }));
    throw new Error(hata.detail || "İstek başarısız");
  }
  return cevap.status === 204 ? null : cevap.json();
}

// DOSYA İNDİRME URL'İ (2026-09-18): `/disa-aktar/...` ve şablon indirme
// uçları `window.open()` ile açılır -- bu, `fetch()`in aksine bir
// Authorization header TAŞIYAMAZ (bkz. korumaliGorselAta'nın aynı kısıtlama
// için neden fetch+blob kullandığını anlatan not). GÜVENLİK KÖK NEDEN
// DÜZELTMESİ: bu uç noktalar önceden hiç kimlik doğrulaması istemiyordu --
// artık istiyor (bkz. main.py::_giris_gerekli), bu yüzden token'ın buradan
// `?token=` sorgu parametresi olarak eklenmesi ZORUNLU, aksi halde her
// indirme 401 ile başarısız olur.
function indirmeUrlOlustur(yol, params = new URLSearchParams()) {
  const token = sessionStorage.getItem("pts_token");
  if (token) params.set("token", token);
  const sorgu = params.toString();
  return sorgu ? `${yol}?${sorgu}` : yol;
}

// SON KULLANILAN NOT ÖNERİSİ (2026-09-17, devam): kullanıcı talebi -- aynı
// plakaya (örn. bir kargo aracına) art arda günlerde not eklerken görevli
// notu her seferinde yeniden yazmak zorunda kalmasın diye, bir önceki not
// giriş kutusuna ÖNERİ olarak sunulur (her zaman düzenlenebilir). Bu bir
// kalıcı kayıt DEĞİLDİR -- backend'de her gece 23:59'da otomatik sıfırlanan
// geçici bir önbellektir (bkz. main.py::_SON_NOT_ONBELLEGI), yani ertesi
// güne asla taşınmaz. Herhangi bir sebeple alınamazsa (ağ hatası, boş sonuç)
// sessizce boş döner -- bu yalnızca bir kolaylık, işlemi asla engellemez.
async function sonNotOnerisiGetir(plaka) {
  if (!plaka) return "";
  try {
    const r = await apiCagir(`/kayitlar/son-not?plaka=${encodeURIComponent(plaka)}`);
    return r?.not_metni || "";
  } catch {
    return "";
  }
}

async function authBaslat() {
  const durum = await apiCagir("/auth/durum");
  if (!durum.kurulum_tamamlandi) {
    document.getElementById("authBaslik").textContent = "Yönetici hesabı oluştur";
    document.getElementById("authAciklama").textContent = "Bu PTS kurulumu için ilk yönetici hesabını belirleyin.";
    document.getElementById("authButon").textContent = "Hesabı oluştur";
    document.getElementById("authForm").dataset.ilkKurulum = "true";
  }
  document.getElementById("authForm").addEventListener("submit", authFormGonder);
  const token = sessionStorage.getItem("pts_token");
  if (token) {
    try { const kullanici = await apiCagir("/auth/me"); authBasarili(kullanici); return true; } catch { sessionStorage.removeItem("pts_token"); }
  }
  return false;
}

function authBasarili(kullanici) {
  document.getElementById("authKapisi").classList.add("d-none");
  document.getElementById("oturumKullanici").textContent = kullanici.kullanici_adi;
  mevcutRol = kullanici.rol;
  // "sakin" (site sakini öz-hizmet) hesabı panel PERSONELİ değil -- normal
  // sidebar/sekme arayüzünü hiç göstermeden, yalnızca kendi profili/
  // plakaları/geçmişini gördüğü sadeleştirilmiş ayrı bir görünüme yönlendir
  // (bkz. main.py::_personel_girisi_gerekli'nin arkasındaki aynı ayrım).
  if (mevcutRol === "sakin") {
    sakinModunuBaslat();
    return;
  }
  rolBazliArayuzuUygula();
  uygulamaVerileriniYukle();
}

async function uygulamaVerileriniYukle() {
  panelYenile(); kayitlariYukle(); kisileriYukle(); ledAyarlariYukle(); lisansYukle(); kameralariYukle();
  grafikYukle(); karaListesiYukle(); bariyerleriYukle(); kullanicilariYukle(); sistemSagliginiYukle();
  bildirimleriYukle();
  await siteleriYukle(); noktalariYukle();
  sseBaslat();
}

function oturumKapat() {
  sessionStorage.removeItem("pts_token");
  location.reload();
}

// ================================================================
// SAKİN ÖZ-HİZMET PANELİ (2026-09-17)
// ================================================================
// Bir "sakin" hesabı yalnızca /sakin/... uçlarını çağırabilir (bkz.
// backend/main.py::_sakin_girisi_gerekli) -- bu yüzden burada da normal
// panelin diğer TÜM veri yükleme fonksiyonları (kayitlariYukle, kisileriYukle,
// vb.) hiç çağrılmaz; onlar zaten 403 alırdı.
function sakinModunuBaslat() {
  document.querySelector(".app-layout")?.classList.add("d-none");
  document.querySelector(".navbar-pts small")?.classList.add("d-none");
  document.getElementById("sakinPaneli").classList.remove("d-none");
  sakinPaneliYukle();
}

async function sakinPaneliYukle() {
  try {
    const profil = await apiCagir("/sakin/profilim");
    document.getElementById("sakinAdSoyad").textContent = profil.ad_soyad;
    document.getElementById("sakinAnaPlaka").textContent = profil.plaka_no;
    document.getElementById("sakinDaire").textContent = profil.daire_departman || "-";
    document.getElementById("sakinDurum").textContent = profil.aktif ? "Aktif" : "Pasif";

    const tablo = document.getElementById("sakinAraclarTablo");
    const anaPlaka = `<tr><td class="fw-bold">${escapeHtml(profil.plaka_no)}</td><td class="text-muted small">Ana plaka</td><td></td></tr>`;
    const ekPlakalar = profil.ek_plakalar.map(p => `
      <tr>
        <td class="fw-bold">${escapeHtml(p.plaka_no)}</td>
        <td>${escapeHtml(p.aciklama || "-")}</td>
        <td><button class="btn btn-sm btn-outline-danger" onclick="sakinAracSil(${p.id})" title="Sil" aria-label="Sil"><i class="bi bi-trash"></i></button></td>
      </tr>`).join("");
    tablo.innerHTML = anaPlaka + ekPlakalar;
  } catch (err) {
    document.getElementById("sakinAdSoyad").textContent = "Hata: " + err.message;
  }

  try {
    const gecmis = await apiCagir("/sakin/gecmisim?limit=50");
    const tablo = document.getElementById("sakinGecmisTablo");
    tablo.innerHTML = gecmis.map(k => `
      <tr>
        <td>${tarihFormatla(k.tarih_saat)}</td>
        <td>${escapeHtml(k.kamera_id)}</td>
        <td>${k.yon === "giris" ? "Giriş" : "Çıkış"}</td>
        <td>${durumRozeti(k.yetki_durumu)}</td>
      </tr>
    `).join("") || `<tr><td colspan="4" class="text-center text-muted py-3">Henüz geçiş kaydınız yok</td></tr>`;
  } catch (err) {
    document.getElementById("sakinGecmisTablo").innerHTML = `<tr><td colspan="4" class="text-center text-danger py-3">${escapeHtml(err.message)}</td></tr>`;
  }
}

document.getElementById("sakinAracEkleForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const sonuc = document.getElementById("sakinAracSonuc");
  try {
    await apiCagir("/sakin/arac-ekle", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        plaka_no: document.getElementById("sakinYeniPlaka").value,
        aciklama: document.getElementById("sakinYeniAciklama").value || null,
      }),
    });
    document.getElementById("sakinAracEkleForm").reset();
    sonuc.className = "small mt-1 text-success";
    sonuc.textContent = "Araç eklendi.";
    sakinPaneliYukle();
  } catch (err) {
    sonuc.className = "small mt-1 text-danger";
    sonuc.textContent = err.message;
  }
});

async function sakinAracSil(id) {
  if (!confirm("Bu aracı listenizden kaldırmak istiyor musunuz?")) return;
  try {
    await apiCagir(`/sakin/arac/${id}`, { method: "DELETE" });
    sakinPaneliYukle();
  } catch (err) {
    alert(err.message);
  }
}

async function authFormGonder(e) {
  e.preventDefault();
  const form = e.target;
  const sonuc = document.getElementById("authSonuc");
  const govde = { kullanici_adi: document.getElementById("authKullanici").value, parola: document.getElementById("authParola").value };
  try {
    const yol = form.dataset.ilkKurulum === "true" ? "/auth/ilk-yonetici" : "/auth/giris";
    const cevap = await apiCagir(yol, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(govde) });
    if (yol === "/auth/ilk-yonetici") {
      form.dataset.ilkKurulum = "false";
      document.getElementById("authBaslik").textContent = "Güvenli giriş";
      document.getElementById("authAciklama").textContent = "Yönetici hesabınız oluşturuldu. Giriş yapın.";
      document.getElementById("authButon").textContent = "Giriş yap";
      sonuc.className = "small mt-3 text-success"; sonuc.textContent = "Hesap hazır.";
    } else { sessionStorage.setItem("pts_token", cevap.token); authBasarili(cevap.kullanici); }
  } catch (err) { sonuc.className = "small mt-3 text-danger"; sonuc.textContent = err.message; }
}

// ---------------------- PANEL (DASHBOARD) ----------------------

async function panelYenile() {
  try {
    const ist = await apiCagir("/kayitlar/istatistik");
    document.getElementById("istToplam").textContent = ist.toplam_kayit;
    document.getElementById("istBugun").textContent = ist.bugunku_kayit;
    document.getElementById("istYetkisiz").textContent = ist.yetkisiz_giris_denemesi;
    document.getElementById("istKisi").textContent = ist.aktif_kisi_sayisi;
    const elKL = document.getElementById("istKaraListe");
    if (elKL) elKL.textContent = ist.kara_liste_gecis ?? 0;
    const elKLS = document.getElementById("istKaraListeSayisi");
    if (elKLS) elKLS.textContent = ist.kara_liste_kayit_sayisi ?? 0;

    // Araç içeride sayısı
    apiCagir("/araclar/iceridedurum").then(d => {
      const el = document.getElementById("istIceride");
      if (el) el.textContent = d.iceride_sayisi;
    }).catch(() => {});

    const kayitlar = await apiCagir("/kayitlar?limit=10");
    const canliOlaylar = document.getElementById("canliOlaylar");
    if (canliOlaylar) {
      const alarmlar = await apiCagir("/alarmlar?sadece_acik=true&limit=4");
      const alarmSatirlari = alarmlar.map(a => `<div class="event-row alarm-row"><div class="event-icon blocked"><i class="bi bi-exclamation-triangle-fill"></i></div><div class="event-main"><strong>${escapeHtml(a.plaka_no)}</strong><span>${alarmTipiEtiketi(a.alarm_tipi)}</span></div>${rolYeterli("operatör") ? `<button class="btn btn-sm btn-light" title="Okundu işaretle" aria-label="Okundu işaretle" onclick="alarmOkundu(${a.id})"><i class="bi bi-check2"></i></button>` : ""}</div>`).join("");
      const olaySatirlari = kayitlar.slice(0, 8).map(k => `<button class="event-row event-button" onclick="olayDetayAc(${k.id})"><div class="event-icon ${k.yetki_durumu === "yetkili" ? "allowed" : "blocked"}"><i class="bi ${k.yon === "giris" ? "bi-box-arrow-in-right" : "bi-box-arrow-right"}"></i></div><div class="event-main"><strong>${escapeHtml(k.plaka_no)}</strong><span>${escapeHtml(k.kamera_id)} · ${k.yon === "giris" ? "Giriş" : "Çıkış"}</span></div><div class="event-time">${tarihFormatla(k.tarih_saat).split(",")[1] || "-"}</div></button>`).join("");
      canliOlaylar.innerHTML = alarmSatirlari + olaySatirlari || '<div class="empty-state">Henüz geçiş kaydı yok</div>';
    }
    sonKayitlarCache = kayitlar;
    const canliYenileme = document.getElementById("canliYenileme");
    if (canliYenileme) canliYenileme.textContent = new Date().toLocaleTimeString("tr-TR");
    const tbody = document.getElementById("sonKayitlarTablo");
    tbody.innerHTML = kayitlar.map(k => `
      <tr>
        <td>${k.goruntu_yolu ? `<img class="thumb" data-goruntu-yolu="${escapeHtml(k.goruntu_yolu)}" role="button" tabindex="0" alt="Geçiş görseli, büyütmek için tıklayın veya Enter'a basın">` : '<span class="text-muted small">Görsel yok</span>'}</td>
        <td class="fw-bold"><button class="plate-link" onclick="olayDetayAc(${k.id})">${escapeHtml(k.plaka_no)}</button></td>
        <td>${tarihFormatla(k.tarih_saat)}</td>
        <td>${k.yon === "giris" ? "Giriş" : "Çıkış"}</td>
        <td>${durumRozeti(k.yetki_durumu)}</td>
        <td>${tipRozeti(k.kisi_tip_anlik)}</td>
      </tr>
    `).join("") || `<tr><td colspan="6" class="text-center text-muted py-3">Henüz kayıt yok</td></tr>`;
    korumaliGorselleriYukle(tbody);
  } catch (e) {
    console.error(e);
  }
}

async function alarmOkundu(id) {
  await apiCagir(`/alarmlar/${id}/okundu`, { method: "PATCH" });
  panelYenile();
}

async function olayDetayAc(id) {
  const kayit = sonKayitlarCache.find(item => item.id === id);
  if (!kayit) return;
  const detay = kayit.kisi_id ? await apiCagir(`/kisiler/${kayit.kisi_id}`).catch(() => null) : null;
  // Kameranın bağlı olduğu erişim noktasını (ve varsa sitesini/bariyerini) bul —
  // kameralar ile siteler/bariyerler arasındaki tek bağlantı Nokta kaydıdır.
  const noktalar = await apiCagir("/noktalar").catch(() => []);
  const nokta = noktalar.find(n => n.kamera_id && n.kamera_id === kayit.kamera_id) || null;
  let siteAdi = null;
  if (nokta) {
    const siteler = await apiCagir("/siteler").catch(() => []);
    siteAdi = siteler.find(s => s.id === nokta.site_id)?.ad || null;
  }
  const gorsel = document.getElementById("olayModalGorsel");
  const gorselYok = document.getElementById("olayModalGorselYok");
  if (kayit.goruntu_yolu) { korumaliGorselAta(gorsel, kayit.goruntu_yolu); gorsel.classList.remove("d-none"); gorselYok.classList.add("d-none"); } else { gorsel.removeAttribute("src"); gorsel.classList.add("d-none"); gorselYok.classList.remove("d-none"); }
  document.getElementById("olayModalTur").textContent = kayit.yetki_durumu === "yetkili" ? "TANIMLI ARAÇ"
    : kayit.yetki_durumu === "ziyaretci_onayli" ? "ZİYARETÇİ GİRİŞİ ONAYLANDI"
    : kayit.yetki_durumu === "suresi_dolmus" ? "ZİYARETÇİ GİRİŞİ" : "YETKİSİZ ARAÇ";
  document.getElementById("olayModalPlaka").textContent = kayit.plaka_no;
  document.getElementById("olayModalTarih").textContent = new Date(kayit.tarih_saat).toLocaleDateString("tr-TR");
  document.getElementById("olayModalSaat").textContent = new Date(kayit.tarih_saat).toLocaleTimeString("tr-TR");
  document.getElementById("olayModalSite").textContent = siteAdi || "Bağlı site tanımlı değil";
  document.getElementById("olayModalNokta").textContent = nokta?.ad || kayit.kamera_id;
  document.getElementById("olayModalYon").textContent = kayit.yon === "giris" ? "Giriş" : "Çıkış";
  document.getElementById("olayModalKisi").textContent = detay?.ad_soyad || "Tanımsız araç";
  document.getElementById("olayModalDaire").textContent = detay?.daire_departman || "-";
  document.getElementById("olayModalAracTipi").textContent = detay ? (detay.tip === "ziyaretci" ? "Ziyaretçi" : "Tanımlı") : "Tanımsız araç";
  document.getElementById("olayModalGuven").textContent = kayit.guven_skoru ? `${(kayit.guven_skoru * 100).toFixed(0)}%` : "-";
  document.getElementById("olayModalDuzeltme").textContent = kayit.ham_plaka_metni
    ? `${kayit.ham_plaka_metni} → ${kayit.plaka_no} (bilinen plakaya göre düzeltildi)`
    : "-";
  _olayModalBariyerButonunuAyarla(nokta);
  _olayModalAnalizButonunuAyarla(kayit);
  await _ziyaretciGirisiKutusunuAyarla(kayit, nokta);
  bootstrap.Modal.getOrCreateInstance(document.getElementById("olayDetayModal")).show();
}

// "Son Geçişler" panelinden (ve Ana Sayfa'daki son kayıtlar tablosundan)
// olayDetayAc() ile açılan TEK bir geçiş kaydına özel bu modal, kullanıcının
// başka ekranlarda (Kayıtlar/Kara Liste/Kişiler) zaten alışık olduğu, PLAKA
// bazlı tam geçmiş + manuel kayıt ekleme ekranına (plakaAnalizAc) da buradan
// erişim sağlar — bkz. kullanıcı isteği: "son geçişlerde gözüken plakalara
// da tıklandığında ziyaretçi ekleme aracın resmini görme kayıt etme gibi
// şeylerin aynısını görmek istiyorum". kayit.plaka_no zaten backend'de
// schemas.py::plaka_normalize ile harf/rakam/boşluk dışı karakterlerden
// arındırıldığı için burada güvenlidir; yine de HTML attribute'una GÖMMEK
// yerine (bkz. yukarıdaki data-plaka-analiz güvenlik notu) kapanışta doğrudan
// JS değişkeni olarak kullanılıyor.
function _olayModalAnalizButonunuAyarla(kayit) {
  const btn = document.getElementById("olayModalAnalizBtn");
  if (!btn) return;
  btn.onclick = () => {
    bootstrap.Modal.getInstance(document.getElementById("olayDetayModal"))?.hide();
    plakaAnalizAc(kayit.plaka_no);
  };
}

// "Ziyaretçi Girişi" hızlı onay kutusu: bir tespiti tek tuşla bir kişiye/
// daireye bağlayıp (opsiyonel) AYNI ANDA bariyeri açan akış. Mevcut iki uç
// noktayı (kayıt düzenle + bariyer aç) birleştirir, yeni bir backend uç
// noktası GEREKMEZ (bkz. README'deki 2026-09-17 "Ziyaretçi Girişi" notu).
async function _ziyaretciGirisiKutusunuAyarla(kayit, nokta) {
  const kutu = document.getElementById("ziyaretciGirisiKutusu");
  const zatenOnayli = kayit.yetki_durumu === "yetkili" || kayit.yetki_durumu === "ziyaretci_onayli";
  document.getElementById("ziyaretciGirisiSonuc").textContent = "";
  document.getElementById("olayModalZiyaretciNot").value = "";
  if (zatenOnayli || !rolYeterli("operatör")) {
    kutu.classList.add("d-none");
    return;
  }
  kutu.classList.remove("d-none");
  // Not kutusu boş açılır (yukarısı); varsa aynı plakanın bugün için "son
  // kullanılan not" önerisi asenkron olarak doldurulur (kutu zaten boşsa).
  sonNotOnerisiGetir(kayit.plaka_no).then(oneri => {
    const notEl = document.getElementById("olayModalZiyaretciNot");
    if (oneri && notEl && !notEl.value) notEl.value = oneri;
  });
  const secim = document.getElementById("olayModalKisiSecim");
  try {
    const kisiler = await apiCagir("/kisiler");
    secim.innerHTML = '<option value="">Kişiye bağlamadan onayla</option>' + kisiler.map(k =>
      `<option value="${k.id}">${escapeHtml(k.ad_soyad)} (${escapeHtml(k.plaka_no)}${k.daire_departman ? " · " + escapeHtml(k.daire_departman) : ""})</option>`
    ).join("");
  } catch { secim.innerHTML = '<option value="">Kişiye bağlamadan onayla</option>'; }

  const btn = document.getElementById("ziyaretciGirisiBtn");
  btn.onclick = async () => {
    const sonuc = document.getElementById("ziyaretciGirisiSonuc");
    if (kayit.yetki_durumu === "kara_liste" && !confirm("Bu araç KARA LİSTEDE. Yine de ziyaretçi olarak onaylayıp bariyeri açmak istediğinize emin misiniz? Bu işlem kayda geçer.")) {
      return;
    }
    btn.disabled = true;
    sonuc.className = "small mt-1";
    sonuc.textContent = "İşleniyor...";
    try {
      const govde = { yetki_durumu: "ziyaretci_onayli" };
      const notMetni = document.getElementById("olayModalZiyaretciNot").value.trim();
      if (notMetni) govde.not_metni = notMetni;
      if (secim.value) govde.kisi_id = Number(secim.value);
      await apiCagir(`/kayitlar/${kayit.id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(govde),
      });
      if (nokta?.bariyer_id) {
        const r = await apiCagir(`/bariyer/${nokta.bariyer_id}/ac`, { method: "POST" });
        sonuc.className = "small mt-1 text-success";
        sonuc.textContent = `Ziyaretçi girişi onaylandı, bariyer açıldı: ${r.mesaj}`;
      } else {
        sonuc.className = "small mt-1 text-success";
        sonuc.textContent = "Ziyaretçi girişi onaylandı (bu noktaya bağlı bariyer tanımlı değil).";
      }
      toastGoster("Ziyaretçi girişi onaylandı: " + kayit.plaka_no, "basari");
      kutu.classList.add("d-none");
      panelYenile();
      kayitlariYukle(false);
    } catch (err) {
      sonuc.className = "small mt-1 text-danger";
      sonuc.textContent = err.message;
    } finally {
      btn.disabled = false;
    }
  };
}

function _olayModalBariyerButonunuAyarla(nokta) {
  const btn = document.getElementById("bariyerAcBtn");
  btn.onclick = null;
  if (!rolYeterli("operatör")) {
    btn.disabled = true;
    btn.title = "Bu işlem için yetkiniz yok";
    return;
  }
  if (!nokta || !nokta.bariyer_id) {
    btn.disabled = true;
    btn.title = "Bu kameraya bağlı tanımlı bir bariyer yok (Site/Nokta Yönetimi'nden bağlayın)";
    return;
  }
  btn.disabled = false;
  btn.title = "Bariyeri aç";
  btn.onclick = async () => {
    btn.disabled = true;
    try {
      const r = await apiCagir(`/bariyer/${nokta.bariyer_id}/ac`, { method: "POST" });
      toastGoster(r.mesaj, "basari");
    } catch (err) {
      toastGoster(err.message, "hata");
    } finally {
      btn.disabled = false;
    }
  };
}

async function lisansYukle() {
  try {
    const lisans = await apiCagir("/lisans");
    const durumMetni = lisans.aktif ? "Aktif" : "Aktivasyon bekliyor";
    const durumEl = document.getElementById("lisansDurum");
    if (durumEl) durumEl.innerHTML = `<div class="license-icon ${lisans.aktif ? "active" : "pending"}"><i class="bi ${lisans.aktif ? "bi-shield-check" : "bi-shield-exclamation"}"></i></div><div><strong>${durumMetni}</strong><span>${lisans.aktif ? "Kamera bağlantıları kullanılabilir" : "Kamera kullanımını etkinleştirmek için anahtar girin"}</span></div>`;
    document.getElementById("lisansMiniDurum").innerHTML = `<i class="bi ${lisans.aktif ? "bi-shield-check" : "bi-shield-exclamation"}"></i> Lisans ${lisans.aktif ? "aktif" : "pasif"}`;
    document.getElementById("lisansMiniDurum").classList.toggle("active", lisans.aktif);
    document.getElementById("cihazKodu").textContent = lisans.cihaz_kodu;
    document.getElementById("kameraLimiti").textContent = lisans.aktif ? `${lisans.kamera_limiti} kamera` : "0 kamera";
    document.getElementById("lisansBitisi").textContent = lisans.bitis_tarihi || "Aktif değil";
  } catch (err) { console.error(err); }
}

// Kamera Yön/ROI değişikliklerinde (kameraYonDegistir, kameraRoiAc/Kaydet)
// RTSP adresi gibi başka alanlara tekrar erişebilmek için son yüklenen liste
// burada tutulur.
let _kameralarCache = [];

async function kameralariYukle() {
  try {
    const kameralar = await apiCagir("/kameralar");
    _kameralarCache = kameralar;
    document.getElementById("kameraSayac").textContent = `${kameralar.length} kamera tanımlı`;
    document.getElementById("kameralarTablo").innerHTML = kameralar.map(k => {
      const durum = !k.kutuphaneler_mevcut
        ? `<span class="badge bg-warning text-dark" title="fast-alpr + opencv kurulu değil">Kütüphane Yok</span>`
        : !k.pipeline_calisiyor
          ? `<span class="badge bg-danger">Durdu</span>`
          : k.donmus
            ? `<span class="badge bg-warning text-dark" title="${k.son_kare_yasi_sn != null ? k.son_kare_yasi_sn + ' sn önceki kare' : ''}"><i class="bi bi-exclamation-triangle-fill"></i> Görüntü Donmuş</span>`
            : `<span class="badge bg-success">Çalışıyor</span>`;
      const yenidenBaglanmaBadge = (k.yeniden_baglanma_sayisi > 0)
        ? `<span class="badge bg-light text-muted ms-1" title="Bu oturumda yeniden bağlanma denemesi">↻ ${k.yeniden_baglanma_sayisi}</span>`
        : "";
      const saglik = _kameraSaglikCache[k.id];
      const tcpBadge = saglik
        ? (saglik.tcp_erisim
            ? `<span class="badge bg-success" title="${saglik.gecikme_ms}ms">${saglik.gecikme_ms}ms</span>`
            : `<span class="badge bg-danger">Erişilemiyor</span>`)
        : `<span class="badge bg-light text-muted">-</span>`;
      // Yön artık düz metin değil, DÜZENLENEBİLİR bir seçim kutusu: iki kamera
      // aynı bariyeri farklı açılardan izlediğinde biri yanlış yönle
      // tanımlanmış olabiliyor (bkz. README.md'deki 2026-09-17 notu) — bunu
      // düzeltmenin tek yolu artık kamerayı silip RTSP'yi elden yeniden
      // yazmak değil, burada tek tıkla değiştirmek (kamera id'si/RTSP'si hiç
      // değişmez, bkz. main.py::kamera_yon_degistir).
      const yonSecim = rolYeterli("operatör")
        ? `<select class="form-select form-select-sm" style="width:auto" onchange="kameraYonDegistir('${k.id}', this)">
             <option value="giris" ${k.yon === "giris" ? "selected" : ""}>Giriş</option>
             <option value="cikis" ${k.yon === "cikis" ? "selected" : ""}>Çıkış</option>
           </select>`
        : (k.yon === "giris" ? "Giriş" : "Çıkış");
      const roiRozeti = k.roi
        ? `<span class="badge bg-info-subtle text-info-emphasis ms-1" title="Tespit alanı sınırlı: yalnızca karenin %${Math.round(k.roi.x1)}-%${Math.round(k.roi.x2)} (yatay) / %${Math.round(k.roi.y1)}-%${Math.round(k.roi.y2)} (dikey) bölgesi geçerli"><i class="bi bi-crop"></i> Alan sınırlı</span>`
        : "";
      const roiBtn = rolYeterli("operatör")
        ? `<button class="btn btn-sm btn-outline-warning ms-1" title="Tespit alanını (ROI) ayarla" onclick="kameraRoiAc('${k.id}')"><i class="bi bi-crop"></i></button>`
        : "";
      const yenidenBtn = rolYeterli("operatör")
        ? `<button class="btn btn-sm btn-outline-secondary ms-1" title="Pipeline'ı yeniden başlat" onclick="kameraYenidenBaslat('${k.id}')"><i class="bi bi-arrow-repeat"></i></button>`
        : "";
      const silBtn = rolYeterli("operatör")
        ? `<button class="btn btn-sm btn-outline-danger" title="Kamerayı sil" onclick="kameraSil('${k.id}')"><i class="bi bi-trash"></i></button>`
        : "";
      return `<tr><td><strong>${escapeHtml(k.ad)}</strong>${roiRozeti}</td><td>${yonSecim}</td><td class="text-muted small text-truncate" style="max-width: 180px">${escapeHtml(k.rtsp_url)}</td><td>${durum}${yenidenBaglanmaBadge}</td><td>${tcpBadge}</td><td class="text-nowrap">${silBtn}${yenidenBtn}${roiBtn}</td></tr>`;
    }).join("") || '<tr><td colspan="6" class="text-center text-muted py-4">Henüz kamera tanımlanmadı</td></tr>';
    kameraDuvariniGuncelle(kameralar);
  } catch (err) { console.error(err); }
}

async function kameraYonDegistir(id, selectEl) {
  const eskiDeger = selectEl.value === "giris" ? "cikis" : "giris";  // geri almak için
  try {
    await apiCagir(`/kameralar/${id}/yon`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ yon: selectEl.value }),
    });
    toastGoster("Kamera yönü güncellendi, pipeline yeniden başlatılıyor.", "basari");
    kameralariYukle();
  } catch (err) {
    selectEl.value = eskiDeger;  // istek başarısızsa arayüzü eski haline döndür
    alert(err.message);
  }
}

// ---------------------- KAMERA TESPİT ALANI (ROI) ----------------------
// Giriş ve çıkış kameralarının açıları birbirinin şeridini de görüyorsa, bir
// araç her iki kamerada da tespit edilip hem "giriş" hem "çıkış" olarak ayrı
// ayrı kaydedilebiliyor (bkz. README.md'deki 2026-09-17 notu). Bu modal, canlı
// bir kare üzerinde yüzdesel bir dikdörtgen (ROI) tanımlayarak her kameranın
// SADECE kendi şeridine denk gelen bölgeyi izlemesini sağlar.

function _roiOnizlemeGuncelle() {
  const kutu = document.getElementById("roiKutuOnizleme");
  const x1 = parseFloat(document.getElementById("roiX1").value) || 0;
  const y1 = parseFloat(document.getElementById("roiY1").value) || 0;
  const x2 = parseFloat(document.getElementById("roiX2").value);
  const y2 = parseFloat(document.getElementById("roiY2").value);
  const x2Guvenli = isNaN(x2) ? 100 : x2;
  const y2Guvenli = isNaN(y2) ? 100 : y2;
  kutu.style.left = `${Math.max(0, Math.min(100, x1))}%`;
  kutu.style.top = `${Math.max(0, Math.min(100, y1))}%`;
  kutu.style.width = `${Math.max(0, Math.min(100, x2Guvenli) - Math.max(0, Math.min(100, x1)))}%`;
  kutu.style.height = `${Math.max(0, Math.min(100, y2Guvenli) - Math.max(0, Math.min(100, y1)))}%`;
}

["roiX1", "roiY1", "roiX2", "roiY2"].forEach(id => {
  document.getElementById(id)?.addEventListener("input", _roiOnizlemeGuncelle);
});

async function kameraRoiAc(id) {
  const kamera = _kameralarCache.find(k => k.id === id);
  if (!kamera) return;
  document.getElementById("roiKameraId").value = id;
  document.getElementById("roiKameraAdi").textContent = kamera.ad;
  document.getElementById("roiX1").value = kamera.roi ? Math.round(kamera.roi.x1) : "";
  document.getElementById("roiY1").value = kamera.roi ? Math.round(kamera.roi.y1) : "";
  document.getElementById("roiX2").value = kamera.roi ? Math.round(kamera.roi.x2) : "";
  document.getElementById("roiY2").value = kamera.roi ? Math.round(kamera.roi.y2) : "";
  document.getElementById("roiSonuc").textContent = "";
  _roiOnizlemeGuncelle();
  bootstrap.Modal.getOrCreateInstance(document.getElementById("kameraRoiModal")).show();
  // Anlık kare, diğer korumalı görseller gibi (bkz. korumaliGorselAta) token'lı
  // fetch + blob URL ile yüklenir -- ama o yardımcı fonksiyon sabit olarak
  // `/goruntuler/<dosya adı>` yoluna göre çalışıyor, burada ise doğrudan
  // `/kameralar/{id}/goruntu` uç noktasından ANLIK bir kare çekiliyor, bu
  // yüzden aynı desen (token + blob URL + eski blob'u serbest bırakma) burada
  // ayrıca uygulanıyor.
  const imgEl = document.getElementById("roiOnizlemeGorsel");
  try {
    const token = sessionStorage.getItem("pts_token");
    const yanit = await fetch(`/kameralar/${id}/goruntu`, { headers: { Authorization: `Bearer ${token}` } });
    if (yanit.ok) {
      const blob = await yanit.blob();
      const eskiUrl = _korumaliGorselBlobURLleri.get(imgEl);
      if (eskiUrl) URL.revokeObjectURL(eskiUrl);
      const url = URL.createObjectURL(blob);
      _korumaliGorselBlobURLleri.set(imgEl, url);
      imgEl.src = url;
    } else {
      document.getElementById("roiSonuc").textContent = "Kameradan anlık görüntü alınamadı (kamera durmuş olabilir) -- yine de yüzdeleri elle girip kaydedebilirsiniz.";
    }
  } catch (e) {
    document.getElementById("roiSonuc").textContent = "Kameradan anlık görüntü alınamadı -- yine de yüzdeleri elle girip kaydedebilirsiniz.";
  }
}

async function kameraRoiKaydet() {
  const id = document.getElementById("roiKameraId").value;
  const sonuc = document.getElementById("roiSonuc");
  const x1 = document.getElementById("roiX1").value;
  const y1 = document.getElementById("roiY1").value;
  const x2 = document.getElementById("roiX2").value;
  const y2 = document.getElementById("roiY2").value;
  if (x1 === "" || y1 === "" || x2 === "" || y2 === "") {
    sonuc.className = "small mt-2 text-danger";
    sonuc.textContent = "Dört değer de (Sol/Üst/Sağ/Alt) girilmeli. Sınırı tamamen kaldırmak için 'Sınırı Kaldır' butonunu kullanın.";
    return;
  }
  try {
    await apiCagir(`/kameralar/${id}/roi`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ x1: Number(x1), y1: Number(y1), x2: Number(x2), y2: Number(y2) }),
    });
    bootstrap.Modal.getInstance(document.getElementById("kameraRoiModal"))?.hide();
    toastGoster("Tespit alanı kaydedildi, pipeline yeniden başlatılıyor.", "basari");
    kameralariYukle();
  } catch (err) {
    sonuc.className = "small mt-2 text-danger"; sonuc.textContent = err.message;
  }
}

async function kameraRoiKaldir() {
  const id = document.getElementById("roiKameraId").value;
  const sonuc = document.getElementById("roiSonuc");
  try {
    await apiCagir(`/kameralar/${id}/roi`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ temizle: true }),
    });
    bootstrap.Modal.getInstance(document.getElementById("kameraRoiModal"))?.hide();
    toastGoster("Tespit alanı sınırı kaldırıldı.", "basari");
    kameralariYukle();
  } catch (err) {
    sonuc.className = "small mt-2 text-danger"; sonuc.textContent = err.message;
  }
}

// ---------------------- BAĞIMSIZ ZİYARETÇİ GİRİŞİ ----------------------
// Herhangi bir kamera tespitine bağlı olmadan (kağıt üstünde/telefonla önceden
// haber verilmiş bir ziyaretçi için) elle plaka girip hangi bariyerin
// açılacağını seçebileceğiniz form. Üç adımı tek düğmede birleştirir: (1)
// POST /kayitlar ile manuel bir geçiş kaydı oluşturur, (2) PATCH /kayitlar/{id}
// ile durumu "ziyaretci_onayli" yapıp (varsa) kişiye bağlar, (3) POST
// /bariyer/{id}/ac ile seçilen noktanın bariyerini fiilen açar. Hiçbiri için
// yeni bir backend uç noktası GEREKMEDİ (bkz. README'deki 2026-09-17
// "Ziyaretçi Girişi" notu).
async function ziyaretciBilgileriAc() {
  document.getElementById("zbPlaka").value = "";
  document.getElementById("zbNot").value = "";
  document.getElementById("zbSonuc").textContent = "";
  const kisiSecim = document.getElementById("zbKisiSecim");
  const noktaSecim = document.getElementById("zbNokta");
  kisiSecim.innerHTML = '<option value="">Kişiye bağlamadan devam et</option>';
  noktaSecim.innerHTML = '<option value="">Nokta seçiniz...</option>';
  try {
    const [kisiler, noktalar] = await Promise.all([
      apiCagir("/kisiler").catch(() => []),
      apiCagir("/noktalar").catch(() => []),
    ]);
    kisiSecim.innerHTML += kisiler.map(k =>
      `<option value="${k.id}">${escapeHtml(k.ad_soyad)} (${escapeHtml(k.plaka_no)}${k.daire_departman ? " · " + escapeHtml(k.daire_departman) : ""})</option>`
    ).join("");
    const bariyerliNoktalar = noktalar.filter(n => n.aktif && n.bariyer_id);
    noktaSecim.innerHTML += bariyerliNoktalar.map(n =>
      `<option value="${n.id}" data-bariyer-id="${n.bariyer_id}" data-yon="${n.yon}" data-kamera-id="${n.kamera_id || ""}">${escapeHtml(n.ad)} (${n.yon === "giris" ? "Giriş" : "Çıkış"})</option>`
    ).join("");
    if (bariyerliNoktalar.length === 0) {
      document.getElementById("zbSonuc").className = "small text-warning";
      document.getElementById("zbSonuc").textContent = "Bariyere bağlı hiçbir erişim noktası tanımlı değil (Site / Erişim Noktası'ndan bağlayın).";
    }
  } catch (err) {
    document.getElementById("zbSonuc").className = "small text-danger";
    document.getElementById("zbSonuc").textContent = err.message;
  }
  bootstrap.Modal.getOrCreateInstance(document.getElementById("ziyaretciBilgileriModal")).show();
}

// Bu formda plaka önceden bilinmediği (görevli elle yazdığı) için modal
// açılışında değil, plaka alanından çıkıldığında (blur) "son kullanılan not"
// önerisi denenir -- yalnızca not kutusu hâlâ boşsa doldurulur.
document.getElementById("zbPlaka")?.addEventListener("blur", async () => {
  const notEl = document.getElementById("zbNot");
  const plaka = document.getElementById("zbPlaka").value.trim();
  if (!plaka || !notEl || notEl.value) return;
  const oneri = await sonNotOnerisiGetir(plaka);
  if (oneri && !notEl.value) notEl.value = oneri;
});

async function ziyaretciBilgileriKaydet() {
  const sonuc = document.getElementById("zbSonuc");
  const plaka = document.getElementById("zbPlaka").value.trim();
  const noktaSecim = document.getElementById("zbNokta");
  const secilenSecenek = noktaSecim.selectedOptions[0];
  if (!plaka) { sonuc.className = "small text-danger"; sonuc.textContent = "Plaka gerekli."; return; }
  if (!noktaSecim.value) { sonuc.className = "small text-danger"; sonuc.textContent = "Açılacak bariyer/erişim noktası seçilmeli."; return; }

  const bariyerId = secilenSecenek.dataset.bariyerId;
  const yon = secilenSecenek.dataset.yon || "giris";
  const kameraId = secilenSecenek.dataset.kameraId || "PANEL-ZIYARETCI";
  const kisiId = document.getElementById("zbKisiSecim").value;
  const notMetni = document.getElementById("zbNot").value.trim();

  const btn = document.getElementById("zbKaydetBtn");
  btn.disabled = true;
  sonuc.className = "small"; sonuc.textContent = "İşleniyor...";
  try {
    const kayit = await apiCagir("/kayitlar", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plaka_no: plaka, kamera_id: kameraId, yon, not_metni: notMetni || null }),
    });
    const govde = { yetki_durumu: "ziyaretci_onayli" };
    if (kisiId) govde.kisi_id = Number(kisiId);
    await apiCagir(`/kayitlar/${kayit.id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(govde),
    });
    const r = await apiCagir(`/bariyer/${bariyerId}/ac`, { method: "POST" });
    toastGoster(`Ziyaretçi girişi kaydedildi, bariyer açıldı: ${plaka}`, "basari");
    sonuc.className = "small text-success";
    sonuc.textContent = r.mesaj;
    panelYenile();
    kayitlariYukle(false);
    setTimeout(() => bootstrap.Modal.getInstance(document.getElementById("ziyaretciBilgileriModal"))?.hide(), 900);
  } catch (err) {
    sonuc.className = "small text-danger";
    sonuc.textContent = err.message;
  } finally {
    btn.disabled = false;
  }
}

// Kamera başına açık MJPEG canlı akış bağlantısını (AbortController) tutar.
// Eskiden burada 3 saniyede bir tek kare çekilirdi (kesikli/adım adım görünüm);
// artık her kamera için TEK bir bağlantı açık kalır ve pipeline'ın ürettiği HER
// yeni kare anında gelir (bkz. _kameraAkisiBaslat, backend: /kameralar/{id}/akis).
let _kameraAkisAbortlar = {};
let _kameraPlakaInterval = null;

function _tumKameraAkislariniDurdur() {
  const eskiler = _kameraAkisAbortlar;
  _kameraAkisAbortlar = {};
  Object.values(eskiler).forEach(ctrl => { try { ctrl.abort(); } catch {} });
}

function _bayt_dizisi_bul(buf, dizi, baslangic = 0) {
  disForEach: for (let i = baslangic; i <= buf.length - dizi.length; i++) {
    for (let j = 0; j < dizi.length; j++) if (buf[i + j] !== dizi[j]) continue disForEach;
    return i;
  }
  return -1;
}

function _kameraAkisiBaslat(kameraId) {
  const ctrl = new AbortController();
  _kameraAkisAbortlar[kameraId] = ctrl;
  const token = sessionStorage.getItem("pts_token");
  const CRLFCRLF = [13, 10, 13, 10];
  let sonUrl = null;

  fetch(`/kameralar/${kameraId}/akis`, { headers: { Authorization: `Bearer ${token}` }, signal: ctrl.signal })
    .then(async (r) => {
      if (!r.ok || !r.body) throw new Error("Akış kurulamadı");
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = new Uint8Array(0);
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const birlesik = new Uint8Array(buf.length + value.length);
        birlesik.set(buf, 0); birlesik.set(value, buf.length);
        buf = birlesik;

        // Arabellekte tamamlanmış kare(ler) varsa hepsini ardarda işle
        // (Content-Length her zaman gönderildiği için ikili veri içinde sınır
        // dizisini aramaya HİÇ gerek yok — bu, bir JPEG'in tesadüfen sınıra
        // benzeyen baytlar içermesinden kaynaklanabilecek bozulmayı önler).
        while (true) {
          const baslikSonu = _bayt_dizisi_bul(buf, CRLFCRLF);
          if (baslikSonu === -1) break;
          const baslikMetni = dec.decode(buf.slice(0, baslikSonu));
          const eslesme = baslikMetni.match(/Content-Length:\s*(\d+)/i);
          if (!eslesme) { buf = new Uint8Array(0); break; }
          const uzunluk = parseInt(eslesme[1], 10);
          const govdeBas = baslikSonu + 4;
          const govdeBit = govdeBas + uzunluk;
          if (buf.length < govdeBit + 2) break; // kare henüz tam gelmedi
          const jpegBaytlari = buf.slice(govdeBas, govdeBit);
          const el = document.getElementById(`frame-${kameraId}`);
          if (el) {
            let img = el.querySelector("img.camera-frame-img");
            if (!img) {
              el.innerHTML = `<img class="camera-frame-img">`;
              el.style.padding = "0";
              img = el.querySelector("img");
            }
            const yeniUrl = URL.createObjectURL(new Blob([jpegBaytlari], { type: "image/jpeg" }));
            img.src = yeniUrl;
            if (sonUrl) URL.revokeObjectURL(sonUrl);
            sonUrl = yeniUrl;
          }
          buf = buf.slice(govdeBit + 2);
        }
      }
    })
    .catch(() => {})
    .finally(() => {
      // Kasıtlı olarak durdurulmadıysak (kontrolcü hâlâ bizim başlattığımızsa)
      // bağlantı koptuğunda (ağ sorunu, pipeline yeniden başlıyor vb.) kısa bir
      // bekleyle yeniden bağlan.
      if (_kameraAkisAbortlar[kameraId] === ctrl) {
        setTimeout(() => { if (_kameraAkisAbortlar[kameraId] === ctrl) _kameraAkisiBaslat(kameraId); }, 2000);
      }
    });
}

function kameraDuvariniGuncelle(kameralar) {
  const duvar = document.getElementById("kameraDuvari");
  const sayacBtn = document.getElementById("kameraSayacBtn");
  if (!duvar) return;
  if (sayacBtn) sayacBtn.innerHTML = `<i class="bi bi-grid-2x2"></i> ${kameralar.length} Kamera`;
  if (!kameralar.length) {
    duvar.innerHTML = `<div class="camera-tile camera-simulated"><div class="camera-label"><span><i class="bi bi-camera-video-fill me-1"></i>KAMERA TANIMLI DEĞİL</span><span class="camera-status">Simülasyon</span></div><div class="camera-empty"><i class="bi bi-camera-video"></i><strong>Henüz kamera eklenmedi</strong><small>Kamera Yönetimi ekranından RTSP kamera ekleyin</small></div></div>`;
    _tumKameraAkislariniDurdur();
    return;
  }
  duvar.innerHTML = kameralar.map(k => {
    const statusClass = !k.pipeline_calisiyor ? "camera-simulated" : (k.donmus ? "camera-frozen" : "camera-live");
    const statusText = !k.pipeline_calisiyor
      ? (k.kutuphaneler_mevcut ? "Bağlanmıyor" : "Simülasyon")
      : (k.donmus ? "Görüntü Donmuş" : "Canlı");
    const donmusUyarisi = (k.pipeline_calisiyor && k.donmus)
      ? `<div class="camera-frozen-banner"><i class="bi bi-exclamation-triangle-fill"></i> Görüntü ${k.son_kare_yasi_sn != null ? Math.round(k.son_kare_yasi_sn) + " sn" : ""} önceden beri güncellenmiyor — sistem otomatik yeniden bağlanmayı deniyor</div>`
      : "";
    return `<div class="camera-tile ${statusClass}" id="tile-${k.id}"><div class="camera-label"><span><i class="bi bi-camera-video-fill me-1"></i>${escapeHtml(k.ad).toUpperCase()}</span><span class="camera-status">${statusText}</span></div>${donmusUyarisi}<div class="camera-empty" id="frame-${k.id}"><i class="bi bi-camera-video"></i><strong>${k.yon === "giris" ? "Giriş" : "Çıkış"} kamerası</strong><small>${k.pipeline_calisiyor ? "Görüntü yükleniyor..." : (k.kutuphaneler_mevcut ? "Pipeline başlatılamadı" : "opencv + fast-alpr gerekli")}</small></div></div>`;
  }).join("");

  // Pipeline çalışan kameralar için canlı MJPEG akışını başlat (bkz. yukarıdaki
  // _kameraAkisiBaslat) — artık periyodik "anlık görüntü" çekmiyoruz, tek bir
  // bağlantı üzerinden her yeni kare geldiği an ekrana yansıyor.
  _tumKameraAkislariniDurdur();
  const canliKameralar = kameralar.filter(k => k.pipeline_calisiyor);
  if (canliKameralar.length) {
    canliKameralar.forEach(k => _kameraAkisiBaslat(k.id));

    // Son plaka overlay — 2 sn'de bir güncelle
    if (_kameraPlakaInterval) clearInterval(_kameraPlakaInterval);
    const _plakalariGuncelle = () => {
      canliKameralar.forEach(async k => {
        try {
          const token = sessionStorage.getItem("pts_token");
          const r = await fetch(`/kameralar/${k.id}/son-plaka`, { headers: { Authorization: `Bearer ${token}` } });
          if (!r.ok) return;
          const veri = await r.json();
          const tile = document.getElementById(`tile-${k.id}`);
          if (!tile) return;
          let overlay = tile.querySelector(".plaka-overlay");
          if (veri.tespitler?.length) {
            const t = veri.tespitler[0];
            if (!overlay) {
              overlay = document.createElement("div");
              overlay.className = "plaka-overlay";
              tile.appendChild(overlay);
            }
            overlay.textContent = `${t.plaka}  ${(t.guven * 100).toFixed(0)}%`;
            overlay.className = "plaka-overlay";
            overlay._timeout && clearTimeout(overlay._timeout);
            overlay._timeout = setTimeout(() => overlay.remove(), 8000);
          }
        } catch {}
      });
    };
    _plakalariGuncelle();
    _kameraPlakaInterval = setInterval(_plakalariGuncelle, 2000);
  }
}

document.getElementById("kameraForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const sonuc = document.getElementById("kameraSonuc");
  try {
    await apiCagir("/kameralar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ad: document.getElementById("kameraAd").value, rtsp_url: document.getElementById("kameraRtsp").value, yon: document.getElementById("kameraYon").value }) });
    sonuc.className = "small mt-3 text-success"; sonuc.textContent = "Kamera kaydedildi."; e.target.reset(); kameralariYukle();
  } catch (err) { sonuc.className = "small mt-3 text-danger"; sonuc.textContent = err.message; }
});

async function kameraSil(id) {
  if (!confirm("Bu kamerayı silmek istediğinize emin misiniz?")) return;
  await apiCagir(`/kameralar/${id}`, { method: "DELETE" });
  kameralariYukle();
}
async function kameraYenidenBaslat(id) {
  try {
    const sonuc = await apiCagir(`/kameralar/${id}/yeniden-baslat`, { method: "POST" });
    if (sonuc.basarili) {
      alert("Pipeline yeniden başlatıldı.");
    } else if (!sonuc.kutuphaneler_mevcut) {
      alert("Gerekli kütüphaneler kurulu değil.\npip install \"fast-alpr[onnx]\" opencv-python requests");
    } else {
      alert("Pipeline başlatılamadı. Log dosyasını kontrol edin.");
    }
    kameralariYukle();
  } catch (err) { alert(err.message); }
}
document.getElementById("lisansForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const sonuc = document.getElementById("lisansSonuc");
  try { await apiCagir("/lisans/aktive-et", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ anahtar: document.getElementById("lisansAnahtari").value }) }); sonuc.className = "small mt-2 text-success"; sonuc.textContent = "Lisans başarıyla aktive edildi."; lisansYukle(); } catch (err) { sonuc.className = "small mt-2 text-danger"; sonuc.textContent = err.message; }
});

// ---------------------- KAYITLAR (sayfalama destekli) ----------------------

let _kayitlarSayfa = 0;
const _kayitlarLimit = 50;

// Otomatik arka plan yenilemesi (bkz. _canliBolumleriTazeleDebounce ve
// aşağıdaki 15 sn'lik yedek polling) kullanıcı tam o anda Kayıtlar filtre
// alanlarından birine yazı yazıyorken tabloyu ELİNİN ALTINDAN değiştirip
// yarım kalan aramasını bozmasın diye bu durumu tespit eder.
function _kayitlarFiltresiDuzenleniyorMu() {
  const aktif = document.activeElement;
  return !!aktif && ["filtrePlaka", "filtreBaslangic", "filtreBitis", "filtreDurum"].includes(aktif.id);
}

function filtreParametreleri() {
  const params = new URLSearchParams();
  const plaka = document.getElementById("filtrePlaka").value.trim();
  const baslangic = document.getElementById("filtreBaslangic").value;
  const bitis = document.getElementById("filtreBitis").value;
  const durum = document.getElementById("filtreDurum").value;
  if (plaka) params.set("plaka", plaka);
  if (baslangic) params.set("baslangic", baslangic);
  if (bitis) params.set("bitis", bitis);
  if (durum) params.set("yetki_durumu", durum);
  params.set("limit", _kayitlarLimit);
  params.set("offset", _kayitlarSayfa * _kayitlarLimit);
  return params;
}

async function kayitlariYukle(sifirla = true) {
  if (sifirla) _kayitlarSayfa = 0;
  const params = filtreParametreleri();
  const [kayitlar, sayfaBilgisi] = await Promise.all([
    apiCagir(`/kayitlar?${params.toString()}`),
    apiCagir(`/kayitlar/sayfa-bilgisi?${new URLSearchParams({
      plaka: document.getElementById("filtrePlaka").value.trim(),
      baslangic: document.getElementById("filtreBaslangic").value,
      bitis: document.getElementById("filtreBitis").value,
      yetki_durumu: document.getElementById("filtreDurum").value,
      limit: _kayitlarLimit,
    }).toString()}`),
  ]);
  sonKayitlarCache = [...sonKayitlarCache.filter(k => !kayitlar.find(n => n.id === k.id)), ...kayitlar];
  const el = document.getElementById("kayitlarSayac");
  if (el) el.textContent = `${sayfaBilgisi.toplam} kayıt · Sayfa ${_kayitlarSayfa + 1}/${sayfaBilgisi.sayfa_sayisi}`;
  const tbody = document.getElementById("kayitlarTablo");
  tbody.innerHTML = kayitlar.map(k => `
    <tr>
      <td>${k.goruntu_yolu ? `<img class="thumb" data-goruntu-yolu="${escapeHtml(k.goruntu_yolu)}" role="button" tabindex="0" alt="Geçiş görseli, büyütmek için tıklayın veya Enter'a basın">` : '<span class="text-muted small">-</span>'}</td>
      <td>${k.id}</td>
      <td class="fw-bold"><button class="plate-link" data-plaka-analiz="${escapeHtml(k.plaka_no)}">${escapeHtml(k.plaka_no)}</button></td>
      <td>${tarihFormatla(k.tarih_saat)}</td>
      <td>${escapeHtml(k.kamera_id)}</td>
      <td>${k.yon === "giris" ? "Giriş" : "Çıkış"}</td>
      <td>${durumRozeti(k.yetki_durumu)}</td>
      <td>${tipRozeti(k.kisi_tip_anlik)}</td>
      <td>${k.guven_skoru ? (k.guven_skoru * 100).toFixed(0) + "%" : "-"}</td>
      <td>${dogrulamaRozeti(k.dogrulama_kare_sayisi, k.farkli_okuma_sayisi)}</td>
      <td class="text-nowrap">
        <button class="btn btn-sm btn-outline-danger" onclick="kayitPdfIndir(${k.id})" title="PDF indir" aria-label="PDF indir"><i class="bi bi-file-earmark-pdf"></i></button>
        ${rolYeterli("operatör") ? `<button class="btn btn-sm btn-outline-primary ms-1" onclick="kayitDuzenleAc(${k.id})" title="Kaydı düzenle" aria-label="Kaydı düzenle"><i class="bi bi-pencil"></i></button>` : ""}
        ${rolYeterli("yonetici") ? `<button class="btn btn-sm btn-outline-secondary ms-1" onclick="kayitSil(${k.id})" title="Kaydı sil" aria-label="Kaydı sil"><i class="bi bi-trash"></i></button>` : ""}
      </td>
    </tr>
  `).join("") || `<tr><td colspan="11" class="text-center text-muted py-3">Kayıt bulunamadı</td></tr>`;
  korumaliGorselleriYukle(tbody);

  // Sayfalama kontrolleri
  const sayfaEl = document.getElementById("sayfalama");
  if (sayfaEl) {
    const onceki = _kayitlarSayfa > 0;
    const sonraki = _kayitlarSayfa < sayfaBilgisi.sayfa_sayisi - 1;
    sayfaEl.innerHTML = `
      <div class="d-flex gap-2">
        <button class="btn btn-sm btn-outline-secondary" ${!onceki ? "disabled" : ""} onclick="sayfaDegistir(-1)"><i class="bi bi-chevron-left"></i> Önceki</button>
        <button class="btn btn-sm btn-outline-secondary" ${!sonraki ? "disabled" : ""} onclick="sayfaDegistir(1)">Sonraki <i class="bi bi-chevron-right"></i></button>
      </div>
      <span class="small text-muted">${_kayitlarSayfa * _kayitlarLimit + 1}–${Math.min((_kayitlarSayfa + 1) * _kayitlarLimit, sayfaBilgisi.toplam)} / ${sayfaBilgisi.toplam}</span>`;
  }
}

function sayfaDegistir(delta) {
  _kayitlarSayfa = Math.max(0, _kayitlarSayfa + delta);
  kayitlariYukle(false);
}

function disaAktar(tur) {
  const params = filtreParametreleri();
  window.open(indirmeUrlOlustur(`/disa-aktar/${tur}/kayitlar`, params), "_blank");
}

function kayitPdfIndir(id) {
  window.open(indirmeUrlOlustur(`/disa-aktar/pdf/kayit/${id}`), "_blank");
}

// Bir geçiş kaydını (plaka, yön, durum, kişi eşleştirmesi, not) panelden tam
// düzenleyebilmek için (bkz. main.py::kayit_duzenle). Örn. OCR'ın "39 SU 877"yi
// tek bir karede "04 SD 377" olarak yanlış okuyup kaydettiği bir vakada,
// operatör plakayı düzeltebilir ya da kaydı doğrulayabilir/not düşebilir.
async function kayitDuzenleAc(id) {
  const kayit = sonKayitlarCache.find(k => k.id === id);
  if (!kayit) return;
  document.getElementById("duzenleKayitId").value = id;
  document.getElementById("duzenleKayitPlaka").value = kayit.plaka_no;
  document.getElementById("duzenleKayitYon").value = kayit.yon;
  document.getElementById("duzenleKayitDurum").value = kayit.yetki_durumu;
  document.getElementById("duzenleKayitNot").value = kayit.not_metni || "";
  if (!kayit.not_metni) {
    // Bu kaydın kendi notu yoksa, aynı plakanın bugün için "son kullanılan
    // not" önerisini asenkron olarak dener (bkz. sonNotOnerisiGetir).
    sonNotOnerisiGetir(kayit.plaka_no).then(oneri => {
      const notEl = document.getElementById("duzenleKayitNot");
      if (oneri && notEl && !notEl.value) notEl.value = oneri;
    });
  }
  document.getElementById("duzenleKayitSonuc").textContent = "";
  const denetim = document.getElementById("duzenleKayitDenetim");
  denetim.textContent = kayit.duzenleyen
    ? `Son düzenleyen: ${kayit.duzenleyen} · ${tarihFormatla(kayit.duzenleme_tarihi)}`
    : (kayit.manuel_giris ? "Bu kayıt manuel olarak eklendi." : "");

  const kisiSecim = document.getElementById("duzenleKayitKisi");
  kisiSecim.innerHTML = '<option value="">Eşleştirme yok</option>';
  try {
    const kisiler = await apiCagir("/kisiler");
    kisiSecim.innerHTML += kisiler.map(k =>
      `<option value="${k.id}">${escapeHtml(k.ad_soyad)} (${escapeHtml(k.plaka_no)})</option>`
    ).join("");
    if (kayit.kisi_id) kisiSecim.value = String(kayit.kisi_id);
  } catch (e) { /* kişi listesi yüklenemezse eşleştirme alanı boş kalır, kritik değil */ }

  bootstrap.Modal.getOrCreateInstance(document.getElementById("kayitDuzenleModal")).show();
}

document.getElementById("kayitDuzenleForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("duzenleKayitId").value;
  const kayit = sonKayitlarCache.find(k => k.id === Number(id));
  const kisiSecim = document.getElementById("duzenleKayitKisi").value;
  const sonuc = document.getElementById("duzenleKayitSonuc");
  const govde = {
    plaka_no: document.getElementById("duzenleKayitPlaka").value,
    yon: document.getElementById("duzenleKayitYon").value,
    yetki_durumu: document.getElementById("duzenleKayitDurum").value,
    not_metni: document.getElementById("duzenleKayitNot").value || null,
  };
  if (kisiSecim) {
    govde.kisi_id = Number(kisiSecim);
  } else if (kayit?.kisi_id) {
    govde.kisi_id_temizle = true;
  }
  try {
    await apiCagir(`/kayitlar/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(govde) });
    bootstrap.Modal.getInstance(document.getElementById("kayitDuzenleModal"))?.hide();
    kayitlariYukle(false);
    panelYenile();
    analizAcikSeAyniPlakayiYenile();
  } catch (err) {
    sonuc.className = "small text-danger"; sonuc.textContent = err.message;
  }
});

async function kayitSil(id) {
  if (!confirm("Bu geçiş kaydını kalıcı olarak silmek istediğinize emin misiniz? Bu işlem geri alınamaz.")) return;
  try {
    await apiCagir(`/kayitlar/${id}`, { method: "DELETE" });
    kayitlariYukle(false);
    panelYenile();
    analizAcikSeAyniPlakayiYenile();
  } catch (e) {
    alert(e.message);
  }
}

// Kayıt düzenleme/silme, hem "Kayıtlar" tablosundan hem de "Plaka Analizi"
// modalinin kendi içinden (aynı düzenle/sil butonları tekrar kullanılarak)
// tetiklenebiliyor. İkinci durumda, işlem bitince analiz modalindeki liste
// ve istatistiklerin bayatlamaması için modal hâlâ açıksa aynı plaka için
// yeniden yüklenir.
function analizAcikSeAyniPlakayiYenile() {
  const modalEl = document.getElementById("plakaAnalizModal");
  const gosterilenPlaka = document.getElementById("analizPlaka")?.textContent;
  if (modalEl && modalEl.classList.contains("show") && gosterilenPlaka) {
    plakaAnalizAc(gosterilenPlaka);
  }
}

// ---------------------- KİŞİLER ----------------------

let aktifTipFiltre = "";

function ziyaretciAlanGoster() {
  const tip = document.getElementById("kisiTip").value;
  document.getElementById("ziyaretciBitisAlani").classList.toggle("d-none", tip !== "ziyaretci");
  document.getElementById("daireEtiket").textContent = tip === "personel" ? "Departman" : "Daire No";
}

function kisiTipFiltrele(tip, btn) {
  aktifTipFiltre = tip;
  document.querySelectorAll(".tip-filtre").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  kisileriYukle();
}

async function kisileriYukle() {
  const params = new URLSearchParams();
  if (aktifTipFiltre) params.set("tip", aktifTipFiltre);
  const kisiler = await apiCagir(`/kisiler?${params.toString()}`);
  const tbody = document.getElementById("kisilerTablo");
  tbody.innerHTML = kisiler.map(k => `
    <tr>
      <td>${escapeHtml(k.ad_soyad)}</td>
      <td class="fw-bold"><button class="plate-link" data-plaka-analiz="${escapeHtml(k.plaka_no)}" title="Geçiş geçmişini ve görsellerini gör">${escapeHtml(k.plaka_no)}</button></td>
      <td>${tipRozeti(k.tip)}</td>
      <td>${escapeHtml(k.telefon) || "-"}</td>
      <td>${escapeHtml(k.daire_departman) || "-"}</td>
      <td>${k.aktif ? '<span class="badge bg-success">Aktif</span>' : '<span class="badge bg-secondary">Pasif</span>'}</td>
      <td>
        ${rolYeterli("operatör") ? `
        <button class="btn btn-sm btn-outline-primary" onclick="kisiDuzenleAc(${k.id})" title="Düzenle"><i class="bi bi-pencil"></i></button>
        <button class="btn btn-sm btn-outline-secondary" onclick="kisiDurumDegistir(${k.id}, ${!k.aktif})" title="Aktif/Pasif Yap"><i class="bi bi-toggle2-on"></i></button>
        <button class="btn btn-sm btn-outline-warning" onclick="kisiGecmisKayitlariGuncelle(${k.id})" title="Bu kişinin plakasına ait, kaydedilmeden ÖNCEKİ eski 'yetkisiz' geçişleri yeniden değerlendirir"><i class="bi bi-clock-history"></i></button>
        <button class="btn btn-sm btn-outline-danger" onclick="kisiSil(${k.id})" title="Sil"><i class="bi bi-trash"></i></button>
        ` : '<span class="text-muted small">-</span>'}
      </td>
    </tr>
  `).join("") || `<tr><td colspan="7" class="text-center text-muted py-3">Kişi bulunamadı</td></tr>`;
}

document.getElementById("kisiForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const secilenGunler = [...document.querySelectorAll("#kisiGunler input:checked")].map(c => c.value);
  const gövde = {
    ad_soyad: document.getElementById("kisiAdSoyad").value,
    plaka_no: document.getElementById("kisiPlaka").value,
    tip: document.getElementById("kisiTip").value,
    telefon: document.getElementById("kisiTelefon").value || null,
    daire_departman: document.getElementById("kisiDaire").value || null,
    aciklama: document.getElementById("kisiAciklama").value || null,
    bitis_tarihi: document.getElementById("kisiBitisTarihi").value || null,
    giris_saati_baslangic: document.getElementById("kisiSaatBaslangic").value || null,
    giris_saati_bitis: document.getElementById("kisiSaatBitis").value || null,
    izin_verilen_gunler: secilenGunler.length ? secilenGunler.join(",") : null,
  };
  try {
    await apiCagir("/kisiler", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(gövde) });
    document.getElementById("kisiForm").reset();
    ziyaretciAlanGoster();
    kisileriYukle(); panelYenile();
  } catch (err) { alert("Hata: " + err.message); }
});

async function kisiDurumDegistir(id, yeniDurum) {
  await apiCagir(`/kisiler/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ aktif: yeniDurum }),
  });
  kisileriYukle();
  panelYenile();
}

async function kisiSil(id) {
  if (!confirm("Bu kişiyi silmek istediğinize emin misiniz?")) return;
  await apiCagir(`/kisiler/${id}`, { method: "DELETE" });
  kisileriYukle();
  panelYenile();
}

// 2026-09-18: kullanıcı bildirimi -- bir araç personel/abone olarak
// kaydedildikten SONRA yeni kamera tespitleri doğru şekilde "yetkili"
// gösteriliyor, ama kayıttan ÖNCEKİ eski tespitler "yetkisiz" olarak kalıyor
// (bu, o an henüz kişi tanımlı olmadığı için beklenen bir davranış). Bu kişi
// eklendiğinde/düzenlendiğinde arka planda ZATEN otomatik düzeltiliyor
// (bkz. backend/main.py::_gecmis_kayitlari_kisiye_bagla) -- bu düğme, bu
// özellik eklenmeden ÖNCE kaydedilmiş kişiler için elle tetiklemeyi sağlar.
async function kisiGecmisKayitlariGuncelle(id) {
  try {
    const sonuc = await apiCagir(`/kisiler/${id}/gecmis-kayitlari-guncelle`, { method: "POST" });
    if (sonuc.guncellenen_kayit_sayisi > 0) {
      alert(`${sonuc.guncellenen_kayit_sayisi} adet geçmiş kayıt bu kişiyle güncellendi (artık "Yetkili" görünecek).`);
      panelYenile();
    } else {
      alert("Bu kişiye ait güncellenecek geçmiş kayıt bulunamadı (zaten hepsi güncel ya da eşleşen kayıt yok).");
    }
  } catch (err) {
    alert("Hata: " + err.message);
  }
}

function kisilerExcelIndir() {
  const params = new URLSearchParams();
  if (aktifTipFiltre) params.set("tip", aktifTipFiltre);
  window.open(indirmeUrlOlustur("/disa-aktar/excel/kisiler", params), "_blank");
}

function kisiIceAktarmaSablonuIndir() {
  window.open(indirmeUrlOlustur("/kisiler/toplu-import/sablon"), "_blank");
}

function duzenleZiyaretciAlanGoster() {
  const tip = document.getElementById("duzenleTip").value;
  document.getElementById("duzenleZiyaretciBitisAlani").classList.toggle("d-none", tip !== "ziyaretci");
  document.getElementById("duzenleDaireEtiket").textContent = tip === "personel" ? "Departman" : "Daire No";
}

async function kisiDuzenleAc(id) {
  const kisi = await apiCagir(`/kisiler/${id}`);
  document.getElementById("duzenleId").value = kisi.id;
  document.getElementById("duzenleTip").value = kisi.tip;
  document.getElementById("duzenleAdSoyad").value = kisi.ad_soyad;
  document.getElementById("duzenlePlaka").value = kisi.plaka_no;
  document.getElementById("duzenleTelefon").value = kisi.telefon || "";
  document.getElementById("duzenleDaire").value = kisi.daire_departman || "";
  document.getElementById("duzenleAciklama").value = kisi.aciklama || "";
  document.getElementById("duzenleBitisTarihi").value = kisi.bitis_tarihi ? kisi.bitis_tarihi.slice(0, 16) : "";
  document.getElementById("duzenleSonuc").textContent = "";
  duzenleZiyaretciAlanGoster();
  bootstrap.Modal.getOrCreateInstance(document.getElementById("kisiDuzenleModal")).show();
}

document.getElementById("kisiDuzenleForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("duzenleId").value;
  const sonuc = document.getElementById("duzenleSonuc");
  const gövde = {
    ad_soyad: document.getElementById("duzenleAdSoyad").value,
    plaka_no: document.getElementById("duzenlePlaka").value,
    tip: document.getElementById("duzenleTip").value,
    telefon: document.getElementById("duzenleTelefon").value || null,
    daire_departman: document.getElementById("duzenleDaire").value || null,
    aciklama: document.getElementById("duzenleAciklama").value || null,
    bitis_tarihi: document.getElementById("duzenleBitisTarihi").value || null,
  };
  try {
    await apiCagir(`/kisiler/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(gövde),
    });
    bootstrap.Modal.getInstance(document.getElementById("kisiDuzenleModal")).hide();
    kisileriYukle();
    panelYenile();
  } catch (err) {
    sonuc.className = "small text-danger"; sonuc.textContent = err.message;
  }
});

// ---------------------- LED PANEL ----------------------

function ledModDegisti() {
  const mod = document.getElementById("ledMod").value;
  document.getElementById("ledSerialAlani").classList.toggle("d-none", mod !== "serial");
  document.getElementById("ledTcpAlani").classList.toggle("d-none", mod !== "tcp");
}

async function ledAyarlariYukle() {
  const ayarlar = await apiCagir("/led/ayarlar");
  document.getElementById("ledMod").value = ayarlar.led_mod;
  document.getElementById("ledSerialPort").value = ayarlar.serial_port;
  document.getElementById("ledBaudrate").value = ayarlar.serial_baudrate;
  document.getElementById("ledTcpHost").value = ayarlar.tcp_host;
  document.getElementById("ledTcpPort").value = ayarlar.tcp_port;
  ledModDegisti();
}

document.getElementById("ledForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const gövde = {
    led_mod: document.getElementById("ledMod").value,
    serial_port: document.getElementById("ledSerialPort").value,
    serial_baudrate: parseInt(document.getElementById("ledBaudrate").value) || 9600,
    tcp_host: document.getElementById("ledTcpHost").value,
    tcp_port: parseInt(document.getElementById("ledTcpPort").value) || 5000,
  };
  await apiCagir("/led/ayarlar", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(gövde),
  });
  alert("LED ayarları kaydedildi.");
});

async function ledTestGonder() {
  const mesaj = document.getElementById("ledTestMesaj").value;
  const sonuc = await apiCagir(`/led/test?mesaj=${encodeURIComponent(mesaj)}`, { method: "POST" });
  document.getElementById("ledTestSonuc").innerHTML = sonuc.basarili
    ? `<div class="alert alert-success mb-0">Mesaj gönderildi: "${escapeHtml(sonuc.mesaj)}"</div>`
    : `<div class="alert alert-danger mb-0">Mesaj gönderilemedi. Ayarları ve bağlantıyı kontrol edin.</div>`;
}

// ---------------------- TEST KAYDI EKLE ----------------------

document.getElementById("testKayitForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const gövde = {
    plaka_no: document.getElementById("testPlaka").value,
    kamera_id: document.getElementById("testKamera").value,
    yon: document.getElementById("testYon").value,
  };
  try {
    const kayit = await apiCagir("/kayitlar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(gövde),
    });
    document.getElementById("testSonuc").innerHTML = `
      <div class="alert alert-info">
        Kayıt oluşturuldu: <b>${escapeHtml(kayit.plaka_no)}</b> — Durum: ${durumRozeti(kayit.yetki_durumu)}
      </div>`;
    document.getElementById("testKayitForm").reset();
    panelYenile();
  } catch (err) {
    alert("Hata: " + err.message);
  }
});

// ---------------------- BAŞLANGIÇ ----------------------

authBaslat().then(() => {
  ziyaretciAlanGoster();
  // SSE bağlıysa (gerçek zamanlı olaylar zaten Panel+Kayıtlar'ı tazeliyor,
  // bkz. _sseKayitAl -> _canliBolumleriTazeleDebounce) bu yedek polling'e
  // gerek yok; SSE bağlı DEĞİLSE (bağlantı koptu/henüz kurulmadıysa) 15
  // sn'de bir Panel VE Kayıtlar sekmesi otomatik olarak yeniden yüklenir --
  // kullanıcının müdahalesi olmadan sayfa arka planda kendini güncel tutar.
  setInterval(() => {
    if (sessionStorage.getItem("pts_token") && !_sseAktif) {
      panelYenile();
      if (!_kayitlarFiltresiDuzenleniyorMu()) kayitlariYukle(false);
    }
  }, 15000);
});

// ================================================================
// TOAST BİLDİRİMLER
// ================================================================

function toastGoster(mesaj, tip = "bilgi") {
  const renkler = { bilgi: "bg-primary", basari: "bg-success", uyari: "bg-warning text-dark", hata: "bg-danger", kara: "bg-dark" };
  const id = "toast_" + Date.now();
  const html = `<div id="${id}" class="toast align-items-center text-white ${renkler[tip] || "bg-primary"} border-0" role="alert" aria-live="assertive" data-bs-delay="5000">
    <div class="d-flex"><div class="toast-body fw-semibold">${escapeHtml(mesaj)}</div>
    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div></div>`;
  const kont = document.getElementById("toastKonteyneri");
  kont.insertAdjacentHTML("beforeend", html);
  const el = document.getElementById(id);
  bootstrap.Toast.getOrCreateInstance(el).show();
  el.addEventListener("hidden.bs.toast", () => el.remove());
}

// ================================================================
// SSE — GERÇEK ZAMANLI PLAKA BİLDİRİMLERİ
// ================================================================

let _sseAktif = false;
let _sseYenidenBaglaSayaci = 0;

function sseBaslat() {
  const token = sessionStorage.getItem("pts_token");
  if (!token || _sseAktif) return;

  // NOT: Tarayıcının yerleşik EventSource API'si Authorization header'ı
  // desteklemez, bu yüzden burada KULLANILMIYOR — token'ı gerçekten taşıyan
  // ve akışı işleyen tek mekanizma aşağıdaki fetch tabanlı _sseBaslatFetch().
  // (Önceden burada kimliksiz bir `new EventSource(...)` de oluşturuluyordu;
  // backend'e header'sız gerçek bir istek atıp her seferinde 401 ile
  // reddediliyordu ve hiçbir yerde kullanılmıyordu — konsolu kirleten ölü
  // koddu, kaldırıldı.)
  _sseBaslatFetch(token);
}

function _sseBaslatFetch(token) {
  if (_sseAktif) return;
  _sseAktif = true;
  _sseYenidenBaglaSayaci++;

  const ctrl = new AbortController();
  fetch("/olaylar/sse", { headers: { Authorization: `Bearer ${token}` }, signal: ctrl.signal })
    .then(async (r) => {
      if (!r.ok || !r.body) throw new Error("SSE bağlantısı kurulamadı");
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let tampon = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        tampon += dec.decode(value, { stream: true });
        const satirlar = tampon.split("\n");
        tampon = satirlar.pop();
        let olay = "", veri = "";
        for (const satir of satirlar) {
          if (satir.startsWith("event: ")) olay = satir.slice(7).trim();
          else if (satir.startsWith("data: ")) veri = satir.slice(6).trim();
          else if (satir === "" && veri) {
            try {
              const nesne = JSON.parse(veri);
              if (olay === "kayit") _sseKayitAl(nesne);
            } catch { }
            olay = ""; veri = "";
          }
        }
      }
    })
    .catch(() => { })
    .finally(() => {
      _sseAktif = false;
      // Yeniden bağlan (max 5 dk bekleme)
      const bekleme = Math.min(2000 * Math.pow(1.5, _sseYenidenBaglaSayaci - 1), 300000);
      setTimeout(() => { if (sessionStorage.getItem("pts_token")) _sseBaslatFetch(sessionStorage.getItem("pts_token")); }, bekleme);
    });
}

function _sseKayitAl(kayit) {
  sonKayitlarCache.unshift(kayit);
  if (sonKayitlarCache.length > 500) sonKayitlarCache.pop();

  const tip = kayit.yetki_durumu === "yetkili" ? "basari"
    : kayit.yetki_durumu === "kara_liste" ? "kara"
    : "uyari";
  const yon = kayit.yon === "giris" ? "Giriş" : "Çıkış";
  toastGoster(`${kayit.plaka_no} · ${yon} · ${kayit.kamera_id}`, tip);

  // Panel'deki canlı olay listesini anlık güncelle (sıfır gecikmeli ilk his)
  const canliOlaylar = document.getElementById("canliOlaylar");
  if (canliOlaylar) {
    const yeniSatir = `<button class="event-row event-button" onclick="olayDetayAc(${kayit.id})"><div class="event-icon ${kayit.yetki_durumu === "yetkili" ? "allowed" : "blocked"}"><i class="bi ${kayit.yon === "giris" ? "bi-box-arrow-in-right" : "bi-box-arrow-right"}"></i></div><div class="event-main"><strong>${escapeHtml(kayit.plaka_no)}</strong><span>${escapeHtml(kayit.kamera_id)} · ${yon}</span></div><div class="event-time">${new Date(kayit.tarih_saat).toLocaleTimeString("tr-TR")}</div></button>`;
    canliOlaylar.insertAdjacentHTML("afterbegin", yeniSatir);
    // 8'den fazla satır varsa sonuncuları kaldır
    const satirlar = canliOlaylar.querySelectorAll(".event-button");
    if (satirlar.length > 8) satirlar[satirlar.length - 1].remove();
  }

  // Yenileme zamanını güncelle
  const el = document.getElementById("canliYenileme");
  if (el) el.textContent = new Date().toLocaleTimeString("tr-TR");

  // Kullanıcı hiçbir şey yapmadan Panel VE Kayıtlar bölümlerinin kendiliğinden
  // tazelenmesi isteniyor (araç girişi/çıkışı olduğunda) -- yukarıdaki anlık
  // DOM yaması sadece "canlı olaylar" listesini ve toast'u günceller; panel
  // sayaçları (toplam/bugünkü/yetkisiz/araç içeride/kara liste vb.) ve
  // Kayıtlar sekmesindeki tam tablo bundan etkilenmez. Bu yüzden her SSE
  // olayında ikisini de arka planda tam olarak yeniden yüklüyoruz.
  _canliBolumleriTazeleDebounce();
}

// Aynı anda birden fazla araç geçtiğinde (art arda gelen SSE olaylarında)
// panel+kayıtlar'ı her olay için ayrı ayrı değil, kısa bir pencerede TEK
// seferde tazelemek için debounce edilir -- gereksiz API isteği yığılmasını
// önler.
let _canliYenilemeZamanlayici = null;
function _canliBolumleriTazeleDebounce() {
  if (_canliYenilemeZamanlayici) return;
  _canliYenilemeZamanlayici = setTimeout(async () => {
    _canliYenilemeZamanlayici = null;
    try { await panelYenile(); } catch (e) { console.error("Panel otomatik yenileme hatası:", e); }
    if (!_kayitlarFiltresiDuzenleniyorMu()) {
      try { await kayitlariYukle(false); } catch (e) { console.error("Kayıtlar otomatik yenileme hatası:", e); }
    }
  }, 400);
}

// ================================================================
// DASHBOARD GRAFİKLERİ (Chart.js)
// ================================================================

let _gunlukGrafik = null;
let _yetkiPie = null;

async function grafikYukle() {
  const gun = document.getElementById("grafikGunSec")?.value || 7;
  try {
    const veri = await apiCagir(`/kayitlar/grafik?gun=${gun}`);
    _gunlukGrafigCiz(veri.gunluk);
    _yetkiPieCiz(veri.yetki_dagilimi);
  } catch (e) { console.error(e); }
}

function _gunlukGrafigCiz(gunluk) {
  const etiketler = Object.keys(gunluk).sort();
  const toplam = etiketler.map(g => gunluk[g].toplam);
  const yetkili = etiketler.map(g => gunluk[g].yetkili);
  const yetkisiz = etiketler.map(g => gunluk[g].yetkisiz + (gunluk[g].kara_liste || 0));

  if (_gunlukGrafik) _gunlukGrafik.destroy();
  const ctx = document.getElementById("gunlukGrafik");
  if (!ctx) return;
  _gunlukGrafik = new Chart(ctx, {
    type: "bar",
    data: {
      labels: etiketler.map(g => g.slice(5)),
      datasets: [
        { label: "Toplam", data: toplam, backgroundColor: "#6ea8fe55", borderColor: "#6ea8fe", borderWidth: 1 },
        { label: "Yetkili", data: yetkili, backgroundColor: "#75b79855", borderColor: "#75b798", borderWidth: 1 },
        { label: "Yetkisiz/Engel", data: yetkisiz, backgroundColor: "#ea868f55", borderColor: "#ea868f", borderWidth: 1 },
      ],
    },
    options: { responsive: true, plugins: { legend: { position: "top" } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
  });
}

function _yetkiPieCiz(dagilim) {
  if (_yetkiPie) _yetkiPie.destroy();
  const ctx = document.getElementById("yetkiPie");
  if (!ctx) return;
  _yetkiPie = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Yetkili", "Yetkisiz", "Kara Liste", "Süresi Dolmuş"],
      datasets: [{ data: [dagilim.yetkili, dagilim.yetkisiz, dagilim.kara_liste, dagilim.suresi_dolmus], backgroundColor: ["#75b798", "#ea868f", "#343a40", "#ffc107"] }],
    },
    options: { responsive: true, plugins: { legend: { position: "bottom" } } },
  });
}

// ================================================================
// PLAKA ANALİZİ
// ================================================================

async function plakaAnalizAc(plaka) {
  document.getElementById("analizPlaka").textContent = plaka;
  document.getElementById("analizIcerik").innerHTML = '<div class="text-center py-4"><div class="spinner-border"></div></div>';
  bootstrap.Modal.getOrCreateInstance(document.getElementById("plakaAnalizModal")).show();
  try {
    const v = await apiCagir(`/kayitlar/analiz/${encodeURIComponent(plaka)}`);
    // "Kayıtlar" tablosundaki düzenle/sil butonları (kayitDuzenleAc/kayitSil)
    // aynen bu ekranda da tekrar kullanılıyor; onlar sonKayitlarCache üzerinden
    // çalıştığı için burada gösterilen kayıtlar da önbelleğe eklenir/güncellenir.
    sonKayitlarCache = [...sonKayitlarCache.filter(k => !v.son_kayitlar.find(n => n.id === k.id)), ...v.son_kayitlar];
    const karaRozet = v.kara_listesinde
      ? `<span class="badge bg-danger ms-2">KARA LİSTEDE</span>`
      : `<span class="badge bg-success ms-2">Temiz</span>`;
    const kisiBlok = v.kisi
      ? `<div class="alert alert-success py-2 mb-3"><b>${escapeHtml(v.kisi.ad_soyad)}</b> · ${escapeHtml(v.kisi.tip)} ${v.kisi.telefon ? " · " + escapeHtml(v.kisi.telefon) : ""}</div>`
      : `<div class="alert alert-warning py-2 mb-3">Sistemde kayıtlı kişi yok</div>`;
    const satirlar = v.son_kayitlar.map(k => `
      <tr>
        <td>${k.goruntu_yolu ? `<img class="thumb" data-goruntu-yolu="${escapeHtml(k.goruntu_yolu)}" role="button" tabindex="0" alt="Geçiş görseli, büyütmek için tıklayın veya Enter'a basın">` : '<span class="text-muted small">-</span>'}</td>
        <td>${tarihFormatla(k.tarih_saat)}</td>
        <td>${k.yon === "giris" ? "Giriş" : "Çıkış"}</td>
        <td>${escapeHtml(k.kamera_id)}</td>
        <td>${durumRozeti(k.yetki_durumu)}</td>
        <td>${k.guven_skoru ? (k.guven_skoru * 100).toFixed(0) + "%" : "-"}</td>
        <td>${dogrulamaRozeti(k.dogrulama_kare_sayisi, k.farkli_okuma_sayisi)}</td>
        <td class="small">${k.manuel_giris ? '<span class="badge bg-secondary d-block mb-1">Manuel</span>' : ""}${k.not_metni ? escapeHtml(k.not_metni) : (k.manuel_giris ? "" : '<span class="text-muted">-</span>')}</td>
        <td class="text-nowrap">
          ${rolYeterli("operatör") ? `<button class="btn btn-sm btn-outline-primary" onclick="kayitDuzenleAc(${k.id})" title="Kaydı düzenle" aria-label="Kaydı düzenle"><i class="bi bi-pencil"></i></button>` : ""}
          ${rolYeterli("yonetici") ? `<button class="btn btn-sm btn-outline-secondary ms-1" onclick="kayitSil(${k.id})" title="Kaydı sil" aria-label="Kaydı sil"><i class="bi bi-trash"></i></button>` : ""}
        </td>
      </tr>`).join("");
    document.getElementById("analizIcerik").innerHTML = `
      <div class="d-flex gap-3 mb-3 flex-wrap">
        <div class="stat-card card flex-fill text-center py-2"><div class="text-muted small">Toplam Geçiş</div><div class="fs-3 fw-bold">${v.toplam_gecis}</div></div>
        <div class="stat-card card flex-fill text-center py-2"><div class="text-muted small">Son Geçiş</div><div class="small">${v.son_gecis ? tarihFormatla(v.son_gecis) : "—"}</div></div>
        <div class="stat-card card flex-fill text-center py-2"><div class="text-muted small">Kara Liste</div>${karaRozet}</div>
      </div>
      ${kisiBlok}
      ${v.kara_sebep ? `<div class="alert alert-danger py-2 mb-3">Engel sebebi: ${escapeHtml(v.kara_sebep)}</div>` : ""}
      <div class="table-responsive">
        <table class="table table-sm align-middle">
          <thead class="table-light"><tr><th>Görsel</th><th>Tarih/Saat</th><th>Yön</th><th>Kamera</th><th>Durum</th><th>Güven</th><th title="Bu okuma kaç farklı karede doğrulandı">Doğrulama</th><th>Not</th><th></th></tr></thead>
          <tbody>${satirlar || "<tr><td colspan='9' class='text-center text-muted'>Kayıt yok</td></tr>"}</tbody>
        </table>
      </div>
      <div class="d-flex gap-2 mt-2 flex-wrap">
        ${!v.kara_listesinde ? `<button class="btn btn-sm btn-danger" data-kara-ekle="${escapeHtml(v.plaka_no)}">Kara Listeye Ekle</button>` : ""}
        ${rolYeterli("operatör") ? `<button class="btn btn-sm btn-outline-primary" type="button" data-bs-toggle="collapse" data-bs-target="#analizManuelForm">+ Manuel Kayıt Ekle</button>` : ""}
      </div>
      ${rolYeterli("operatör") ? `
      <div class="collapse mt-2" id="analizManuelForm">
        <form id="analizManuelKayitForm" class="card card-body py-2">
          <div class="row g-2 align-items-end">
            <div class="col-auto">
              <label class="form-label small mb-0">Yön</label>
              <select id="analizManuelYon" class="form-select form-select-sm">
                <option value="giris">Giriş</option>
                <option value="cikis">Çıkış</option>
              </select>
            </div>
            <div class="col">
              <label class="form-label small mb-0">Not</label>
              <input type="text" id="analizManuelNot" class="form-control form-control-sm" value="${escapeHtml(v.son_not_onerisi || "")}" placeholder="örn. teslimat aracı, güvenlik onayıyla alındı" maxlength="500">
            </div>
            <div class="col-auto">
              <button type="submit" class="btn btn-sm btn-primary">Kaydı Ekle</button>
            </div>
          </div>
          <div id="analizManuelSonuc" class="small mt-1"></div>
        </form>
      </div>` : ""}`;
    korumaliGorselleriYukle(document.getElementById("analizIcerik"));
    document.getElementById("analizManuelKayitForm")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const sonuc = document.getElementById("analizManuelSonuc");
      try {
        // Bu ekrandan eklenen kayıtlar, görevlinin bir aracı elle içeri/dışarı
        // aldığı durumlar için: gerçek kamera pipeline'ından gelmediği kamera_id
        // ile ayırt edilsin ve manuel_giris=True bayrağıyla panelde "Manuel"
        // etiketiyle işaretlensin diye backend/main.py::kayit_ekle_manuel
        // çağrılıyor (görsel yok, güven skoru yok -- test kaydı formuyla aynı uç).
        await apiCagir("/kayitlar", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            plaka_no: v.plaka_no,
            kamera_id: "PANEL-MANUEL",
            yon: document.getElementById("analizManuelYon").value,
            not_metni: document.getElementById("analizManuelNot").value || null,
          }),
        });
        panelYenile();
        kayitlariYukle(false);
        plakaAnalizAc(v.plaka_no);
      } catch (err) {
        sonuc.className = "small text-danger mt-1"; sonuc.textContent = err.message;
      }
    });
  } catch (e) {
    document.getElementById("analizIcerik").innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
  }
}

// ================================================================
// KARA LİSTE
// ================================================================

async function karaListesiYukle() {
  try {
    const liste = await apiCagir("/kara-listesi");
    const el = document.getElementById("karaListeTablo");
    if (!el) return;
    el.innerHTML = liste.map(k => `<tr>
      <td class="fw-bold"><button class="plate-link" data-plaka-analiz="${escapeHtml(k.plaka_no)}">${escapeHtml(k.plaka_no)}</button></td>
      <td>${escapeHtml(k.sebep) || "<span class='text-muted'>-</span>"}</td>
      <td>${escapeHtml(k.ekleyen) || "-"}</td>
      <td class="small text-muted">${tarihFormatla(k.olusturma_tarihi)}</td>
      <td>${rolYeterli("operatör") ? `<button class="btn btn-sm btn-outline-success" onclick="karaListedenCikar(${k.id})" title="Listeden çıkar"><i class="bi bi-check-circle"></i></button>` : '<span class="text-muted small">-</span>'}</td>
    </tr>`).join("") || `<tr><td colspan="5" class="text-center text-muted py-3">Kara listede kayıt yok</td></tr>`;
  } catch (e) { console.error(e); }
}

document.getElementById("karaListeForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const sonuc = document.getElementById("karaListeSonuc");
  try {
    await apiCagir("/kara-listesi", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plaka_no: document.getElementById("karaPlaka").value, sebep: document.getElementById("karaSebep").value || null }) });
    sonuc.className = "small mt-2 text-success"; sonuc.textContent = "Araç kara listeye eklendi.";
    e.target.reset(); karaListesiYukle(); panelYenile();
  } catch (err) { sonuc.className = "small mt-2 text-danger"; sonuc.textContent = err.message; }
});

async function karaListedenCikar(id) {
  if (!confirm("Bu aracı kara listeden çıkarmak istiyor musunuz?")) return;
  await apiCagir(`/kara-listesi/${id}`, { method: "DELETE" });
  karaListesiYukle(); panelYenile();
}

function karaListeyeEkleModal(plaka) {
  bootstrap.Modal.getInstance(document.getElementById("plakaAnalizModal"))?.hide();
  document.getElementById("karaPlaka").value = plaka;
  sekmeAc("#karaliste-sekme");
}

// ================================================================
// BARİYER KONTROLÜ
// ================================================================

function bariyerModDegisti() {
  const mod = document.getElementById("bariyerMod").value;
  document.getElementById("bariyerHttpAlani").classList.toggle("d-none", mod !== "http");
}

async function bariyerleriYukle() {
  try {
    const bariyerler = await apiCagir("/bariyer/ayarlar");
    const el = document.getElementById("bariyerTablo");
    if (!el) return;
    el.innerHTML = bariyerler.map(b => `<tr>
      <td><strong>${escapeHtml(b.ad)}</strong></td>
      <td><span class="badge bg-secondary">${escapeHtml(b.mod)}</span></td>
      <td class="text-muted small text-truncate" style="max-width:150px">${escapeHtml(b.http_url || "-")}</td>
      <td>
        ${rolYeterli("operatör") ? `
        <button class="btn btn-sm btn-success" onclick="bariyerAc(${b.id})" title="Bariyeri aç"><i class="bi bi-unlock-fill"></i> Aç</button>
        <button class="btn btn-sm btn-outline-danger ms-1" onclick="bariyerSil(${b.id})"><i class="bi bi-trash"></i></button>
        ` : '<span class="text-muted small">-</span>'}
      </td>
    </tr>`).join("") || `<tr><td colspan="4" class="text-center text-muted py-3">Bariyer tanımlanmadı</td></tr>`;
  } catch (e) { console.error(e); }
}

document.getElementById("bariyerForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const sonuc = document.getElementById("bariyerSonuc");
  try {
    await apiCagir("/bariyer/ayarlar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      ad: document.getElementById("bariyerAd").value,
      mod: document.getElementById("bariyerMod").value,
      http_url: document.getElementById("bariyerUrl").value || null,
      http_metot: document.getElementById("bariyerMetot").value,
      http_govde: document.getElementById("bariyerGovde").value || null,
      auto_ac: document.getElementById("bariyerAutoAc").checked,
    })});
    sonuc.className = "small mt-2 text-success"; sonuc.textContent = "Bariyer kaydedildi.";
    e.target.reset(); bariyerleriYukle();
  } catch (err) { sonuc.className = "small mt-2 text-danger"; sonuc.textContent = err.message; }
});

async function bariyerAc(id) {
  try {
    const r = await apiCagir(`/bariyer/${id}/ac`, { method: "POST" });
    toastGoster(r.mesaj, "basari");
  } catch (e) { toastGoster(e.message, "hata"); }
}

async function bariyerSil(id) {
  if (!confirm("Bu bariyer kaydını silmek istiyor musunuz?")) return;
  await apiCagir(`/bariyer/ayarlar/${id}`, { method: "DELETE" });
  bariyerleriYukle();
}

// ================================================================
// SİTE / ERİŞİM NOKTASI YÖNETİMİ
// ================================================================

let _siteCache = [];

async function siteleriYukle() {
  try {
    const siteler = await apiCagir("/siteler");
    _siteCache = siteler;
    const tbody = document.getElementById("sitelerTablo");
    if (tbody) {
      tbody.innerHTML = siteler.map(s => `<tr>
        <td><strong>${escapeHtml(s.ad)}</strong></td>
        <td class="text-muted small">${escapeHtml(s.aciklama) || "-"}</td>
        <td>${rolYeterli("yonetici") ? `<button class="btn btn-sm btn-outline-danger" onclick="siteSil(${s.id})" title="Sil"><i class="bi bi-trash"></i></button>` : '<span class="text-muted small">-</span>'}</td>
      </tr>`).join("") || `<tr><td colspan="3" class="text-center text-muted py-3">Henüz site tanımlanmadı</td></tr>`;
    }
    const secim = document.getElementById("noktaSiteId");
    if (secim) {
      const oncekiDeger = secim.value;
      secim.innerHTML = siteler.map(s => `<option value="${s.id}">${escapeHtml(s.ad)}</option>`).join("") || '<option value="">- Önce bir site ekleyin -</option>';
      if (oncekiDeger && siteler.some(s => String(s.id) === oncekiDeger)) secim.value = oncekiDeger;
    }
  } catch (e) { console.error(e); }
}

document.getElementById("siteForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const sonuc = document.getElementById("siteSonuc");
  try {
    await apiCagir("/siteler", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      ad: document.getElementById("siteAd").value,
      aciklama: document.getElementById("siteAciklama").value || null,
    })});
    sonuc.className = "small mt-3 text-success"; sonuc.textContent = "Site kaydedildi.";
    e.target.reset(); siteleriYukle();
  } catch (err) { sonuc.className = "small mt-3 text-danger"; sonuc.textContent = err.message; }
});

async function siteSil(id) {
  if (!confirm("Bu siteyi ve bağlı tüm erişim noktalarını silmek istiyor musunuz?")) return;
  try {
    await apiCagir(`/siteler/${id}`, { method: "DELETE" });
    siteleriYukle(); noktalariYukle();
  } catch (err) { toastGoster(err.message, "hata"); }
}

async function _kameraSecenekleriniDoldur() {
  const secim = document.getElementById("noktaKameraId");
  if (!secim) return;
  try {
    const kameralar = await apiCagir("/kameralar");
    const oncekiDeger = secim.value;
    secim.innerHTML = '<option value="">- Yok -</option>' + kameralar.map(k => `<option value="${k.id}">${escapeHtml(k.ad)}</option>`).join("");
    secim.value = oncekiDeger;
  } catch (e) { console.error(e); }
}

async function _bariyerSecenekleriniDoldur() {
  const secim = document.getElementById("noktaBariyerId");
  if (!secim) return;
  try {
    const bariyerler = await apiCagir("/bariyer/ayarlar");
    const oncekiDeger = secim.value;
    secim.innerHTML = '<option value="">- Yok -</option>' + bariyerler.map(b => `<option value="${b.id}">${escapeHtml(b.ad)}</option>`).join("");
    secim.value = oncekiDeger;
  } catch (e) { console.error(e); }
}

async function noktalariYukle() {
  try {
    const [noktalar, kameralar, bariyerler] = await Promise.all([
      apiCagir("/noktalar"),
      apiCagir("/kameralar").catch(() => []),
      apiCagir("/bariyer/ayarlar").catch(() => []),
    ]);
    const tbody = document.getElementById("noktalarTablo");
    if (tbody) {
      tbody.innerHTML = noktalar.map(n => {
        const site = _siteCache.find(s => s.id === n.site_id);
        const kamera = kameralar.find(k => k.id === n.kamera_id);
        const bariyer = bariyerler.find(b => b.id === n.bariyer_id);
        return `<tr>
          <td>${site ? escapeHtml(site.ad) : "-"}</td>
          <td><strong>${escapeHtml(n.ad)}</strong></td>
          <td>${n.yon === "giris" ? "Giriş" : "Çıkış"}</td>
          <td>${kamera ? escapeHtml(kamera.ad) : '<span class="text-muted">Bağlı değil</span>'}</td>
          <td>${bariyer ? escapeHtml(bariyer.ad) : '<span class="text-muted">Bağlı değil</span>'}</td>
          <td>${rolYeterli("yonetici") ? `<button class="btn btn-sm btn-outline-danger" onclick="noktaSil(${n.id})" title="Sil"><i class="bi bi-trash"></i></button>` : '<span class="text-muted small">-</span>'}</td>
        </tr>`;
      }).join("") || `<tr><td colspan="6" class="text-center text-muted py-3">Henüz erişim noktası tanımlanmadı</td></tr>`;
    }
    await _kameraSecenekleriniDoldur();
    await _bariyerSecenekleriniDoldur();
  } catch (e) { console.error(e); }
}

document.getElementById("noktaForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const sonuc = document.getElementById("noktaSonuc");
  try {
    await apiCagir("/noktalar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      site_id: Number(document.getElementById("noktaSiteId").value),
      ad: document.getElementById("noktaAd").value,
      yon: document.getElementById("noktaYon").value,
      kamera_id: document.getElementById("noktaKameraId").value || null,
      bariyer_id: document.getElementById("noktaBariyerId").value ? Number(document.getElementById("noktaBariyerId").value) : null,
      aciklama: document.getElementById("noktaAciklama").value || null,
    })});
    sonuc.className = "small mt-3 text-success"; sonuc.textContent = "Erişim noktası kaydedildi.";
    e.target.reset(); noktalariYukle();
  } catch (err) { sonuc.className = "small mt-3 text-danger"; sonuc.textContent = err.message; }
});

async function noktaSil(id) {
  if (!confirm("Bu erişim noktasını silmek istiyor musunuz?")) return;
  try {
    await apiCagir(`/noktalar/${id}`, { method: "DELETE" });
    noktalariYukle();
  } catch (err) { toastGoster(err.message, "hata"); }
}

// ================================================================
// KULLANICI YÖNETİMİ
// ================================================================

async function kullanicilariYukle() {
  try {
    const [kullanicilar, kisiler] = await Promise.all([
      apiCagir("/kullanicilar"),
      apiCagir("/kisiler").catch(() => []),
    ]);
    const el = document.getElementById("kullanicilarTablo");
    if (!el) return;
    const roller = { yonetici: "bg-danger", "operatör": "bg-warning text-dark", izleyici: "bg-secondary", sakin: "bg-info text-dark" };
    el.innerHTML = kullanicilar.map(k => {
      const bagliKisi = k.kisi_id ? kisiler.find(ki => ki.id === k.kisi_id) : null;
      return `<tr>
      <td><strong>${escapeHtml(k.kullanici_adi)}</strong></td>
      <td><span class="badge ${roller[k.rol] || "bg-secondary"}">${escapeHtml(k.rol)}</span></td>
      <td class="small">${bagliKisi ? escapeHtml(bagliKisi.ad_soyad) : (k.kisi_id ? `#${k.kisi_id} (silinmiş)` : "-")}</td>
      <td class="small text-muted">${k.son_giris ? tarihFormatla(k.son_giris) : "—"}</td>
      <td>${k.aktif ? '<span class="badge bg-success">Aktif</span>' : '<span class="badge bg-secondary">Pasif</span>'}</td>
      <td>
        ${rolYeterli("yonetici") ? `
        <button class="btn btn-sm btn-outline-secondary" onclick="kullaniciDurumDegistir(${k.id}, ${!k.aktif})" title="${k.aktif ? "Pasif yap" : "Aktif yap"}"><i class="bi bi-toggle2-on"></i></button>
        <button class="btn btn-sm btn-outline-danger ms-1" onclick="kullaniciSil(${k.id})" title="Sil"><i class="bi bi-trash"></i></button>
        ` : '<span class="text-muted small">-</span>'}
      </td>
    </tr>`;
    }).join("") || `<tr><td colspan="6" class="text-center text-muted py-3">Kullanıcı bulunamadı</td></tr>`;
  } catch (e) {
    const el = document.getElementById("kullanicilarTablo");
    if (el) el.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-3">Bu sekmeyi sadece yönetici görebilir</td></tr>`;
  }
}

// rol="sakin" seçilince "Bağlı Kişi" alanını gösterir ve o anki kişi listesini
// doldurur -- bir sakin hesabı mutlaka bir Kişi kaydına bağlı olmalı (bkz.
// main.py::_sakin_kisi_id_dogrula, 400 döner aksi halde).
async function yeniKullaniciRolDegisti() {
  const alan = document.getElementById("yeniKullaniciKisiAlani");
  const sakinSecildi = document.getElementById("yeniRol").value === "sakin";
  alan.classList.toggle("d-none", !sakinSecildi);
  if (!sakinSecildi) return;
  const secim = document.getElementById("yeniKullaniciKisi");
  try {
    const kisiler = await apiCagir("/kisiler");
    secim.innerHTML = '<option value="">Kişi seçiniz...</option>' + kisiler.map(k =>
      `<option value="${k.id}">${escapeHtml(k.ad_soyad)} (${escapeHtml(k.plaka_no)}${k.daire_departman ? " · " + escapeHtml(k.daire_departman) : ""})</option>`
    ).join("");
  } catch { /* kişi listesi alınamazsa boş bırak, gönderimde 400 ile fark edilir */ }
}

document.getElementById("kullaniciForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const sonuc = document.getElementById("kullaniciSonuc");
  const rol = document.getElementById("yeniRol").value;
  if (rol === "sakin" && !document.getElementById("yeniKullaniciKisi").value) {
    sonuc.className = "small mt-2 text-danger";
    sonuc.textContent = "'Sakin' rolü için bağlı kişi seçilmeli.";
    return;
  }
  try {
    const govde = {
      kullanici_adi: document.getElementById("yeniKullanici").value,
      parola: document.getElementById("yeniParola").value,
      rol,
    };
    if (rol === "sakin") govde.kisi_id = Number(document.getElementById("yeniKullaniciKisi").value);
    await apiCagir("/kullanicilar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(govde) });
    sonuc.className = "small mt-2 text-success"; sonuc.textContent = "Kullanıcı oluşturuldu.";
    e.target.reset();
    document.getElementById("yeniKullaniciKisiAlani").classList.add("d-none");
    kullanicilariYukle();
  } catch (err) { sonuc.className = "small mt-2 text-danger"; sonuc.textContent = err.message; }
});

async function kullaniciDurumDegistir(id, yeniDurum) {
  try {
    await apiCagir(`/kullanicilar/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ aktif: yeniDurum }) });
    kullanicilariYukle();
  } catch (e) { toastGoster(e.message, "hata"); }
}

async function kullaniciSil(id) {
  if (!confirm("Bu kullanıcıyı silmek istediğinize emin misiniz?")) return;
  try {
    await apiCagir(`/kullanicilar/${id}`, { method: "DELETE" });
    kullanicilariYukle();
  } catch (e) { toastGoster(e.message, "hata"); }
}

// ================================================================
// SİSTEM SAĞLIĞI & LOGLAR
// ================================================================

async function sistemSagliginiYukle() {
  try {
    const s = await apiCagir("/sistem/saglik");
    const el = document.getElementById("sistemSaglikPaneli");
    if (!el) return;
    const ikon = (ok) => ok ? '<i class="bi bi-check-circle-fill text-success"></i>' : '<i class="bi bi-x-circle-fill text-danger"></i>';
    // PTS_SQL_YEDEK_KLASORU ayarlanmamışsa "yedek.izleniyor" false döner ve bu
    // satır hiç gösterilmez (davranış eklenmeden önceki gibi kalır — bkz.
    // main.py::_son_yedek_bilgisini_al). Ayarlıysa, SQL Server Agent bakım
    // planının GERÇEKTEN çalışıp çalışmadığını (önceden hiç izlenmiyordu)
    // panelde görünür kılar.
    const yedekSatiri = s.yedek?.izleniyor
      ? `<div class="info-row">${ikon(!s.yedek.yedek_gecikmis)} <span>SQL Yedek</span><strong>${s.yedek.son_yedek_zamani ? tarihFormatla(s.yedek.son_yedek_zamani) : "Hiç yedek yok"}</strong></div>`
      : "";
    // PTS_GORSEL_IZLEME_DIZINI ayarlanmamışsa "gorsel_izleme.aktif" false döner
    // ve bu satır hiç gösterilmez (bkz. main.py::_klasor_izlemeyi_baslat_gerekirse,
    // camera_reader.py::KlasorIzleyici).
    const gorselIzlemeSatiri = s.gorsel_izleme?.aktif
      ? `<div class="info-row"><i class="bi bi-folder-check text-primary"></i> <span>Klasör İzleme</span><strong title="${escapeHtml(s.gorsel_izleme.klasor)}">Aktif</strong></div>`
      : "";
    // Motor henüz hiçbir kamera/klasör izleyici tarafından oluşturulmadıysa
    // (uygulama yeni açıldı, henüz bir pipeline başlamadı) anpr_dedektor_esigi
    // null döner ve bu satır hiç gösterilmez. NOT: bu, panelin "Sistem
    // Ayarları" bölümündeki "Min. plaka tanıma güveni" alanından TAMAMEN
    // FARKLI bir eşiktir (bkz. anpr_engine.py) — PTS_ANPR_DETECTOR_ESIGI ortam
    // değişkeni ile ayarlanır; kaynağı burada gösterilerek "ayarım kabul
    // edildi mi?" sorusuna log dosyasına inmeden cevap verilebilir.
    const dedektorEsigiSatiri = s.anpr_dedektor_esigi
      ? `<div class="info-row"><i class="bi bi-bullseye text-primary"></i> <span>Dedektör Eşiği</span><strong title="${escapeHtml(s.anpr_dedektor_esigi.kaynak)}">${s.anpr_dedektor_esigi.esik.toFixed(2)}</strong></div>`
      : "";
    // "model" alanı yoksa (eski bir yedekten dönülmüş/uyumsuz bir versiyon
    // ihtimaline karşı) bu satır sessizce gösterilmez.
    const dedektorModeliSatiri = s.anpr_dedektor_esigi?.model
      ? `<div class="info-row"><i class="bi bi-aspect-ratio text-primary"></i> <span>Dedektör Modeli</span><strong title="${escapeHtml(s.anpr_dedektor_esigi.model_kaynagi || "")}">${escapeHtml(s.anpr_dedektor_esigi.model)}</strong></div>`
      : "";
    el.innerHTML = `
      <div class="info-row">${ikon(s.durum === "cevrimici")} <span>Uygulama</span><strong>${s.durum}</strong></div>
      <div class="info-row">${ikon(s.veritabani === "ok")} <span>Veritabanı</span><strong>${s.veritabani}</strong></div>
      <div class="info-row"><i class="bi bi-camera-video text-primary"></i> <span>Aktif Pipeline</span><strong>${s.aktif_pipeline}</strong></div>
      <div class="info-row"><i class="bi bi-wifi text-primary"></i> <span>SSE İstemci</span><strong>${s.sse_istemci}</strong></div>
      <div class="info-row">${ikon(s.kutuphaneler_mevcut)} <span>ANPR Kütüp.</span><strong>${s.kutuphaneler_mevcut ? "Kurulu" : "Kurulu değil"}</strong></div>
      ${yedekSatiri}
      ${gorselIzlemeSatiri}
      ${dedektorEsigiSatiri}
      ${dedektorModeliSatiri}
      <div class="info-row"><i class="bi bi-code text-muted"></i> <span>Sürüm</span><strong>PTS v${s.surum}</strong></div>
      <div class="text-muted small mt-2">${new Date(s.zaman).toLocaleString("tr-TR")}</div>`;
  } catch (e) { console.error(e); }
}

async function loglariYukle() {
  try {
    const r = await apiCagir("/sistem/loglar?satir=300");
    const el = document.getElementById("logKonteyneri");
    if (!el) return;
    el.textContent = r.satirlar.join("\n");
    el.scrollTop = el.scrollHeight;
  } catch (e) { console.error(e); }
}

// Toplu doğruluk testi (bkz. camera_reader.py::toplu_dogruluk_testi,
// main.py::/sistem/dogruluk-testi) — canlı sisteme hiç dokunmadan, etiketli
// bir fotoğraf klasörü üzerinde farklı eşik/model/kontrast ayarlarının
// GERÇEK doğruluk oranını karşılaştırmak için kullanılır.
async function dogrulukTestiCalistir(olay) {
  olay.preventDefault();
  const buton = document.getElementById("dogrulukTestiButon");
  const sonucEl = document.getElementById("dogrulukTestiSonuc");
  const klasor = document.getElementById("dogrulukTestiKlasor").value.trim();
  const esikHam = document.getElementById("dogrulukTestiEsik").value.trim();
  const kontrast = document.getElementById("dogrulukTestiKontrast").checked;
  if (!klasor) return;

  buton.disabled = true;
  buton.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Çalışıyor…';
  sonucEl.innerHTML = '<div class="text-muted small">Fotoğraflar işleniyor, klasör büyükse biraz sürebilir…</div>';
  try {
    const govde = { klasor, kontrast_iyilestir: kontrast };
    if (esikHam) govde.min_guven_skoru = parseFloat(esikHam.replace(",", "."));
    const r = await apiCagir("/sistem/dogruluk-testi", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(govde),
    });
    const oranYuzde = r.dogruluk_orani != null ? `%${(r.dogruluk_orani * 100).toFixed(1)}` : "—";
    // "tespit_edilemedi" (dedektör hiçbir aday bulamadı) ile "gorsel_okunamadi"
    // (dosya hiç açılamadı) ve "hata" (motor çağrısı sırasında istisna) BİLEREK
    // ayrı rozetlerle gösterilir -- hepsi aynı gri rozette birleştirilirse
    // "model değiştirince de hâlâ 0 tespit" gibi bir sonucun aslında "dosyalar
    // hiç okunamıyor" anlamına gelebileceği fark edilmez (bkz. camera_reader.py).
    const rozetler = {
      dogru: "success", yanlis: "danger", esik_altinda: "warning",
      tespit_edilemedi: "secondary", gorsel_okunamadi: "dark", hata: "danger",
      etiketlenemedi: "light",
    };
    const detaySatirlari = r.detaylar.map(d => {
      const rozetRenk = rozetler[d.sonuc] || "secondary";
      const notSatiri = d.hata_mesaji ? ` title="${escapeHtml(d.hata_mesaji)}"` : "";
      return `<tr>
        <td class="small">${escapeHtml(d.dosya)}</td>
        <td class="small">${escapeHtml(d.gercek_plaka || "—")}</td>
        <td class="small">${escapeHtml(d.okunan_plaka || "—")}</td>
        <td class="small">${d.guven != null ? d.guven.toFixed(2) : "—"}</td>
        <td class="small">${escapeHtml(d.kare_boyutu || "—")}</td>
        <td${notSatiri}><span class="badge bg-${rozetRenk} text-${["light"].includes(rozetRenk) ? "dark" : "white"}">${escapeHtml(d.sonuc)}</span></td>
      </tr>`;
    }).join("");
    sonucEl.innerHTML = `
      <div class="alert alert-info py-2 px-3 mb-2">
        <strong>Doğruluk oranı: ${oranYuzde}</strong>
        (${r.dogru}/${r.toplam - r.etiketlenemedi} etiketli dosya doğru okundu)
      </div>
      <div class="small text-muted mb-2">
        Doğru: ${r.dogru} · Yanlış: ${r.yanlis} · Eşik altında: ${r.esik_altinda} ·
        Tespit edilemedi: ${r.tespit_edilemedi} · Görsel okunamadı: ${r.gorsel_okunamadi ?? 0} ·
        Hata: ${r.hata ?? 0} · Etiketlenemedi: ${r.etiketlenemedi}
      </div>
      <div class="table-responsive" style="max-height:320px;overflow-y:auto">
        <table class="table table-sm table-borderless mb-0">
          <thead><tr><th class="small">Dosya</th><th class="small">Gerçek</th><th class="small">Okunan</th><th class="small">Güven</th><th class="small">Kare</th><th class="small">Sonuç</th></tr></thead>
          <tbody>${detaySatirlari}</tbody>
        </table>
      </div>`;
  } catch (err) {
    sonucEl.innerHTML = `<div class="alert alert-danger py-2 px-3 small mb-0">${escapeHtml(err.message)}</div>`;
  } finally {
    buton.disabled = false;
    buton.innerHTML = '<i class="bi bi-play-fill"></i> Testi Çalıştır';
  }
}

// Sistem sekmesi açıldığında logları ve sağlık bilgisini otomatik yükle
document.querySelector('[data-bs-target="#sistem-sekme"]')?.addEventListener("click", () => {
  sistemSagliginiYukle(); loglariYukle(); sistemAyarlariYukle(); diskBilgisiYukle();
});

// ================================================================
// KAMERA DUVARI — TAM EKRAN
// ================================================================

function kameraDuvariFullscreen() {
  const duvar = document.getElementById("kameraDuvari");
  if (!duvar) return;
  if (!document.fullscreenElement) {
    duvar.requestFullscreen().catch(err => console.warn("Fullscreen reddedildi:", err));
  } else {
    document.exitFullscreen();
  }
}

document.addEventListener("fullscreenchange", () => {
  const btn = document.getElementById("fullscreenBtn");
  if (!btn) return;
  btn.innerHTML = document.fullscreenElement
    ? '<i class="bi bi-fullscreen-exit"></i> Küçült'
    : '<i class="bi bi-arrows-fullscreen"></i> Tam ekran';
});

// Çift tıkla tek kamera tam ekran
document.addEventListener("dblclick", (e) => {
  const tile = e.target.closest(".camera-tile");
  if (!tile) return;
  if (!document.fullscreenElement) {
    tile.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen();
  }
});

// ================================================================
// TÜMÜNÜ OKUNDU
// ================================================================

async function alarmHepsiniOku() {
  const r = await apiCagir("/alarmlar/tumu-okundu", { method: "POST" });
  toastGoster(`${r.guncellenen} alarm okundu işaretlendi`, "basari");
  panelYenile();
}

// ================================================================
// SİSTEM AYARLARI
// ================================================================

async function sistemAyarlariYukle() {
  try {
    const ayarlar = await apiCagir("/sistem/ayarlar");
    const el = document.getElementById("sistemAyarlariPaneli");
    if (!el) return;
    const satirlar = [
      { key: "supheli_esik", label: "Şüpheli araç eşiği (red/saat)", tip: "number" },
      { key: "goruntu_saklama_gun", label: "Görüntü saklama süresi (gün)", tip: "number" },
      { key: "panel_yenileme_sn", label: "Panel yenileme aralığı (sn)", tip: "number" },
      { key: "min_tanima_guveni", label: "Min. OCR okuma güveni — oy birikimine giriş eşiği (0-1)", tip: "number", step: "0.05" },
      { key: "otomatik_kayit_min_guven_skoru", label: "Min. kayıt güven skoru — kayda düşme eşiği (0-1)", tip: "number", step: "0.01" },
      { key: "otomatik_kayit_min_guven_skoru_bilinen_arac", label: "Min. kayıt güven skoru — BİLİNEN araç istisnası (0-1)", tip: "number", step: "0.01" },
      { key: "tekrar_gecikme_sn", label: "Aynı kameranın kendi tekrarını bastırma gecikmesi (sn)", tip: "number" },
      { key: "capraz_kamera_tekrar_penceresi_sn", label: "Farklı kameralar arası kısa süreli tekrar penceresi (sn, 0 = kapalı)", tip: "number" },
    ];
    el.innerHTML = `<form id="sistemAyarlariForm" data-rol-min="yonetici">${satirlar.map(s =>
      `<div class="mb-2"><label class="form-label small">${escapeHtml(s.label)}</label>
       <input type="number" ${s.step ? `step="${s.step}" min="0" max="1"` : ""} class="form-control form-control-sm" id="ayar_${s.key}" value="${escapeHtml(String(ayarlar[s.key] ?? ""))}"></div>`
    ).join("")}
      <p class="small text-muted mb-2">"OCR okuma güveni" tek tek kamera karelerinin oylamaya katılıp
        katılmayacağına bakar; "kayıt güven skoru" ise oturum kapanıp nihai güven belirlendikten sonra
        tespitin panele/kayıtlara hiç düşüp düşmeyeceğine karar verir — düşük güvenli, hatalı okunan
        plakaların kayıtları şişirmesini engellemek için varsayılan %97'dir. "BİLİNEN araç istisnası"
        (varsayılan %80), sahada zaten kayıtlı (abone/personel) bir plakayla tam/çok yakın eşleşen bir
        tespitin, genel eşiğin altında kalsa bile bu daha düşük eşiği geçtiği sürece yine de kaydedilmesini
        sağlar — kayıtlı bir aracın düşük ışık/açı yüzünden düşük OCR güveniyle okunup girişte hiç
        kaydedilmemesi (ama çıkışta kaydedilmesi gibi tutarsızlıklar) buradan kaynaklanır.
        "Aynı kameranın kendi tekrarı", TEK bir kameranın (örn. bariyer önünde bekleyen bir aracı)
        art arda birden fazla kez "yeni bir geçiş" olarak kaydetmesini engeller. "Farklı kameralar
        arası kısa süreli tekrar" ise FARKLI bir sorunu çözer: giriş ve çıkış kameraları aynı fiziksel
        geçidi/yolu paylaşıyorsa, bir aracın TEK geçişi her iki kameranın da görüş alanına girip iki
        AYRI (ve çelişkili yönde) kayıt oluşturabilir -- bu pencere içinde farklı bir kameradan gelen
        aynı plaka, yeni bir kayıt olarak SAYILMAZ.</p>
      <div class="form-check mb-2">
        <input type="checkbox" class="form-check-input" id="ayar_bilinen_plaka_duzeltme_aktif" ${ayarlar.bilinen_plaka_duzeltme_aktif ? "checked" : ""}>
        <label class="form-check-label small" for="ayar_bilinen_plaka_duzeltme_aktif">Bilinen plakaya göre OCR düzeltmesi (tek karakter hataları)</label>
      </div>
      ${rolYeterli("yonetici") ? '' : '<p class="small text-muted mb-2"><i class="bi bi-lock-fill"></i> Bu ayarları sadece yönetici değiştirebilir.</p>'}
      <button type="submit" class="btn btn-sm btn-primary w-100 mt-1"><i class="bi bi-save"></i> Kaydet</button></form>`;
    document.getElementById("sistemAyarlariForm").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const guncel = {};
      satirlar.forEach(s => { guncel[s.key] = Number(document.getElementById(`ayar_${s.key}`).value); });
      guncel.bilinen_plaka_duzeltme_aktif = document.getElementById("ayar_bilinen_plaka_duzeltme_aktif").checked;
      await apiCagir("/sistem/ayarlar", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(guncel) });
      toastGoster("Sistem ayarları kaydedildi", "basari");
    });
    rolBazliArayuzuUygula();
  } catch (e) { console.error(e); }
}

// ================================================================
// DİSK YÖNETİMİ
// ================================================================

async function diskBilgisiYukle() {
  try {
    const d = await apiCagir("/sistem/disk-kullanimi");
    const el = document.getElementById("diskBilgisi");
    if (el) el.innerHTML = `<span class="fw-bold">${d.goruntu_mb} MB</span> — ${d.goruntu_sayisi} görüntü dosyası`;
  } catch (e) {}
}

async function goruntuleriTemizle() {
  const gun = document.getElementById("temizleGun")?.value || 30;
  if (!confirm(`${gun} günden eski görüntüler silinecek. Emin misiniz?`)) return;
  const r = await apiCagir(`/sistem/goruntu-temizle?gun=${gun}`, { method: "POST" });
  toastGoster(`${r.silinen_goruntu} görüntü silindi`, "basari");
  diskBilgisiYukle();
}

// "Güven eşiği" filtresi (2026-09-17) devreye alınmadan ÖNCE zaten kaydedilmiş,
// düşük güvenli OTOMATİK tespit kayıtlarını geriye dönük temizler (bkz.
// main.py::dusuk_guven_kayitlarini_temizle). Yeni tespitler zaten kayıt
// oluşturulmadan elenir -- bu düğme yalnızca eski birikmiş kayıtlar içindir.
async function dusukGuvenliKayitlariTemizle() {
  if (!confirm("Sistem Ayarları'ndaki eşiğin ALTINDA kalan, elle girilmemiş tüm otomatik tespit kayıtları (ve görselleri) kalıcı olarak silinecek. Emin misiniz?")) return;
  try {
    const r = await apiCagir("/sistem/dusuk-guven-temizle", { method: "POST" });
    toastGoster(`${r.silinen_kayit} kayıt, ${r.silinen_goruntu} görüntü silindi (eşik: %${Math.round(r.esik * 100)})`, "basari");
    diskBilgisiYukle();
  } catch (err) {
    toastGoster(err.message, "hata");
  }
}

async function veritabaniIndir() {
  // NOT: window.open(...) burada KULLANILAMAZ — yeni sekme açılışı taze bir
  // üst düzey (top-level) gezinme başlatır ve apiCagir()'ın sessionStorage'daki
  // token'dan enjekte ettiği "Authorization: Bearer ..." başlığını taşımaz.
  // Bu yüzden backend "Bearer token gerekli" hatası veriyordu. Doğru yöntem:
  // token'ı elle ekleyerek fetch ile indirip, gelen dosyayı blob olarak
  // tarayıcıya indirtmek.
  const token = sessionStorage.getItem("pts_token");
  try {
    const cevap = await fetch(API + "/sistem/yedek", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!cevap.ok) {
      const hata = await cevap.json().catch(() => ({ detail: "Yedek alınamadı" }));
      throw new Error(hata.detail || "Yedek alınamadı");
    }
    const blob = await cevap.blob();
    let dosyaAdi = "pts_yedek.db";
    const icerikBaslik = cevap.headers.get("Content-Disposition") || "";
    const eslesme = icerikBaslik.match(/filename="?([^";]+)"?/i);
    if (eslesme) dosyaAdi = eslesme[1];
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = dosyaAdi;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    toastGoster(e.message || "Veritabanı yedeği indirilemedi", "hata");
  }
}

// ================================================================
// BİLDİRİM AYARLARI (Webhook)
// ================================================================

async function bildirimleriYukle() {
  try {
    const liste = await apiCagir("/bildirim/ayarlar");
    const el = document.getElementById("bildirimTablo");
    if (!el) return;
    const tetikEtiket = { hepsi: "Her geçiş", yetkisiz: "Yetkisiz", kara_liste: "Kara Liste", suresi_dolmus: "Süresi Dolmuş", kamera_arizasi: "Kamera Arızası" };
    el.innerHTML = liste.map(b => `<tr>
      <td><strong>${escapeHtml(b.ad)}</strong></td>
      <td class="text-muted small text-truncate" style="max-width:160px">${escapeHtml(b.hedef)}</td>
      <td><span class="badge bg-secondary">${escapeHtml(tetikEtiket[b.tetikleyici] || b.tetikleyici)}</span></td>
      <td>${b.aktif ? '<span class="badge bg-success">Aktif</span>' : '<span class="badge bg-secondary">Pasif</span>'}</td>
      <td class="text-nowrap">
        ${rolYeterli("yonetici") ? `
        <button class="btn btn-sm btn-outline-info" title="Test gönder" onclick="bildirimTestGonder(${b.id})"><i class="bi bi-send"></i></button>
        <button class="btn btn-sm btn-outline-secondary ms-1" title="${b.aktif ? "Pasif yap" : "Aktif yap"}" onclick="bildirimToggle(${b.id})"><i class="bi bi-toggle2-on"></i></button>
        <button class="btn btn-sm btn-outline-danger ms-1" onclick="bildirimSil(${b.id})"><i class="bi bi-trash"></i></button>
        ` : '<span class="text-muted small">-</span>'}
      </td>
    </tr>`).join("") || `<tr><td colspan="5" class="text-center text-muted py-3">Henüz webhook tanımlanmadı</td></tr>`;
  } catch (e) { console.error(e); }
}

document.getElementById("bildirimForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const sonuc = document.getElementById("bildirimSonuc");
  try {
    await apiCagir("/bildirim/ayarlar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      ad: document.getElementById("bildirimAd").value,
      hedef: document.getElementById("bildirimHedef").value,
      tetikleyici: document.getElementById("bildirimTetikleyici").value,
      http_metot: document.getElementById("bildirimMetot").value,
    })});
    sonuc.className = "small mt-2 text-success"; sonuc.textContent = "Webhook kaydedildi.";
    e.target.reset(); bildirimleriYukle();
  } catch (err) { sonuc.className = "small mt-2 text-danger"; sonuc.textContent = err.message; }
});

async function bildirimTestGonder(id) {
  try {
    const r = await apiCagir(`/bildirim/test/${id}`, { method: "POST" });
    toastGoster(r.basarili ? "Test isteği gönderildi ✓" : "Test isteği gönderilemedi", r.basarili ? "basari" : "hata");
  } catch (e) { toastGoster(e.message, "hata"); }
}

async function bildirimToggle(id) {
  await apiCagir(`/bildirim/ayarlar/${id}/aktif`, { method: "PATCH" });
  bildirimleriYukle();
}

async function bildirimSil(id) {
  if (!confirm("Bu webhook'u silmek istediğinize emin misiniz?")) return;
  await apiCagir(`/bildirim/ayarlar/${id}`, { method: "DELETE" });
  bildirimleriYukle();
}

// ================================================================
// KAMERA SAĞLIK KONTROLÜ
// ================================================================

let _kameraSaglikCache = {};

async function tumKameralarSaglikKontrol() {
  toastGoster("Kameralar kontrol ediliyor…", "bilgi");
  try {
    const sonuclar = await apiCagir("/kameralar/saglik/tumu");
    _kameraSaglikCache = {};
    sonuclar.forEach(s => { _kameraSaglikCache[s.id] = s; });
    kameralariYukle(); // tabloyu saglik bilgisiyle yenile
    toastGoster(`${sonuclar.filter(s => s.tcp_erisim).length}/${sonuclar.length} kamera erişilebilir`, "basari");
  } catch (e) { toastGoster(e.message, "hata"); }
}

// ================================================================
// TOPLU EXCEL İÇE AKTARMA
// ================================================================

async function topluImport(input) {
  if (!input.files?.length) return;
  const dosya = input.files[0];
  const formData = new FormData();
  formData.append("dosya", dosya);
  try {
    toastGoster("İçe aktarma başladı…", "bilgi");
    const token = sessionStorage.getItem("pts_token");
    const cevap = await fetch("/kisiler/toplu-import", {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    });
    if (!cevap.ok) {
      const hata = await cevap.json().catch(() => ({ detail: "Bilinmeyen hata" }));
      throw new Error(hata.detail);
    }
    const sonuc = await cevap.json();
    input.value = "";
    let mesaj = `${sonuc.eklendi} kişi eklendi.`;
    if (sonuc.hatalar?.length) mesaj += ` ${sonuc.hatalar.length} satırda hata.`;
    toastGoster(mesaj, sonuc.eklendi > 0 ? "basari" : "uyari");
    if (sonuc.hatalar?.length) {
      console.warn("İçe aktarma hataları:", sonuc.hatalar);
      alert("Bazı satırlarda hata:\n" + sonuc.hatalar.slice(0, 5).join("\n"));
    }
    kisileriYukle(); panelYenile();
  } catch (err) {
    input.value = "";
    toastGoster(err.message, "hata");
  }
}

