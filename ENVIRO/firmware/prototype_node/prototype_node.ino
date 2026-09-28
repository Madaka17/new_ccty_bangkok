#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include "HT_SSD1306Wire.h"

// =====================================================
// PROTOTYPE NODE
// HELTEC WiFi LoRa 32 V4 + GY-91
//
// GY-91:
//   SDA = GPIO7
//   SCL = GPIO6
//
// OLED:
//   SDA = GPIO17
//   SCL = GPIO18
//   RST = GPIO21
//
// PRG:
//   GPIO0
//
// LED:
//   GPIO3 = GREEN  : ONLINE
//   GPIO4 = YELLOW : UPLINK TX (flashes when server upload succeeds)
//   GPIO5 = RED    : VIBRATION
//
// PAGE:
//   1 = MAIN
//   2 = IMU
//   3 = ORIENTATION
//   4 = SYSTEM
//
// SERVER UPLINK:
//   Connects to Wi-Fi, then POSTs its own sensor readings once per second
//   (same 1 Hz cadence as the OLED/BMP/battery block in loop()) to the
//   ENVIRO server's node-ingestion endpoint:
//
//     POST http://SERVER_HOST:SERVER_PORT/api/nodes/NODE_ID/telemetry
//     Header: X-Node-Key: NODE_API_KEY
//     Body  : flat JSON -- see server/routes/nodes.py NODE_FIELDS, plus a
//             "wave" object carrying the last ~1s of raw 20Hz x/y/z
//             accelerometer samples for real server-side PGA/STA-LTA/FFT
//
//   NODE_ID/NODE_API_KEY below must match a row in the server's real_nodes
//   table (seeded from REAL_NODES in server/db.py) -- the server rejects
//   any upload from an unknown node id or a mismatched key.
// =====================================================


// =====================================================
// GY-91 I2C
// =====================================================

#define GY91_SDA 7
#define GY91_SCL 6

TwoWire SensorWire = TwoWire(1);


// =====================================================
// OLED
// =====================================================

#define OLED_SDA   17
#define OLED_SCL   18
#define OLED_RST   21
#define OLED_ADDR  0x3C
#define VEXT_CTRL  36

SSD1306Wire oled(
  OLED_ADDR,
  500000,
  OLED_SDA,
  OLED_SCL,
  GEOMETRY_128_64,
  OLED_RST
);


// =====================================================
// WIFI / SERVER UPLINK
//
// Fill in before flashing:
//   WIFI_SSID / WIFI_PASSWORD -- the network this node should join
//   SERVER_HOST               -- the ENVIRO server's LAN IP or hostname
//                                 (the machine running python3 main.py)
//   SERVER_PORT               -- whatever port that server is listening on
//
// NODE_ID / NODE_API_KEY ship pre-filled to match this project's seeded
// demo row (REAL_NODES in server/db.py) -- change both together if you
// add a different node id there, and always replace NODE_API_KEY with a
// real secret before this node is reachable from an untrusted network.
// =====================================================

#define WIFI_SSID     "Haris"
#define WIFI_PASSWORD "11111111"

#define SERVER_HOST   "10.242.68.126"
#define SERVER_PORT   5050

#define NODE_ID       "PROTO-01"
#define NODE_API_KEY  "enviro-proto-01-demo-key"

#define WIFI_RECONNECT_INTERVAL_MS 10000
#define UPLINK_HTTP_TIMEOUT_MS     1000
#define UPLINK_LED_PULSE_MS        150

bool wifiConnected = false;
bool lastUploadOk = false;
unsigned long lastWifiAttempt = 0;


// =====================================================
// RAW WAVEFORM BUFFER (FOR SERVER-SIDE PGA / STA-LTA / FFT)
//
// The 20 Hz IMU block below already reads relAx/relAy/relAz every 50 ms --
// this just keeps the last ~1 second of THOSE same samples so each 1 Hz
// upload can carry them up to the server, which appends them into its own
// much longer rolling buffer (see server/routes/nodes.py + server/signal.py)
// and runs the SAME real STA/LTA / FFT / classifier already used for the
// simulated station network, on real accelerometer data this time.
//
// Sized a little above 20 samples/sec to tolerate normal jitter without
// dropping samples; if an upload is delayed past capacity, newer samples
// are simply not appended until the buffer is cleared by the next upload
// attempt -- a brief gap in the raw waveform, not a correctness problem,
// since the server keeps the true continuous history across uploads.
// =====================================================

#define WAVE_BUFFER_CAPACITY 30

float waveBufX[WAVE_BUFFER_CAPACITY];
float waveBufY[WAVE_BUFFER_CAPACITY];
float waveBufZ[WAVE_BUFFER_CAPACITY];
uint8_t waveBufCount = 0;


// =====================================================
// PRG BUTTON
// =====================================================

#define PRG_BUTTON 0
#define BUTTON_DEBOUNCE 250

bool lastButtonState = HIGH;
unsigned long lastButtonTime = 0;


// =====================================================
// STATUS LED
// =====================================================

#define LED_GREEN   3
#define LED_YELLOW  4
#define LED_RED     5

// GREEN  = NODE ONLINE
// YELLOW = UPLINK TX
// RED    = VIBRATION


// =====================================================
// VIBRATION FILTER
//
// IMU sample = 50 ms
//
// < 0.015g = noise floor
//
// >= 0.050g ต่อเนื่อง 3 samples
// = VIBRATION ON
//
// <= 0.025g ต่อเนื่อง 8 samples
// = VIBRATION OFF
//
// ใช้ Hysteresis ป้องกันไฟกระพริบบริเวณ Threshold
// =====================================================

#define VIB_NOISE_FLOOR       0.015f
#define VIB_TRIGGER_THRESHOLD 0.050f
#define VIB_RELEASE_THRESHOLD 0.025f

#define VIB_TRIGGER_COUNT     3
#define VIB_RELEASE_COUNT     8

// Auto re-zero IMU every 1 minute with NO CONFIRMED vibration.
// Small accel/gyro noise and drift do NOT restart this timer.
#define IMU_REZERO_STABLE_MS 60000UL

unsigned long lastVibrationMs = 0;
unsigned long lastAutoZeroMs = 0;

uint8_t vibrationTriggerCount = 0;
uint8_t vibrationReleaseCount = 0;

bool vibrationActive = false;


// =====================================================
// PAGE
// =====================================================

#define PAGE_MAIN         0
#define PAGE_IMU          1
#define PAGE_ORIENTATION  2
#define PAGE_SYSTEM       3

#define TOTAL_PAGES       4

uint8_t currentPage = PAGE_MAIN;


// =====================================================
// BATTERY
// =====================================================

#define VBAT_ADC_PIN 1
#define ADC_CTRL_PIN 37

#define VBAT_DIVIDER 4.90

#define BATTERY_MIN_V 3.20
#define BATTERY_MAX_V 4.20

float batteryVoltage = 0.0;
int batteryPercent = 0;


// =====================================================
// BMP280
// =====================================================

#define BMP_CHIP_ID    0xD0
#define BMP_CTRL_MEAS  0xF4
#define BMP_CONFIG     0xF5
#define BMP_PRESS_MSB  0xF7

uint8_t BMP_ADDR = 0x76;

bool bmpFound = false;


