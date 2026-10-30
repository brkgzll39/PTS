// Kapı Modu (2026-10-22, kullanıcı isteği: "arkadaşlar bazen bunda bile takılıp
// kalıyor" -- önerilen sade arayüz onaylandı, "hepsini uygula").
//
// Görevli için 4 sekme: Kapı (son geçen araç + son geçişler + not), İçeridekiler,
// Ara / Rapor, Nöbet Defteri. Klasik panel silinmedi: yönetici her zaman klasik
// görünümle açılır; operatör/güvenlik hesapları (ve parolasız kiosk ekranları)
// Kapı Modu'yla açılır. Her iki görünümde de bir düğmeyle diğerine geçilir
// (tercih bu tarayıcıda saklanır).
//
// app.js'teki yardımcıları kullanır: apiCagir, escapeHtml, korumaliGorselAta,
// buyukGorselAc, toastGoster, onayAl, sekmeAc, _indirmeDosyaAdi, oturumKapat,
// farkliKullaniciylaGiris, _otomatikGirisMi.

const KAPI_NOT_DUGMELERI = [
  ["Kargo", "bi-box-seam"], ["Teslimat", "bi-truck"], ["Misafir", "bi-people"], ["Teknik Servis", "bi-tools"],
  ["TPIC", "bi-buildings"], ["Servis", "bi-bus-front"], ["Görevli Onayı", "bi-person-check"], ["Bakım", "bi-wrench-adjustable"],
];

let _kapiKayitlar = [];          // Kapı sekmesindeki son geçişler (yeniden eskiye)
let _kapiSeciliId = null;        // büyük kartta gösterilen kayıt (null = en yenisi)
let _kapiSeciliZaman = 0;        // görevli bir satır seçtiyse yeni geçiş 60 sn kartı değiştirmez
let _kapiSekmeAdi = "kapi";
let _kapiYenileZamanlayici = null;
let _kapiAcikPencere = false;
let _kapiIcerideVeri = null;
let _kapiIcerideFiltre = "hepsi";
let _kapiArama = { metin: "", tarih: "bugun", bas: "", bit: "", kapi: "", kim: "", sayfa: 0 };
let _kapiAramaZamanlayici = null;
let _kapiAramaIstekNo = 0;

function kapiModuAcilsinMi() {
  if (mevcutRol === "sakin") return false;
  if (typeof _ekranIzinli === "function" && !_ekranIzinli("kapi")) return false;
  try {
    const tercih = localStorage.getItem("pts_gorunum");
    if (tercih === "kapi") return true;
    if (tercih === "klasik") return false;
  } catch { /* gizli pencere: varsayılan */ }
  return mevcutRol === "operatör" || mevcutRol === "güvenlik";
}

function gorunumDegistir(tercih) {
  try { localStorage.setItem("pts_gorunum", tercih); } catch { /* yok say */ }
  location.reload();
}

function kapiModunuBaslat(kullanici) {
  document.body.classList.add("kapi-modu");
  document.getElementById("kapiModu").classList.remove("d-none");
  document.getElementById("kapiKullanici").textContent = kullanici.kullanici_adi;
  const otomatik = typeof _otomatikGirisMi === "function" && _otomatikGirisMi();
  document.getElementById("kapiCikis").classList.toggle("d-none", otomatik);
  document.getElementById("kapiFarkliKullanici").classList.toggle("d-none", !otomatik);
  _kapiSaatGuncelle();
  setInterval(_kapiSaatGuncelle, 15000);
  _kapiVardiyaGuncelle();
  setInterval(_kapiVardiyaGuncelle, 60000);
  _kapiAramaSecenekleriniHazirla();
  kapiSekme("kapi");
  kapiSonGecisleriYukle();
  _kapiIcerideYukle();
  // SSE kopsa bile ekran güncel kalsın diye yedek yenileme.
  _kapiYenileZamanlayici = setInterval(() => {
    if (_kapiAcikPencere) return;
    if (_kapiSekmeAdi === "kapi") kapiSonGecisleriYukle();
    _kapiIcerideYukle();
  }, 30000);
}

function kapiSekme(ad) {
  _kapiSekmeAdi = ad;
  document.querySelectorAll("#kapiModu .kapi-sekme[data-kapi-sekme]").forEach(b =>
    b.classList.toggle("aktif", b.dataset.kapiSekme === ad));
  for (const s of ["kapi", "iceride", "ara"]) {
    document.getElementById(`kapiSekme_${s}`).classList.toggle("d-none", s !== ad);
  }
  const nobet = ad === "nobet";
  document.body.classList.toggle("kapi-nobet", nobet);
  document.getElementById("kapiIcerik").classList.toggle("d-none", nobet);
  if (nobet) sekmeAc("#nobet-sekme");
  if (ad === "iceride") _kapiIcerideYukle();
  if (ad === "ara") kapiAramaYap();
  if (ad === "kapi") kapiSonGecisleriYukle();
  window.scrollTo(0, 0);
}

