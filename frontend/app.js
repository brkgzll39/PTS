const API = "";  // aynı sunucudan servis edildiği için boş bırakıldı
let sonKayitlarCache = [];

// ---------------------- KÜRESEL HATA YAKALAYICI (2026-09-20) ----------------------
// Backend'in "sıfır sessiz hata" ilkesi (küresel exception handler'lar,
// hemen hemen her uçta try/except + loglama) frontend'de KARŞILIKSIZDI: bir
// render/olay-işleyici fonksiyonundaki yakalanmamış bir hata, yalnızca
// tarayıcı konsoluna (geliştiricinin açıp baktığı yere) düşüp kullanıcıya
// HİÇ görünmeden kayboluyordu. Güvenlik masasındaki bir kullanıcı devtools
// konsolunu asla açmaz, bu yüzden "ekranda bir şey güncellenmiyor ama neden
// bilmiyorum" türü şikayetlerin kök nedeni hiç görünür olmuyordu -- bu, geniş
// kapsamlı bir kod denetiminde tespit edilen en büyük "sessiz hata"
// asimetrisiydi. Artık yakalanmamış HER hata en azından bir toast ile
// bildiriliyor; art arda patlayan bir döngü toast'u spam'lemesin diye
// 10 saniyede bir ile sınırlanıyor. `toastGoster` bu dosyada daha aşağıda
// tanımlı ama fonksiyon bildirimleri JS'te hoisted olduğu için burada
// (dosyanın en başında) çağrılması güvenlidir.
let _sonKuresekHataToastZamani = 0;

function _kuresekHataBildir(mesaj) {
  console.error(mesaj);
  const simdi = Date.now();
  if (simdi - _sonKuresekHataToastZamani < 10000) return;  // spam koruması
  _sonKuresekHataToastZamani = simdi;
  try {
    toastGoster(
      "Beklenmeyen bir arayüz hatası oluştu. Sorun sürerse sayfayı yenileyin veya sistem yöneticisine bildirin.",
      "hata",
    );
  } catch {
    // toastGoster'ın kendisi (örn. DOM/Bootstrap henüz hazır değilse)
    // çağrılamıyorsa sessizce vazgeç -- konsola zaten yukarıda yazıldı.
  }
}

window.addEventListener("error", (olay) => {
  // Kaynak yükleme hataları (örn. başarısız bir <img>) da bu olayı tetikler
  // ama bunlarda `error` alanı hep null'dur -- yalnızca GERÇEK JS
  // hatalarını (script çalışırken fırlatılan) ele alıyoruz.
  if (!olay.error) return;
  _kuresekHataBildir(`Yakalanmamış hata: ${olay.message}`);
});

window.addEventListener("unhandledrejection", (olay) => {
  const sebep = olay.reason;
  const mesaj = sebep instanceof Error ? sebep.message : String(sebep);
  _kuresekHataBildir(`Yakalanmamış promise reddi: ${mesaj}`);
});