// =====================================================
// BMP CALIBRATION
// =====================================================

uint16_t dig_T1;
int16_t dig_T2;
int16_t dig_T3;

uint16_t dig_P1;
int16_t dig_P2;
int16_t dig_P3;
int16_t dig_P4;
int16_t dig_P5;
int16_t dig_P6;
int16_t dig_P7;
int16_t dig_P8;
int16_t dig_P9;

int32_t t_fine = 0;


// =====================================================
// BMP VALUES
// =====================================================

float temperatureC = 0.0;
float pressureHpa = 0.0;


// =====================================================
// MPU
// =====================================================

uint8_t MPU_ADDR = 0x68;

#define MPU_WHO_AM_I       0x75
#define MPU_PWR_MGMT_1     0x6B
#define MPU_CONFIG         0x1A
#define MPU_GYRO_CONFIG    0x1B
#define MPU_ACCEL_CONFIG   0x1C
#define MPU_ACCEL_CONFIG2  0x1D
#define MPU_ACCEL_XOUT_H   0x3B

bool mpuFound = false;
uint8_t mpuWhoAmI = 0;


// =====================================================
// RAW IMU
// =====================================================

int16_t rawAx = 0;
int16_t rawAy = 0;
int16_t rawAz = 0;

int16_t rawGx = 0;
int16_t rawGy = 0;
int16_t rawGz = 0;


// =====================================================
// PHYSICAL IMU
// =====================================================

float accelX = 0.0;
float accelY = 0.0;
float accelZ = 0.0;

float gyroX = 0.0;
float gyroY = 0.0;
float gyroZ = 0.0;


// =====================================================
// AUTO ZERO
// =====================================================

float zeroAx = 0.0;
float zeroAy = 0.0;
float zeroAz = 0.0;

float zeroGx = 0.0;
float zeroGy = 0.0;
float zeroGz = 0.0;

float zeroRoll = 0.0;
float zeroPitch = 0.0;

bool imuCalibrated = false;

// IMU communication health / recovery
bool imuDataValid = false;
uint8_t imuReadFailCount = 0;
unsigned long lastIMURecoveryAttempt = 0;

#define IMU_I2C_TIMEOUT_MS        20
#define IMU_RECOVERY_FAIL_COUNT    3
#define IMU_RECOVERY_INTERVAL_MS 2000UL
#define IMU_AUTOZERO_TIMEOUT_MS  2500UL
#define IMU_AUTOZERO_SAMPLES       80
#define IMU_AUTOZERO_MIN_SAMPLES   50
#define IMU_AUTOZERO_MAX_FAILS      5


// =====================================================
// RELATIVE IMU
// =====================================================

float relAx = 0.0;
float relAy = 0.0;
float relAz = 0.0;

float relGx = 0.0;
float relGy = 0.0;
float relGz = 0.0;


// =====================================================
// ORIENTATION
// =====================================================

float rollDeg = 0.0;
float pitchDeg = 0.0;

float relativeRoll = 0.0;
float relativePitch = 0.0;


// =====================================================
// VIBRATION
// =====================================================

float vibrationMagnitude = 0.0;

bool motionDetected = false;


// =====================================================
// I2C WRITE
// =====================================================

void writeRegister(
  uint8_t addr,
  uint8_t reg,
  uint8_t value
)
{
  SensorWire.beginTransmission(addr);

  SensorWire.write(reg);
  SensorWire.write(value);

  SensorWire.endTransmission();
}


// =====================================================
// I2C READ
// =====================================================

uint8_t readRegister(
  uint8_t addr,
  uint8_t reg
)
{
  SensorWire.beginTransmission(addr);

  SensorWire.write(reg);

  if (SensorWire.endTransmission(false) != 0)
  {
    return 0xFF;
  }

  SensorWire.requestFrom(
    addr,
    (uint8_t)1
  );

  if (SensorWire.available())
  {
    return SensorWire.read();
  }

  return 0xFF;
}


// =====================================================
// BMP READ 16 BIT LE
// =====================================================

uint16_t read16LE(
  uint8_t addr,
  uint8_t reg
)
{
  uint8_t lsb =
    readRegister(
      addr,
      reg
    );

  uint8_t msb =
    readRegister(
      addr,
      reg + 1
    );

  return
    ((uint16_t)msb << 8) |
    lsb;
}


int16_t readS16LE(
  uint8_t addr,
  uint8_t reg
)
{
  return
    (int16_t)read16LE(
      addr,
      reg
    );
}


// =====================================================
// DETECT BMP
// =====================================================

bool detectBMP()
{
  const uint8_t addresses[] =
  {
    0x76,
    0x77
  };

  for (uint8_t i = 0; i < 2; i++)
  {
    uint8_t addr = addresses[i];

    uint8_t id =
      readRegister(
        addr,
        BMP_CHIP_ID
      );

    if (
      id == 0x58 ||
      id == 0x56 ||
      id == 0x57 ||
      id == 0x60
    )
    {
      BMP_ADDR = addr;

      Serial.println();
      Serial.println("BAROMETER DETECTED");

      Serial.print("BMP Address : 0x");
      Serial.println(BMP_ADDR, HEX);

      Serial.print("BMP Chip ID : 0x");
      Serial.println(id, HEX);

      return true;
    }
  }

  Serial.println();
  Serial.println("BAROMETER NOT FOUND");

  return false;
}


// =====================================================
// BMP CALIBRATION
// =====================================================

void readBMPCalibration()
{
  dig_T1 = read16LE(BMP_ADDR, 0x88);
  dig_T2 = readS16LE(BMP_ADDR, 0x8A);
  dig_T3 = readS16LE(BMP_ADDR, 0x8C);

  dig_P1 = read16LE(BMP_ADDR, 0x8E);
  dig_P2 = readS16LE(BMP_ADDR, 0x90);
  dig_P3 = readS16LE(BMP_ADDR, 0x92);
  dig_P4 = readS16LE(BMP_ADDR, 0x94);
  dig_P5 = readS16LE(BMP_ADDR, 0x96);
  dig_P6 = readS16LE(BMP_ADDR, 0x98);
  dig_P7 = readS16LE(BMP_ADDR, 0x9A);
  dig_P8 = readS16LE(BMP_ADDR, 0x9C);
  dig_P9 = readS16LE(BMP_ADDR, 0x9E);
}


// =====================================================
// INIT BMP
// =====================================================

void initBMP()
{
  readBMPCalibration();

  writeRegister(
    BMP_ADDR,
    BMP_CTRL_MEAS,
    0x57
  );

  writeRegister(
    BMP_ADDR,
    BMP_CONFIG,
    0x90
  );

  delay(100);
}


// =====================================================
// BMP TEMPERATURE
// =====================================================

float compensateTemperature(
  int32_t adc_T
)
{
  int32_t var1;
  int32_t var2;

  var1 =
    ((((adc_T >> 3) -
       ((int32_t)dig_T1 << 1))) *
     ((int32_t)dig_T2)) >>
    11;

  var2 =
    (((((adc_T >> 4) -
        ((int32_t)dig_T1)) *
       ((adc_T >> 4) -
        ((int32_t)dig_T1))) >>
      12) *
     ((int32_t)dig_T3)) >>
    14;

  t_fine =
    var1 + var2;

  int32_t T =
    (t_fine * 5 + 128) >> 8;

  return
    T / 100.0;
}


