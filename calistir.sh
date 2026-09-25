#!/bin/bash
# ================================================================
# 2026-09-16: Bu betik onceden uvicorn'u YALNIZCA BIR KEZ calistirip
# cikiyordu -- gecici bir cokme (RTSP kutuphanesinden gelen beklenmedik
# bir istisna, kisa sureli bir kaynak sorunu vb.) sistemi tamamen
# durdururdu ve kimse fark etmeyene kadar (bir sonraki manuel kontrole
# kadar) PTS kapali kalirdi. Artik Windows'taki calistir.bat ile ayni
# mantik: (1) baslamadan once 8000 portu zaten kullanimda mi kontrol
# edilir (tipik neden: PTS'in kapatilmamis eski bir kopyasi hala
# calisiyor), (2) uvicorn beklenmedik sekilde cokerse otomatik olarak
# yeniden baslatilir; art arda KISA surede cokmeye devam ederse (kalici bir
# yapilandirma sorununa isaret eder) bekleme suresi artirilir (5 sn -> 60 sn
# -> 5 dk) ama betik ARTIK DURMAZ (2026-09-25 degisikligi, bkz. asagisi).
cd "$(dirname "$0")"

echo "Bağımlılıklar kuruluyor (ilk çalıştırmada biraz sürebilir)..."
pip install -r backend/requirements.txt
echo ""
echo "PTS başlatılıyor. Tarayıcıdan http://localhost:8000 adresine gidin."
echo "Durdurmak için bu pencerede CTRL+C tuşlarına basın."
echo ""

port_sahibi_pid() {
    # ss modern dagitimlarda varsayilan olarak kurulu; yoksa netstat'a
    # (net-tools) düş, o da yoksa sessizce vazgeç (kontrolü atla).
    if command -v ss >/dev/null 2>&1; then
        ss -ltnp 2>/dev/null | awk '$4 ~ /:8000$/ {print}' | grep -oP 'pid=\K[0-9]+' | head -n1
    elif command -v netstat >/dev/null 2>&1; then
        netstat -ltnp 2>/dev/null | awk '$4 ~ /:8000$/ {print}' | grep -oP '\K[0-9]+(?=/)' | head -n1
    fi
}

deneme=0
ilk_baslatma=1

while true; do
    port_pid="$(port_sahibi_pid)"
    if [ -n "$port_pid" ] && [ "$ilk_baslatma" -eq 0 ]; then
        # 2026-09-25: yalnizca ilk baslatmada durup kullaniciya soruyoruz;
        # bir cokmeden SONRAKI yeniden baslatmada port hala doluysa (coken
        # surecin soketi henuz birakmamasi vb.) bekleyip tekrar deniyoruz.
        echo ""
        echo "UYARI: 8000 portu hâlâ dolu (PID ${port_pid}). 30 saniye sonra tekrar denenecek..."
        sleep 30
        continue
    fi
    if [ -n "$port_pid" ]; then
        echo ""
        echo "============================================================"
        echo "HATA: 8000 portu zaten başka bir işlem tarafından kullanılıyor (PID ${port_pid})."
        echo "Bu genellikle PTS'in kapatılmamış eski bir kopyasının hâlâ"
        echo "çalışıyor olmasından kaynaklanır."
        echo ""
        echo "Çözüm:"
        echo "  1) O sürecin gerçekten eski/artık bir PTS kopyası olduğundan"
        echo "     emin olmak için: ps -p ${port_pid} -o pid,cmd"
        echo "  2) Eminseniz kapatmak için: kill ${port_pid}  (gerekirse: kill -9 ${port_pid})"
        echo "Ardından bu betiği tekrar çalıştırın."
        echo "============================================================"
        exit 1
    fi

    ilk_baslatma=0
    baslangic_zamani=$(date +%s)
    uvicorn backend.main:app --host 0.0.0.0 --port 8000
    cikis_kodu=$?
    bitis_zamani=$(date +%s)

    if [ "$cikis_kodu" -eq 0 ]; then
        break  # normal kapanış (CTRL+C vb.) -- yeniden başlatma yok
    fi

    calisma_suresi=$((bitis_zamani - baslangic_zamani))
    if [ "$calisma_suresi" -ge 60 ]; then
        # En az 60 saniye sorunsuz çalıştı -- bu geçici bir olaydı,
        # sayaç sıfırlanır ve normal otomatik yeniden başlatmaya devam edilir.
        deneme=0
    fi
    deneme=$((deneme + 1))

    # 2026-09-25 (sistem taramasi): eskiden 5 kisa cokmeden sonra "exit 1"
    # ile KALICI olarak duruluyordu -- gozetimsiz calisan bir nizamiyede
    # gecici ama birkac dakika suren bir sorun (veritabanina henuz
    # ulasilamamasi, disk anlik dolu vb.) sistemi biri fark edene kadar
    # kapali birakiyordu. Artik durmuyoruz, bekleme suresini artiriyoruz.
    bekleme_sn=5
    [ "$deneme" -ge 5 ] && bekleme_sn=60
    [ "$deneme" -ge 10 ] && bekleme_sn=300

    echo ""
    if [ "$deneme" -ge 5 ]; then
        echo "============================================================"
        echo "UYARI: PTS art arda ${deneme} kez kısa sürede beklenmedik şekilde durdu."
        echo "Bu genellikle tekrar eden aynı bir soruna (yanlış yapılandırma,"
        echo "veritabanına ulaşılamaması, eksik bağımlılık vb.) işaret eder."
        echo "Olası nedeni görmek için loglar/pts.log dosyasına bakın."
        echo "Otomatik yeniden başlatma DURDURULMUYOR -- sorun düzeldiğinde PTS"
        echo "kendiliğinden geri gelecek."
        echo "============================================================"
    fi
    echo "PTS beklenmedik şekilde durdu (deneme ${deneme}). ${bekleme_sn} saniye içinde yeniden başlatılıyor..."
    echo "Tamamen durdurmak için CTRL+C tuşlarına basın."
    sleep "$bekleme_sn"
done