// ---------------------------------------------------------------- yardımcılar
function _kapiPlakaHtml(plaka) {
  return `<span class="kapi-plaka"><span class="tr">TR</span><span class="no">${escapeHtml(plaka || "-")}</span></span>`;
}

// Kaydın "kimin aracı" sınıfı ve etiketi (renk = tür).
function _kapiTur(yetki, tip, departman) {
  if (yetki === "kara_liste") return { sinif: "kara", etiket: "Kara Liste", ikon: "bi-slash-circle" };
  if (yetki === "suresi_dolmus") return { sinif: "sure", etiket: "Süresi Dolmuş", ikon: "bi-hourglass-bottom" };
  if (yetki === "yetkili") {
    if (tip === "vip") return { sinif: "vip", etiket: "Bölge Müdürü", ikon: "bi-star" };
    if (tip === "alt_isveren") return { sinif: "alt", etiket: departman ? `Alt İşveren · ${departman}` : "Alt İşveren", ikon: "bi-buildings" };
    if (tip === "ziyaretci") return { sinif: "ziyaretci", etiket: "Ziyaretçi", ikon: "bi-person" };
    return { sinif: "personel", etiket: "Personel", ikon: "bi-person-badge" };
  }
  if (yetki === "ziyaretci_onayli") return { sinif: "ziyaretci", etiket: "Ziyaretçi (onaylı)", ikon: "bi-person-check" };
  return { sinif: "ziyaretci", etiket: "Ziyaretçi", ikon: "bi-person" };
}

// Alt işverende görev kişinin adıyla aynıysa ("TPIC" kişisi, görevi "TPIC")
// rozette tekrar yazılmaz.
function _kapiKayitTuru(k) {
  const dep = k.kisi_departman && _kapiAyni(k.kisi_departman, k.kisi_adi) ? null : k.kisi_departman;
  return _kapiTur(k.yetki_durumu, k.kisi_tip_anlik, dep);
}

function _kapiAyni(a, b) {
  return (a || "").trim().toLocaleLowerCase("tr") === (b || "").trim().toLocaleLowerCase("tr");
}

// Not, kişi adı ya da görevle aynıysa (otomatik not "TPIC" vb.) ayrıca gösterilmez.
function _kapiEkNot(not, ...digerleri) {
  const n = (not || "").trim();
  return n && !digerleri.some(d => _kapiAyni(n, d)) ? n : "";
}

function _kapiSaat(iso) {
  const d = new Date(iso);
  return d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
}

function _kapiTarihSaat(iso) {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")} · ${_kapiSaat(iso)}`;
}

function _kapiBugunMu(iso) { return new Date(iso).toDateString() === new Date().toDateString(); }

// Bugünkü geçişte yalnız saat; daha eskisinde tarih de yazılır -- 2026-10-22:
// güvenlik hesabı yalnız kendi vardiya oturumlarındaki kayıtları görür; yeni
// girişte liste 8 gün önceki aynı vardiyanın kayıtlarını saatle (23:22)
// gösterince görevli onları bu gecenin geçişleri sandı.
function _kapiZaman(iso) { return _kapiBugunMu(iso) ? _kapiSaat(iso) : _kapiTarihSaat(iso); }

function _kapiNeKadarOnce(iso) {
  const dk = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (dk < 1) return "az önce";
  if (dk < 60) return `${dk} dk önce`;
  const sa = Math.floor(dk / 60);
  return sa < 24 ? `${sa} sa ${dk % 60} dk önce` : `${Math.floor(sa / 24)} gün önce`;
}

function _kapiSure(dk) {
  if (dk < 60) return `${dk} dk`;
  return `${Math.floor(dk / 60)} sa ${dk % 60} dk`;
}

function _kapiYonHtml(yon) {
  return yon === "giris" ? '<span class="kapi-giris">Giriş</span>' : '<span class="kapi-cikis">Çıkış</span>';
}

function _kapiSaatGuncelle() {
  const d = new Date();
  document.getElementById("kapiSaat").textContent =
    `${d.toLocaleDateString("tr-TR")} · ${d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })}`;
}

async function _kapiVardiyaGuncelle() {
  const el = document.getElementById("kapiVardiya");
  try {
    const v = await apiCagir("/vardiya-cizelgesi/simdi");
    if (!v.simdi || !v.kameralar.length) { el.classList.add("d-none"); return; }
    el.textContent = `${v.simdi.vardiya_adi} vardiyası · ${v.simdi.dilim}`;
    el.classList.remove("d-none");
  } catch {
    el.classList.add("d-none");
  }
}