// =====================================================
// BMP PRESSURE
// =====================================================

float compensatePressure(
  int32_t adc_P
)
{
  int64_t var1;
  int64_t var2;
  int64_t p;

  var1 =
    ((int64_t)t_fine) -
    128000;

  var2 =
    var1 *
    var1 *
    (int64_t)dig_P6;

  var2 =
    var2 +
    ((var1 *
      (int64_t)dig_P5) << 17);

  var2 =
    var2 +
    (((int64_t)dig_P4) << 35);

  var1 =
    ((var1 *
      var1 *
      (int64_t)dig_P3) >> 8) +
    ((var1 *
      (int64_t)dig_P2) << 12);

  var1 =
    (((((int64_t)1) << 47) +
      var1) *
     ((int64_t)dig_P1)) >>
    33;

  if (var1 == 0)
  {
    return 0;
  }

  p =
    1048576 -
    adc_P;

  p =
    (((p << 31) - var2) *
     3125) /
    var1;

  var1 =
    (((int64_t)dig_P9) *
     (p >> 13) *
     (p >> 13)) >>
    25;

  var2 =
    (((int64_t)dig_P8) *
     p) >>
    19;

  p =
    ((p + var1 + var2) >> 8) +
    (((int64_t)dig_P7) << 4);

  float pressurePa =
    (float)p /
    256.0;

  return
    pressurePa /
    100.0;
}


// =====================================================
// READ BMP
// =====================================================

bool readBMP()
{
  SensorWire.beginTransmission(
    BMP_ADDR
  );

  SensorWire.write(
    BMP_PRESS_MSB
  );

  if (
    SensorWire.endTransmission(false)
    != 0
  )
  {
    return false;
  }

  SensorWire.requestFrom(
    BMP_ADDR,
    (uint8_t)6
  );

  if (
    SensorWire.available() < 6
  )
  {
    return false;
  }

  uint8_t pmsb = SensorWire.read();
  uint8_t plsb = SensorWire.read();
  uint8_t pxlsb = SensorWire.read();

  uint8_t tmsb = SensorWire.read();
  uint8_t tlsb = SensorWire.read();
  uint8_t txlsb = SensorWire.read();

  int32_t adc_P =
    ((uint32_t)pmsb << 12) |
    ((uint32_t)plsb << 4) |
    (pxlsb >> 4);

  int32_t adc_T =
    ((uint32_t)tmsb << 12) |
    ((uint32_t)tlsb << 4) |
    (txlsb >> 4);

  temperatureC =
    compensateTemperature(
      adc_T
    );

  pressureHpa =
    compensatePressure(
      adc_P
    );

  return true;
}


// =====================================================
// DETECT MPU
// =====================================================

bool detectMPU()
{
  const uint8_t addresses[] =
  {
    0x68,
    0x69
  };

  for (uint8_t i = 0; i < 2; i++)
  {
    uint8_t addr = addresses[i];

    uint8_t who =
      readRegister(
        addr,
        MPU_WHO_AM_I
      );

    if (
      who != 0xFF &&
      who != 0x00
    )
    {
      MPU_ADDR = addr;
      mpuWhoAmI = who;

      Serial.println();
      Serial.println("IMU DETECTED");

      Serial.print("MPU Address : 0x");
      Serial.println(MPU_ADDR, HEX);

      Serial.print("WHO_AM_I    : 0x");
      Serial.println(mpuWhoAmI, HEX);

      return true;
    }
  }

  Serial.println();
  Serial.println("IMU NOT FOUND");

  return false;
}


// =====================================================
// INIT MPU
// =====================================================

void initMPU()
{
  // Wake
  writeRegister(
    MPU_ADDR,
    MPU_PWR_MGMT_1,
    0x00
  );

  delay(100);

  // Gyro DLPF
  writeRegister(
    MPU_ADDR,
    MPU_CONFIG,
    0x03
  );

  // Gyro +/-250 dps
  writeRegister(
    MPU_ADDR,
    MPU_GYRO_CONFIG,
    0x00
  );

  // Accel +/-2g
  writeRegister(
    MPU_ADDR,
    MPU_ACCEL_CONFIG,
    0x00
  );

  // Accel DLPF
  writeRegister(
    MPU_ADDR,
    MPU_ACCEL_CONFIG2,
    0x03
  );

  delay(100);
}


// =====================================================
// READ MPU RAW
// =====================================================

bool readMPURaw()
{
  SensorWire.beginTransmission(
    MPU_ADDR
  );

  SensorWire.write(
    MPU_ACCEL_XOUT_H
  );

  if (
    SensorWire.endTransmission(false)
    != 0
  )
  {
    return false;
  }

  SensorWire.requestFrom(
    MPU_ADDR,
    (uint8_t)14
  );

  if (
    SensorWire.available() < 14
  )
  {
    return false;
  }

  rawAx =
    (int16_t)(
      ((uint16_t)SensorWire.read() << 8) |
      SensorWire.read()
    );

  rawAy =
    (int16_t)(
      ((uint16_t)SensorWire.read() << 8) |
      SensorWire.read()
    );

  rawAz =
    (int16_t)(
      ((uint16_t)SensorWire.read() << 8) |
      SensorWire.read()
    );

  // MPU internal temperature - skip
  SensorWire.read();
  SensorWire.read();

  rawGx =
    (int16_t)(
      ((uint16_t)SensorWire.read() << 8) |
      SensorWire.read()
    );

  rawGy =
    (int16_t)(
      ((uint16_t)SensorWire.read() << 8) |
      SensorWire.read()
    );

  rawGz =
    (int16_t)(
      ((uint16_t)SensorWire.read() << 8) |
      SensorWire.read()
    );

  return true;
}


// =====================================================
// CALCULATE IMU
// =====================================================

void calculateIMU()
{
  accelX =
    rawAx /
    16384.0f;

  accelY =
    rawAy /
    16384.0f;

  accelZ =
    rawAz /
    16384.0f;


  gyroX =
    rawGx /
    131.0f;

  gyroY =
    rawGy /
    131.0f;

  gyroZ =
    rawGz /
    131.0f;


  // Relative acceleration
  relAx =
    accelX -
    zeroAx;

  relAy =
    accelY -
    zeroAy;

  relAz =
    accelZ -
    zeroAz;


  // Gyro bias correction
  relGx =
    gyroX -
    zeroGx;

  relGy =
    gyroY -
    zeroGy;

  relGz =
    gyroZ -
    zeroGz;


  // Orientation
  rollDeg =
    atan2(
      accelY,
      accelZ
    ) *
    180.0f /
    PI;


  pitchDeg =
    atan2(
      -accelX,
      sqrt(
        accelY * accelY +
        accelZ * accelZ
      )
    ) *
    180.0f /
    PI;


  relativeRoll =
    rollDeg -
    zeroRoll;

  relativePitch =
    pitchDeg -
    zeroPitch;
}


// =====================================================
// READ MPU
// =====================================================

bool readMPU()
{
  if (!readMPURaw())
  {
    imuDataValid = false;

    if (imuReadFailCount < 255)
    {
      imuReadFailCount++;
    }

    return false;
  }

  calculateIMU();

  imuDataValid = true;
  imuReadFailCount = 0;

  return true;
}


