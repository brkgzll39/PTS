# Müşteri marka klasörleri

Her müşteri için bir klasör: `musteriler/<musteri-adi>/`

- `marka.json` — kurum adı, iletişim, VIP etiketi, LED yazısı
  (`installer/marka-ornek.json` kopyalanıp doldurulur; alanlar `backend/marka.py`'de açıklanır)
- `logo.png` (ya da `marka.json`'daki `logo_dosyasi` adıyla) — yaklaşık 720x220, şeffaf arka plan

Kurulum paketi: GitHub → Actions → "Derlenmis Windows paketi" → Run workflow →
`marka` kutusuna `musteriler/<musteri-adi>`. Ayrıntılar: `URUNLESTIRME.md` §3.

`ornek/` yalnızca deneme içindir (Örnek Sanayi A.Ş. gerçek bir kurum değildir).