// ---------------------------------------------------------------- Kapı sekmesi
async function kapiSonGecisleriYukle() {
  if (typeof klonUyarilariYukle === "function") klonUyarilariYukle();
  try {
    _kapiKayitlar = await apiCagir("/kayitlar?limit=30");
  } catch (e) {
    console.error("Kapı: son geçişler yüklenemedi", e);
    return;
  }
  _kapiCiz();
}

// app.js::_sseKayitAl'dan çağrılır (yeni geçiş).
function kapiYeniKayit() {
  if (_kapiSekmeAdi === "kapi" && !_kapiAcikPencere) kapiSonGecisleriYukle();
  _kapiIcerideYukle();
}

function _kapiGosterilenKayit() {
  if (_kapiSeciliId !== null && Date.now() - _kapiSeciliZaman < 60000) {
    const k = _kapiKayitlar.find(x => x.id === _kapiSeciliId);
    if (k) return k;
  }
  _kapiSeciliId = null;
  return _kapiKayitlar[0] || null;
}

function _kapiCiz() {
  const k = _kapiGosterilenKayit();
  const kart = document.getElementById("kapiSonKart");
  if (!k) {
    kart.innerHTML = '<div class="kapi-bos"><i class="bi bi-hourglass-split"></i><br>Henüz geçiş yok.</div>';
  } else {
    const tur = _kapiKayitTuru(k);
    const kim = k.kisi_adi || k.misafir_adi || (tur.sinif === "ziyaretci" ? "Tanımsız araç" : "");
    const not = (k.not_metni || "").trim();
    kart.innerHTML = `
      <div class="ust-satir"><span class="kapi-baslik">${_kapiSeciliId === null ? "Son geçen araç" : "Seçilen geçiş"}</span><span class="kapi-canli">Canlı</span></div>
      ${_kapiSeciliId === null && !_kapiBugunMu(k.tarih_saat) ? `<div class="kapi-eski-uyari"><i class="bi bi-info-circle"></i> Bugün henüz size görünen geçiş yok; aşağıdaki kayıt ${_kapiTarihSaat(k.tarih_saat)} tarihli.</div>` : ""}
      <div class="kapi-goruntu" id="kapiGoruntu"><span class="kamera"><i class="bi bi-camera-video"></i> ${escapeHtml(k.kamera_id)} · ${k.yon === "giris" ? "Giriş" : "Çıkış"}</span><i class="bi bi-car-front-fill"></i></div>
      <div class="kapi-bilgi">
        ${_kapiPlakaHtml(k.plaka_no)}
        <div class="kapi-kim">${kim ? `<span class="ad">${escapeHtml(kim)}</span>` : ""}<span class="kapi-rozet kr-${tur.sinif}"><i class="bi ${tur.ikon}"></i> ${escapeHtml(tur.etiket)}</span></div>
      </div>
      <div class="kapi-ayrinti"><span>${_kapiYonHtml(k.yon)}</span><span><i class="bi bi-clock"></i> <b>${_kapiZaman(k.tarih_saat)}</b> (${_kapiNeKadarOnce(k.tarih_saat)})</span><span><i class="bi bi-geo-alt"></i> <b>${escapeHtml(k.kamera_id)}</b></span></div>
      <div class="kapi-not ${not ? "dolu" : ""}"><i class="bi bi-chat-left-text"></i> ${not ? escapeHtml(not) : "Not yok — eklemek için aşağıdaki düğmeye basın."}</div>
      <div class="kapi-dugmeler">
        <button class="kapi-dugme kd-ana" onclick="kapiNotAc(${k.id})"><i class="bi bi-pencil-square"></i> ${not ? "Notu Değiştir" : "Not Ekle"}</button>
        <button class="kapi-dugme kd-acik" onclick="kapiPlakaDuzeltAc(${k.id})"><i class="bi bi-arrow-repeat"></i> Plaka Yanlış</button>
      </div>`;
    const goruntu = document.getElementById("kapiGoruntu");
    if (k.goruntu_yolu) {
      const img = document.createElement("img");
      img.alt = `${k.plaka_no} geçiş görseli`;
      goruntu.appendChild(img);
      korumaliGorselAta(img, k.goruntu_yolu, false);
      goruntu.addEventListener("click", () => { if (img.src) buyukGorselAc(img); });
    }
  }
  _kapiListeCiz();
}