// =====================================================
// RECOVER IMU / SENSOR I2C BUS
// =====================================================

bool recoverIMU()
{
  unsigned long now = millis();

  if (
    lastIMURecoveryAttempt != 0 &&
    now - lastIMURecoveryAttempt <
    IMU_RECOVERY_INTERVAL_MS
  )
  {
    return false;
  }

  lastIMURecoveryAttempt = now;

  Serial.println();
  Serial.println(
    ">>> IMU/I2C RECOVERY"
  );

  imuDataValid = false;

  SensorWire.end();
  delay(5);

  SensorWire.begin(
    GY91_SDA,
    GY91_SCL,
    100000
  );

  SensorWire.setTimeOut(
    IMU_I2C_TIMEOUT_MS
  );

  delay(10);

  uint8_t who =
    readRegister(
      MPU_ADDR,
      MPU_WHO_AM_I
    );

  if (
    who == 0xFF ||
    who == 0x00
  )
  {
    Serial.println(
      "IMU RECOVERY FAILED"
    );

    return false;
  }

  mpuWhoAmI = who;

  initMPU();
  delay(20);

  if (!readMPURaw())
  {
    Serial.println(
      "IMU RECOVERY READ FAILED"
    );

    return false;
  }

  imuReadFailCount = 0;
  imuDataValid = true;

  Serial.println(
    "IMU RECOVERY OK"
  );

  return true;
}


// =====================================================
// AUTO ZERO IMU - FAIL-SAFE
//
// Maximum calibration time is bounded.
// If I2C/MPU fails, calibration exits instead of freezing.
// Old good zero values are preserved on failure.
// =====================================================

bool autoZeroIMU()
{
  if (!mpuFound)
  {
    return false;
  }

  digitalWrite(
    LED_RED,
    LOW
  );

  vibrationActive = false;

  Serial.println();
  Serial.println("==============================");
  Serial.println(" IMU AUTO ZERO");
  Serial.println(" KEEP NODE STILL");
  Serial.println("==============================");

  oled.clear();

  oled.setTextAlignment(
    TEXT_ALIGN_CENTER
  );

  oled.setFont(
    ArialMT_Plain_16
  );

  oled.drawString(
    64,
    8,
    "AUTO ZERO"
  );

  oled.setFont(
    ArialMT_Plain_10
  );

  oled.drawString(
    64,
    34,
    "Keep node still"
  );

  oled.drawString(
    64,
    48,
    "Calibrating..."
  );

  oled.display();

  delay(50);

  float oldZeroAx = zeroAx;
  float oldZeroAy = zeroAy;
  float oldZeroAz = zeroAz;

  float oldZeroGx = zeroGx;
  float oldZeroGy = zeroGy;
  float oldZeroGz = zeroGz;

  float oldZeroRoll = zeroRoll;
  float oldZeroPitch = zeroPitch;

  bool oldCalibrated = imuCalibrated;

  double sumAx = 0;
  double sumAy = 0;
  double sumAz = 0;

  double sumGx = 0;
  double sumGy = 0;
  double sumGz = 0;

  int validSamples = 0;
  int consecutiveFails = 0;

  unsigned long calibrationStart =
    millis();

  while (
    validSamples <
    IMU_AUTOZERO_SAMPLES
  )
  {
    if (
      millis() - calibrationStart >=
      IMU_AUTOZERO_TIMEOUT_MS
    )
    {
      Serial.println(
        "AUTO ZERO TIMEOUT"
      );

      break;
    }

    if (readMPURaw())
    {
      float ax =
        rawAx /
        16384.0f;

      float ay =
        rawAy /
        16384.0f;

      float az =
        rawAz /
        16384.0f;

      float gx =
        rawGx /
        131.0f;

      float gy =
        rawGy /
        131.0f;

      float gz =
        rawGz /
        131.0f;

      sumAx += ax;
      sumAy += ay;
      sumAz += az;

      sumGx += gx;
      sumGy += gy;
      sumGz += gz;

      validSamples++;
      consecutiveFails = 0;
    }
    else
    {
      consecutiveFails++;

      if (
        consecutiveFails >=
        IMU_AUTOZERO_MAX_FAILS
      )
      {
        Serial.println(
          "AUTO ZERO ABORT: IMU READ FAIL"
        );

        break;
      }
    }

    delay(5);
  }

  if (
    validSamples <
    IMU_AUTOZERO_MIN_SAMPLES
  )
  {
    zeroAx = oldZeroAx;
    zeroAy = oldZeroAy;
    zeroAz = oldZeroAz;

    zeroGx = oldZeroGx;
    zeroGy = oldZeroGy;
    zeroGz = oldZeroGz;

    zeroRoll = oldZeroRoll;
    zeroPitch = oldZeroPitch;

    imuCalibrated = oldCalibrated;
    imuDataValid = false;

    Serial.print(
      "AUTO ZERO FAILED - VALID SAMPLES: "
    );

    Serial.println(
      validSamples
    );

    oled.clear();

    oled.setTextAlignment(
      TEXT_ALIGN_CENTER
    );

    oled.setFont(
      ArialMT_Plain_16
    );

    oled.drawString(
      64,
      12,
      "IMU ERROR"
    );

    oled.setFont(
      ArialMT_Plain_10
    );

    oled.drawString(
      64,
      38,
      "Recovery pending"
    );

    oled.display();

    delay(100);

    return false;
  }

  float newZeroAx =
    sumAx /
    validSamples;

  float newZeroAy =
    sumAy /
    validSamples;

  float newZeroAz =
    sumAz /
    validSamples;

  float newZeroGx =
    sumGx /
    validSamples;

  float newZeroGy =
    sumGy /
    validSamples;

  float newZeroGz =
    sumGz /
    validSamples;

  if (!readMPURaw())
  {
    zeroAx = oldZeroAx;
    zeroAy = oldZeroAy;
    zeroAz = oldZeroAz;

    zeroGx = oldZeroGx;
    zeroGy = oldZeroGy;
    zeroGz = oldZeroGz;

    zeroRoll = oldZeroRoll;
    zeroPitch = oldZeroPitch;

    imuCalibrated = oldCalibrated;
    imuDataValid = false;

    Serial.println(
      "AUTO ZERO FAILED: FINAL IMU READ"
    );

    return false;
  }

  zeroAx = newZeroAx;
  zeroAy = newZeroAy;
  zeroAz = newZeroAz;

  zeroGx = newZeroGx;
  zeroGy = newZeroGy;
  zeroGz = newZeroGz;

  accelX =
    rawAx /
    16384.0f;

  accelY =
    rawAy /
    16384.0f;

  accelZ =
    rawAz /
    16384.0f;

  zeroRoll =
    atan2(
      accelY,
      accelZ
    ) *
    180.0f /
    PI;

  zeroPitch =
    atan2(
      -accelX,
      sqrt(
        accelY * accelY +
        accelZ * accelZ
      )
    ) *
    180.0f /
    PI;

  imuCalibrated = true;
  imuDataValid = true;
  imuReadFailCount = 0;

  Serial.println(
    "AUTO ZERO COMPLETE"
  );

  Serial.print(
    "VALID SAMPLES : "
  );

  Serial.println(
    validSamples
  );

  Serial.print(
    "ZERO A : "
  );

  Serial.print(zeroAx, 4);
  Serial.print(", ");
  Serial.print(zeroAy, 4);
  Serial.print(", ");
  Serial.println(zeroAz, 4);

  Serial.print(
    "ZERO G : "
  );

  Serial.print(zeroGx, 3);
  Serial.print(", ");
  Serial.print(zeroGy, 3);
  Serial.print(", ");
  Serial.println(zeroGz, 3);

  delay(50);

  return true;
}


