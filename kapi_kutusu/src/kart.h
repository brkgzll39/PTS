// KinCony KC868-A8 (ESP32 + LAN8720) donanım tanımları.
// Kaynak: üreticinin ESPHome şablonu (github.com/hzkincony/kc868-a8).
// DİKKAT: KC868-A8M'de SDA/SCL yer değiştirir (SDA 5, SCL 4); A8v3 farklı bir
// karttır (ESP32-S3, PCF8575) ve bu dosyayla çalışmaz.
#pragma once

#define KART_ADI "KC868-A8"

// I2C ve PCF8574 genişleticiler
#define KART_I2C_SDA 4
#define KART_I2C_SCL 5
#define KART_ROLE_ADRES 0x24   // 8 röle
#define KART_GIRIS_ADRES 0x22  // 8 optokuplörlü giriş
// Girişler aktifken PCF8574 pini 0 okunur; röle 0 yazılınca çeker.
#define KART_GIRIS_TERS 1
#define KART_ROLE_TERS 1

// Ethernet (LAN8720)
#define KART_ETH_PHY_ADDR 0
#define KART_ETH_POWER -1
#define KART_ETH_MDC 23
#define KART_ETH_MDIO 18
#define KART_ETH_CLK ETH_CLOCK_GPIO17_OUT