function _kapiListeCiz() {
  const filtre = _kapiPlakaSade(document.getElementById("kapiListeAra").value);
  const gosterilen = _kapiGosterilenKayit();
  const satirlar = _kapiKayitlar
    .filter(k => !filtre || _kapiPlakaSade(k.plaka_no).includes(filtre))
    .map(k => {
      const tur = _kapiKayitTuru(k);
      const kim = k.kisi_adi || k.misafir_adi;
      const not = _kapiEkNot(k.not_metni, kim, k.kisi_departman);
      const alt = [kim ? `<b>${escapeHtml(kim)}</b>` : "", escapeHtml(tur.etiket),
        not ? `<i class="bi bi-chat-left-text"></i> ${escapeHtml(not)}` : ""].filter(Boolean).join(" · ");
      return `<button type="button" class="kapi-satir ${gosterilen && gosterilen.id === k.id ? "secili" : ""}" data-kapi-kayit="${k.id}">
        <span class="serit ks-${tur.sinif}"></span>
        <div style="min-width:0">${_kapiPlakaHtml(k.plaka_no)}<div class="alt">${alt}</div></div>
        <div class="sag2"><div class="saat">${_kapiZaman(k.tarih_saat)}</div>${_kapiYonHtml(k.yon)} · ${escapeHtml(k.kamera_id)}</div>
      </button>`;
    }).join("");
  document.getElementById("kapiListe").innerHTML = satirlar ||
    '<div class="kapi-bos" style="padding:40px 20px;font-size:17px">Eşleşen geçiş yok.</div>';
}

function _kapiPlakaSade(m) { return (m || "").toUpperCase().replace(/[^A-Z0-9]/g, ""); }

function _kapiKayitBul(id) {
  return _kapiKayitlar.find(x => x.id === id) || (_kapiAramaSonuc || []).find(x => x.id === id) || null;
}

// ---------------------------------------------------------------- Not penceresi
let _kapiNotKayit = null;

async function kapiNotAc(kayitId, hazirKayit = null) {
  let k = hazirKayit || _kapiKayitBul(kayitId);
  if (!k) {
    try { k = await apiCagir(`/kayitlar/${kayitId}`); } catch (e) { toastGoster(e.message, "hata"); return; }
  }
  _kapiNotKayit = k;
  const tur = _kapiKayitTuru(k);
  const ziyaretciOnayi = ["yetkisiz", "bilinmiyor", "kara_liste", "suresi_dolmus"].includes(k.yetki_durumu);
  document.getElementById("kapiNotBas").innerHTML =
    `${_kapiPlakaHtml(k.plaka_no)}<span class="kapi-rozet kr-${tur.sinif}" style="font-size:19px"><i class="bi ${tur.ikon}"></i> ${escapeHtml(tur.etiket)}</span>`;
  document.getElementById("kapiNotAlt").innerHTML =
    `${_kapiYonHtml(k.yon)} · ${escapeHtml(k.kamera_id)} · <b>${_kapiZaman(k.tarih_saat)}</b>${k.kisi_adi ? ` · ${escapeHtml(k.kisi_adi)}` : ""}`;
  document.getElementById("kapiNotUyari").classList.toggle("d-none", k.yetki_durumu !== "kara_liste");
  const alan = document.getElementById("kapiNotAlani");
  alan.value = k.not_metni || "";
  document.getElementById("kapiNotCipler").innerHTML = KAPI_NOT_DUGMELERI.map(([ad, ikon]) =>
    `<button type="button" class="kapi-cip" data-kapi-cip="${escapeHtml(ad)}"><i class="bi ${ikon}"></i> ${escapeHtml(ad)}</button>`).join("");
  _kapiCipleriEsle();
  document.getElementById("kapiNotOnayla").classList.toggle("d-none", !ziyaretciOnayi);
  document.getElementById("kapiNotKaydet").textContent = ziyaretciOnayi ? "Sadece Kaydet" : "Kaydet";
  document.getElementById("kapiNotKaydet").classList.toggle("kd-ana", !ziyaretciOnayi);
  document.getElementById("kapiNotKaydet").classList.toggle("kd-acik", ziyaretciOnayi);
  _kapiPencereAc("kapiNotPencere");
  setTimeout(() => alan.focus(), 50);
}

function _kapiNotParcalari(metin) {
  return (metin || "").split(/\s*[,;]\s*/).map(p => p.trim()).filter(Boolean);
}

function _kapiCipleriEsle() {
  const parcalar = _kapiNotParcalari(document.getElementById("kapiNotAlani").value).map(p => p.toLocaleLowerCase("tr"));
  document.querySelectorAll("#kapiNotCipler [data-kapi-cip]").forEach(b =>
    b.classList.toggle("secili", parcalar.includes(b.dataset.kapiCip.toLocaleLowerCase("tr"))));
}