// =====================================================
// STATUS LED INIT
// =====================================================

void initStatusLED()
{
  pinMode(
    LED_GREEN,
    OUTPUT
  );

  pinMode(
    LED_YELLOW,
    OUTPUT
  );

  pinMode(
    LED_RED,
    OUTPUT
  );


  // Boot = ยังไม่ online
  digitalWrite(
    LED_GREEN,
    LOW
  );


  // Uplink reserved
  digitalWrite(
    LED_YELLOW,
    LOW
  );


  // No vibration
  digitalWrite(
    LED_RED,
    LOW
  );
}


// =====================================================
// NODE ONLINE LED
// =====================================================

void setNodeOnline(
  bool online
)
{
  digitalWrite(
    LED_GREEN,
    online ?
    HIGH :
    LOW
  );
}


// =====================================================
// VIBRATION DETECTOR
// =====================================================

void updateVibrationDetector()
{
  if (
    !mpuFound ||
    !imuCalibrated
  )
  {
    vibrationMagnitude = 0.0f;
    vibrationActive = false;
    motionDetected = false;

    vibrationTriggerCount = 0;
    vibrationReleaseCount = 0;

    digitalWrite(
      LED_RED,
      LOW
    );

    return;
  }


  // =================================================
  // Relative acceleration magnitude
  // =================================================

  float magnitude =
    sqrt(
      relAx * relAx +
      relAy * relAy +
      relAz * relAz
    );


  // =================================================
  // NOISE FLOOR
  // =================================================

  if (
    magnitude <
    VIB_NOISE_FLOOR
  )
  {
    magnitude = 0.0f;
  }


  vibrationMagnitude =
    magnitude;


  // =================================================
  // WAITING FOR VIBRATION
  // =================================================

  if (!vibrationActive)
  {
    if (
      magnitude >=
      VIB_TRIGGER_THRESHOLD
    )
    {
      if (
        vibrationTriggerCount <
        255
      )
      {
        vibrationTriggerCount++;
      }


      if (
        vibrationTriggerCount >=
        VIB_TRIGGER_COUNT
      )
      {
        vibrationActive = true;

        // Confirmed vibration: restart 60-second re-zero timer.
        lastVibrationMs = millis();

        vibrationTriggerCount = 0;
        vibrationReleaseCount = 0;


        // RED = VIBRATION
        digitalWrite(
          LED_RED,
          HIGH
        );


        Serial.println();
        Serial.println(
          ">>> VIBRATION DETECTED"
        );

        Serial.print(
          "Magnitude : "
        );

        Serial.print(
          vibrationMagnitude,
          4
        );

        Serial.println(
          " g"
        );

        Serial.println(
          "RED LED ON"
        );
      }
    }
    else
    {
      vibrationTriggerCount = 0;
    }
  }


  // =================================================
  // VIBRATION ACTIVE
  // =================================================

  else
  {
    // Countdown starts only after vibration has actually stopped.
    lastVibrationMs = millis();

    if (
      magnitude <=
      VIB_RELEASE_THRESHOLD
    )
    {
      if (
        vibrationReleaseCount <
        255
      )
      {
        vibrationReleaseCount++;
      }


      if (
        vibrationReleaseCount >=
        VIB_RELEASE_COUNT
      )
      {
        vibrationActive = false;

        vibrationTriggerCount = 0;
        vibrationReleaseCount = 0;


        digitalWrite(
          LED_RED,
          LOW
        );


        Serial.println();
        Serial.println(
          ">>> VIBRATION STOPPED"
        );

        Serial.println(
          "RED LED OFF"
        );
      }
    }
    else
    {
      vibrationReleaseCount = 0;
    }
  }


  motionDetected =
    vibrationActive;
}


// =====================================================
// PERIODIC IMU RE-ZERO
//
// Count 60 seconds from the last confirmed vibration.
// Calibration is fail-safe and bounded.
// =====================================================

void updatePeriodicIMUZero()
{
  if (
    !mpuFound ||
    !imuCalibrated
  )
  {
    return;
  }

  if (vibrationActive)
  {
    lastVibrationMs = millis();
    return;
  }

  unsigned long now =
    millis();

  unsigned long referenceTime =
    (lastVibrationMs > lastAutoZeroMs) ?
    lastVibrationMs :
    lastAutoZeroMs;

  if (
    now - referenceTime <
    IMU_REZERO_STABLE_MS
  )
  {
    return;
  }

  Serial.println();
  Serial.println(
    ">>> 60 SEC NO VIBRATION -> IMU RE-ZERO"
  );

  vibrationTriggerCount = 0;
  vibrationReleaseCount = 0;

  vibrationActive = false;
  motionDetected = false;
  vibrationMagnitude = 0.0f;

  digitalWrite(
    LED_RED,
    LOW
  );

  bool zeroOk =
    autoZeroIMU();

  // Always move the timer forward so a failed calibration
  // cannot immediately retry every loop and appear frozen.
  lastAutoZeroMs =
    millis();

  lastVibrationMs =
    lastAutoZeroMs;

  if (zeroOk)
  {
    readMPU();

    vibrationTriggerCount = 0;
    vibrationReleaseCount = 0;

    vibrationActive = false;
    motionDetected = false;
    vibrationMagnitude = 0.0f;

    digitalWrite(
      LED_RED,
      LOW
    );

    Serial.println(
      ">>> PERIODIC IMU RE-ZERO COMPLETE"
    );
  }
  else
  {
    Serial.println(
      ">>> PERIODIC RE-ZERO FAILED"
    );

    recoverIMU();
  }

  drawCurrentPage();
}


// =====================================================
// BATTERY
// =====================================================

void readBattery()
{
  digitalWrite(
    ADC_CTRL_PIN,
    HIGH
  );

  delay(5);


  uint32_t adcMv =
    analogReadMilliVolts(
      VBAT_ADC_PIN
    );


  batteryVoltage =
    (adcMv / 1000.0f) *
    VBAT_DIVIDER;


  digitalWrite(
    ADC_CTRL_PIN,
    LOW
  );


  float percent =
    (
      batteryVoltage -
      BATTERY_MIN_V
    ) /
    (
      BATTERY_MAX_V -
      BATTERY_MIN_V
    ) *
    100.0f;


  if (percent > 100.0f)
  {
    percent = 100.0f;
  }

  if (percent < 0.0f)
  {
    percent = 0.0f;
  }


  batteryPercent =
    (int)round(percent);
}


// =====================================================
// WIFI CONNECT (BLOCKING -- SETUP ONLY)
// =====================================================

