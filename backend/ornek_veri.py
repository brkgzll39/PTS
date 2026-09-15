"""
Sistemi hemen deneyebilmeniz için örnek kişi ve kayıt verisi ekler.
Çalıştırma: python ornek_veri.py
(Sunucunun mutlaka çalışıyor olmasına gerek yok, doğrudan veritabanına yazar.)
"""
from datetime import datetime, timedelta

from database import SessionLocal, engine, Base
import models

Base.metadata.create_all(bind=engine)
db = SessionLocal()

ornek_kisiler = [
    dict(ad_soyad="Ahmet Yılmaz", plaka_no="34 ABC 123", tip="abone", telefon="0532 111 2233", daire_departman="A Blok Daire 5"),
    dict(ad_soyad="Elif Kaya", plaka_no="06 XYZ 45", tip="abone", telefon="0533 222 3344", daire_departman="B Blok Daire 12"),
    dict(ad_soyad="Mehmet Demir", plaka_no="35 K 789", tip="personel", telefon="0534 333 4455", daire_departman="Güvenlik"),
    dict(ad_soyad="Zeynep Arslan", plaka_no="06 TEST 99", tip="ziyaretci", telefon="0535 444 5566",
         daire_departman="A Blok Daire 5 Ziyaretçisi", bitis_tarihi=datetime.now() + timedelta(hours=6)),
]

eklenen = 0
for veri in ornek_kisiler:
    var_mi = db.query(models.Kisi).filter(models.Kisi.plaka_no == veri["plaka_no"]).first()
    if not var_mi:
        db.add(models.Kisi(**veri))
        eklenen += 1

db.commit()
print(f"{eklenen} örnek kişi eklendi. (Sistem panelinden 'Kişiler' sekmesinde görebilirsiniz.)")
print("Test için 'Test Kaydı Ekle' sekmesinden yukarıdaki plakalardan birini deneyebilirsiniz, örn: 34 ABC 123")
db.close()