function _kapiCipTikla(ad) {
  const alan = document.getElementById("kapiNotAlani");
  const parcalar = _kapiNotParcalari(alan.value);
  const i = parcalar.findIndex(p => p.toLocaleLowerCase("tr") === ad.toLocaleLowerCase("tr"));
  if (i >= 0) parcalar.splice(i, 1); else parcalar.unshift(ad);
  alan.value = parcalar.join(", ");
  _kapiCipleriEsle();
  alan.focus();
}

async function kapiNotKaydet(onayla) {
  const k = _kapiNotKayit;
  if (!k) return;
  const govde = { not_metni: document.getElementById("kapiNotAlani").value.trim() };
  if (onayla) {
    if (k.yetki_durumu === "kara_liste" && !(await onayAl("Bu araç KARA LİSTEDE. Yine de ziyaretçi olarak onaylamak istediğinize emin misiniz? Bu işlem kayda geçer."))) return;
    govde.yetki_durumu = "ziyaretci_onayli";
  }
  const dugmeler = document.querySelectorAll("#kapiNotPencere .kapi-dugme");
  dugmeler.forEach(b => { b.disabled = true; });
  try {
    await apiCagir(`/kayitlar/${k.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(govde) });
    toastGoster(onayla ? `${k.plaka_no}: not kaydedildi, ziyaretçi onaylandı` : `${k.plaka_no}: not kaydedildi`, "basari");
    kapiPencereKapat();
    _kapiSonrasiYenile();
  } catch (e) {
    toastGoster(e.message, "hata");
  } finally {
    dugmeler.forEach(b => { b.disabled = false; });
  }
}

function _kapiSonrasiYenile() {
  kapiSonGecisleriYukle();
  _kapiIcerideYukle();
  if (_kapiSekmeAdi === "ara") kapiAramaYap();
}

// ---------------------------------------------------------------- Plaka düzelt
let _kapiPlakaKayit = null;

function kapiPlakaDuzeltAc(kayitId) {
  const k = _kapiKayitBul(kayitId);
  if (!k) return;
  _kapiPlakaKayit = k;
  document.getElementById("kapiPlakaEski").innerHTML = _kapiPlakaHtml(k.plaka_no);
  const alan = document.getElementById("kapiPlakaYeni");
  alan.value = k.plaka_no;
  _kapiPencereAc("kapiPlakaPencere");
  setTimeout(() => { alan.focus(); alan.select(); }, 50);
}

async function kapiPlakaKaydet() {
  const k = _kapiPlakaKayit;
  const yeni = document.getElementById("kapiPlakaYeni").value.trim().toUpperCase();
  if (!k || !yeni) return;
  if (_kapiPlakaSade(yeni) === _kapiPlakaSade(k.plaka_no)) { kapiPencereKapat(); return; }
  const btn = document.getElementById("kapiPlakaKaydetBtn");
  btn.disabled = true;
  try {
    const r = await apiCagir(`/kayitlar/${k.id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plaka_no: yeni, yeniden_degerlendir: true }),
    });
    const tur = _kapiTur(r.yetki_durumu, r.kisi_tip_anlik, null);
    toastGoster(`Plaka düzeltildi: ${k.plaka_no} → ${r.plaka_no} (${tur.etiket})`, "basari");
    kapiPencereKapat();
    _kapiSonrasiYenile();
  } catch (e) {
    toastGoster(e.message, "hata");
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------- Pencereler
function _kapiPencereAc(id) {
  _kapiAcikPencere = true;
  document.getElementById(id).classList.remove("d-none");
}

function kapiPencereKapat() {
  _kapiAcikPencere = false;
  document.querySelectorAll("#kapiModu .kapi-perde").forEach(p => p.classList.add("d-none"));
}

// ---------------------------------------------------------------- İçeridekiler
async function _kapiIcerideYukle() {
  try {
    _kapiIcerideVeri = await apiCagir("/araclar/iceridedurum");
  } catch (e) {
    console.error("Kapı: içeridekiler yüklenemedi", e);
    return;
  }
  const rozet = document.getElementById("kapiIcerideSayi");
  rozet.textContent = _kapiIcerideVeri.iceride_sayisi;
  rozet.classList.toggle("d-none", !_kapiIcerideVeri.iceride_sayisi);
  if (_kapiSekmeAdi === "iceride") _kapiIcerideCiz();
}

function kapiIcerideFiltre(ad) {
  _kapiIcerideFiltre = ad;
  _kapiIcerideCiz();
}

function _kapiIcerideCiz() {
  const v = _kapiIcerideVeri;
  if (!v) return;
  const araclar = v.araclar;
  const tanimli = araclar.filter(a => !a.ziyaretci).length;
  const kutular = [
    ["hepsi", araclar.length, "bi-car-front", "Şu an içeride", ""],
    ["tanimli", tanimli, "bi-person-badge", "Personel / Alt İşveren", ""],
    ["ziyaretci", v.ziyaretci_sayisi, "bi-person", "Ziyaretçi", ""],
    ["uyari", v.uyarili_sayisi, "bi-exclamation-triangle", v.uyari_saat ? `${v.uyari_saat} saattir çıkmadı` : "Uzun süredir içeride", "uyari"],
  ];
  document.getElementById("kapiOzet").innerHTML = kutular.map(([ad, sayi, ikon, etiket, ek]) =>
    `<button type="button" class="kapi-kart kapi-kutu ${ek} ${_kapiIcerideFiltre === ad ? "secili" : ""}" onclick="kapiIcerideFiltre('${ad}')">
      <div class="sayi">${sayi}</div><div class="ad"><i class="bi ${ikon}"></i> ${escapeHtml(etiket)}</div></button>`).join("");

  const sirali = araclar
    .filter(a => _kapiIcerideFiltre === "hepsi" || (_kapiIcerideFiltre === "tanimli" && !a.ziyaretci)
      || (_kapiIcerideFiltre === "ziyaretci" && a.ziyaretci) || (_kapiIcerideFiltre === "uyari" && a.uyari))
    .sort((a, b) => (b.uyari ? 1 : 0) - (a.uyari ? 1 : 0) || b.sure_dk - a.sure_dk);
  document.getElementById("kapiIcerideTablo").innerHTML = sirali.length ? sirali.map(a => _kapiIcerideSatir(a, false)).join("")
    : '<div class="kapi-bos" style="padding:40px">Bu grupta araç yok.</div>';

  const onaysiz = v.onaysiz || [];
  document.getElementById("kapiOnaysizBolum").classList.toggle("d-none", !onaysiz.length);
  document.getElementById("kapiOnaysizSayi").textContent = onaysiz.length;
  document.getElementById("kapiOnaysizTablo").innerHTML = onaysiz.map(a => _kapiIcerideSatir(a, true)).join("");
}

function _kapiIcerideSatir(a, onaysiz) {
  // Sunucu "kim"i "Ad – Departman" diye verir; alt işverende görev zaten rozette.
  let ad = a.kim || "";
  if (a.tip_kodu === "alt_isveren" && a.departman && ad.endsWith(` – ${a.departman}`)) ad = ad.slice(0, -(a.departman.length + 3));
  const dep = a.departman && _kapiAyni(a.departman, ad) ? null : a.departman;
  const tur = onaysiz ? { sinif: "ziyaretci", etiket: "Onay bekliyor" } : _kapiTur(a.yetki_durumu, a.tip_kodu, dep);
  const kim = [ad, _kapiEkNot(a.not_metni, ad, a.departman)].filter(Boolean).join(" — ");
  const sure = a.uyari ? `<span class="kirmizi"><i class="bi bi-exclamation-triangle-fill"></i> ${_kapiSure(a.sure_dk)}</span>` : `<b>${_kapiSure(a.sure_dk)}</b>`;
  return `<button type="button" class="kapi-tsat" data-kapi-iceride="${a.kayit_id}">
    ${_kapiPlakaHtml(a.plaka_no)}<span>${kim ? escapeHtml(kim) : '<span class="kapi-soluk">—</span>'}</span>
    <span><span class="kapi-rozet kr-${tur.sinif}">${escapeHtml(tur.etiket)}</span></span>
    <span class="kapi-soluk">${_kapiZaman(a.giris_saati)} · ${escapeHtml(a.kamera_id)}</span><span>${sure}</span></button>`;
}

function _kapiIcerideKayit(kayitId) {
  const v = _kapiIcerideVeri;
  const a = v && [...v.araclar, ...(v.onaysiz || [])].find(x => x.kayit_id === kayitId);
  if (!a) return null;
  return { id: a.kayit_id, plaka_no: a.plaka_no, yon: "giris", kamera_id: a.kamera_id, tarih_saat: a.giris_saati,
    yetki_durumu: a.yetki_durumu, kisi_tip_anlik: a.tip_kodu, kisi_departman: a.departman, kisi_adi: a.kim, not_metni: a.not_metni };
}

// ---------------------------------------------------------------- Ara / Rapor
let _kapiAramaSonuc = [];

async function _kapiAramaSecenekleriniHazirla() {
  try {
    const liste = await apiCagir("/kayitlar/nizamiyeler");
    document.getElementById("kapiAramaKapilar").innerHTML =
      `<button type="button" class="kapi-secim secili" data-kapi-kapi="">Hepsi</button>` +
      liste.map(n => `<button type="button" class="kapi-secim" data-kapi-kapi="${escapeHtml(n.deger)}">${escapeHtml(n.ad)}</button>`).join("");
  } catch (e) {
    console.error("Kapı: nizamiye listesi", e);
  }
}

function _kapiGun(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function _kapiTarihAraligi() {
  const bugun = new Date();
  const gun = (geri) => { const d = new Date(bugun); d.setDate(d.getDate() - geri); return _kapiGun(d); };
  switch (_kapiArama.tarih) {
    case "bugun": return [gun(0), gun(0)];
    case "dun": return [gun(1), gun(0)];
    case "hafta": return [gun((bugun.getDay() + 6) % 7), gun(0)];
    case "ay": return [`${bugun.getFullYear()}-${String(bugun.getMonth() + 1).padStart(2, "0")}-01`, gun(0)];
    case "sec": return [_kapiArama.bas, _kapiArama.bit];
    default: return ["", ""];
  }
}

function _kapiAramaParametreleri() {
  const p = new URLSearchParams();
  const [bas, bit] = _kapiTarihAraligi();
  if (bas) p.set("baslangic", bas);
  if (bit) p.set("bitis", bit);
  if (_kapiArama.metin) p.set("arama", _kapiArama.metin);
  if (_kapiArama.kapi) p.set("nizamiye", _kapiArama.kapi);
  if (_kapiArama.kim) p.set("kim", _kapiArama.kim);
  return p;
}

function _kapiSecimiIsaretle(kapsayiciId, ozellik, deger) {
  document.querySelectorAll(`#${kapsayiciId} [${ozellik}]`).forEach(b =>
    b.classList.toggle("secili", b.getAttribute(ozellik) === deger));
}

async function kapiAramaYap(ekle = false) {
  const istekNo = ++_kapiAramaIstekNo;
  if (!ekle) _kapiArama.sayfa = 0;
  const p = _kapiAramaParametreleri();
  p.set("limit", "100");
  p.set("offset", String(_kapiArama.sayfa * 100));
  const sayac = _kapiAramaParametreleri();
  try {
    const [liste, bilgi] = await Promise.all([apiCagir(`/kayitlar?${p}`), ekle ? null : apiCagir(`/kayitlar/sayfa-bilgisi?${sayac}`)]);
    if (istekNo !== _kapiAramaIstekNo) return;
    _kapiAramaSonuc = ekle ? _kapiAramaSonuc.concat(liste) : liste;
    if (bilgi) _kapiAramaToplam = bilgi.toplam;
  } catch (e) {
    if (istekNo === _kapiAramaIstekNo) toastGoster(e.message, "hata");
    return;
  }
  const [bas, bit] = _kapiTarihAraligi();
  const tr = (g) => g ? g.split("-").reverse().join(".") : "";
  const aralik = bas && bit ? (bas === bit ? tr(bas) : `${tr(bas)} – ${tr(bit)}`) : "tüm tarihler";
  document.getElementById("kapiAramaOzet").innerHTML =
    `<b>${_kapiAramaToplam} geçiş</b> bulundu · ${escapeHtml(aralik)}${_kapiAramaToplam > _kapiAramaSonuc.length ? ` · ilk ${_kapiAramaSonuc.length} gösteriliyor` : ""}`;
  document.getElementById("kapiAramaTablo").innerHTML = _kapiAramaSonuc.length ? _kapiAramaSonuc.map(k => {
    const tur = _kapiKayitTuru(k);
    const kim = k.kisi_adi || k.misafir_adi || "";
    const not = _kapiEkNot(k.not_metni, kim, k.kisi_departman);
    return `<button type="button" class="kapi-rtsat" data-kapi-kayit="${k.id}">
      <span><b>${_kapiTarihSaat(k.tarih_saat)}</b></span>${_kapiPlakaHtml(k.plaka_no)}
      <span style="min-width:0">${kim ? escapeHtml(kim) : '<span class="kapi-soluk">—</span>'}${not ? `<div class="not"><i class="bi bi-chat-left-text"></i> ${escapeHtml(not)}</div>` : ""}</span>
      <span><span class="kapi-rozet kr-${tur.sinif}">${escapeHtml(tur.etiket)}</span></span>
      <span>${_kapiYonHtml(k.yon)} · ${escapeHtml(k.kamera_id)}</span></button>`;
  }).join("") : '<div class="kapi-bos" style="padding:40px">Bu filtrelerle geçiş bulunamadı.</div>';
  document.getElementById("kapiAramaDaha").classList.toggle("d-none", _kapiAramaToplam <= _kapiAramaSonuc.length);
}
let _kapiAramaToplam = 0;

function kapiAramaDahaFazla() {
  _kapiArama.sayfa += 1;
  kapiAramaYap(true);
}

async function kapiIndir(tur) {
  const btn = document.getElementById(tur === "pdf" ? "kapiPdfBtn" : "kapiExcelBtn");
  btn.disabled = true;
  toastGoster(`${tur === "pdf" ? "PDF" : "Excel"} hazırlanıyor…`, "bilgi");
  const token = sessionStorage.getItem("pts_token");
  try {
    const cevap = await fetch(`${API}/disa-aktar/${tur}/kayitlar?${_kapiAramaParametreleri()}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (cevap.status === 401) { _oturumSuresiDoldu(); return; }
    if (!cevap.ok) {
      const hata = await cevap.json().catch(() => ({ detail: "Rapor oluşturulamadı" }));
      throw new Error(hata.detail || "Rapor oluşturulamadı");
    }
    const blob = await cevap.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = _indirmeDosyaAdi(cevap, tur === "pdf" ? "kayitlar.pdf" : "kayitlar.xlsx");
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  } catch (e) {
    toastGoster(e.message, "hata");
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------- olaylar
document.addEventListener("click", (e) => {
  const kapi = document.getElementById("kapiModu");
  if (!kapi || kapi.classList.contains("d-none")) return;
  const sekme = e.target.closest("[data-kapi-sekme]");
  if (sekme) { kapiSekme(sekme.dataset.kapiSekme); return; }
  const cip = e.target.closest("[data-kapi-cip]");
  if (cip) { _kapiCipTikla(cip.dataset.kapiCip); return; }
  const satir = e.target.closest("[data-kapi-kayit]");
  if (satir) {
    const id = Number(satir.dataset.kapiKayit);
    if (_kapiSekmeAdi === "kapi") {
      _kapiSeciliId = id;
      _kapiSeciliZaman = Date.now();
      _kapiCiz();
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      kapiNotAc(id);
    }
    return;
  }
  const iceride = e.target.closest("[data-kapi-iceride]");
  if (iceride) {
    const k = _kapiIcerideKayit(Number(iceride.dataset.kapiIceride));
    if (k) kapiNotAc(k.id, k);
    return;
  }
  const tarih = e.target.closest("[data-kapi-tarih]");
  if (tarih) {
    _kapiArama.tarih = tarih.dataset.kapiTarih;
    _kapiSecimiIsaretle("kapiAramaTarihler", "data-kapi-tarih", _kapiArama.tarih);
    document.getElementById("kapiTarihSecimi").classList.toggle("d-none", _kapiArama.tarih !== "sec");
    if (_kapiArama.tarih !== "sec" || (_kapiArama.bas && _kapiArama.bit)) kapiAramaYap();
    return;
  }
  const kapiSec = e.target.closest("[data-kapi-kapi]");
  if (kapiSec) {
    _kapiArama.kapi = kapiSec.dataset.kapiKapi;
    _kapiSecimiIsaretle("kapiAramaKapilar", "data-kapi-kapi", _kapiArama.kapi);
    kapiAramaYap();
    return;
  }
  const kim = e.target.closest("[data-kapi-kim]");
  if (kim) {
    _kapiArama.kim = kim.dataset.kapiKim;
    _kapiSecimiIsaretle("kapiAramaKimler", "data-kapi-kim", _kapiArama.kim);
    kapiAramaYap();
    return;
  }
  if (e.target.classList.contains("kapi-perde")) kapiPencereKapat();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && _kapiAcikPencere) kapiPencereKapat();
  if (e.key === "Enter" && !document.getElementById("kapiPlakaPencere")?.classList.contains("d-none")
      && document.activeElement?.id === "kapiPlakaYeni") { e.preventDefault(); kapiPlakaKaydet(); }
});

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("kapiNotAlani")?.addEventListener("input", _kapiCipleriEsle);
  document.getElementById("kapiListeAra")?.addEventListener("input", _kapiListeCiz);
  document.getElementById("kapiAramaMetin")?.addEventListener("input", (e) => {
    clearTimeout(_kapiAramaZamanlayici);
    _kapiAramaZamanlayici = setTimeout(() => { _kapiArama.metin = e.target.value.trim(); kapiAramaYap(); }, 400);
  });
  for (const [id, alan] of [["kapiTarihBas", "bas"], ["kapiTarihBit", "bit"]]) {
    document.getElementById(id)?.addEventListener("change", (e) => {
      _kapiArama[alan] = e.target.value;
      if (_kapiArama.bas && _kapiArama.bit) kapiAramaYap();
    });
  }
});