void connectWiFi()
{
  Serial.println();
  Serial.print(
    "WIFI CONNECTING TO : "
  );
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long start = millis();

  while (
    WiFi.status() != WL_CONNECTED &&
    millis() - start < 10000
  )
  {
    delay(250);
    Serial.print(".");
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED)
  {
    wifiConnected = true;

    Serial.println("WIFI CONNECTED");

    Serial.print(
      "IP ADDRESS  : "
    );
    Serial.println(WiFi.localIP());
  }
  else
  {
    wifiConnected = false;

    Serial.println(
      "WIFI CONNECT FAILED -- WILL KEEP RETRYING IN BACKGROUND"
    );
  }
}


// =====================================================
// WIFI RECONNECT (NON-BLOCKING -- CALLED FROM loop())
// =====================================================

void ensureWiFi()
{
  if (WiFi.status() == WL_CONNECTED)
  {
    wifiConnected = true;
    return;
  }

  wifiConnected = false;

  // Rate-limit reconnect attempts so a prolonged outage doesn't repeatedly
  // block the 1 Hz sensor/OLED loop -- WiFi.begin() itself returns quickly,
  // but retrying every single cycle would still add needless overhead.
  if (
    lastWifiAttempt != 0 &&
    millis() - lastWifiAttempt <
    WIFI_RECONNECT_INTERVAL_MS
  )
  {
    return;
  }

  lastWifiAttempt = millis();

  Serial.println();
  Serial.println(
    "WIFI DISCONNECTED -- RETRYING"
  );

  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}


// =====================================================
// SERVER UPLINK
//
// POST http://SERVER_HOST:SERVER_PORT/api/nodes/NODE_ID/telemetry
// Header: X-Node-Key: NODE_API_KEY
//
// Hand-built JSON (no ArduinoJson dependency) -- every field here is a
// known float/bool this file already tracks, so plain string concatenation
// is safe and keeps this node's dependencies to just what ships with the
// Heltec/ESP32 core.
// =====================================================

// Appends one axis of the wave buffer as a JSON array, e.g. "[0.0123,-0.0041,...]"
void appendWaveArrayJson(
  String &body,
  float *axisBuf,
  uint8_t count
)
{
  body += "[";

  for (uint8_t i = 0; i < count; i++)
  {
    if (i)
    {
      body += ",";
    }

    body += String(axisBuf[i], 4);
  }

  body += "]";
}


bool uploadTelemetry()
{
  if (WiFi.status() != WL_CONNECTED)
  {
    return false;
  }

  HTTPClient http;

  String url =
    String("http://") +
    SERVER_HOST +
    ":" +
    String(SERVER_PORT) +
    "/api/nodes/" +
    NODE_ID +
    "/telemetry";

  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Node-Key", NODE_API_KEY);
  http.setTimeout(UPLINK_HTTP_TIMEOUT_MS);

  String body = "{";

  body += "\"temperature_c\":" + String(bmpFound ? temperatureC : 0.0f, 2) + ",";
  body += "\"pressure_hpa\":"  + String(bmpFound ? pressureHpa  : 0.0f, 2) + ",";

  body += "\"battery_v\":"   + String(batteryVoltage, 3) + ",";
  body += "\"battery_pct\":" + String(batteryPercent) + ",";

  body += "\"accel_x\":" + String(relAx, 4) + ",";
  body += "\"accel_y\":" + String(relAy, 4) + ",";
  body += "\"accel_z\":" + String(relAz, 4) + ",";

  body += "\"gyro_x\":" + String(relGx, 3) + ",";
  body += "\"gyro_y\":" + String(relGy, 3) + ",";
  body += "\"gyro_z\":" + String(relGz, 3) + ",";

  body += "\"roll_deg\":"  + String(relativeRoll, 2) + ",";
  body += "\"pitch_deg\":" + String(relativePitch, 2) + ",";

  body += "\"vibration_g\":"      + String(vibrationMagnitude, 4) + ",";
  body += "\"vibration_active\":" + String(vibrationActive ? "true" : "false") + ",";

  body += "\"bmp_ok\":" + String(bmpFound ? "true" : "false") + ",";
  body += "\"imu_ok\":" + String(mpuFound ? "true" : "false") + ",";

  body += "\"uptime_s\":" + String(millis() / 1000) + ",";

  // Raw ~1 second of 20 Hz samples since the last upload -- see
  // server/routes/nodes.py post_telemetry() for how these get appended
  // into the server's own rolling per-node buffer.
  body += "\"wave\":{\"x\":";
  appendWaveArrayJson(body, waveBufX, waveBufCount);
  body += ",\"y\":";
  appendWaveArrayJson(body, waveBufY, waveBufCount);
  body += ",\"z\":";
  appendWaveArrayJson(body, waveBufZ, waveBufCount);
  body += "}";

  body += "}";

  // Cleared now that this second's samples are already copied into `body`
  // above -- regardless of whether the POST below actually succeeds, so a
  // slow/failed upload can't leave the buffer stuck full and silently
  // dropping every new sample until the next successful attempt.
  waveBufCount = 0;

  int httpCode = http.POST(body);

  bool ok = (httpCode == 200);

  if (ok)
  {
    // YELLOW LED = flash when telemetry is successfully sent to server
    digitalWrite(LED_YELLOW, HIGH);
    delay(UPLINK_LED_PULSE_MS);
    digitalWrite(LED_YELLOW, LOW);

    Serial.println("UPLINK OK");
  }
  else
  {
    Serial.print(
      "UPLINK FAILED, HTTP CODE : "
    );
    Serial.println(httpCode);
  }

  http.end();

  return ok;
}


// =====================================================
// OLED HEADER
// =====================================================

void drawHeader(
  const String &title
)
{
  oled.setTextAlignment(
    TEXT_ALIGN_CENTER
  );

  oled.setFont(
    ArialMT_Plain_16
  );

  oled.drawString(
    64,
    0,
    title
  );


  oled.drawHorizontalLine(
    0,
    18,
    128
  );


  oled.setTextAlignment(
    TEXT_ALIGN_LEFT
  );

  oled.setFont(
    ArialMT_Plain_10
  );
}


// =====================================================
// PAGE 1 : MAIN
// ACCEL + GYRO AXES
// =====================================================

void drawMainPage()
{
  oled.clear();

  drawHeader(
    "ACCEL / GYRO"
  );

  if (!mpuFound)
  {
    oled.drawString(
      4,
      30,
      "IMU : NOT FOUND"
    );

    oled.display();
    return;
  }

  if (!imuDataValid)
  {
    oled.drawString(
      4,
      26,
      "IMU : RECOVERING"
    );

    oled.drawString(
      4,
      42,
      "DATA : INVALID"
    );

    oled.display();
    return;
  }

  oled.drawString(
    2,
    21,
    "A X:" + String(relAx, 3) +
    " Y:" + String(relAy, 3)
  );

  oled.drawString(
    2,
    32,
    "A Z:" + String(relAz, 3) +
    " g"
  );

  oled.drawString(
    2,
    43,
    "G X:" + String(relGx, 1) +
    " Y:" + String(relGy, 1)
  );

  oled.drawString(
    2,
    54,
    "G Z:" + String(relGz, 1) +
    " d/s"
  );

  oled.display();
}


// =====================================================
// PAGE 2 : IMU
// =====================================================

