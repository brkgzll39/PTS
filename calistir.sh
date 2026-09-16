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
# yeniden baslatilir, AMA art arda 5 kez KISA surede cokerse (kalici bir
# yapilandirma sorununa isaret eder) sonsuz donguye girmeden durulur.
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

while true; do
    port_pid="$(port_sahibi_pid)"
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

    if [ "$deneme" -ge 5 ]; then
        echo ""
        echo "============================================================"
        echo "PTS art arda ${deneme} kez kısa sürede beklenmedik şekilde durdu."
        echo "Bu genellikle tekrar eden aynı sorunun (yanlış yapılandırma,"
        echo "eksik bağımlılık, vb.) her seferinde hemen tekrar oluştuğu"
        echo "anlamına gelir -- otomatik yeniden başlatma DURDURULDU."
        echo "Olası nedeni görmek için loglar/pts.log dosyasına bakın."
        echo "============================================================"
        exit 1
    fi

    echo ""
    echo "PTS beklenmedik şekilde durdu (deneme ${deneme}/5). 5 saniye içinde yeniden başlatılıyor..."
    echo "Tamamen durdurmak için CTRL+C tuşlarına basın."
    sleep 5
done
