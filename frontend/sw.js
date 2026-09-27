// PTS Service Worker — SADECE mobil "ana ekrana ekle" kurulabilirliği ve
// statik arayüz dosyalarının (HTML/CSS/JS/ikon) çevrimdışıyken de açılabilmesi
// için var. GÜVENLİK NEDENİYLE BİLİNÇLİ TASARIM KARARI: bu bir erişim kontrol
// sistemi olduğu için CANLI/GÜVENLİK VERİSİ (kayıtlar, canlı izleme, SSE akışı,
// auth uçları, görseller vb.) KESİNLİKLE ÖNBELLEKLENMİYOR — aksi halde çevrimdışı
// kaldığında eski bir "yetkili" durumunu güncelmiş gibi göstermek gibi tehlikeli
// bir yanlışa yol açabilirdi. Sadece "/static/..." altındaki dosyalar ve "/"
// (ana sayfa kabuğu) bu SW'nin kapsamına girer; başka HİÇBİR istek yakalanmaz,
// tarayıcı onu her zamanki gibi doğrudan sunucuya/ağa yönlendirir.

const SURUM = "pts-shell-v1";
const KABUK_DOSYALARI = [
  "/",
  "/static/style.css",
  "/static/app.js",
  "/static/manifest.json",
  "/static/img/tpao-logo.png",
  "/static/img/icon-192.png",
  "/static/img/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SURUM).then((cache) => cache.addAll(KABUK_DOSYALARI)).catch(() => {
      // Kurulum sırasında tek bir dosya bile başarısız olursa SW hiç
      // kurulmaz -- bu yüzden hata yutuluyor, kabuk önbelleği eksik kalsa
      // bile en azından SW devreye girip normal ağ isteklerini engellememeli.
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((isimler) =>
      Promise.all(isimler.filter((ad) => ad !== SURUM).map((ad) => caches.delete(ad)))
    )
  );
  self.clients.claim();
});

function statikKabukIstegiMi(url) {
  if (url.origin !== self.location.origin) return false;
  if (url.pathname === "/") return true;
  return url.pathname.startsWith("/static/");
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return; // POST/PUT/DELETE hiç dokunulmadan geçer
  const url = new URL(req.url);
  if (!statikKabukIstegiMi(url)) return; // /auth, /panel, /kayitlar, /goruntuler, SSE vb. -- HİÇ ele alınmaz

  // Ağ-önce, çevrimdışıysa önbellekten -- sunucu zaten bu dosyaları
  // "Cache-Control: no-cache" ile servis ediyor (bkz. main.py
  // _OnbellegiHicDogrulamadanKullanma) yani normalde her yüklemede güncel
  // sürüm gelir; SW önbelleği yalnızca ağ tamamen ulaşılamaz olduğunda
  // (çevrimdışı) devreye giren bir yedek.
  event.respondWith(
    fetch(req)
      .then((yanit) => {
        const kopya = yanit.clone();
        caches.open(SURUM).then((cache) => cache.put(req, kopya)).catch(() => {});
        return yanit;
      })
      .catch(() => caches.match(req).then((onbellek) => onbellek || Response.error()))
  );
});