void drawIMUPage()
{
  oled.clear();

  drawHeader(
    "IMU SENSOR"
  );


  if (!mpuFound)
  {
    oled.drawString(
      4,
      30,
      "MPU : NOT FOUND"
    );

    oled.display();

    return;
  }


  oled.drawString(
    2,
    21,
    "AX:" +
    String(relAx, 3) +
    " AY:" +
    String(relAy, 3)
  );


  oled.drawString(
    2,
    32,
    "AZ:" +
    String(relAz, 3) +
    " g"
  );


  oled.drawString(
    2,
    43,
    "GX:" +
    String(relGx, 1) +
    " GY:" +
    String(relGy, 1)
  );


  oled.drawString(
    2,
    54,
    "GZ:" +
    String(relGz, 1) +
    " d/s"
  );


  oled.display();
}


// =====================================================
// PAGE 3 : ORIENTATION
// =====================================================

void drawOrientationPage()
{
  oled.clear();

  drawHeader(
    "ORIENTATION"
  );


  if (!mpuFound)
  {
    oled.drawString(
      4,
      30,
      "MPU : NOT FOUND"
    );

    oled.display();

    return;
  }


  oled.drawString(
    4,
    21,
    "ROLL  : " +
    String(relativeRoll, 1) +
    " deg"
  );


  oled.drawString(
    4,
    32,
    "PITCH : " +
    String(relativePitch, 1) +
    " deg"
  );


  oled.drawString(
    4,
    43,
    "VIB   : " +
    String(vibrationMagnitude, 3) +
    " g"
  );


  oled.drawString(
    4,
    54,
    String("STATE : ") +
    (
      vibrationActive ?
      "VIBRATION" :
      "STABLE"
    )
  );


  oled.display();
}


// =====================================================
// PAGE 4 : SYSTEM
// =====================================================

void drawSystemPage()
{
  oled.clear();

  drawHeader(
    "SYSTEM"
  );


  oled.drawString(
    4,
    21,
    String("BMP : ") +
    (
      bmpFound ?
      "ONLINE" :
      "ERROR"
    )
  );


  oled.drawString(
    4,
    32,
    String("IMU : ") +
    (
      (
        mpuFound && imuDataValid ?
        "ONLINE" :
        (
          mpuFound ?
          "RECOVER" :
          "ERROR"
        )
      )
    )
  );


  oled.drawString(
    4,
    43,
    String("NET : ") +
    (
      !wifiConnected ?
      "OFFLINE" :
      (
        lastUploadOk ?
        "UPLINK OK" :
        "NO UPLINK"
      )
    )
  );


  oled.drawString(
    4,
    54,
    "BATT: " +
    String(batteryPercent) +
    "% " +
    String(batteryVoltage, 2) +
    "V"
  );


  oled.display();
}


// =====================================================
// DRAW CURRENT PAGE
// =====================================================

void drawCurrentPage()
{
  switch (currentPage)
  {
    case PAGE_MAIN:

      drawMainPage();

      break;


    case PAGE_IMU:

      drawIMUPage();

      break;


    case PAGE_ORIENTATION:

      drawOrientationPage();

      break;


    case PAGE_SYSTEM:

      drawSystemPage();

      break;


    default:

      currentPage =
        PAGE_MAIN;

      drawMainPage();

      break;
  }
}


// =====================================================
// PRG BUTTON
// =====================================================

void handlePRG()
{
  bool buttonState =
    digitalRead(
      PRG_BUTTON
    );


  if (
    buttonState == LOW &&
    lastButtonState == HIGH
  )
  {
    if (
      millis() -
      lastButtonTime >
      BUTTON_DEBOUNCE
    )
    {
      lastButtonTime =
        millis();


      currentPage++;


      if (
        currentPage >=
        TOTAL_PAGES
      )
      {
        currentPage =
          PAGE_MAIN;
      }


      Serial.println();

      Serial.print(
        "PRG -> PAGE "
      );

      Serial.println(
        currentPage + 1
      );


      drawCurrentPage();
    }
  }


  lastButtonState =
    buttonState;
}


// =====================================================
// SERIAL
// =====================================================

void printSerial()
{
  Serial.println();

  Serial.println(
    "========================================"
  );

  Serial.println(
    "Prototype-node"
  );

  Serial.println(
    "========================================"
  );


  Serial.print(
    "PAGE        : "
  );

  Serial.println(
    currentPage + 1
  );


  if (bmpFound)
  {
    Serial.print(
      "Temperature : "
    );

    Serial.print(
      temperatureC,
      2
    );

    Serial.println(
      " C"
    );


    Serial.print(
      "Pressure    : "
    );

    Serial.print(
      pressureHpa,
      2
    );

    Serial.println(
      " hPa"
    );
  }
  else
  {
    Serial.println(
      "BMP         : ERROR"
    );
  }


  Serial.print(
    "Battery     : "
  );

  Serial.print(
    batteryVoltage,
    3
  );

  Serial.print(
    " V  "
  );

  Serial.print(
    batteryPercent
  );

  Serial.println(
    "%"
  );


  Serial.print(
    "WiFi        : "
  );

  Serial.println(
    wifiConnected ?
    WiFi.localIP().toString() :
    "DISCONNECTED"
  );

  Serial.print(
    "Uplink      : "
  );

  Serial.println(
    lastUploadOk ?
    "OK" :
    "FAILED"
  );


  if (mpuFound)
  {
    Serial.println(
      "----------------------------------------"
    );


    Serial.print(
      "Accel Rel   : "
    );

    Serial.print(
      relAx,
      4
    );

    Serial.print(
      "  "
    );

    Serial.print(
      relAy,
      4
    );

    Serial.print(
      "  "
    );

    Serial.println(
      relAz,
      4
    );


    Serial.print(
      "Gyro Zero   : "
    );

    Serial.print(
      relGx,
      3
    );

    Serial.print(
      "  "
    );

    Serial.print(
      relGy,
      3
    );

    Serial.print(
      "  "
    );

    Serial.println(
      relGz,
      3
    );


    Serial.print(
      "Roll/Pitch  : "
    );

    Serial.print(
      relativeRoll,
      2
    );

    Serial.print(
      " / "
    );

    Serial.println(
      relativePitch,
      2
    );


    Serial.print(
      "Vibration   : "
    );

    Serial.print(
      vibrationMagnitude,
      4
    );

    Serial.println(
      " g"
    );


    Serial.print(
      "VIB State   : "
    );

    Serial.println(
      vibrationActive ?
      "ACTIVE" :
      "STABLE"
    );


    unsigned long reZeroRef =
      (lastVibrationMs > lastAutoZeroMs) ?
      lastVibrationMs :
      lastAutoZeroMs;

    unsigned long quietMs =
      millis() - reZeroRef;

    Serial.print(
      "ReZero in   : "
    );

    if (
      quietMs >=
      IMU_REZERO_STABLE_MS
    )
    {
      Serial.println(
        "NOW"
      );
    }
    else
    {
      Serial.print(
        (IMU_REZERO_STABLE_MS - quietMs) /
        1000
      );

      Serial.println(
        " s"
      );
    }
  }
  else
  {
    Serial.println(
      "IMU         : ERROR"
    );
  }


  Serial.println(
    "----------------------------------------"
  );

  Serial.println(
    "GREEN LED   : ONLINE"
  );

  Serial.print(
    "YELLOW/UPLINK: "
  );

  Serial.println(
    lastUploadOk ?
    "LAST SEND OK" :
    "LAST SEND FAILED"
  );

  Serial.print(
    "RED LED     : "
  );

  Serial.println(
    vibrationActive ?
    "VIBRATION" :
    "OFF"
  );


  Serial.println(
    "========================================"
  );
}