// ---------------------- ROL BAZLI ARAYÜZ (RBAC) ----------------------
// Backend'deki _rol_dogrula() politikasıyla birebir eşleşir (backend/main.py).
// izleyici: salt okunur | operatör: günlük işlemler | yonetici: tam yetki
// "sakin" bilinçli olarak -1: panel personeli hiyerarşisinin (izleyici/
// operatör/yönetici) DIŞINDadır, bu yüzden hiçbir data-rol-min eşiğini
// (en düşüğü "izleyici"=0 dahil) hiç sağlamamalı -- normalde sakin girişinde
// zaten authBasarili() erken dönüp rolBazliArayuzuUygula()'yı hiç
// çağırmıyor (bkz. sakinModunuBaslat), ama bu satır ek bir güvenlik katmanı.
// "güvenlik" (Güvenlik Personeli) bilinçli olarak "operatör" ile AYNI
// seviyede (1): görünürlük/yetki açısından ikisi birebir aynıdır (bkz.
// backend/main.py::_rol_dogrula'daki eşdeğerlik notu) -- TEK farkı kayıtlar
// listesinin kendi vardiya saatleriyle filtrelenmesi olup bu FİLTRE backend
// tarafından uygulanır, frontend'de ayrı bir rol seviyesi gerektirmez.
const ROL_SEVIYE = { sakin: -1, izleyici: 0, "operatör": 1, "güvenlik": 1, yonetici: 2 };
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
  // "Güvenlik Personeli Vardiya Filtresi" (bkz. README, 2026-09-18): kayıtlar
  // listesinin backend tarafından SESSİZCE kısaltılması yerine, güvenlik
  // rolündeki kullanıcıya bunun neden olduğu Kayıtlar sekmesinde açıkça
  // belirtilir -- data-rol-min mekanizması yalnızca "en az X rolü" gizleyip/
  // kilitleyebildiği için (tam tersi: "SADECE X rolünde göster" değil) bu
  // banner ayrıca burada, doğrudan mevcutRol karşılaştırmasıyla yönetiliyor.
  const guvenlikBanner = document.getElementById("guvenlikVardiyaBilgisi");
  if (guvenlikBanner) guvenlikBanner.classList.toggle("d-none", mevcutRol !== "güvenlik");
  if (mevcutRol === "güvenlik") guvenlikVardiyaDurumunuGuncelle();
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
  // 2026-09-22 GERÇEK ÜRETİMDE BULUNAN HATA: Panel'deki "NİZAMİYE DURUMU"
  // kartlarına (bkz. nizamiyeSemasiniYukle) tıklayınca "Beklenmeyen bir arayüz
  // hatası oluştu" toast'ı çıkıyordu. Kök neden, o kartların eskiden
  // `onclick="document.querySelector('[data-target=\\"#canli-sekme\\"]')...`
  // biçiminde, JS template literal'i içinde \" ile kaçışlanmış bir inline
  // onclick üretmesiydi -- bu kaçış YALNIZCA JS string literalleri içinde
  // geçerlidir, HTML attribute değerleri İÇİNDE \" diye bir kaçış YOKTUR (HTML
  // bunun yerine &quot; kullanır). `innerHTML` bu diziyi HTML olarak
  // ayrıştırırken onclick attribute'u backslash'ten HEMEN ÖNCEKİ `"`de
  // kesiliyor, geriye `document.querySelector('[data-target=` gibi eksik/
  // sözdizimi hatalı bir JS gövdesi kalıyor -- tıklanınca bu, tam olarak
  // yakalanmamış bir hata olarak patlıyordu. Bu, dosyanın başındaki (satır
  // ~102) "kullanıcı/kamera verisini asla onclick="..." içine JS string'i
  // olarak gömme" uyarısıyla AYNI kök nedenin bir başka görünümü -- burada
  // gömülen veri kullanıcı girdisi değildi ama kaçışlama yine de HTML'de
  // GEÇERSİZDİ. Düzeltme: kartlar artık düz bir `data-gate-hedef` attribute'u
  // taşıyor, hedefe geçiş bu delege edilmiş tık dinleyicisi üzerinden (diğer
  // data-* örüntüleriyle aynı, güvenli yöntemle) yapılıyor.
  const gateEl = e.target.closest("[data-gate-hedef]");
  if (gateEl) {
    sekmeAc(gateEl.dataset.gateHedef);
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

  // 2026-09-22: bkz. style.css'teki #gorselBuyutModal z-index notu -- bu
  // modal olay detayı/plaka geçmişi gibi ZATEN AÇIK olan başka bir modalin
  // içinden de açılabiliyor. CSS'teki yüksek z-index modalin KENDİSİNİ öne
  // çıkarır, ama Bootstrap'ın bu modal için oluşturduğu `.modal-backdrop`
  // AYRI bir elemandır ve varsayılan olarak hâlâ eski (1050) katmanda kalır
  // -- bu da alttaki (görünür) modalin (1055) üstünü örtemeyeceği anlamına
  // gelir. `shown.bs.modal` anında (backdrop DOM'a eklendikten SONRA) en son
  // eklenen backdrop'u (Bootstrap her zaman en sona ekler, yani bu modala
  // ait olan budur) bulup z-index'ini modalin kendisinin altına ama diğer
  // TÜM modal/backdrop'ların üstüne çekiyoruz.
  modalEl.addEventListener("shown.bs.modal", () => {
    const backdroplar = document.querySelectorAll(".modal-backdrop");
    const buBackdrop = backdroplar[backdroplar.length - 1];
    if (buBackdrop) buBackdrop.style.zIndex = "1071";
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

// ---------------------- ARANABİLİR KİŞİ SEÇİMİ ----------------------
// 2026-09-22 kullanıcı isteği: kayıtlı kişi sayısı arttıkça (bkz. ekran
// görüntüsü, onlarca isim) "kişiye bağla" <select>'i içinde doğru kişiyi
// bulmak zorlaşıyor -- "kişi ismi yazınca kayıtlı kişilerin ismi öyle
// gözüksün" istendi. Tarayıcılar native <select>'te "yazarak filtrele"
// desteği sunmaz (yalnızca ilk harfe atlama yapılır); bu yüzden dört ayrı
// kişi-seçim <select>'inin (Ziyaretçi Girişi, Manuel Kayıt, Kaydı Düzenle,
// Yeni Kullanıcı) HİÇBİRİNİ yeniden yazmadan üzerlerine ortak, hafif bir
// "yazarak filtrele" katmanı ekleniyor: select'in hemen üstüne bir arama
// kutusu ekleniyor; yazıldıkça <option>'lar DOM'dan KALDIRILMIYOR (bu,
// zaten seçili bir değeri kaybettirebilir), yalnızca eşleşmeyenler `hidden`
// yapılıyor (tüm modern tarayıcılar <option hidden> öğesini dropdown'dan
// gizler) -- select'in kendi value/onchange davranışı ve onu kullanan
// mevcut kod hiç değişmeden çalışmaya devam eder.
function aramaliSecimEkle(selectEl) {
  if (!selectEl) return;
  let kutu = document.getElementById(selectEl.id + "AramaKutusu");
  if (!kutu) {
    kutu = document.createElement("input");
    kutu.type = "text";
    kutu.id = selectEl.id + "AramaKutusu";
    kutu.className = "form-control form-control-sm mb-1";
    kutu.placeholder = "İsim veya plaka ile ara...";
    kutu.setAttribute("aria-label", "Kişi ara");
    kutu.addEventListener("input", () => {
      const q = kutu.value.trim().toLocaleLowerCase("tr-TR");
      Array.from(selectEl.options).forEach(o => {
        // İlk "Kişiye bağlamadan..." / "Eşleştirme yok" seçeneği (value="")
        // filtreden bağımsız her zaman görünür kalır.
        o.hidden = !!o.value && q !== "" && !o.textContent.toLocaleLowerCase("tr-TR").includes(q);
      });
      // Filtre, o an seçili olan (artık gizlenmiş) bir seçeneği ekrandan
      // kaldırdıysa, kullanıcının görmediği bir kişiye bağlı kalınmasın diye
      // seçim boş seçeneğe çekilir.
      if (selectEl.selectedOptions[0]?.hidden) selectEl.value = "";
    });
    selectEl.parentNode.insertBefore(kutu, selectEl);
  }
  kutu.value = "";
  Array.from(selectEl.options).forEach(o => { o.hidden = false; });
}

function escapeHtml(deger) {
  // Kamera/kullanıcı kaynaklı verileri innerHTML'e basmadan önce kaçış karakterlerine çevirir (XSS önlemi).
  return String(deger ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// 2026-09-23 kullanıcı geri bildirimi (ekran görüntüsüyle): "kişi silmek
// istediğim zaman üstten böyle localhost:8000 gibi gelmesin normal ana
// ekrana kişi silinsin mi diye buton eklensin" -- tarayıcının yerleşik
// confirm() penceresi sitenin adresini ("localhost:8000 web sitesinin
// mesajı") gösteriyor ve uygulamanın geri kalanıyla görsel olarak hiç
// tutarlı değil. Bu, uygulamadaki (yalnızca Kişiler değil) TÜM silme/onay
// akışlarının paylaştığı tek bir sorun sınıfı olduğu için (bkz. aşağıdaki
// tüm confirm() çağrılarının yerini alan kullanım noktaları) tek, paylaşılan
// bir uygulama-içi onay modaliyle (index.html #onayModal) değiştirildi.
//
// confirm()'in aksine ASENKRON'dur (bir modal animasyonla açılıp kullanıcı
// bir düğmeye basana kadar beklemek zorunda) -- bu yüzden çağıran taraf
// `if (!confirm(...)) return;` yerine `if (!(await onayAl(...))) return;`
// kullanmalı (tüm çağıran fonksiyonlar zaten async'ti, bu değişiklik ek bir
// async dönüşümü GEREKTİRMEDİ). Modal kapatma/İptal/Esc/backdrop tıklama
// gibi "onaylanmadı" yollarının HEPSİ `hidden.bs.modal` olayı üzerinden tek
// bir noktada yakalanır, bu yüzden her kapanma yolunu ayrı ayrı ele almaya
// gerek yoktur.
function onayAl(mesaj, secenekler = {}) {
  return new Promise((resolve) => {
    const modalEl = document.getElementById("onayModal");
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    document.getElementById("onayModalBaslik").textContent = secenekler.baslik || "Emin misiniz?";
    document.getElementById("onayModalMetin").textContent = mesaj;
    const onayBtn = document.getElementById("onayModalOnayBtn");
    onayBtn.textContent = secenekler.onayMetni || "Evet, Onayla";
    onayBtn.className = `btn ${secenekler.guvenli ? "btn-primary" : "btn-danger"}`;
    let onaylandi = false;
    onayBtn.addEventListener("click", () => { onaylandi = true; modal.hide(); }, { once: true });
    modalEl.addEventListener("hidden.bs.modal", () => resolve(onaylandi), { once: true });
    modal.show();
  });
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

// 2026-09-22 GERÇEK KULLANICI GERİ BİLDİRİMİ: "Kaydı Düzenle" ekranındaki
// "Kişi eşleştirmesi" alanından bir kişi seçilip kaydedildiğinde, kisi_id
// backend'de doğru güncelleniyordu AMA Kayıtlar/Plaka Analizi tablolarının
// HİÇBİRİ eşleştirilen kişinin ADINI göstermiyordu -- yalnızca TİPİNİ
// (tipRozeti, Abone/Personel/Ziyaretçi rozeti) gösteren "Kişi/Tip" sütunu
// vardı. Bu yardımcı, kayıtta eşleşen bir Kişi varsa onun adını (bkz.
// backend/main.py::_kayitlara_kisi_adini_ekle'nin doldurduğu kisi_adi),
// yoksa (sistemde kayıtlı olmayan bir misafirse) misafir_adi'yı (bkz.
// models.Kayit.misafir_adi) gösterir -- ikisi de yoksa "-" döner.
function kayitIsimGoster(kayit) {
  const isim = kayit.kisi_adi || kayit.misafir_adi;
  return isim ? escapeHtml(isim) : '<span class="text-muted">-</span>';
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
  panelYenile(); sonGecislerYukle(); kayitlariYukle(); kisileriYukle(); ledAyarlariYukle(); lisansYukle(); kameralariYukle();
  grafikYukle(); karaListesiYukle(); bariyerleriYukle(); kullanicilariYukle(); sistemSagliginiYukle();
  bildirimleriYukle(); vardiyaOturumlariniYukle();
  await siteleriYukle(); noktalariYukle();
  sseBaslat();
}

async function oturumKapat() {
  // ÖZ-HİZMET VARDİYA OTURUMU (2026-09-20): rol=="güvenlik" için sunucudaki
  // açık VardiyaOturumu'nu burada, token silinmeden ÖNCE kapatmalıyız (bkz.
  // backend/main.py::cikis_yap) -- aksi halde vardiya "kapanmamış" (yani hâlâ
  // açıkmış) gibi kalır ve bu kullanıcının bir SONRAKİ girişine kadar tüm yeni
  // geçişler kayıtlar listesinde görünmeye devam eder. Çağrı başarısız olsa
  // bile (ağ hatası vb.) çıkışı ASLA engellemeyiz -- token zaten siliniyor,
  // en kötü ihtimalle oturum sunucuda "açık" kalır (bu da bir sonraki girişte
  // zaten otomatik kapanır, bkz. _guvenlik_oturum_baslat).
  try {
    await apiCagir("/auth/cikis", { method: "POST" });
  } catch (e) {
    console.error(e);
  }
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
  if (!(await onayAl("Bu aracı listenizden kaldırmak istiyor musunuz?"))) return;
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

// Backend'deki VARDIYA_MAKS_SURE_SAAT = 8 (main.py, "8 saatlik otomatik
// kapanma") ile AYNI değer -- yalnızca vardiya durum şeridinde kalan süreyi
// göstermek için burada tekrarlanır, sunucudaki gerçek kapanma mantığı
// (main.py::_vardiya_otomatik_kapama_calistir) BU değere değil kendi sabitine
// bakar; ikisi değişirse burası da güncellenmeli.
const VARDIYA_MAKS_SURE_SAAT_DK = 8 * 60;

// Dakika cinsinden bir süreyi "3 sa 12 dk" / "45 dk" biçiminde okunur hale
// getirir -- vardiya durum şeridinde (geçen/kalan süre) ve ileride benzer
// ihtiyaçlarda kullanılmak üzere genel amaçlı tutuldu.
function _saatDkMetni(toplamDk) {
  const dk = Math.max(0, Math.round(toplamDk));
  const saat = Math.floor(dk / 60);
  const kalanDk = dk % 60;
  if (saat > 0) return kalanDk > 0 ? `${saat} sa ${kalanDk} dk` : `${saat} sa`;
  return `${kalanDk} dk`;
}

// "Nizamiye Durumu" şeması (2026-09-21, "benzersiz ana sayfa" isteği): Panel
// sekmesinin en üstünde, soyut KPI sayıları yerine GERÇEK fiziksel giriş
// noktalarının (nizamiye) o anki canlılık durumunu gösterir. Kullanıcının
// tercihi doğrultusunda tamamen KAMERA LİSTESİNDEN OTOMATİK türetilir --
// kameranın "ad" alanına göre gruplanır (bkz. backend'deki aynı "ad bazlı
// nokta kimliği" kuralı: Vardiya Grupları ve Kamera Erişimi de aynı alanı
// kullanır, bkz. main.py::_kullanicinin_izinli_kamera_adlari'nin kök neden
// notu) -- yeni bir kamera eklenip aynı "ad" ile kaydedildiğinde şema elle
// güncellenmeden otomatik büyür. `/kameralar` zaten Canlı İzleme sekmesinde
// kullanılan, TCP/soket açmayan HAFİF bir uç nokta olduğu için (aksine
// `/kameralar/saglik/tumu` her çağrıda gerçek bir soket bağlantısı dener,
// bkz. tumKameralarSaglikKontrol) burada da o kullanılıyor -- panelYenile
// her 15 saniyede bir veya her SSE olayında tetiklendiği için ağır bir
// sağlık taramasını burada tekrar tekrar çalıştırmak istemeyiz.
async function nizamiyeSemasiniYukle() {
  const el = document.getElementById("nizamiyeSemasi");
  if (!el) return;
  try {
    const kameralar = await apiCagir("/kameralar");
    if (!kameralar.length) {
      el.innerHTML = '<div class="empty-state">Henüz kamera eklenmedi</div>';
      return;
    }
    const gruplar = {};
    kameralar.forEach(k => {
      const ad = k.ad || "Adsız";
      (gruplar[ad] = gruplar[ad] || []).push(k);
    });
    el.innerHTML = Object.entries(gruplar).map(([ad, liste]) => {
      const aktifOlanlar = liste.filter(k => k.aktif !== false);
      const canliSayisi = aktifOlanlar.filter(k => k.pipeline_calisiyor && !k.donmus).length;
      const donmusSayisi = aktifOlanlar.filter(k => k.pipeline_calisiyor && k.donmus).length;
      let durumSinif = "down", durumMetni = "Bağlı değil", ikon = "bi-x-circle-fill";
      if (!aktifOlanlar.length) {
        durumSinif = "off"; durumMetni = "Pasif"; ikon = "bi-dash-circle";
      } else if (canliSayisi === aktifOlanlar.length) {
        durumSinif = "ok"; durumMetni = liste.length > 1 ? "Tüm kameralar canlı" : "Canlı"; ikon = "bi-check-circle-fill";
      } else if (canliSayisi > 0 || donmusSayisi > 0) {
        durumSinif = "warn";
        durumMetni = donmusSayisi && !canliSayisi ? "Görüntü donmuş" : `${canliSayisi}/${aktifOlanlar.length} kamera canlı`;
        ikon = "bi-exclamation-triangle-fill";
      }
      const yonler = [...new Set(liste.map(k => k.yon === "giris" ? "Giriş" : "Çıkış"))].join(" + ");
      return `<button type="button" class="gate-card ${durumSinif}" data-gate-hedef="#canli-sekme">
        <div class="gate-dot"></div>
        <div><strong>${escapeHtml(ad)}</strong><span class="gate-status"><i class="bi ${ikon} me-1"></i>${durumMetni}</span><span class="gate-meta">${liste.length} kamera · ${yonler || "-"}</span></div>
      </button>`;
    }).join("");
  } catch (e) {
    el.innerHTML = `<div class="empty-state text-danger">Nizamiye durumu alınamadı: ${escapeHtml(e.message)}</div>`;
  }
}

async function panelYenile() {
  try {
    nizamiyeSemasiniYukle();
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
      // 2026-09-23 KULLANICI GERİ BİLDİRİMİ (birebir): "şu ekranda son
      // geçişlerde tüm alarmlar okundu işaretle demeden son giriş yapan
      // araçların ekranı açılmıyor onları da otomatik yapar mısın" --
      // alarm satırları (ör. "Yetkisiz araç") önceden yalnızca "okundu
      // işaretle" düğmesine sahipti, satırın KENDİSİNE tıklamak hiçbir şey
      // yapmıyordu; kullanıcı aynı geçişin ayrıntısını görebilmek için önce
      // "tüm alarmlar okundu işaretle"ye basıp alarm satırının kaybolup
      // yerine (eğer son 8 kayıt içindeyse) tıklanabilir bir "son geçiş"
      // satırının görünmesini bekliyordu. Artık models.Alarm.kayit_id (bkz.
      // schemas.AlarmCevap) doluysa satırın kendisi de aynı olayDetayAc(id)
      // ile açılıyor -- diğer "son geçiş" satırlarıyla BİREBİR aynı davranış.
      // "Okundu işaretle" düğmesi kendi tıklamasını event.stopPropagation()
      // ile durdurup yalnızca kendi işlevini yapmaya devam eder.
      const alarmSatirlari = alarmlar.map(a => {
        const tiklanabilirMi = a.kayit_id != null;
        const tiklanabilirOznitelikler = tiklanabilirMi
          ? ` role="button" tabindex="0" onclick="olayDetayAc(${a.kayit_id})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();olayDetayAc(${a.kayit_id})}"`
          : "";
        return `<div class="event-row alarm-row${tiklanabilirMi ? " alarm-row-tiklanabilir" : ""}"${tiklanabilirOznitelikler}><div class="event-icon blocked"><i class="bi bi-exclamation-triangle-fill"></i></div><div class="event-main"><strong>${escapeHtml(a.plaka_no)}</strong><span>${alarmTipiEtiketi(a.alarm_tipi)}</span></div>${rolYeterli("operatör") ? `<button class="btn btn-sm btn-light" title="Okundu işaretle" aria-label="Okundu işaretle" onclick="event.stopPropagation(); alarmOkundu(${a.id})"><i class="bi bi-check2"></i></button>` : ""}</div>`;
      }).join("");
      const olaySatirlari = kayitlar.slice(0, 8).map(k => `<button class="event-row event-button" onclick="olayDetayAc(${k.id})"><div class="event-icon ${k.yetki_durumu === "yetkili" ? "allowed" : "blocked"}"><i class="bi ${k.yon === "giris" ? "bi-box-arrow-in-right" : "bi-box-arrow-right"}"></i></div><div class="event-main"><strong>${escapeHtml(k.plaka_no)}</strong><span>${escapeHtml(k.kamera_id)} · ${k.yon === "giris" ? "Giriş" : "Çıkış"}</span></div><div class="event-time">${tarihFormatla(k.tarih_saat).split(",")[1] || "-"}</div></button>`).join("");
      canliOlaylar.innerHTML = alarmSatirlari + olaySatirlari || '<div class="empty-state">Henüz geçiş kaydı yok</div>';
    }
    _kayitCacheBirlestir(kayitlar);
    const canliYenileme = document.getElementById("canliYenileme");
    if (canliYenileme) canliYenileme.textContent = new Date().toLocaleTimeString("tr-TR");
    if (mevcutRol === "güvenlik") guvenlikVardiyaDurumunuGuncelle();
  } catch (e) {
    console.error(e);
  }
}

// ---------------------- SON GEÇİŞLER (sınırsız, sayfalama destekli) ----------------------
// 2026-09-23 kullanıcı isteği: "Panel ekranında sadece Son geçişleri görmek
// istiyorum bir de son geçişler sınırlı olmasın sayfa geçişleri de olmasını
// istiyorum" -- Panel sekmesindeki eski "Son Kayıtlar" kutusu (bkz. yukarıdaki
// panelYenile'nin ESKİ sürümü) her zaman yalnızca en son 10 kaydı gösteriyordu
// ve önceki/sonraki sayfa GEZİNMESİ YOKTU. Panel artık YALNIZCA bu bölümü
// içeriyor (istatistik/grafik/nizamiye durumu gibi diğer her şey, kullanıcının
// tercihiyle, ayrı bir "Kontrol Merkezi" sekmesine taşındı, bkz. index.html).
// Bu fonksiyon, Kayıtlar sekmesindeki kayitlariYukle/sayfaDegistir ile AYNI
// sayfalama desenini (limit/offset + /kayitlar/sayfa-bilgisi) kullanır, ama
// FİLTRE alanları olmadan -- bu ekranın tek amacı ham, kesintisiz bir geçiş
// akışı sunmak.
//
// 2026-09-24 kullanıcı geri bildirimi: "sol taraf 16 araç gösterirken 1.
// sayfada sağ taraf 10 tane araç kaydı gösteriyor, sayfa geçişi yaptığımda
// eksik yansımalar oluyor". İKİ AYRI kök neden bulunup ikisi de düzeltildi:
//
// 1) DENGESİZ SÜTUNLAR: önceden TEK bir karma sorgu (`/kayitlar?limit=25`,
//    yön filtresi YOK) çekilip GİRİŞ/ÇIKIŞ'a istemci tarafında ayrılıyordu.
//    Öz-hizmet giriş/çıkış modelinde (bkz. 2026-09-20 notu) iki yön eşit
//    sıklıkta olmadığından, paylaşılan 25'lik pencere neredeyse HER ZAMAN
//    dengesiz bölünüyordu (ör. 16 giriş / 10 çıkış toplamı bile 25'i geçebilir
//    -- otomatik yenilemeler arada yeni kayıt eklediği için iki çağrı arasında
//    kaymalar da olabiliyordu). DAHA KÖTÜSÜ: bir yönün kaydı seyrekse, o
//    yönün ızgarası sayfalar boyu "kayıt yok" gösterip aslında var olan
//    kayıtlara ulaşmak için gereksiz yere çok sayfa tıklamak gerekiyordu --
//    "daha verimli olsun" isteğinin karşılığı budur. ÇÖZÜM: backend'e eklenen
//    `yon` filtresiyle (bkz. main.py::kayitlari_listele) artık GİRİŞ ve ÇIKIŞ
//    ayrı ayrı, HER BİRİ KENDİ limit/offset'iyle çekiliyor -- her ızgara,
//    kendi türünden yeterince kayıt olduğu sürece HER SAYFADA dolu (25 kart)
//    görünür; sayfa sayısı iki yönden UZUN olanına göre belirlenir (kısa olan
//    yön biterse -- bu artık GERÇEKTEN son sayfasına gelindiği anlamına gelir,
//    rastgele bir bölünme kazası değil).
//
// 2) "EKSİK YANSIMALAR" (sayfa geçişken): bu fonksiyon hem "Önceki/Sonraki"
//    tıklamasıyla HEM DE otomatik yenilemelerle (SSE debounce'u, 15sn'lik
//    kalp atışı) `sifirla=false` ile çağrılıyor -- yani AYNI ANDA birden
//    fazla çağrı iç içe geçebiliyordu. Önceki kod, `await` sonrasında sayfa
//    numarasını (_sonGecislerSayfa) TEKRAR OKUYUP etiketi/butonları ona göre
//    çiziyordu -- ama o ana kadar kullanıcı "Sonraki"ye bir kez daha basmışsa
//    bu değişken artık İLERİ gitmiş oluyordu. Sonuç: yavaş/geç dönen ESKİ bir
//    isteğin verisi, YENİ sayfa numarasının etiketiyle ekrana yazılıyordu
//    (veya ağ sırası tersine döndüyse eski istek yeni isteğin ÜZERİNE yazıp
//    doğru veriyi siliyordu) -- kullanıcının "eksik yansımalar" dediği tam
//    olarak budur. ÇÖZÜM: her çağrıya artan bir "istek numarası" veriliyor;
//    yanıt geldiğinde hâlâ EN SON başlatılan istek DEĞİLSE (araya başka bir
//    çağrı girmişse) sonuç sessizce atılıyor, DOM'a hiç dokunulmuyor -- ekranda
//    her zaman yalnızca en son istenen sayfa görünür.
let _sonGecislerSayfa = 0;
const _sonGecislerLimit = 25;
let _sonGecislerIstekNo = 0;

async function sonGecislerYukle(sifirla = true) {
  if (sifirla) _sonGecislerSayfa = 0;
  const istekNo = ++_sonGecislerIstekNo;
  const sayfa = _sonGecislerSayfa; // bu isteğin ait olduğu sayfa -- await sonrası tekrar okunmaz (bkz. yukarıdaki 2. madde)
  const ortakParams = { limit: _sonGecislerLimit, offset: sayfa * _sonGecislerLimit };
  try {
    const [girisKayitlari, cikisKayitlari, girisSayfaBilgisi, cikisSayfaBilgisi] = await Promise.all([
      apiCagir(`/kayitlar?${new URLSearchParams({ ...ortakParams, yon: "giris" }).toString()}`),
      apiCagir(`/kayitlar?${new URLSearchParams({ ...ortakParams, yon: "cikis" }).toString()}`),
      apiCagir(`/kayitlar/sayfa-bilgisi?${new URLSearchParams({ limit: _sonGecislerLimit, yon: "giris" }).toString()}`),
      apiCagir(`/kayitlar/sayfa-bilgisi?${new URLSearchParams({ limit: _sonGecislerLimit, yon: "cikis" }).toString()}`),
    ]);
    // Araya (bu istek başladıktan SONRA) başka bir sonGecislerYukle çağrısı
    // girdiyse -- ör. kullanıcı "Sonraki"ye tekrar bastı veya bir SSE olayı
    // arka planda yeniden yükleme tetikledi -- bu artık BAYAT bir yanıt: DOM'a
    // hiç dokunma, en son (daha yeni) çağrının kendi yanıtı ekranı zaten
    // güncelleyecek/güncelledi.
    if (istekNo !== _sonGecislerIstekNo) return;

    _kayitCacheBirlestir(girisKayitlari);
    _kayitCacheBirlestir(cikisKayitlari);

    const toplam = girisSayfaBilgisi.toplam + cikisSayfaBilgisi.toplam;
    const sayfaSayisi = Math.max(1, girisSayfaBilgisi.sayfa_sayisi, cikisSayfaBilgisi.sayfa_sayisi);
    const sayacEl = document.getElementById("sonGecislerSayac");
    if (sayacEl) sayacEl.textContent = `${toplam} geçiş · Sayfa ${sayfa + 1}/${sayfaSayisi}`;

    // Artık her ızgara KENDİ yönünden gelen, kendi limit/offset'iyle çekilmiş
    // kayıtları gösteriyor -- bkz. yukarıdaki 1. madde. Sunucudan gelen sıra
    // (en yeniden en eskiye) korunuyor.
    const girisGrid = document.getElementById("sonGecislerGirisGrid");
    const cikisGrid = document.getElementById("sonGecislerCikisGrid");
    if (girisGrid && cikisGrid) {
      girisGrid.innerHTML = girisKayitlari.map(_gecisKartiOlustur).join("") || '<div class="empty-state">Bu sayfada giriş kaydı yok</div>';
      cikisGrid.innerHTML = cikisKayitlari.map(_gecisKartiOlustur).join("") || '<div class="empty-state">Bu sayfada çıkış kaydı yok</div>';
      korumaliGorselleriYukle(girisGrid);
      korumaliGorselleriYukle(cikisGrid);
    }

    const sayfaEl = document.getElementById("sonGecislerSayfalama");
    if (sayfaEl) {
      const onceki = sayfa > 0;
      const sonraki = sayfa < sayfaSayisi - 1;
      sayfaEl.innerHTML = `
        <div class="d-flex gap-2">
          <button class="btn btn-sm btn-outline-secondary" ${!onceki ? "disabled" : ""} onclick="sonGecislerSayfaDegistir(-1)"><i class="bi bi-chevron-left"></i> Önceki</button>
          <button class="btn btn-sm btn-outline-secondary" ${!sonraki ? "disabled" : ""} onclick="sonGecislerSayfaDegistir(1)">Sonraki <i class="bi bi-chevron-right"></i></button>
        </div>
        <span class="small text-muted">${girisKayitlari.length + cikisKayitlari.length ? `Sayfa başına en fazla ${_sonGecislerLimit} giriş + ${_sonGecislerLimit} çıkış · toplam ${toplam}` : ""}</span>`;
    }
  } catch (e) {
    if (istekNo !== _sonGecislerIstekNo) return; // bayat bir isteğin hatası -- yok say
    console.error("Son Geçişler yüklenemedi:", e);
  }
}

function sonGecislerSayfaDegistir(delta) {
  _sonGecislerSayfa = Math.max(0, _sonGecislerSayfa + delta);
  sonGecislerYukle(false);
}

// "Son Geçişler" ızgarasındaki TEK bir kartın HTML'i (bkz. sonGecislerYukle).
// 2026-09-23 kullanıcı isteği (başka bir ANPR panelinden ekran görüntüsüyle):
// eski tablo satırı yerine, görsel üzerine plaka+tarih bindirilmiş bir kart.
//
// Eski tablodaki bilgilerden HİÇBİRİ sessizce kaybolmadı:
// - "Durum" (yetkili/yetkisiz/kara liste vb.) -- artık kartın SOL KENAR
//   ŞERİDİNDE (durum-* sınıfı, badge-* ile AYNI renk paletini kullanır, bkz.
//   style.css) VE görsel üzerindeki rozette (durumRozeti) korunuyor. Bu,
//   güvenlik personelinin "Yetkisiz araç" gibi durumları tablo sütunu
//   olmadan da tek bakışta ayırt edebilmesi için bilinçli bir tercih --
//   yalnızca yön (giriş/çıkış) başlık şeridine göre renklendirseydik bu
//   kritik bilgi kaybolurdu.
// - "Kişi/Tip" rozeti (tipRozeti) kartlara TAŞINMADI (kullanıcının kabul
//   ettiği bilinçli bir sadeleştirme) -- kartın tamamına tıklayınca açılan
//   olayDetayAc() detay modalında hâlâ "Araç Tipi" olarak gösteriliyor.
// - "İsim" ve "Vardiya" kart altında küçük, ikincil bir satırda korunuyor.
//
// 2026-09-24 kullanıcı isteği: "son geçişlerde direkt araç resmine
// tıkladığımda büyük ekranda araç görüntüsü açılmasın not ekleme sayfası
// gelsin". ESKİ davranış: tıklama İKİYE ayrılmıştı -- görsel `.thumb`
// sınıfını taşıyordu ve dosyanın üstündeki paylaşılan `.thumb`/`.zoomable-img`
// document-level tıklama delegasyonu üzerinden büyütme/lightbox
// (buyukGorselAc) açıyordu; yalnızca plaka/tarih şeridi ve not ikonu
// olayDetayAc(id) ile detay/not modalini açıyordu. Artık görsel `.thumb`
// sınıfını TAŞIMIYOR (bkz. style.css::.gecis-karti-gorsel notu) -- bunun
// yerine kartın HER ÜÇ tıklanabilir alanı da (görsel, plaka/tarih şeridi,
// not ikonu) AYNI olayDetayAc(id) detay/not modalini açıyor. Görsel yine de
// kendi onclick/onkeydown'ını taşıyor (kartın TAMAMINA tek bir onclick
// eklenmedi) -- salt erişilebilirlik/tutarlılık için, üç alan da birbirinden
// bağımsız ayrı düğmeler gibi davranmaya devam ediyor. Büyük/yakınlaştırılmış
// görseli görmek isteyen kullanıcı artık açılan detay modalindeki görsele
// tıklayabilir (o hâlâ `.zoomable-img`, bkz. #olayModalGorsel).
function _gecisKartiOlustur(k) {
  const yonSinifi = k.yon === "giris" ? "yon-giris" : "yon-cikis";
  const yonEtiketi = k.yon === "giris" ? "GİRİŞ" : "ÇIKIŞ";
  const isim = kayitIsimGoster(k);
  const isimBos = isim === '<span class="text-muted">-</span>';
  // İsim boşsa (kişiye/misafire bağlı değilse) yalnızca "- · A" gibi anlamsız
  // bir tire kalmasın diye, alt bilgi satırı yalnızca GERÇEKTEN dolu olan
  // parçalardan (isim, vardiya) kuruluyor.
  const altBilgiParcalari = [isimBos ? null : isim, k.vardiya_adi ? escapeHtml(k.vardiya_adi) : null].filter(Boolean);
  return `
    <div class="gecis-karti durum-${escapeHtml(k.yetki_durumu)} ${yonSinifi}">
      <div class="gecis-karti-baslik">
        <span class="gecis-karti-kamera" title="${escapeHtml(k.kamera_id)}">${escapeHtml(k.kamera_id)} - ${yonEtiketi}</span>
        <button class="gecis-karti-not-btn" onclick="olayDetayAc(${k.id})" title="${k.not_metni ? "Not var, görmek için tıklayın" : "Detay / not ekle"}" aria-label="Detay ve not">
          <i class="bi ${k.not_metni ? "bi-chat-left-text-fill" : "bi-chat-left-text"}"></i>
        </button>
      </div>
      <div class="gecis-karti-gorsel-wrap">
        ${k.goruntu_yolu
          ? `<img class="gecis-karti-gorsel" data-goruntu-yolu="${escapeHtml(k.goruntu_yolu)}" role="button" tabindex="0" onclick="olayDetayAc(${k.id})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();olayDetayAc(${k.id})}" alt="${escapeHtml(k.plaka_no)} geçiş görseli, detay ve not eklemek için tıklayın veya Enter'a basın">`
          : `<div class="gecis-karti-gorsel-yok"><i class="bi bi-camera-video-off"></i></div>`}
        <span class="gecis-karti-durum-rozeti">${durumRozeti(k.yetki_durumu)}</span>
        <button class="gecis-karti-alt-serit" onclick="olayDetayAc(${k.id})" title="Kaydı görüntüle">
          <span class="gecis-karti-plaka">${escapeHtml(k.plaka_no)}</span>
          <span class="gecis-karti-tarih">${tarihFormatla(k.tarih_saat)}</span>
        </button>
      </div>
      ${altBilgiParcalari.length ? `<div class="gecis-karti-footer small text-muted">${altBilgiParcalari.join(" · ")}</div>` : ""}
    </div>`;
}

// Güvenlik personeli için teşhis: sunucunun "şu an" bilgisi + kullanıcının
// kendi vardiya OTURUMLARI (2026-09-20: öz-hizmet giriş/çıkış tabanlı sisteme
// geçildi, bkz. backend/main.py::vardiya_oturumu_durumum ve README'deki aynı
// tarihli not). 2026-09-18 kullanıcı geri bildirimi -- vardiyası olmasına
// rağmen canlı geçişlerin Kayıtlar sekmesinde görünmediği bildirilmişti --
// bu, filtrenin NEDEN boş kaldığını sunucu/istemci saat karşılaştırmasıyla
// teşhis etmeye yarar; aynı gerekçe öz-hizmet sistemi için de geçerli.
// Kontrol Merkezi sekmesindeki vardiya durum şeridi (bkz. index.html
// #vardiyaHeroSeridi, "benzersiz ana sayfa" isteği, 2026-09-21; 2026-09-23'te
// bu şerit -- Panel sekmesinin geri kalanıyla birlikte -- Panel'den ayrı bir
// "Kontrol Merkezi" sekmesine taşındı, bkz. sonGecislerYukle'nin üstündeki
// not). Ayrı bir uç nokta çağırmaz --
// guvenlikVardiyaDurumunuGuncelle'nin ZATEN çektiği /vardiya-oturumlari/durumum
// yanıtını (d) yeniden kullanır, bu yüzden bu fonksiyon o fonksiyonun İÇİNDEN
// çağrılır, ayrı bir async akış olarak DEĞİL.
function _vardiyaHeroSeridiniGuncelle(d) {
  const heroEl = document.getElementById("vardiyaHeroSeridi");
  if (!heroEl) return;
  if (!d || !d.rol_guvenlik_mi) { heroEl.classList.add("d-none"); heroEl.innerHTML = ""; return; }
  const grupMu = !!d.vardiya_adi;
  const adEtiketi = grupMu ? `"${escapeHtml(d.vardiya_adi)}" Vardiyası` : "Vardiyanız";
  const acikOturum = (d.oturumlar || []).find(o => o.devam_ediyor);
  let sinif, ozet;
  if (acikOturum) {
    const simdi = new Date(d.sunucu_simdiki_zaman);
    const giris = new Date(acikOturum.giris_zamani);
    const gecenDk = (simdi - giris) / 60000;
    const kalanDk = VARDIYA_MAKS_SURE_SAAT_DK - gecenDk;
    sinif = "active";
    ozet = kalanDk > 0
      ? `${_saatDkMetni(gecenDk)} önce giriş yapıldı · ${_saatDkMetni(kalanDk)} sonra otomatik kapanacak`
      : "8 saatlik süre doldu, sıradaki otomatik kapanma taramasında kapatılacak";
  } else {
    sinif = "inactive";
    ozet = "Şu an açık bir oturum yok";
  }
  heroEl.classList.remove("d-none");
  heroEl.className = `shift-banner mb-3 ${sinif}`;
  heroEl.innerHTML = `<div class="shift-dot"></div><div><strong>${adEtiketi} ${acikOturum ? "aktif" : "kapalı"}</strong><span>${ozet}</span></div>`;
}

async function guvenlikVardiyaDurumunuGuncelle() {
  const el = document.getElementById("guvenlikVardiyaDurumu");
  if (!el || mevcutRol !== "güvenlik") return;
  try {
    const d = await apiCagir("/vardiya-oturumlari/durumum");
    _vardiyaHeroSeridiniGuncelle(d);
    if (!d.rol_guvenlik_mi) { el.innerHTML = ""; return; }
    const sunucuSaati = tarihFormatla(d.sunucu_simdiki_zaman);
    const istemciSaati = tarihFormatla(new Date().toISOString());
    // "Vardiya Grupları" (2026-09-21): vardiya_adi doluysa bu bilgi ARTIK
    // yalnızca bu hesabı değil, AYNI grubu paylaşan tüm hesapları yansıtır
    // (bkz. backend/main.py::vardiya_oturumu_durumum) -- metin buna göre
    // netleştirilir, aksi halde "vardiyanız açık/kapalı" ifadesi başka bir
    // hesabın oturumuna dayandığında kafa karıştırıcı olurdu.
    const grupMu = !!d.vardiya_adi;
    const aktifDurum = d.su_an_aktif_vardiya_var_mi
      ? `<span class="text-success fw-bold"><i class="bi bi-check-circle-fill"></i> ${grupMu ? `"${escapeHtml(d.vardiya_adi)}" vardiya grubunda şu an AÇIK bir oturum var` : "Vardiyanız şu an AÇIK (giriş yaptığınızdan beri)"}</span>`
      : `<span class="text-danger fw-bold"><i class="bi bi-x-circle-fill"></i> ${grupMu ? `"${escapeHtml(d.vardiya_adi)}" vardiya grubunda şu an AÇIK bir oturum YOK` : "Şu an açık bir vardiyanız YOK -- çıkış yapmış görünüyorsunuz"}</span>`;
    let oturumListesi = "";
    if (!d.toplam_oturum_sayisi) {
      oturumListesi = '<div class="text-warning">Hiç vardiya oturumu yok -- bu normalde olmamalı (her girişte otomatik açılır), lütfen sayfayı yenileyin.</div>';
    } else {
      const satirlar = (d.oturumlar || []).map(o => {
        const rozet = o.devam_ediyor ? '<span class="badge bg-success">devam ediyor</span>' : '<span class="badge bg-secondary">kapandı</span>';
        const cikisMetni = o.cikis_zamani ? tarihFormatla(o.cikis_zamani) : "devam ediyor";
        return `<div>${tarihFormatla(o.giris_zamani)} → ${cikisMetni} ${rozet}</div>`;
      }).join("");
      oturumListesi = `<div class="mt-1">Son ${d.oturumlar.length} ${grupMu ? `"${escapeHtml(d.vardiya_adi)}" vardiya grubu` : "vardiya"} oturumu:</div>${satirlar}`;
    }
    el.innerHTML = `<div>Sunucu saati: <strong>${sunucuSaati}</strong> · Tarayıcınızın saati: <strong>${istemciSaati}</strong></div><div>${aktifDurum}</div>${oturumListesi}` +
      (sunucuSaati !== istemciSaati ? '<div class="text-warning mt-1"><i class="bi bi-exclamation-triangle-fill"></i> Sunucu ile tarayıcınızın saati farklı görünüyor -- kayıt görünürlüğü SUNUCU saatine göre belirlenir.</div>' : "");
  } catch (e) {
    el.textContent = "Vardiya durumu alınamadı: " + e.message;
    const heroEl = document.getElementById("vardiyaHeroSeridi");
    if (heroEl) heroEl.classList.add("d-none");
  }
}

async function alarmOkundu(id) {
  try {
    await apiCagir(`/alarmlar/${id}/okundu`, { method: "PATCH" });
    panelYenile();
  } catch (e) {
    toastGoster(e.message, "hata");
  }
}

async function olayDetayAc(id) {
  let kayit = sonKayitlarCache.find(item => item.id === id);
  if (!kayit) {
    // 2026-09-23 KRİTİK HATA DÜZELTMESİ (gerçek kullanıcı geri bildirimi:
    // "tüm alarmlar okundu işaretle demeden son giriş yapan araçların ekranı
    // açılmıyor"): sonKayitlarCache yalnızca panelYenile'nin çektiği "son 10"
    // kaydı tutuyor (bkz. dosyanın başındaki değişkenin tanımı ve
    // _kayitCacheBirlestir). "Son Geçişler" widget'ındaki bir ALARM satırına
    // (ör. "Yetkisiz araç") bağlı kayıt, aradan geçen başka trafik yüzünden
    // bu "son 10" listesinin dışında kalmışsa, önceden bu fonksiyon burada
    // SESSİZCE `return` ediyordu -- kullanıcı satıra tıklayınca HİÇBİR ŞEY
    // olmuyordu, tüm alarmlar okundu işaretlenip panel yenilendiğinde kayıt
    // tesadüfen tekrar "son 10" içine girince çalışıyormuş GİBİ görünüyordu.
    // Artık önbellekte yoksa kayıt doğrudan sunucudan (GET /kayitlar/{id})
    // çekilip önbelleğe eklenir; bu da başarısız olursa (kayıt silinmiş,
    // vardiya/kamera erişimi yetersiz vb.) sessiz kalmak yerine kullanıcıya
    // AÇIKÇA bir hata bildirilir.
    try {
      kayit = await apiCagir(`/kayitlar/${id}`);
      _kayitCacheYerindeGuncelle(kayit);
    } catch (e) {
      toastGoster("Kayıt açılamadı: " + e.message, "hata");
      return;
    }
  }
  // 2026-09-22 KRİTİK HATA DÜZELTMESİ: bu fonksiyon YENİ bir SSE bildirimine
  // tıklanınca da çağrılıyor (bkz. sseBaslat içindeki toastGoster(...,
  // () => olayDetayAc(kayit.id)) çağrısı). #gorselBuyutModal, kendisini
  // AÇTIĞI modalin (bu modal dahil) önünde görünmesi için bilinçli olarak
  // her zaman en yüksek z-index'e sahip (bkz. style.css notu, 2026-09-22
  // önceki düzeltme). Ama bu SABİT yüksek z-index, o lightbox açıkken
  // SONRADAN gösterilen bu modali de (yeni aracın bilgisiyle güncellenmiş
  // olsa bile) görsel olarak KAPATIYORDU -- kullanıcı bildirimine tıklamasına
  // rağmen ekranda eski, artık geçersiz büyütülmüş fotoğraf kalmaya devam
  // ediyordu, yeni aracı görmek için onu elle kapatması gerekiyordu. Bu
  // modal her (yeniden) gösterildiğinde, eğer lightbox hâlâ açıksa önce onu
  // kapatıyoruz ki altındaki (az önce güncellenen) bu modal görünür olsun.
  bootstrap.Modal.getInstance(document.getElementById("gorselBuyutModal"))?.hide();
  const detay = kayit.kisi_id ? await apiCagir(`/kisiler/${kayit.kisi_id}`).catch(() => null) : null;
  // Kameranın bağlı olduğu erişim noktasını (ve varsa sitesini/bariyerini) bul —
  // kameralar ile siteler/bariyerler arasındaki tek bağlantı Nokta kaydıdır.
  // ÖNEMLİ (2026-09-21, "id vs ad" hata sınıfı -- bkz. schemas.NoktaCevap.
  // kamera_adi'nin docstring'i): kayit.kamera_id HER ZAMAN kameranın "ad"
  // alanıdır, Nokta.kamera_id ise "id"dir -- bu yüzden burada n.kamera_id
  // DEĞİL, sunucunun ayrıca hesapladığı n.kamera_adi ile karşılaştırılır.
  // Eskiden n.kamera_id ile karşılaştırılıyordu ve id!=ad olduğu (yani
  // neredeyse HER kurulumda) bu eşleşme hiçbir zaman tutmuyor, "Bağlı site
  // tanımlı değil" her olayda sessizce gösteriliyordu.
  const noktalar = await apiCagir("/noktalar").catch(() => []);
  const nokta = noktalar.find(n => n.kamera_adi && n.kamera_adi === kayit.kamera_id) || null;
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
  // 2026-09-22 kullanıcı isteği: "tanımsız araç dediği yer boş dönüyorsa
  // onlar güncellensin" -- sistemde kayıtlı bir Kişi'ye (detay) bağlı
  // OLMAYAN bir kayıt için artık her zaman düz "Tanımsız araç" yerine,
  // varsa kaydın misafir_adi'sı (bkz. models.Kayit.misafir_adi, "Kaydı
  // Düzenle"/Ziyaretçi Girişi'nde girilebilir) gösteriliyor.
  document.getElementById("olayModalKisi").textContent = detay?.ad_soyad || kayit.misafir_adi || "Tanımsız araç";
  document.getElementById("olayModalDaire").textContent = detay?.daire_departman || "-";
  document.getElementById("olayModalAracTipi").textContent = detay ? (detay.tip === "ziyaretci" ? "Ziyaretçi" : "Tanımlı") : (kayit.misafir_adi ? "Misafir" : "Tanımsız araç");
  // 2026-09-22: kullanıcı isteği -- "OCR güven skoru gibi şeyleri görmeme
  // gerek yok, onların yerine Not yazınca not bilgisi eklensin". GÜVEN
  // SKORU/OCR DÜZELTMESİ alanları (operasyonel personel için anlamsız, teknik
  // OCR ayrıntıları) kaldırıldı; yerine kaydın NOT alanı (Kayit.not_metni)
  // gösteriliyor. Bu bilgiler tamamen kaybolmuyor -- Excel/PDF dışa aktarımda
  // ve "Kaydı Düzenle" ekranında hâlâ mevcut, yalnızca bu hızlı-bakış
  // modalinden çıkarıldı.
  const notEl = document.getElementById("olayModalNot");
  notEl.textContent = kayit.not_metni || "-";
  notEl.title = kayit.not_metni || "";
  _olayModalAnalizButonunuAyarla(kayit);
  _olayModalNotButonunuAyarla(kayit);
  await _ziyaretciGirisiKutusunuAyarla(kayit);
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

// 2026-09-22: "NOT" alanının yanındaki kalem ikonu -- kaydın notunu (ve
// gerekirse plaka/yön/durum/kişi eşleştirmesini) tam düzenleyebilmek için
// zaten var olan "Kaydı Düzenle" ekranına (kayitDuzenleAc, main.py::kayit_duzenle)
// yönlendirir. Yeni bir düzenleme arayüzü İCAT ETMEK yerine mevcut, zaten
// rol bazlı (data-rol-min="operatör") kısıtlı ve test edilmiş akış yeniden
// kullanılıyor -- bkz. _olayModalAnalizButonunuAyarla'daki AYNI "önce bu
// modali kapat, sonra diğerini aç" deseni.
function _olayModalNotButonunuAyarla(kayit) {
  const btn = document.getElementById("olayModalNotDuzenleBtn");
  if (!btn) return;
  btn.onclick = () => {
    bootstrap.Modal.getInstance(document.getElementById("olayDetayModal"))?.hide();
    kayitDuzenleAc(kayit.id);
  };
}

// "Ziyaretçi Girişi" hızlı onay kutusu: bir tespiti tek tuşla bir kişiye/
// daireye bağlayıp yetki_durumu="ziyaretci_onayli" yapan akış (PATCH
// /kayitlar/{id}, yeni bir backend uç noktası GEREKMEZ -- bkz. README'deki
// 2026-09-17 "Ziyaretçi Girişi" notu). 2026-09-24 kullanıcı isteği:
// "ziyaretçi giriş onayla + bariyer aç kısmınıda düzelt sadece ziyaretçi
// giriş onayla kalsın" -- bu akış eskiden AYNI ANDA bariyeri de açıyordu
// (POST /bariyer/{id}/ac), artık YALNIZCA onaylıyor, bariyer açmıyor (bkz.
// index.html'deki aynı tarihli yorum ve README). "Bağımsız Ziyaretçi
// Girişi" formu (ziyaretciBilgileriAc, aşağıda) BUNDAN ETKİLENMEDİ -- o
// akışta kamera tespiti hiç yok, bariyeri açmak formun TEK amacı.
async function _ziyaretciGirisiKutusunuAyarla(kayit) {
  const kutu = document.getElementById("ziyaretciGirisiKutusu");
  const zatenOnayli = kayit.yetki_durumu === "yetkili" || kayit.yetki_durumu === "ziyaretci_onayli";
  document.getElementById("ziyaretciGirisiSonuc").textContent = "";
  document.getElementById("olayModalMisafirAdi").value = "";
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
  const btn = document.getElementById("ziyaretciGirisiBtn");
  btn.onclick = async () => {
    const sonuc = document.getElementById("ziyaretciGirisiSonuc");
    if (kayit.yetki_durumu === "kara_liste" && !(await onayAl("Bu araç KARA LİSTEDE. Yine de ziyaretçi olarak onaylamak istediğinize emin misiniz? Bu işlem kayda geçer."))) {
      return;
    }
    btn.disabled = true;
    sonuc.className = "small mt-1";
    sonuc.textContent = "İşleniyor...";
    try {
      const govde = { yetki_durumu: "ziyaretci_onayli" };
      const misafirAdi = document.getElementById("olayModalMisafirAdi").value.trim();
      if (misafirAdi) govde.misafir_adi = misafirAdi;
      const notMetni = document.getElementById("olayModalZiyaretciNot").value.trim();
      if (notMetni) govde.not_metni = notMetni;
      const guncelKayit = await apiCagir(`/kayitlar/${kayit.id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(govde),
      });
      // 2026-09-22 KRİTİK HATA DÜZELTMESİ: bkz. _kayitCacheYerindeGuncelle'nin
      // docstring'i -- panelYenile()/kayitlariYukle(false) YARIŞ DURUMU
      // yüzünden bu kaydın az önce girilen not/misafir_adi/kişi
      // eşleştirmesini SİLEBİLİYORDU, kullanıcı aynı olayı (ekranı kapatıp
      // açmadan) tekrar açtığında eski veriyi görüyordu. Önce önbellek
      // DOĞRUDAN güncellenir, SONRA hâlâ açık olan bu modal aynı kaydın artık
      // güncel hâliyle (yeni başlık: "ZİYARETÇİ GİRİŞİ ONAYLANDI", İSİM/NOT
      // dolu, onay kutusu gizli) YENİDEN ÇİZİLİR -- kullanıcının modali
      // kapatıp tekrar açmasına gerek kalmaz.
      _kayitCacheYerindeGuncelle(guncelKayit);
      sonuc.className = "small mt-1 text-success";
      sonuc.textContent = "Ziyaretçi girişi onaylandı.";
      toastGoster("Ziyaretçi girişi onaylandı: " + kayit.plaka_no, "basari");
      kutu.classList.add("d-none");
      panelYenile();
      sonGecislerYukle(false);
      kayitlariYukle(false);
      await olayDetayAc(guncelKayit.id);
    } catch (err) {
      sonuc.className = "small mt-1 text-danger";
      sonuc.textContent = err.message;
    } finally {
      btn.disabled = false;
    }
  };
}

// 2026-09-24 kullanıcı isteği: "araçlarda bariyer aç kısmını kaldıralım,
// kayıtsız olan araçlarda da sadece ziyaretçi giriş diye bir buton
// ekleyelim bariyer aç butonu gereksiz" -- olayDetayModal'daki koşulsuz,
// ayrı "Bariyer Aç" düğmesi (#bariyerAcBtn) ve onu yöneten bu fonksiyon
// KALDIRILDI (bkz. index.html'deki aynı tarihli yorum). Bariyer açma artık
// yalnızca _ziyaretciGirisiKutusunuAyarla'nın kurduğu "Ziyaretçi Girişi"
// akışı üzerinden yapılıyor; "yetkili" araçlar için zaten backend'de
// otomatik açılıyor (bkz. main.py). Genel bariyer test/yönetim paneli
// (bariyerAc(id), aşağıda) bundan ETKİLENMEDİ -- o donanım kurulum/test
// amaçlı ayrı bir ekran.

async function lisansYukle() {
  try {
    const lisans = await apiCagir("/lisans");
    // Lisans AKTİF olsa bile bitişe _LISANS_UYARI_ESIK_GUN (14) gün veya daha
    // az kaldıysa "yakinda_doluyor" true döner (2026-09-20 -- bkz. backend
    // _lisans_kalan_gun_ekle): süre dolup kameralar aniden durmadan ÖNCE
    // turuncu bir uyarı gösteriyoruz, "aktif"/"pasif" ikili durumunun
    // dışında üçüncü bir görsel durum olarak.
    const yakindaDoluyor = lisans.aktif && lisans.yakinda_doluyor;
    const durumMetni = !lisans.aktif ? "Aktivasyon bekliyor" : yakindaDoluyor ? "Süresi yakında doluyor" : "Aktif";
    const ikonSinifi = !lisans.aktif ? "bi-shield-exclamation" : yakindaDoluyor ? "bi-shield-exclamation" : "bi-shield-check";
    const kartSinifi = !lisans.aktif ? "pending" : yakindaDoluyor ? "warning" : "active";
    const durumEl = document.getElementById("lisansDurum");
    const altMetin = !lisans.aktif
      ? "Kamera kullanımını etkinleştirmek için anahtar girin"
      : yakindaDoluyor
        ? `Lisans ${lisans.kalan_gun} gün içinde dolacak — süresi dolmadan yeni bir anahtar girin, aksi halde kameralar otomatik olarak durur`
        : "Kamera bağlantıları kullanılabilir";
    if (durumEl) durumEl.innerHTML = `<div class="license-icon ${kartSinifi}"><i class="bi ${ikonSinifi}"></i></div><div><strong>${durumMetni}</strong><span>${escapeHtml(altMetin)}</span></div>`;
    document.getElementById("lisansMiniDurum").innerHTML = `<i class="bi ${ikonSinifi}"></i> Lisans ${!lisans.aktif ? "pasif" : yakindaDoluyor ? `${lisans.kalan_gun} gün kaldı` : "aktif"}`;
    document.getElementById("lisansMiniDurum").classList.toggle("active", lisans.aktif && !yakindaDoluyor);
    document.getElementById("lisansMiniDurum").classList.toggle("warning", yakindaDoluyor);
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
      // 2026-09-20: ROI artık dikdörtgen (x1..y2) VEYA serbest çizim/polygon
      // ({tip:"polygon", noktalar:[...]}) olabilir -- rozet metni buna göre
      // ayrılır (bkz. backend/schemas.py::KameraRoiGuncelle).
      const roiRozeti = k.roi
        ? (k.roi.tip === "polygon"
          ? `<span class="badge bg-info-subtle text-info-emphasis ms-1" title="Tespit alanı sınırlı: ${k.roi.noktalar.length} köşeli serbest çizim (polygon) alanı geçerli"><i class="bi bi-pentagon"></i> Alan sınırlı</span>`
          : `<span class="badge bg-info-subtle text-info-emphasis ms-1" title="Tespit alanı sınırlı: yalnızca karenin %${Math.round(k.roi.x1)}-%${Math.round(k.roi.x2)} (yatay) / %${Math.round(k.roi.y1)}-%${Math.round(k.roi.y2)} (dikey) bölgesi geçerli"><i class="bi bi-crop"></i> Alan sınırlı</span>`)
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
      // 2026-09-25 kullanıcı isteği: "tanımlı kamera listesine tanımlı
      // kameranın ismini değiştirmek için buton koyar mısın" -- kameranın
      // GÜNCEL adı, olası özel karakterler (tek/çift tırnak vb.) yüzünden
      // onclick attribute'una GÖMÜLMEDEN (bkz. dosyada başka yerlerde
      // tekrarlanan AYNI güvenlik notu, ör. olayModalAnaliz/plaka
      // örüntüleri), yalnızca güvenli bir id ile çağrılıyor --
      // kameraAdDuzenleAc(id) kendi içinde _kameralarCache'ten okuyor.
      const adDuzenleBtn = rolYeterli("operatör")
        ? `<button type="button" class="btn btn-sm btn-link p-0 ms-1 align-baseline" title="Kamera adını değiştir" aria-label="Kamera adını değiştir" onclick="kameraAdDuzenleAc('${k.id}')"><i class="bi bi-pencil-square"></i></button>`
        : "";
      return `<tr><td><strong>${escapeHtml(k.ad)}</strong>${adDuzenleBtn}${roiRozeti}</td><td>${yonSecim}</td><td class="text-muted small text-truncate" style="max-width: 180px">${escapeHtml(k.rtsp_url)}</td><td>${durum}${yenidenBaglanmaBadge}</td><td>${tcpBadge}</td><td class="text-nowrap">${silBtn}${yenidenBtn}${roiBtn}</td></tr>`;
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

// ---------------------- KAMERA ADINI DEĞİŞTİRME ----------------------
// 2026-09-25 kullanıcı isteği: "tanımlı kamera listesine tanımlı kameranın
// ismini değiştirmek için buton koyar mısın". Yön değiştirmede olduğu gibi
// (bkz. yukarıdaki kameraYonDegistir'in dayandığı main.py::kamera_yon_degistir
// notu) kameranın id'si/RTSP adresi hiç değişmeden yalnızca "ad" güncellenir
// -- ama bu sefer backend AYRICA bu kameraya ait geçmiş Kayit satırlarını da
// günceller (bkz. main.py::kamera_ad_degistir'in docstring'i, "id vs ad" kök
// nedeni) -- bu yüzden basit bir satır-içi metin kutusu yerine, ne olacağını
// açıklayan bir uyarı metniyle birlikte küçük bir onay modali kullanıldı.
let _kameraAdDuzenleId = null;

function kameraAdDuzenleAc(id) {
  const kamera = (_kameralarCache || []).find(k => k.id === id);
  if (!kamera) return;
  _kameraAdDuzenleId = id;
  document.getElementById("kameraAdDuzenleGirdi").value = kamera.ad;
  document.getElementById("kameraAdDuzenleSonuc").textContent = "";
  bootstrap.Modal.getOrCreateInstance(document.getElementById("kameraAdDuzenleModal")).show();
}

document.getElementById("kameraAdDuzenleKaydetBtn")?.addEventListener("click", async () => {
  const sonuc = document.getElementById("kameraAdDuzenleSonuc");
  const yeniAd = document.getElementById("kameraAdDuzenleGirdi").value.trim();
  if (!yeniAd) {
    sonuc.className = "small mt-2 text-danger";
    sonuc.textContent = "Kamera adı boş olamaz.";
    return;
  }
  const btn = document.getElementById("kameraAdDuzenleKaydetBtn");
  btn.disabled = true;
  sonuc.className = "small mt-2";
  sonuc.textContent = "Kaydediliyor...";
  try {
    await apiCagir(`/kameralar/${_kameraAdDuzenleId}/ad`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ad: yeniAd }),
    });
    toastGoster("Kamera adı güncellendi.", "basari");
    bootstrap.Modal.getInstance(document.getElementById("kameraAdDuzenleModal"))?.hide();
    kameralariYukle();
  } catch (err) {
    sonuc.className = "small mt-2 text-danger";
    sonuc.textContent = err.message;
  } finally {
    btn.disabled = false;
  }
});

// ---------------------- KAMERA TESPİT ALANI (ROI) ----------------------
// Giriş ve çıkış kameralarının açıları birbirinin şeridini de görüyorsa, bir
// araç her iki kamerada da tespit edilip hem "giriş" hem "çıkış" olarak ayrı
// ayrı kaydedilebiliyor (bkz. README.md'deki 2026-09-17 notu). Bu modal, canlı
// bir kare üzerinde yüzdesel bir dikdörtgen (ROI) tanımlayarak her kameranın
// SADECE kendi şeridine denk gelen bölgeyi izlemesini sağlar.
//
// GÜNCELLEME (2026-09-20, kullanıcı geri bildirimi birebir): "kare seçimde
// bazen farklı yönden geçen araçları da tespit ediyor bunu istemiyorum" --
// bir şerit çapraz/eğik açıdan görüntülendiğinde dikdörtgen komşu şeridi de
// kapsayabiliyor. Bu yüzden dikdörtgenin YANINA (onun yerine değil -- basit
// durumlarda dikdörtgen hâlâ daha hızlı/kolay) SERBEST ÇİZİM (polygon) modu
// eklendi: kullanıcı görüntü üzerine sırayla tıklayarak şeridin gerçek
// hattını takip eden keyfi bir çokgen çizebilir (bkz. backend/camera_reader.py::
// _kutu_polygon_icinde_mi).

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

// Serbest çizim (polygon) noktaları -- {x, y} yüzde (0-100) çiftleri, sırayla.
let _roiPoligonNoktalari = [];

function roiModuDegisti() {
  const poligonSecili = document.getElementById("roiModPoligon")?.checked === true;
  document.getElementById("roiKareAlanlari").classList.toggle("d-none", poligonSecili);
  document.getElementById("roiPoligonAlanlari").classList.toggle("d-none", !poligonSecili);
  document.getElementById("roiKutuOnizleme").classList.toggle("d-none", poligonSecili);
  document.getElementById("roiPoligonSvg").classList.toggle("d-none", !poligonSecili);
  document.getElementById("roiSonuc").textContent = "";
  if (poligonSecili) _roiPoligonOnizlemeGuncelle();
}

function roiPoligonTiklandi(event) {
  if (document.getElementById("roiModPoligon")?.checked !== true) return;
  const svg = event.currentTarget;
  const dikdortgen = svg.getBoundingClientRect();
  const x = ((event.clientX - dikdortgen.left) / dikdortgen.width) * 100;
  const y = ((event.clientY - dikdortgen.top) / dikdortgen.height) * 100;
  _roiPoligonNoktalari.push({
    x: Math.round(Math.max(0, Math.min(100, x)) * 10) / 10,
    y: Math.round(Math.max(0, Math.min(100, y)) * 10) / 10,
  });
  _roiPoligonOnizlemeGuncelle();
}

function roiPoligonSonNoktayiSil() {
  _roiPoligonNoktalari.pop();
  _roiPoligonOnizlemeGuncelle();
}

function roiPoligonTemizle() {
  _roiPoligonNoktalari = [];
  _roiPoligonOnizlemeGuncelle();
}

const _ROI_SVG_ISIM_ALANI = "http://www.w3.org/2000/svg";

function _roiPoligonOnizlemeGuncelle() {
  const svg = document.getElementById("roiPoligonSvg");
  if (!svg) return;
  while (svg.firstChild) svg.removeChild(svg.firstChild);

  const noktaSayisi = document.getElementById("roiPoligonNoktaSayisi");
  if (noktaSayisi) {
    noktaSayisi.textContent = _roiPoligonNoktalari.length === 0
      ? "0 nokta"
      : `${_roiPoligonNoktalari.length} nokta${_roiPoligonNoktalari.length < 3 ? " (en az 3 gerekli)" : ""}`;
  }
  if (_roiPoligonNoktalari.length === 0) return;

  const noktaMetni = _roiPoligonNoktalari.map(n => `${n.x},${n.y}`).join(" ");
  if (_roiPoligonNoktalari.length >= 3) {
    const cokgen = document.createElementNS(_ROI_SVG_ISIM_ALANI, "polygon");
    cokgen.setAttribute("points", noktaMetni);
    cokgen.setAttribute("fill", "rgba(255, 193, 7, 0.25)");
    cokgen.setAttribute("stroke", "#ffc107");
    cokgen.setAttribute("stroke-width", "0.6");
    cokgen.setAttribute("vector-effect", "non-scaling-stroke");
    svg.appendChild(cokgen);
  } else {
    const cizgi = document.createElementNS(_ROI_SVG_ISIM_ALANI, "polyline");
    cizgi.setAttribute("points", noktaMetni);
    cizgi.setAttribute("fill", "none");
    cizgi.setAttribute("stroke", "#ffc107");
    cizgi.setAttribute("stroke-width", "0.6");
    cizgi.setAttribute("vector-effect", "non-scaling-stroke");
    svg.appendChild(cizgi);
  }
  _roiPoligonNoktalari.forEach((n, i) => {
    const daire = document.createElementNS(_ROI_SVG_ISIM_ALANI, "circle");
    daire.setAttribute("cx", n.x);
    daire.setAttribute("cy", n.y);
    daire.setAttribute("r", "1.2");
    daire.setAttribute("fill", i === 0 ? "#dc3545" : "#ffc107");
    daire.setAttribute("stroke", "#212529");
    daire.setAttribute("stroke-width", "0.3");
    daire.setAttribute("vector-effect", "non-scaling-stroke");
    svg.appendChild(daire);
  });
}

async function kameraRoiAc(id) {
  const kamera = _kameralarCache.find(k => k.id === id);
  if (!kamera) return;
  document.getElementById("roiKameraId").value = id;
  document.getElementById("roiKameraAdi").textContent = kamera.ad;
  const poligonMi = kamera.roi && kamera.roi.tip === "polygon";
  document.getElementById("roiModKare").checked = !poligonMi;
  document.getElementById("roiModPoligon").checked = poligonMi;
  document.getElementById("roiX1").value = (kamera.roi && !poligonMi) ? Math.round(kamera.roi.x1) : "";
  document.getElementById("roiY1").value = (kamera.roi && !poligonMi) ? Math.round(kamera.roi.y1) : "";
  document.getElementById("roiX2").value = (kamera.roi && !poligonMi) ? Math.round(kamera.roi.x2) : "";
  document.getElementById("roiY2").value = (kamera.roi && !poligonMi) ? Math.round(kamera.roi.y2) : "";
  _roiPoligonNoktalari = poligonMi ? kamera.roi.noktalar.map(n => ({ x: n.x, y: n.y })) : [];
  document.getElementById("roiSonuc").textContent = "";
  _roiOnizlemeGuncelle();
  roiModuDegisti();
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
  const poligonMi = document.getElementById("roiModPoligon")?.checked === true;

  let govde;
  if (poligonMi) {
    if (_roiPoligonNoktalari.length < 3) {
      sonuc.className = "small mt-2 text-danger";
      sonuc.textContent = "Serbest çizim için en az 3 nokta işaretlemelisiniz. Sınırı tamamen kaldırmak için 'Sınırı Kaldır' butonunu kullanın.";
      return;
    }
    govde = { polygon: _roiPoligonNoktalari };
  } else {
    const x1 = document.getElementById("roiX1").value;
    const y1 = document.getElementById("roiY1").value;
    const x2 = document.getElementById("roiX2").value;
    const y2 = document.getElementById("roiY2").value;
    if (x1 === "" || y1 === "" || x2 === "" || y2 === "") {
      sonuc.className = "small mt-2 text-danger";
      sonuc.textContent = "Dört değer de (Sol/Üst/Sağ/Alt) girilmeli. Sınırı tamamen kaldırmak için 'Sınırı Kaldır' butonunu kullanın.";
      return;
    }
    govde = { x1: Number(x1), y1: Number(y1), x2: Number(x2), y2: Number(y2) };
  }

  try {
    await apiCagir(`/kameralar/${id}/roi`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(govde),
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
  document.getElementById("zbMisafirAdi").value = "";
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
    aramaliSecimEkle(kisiSecim);
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
  const misafirAdi = document.getElementById("zbMisafirAdi").value.trim();
  const notMetni = document.getElementById("zbNot").value.trim();

  const btn = document.getElementById("zbKaydetBtn");
  btn.disabled = true;
  sonuc.className = "small"; sonuc.textContent = "İşleniyor...";
  try {
    const kayit = await apiCagir("/kayitlar", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plaka_no: plaka, kamera_id: kameraId, yon, misafir_adi: misafirAdi || null, not_metni: notMetni || null }),
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
    sonGecislerYukle(false);
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

// 2026-09-21: GERÇEK ÜRETİMDE BULUNAN HATA -- "LOJMAN A Vardiyası" ile
// "yönetici" hesapları AYNI tarayıcıda iki farklı sekmede açıkken, ikinci
// sekmedeki kamera karoları hiç görüntü almıyordu (karo HTML'si geliyor ama
// görüntü siyah/donmuş kalıyordu). Kök neden: tarayıcılar aynı origin'e
// (host:port) HTTP/1.1 üzerinden en fazla ~6 eşzamanlı bağlantı açmaya izin
// verir ve bu sınır TARAYICI SEKMELERİ ARASINDA PAYLAŞILIR (sekmeye özel
// değil). PTS düz HTTP üzerinden çalışıyor (bkz. calistir.bat), her kamera
// karosu `_kameraAkisiBaslat` ile SÜRESİZ açık bir MJPEG bağlantısı tutuyor,
// buna bir de gerçek zamanlı olaylar için süresiz SSE bağlantısı ekleniyor
// (bkz. aşağıda `sseBaglantisiniBaslat`) -- iki sekme birlikte kamera sayısı
// arttıkça bu ~6 bağlantı sınırını kolayca aşabiliyor, sınırı aşan bağlantılar
// tarayıcı tarafından SESSİZCE kuyrukta bekletiliyor (ne hata, ne de zaman
// aşımı -- sonsuza dek "bağlantı bekleniyor" durumunda kalıyor).
//
// Kalıcı/doğru çözüm (çoklu kamera + çoklu eşzamanlı izleyici) tüm kare
// akışını tek bir bağlantıda çoğullamak (ör. websocket) olurdu; bu daha büyük
// bir mimari değişiklik. Bunun yerine, daha küçük ve daha güvenli bir önlemle
// asıl israfı ortadan kaldırıyoruz: bir tarayıcı SEKMESİ arka plana
// alındığında (kullanıcı başka bir sekmeye/uygulamaya geçtiğinde), o sekmenin
// tuttuğu TÜM kamera akış bağlantılarını bırakıyoruz (Page Visibility API,
// bkz. aşağıdaki `visibilitychange` dinleyicisi); sekme tekrar öne geldiğinde
// en son bilinen canlı kamera listesiyle yeniden açıyoruz. Böylece arka
// plandaki bir sekme, önde olan sekmenin bağlantı payını sonsuza dek işgal
// etmiyor. Bu, gerçek üretim kullanım deseninde (her nöbet noktası kendi
// bilgisayarında/tarayıcısında) zaten hiç tetiklenmez; yalnızca aynı
// tarayıcıda birden fazla hesabın sekmelerde açık tutulduğu senaryoları
// (ör. test/denetim amaçlı) düzeltir.
let _sonCanliKameralar = [];

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

// Akış başlatma/durdurma mantığının kendisi (kameraDuvariniGuncelle'dan
// çıkarıldı, bkz. yukarıdaki 2026-09-21 kök neden notu) -- hem normal karo
// yenilemesinde HEM DE sekme visibilitychange ile öne geldiğinde, karo
// HTML'sini yeniden kurmadan sadece bağlantıları (ve plaka anketini) açıp
// kapatabilmek için ayrı bir fonksiyon. `canliKameralar` boş dizi verilirse
// (sekme arka plandayken) sadece mevcut akışları durdurur, hiçbir şey açmaz.
function _canliAkislariBaslat(canliKameralar) {
  _tumKameraAkislariniDurdur();
  if (_kameraPlakaInterval) { clearInterval(_kameraPlakaInterval); _kameraPlakaInterval = null; }
  if (!canliKameralar.length) return;

  canliKameralar.forEach(k => _kameraAkisiBaslat(k.id));

  // Son plaka overlay — 2 sn'de bir güncelle
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

// Sekme arka plana alınıp öne geldiğinde akışları durdurup yeniden başlatır
// (bkz. yukarıdaki 2026-09-21 kök neden notu). `_sonCanliKameralar`, en son
// `kameraDuvariniGuncelle` çağrısında hesaplanan canlı kamera listesidir --
// sekme arka planda kalırken bir kamera eklenip/silinmiş olsa bile, sekme
// öne geldiğinde zaten bir sonraki `kameralariYukle()` çağrısı listeyi
// tazeleyecektir (ör. Kamera Yönetimi'nde bir işlem yapılınca).
document.addEventListener("visibilitychange", () => {
  _canliAkislariBaslat(document.hidden ? [] : _sonCanliKameralar);
});

function kameraDuvariniGuncelle(kameralar) {
  const duvar = document.getElementById("kameraDuvari");
  const sayacBtn = document.getElementById("kameraSayacBtn");
  if (!duvar) return;
  if (sayacBtn) sayacBtn.innerHTML = `<i class="bi bi-grid-2x2"></i> ${kameralar.length} Kamera`;
  if (!kameralar.length) {
    duvar.innerHTML = `<div class="camera-tile camera-simulated"><div class="camera-label"><span><i class="bi bi-camera-video-fill me-1"></i>KAMERA TANIMLI DEĞİL</span><span class="camera-status">Simülasyon</span></div><div class="camera-empty"><i class="bi bi-camera-video"></i><strong>Henüz kamera eklenmedi</strong><small>Kamera Yönetimi ekranından RTSP kamera ekleyin</small></div></div>`;
    _sonCanliKameralar = [];
    _canliAkislariBaslat([]);
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
  //
  // 2026-09-21: akışlar burada KOŞULSUZ başlatılmıyor -- sekme şu an arka
  // plandaysa (document.hidden) hiç açılmıyor; en son bilinen listeyi
  // `_sonCanliKameralar`'da tutup gerçek başlatma/durdurma kararını
  // `_canliAkislariBaslat`'a bırakıyoruz (bkz. yukarıdaki kök neden notu ve
  // visibilitychange dinleyicisi).
  const canliKameralar = kameralar.filter(k => k.pipeline_calisiyor);
  _sonCanliKameralar = canliKameralar;
  _canliAkislariBaslat(document.hidden ? [] : canliKameralar);
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
  if (!(await onayAl("Bu kamerayı silmek istediğinize emin misiniz?"))) return;
  try {
    await apiCagir(`/kameralar/${id}`, { method: "DELETE" });
    kameralariYukle();
  } catch (e) {
    toastGoster(e.message, "hata");
  }
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
  return !!aktif && [
    "filtrePlaka", "filtreBaslangic", "filtreBaslangicSaat", "filtreBitis", "filtreBitisSaat", "filtreDurum",
  ].includes(aktif.id);
}

// Bir tarih (<input type="date">) ve opsiyonel bir saat (<input type="time">)
// alanını backend'in beklediği TEK bir ISO 8601 dizgesine birleştirir.
// 2026-09-21 kullanıcı talebi: "kayıt filtreleme kısmına saat seçme özelliği
// de ekler misin, sadece tarih var, belirli saat aralıklarıyla da kayıt
// almam gerekiyor" -- saat alanı BOŞ bırakılırsa (eski/varsayılan davranış)
// yalnızca tarih gönderilir ("YYYY-MM-DD"), backend bunu "o günün tamamı"
// olarak yorumlamaya devam eder (bkz. main.py::_bitis_tarih_filtresi_sinirini_hesapla
// -- ayrım tam olarak dizgede "T" olup olmamasına göre yapılıyor, bu yüzden
// burada saat verildiğinde MUTLAKA "T" ayırıcılı tam ISO biçimi üretilmeli).
function _tarihSaatDegeriOlustur(tarihId, saatId) {
  const tarih = document.getElementById(tarihId).value;
  if (!tarih) return "";
  const saat = document.getElementById(saatId).value;
  return saat ? `${tarih}T${saat}:00` : tarih;
}

// 2026-09-22 kullanıcı talebi: "Kayıtlar ekranından plaka yazarak arama
// yaptığımda ve o plaka ile işim bittiği zaman panel ekranına geçiş
// yapıyorum. Tekrar Kayıtlar ekranına döndüğümde en son aradığım plaka
// ekranda gözüküyor" -- Bootstrap'ın tab-pane'leri sayfa yüklendiğinden beri
// DOM'da KALICI tuttuğu için (sekme değişince yalnızca gizleniyor, hiçbir
// zaman yeniden oluşturulmuyor), `filtrePlaka` alanı kullanıcı elle
// temizleyene kadar bir önceki aramayı göstermeye devam ediyordu.
//
// Kullanıcının Kayıtlar'dan başka bir sekmeye geçmesini "bu aramayla işim
// bitti" sinyali olarak yorumluyoruz: sekmeden AYRILDIĞI anda (Bootstrap'ın
// `hidden.bs.tab` olayı -- hem üst menüdeki `data-bs-toggle="tab"`
// düğmelerinden HEM DE `sekmeAc()` üzerinden `bootstrap.Tab...show()` ile
// tetiklenen tüm geçişlerde, ör. Panel'deki hızlı erişim/nizamiye kartları,
// güvenilir biçimde tetiklenir) plaka VE tarih aralığı alanlarını temizleyip
// listeyi filtresiz olarak yeniden yüklüyoruz -- böylece Kayıtlar'a her
// döndüğünde temiz bir liste bulur.
//
// 2026-09-23 kullanıcı geri bildirimi (birebir): "kayıtlar ekranında tarih
// filtreleyip kayıt aldığımda başka ekrana geçip tekrar kayıtlar ekranına
// geçiş yapınca en son filtrelediğim tarih sabit kalıyor ... filtrelemeyi
// sıfırlamanı istiyorum" -- ve hemen ardından aynı oturumda: "vardiya ve
// yetki durumu da sıfırlansın". Yani plaka, tarih aralığı (filtreBaslangic/
// filtreBaslangicSaat/filtreBitis/filtreBitisSaat), yetki durumu
// (filtreDurum) VE vardiya (filtreVardiyaAdi) -- Kayıtlar ekranındaki TÜM
// filtre alanları -- artık sekmeden ayrılınca sıfırlanıyor. (Önceki bir
// sürümde yetki durumu/vardiya "bir vardiya boyunca sadece yetkisiz
// geçişleri açık tutmak" gibi kalıcı bir tercih olabileceği varsayımıyla
// BİLİNÇLİ olarak dokunulmadan bırakılmıştı; kullanıcı bu varsayımın kendisi
// için geçerli olmadığını belirtti.)
(function () {
  const kayitlarSekmeDugmesi = document.querySelector('[data-bs-target="#kayitlar-sekme"]');
  if (!kayitlarSekmeDugmesi) return;
  kayitlarSekmeDugmesi.addEventListener("hidden.bs.tab", () => {
    const metinAlanIdleri = ["filtrePlaka", "filtreBaslangic", "filtreBaslangicSaat", "filtreBitis", "filtreBitisSaat", "filtreDurum", "filtreVardiyaAdi"];
    const doluAlanVarMi = metinAlanIdleri.some(id => document.getElementById(id)?.value);
    if (!doluAlanVarMi) return;
    metinAlanIdleri.forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
    kayitlariYukle();
  });
})();

// 2026-09-23 kullanıcı geri bildirimi: "son geçişler de başka sayfaya
// geçiyorum geri döndüğümde en son baktığım sayfada kalıyor görüntü" --
// yukarıdaki Kayıtlar sekmesindeki AYNI davranış sınıfının bir başka örneği:
// sekmeden ayrılınca sayfa numarası (_sonGecislerSayfa) sıfırlanmıyordu, bu
// yüzden ör. 3. sayfadayken başka bir sekmeye geçip geri dönünce hâlâ 3.
// sayfadaydı -- yeni gelen geçişleri görmek için elle "Önceki"ye basmak
// gerekiyordu, "Son Geçişler" adının vaat ettiğinin tam tersi bir deneyim.
// Aynı `hidden.bs.tab` deseni kullanılıyor (hem üst nav-tabs hem sidebar
// üzerinden gelen geçişlerde güvenilir biçimde tetiklenir).
(function () {
  const panelSekmeDugmesi = document.querySelector('[data-bs-target="#panel-sekme"]');
  if (!panelSekmeDugmesi) return;
  panelSekmeDugmesi.addEventListener("hidden.bs.tab", () => {
    if (_sonGecislerSayfa === 0) return;  // zaten 1. sayfadaysa gereksiz bir yeniden yükleme yapma
    sonGecislerYukle();  // varsayılan sifirla=true -- 1. sayfaya döner
  });
})();

function filtreParametreleri() {
  const params = new URLSearchParams();
  const plaka = document.getElementById("filtrePlaka").value.trim();
  const baslangic = _tarihSaatDegeriOlustur("filtreBaslangic", "filtreBaslangicSaat");
  const bitis = _tarihSaatDegeriOlustur("filtreBitis", "filtreBitisSaat");
  const durum = document.getElementById("filtreDurum").value;
  // "Vardiya Grupları" (2026-09-21) -- bkz. main.py::kayitlari_listele. Bu
  // filtre `disaAktar`'da da (Excel/PDF, AYNI `filtreParametreleri` çağrısı)
  // otomatik olarak kullanılır.
  const vardiyaAdi = document.getElementById("filtreVardiyaAdi")?.value || "";
  if (plaka) params.set("plaka", plaka);
  if (baslangic) params.set("baslangic", baslangic);
  if (bitis) params.set("bitis", bitis);
  if (durum) params.set("yetki_durumu", durum);
  if (vardiyaAdi) params.set("vardiya_adi", vardiyaAdi);
  params.set("limit", _kayitlarLimit);
  params.set("offset", _kayitlarSayfa * _kayitlarLimit);
  return params;
}

async function kayitlariYukle(sifirla = true) {
  if (sifirla) _kayitlarSayfa = 0;
  const params = filtreParametreleri();
  // NOT (2026-09-21): sayfa-bilgisi çağrısı, /kayitlar ile AYNI filtre
  // parametrelerini (özellikle yeni saat-birleştirmeli baslangic/bitis'i)
  // kullanmalı -- önceden bu iki çağrı filtre alanlarını BİRBİRİNDEN
  // BAĞIMSIZ, ayrı ayrı okuyordu (bkz. eski kod); bu "tek gerçek kaynak"
  // ihlali, saat filtresi eklenirken biri güncellenip diğeri unutulursa
  // tablo ile toplam sayaç/sayfalama arasında SESSİZCE tutarsızlık
  // doğurabilirdi. Artık `params`'tan limit/offset çıkarılıp AYNEN yeniden
  // kullanılıyor.
  const sayfaBilgisiParams = new URLSearchParams(params);
  sayfaBilgisiParams.delete("offset");
  const [kayitlar, sayfaBilgisi] = await Promise.all([
    apiCagir(`/kayitlar?${params.toString()}`),
    apiCagir(`/kayitlar/sayfa-bilgisi?${sayfaBilgisiParams.toString()}`),
  ]);
  _kayitCacheBirlestir(kayitlar);
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
      <td class="small">${kayitIsimGoster(k)}</td>
      <td class="small">${k.surucu_adi ? escapeHtml(k.surucu_adi) : '<span class="text-muted">-</span>'}</td>
      <td>${k.vardiya_adi ? `<span class="badge bg-info text-dark">${escapeHtml(k.vardiya_adi)}</span>` : '<span class="text-muted small">-</span>'}</td>
      ${rolYeterli("yonetici") ? `<td>${dogrulamaRozeti(k.dogrulama_kare_sayisi, k.farkli_okuma_sayisi)}</td>` : ""}
      <td class="text-nowrap">
        <button class="btn btn-sm btn-outline-danger" onclick="kayitPdfIndir(${k.id})" title="PDF indir" aria-label="PDF indir"><i class="bi bi-file-earmark-pdf"></i></button>
        ${rolYeterli("operatör") ? `<button class="btn btn-sm btn-outline-primary ms-1" onclick="kayitDuzenleAc(${k.id})" title="Kaydı düzenle" aria-label="Kaydı düzenle"><i class="bi bi-pencil"></i></button>` : ""}
        ${rolYeterli("yonetici") ? `<button class="btn btn-sm btn-outline-secondary ms-1" onclick="kayitSil(${k.id})" title="Kaydı sil" aria-label="Kaydı sil"><i class="bi bi-trash"></i></button>` : ""}
      </td>
    </tr>
  `).join("") || `<tr><td colspan="13" class="text-center text-muted py-3">Kayıt bulunamadı</td></tr>`;
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
  // 2026-09-22 KRİTİK HATA DÜZELTMESİ: bu düğme yalnızca Kayıtlar ekranının
  // ANA tablosunda var, yani ekrandaki "Vardiya" filtresi (#filtreVardiyaAdi)
  // o an aktifse, bu kayıt kullanıcıya TAM OLARAK o filtre sayesinde
  // görünüyordur (bkz. backend/main.py::kayit_detay_pdf_indir'in
  // `vardiya_adi` parametresinin docstring'i) -- bu değer buraya da
  // iletilmezse, kendi vardiyası DIŞINDA bir vardiyayı filtreleyen bir
  // güvenlik kullanıcısı listede gördüğü bir kaydı indirmeye çalışınca
  // "Bu kayıt vardiyanıza ait değil" (403) hatası alıyordu.
  const params = new URLSearchParams();
  const vardiyaAdi = document.getElementById("filtreVardiyaAdi")?.value;
  if (vardiyaAdi) params.set("vardiya_adi", vardiyaAdi);
  window.open(indirmeUrlOlustur(`/disa-aktar/pdf/kayit/${id}`, params), "_blank");
}

// Bir geçiş kaydını (plaka, yön, durum, kişi eşleştirmesi, not) panelden tam
// düzenleyebilmek için (bkz. main.py::kayit_duzenle). Örn. OCR'ın "39 SU 877"yi
// tek bir karede "04 SD 377" olarak yanlış okuyup kaydettiği bir vakada,
// operatör plakayı düzeltebilir ya da kaydı doğrulayabilir/not düşebilir.
// KÖK NEDEN DÜZELTMESİ (2026-09-22 kullanıcı geri bildirimi -- ekran
// görüntüleriyle: "BİR DE BU EKRAN ŞİMDİ NOT VE İSİM EKLEDİM EKRANI KAPATIP
// AÇMADAN GÜNCELLENMİYOR BUNA DA Bİ ÇARE BULALIM"):
//
// "Kaydı Düzenle" (kayitDuzenleForm) veya "Ziyaretçi Girişi" onayı (bkz.
// _ziyaretciGirisiKutusunuAyarla) sonrasında PATCH /kayitlar/{id}'nin yanıtı
// önceden yalnızca panelYenile()/kayitlariYukle(false) gibi TAM LİSTE
// yenilemelerine bırakılıyordu. Sorun: panelYenile() `/kayitlar?limit=10`
// çağırıp sonKayitlarCache'i TAMAMEN DEĞİŞTİRİYOR (bkz. panelYenile), ve bu
// iki fonksiyon (panelYenile, kayitlariYukle) birbirini AWAIT ETMEDEN eş
// zamanlı çalıştığı için hangisinin ağ isteğinin daha SON tamamlanacağı bir
// YARIŞ DURUMU (race condition) -- düzenlenen kayıt panelYenile'nin çektiği
// "son 10" listesinde değilse (ör. daha eski bir kayıt), o kaydın az önce
// kaydedilen değişikliği sonKayitlarCache'ten SİLİNEBİLİYORDU. Sonuç:
// kullanıcı aynı kaydı (aynı olay/satır) tekrar açtığında (olayDetayAc/
// kayitDuzenleAc, ikisi de sonKayitlarCache'ten okur) ESKİ veriyi görüyordu
// -- yalnızca SAYFAYI TAMAMEN YENİLEDİĞİNDE (ki bu da aslında aynı yarışı
// yeniden oynatıyor, arada bir "şans eseri" düzeliyordu) güncel veriyi
// görebiliyordu.
//
// Kalıcı ve YARIŞTAN BAĞIMSIZ çözüm: PATCH'in kendi yanıtı (backend artık
// bkz. main.py::kayit_duzenle'nin sonundaki kisi_adi/vardiya_adi ekleme
// notu -- liste uç noktalarıyla TUTARLI, TAM bir KayitCevap döner) HER ZAMAN
// otoriter kabul edilip sonKayitlarCache'teki karşılığı DERHAL (herhangi bir
// ağ isteğinin tamamlanmasını beklemeden) güncellenir -- sonraki
// panelYenile()/kayitlariYukle(false) çağrıları yalnızca YENİ gelen kayıtları
// veya listedeki BAŞKA değişiklikleri yakalamak için hâlâ çalıştırılır, ama
// artık bu tek kaydın verisini SİLME riski taşımazlar.
// KÖK NEDEN DÜZELTMESİ, DEVAM (2026-09-22 -- bir önceki düzeltmenin
// EKSİK olduğu bulundu): panelYenile() önceden `sonKayitlarCache = kayitlar;`
// ile önbelleği TAMAMEN DEĞİŞTİRİYORDU (yalnızca `/kayitlar?limit=10`'daki
// SON 10 kayıtla). Bu, _kayitCacheYerindeGuncelle'nin az önce yazdığı
// güncel veriyi de siliyordu -- çünkü panelYenile HER SSE olayında (bkz.
// _canliBolumleriTazeleDebounce) otomatik olarak tekrar çalışıyor. Yani:
// eski bir kaydı düzenleyip kaydettiniz, ekran doğru göründü, AMA bariyerden
// bir sonraki araç geçer geçmez (birkaç saniye içinde) o düzeltme yeniden
// "kayboluyordu" -- ilk düzeltme sorunu yalnızca GEÇİCİ OLARAK gizlemişti.
// Çözüm: kayitlariYukle()'nin zaten kullandığı AYNI "birleştir, değiştirme"
// deseni tek bir ortak yardımcıya taşındı ve panelYenile de artık BUNU
// kullanıyor. Sınırsız büyümeyi önlemek için en fazla 500 kayıt tutulur
// (bkz. _sseKayitAl'daki AYNI sınır, satır ~2397) -- limit aşılırsa en eski
// kayıtlar (tarih_saat'e göre) atılır.
function _kayitCacheBirlestir(yeniKayitlar) {
  sonKayitlarCache = [...sonKayitlarCache.filter(k => !yeniKayitlar.find(n => n.id === k.id)), ...yeniKayitlar];
  if (sonKayitlarCache.length > 500) {
    sonKayitlarCache.sort((a, b) => new Date(b.tarih_saat) - new Date(a.tarih_saat));
    sonKayitlarCache.length = 500;
  }
}

function _kayitCacheYerindeGuncelle(guncelKayit) {
  if (!guncelKayit || guncelKayit.id == null) return;
  const idx = sonKayitlarCache.findIndex(k => k.id === guncelKayit.id);
  if (idx === -1) {
    // Kayıt daha önce hiç önbellekte değildi (ör. çok eski bir kayıt) --
    // yine de eklenir ki bu id ile tekrar açılan bir modal boş dönmesin.
    sonKayitlarCache.unshift(guncelKayit);
  } else {
    sonKayitlarCache[idx] = { ...sonKayitlarCache[idx], ...guncelKayit };
  }
}

async function kayitDuzenleAc(id) {
  const kayit = sonKayitlarCache.find(k => k.id === id);
  if (!kayit) return;
  document.getElementById("duzenleKayitId").value = id;
  document.getElementById("duzenleKayitPlaka").value = kayit.plaka_no;
  document.getElementById("duzenleKayitYon").value = kayit.yon;
  document.getElementById("duzenleKayitDurum").value = kayit.yetki_durumu;
  document.getElementById("duzenleKayitMisafirAdi").value = kayit.misafir_adi || "";
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
  aramaliSecimEkle(kisiSecim);

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
    misafir_adi: document.getElementById("duzenleKayitMisafirAdi").value || null,
    not_metni: document.getElementById("duzenleKayitNot").value || null,
  };
  if (kisiSecim) {
    govde.kisi_id = Number(kisiSecim);
  } else if (kayit?.kisi_id) {
    govde.kisi_id_temizle = true;
  }
  try {
    const guncelKayit = await apiCagir(`/kayitlar/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(govde) });
    bootstrap.Modal.getInstance(document.getElementById("kayitDuzenleModal"))?.hide();
    // 2026-09-22 KRİTİK HATA DÜZELTMESİ: "bu ekran şimdi not ve isim
    // ekledim ekranı kapatıp açmadan güncellenmiyor" -- bkz. aşağıdaki
    // _kayitCacheYerindeGuncelle'nin docstring'i.
    _kayitCacheYerindeGuncelle(guncelKayit);
    kayitlariYukle(false);
    panelYenile();
    sonGecislerYukle(false);
    analizAcikSeAyniPlakayiYenile();
  } catch (err) {
    sonuc.className = "small text-danger"; sonuc.textContent = err.message;
  }
});

async function kayitSil(id) {
  if (!(await onayAl("Bu geçiş kaydını kalıcı olarak silmek istediğinize emin misiniz? Bu işlem geri alınamaz."))) return;
  try {
    await apiCagir(`/kayitlar/${id}`, { method: "DELETE" });
    // 2026-09-22: silinen kayıt, bir sonraki TAM liste yenilemesine kadar
    // (panelYenile()/kayitlariYukle() birer MERGE yaptığı için -- bkz.
    // _kayitCacheBirlestir -- kendi fetch sonucunda artık hiç dönmeyecek
    // olsa bile eski önbellek girdisini SİLMEZLER) sonKayitlarCache'te
    // hayalet olarak kalıyordu; bu da o id'ye tıklayan (ör. eski bir toast,
    // ikinci bir sekme) bir kullanıcıya artık var olmayan bir kaydı
    // gösterebiliyordu. Silme başarılı olur olmaz doğrudan çıkarılır.
    sonKayitlarCache = sonKayitlarCache.filter(k => k.id !== Number(id));
    kayitlariYukle(false);
    panelYenile();
    sonGecislerYukle(false);
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
  // 2026-09-22 kullanıcı isteği: "aracın sisteme kayıtlara ilk giriş tarihi
  // eklensin. son güncel geçiş tarihi ve saati eklensin. Not ekleyen
  // Personel ... bilgisi yazılsın ... yetkisiz araç olduğunda kırmızı ile
  // belirtilsin". Bu üç alan (ilk_gecis/son_gecis/son_not_*) ve
  // son_yetki_durumu backend/main.py::_kisilerin_gecis_ozetini_ekle
  // tarafından hesaplanıp GET /kisiler yanıtına eklendi -- burada sadece
  // gösteriliyor, ayrı bir istek YAPILMIYOR.
  tbody.innerHTML = kisiler.map(k => {
    const plakaKirmizi = k.son_yetki_durumu === "yetkisiz";
    const sonNot = k.son_not_metni
      ? `${escapeHtml(k.son_not_metni)}${k.son_not_ekleyen ? ` <span class="text-muted small">(${escapeHtml(k.son_not_ekleyen)})</span>` : ""}`
      : '<span class="text-muted small">-</span>';
    // 2026-09-23 kullanıcı isteği: "birden fazla aracı olanların araçlarını
    // kişiye tıklayınca sıralı bir şekilde görecek şekilde düzenle" -- bu
    // rozet, listede kaç ek plakası olduğunu tek bakışta gösterir (önceden
    // hiçbir gösterge yoktu); tam sıralı listeye tıklanınca (kisiDuzenleAc)
    // Düzenle penceresindeki #duzenleEkPlakalarListe'den ulaşılır.
    const ekSayisi = (k.ek_plakalar || []).length;
    const ekRozeti = ekSayisi > 0
      ? ` <button type="button" class="badge ek-plaka-rozeti border-0" onclick="kisiDuzenleAc(${k.id})" title="${ekSayisi} ek aracı daha var -- tümünü sıralı görmek için tıklayın">+${ekSayisi}</button>`
      : "";
    return `
    <tr>
      <td>${escapeHtml(k.ad_soyad)}</td>
      <td class="fw-bold"><button class="plate-link${plakaKirmizi ? " plate-link-yetkisiz" : ""}" data-plaka-analiz="${escapeHtml(k.plaka_no)}" title="${plakaKirmizi ? "Son geçişi YETKİSİZ olarak işaretlendi -- " : ""}Geçiş geçmişini ve görsellerini gör">${escapeHtml(k.plaka_no)}</button>${ekRozeti}</td>
      <td>${tipRozeti(k.tip)}</td>
      <td>${escapeHtml(k.telefon) || "-"}</td>
      <td>${escapeHtml(k.daire_departman) || "-"}</td>
      <td>${k.aktif ? '<span class="badge bg-success">Aktif</span>' : '<span class="badge bg-secondary">Pasif</span>'}</td>
      <td class="small">${k.ilk_gecis ? tarihFormatla(k.ilk_gecis) : '<span class="text-muted">-</span>'}</td>
      <td class="small">${k.son_gecis ? tarihFormatla(k.son_gecis) : '<span class="text-muted">-</span>'}</td>
      <td class="small">${sonNot}</td>
      <td>
        ${rolYeterli("operatör") ? `
        <button class="btn btn-sm btn-outline-primary" onclick="kisiDuzenleAc(${k.id})" title="Düzenle"><i class="bi bi-pencil"></i></button>
        <button class="btn btn-sm btn-outline-secondary" onclick="kisiDurumDegistir(${k.id}, ${!k.aktif})" title="Aktif/Pasif Yap"><i class="bi bi-toggle2-on"></i></button>
        <button class="btn btn-sm btn-outline-warning" onclick="kisiGecmisKayitlariGuncelle(${k.id})" title="Bu kişinin plakasına ait, kaydedilmeden ÖNCEKİ eski 'yetkisiz' geçişleri yeniden değerlendirir"><i class="bi bi-clock-history"></i></button>
        <button class="btn btn-sm btn-outline-danger" onclick="kisiSil(${k.id})" title="Sil"><i class="bi bi-trash"></i></button>
        ` : '<span class="text-muted small">-</span>'}
      </td>
    </tr>
  `;
  }).join("") || `<tr><td colspan="10" class="text-center text-muted py-3">Kişi bulunamadı</td></tr>`;
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
  try {
    await apiCagir(`/kisiler/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ aktif: yeniDurum }),
    });
    kisileriYukle();
    panelYenile();
  } catch (e) {
    toastGoster(e.message, "hata");
  }
}

async function kisiSil(id) {
  if (!(await onayAl("Bu kişiyi silmek istediğinize emin misiniz?"))) return;
  try {
    await apiCagir(`/kisiler/${id}`, { method: "DELETE" });
    kisileriYukle();
    panelYenile();
  } catch (e) {
    toastGoster(e.message, "hata");
  }
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
  document.getElementById("duzenleYeniEkPlaka").value = "";
  document.getElementById("duzenleEkPlakaSonuc").textContent = "";
  _duzenleEkPlakalarGoster(kisi.id, kisi.ek_plakalar);
  duzenleZiyaretciAlanGoster();
  bootstrap.Modal.getOrCreateInstance(document.getElementById("kisiDuzenleModal")).show();
}

// 2026-09-23 kullanıcı isteği: "birden fazla aracı olanların araçlarını
// kişiye tıklayınca sıralı bir şekilde görecek şekilde düzenle" -- bkz.
// index.html'deki #duzenleEkPlakalarListe'nin üstündeki not. `ek_plakalar`
// GET /kisiler/{id} yanıtında ZATEN geliyordu (schemas.KisiCevap.ek_plakalar)
// -- burada ekstra bir istek YAPILMIYOR, sadece gösteriliyor. Liste <ol>
// (sıralı/numaralı liste) olduğu için tarayıcı otomatik 1., 2., 3. ...
// numaralandırır -- kullanıcının istediği "sıralı görünüm" budur.
function _duzenleEkPlakalarGoster(kisiId, ekPlakalar) {
  const liste = document.getElementById("duzenleEkPlakalarListe");
  liste.innerHTML = (ekPlakalar && ekPlakalar.length)
    ? ekPlakalar.map(p => `
      <li>
        <span class="ek-plaka-satiri-ic">
          <span class="ek-plaka-metin">${escapeHtml(p.plaka_no)}</span>
          <button type="button" class="btn btn-sm btn-outline-danger" onclick="kisiEkPlakaSil(${kisiId}, ${p.id})" title="Bu ek plakayı kaldır"><i class="bi bi-x-lg"></i></button>
        </span>
      </li>`).join("")
    : `<li class="text-muted small" style="list-style: none;">Bu kişiye ait ek plaka yok</li>`;
}

async function kisiEkPlakaEkle() {
  const kisiId = document.getElementById("duzenleId").value;
  const girdi = document.getElementById("duzenleYeniEkPlaka");
  const sonuc = document.getElementById("duzenleEkPlakaSonuc");
  const plaka = girdi.value.trim();
  if (!plaka) return;
  try {
    await apiCagir(`/kisiler/${kisiId}/plakalar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plaka_no: plaka }),
    });
    girdi.value = "";
    sonuc.className = "small text-success mt-1"; sonuc.textContent = "Ek plaka eklendi.";
    const guncelKisi = await apiCagir(`/kisiler/${kisiId}`);
    _duzenleEkPlakalarGoster(kisiId, guncelKisi.ek_plakalar);
    kisileriYukle();
  } catch (err) {
    sonuc.className = "small text-danger mt-1"; sonuc.textContent = err.message;
  }
}

async function kisiEkPlakaSil(kisiId, plakaId) {
  if (!(await onayAl("Bu ek plakayı kaldırmak istediğinize emin misiniz?"))) return;
  try {
    await apiCagir(`/kisiler/${kisiId}/plakalar/${plakaId}`, { method: "DELETE" });
    const guncelKisi = await apiCagir(`/kisiler/${kisiId}`);
    _duzenleEkPlakalarGoster(kisiId, guncelKisi.ek_plakalar);
    kisileriYukle();
  } catch (err) {
    toastGoster(err.message, "hata");
  }
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
    sonGecislerYukle(false);
  } catch (err) {
    alert("Hata: " + err.message);
  }
});

// ---------------------- BAŞLANGIÇ ----------------------

// 2026-09-25: bkz. dosyanın SSE bölümündeki _sseSonVeriZamani/_sseController
// notu -- "yenile desem de düzelmiyor, sayfayı f5 yapınca düzeldi" kök
// nedeninin düzeltmesi. Eskiden bu yedek polling YALNIZCA `!_sseAktif`
// şartına bakıyordu; ama `_sseAktif`, bağlantı FİİLEN ölse bile (zombi
// `reader.read()`) sonsuza dek `true` kalabiliyordu -- bu durumda ne gerçek
// zamanlı olaylar geliyordu ne de bu "yedek" polling hiç devreye giriyordu,
// sayfa kullanıcı elle F5 yapana kadar tamamen donuyordu. Artık her turda
// SSE'nin gerçekten canlı mı yoksa "görünüşte bağlı ama durgun" mu olduğu da
// ayrıca kontrol ediliyor; durgunsa bağlantı zorla kapatılıyor (bu, mevcut
// `.finally()` bloğunu tetikleyip normal yeniden bağlanma mantığını devreye
// sokar) VE bu turda yenileme de -- yeniden bağlanmayı beklemeden -- hemen
// çalıştırılıyor. Test edilebilirlik için (gerçek 15 sn'yi beklemeden)
// isimli, dışa açık bir fonksiyona çıkarıldı -- bkz.
// tests/test_frontend_rbac.py veya benzeri statik testler.
function _canliYenilemeVeZombiSseKontrolu() {
  if (!sessionStorage.getItem("pts_token")) return;
  const sseDurgun = _sseAktif && _sseSonVeriZamani && (Date.now() - _sseSonVeriZamani > SSE_DURGUNLUK_ESIGI_MS);
  if (sseDurgun) {
    console.warn("SSE bağlantısı durgun görünüyor (uzun süredir veri yok), zorla yeniden bağlanılıyor.");
    try { _sseController?.abort(); } catch { }
  }
  if (!_sseAktif || sseDurgun) {
    panelYenile();
    sonGecislerYukle(false);
    if (!_kayitlarFiltresiDuzenleniyorMu()) kayitlariYukle(false);
  }
}

authBaslat().then(() => {
  ziyaretciAlanGoster();
  // SSE bağlıysa VE gerçekten canlıysa (gerçek zamanlı olaylar zaten
  // Panel+Kayıtlar'ı tazeliyor, bkz. _sseKayitAl -> _canliBolumleriTazeleDebounce)
  // bu yedek polling'e gerek yok; SSE bağlı DEĞİLSE (bağlantı koptu/henüz
  // kurulmadıysa) YA DA yukarıdaki fonksiyonun tespit ettiği gibi durgunsa,
  // 15 sn'de bir Panel/Kayıtlar/Son Geçişler otomatik olarak yeniden yüklenir
  // -- kullanıcının müdahalesi olmadan sayfa arka planda kendini güncel tutar.
  setInterval(_canliYenilemeVeZombiSseKontrolu, 15000);
});

// ================================================================
// TOAST BİLDİRİMLER
// ================================================================

// `tikla` (opsiyonel): verilirse toast'un gövdesi TIKLANABİLİR olur -- örn.
// bir geçiş bildirimine tıklanınca doğrudan o kaydın not/onay ekranını
// açmak için (bkz. _sseKayitAl, kullanıcı isteği: "bildirim geldiğinde son
// geçişler de olduğu gibi direkt olarak onun üstüne tıklayıp not ve onay
// ekranının açılmasını istiyorum", 2026-09-20). Kapatma (X) butonu, olay
// kabarcıklanmasını (bubbling) durdurarak tıklama işleyicisini TETİKLEMEZ.
function toastGoster(mesaj, tip = "bilgi", tikla = null) {
  const renkler = { bilgi: "bg-primary", basari: "bg-success", uyari: "bg-warning text-dark", hata: "bg-danger", kara: "bg-dark" };
  const id = "toast_" + Date.now();
  const govdeSinifi = "toast-body fw-semibold" + (tikla ? " toast-tiklanabilir" : "");
  const html = `<div id="${id}" class="toast align-items-center text-white ${renkler[tip] || "bg-primary"} border-0" role="alert" aria-live="assertive" data-bs-delay="5000">
    <div class="d-flex"><div class="${govdeSinifi}"${tikla ? ' style="cursor:pointer" title="Detayları görmek için tıklayın"' : ""}>${escapeHtml(mesaj)}</div>
    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div></div>`;
  const kont = document.getElementById("toastKonteyneri");
  kont.insertAdjacentHTML("beforeend", html);
  const el = document.getElementById(id);
  const toastOrnegi = bootstrap.Toast.getOrCreateInstance(el);
  if (tikla) {
    el.querySelector(".toast-body").addEventListener("click", () => {
      tikla();
      toastOrnegi.hide();
    });
  }
  toastOrnegi.show();
  el.addEventListener("hidden.bs.toast", () => el.remove());
}

// ================================================================
// SSE — GERÇEK ZAMANLI PLAKA BİLDİRİMLERİ
// ================================================================

let _sseAktif = false;
let _sseYenidenBaglaSayaci = 0;
// 2026-09-25 kullanıcı geri bildirimi: "sistem hiç kapanmadan aktif bir
// şekilde çalışmaya devam etti fakat son geçişler ekranı akşam saatlerinde
// kalmış güncellenmemiş... yenile desem de düzelmiyor... sayfayı f5 yapınca
// düzeldi." KÖK NEDEN: tarayıcı sekmesi uzun süre açık kalırsa (özellikle
// bilgisayar uykuya girip çıktıktan veya kısa bir ağ kesintisinden sonra),
// aşağıdaki `_sseBaslatFetch`'in `reader.read()` çağrısı bazı tarayıcı/işletim
// sistemi senaryolarında ASLA sonuçlanmadan (ne hata verir ne tamamlanır)
// sonsuza dek askıda kalabiliyor -- alttaki TCP bağlantısı fiilen ölü ama
// tarayıcı bunu fark etmiyor. Bu durumda `_sseAktif` sonsuza dek `true`
// kalıyor: ne `.finally()` bloğu (yeniden bağlanma) çalışıyor, ne de
// aşağıdaki 15 sn'lik yedek polling (`!_sseAktif` şartına bağlı olduğu için)
// devreye giriyor -- sonuç: Panel/Kayıtlar/Son Geçişler'in TÜMÜ, kullanıcı
// sayfayı elle F5 ile yenileyene kadar donmuş kalıyor (uygulama içi "Yenile"
// düğmeleri de dahil -- onlar da AYNI zombi ağ yığınına düşen `fetch()`
// çağrıları kullanıyor). `_sseSonVeriZamani`, akıştan HERHANGİ bir veri
// (gerçek bir olay VEYA sunucunun 25 sn'de bir gönderdiği kalp atışı yorum
// satırı, bkz. main.py::sse_baglantisi) alındığında güncellenir;
// `_sseController`, o an aktif fetch'in AbortController'ıdır -- bu ikisi
// birlikte, aşağıdaki periyodik kontrolün "bağlantı GÖRÜNÜŞTE açık ama
// fiilen ölü" durumunu tespit edip ZORLA kapatabilmesini sağlar (bkz.
// _canliYenilemeVeZombiSseKontrolu).
let _sseSonVeriZamani = 0;
let _sseController = null;
const SSE_DURGUNLUK_ESIGI_MS = 70000; // sunucu en geç 25 sn'de bir veri gönderir; 70 sn'lik pay birkaç kaçırılan kalp atışına tolerans tanır

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
  _sseSonVeriZamani = Date.now();
  _sseYenidenBaglaSayaci++;
  const baglanmaZamani = Date.now();

  const ctrl = new AbortController();
  _sseController = ctrl;
  fetch("/olaylar/sse", { headers: { Authorization: `Bearer ${token}` }, signal: ctrl.signal })
    .then(async (r) => {
      if (!r.ok || !r.body) throw new Error("SSE bağlantısı kurulamadı");
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let tampon = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        // Gelen HER parça (gerçek bir olay ya da yalnızca kalp atışı yorum
        // satırı olsun) bağlantının hâlâ canlı olduğunun kanıtıdır -- bkz.
        // yukarıdaki _sseSonVeriZamani'nin docstring'i.
        _sseSonVeriZamani = Date.now();
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
      _sseController = null;
      // calistir.bat/calistir.sh'deki AYNI "en az 60 sn sorunsuz çalıştıysa
      // deneme sayacını sıfırla" mantığı: bağlantı yeterince uzun süre
      // sağlıklı kaldıysa bu KALICI bir sorun değildi (geçici bir ağ
      // kesintisiydi) -- sayaç sıfırlanır. Aksi halde, sistemin ömrü
      // boyunca yaşanmış TEK bir geçici kesinti bile üstel geri çekilmeyi
      // kalıcı olarak 5 dakikalık tavana kilitler; sonraki (bambaşka,
      // ilgisiz) bir kesintide bile yeniden bağlanmak gereksiz yere 5
      // dakikaya kadar sürer.
      if (Date.now() - baglanmaZamani >= 60000) {
        _sseYenidenBaglaSayaci = 0;
      }
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
  // 2026-09-20 kullanıcı isteği (birebir): "bildirim geldiğinde son geçişler
  // de olduğu gibi direkt olarak onun üstüne tıklayıp not ve onay ekranının
  // açılmasını istiyorum" -- "Son Geçişler" panelindeki satırların davranışı
  // (olayDetayAc(id)) burada da aynen uygulanıyor.
  toastGoster(`${kayit.plaka_no} · ${yon} · ${kayit.kamera_id}`, tip, () => olayDetayAc(kayit.id));

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
    try { await sonGecislerYukle(false); } catch (e) { console.error("Son Geçişler otomatik yenileme hatası:", e); }
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
        <td class="small">${kayitIsimGoster(k)}</td>
        <td>${k.vardiya_adi ? `<span class="badge bg-info text-dark">${escapeHtml(k.vardiya_adi)}</span>` : '<span class="text-muted small">-</span>'}</td>
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
          <thead class="table-light"><tr><th>Görsel</th><th>Tarih/Saat</th><th>Yön</th><th>Kamera</th><th>Durum</th><th>İsim</th><th>Vardiya</th><th title="Bu okuma kaç farklı karede doğrulandı">Doğrulama</th><th>Not</th><th></th></tr></thead>
          <tbody>${satirlar || "<tr><td colspan='10' class='text-center text-muted'>Kayıt yok</td></tr>"}</tbody>
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
              <label class="form-label small mb-0">Misafir Adı Soyadı (opsiyonel)</label>
              <input type="text" id="analizManuelMisafirAdi" class="form-control form-control-sm" maxlength="100" placeholder="Örn. Ahmet Yılmaz">
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
            misafir_adi: document.getElementById("analizManuelMisafirAdi").value || null,
            not_metni: document.getElementById("analizManuelNot").value || null,
          }),
        });
        panelYenile();
        sonGecislerYukle(false);
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
  if (!(await onayAl("Bu aracı kara listeden çıkarmak istiyor musunuz?"))) return;
  try {
    await apiCagir(`/kara-listesi/${id}`, { method: "DELETE" });
    karaListesiYukle(); panelYenile();
  } catch (e) {
    toastGoster(e.message, "hata");
  }
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

let _bariyerlerCache = [];

async function bariyerleriYukle() {
  try {
    const bariyerler = await apiCagir("/bariyer/ayarlar");
    _bariyerlerCache = bariyerler;
    const el = document.getElementById("bariyerTablo");
    if (!el) return;
    el.innerHTML = bariyerler.map(b => `<tr>
      <td><strong>${escapeHtml(b.ad)}</strong></td>
      <td><span class="badge bg-secondary">${escapeHtml(b.mod)}</span></td>
      <td class="text-muted small text-truncate" style="max-width:150px">${escapeHtml(b.http_url || "-")}</td>
      <td>${b.auto_ac
        ? '<span class="badge bg-success">Açık</span>'
        : '<span class="badge bg-secondary">Kapalı</span>'}</td>
      <td>
        ${rolYeterli("operatör") ? `
        <button class="btn btn-sm btn-success" onclick="bariyerAc(${b.id})" title="Bariyeri aç"><i class="bi bi-unlock-fill"></i> Aç</button>
        <button class="btn btn-sm btn-outline-secondary ms-1" onclick="bariyerDuzenleAc(${b.id})" title="Ayarları düzenle"><i class="bi bi-pencil-square"></i></button>
        <button class="btn btn-sm btn-outline-danger ms-1" onclick="bariyerSil(${b.id})"><i class="bi bi-trash"></i></button>
        ` : '<span class="text-muted small">-</span>'}
      </td>
    </tr>`).join("") || `<tr><td colspan="5" class="text-center text-muted py-3">Bariyer tanımlanmadı</td></tr>`;
  } catch (e) { console.error(e); }
}

document.getElementById("bariyerForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const sonuc = document.getElementById("bariyerSonuc");
  const btn = e.target.querySelector('button[type="submit"]');
  if (btn) btn.disabled = true;  // çift gönderimi önle (bkz. kameraAdDuzenle'deki aynı desen)
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
  } catch (err) {
    sonuc.className = "small mt-2 text-danger"; sonuc.textContent = err.message;
  } finally {
    if (btn) btn.disabled = false;
  }
});

// DÜZELTME (2026-09-25, sistem taraması): bariyer_ekle'nin isteğin "auto_ac"
// alanını hiç okumaması (bkz. main.py'deki docstring) yüzünden, panelde
// "Yetkili araç girişinde otomatik aç" kutusunu işaretlemenin ÖNCEDEN HİÇBİR
// ETKİSİ yoktu -- yeni eklenen bariyer her zaman auto_ac=False ile
// oluşuyordu. Backend artık bu alanı okuyor VE var olan bir bariyeri
// silmeden düzenleyebilmek için PATCH /bariyer/ayarlar/{id} eklendi; bu
// düzenleme penceresi o uç noktayı kullanır.
function bariyerDuzenleModDegisti() {
  const mod = document.getElementById("bariyerDuzenleMod").value;
  document.getElementById("bariyerDuzenleHttpAlani").classList.toggle("d-none", mod !== "http");
}

let _bariyerDuzenleId = null;

function bariyerDuzenleAc(id) {
  const bariyer = (_bariyerlerCache || []).find(b => b.id === id);
  if (!bariyer) return;
  _bariyerDuzenleId = id;
  document.getElementById("bariyerDuzenleAd").value = bariyer.ad || "";
  document.getElementById("bariyerDuzenleMod").value = bariyer.mod === "http" ? "http" : "simulate";
  document.getElementById("bariyerDuzenleUrl").value = bariyer.http_url || "";
  document.getElementById("bariyerDuzenleMetot").value = bariyer.http_metot || "GET";
  document.getElementById("bariyerDuzenleGovde").value = bariyer.http_govde || "";
  document.getElementById("bariyerDuzenleAutoAc").checked = !!bariyer.auto_ac;
  bariyerDuzenleModDegisti();
  document.getElementById("bariyerDuzenleSonuc").textContent = "";
  bootstrap.Modal.getOrCreateInstance(document.getElementById("bariyerDuzenleModal")).show();
}

document.getElementById("bariyerDuzenleKaydetBtn")?.addEventListener("click", async () => {
  const sonuc = document.getElementById("bariyerDuzenleSonuc");
  const btn = document.getElementById("bariyerDuzenleKaydetBtn");
  btn.disabled = true;
  sonuc.className = "small mt-2";
  sonuc.textContent = "Kaydediliyor...";
  try {
    const mod = document.getElementById("bariyerDuzenleMod").value;
    await apiCagir(`/bariyer/ayarlar/${_bariyerDuzenleId}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ad: document.getElementById("bariyerDuzenleAd").value,
        mod,
        http_url: mod === "http" ? (document.getElementById("bariyerDuzenleUrl").value || null) : null,
        http_metot: document.getElementById("bariyerDuzenleMetot").value,
        http_govde: document.getElementById("bariyerDuzenleGovde").value || null,
        auto_ac: document.getElementById("bariyerDuzenleAutoAc").checked,
      }),
    });
    toastGoster("Bariyer ayarları güncellendi.", "basari");
    bootstrap.Modal.getInstance(document.getElementById("bariyerDuzenleModal"))?.hide();
    bariyerleriYukle();
  } catch (err) {
    sonuc.className = "small mt-2 text-danger";
    sonuc.textContent = err.message;
  } finally {
    btn.disabled = false;
  }
});

async function bariyerAc(id) {
  try {
    const r = await apiCagir(`/bariyer/${id}/ac`, { method: "POST" });
    toastGoster(r.mesaj, "basari");
  } catch (e) { toastGoster(e.message, "hata"); }
}

async function bariyerSil(id) {
  if (!(await onayAl("Bu bariyer kaydını silmek istiyor musunuz?"))) return;
  try {
    await apiCagir(`/bariyer/ayarlar/${id}`, { method: "DELETE" });
    bariyerleriYukle();
  } catch (e) {
    toastGoster(e.message, "hata");
  }
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
  if (!(await onayAl("Bu siteyi ve bağlı tüm erişim noktalarını silmek istiyor musunuz?"))) return;
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
  if (!(await onayAl("Bu erişim noktasını silmek istiyor musunuz?"))) return;
  try {
    await apiCagir(`/noktalar/${id}`, { method: "DELETE" });
    noktalariYukle();
  } catch (err) { toastGoster(err.message, "hata"); }
}

// ================================================================
// KULLANICI YÖNETİMİ
// ================================================================

// "Nizamiye Bazlı Kamera Erişimi" (2026-09-21) -- kullanıcı listesi ve
// düzenleme modalı arasında paylaşılan, o oturumda bir kez yüklenen kamera
// listesi önbelleği (bkz. _kameraListesiniGetir).
let _kullanicilarCache = [];
let _kameraListesiCache = null;

async function _kameraListesiniGetir() {
  if (_kameraListesiCache) return _kameraListesiCache;
  try {
    _kameraListesiCache = await apiCagir("/kameralar");
  } catch (e) {
    _kameraListesiCache = [];
  }
  return _kameraListesiCache;
}

// Bir kamera checkbox listesi HTML'i üretir -- `seciliIdler` null ise
// hepsi işaretlenir (yeni kullanıcı formunda "Tüm Kameralar" işaretini
// kaldırınca varsayılan budur), aksi halde yalnızca o id'ler işaretlenir.
function _kameraCheckboxListesiHtml(kameralar, seciliIdler, girdiAdi) {
  if (!kameralar.length) return '<div class="text-muted small">Tanımlı kamera bulunamadı.</div>';
  return kameralar.map(k => {
    const isaretli = seciliIdler === null || seciliIdler.includes(k.id);
    return `<div class="form-check">
      <input class="form-check-input" type="checkbox" name="${girdiAdi}" value="${escapeHtml(k.id)}" id="${girdiAdi}-${escapeHtml(k.id)}" ${isaretli ? "checked" : ""}>
      <label class="form-check-label small" for="${girdiAdi}-${escapeHtml(k.id)}">${escapeHtml(k.ad || k.id)}</label>
    </div>`;
  }).join("");
}

function _isaretliKameraIdleriniAl(girdiAdi) {
  return Array.from(document.querySelectorAll(`input[name="${girdiAdi}"]:checked`)).map(el => el.value);
}

async function yeniKullaniciKameraListesiGoster() {
  const tumKameralar = document.getElementById("yeniKullaniciTumKameralar").checked;
  const alan = document.getElementById("yeniKullaniciKameraListesi");
  alan.classList.toggle("d-none", tumKameralar);
  if (tumKameralar) return;
  const kameralar = await _kameraListesiniGetir();
  alan.innerHTML = _kameraCheckboxListesiHtml(kameralar, [], "yeniKullaniciKamera");
}

async function kullanicilariYukle() {
  try {
    const [kullanicilar, kisiler] = await Promise.all([
      apiCagir("/kullanicilar"),
      apiCagir("/kisiler").catch(() => []),
    ]);
    _kullanicilarCache = kullanicilar;
    const el = document.getElementById("kullanicilarTablo");
    if (!el) return;
    const roller = { yonetici: "bg-danger", "operatör": "bg-warning text-dark", "güvenlik": "bg-primary", izleyici: "bg-secondary", sakin: "bg-info text-dark" };
    el.innerHTML = kullanicilar.map(k => {
      const bagliKisi = k.kisi_id ? kisiler.find(ki => ki.id === k.kisi_id) : null;
      const kameraEtiketi = k.kamera_erisim_listesi === null || k.kamera_erisim_listesi === undefined
        ? '<span class="badge bg-light text-dark border">Tümü</span>'
        : `<span class="badge bg-warning text-dark" title="Yalnızca ${k.kamera_erisim_listesi.length} kamera">${k.kamera_erisim_listesi.length} kamera</span>`;
      // "Vardiya Grupları" (2026-09-21) -- bkz. main.py::_kullanicinin_vardiya_pencereleri.
      const vardiyaEtiketi = k.vardiya_adi
        ? `<span class="badge bg-info text-dark">${escapeHtml(k.vardiya_adi)} Vardiyası</span>`
        : '<span class="text-muted small">-</span>';
      return `<tr>
      <td><strong>${escapeHtml(k.kullanici_adi)}</strong></td>
      <td><span class="badge ${roller[k.rol] || "bg-secondary"}">${escapeHtml(k.rol)}</span></td>
      <td class="small">${bagliKisi ? escapeHtml(bagliKisi.ad_soyad) : (k.kisi_id ? `#${k.kisi_id} (silinmiş)` : "-")}</td>
      <td>${kameraEtiketi}</td>
      <td>${vardiyaEtiketi}</td>
      <td class="small text-muted">${k.son_giris ? tarihFormatla(k.son_giris) : "—"}</td>
      <td>${k.aktif ? '<span class="badge bg-success">Aktif</span>' : '<span class="badge bg-secondary">Pasif</span>'}</td>
      <td>
        ${rolYeterli("yonetici") ? `
        <button class="btn btn-sm btn-outline-primary" onclick="kullaniciDuzenleAc(${k.id})" title="Düzenle"><i class="bi bi-pencil"></i></button>
        <button class="btn btn-sm btn-outline-secondary ms-1" onclick="kullaniciDurumDegistir(${k.id}, ${!k.aktif})" title="${k.aktif ? "Pasif yap" : "Aktif yap"}"><i class="bi bi-toggle2-on"></i></button>
        <button class="btn btn-sm btn-outline-danger ms-1" onclick="kullaniciSil(${k.id})" title="Sil"><i class="bi bi-trash"></i></button>
        ` : '<span class="text-muted small">-</span>'}
      </td>
    </tr>`;
    }).join("") || `<tr><td colspan="8" class="text-center text-muted py-3">Kullanıcı bulunamadı</td></tr>`;
  } catch (e) {
    const el = document.getElementById("kullanicilarTablo");
    if (el) el.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-3">Bu sekmeyi sadece yönetici görebilir</td></tr>`;
  }
}

// ================================================================
// DENETİM KAYITLARI (2026-09-20) -- bkz. backend/main.py::_denetim_kaydet,
// GET /denetim-kayitlari. Kullanıcı rolü/aktiflik değiştirme, parola
// sıfırlama, kullanıcı/kamera silme, lisans aktivasyonu ve sistem ayarları
// değişikliğinin kalıcı, filtrelenebilir izi. Yalnızca yönetici görebilir.
// ================================================================

let _denetimEylemListesiYuklendiMi = false;

async function _denetimEylemListesiniDoldur() {
  if (_denetimEylemListesiYuklendiMi) return;
  const secim = document.getElementById("denetimFiltreEylem");
  if (!secim) return;
  try {
    const r = await apiCagir("/denetim-kayitlari/eylem-listesi");
    secim.innerHTML = '<option value="">Tümü</option>' + r.eylemler.map(
      e => `<option value="${escapeHtml(e)}">${escapeHtml(e)}</option>`
    ).join("");
    _denetimEylemListesiYuklendiMi = true;
  } catch (e) { console.error(e); }
}

async function denetimKayitlariniYukle() {
  const tbody = document.getElementById("denetimKayitlariTablo");
  if (!tbody) return;
  await _denetimEylemListesiniDoldur();
  const params = new URLSearchParams();
  const kullaniciAdi = document.getElementById("denetimFiltreKullanici").value.trim();
  const eylem = document.getElementById("denetimFiltreEylem").value;
  const baslangic = document.getElementById("denetimFiltreBaslangic").value;
  const bitis = document.getElementById("denetimFiltreBitis").value;
  if (kullaniciAdi) params.set("kullanici_adi", kullaniciAdi);
  if (eylem) params.set("eylem", eylem);
  if (baslangic) params.set("baslangic", baslangic);
  if (bitis) params.set("bitis", bitis);
  try {
    const kayitlar = await apiCagir(`/denetim-kayitlari?${params.toString()}`);
    tbody.innerHTML = kayitlar.map(k => `
      <tr>
        <td class="text-nowrap small">${tarihFormatla(k.zaman)}</td>
        <td><strong>${escapeHtml(k.kullanici_adi)}</strong></td>
        <td><span class="badge bg-secondary">${escapeHtml(k.eylem)}</span></td>
        <td class="small">${escapeHtml(k.aciklama)}</td>
      </tr>`).join("") || `<tr><td colspan="4" class="text-center text-muted py-3">Kayıt bulunamadı</td></tr>`;
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted py-3">Bu sekmeyi sadece yönetici görebilir</td></tr>`;
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
  aramaliSecimEkle(secim);
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
    // "Vardiya Grupları" (2026-09-21): boş seçim ("Yok") -> null (bağımsız hesap).
    govde.vardiya_adi = document.getElementById("yeniKullaniciVardiyaAdi").value || null;
    // "Nizamiye Bazlı Kamera Erişimi" (2026-09-21): "Tüm Kameralar" işaretliyse
    // alan HİÇ gönderilmez (backend'de None = kısıtlama yok, varsayılan);
    // işaret kaldırılmışsa SEÇİLİ kameraların id listesi gönderilir (boş
    // seçim = hiçbir kameraya erişim yok).
    if (!document.getElementById("yeniKullaniciTumKameralar").checked) {
      govde.kamera_erisim_listesi = _isaretliKameraIdleriniAl("yeniKullaniciKamera");
    }
    await apiCagir("/kullanicilar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(govde) });
    sonuc.className = "small mt-2 text-success"; sonuc.textContent = "Kullanıcı oluşturuldu.";
    e.target.reset();
    document.getElementById("yeniKullaniciKisiAlani").classList.add("d-none");
    document.getElementById("yeniKullaniciKameraListesi").classList.add("d-none");
    kullanicilariYukle();
  } catch (err) { sonuc.className = "small mt-2 text-danger"; sonuc.textContent = err.message; }
});

async function kullaniciDurumDegistir(id, yeniDurum) {
  try {
    await apiCagir(`/kullanicilar/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ aktif: yeniDurum }) });
    kullanicilariYukle();
  } catch (e) { toastGoster(e.message, "hata"); }
}

// ================================================================
// KULLANICI DÜZENLEME (2026-09-21) -- rol/parola/kamera erişimi. Önceden bu
// sekmede bir kullanıcıyı OLUŞTURDUKTAN SONRA rolünü ya da (yeni eklenen)
// kamera erişim kısıtlamasını değiştirmenin hiçbir yolu yoktu.
// ================================================================

async function kullaniciDuzenleKameraListesiGoster() {
  const tumKameralar = document.getElementById("kdTumKameralar").checked;
  const alan = document.getElementById("kdKameraListesi");
  alan.classList.toggle("d-none", tumKameralar);
  if (tumKameralar) return;
  const kameralar = await _kameraListesiniGetir();
  // Liste zaten doldurulmuşsa (kullaniciDuzenleAc'te) yeniden ÜZERİNE YAZMA --
  // yalnızca ilk kez (henüz boşken) doldur, aksi halde kullanıcının az önce
  // yaptığı seçimleri sıfırlardı.
  if (!alan.dataset.dolduruldu) {
    alan.innerHTML = _kameraCheckboxListesiHtml(kameralar, [], "kdKamera");
    alan.dataset.dolduruldu = "1";
  }
}

async function kullaniciDuzenleAc(id) {
  const k = _kullanicilarCache.find(k2 => k2.id === id);
  if (!k) return;
  document.getElementById("kdId").value = k.id;
  document.getElementById("kdKullaniciAdi").value = k.kullanici_adi;
  document.getElementById("kdRol").value = k.rol;
  document.getElementById("kdParola").value = "";
  document.getElementById("kdVardiyaAdi").value = k.vardiya_adi || "";
  document.getElementById("kdSonuc").textContent = "";

  const kisitliMi = k.kamera_erisim_listesi !== null && k.kamera_erisim_listesi !== undefined;
  document.getElementById("kdTumKameralar").checked = !kisitliMi;
  const kameraListesiAlani = document.getElementById("kdKameraListesi");
  kameraListesiAlani.classList.toggle("d-none", !kisitliMi);
  delete kameraListesiAlani.dataset.dolduruldu;
  if (kisitliMi) {
    const kameralar = await _kameraListesiniGetir();
    kameraListesiAlani.innerHTML = _kameraCheckboxListesiHtml(kameralar, k.kamera_erisim_listesi, "kdKamera");
    kameraListesiAlani.dataset.dolduruldu = "1";
  }
  bootstrap.Modal.getOrCreateInstance(document.getElementById("kullaniciDuzenleModal")).show();
}

document.getElementById("kullaniciDuzenleForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("kdId").value;
  const sonuc = document.getElementById("kdSonuc");
  const govde = { rol: document.getElementById("kdRol").value };
  const parola = document.getElementById("kdParola").value;
  if (parola) govde.parola = parola;
  // "Vardiya Grupları" (2026-09-21): boş seçim ("Yok") gönderilirse backend
  // atamayı KALDIRIR (bkz. main.py::kullanici_guncelle) -- diğer alanların
  // "None = değiştirme" kuralından FARKLI olarak burada her zaman gönderilir,
  // çünkü bu seçim kutusu her zaman güncel bir değer taşır.
  govde.vardiya_adi = document.getElementById("kdVardiyaAdi").value || "";
  if (document.getElementById("kdTumKameralar").checked) {
    govde.kamera_erisimi_temizle = true;
  } else {
    govde.kamera_erisim_listesi = _isaretliKameraIdleriniAl("kdKamera");
  }
  try {
    await apiCagir(`/kullanicilar/${id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(govde),
    });
    bootstrap.Modal.getInstance(document.getElementById("kullaniciDuzenleModal"))?.hide();
    kullanicilariYukle();
  } catch (err) { sonuc.className = "small text-danger"; sonuc.textContent = err.message; }
});

async function kullaniciSil(id) {
  if (!(await onayAl("Bu kullanıcıyı silmek istediğinize emin misiniz?"))) return;
  try {
    await apiCagir(`/kullanicilar/${id}`, { method: "DELETE" });
    kullanicilariYukle();
  } catch (e) { toastGoster(e.message, "hata"); }
}

// ================================================================
// VARDİYA OTURUMLARI (2026-09-20) -- ÖZ-HİZMET sistem: Güvenlik Personeli
// hesapları KENDİ vardiyasını kendi başlatıp bitirir (giriş/çıkış tabanlı,
// bkz. backend/main.py::/vardiya-oturumlari, ::giris_yap, ::cikis_yap,
// README'deki "Öz-Hizmet Vardiya Oturumları" notu). Önceki elle/gün-bazlı
// "Vardiya Planlama" (vardiyalariYukle/vardiyaSil, POST/DELETE /vardiyalar)
// bununla DEĞİŞTİRİLDİ -- burada yalnızca İZLEME ve açık kalmış bir oturumu
// SONLANDIRMA var, elle "oluştur" YOK.
// ================================================================

async function vardiyaOturumlariniYukle() {
  const tabloEl = document.getElementById("vardiyaOturumlariTablo");
  if (!tabloEl) return;
  try {
    const [oturumlar, kullanicilar] = await Promise.all([
      apiCagir("/vardiya-oturumlari"),
      apiCagir("/kullanicilar"),
    ]);
    const kullaniciAdi = Object.fromEntries(kullanicilar.map(k => [k.id, k.kullanici_adi]));
    // "Vardiya Grupları" (2026-09-21): bu tablodan hangi oturumun hangi
    // ADLANDIRILMIŞ vardiyaya (ör. "A") ait olduğunu da görebilmek için.
    const kullaniciVardiyaAdi = Object.fromEntries(kullanicilar.map(k => [k.id, k.vardiya_adi]));
    tabloEl.innerHTML = oturumlar.map(o => `
      <tr>
        <td>${escapeHtml(kullaniciAdi[o.kullanici_id] || `#${o.kullanici_id} (silinmiş)`)}</td>
        <td>${kullaniciVardiyaAdi[o.kullanici_id] ? `<span class="badge bg-info text-dark">${escapeHtml(kullaniciVardiyaAdi[o.kullanici_id])}</span>` : '<span class="text-muted small">-</span>'}</td>
        <td>${tarihFormatla(o.giris_zamani)}</td>
        <td>${o.cikis_zamani ? tarihFormatla(o.cikis_zamani) : "-"}</td>
        <td>${o.cikis_zamani ? '<span class="badge bg-secondary">kapandı</span>' : '<span class="badge bg-success">devam ediyor</span>'}</td>
        <td>${o.cikis_zamani ? "" : `<button class="btn btn-sm btn-outline-danger" onclick="vardiyaOturumunuSonlandir(${o.id})" title="Sonlandır"><i class="bi bi-stop-circle"></i> Sonlandır</button>`}</td>
      </tr>
    `).join("") || `<tr><td colspan="6" class="text-center text-muted py-3">Henüz vardiya oturumu yok</td></tr>`;
  } catch (e) {
    tabloEl.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-3">Bu bölümü sadece yönetici görebilir</td></tr>`;
  }
}

async function vardiyaOturumunuSonlandir(id) {
  if (!(await onayAl("Bu vardiya oturumunu şimdi sonlandırmak istediğinize emin misiniz?"))) return;
  try {
    await apiCagir(`/vardiya-oturumlari/${id}/sonlandir`, { method: "POST" });
    vardiyaOturumlariniYukle();
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
    _guvenlikUyarilariniGoster(s.guvenlik_uyarilari);
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

// "Güvenlik uyarıları" banner'ı (2026-09-20): yalnızca yönetici görür --
// bu ortam değişkenlerini değiştirebilecek TEK rol odur; operatör/izleyici
// için gösterilmesi eyleme geçemeyecekleri bir bilgi kirliliği olurdu.
function _guvenlikUyarilariniGoster(uyarilar) {
  const alan = document.getElementById("guvenlikUyarilariAlani");
  const liste = document.getElementById("guvenlikUyarilariListesi");
  if (!alan || !liste) return;
  if (mevcutRol !== "yonetici" || !uyarilar) {
    alan.classList.add("d-none");
    return;
  }
  const maddeler = [];
  if (!uyarilar.lisans_secret_ayarli_mi) {
    maddeler.push("PTS_LICENSE_SECRET ayarlanmamış — lisanslar herkese açık, kaynak kodda sabit bir geliştirme anahtarıyla imzalanıyor. Kaynağa erişimi olan biri geçerli bir lisans üretebilir.");
  }
  if (!uyarilar.kamera_anahtari_ayarli_mi) {
    maddeler.push("PTS_KAMERA_ANAHTARI ayarlanmamış — /kayitlar/otomatik uç noktası tamamen kimliksiz (yalnızca hız sınırlaması var). Kameralar güvenilmeyen bir ağdaysa bu değişkeni ayarlayın.");
  }
  if (uyarilar.cors_tum_originlere_acik) {
    maddeler.push("PTS_CORS_ORIGINS='*' — tüm origin'lerden çapraz kaynak isteklerine izin veriliyor, üretimde önerilmez.");
  }
  // arvento_anahtari_ayarli_mi alanı yalnızca entegrasyon GERÇEKTEN
  // kullanılıyorsa (en az bir Arvento olayı alındıysa) gönderilir -- bkz.
  // main.py::_guvenlik_uyarilarini_topla. Bu yüzden `=== false` ile kontrol
  // edilir (undefined/olmayan alan hiçbir uyarı üretmez).
  if (uyarilar.arvento_anahtari_ayarli_mi === false) {
    maddeler.push("PTS_ARVENTO_ANAHTARI ayarlanmamış — /entegrasyonlar/arvento/webhook uç noktası tamamen kimliksiz (yalnızca hız sınırlaması var). Arvento güvenilmeyen bir ağdan/internetten istek gönderiyorsa bu değişkeni ayarlayın.");
  }
  if (maddeler.length === 0) {
    alan.classList.add("d-none");
    return;
  }
  liste.innerHTML = maddeler.map(m => `<li>${escapeHtml(m)}</li>`).join("");
  alan.classList.remove("d-none");
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

// Denetim Kayıtları sekmesi açıldığında otomatik yükle (bkz. yukarıdaki
// denetimKayitlariniYukle -- aynı sistem-sekme deseni).
document.querySelector('[data-bs-target="#denetim-sekme"]')?.addEventListener("click", denetimKayitlariniYukle);

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
  try {
    const r = await apiCagir("/alarmlar/tumu-okundu", { method: "POST" });
    toastGoster(`${r.guncellenen} alarm okundu işaretlendi`, "basari");
    panelYenile();
  } catch (e) {
    toastGoster(e.message, "hata");
  }
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
      // OTOMATİK VERİTABANI YEDEKLEME (2026-09-25, kullanıcı isteği: "günlük
      // otomatik yedek ekle") -- bkz. main.py::_otomatik_yedek_dongu.
      { key: "otomatik_yedek_saklama_gun", label: "Otomatik yedek saklama süresi (gün, 0 = süresiz sakla)", tip: "number" },
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
      <hr>
      <div class="form-check mb-2">
        <input type="checkbox" class="form-check-input" id="ayar_otomatik_yedek_aktif" ${ayarlar.otomatik_yedek_aktif ? "checked" : ""}>
        <label class="form-check-label small" for="ayar_otomatik_yedek_aktif">Veritabanını günde bir kez otomatik yedekle</label>
      </div>
      <div class="mb-2"><label class="form-label small" for="ayar_otomatik_yedek_klasoru">Otomatik yedek klasörü</label>
        <input type="text" class="form-control form-control-sm" id="ayar_otomatik_yedek_klasoru" value="${escapeHtml(String(ayarlar.otomatik_yedek_klasoru ?? ""))}"></div>
      <p class="small text-muted mb-2">Canlı veritabanı çalışırken bile tutarlı bir kopya alınır (WAL
        modunda bekleyen son işlemler dahil, bkz. README) ve seçilen saklama süresinden eski otomatik
        yedekler otomatik silinir. Uzun süreli/afet kurtarma amaçlı saklama için bu klasörü ayrı bir
        diske/harici depolamaya yönlendirmeniz önerilir.</p>
      <div id="otomatikYedekDurumu" class="small mb-2"></div>
      ${rolYeterli("yonetici") ? '' : '<p class="small text-muted mb-2"><i class="bi bi-lock-fill"></i> Bu ayarları sadece yönetici değiştirebilir.</p>'}
      <button type="submit" class="btn btn-sm btn-primary w-100 mt-1"><i class="bi bi-save"></i> Kaydet</button></form>`;
    document.getElementById("sistemAyarlariForm").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const guncel = {};
      satirlar.forEach(s => { guncel[s.key] = Number(document.getElementById(`ayar_${s.key}`).value); });
      guncel.bilinen_plaka_duzeltme_aktif = document.getElementById("ayar_bilinen_plaka_duzeltme_aktif").checked;
      guncel.otomatik_yedek_aktif = document.getElementById("ayar_otomatik_yedek_aktif").checked;
      guncel.otomatik_yedek_klasoru = document.getElementById("ayar_otomatik_yedek_klasoru").value;
      await apiCagir("/sistem/ayarlar", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(guncel) });
      toastGoster("Sistem ayarları kaydedildi", "basari");
      otomatikYedekDurumunuYukle();
    });
    rolBazliArayuzuUygula();
    if (rolYeterli("yonetici")) otomatikYedekDurumunuYukle();
  } catch (e) { console.error(e); }
}

// DÜZELTME (2026-09-25): otomatik yedekleme arka planda sessizce çalıştığı
// için, bir yöneticinin "gerçekten çalışıyor mu" sorusuna panelden cevap
// bulabilmesi gerekir -- bkz. main.py::otomatik_yedekleri_listele.
async function otomatikYedekDurumunuYukle() {
  const el = document.getElementById("otomatikYedekDurumu");
  if (!el) return;
  try {
    const veri = await apiCagir("/sistem/yedek/otomatik-liste");
    if (!veri.yedekler.length) {
      el.className = "small mb-2 text-muted";
      el.textContent = `Henüz otomatik yedek alınmadı (klasör: ${veri.klasor}). İlk yedek en geç 6 saat içinde alınır.`;
      return;
    }
    const son = veri.yedekler[0];
    const boyutMb = (son.boyut_bayt / (1024 * 1024)).toFixed(1);
    el.className = "small mb-2 text-muted";
    el.textContent = `Son otomatik yedek: ${new Date(son.tarih_saat).toLocaleString("tr-TR")} (${boyutMb} MB) — toplam ${veri.yedekler.length} yedek, klasör: ${veri.klasor}`;
  } catch (e) {
    console.error(e);
  }
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
  if (!(await onayAl(`${gun} günden eski görüntüler silinecek. Emin misiniz?`))) return;
  const r = await apiCagir(`/sistem/goruntu-temizle?gun=${gun}`, { method: "POST" });
  toastGoster(`${r.silinen_goruntu} görüntü silindi`, "basari");
  diskBilgisiYukle();
}

// "Güven eşiği" filtresi (2026-09-17) devreye alınmadan ÖNCE zaten kaydedilmiş,
// düşük güvenli OTOMATİK tespit kayıtlarını geriye dönük temizler (bkz.
// main.py::dusuk_guven_kayitlarini_temizle). Yeni tespitler zaten kayıt
// oluşturulmadan elenir -- bu düğme yalnızca eski birikmiş kayıtlar içindir.
async function dusukGuvenliKayitlariTemizle() {
  if (!(await onayAl("Sistem Ayarları'ndaki eşiğin ALTINDA kalan, elle girilmemiş tüm otomatik tespit kayıtları (ve görselleri) kalıcı olarak silinecek. Emin misiniz?"))) return;
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
  if (!(await onayAl("Bu webhook'u silmek istediğinize emin misiniz?"))) return;
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

