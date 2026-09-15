# ANPR / PTS Araştırma Notu

Araştırma tarihi: 2026-08-28

## Karşılaştırma

| Proje | Güçlü tarafı | Sınırlama | PTS kararı |
|---|---|---|---|
| [OpenALPR](https://github.com/openalpr/openalpr) | Olgun C++ çekirdeği, video ve çoklu dil bağlayıcıları, 11.5k yıldız | AGPL-3.0, son GitHub sürümü eski | Uyumluluk ve referans, varsayılan motor değil |
| [FastALPR](https://github.com/ankandrew/fast-alpr) | MIT, ONNX, CPU/GPU/DirectML seçenekleri, değiştirilebilir detector/OCR | Model doğruluğu ülke/kamera verisine göre ayrıca ölçülmeli | Varsayılan ANPR adaptörü |
| [Ultralytics](https://github.com/ultralytics/ultralytics) | Aktif ekosistem, gerçek zamanlı detection/tracking, 61k yıldız | AGPL-3.0 veya ticari lisans gerektirebilir | Opsiyonel detector/tracker |
| [Supervision](https://github.com/roboflow/supervision) | MIT, tracking, zone counting, çizim ve model bağımsız yardımcılar | ANPR motoru değil | Olay/izleme yardımcı katmanı |
| [ALPR Unconstrained](https://github.com/sergiomsilva/alpr-unconstrained) | Akademik detection + OCR yaklaşımı | Python 2.7/TensorFlow 1.5 döneminde, bakım eski | Veri ve benchmark referansı |

## Bizim mimari kararımız

- Kamera erişimi, ANPR motoru, yetki kararı, olay günlüğü ve donanım sürücüleri ayrı katmanlar olacak.
- Motor değişimi `backend/anpr_engine.py` adaptörü üzerinden yapılacak.
- RTSP parolaları istemciye gönderilmeyecek.
- Lisans; müşteri, kamera limiti, tarih ve cihaz kodunu imzalı olarak taşıyacak.
- Her tanıma sonucu ham görsel, OCR skoru, kamera, nokta, yön ve karar ile denetlenebilir olacak.
- Ticari dağıtım öncesi AGPL bileşenleri varsayılan bağımlılık yapmayacağız; model ağırlıkları ve veri setlerinin ayrı lisansları da kontrol edilecek.

## “Daha iyi” ölçümü

Sadece GitHub yıldızıyla değil, kendi Türkiye kamera verimizle ölçüm yapılacak:

- Plaka karakter doğruluğu ve tam plaka doğruluğu
- Kamera başına saniyedeki kare / gecikme
- Gece, yağmur, açı ve hareket bulanıklığı performansı
- Yanlış alarm oranı
- CPU/RAM/GPU kullanımı
- Kamera kopması ve yeniden bağlanma süresi

Bu metrikler olmadan “en iyi” iddiası teknik olarak doğrulanamaz; bu nedenle sistemin içine benchmark ve tekrar oynatma testleri de eklenecek.