// =====================================================
// SETUP
// =====================================================

void setup()
{
  Serial.begin(
    115200
  );

  delay(
    1500
  );


  Serial.println();

  Serial.println(
    "========================================"
  );

  Serial.println(
    " PROTOTYPE NODE"
  );

  Serial.println(
    "========================================"
  );


  // =================================================
  // STATUS LED
  // =================================================

  initStatusLED();


  // =================================================
  // PRG GPIO0
  // =================================================

  pinMode(
    PRG_BUTTON,
    INPUT_PULLUP
  );

  lastButtonState =
    digitalRead(
      PRG_BUTTON
    );


  // =================================================
  // OLED POWER
  //
  // KNOWN-GOOD SEQUENCE
  // =================================================

  pinMode(
    VEXT_CTRL,
    OUTPUT
  );

  digitalWrite(
    VEXT_CTRL,
    LOW
  );

  delay(
    1000
  );


  // =================================================
  // OLED INIT
  // =================================================

  oled.init();

  delay(
    100
  );


  oled.clear();

  oled.setTextAlignment(
    TEXT_ALIGN_CENTER
  );

  oled.setFont(
    ArialMT_Plain_16
  );

  oled.drawString(
    64,
    10,
    "Prototype-node"
  );


  oled.setFont(
    ArialMT_Plain_10
  );

  oled.drawString(
    64,
    37,
    "Starting..."
  );


  oled.display();


  // =================================================
  // SENSOR I2C
  // =================================================

  SensorWire.begin(
    GY91_SDA,
    GY91_SCL,
    100000
  );

  SensorWire.setTimeOut(
    IMU_I2C_TIMEOUT_MS
  );

  delay(
    500
  );


  // =================================================
  // BMP
  // =================================================

  bmpFound =
    detectBMP();

  if (bmpFound)
  {
    initBMP();

    Serial.println(
      "BMP INITIALIZED"
    );
  }


  // =================================================
  // MPU
  // =================================================

  mpuFound =
    detectMPU();

  if (mpuFound)
  {
    initMPU();

    Serial.println(
      "MPU INITIALIZED"
    );
  }


  // =================================================
  // BATTERY
  // =================================================

  analogReadResolution(
    12
  );

  pinMode(
    ADC_CTRL_PIN,
    OUTPUT
  );

  digitalWrite(
    ADC_CTRL_PIN,
    LOW
  );


  // =================================================
  // INITIAL READ
  // =================================================

  if (bmpFound)
  {
    readBMP();
  }


  readBattery();


  // =================================================
  // WIFI
  // Non-blocking startup. Do not hold the OLED on
  // "Starting..." while waiting for an access point.
  // loop() will handle connection/reconnection.
  // =================================================

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  wifiConnected = false;
  lastWifiAttempt = millis();


  // =================================================
  // AUTO ZERO
  // =================================================

  if (mpuFound)
  {
    bool initialZeroOk =
      autoZeroIMU();

    if (initialZeroOk)
    {
      readMPU();
    }
    else
    {
      recoverIMU();
    }

    lastAutoZeroMs = millis();
    lastVibrationMs = lastAutoZeroMs;
  }


  // =================================================
  // RESET VIBRATION FILTER
  // =================================================

  vibrationTriggerCount = 0;
  vibrationReleaseCount = 0;

  vibrationActive = false;
  motionDetected = false;
  vibrationMagnitude = 0.0f;

  digitalWrite(
    LED_RED,
    LOW
  );


  // =================================================
  // YELLOW = UPLINK TX -- starts off and flashes briefly
  // whenever the server accepts an upload
  // =================================================

  digitalWrite(
    LED_YELLOW,
    LOW
  );


  // =================================================
  // NODE READY
  // GREEN ONLINE
  // =================================================

  setNodeOnline(
    true
  );


  // =================================================
  // START PAGE
  // =================================================

  currentPage =
    PAGE_MAIN;

  // Always leave the startup screen, even if WiFi/server is unavailable.
  drawCurrentPage();


  Serial.println();
  Serial.println(
    "NODE READY"
  );

  Serial.println(
    "GREEN LED ON"
  );

  Serial.println(
    "YELLOW = FLASH ON SUCCESSFUL SERVER UPLOAD"
  );

  Serial.println(
    "RED = VIBRATION"
  );

  Serial.println(
    "PRG GPIO0 : PAGE 1 -> 2 -> 3 -> 4 -> 1"
  );

  Serial.print(
    "UPLINK TARGET : "
  );

  Serial.print(SERVER_HOST);
  Serial.print(":");
  Serial.print(SERVER_PORT);
  Serial.print("/api/nodes/");
  Serial.print(NODE_ID);
  Serial.println("/telemetry");
}


// =====================================================
// LOOP
// =====================================================

void loop()
{
  // =================================================
  // BUTTON
  // =================================================

  handlePRG();


  // =================================================
  // IMU
  // 20 Hz = every 50 ms
  // =================================================

  static unsigned long lastIMUUpdate = 0;

  if (
    millis() -
    lastIMUUpdate >=
    50
  )
  {
    lastIMUUpdate =
      millis();


    if (mpuFound)
    {
      if (readMPU())
      {
        updateVibrationDetector();

        // Append this sample to the raw waveform buffer -- see its
        // declaration above for why the server, not this board, is
        // where the long history and the real analysis live.
        if (waveBufCount < WAVE_BUFFER_CAPACITY)
        {
          waveBufX[waveBufCount] = relAx;
          waveBufY[waveBufCount] = relAy;
          waveBufZ[waveBufCount] = relAz;

          waveBufCount++;
        }
      }
      else
      {
        // Do not keep stale values or stale vibration state.
        vibrationActive = false;
        motionDetected = false;
        vibrationMagnitude = 0.0f;

        digitalWrite(
          LED_RED,
          LOW
        );

        if (
          imuReadFailCount >=
          IMU_RECOVERY_FAIL_COUNT
        )
        {
          if (recoverIMU())
          {
            if (!imuCalibrated)
            {
              autoZeroIMU();
            }

            readMPU();
          }
        }
      }
    }
  }


  // =================================================
  // PERIODIC IMU RE-ZERO
  // After 1 minute of continuous stability
  // =================================================

  updatePeriodicIMUZero();


  // =================================================
  // BMP + BATTERY + OLED
  // 1 Hz
  // =================================================

  static unsigned long lastDisplayUpdate = 0;

  if (
    millis() -
    lastDisplayUpdate >=
    1000
  )
  {
    lastDisplayUpdate =
      millis();


    if (bmpFound)
    {
      readBMP();
    }


    readBattery();


    // =============================================
    // SERVER UPLINK
    // =============================================

    ensureWiFi();

    if (wifiConnected)
    {
      lastUploadOk =
        uploadTelemetry();
    }
    else
    {
      lastUploadOk = false;
    }

    // YELLOW LED is pulsed inside uploadTelemetry() only when
    // the server accepts the telemetry upload successfully.


    drawCurrentPage();

    printSerial();
  }


  delay(
    10
  );
}