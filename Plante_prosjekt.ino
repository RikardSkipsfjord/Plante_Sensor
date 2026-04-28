#include <WiFiNINA.h>
#include <DHT.h>
#include <Adafruit_SleepyDog.h>
#include <ArduinoHttpClient.h>

#define DHTPIN 2
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

const int SOIL_PIN = A0;

// Kalibrering (juster etter dine målinger)
int SOIL_DRY = 800;  // tørr luft/tørr jord
int SOIL_WET = 350;  // vann / veldig våt jord

char ssid[] = "Rikard :D";
char pass[] = "yitqcedfaisud";

const char serverAddress[] = "10.0.0.84";
const int serverPort = 5000;

WiFiClient wifi;
HttpClient http(wifi, serverAddress, serverPort);

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  WiFi.disconnect();
  WiFi.begin(ssid, pass);

  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - t0) < 15000) {
    Watchdog.reset();
    delay(250);
  }
}

int readSoilRaw() {
  long sum = 0;
  for (int i = 0; i < 10; i++) {
    sum += analogRead(SOIL_PIN);
    delay(5);
  }
  return (int)(sum / 10);
}

int soilPercentFromRaw(int soil_raw) {
  int raw_clamped = soil_raw;
  if (raw_clamped > SOIL_DRY) raw_clamped = SOIL_DRY;
  if (raw_clamped < SOIL_WET) raw_clamped = SOIL_WET;

  // 0 = tørr, 100 = våt
  return (int)((SOIL_DRY - raw_clamped) * 100.0 / (SOIL_DRY - SOIL_WET));
}

void postJson(const char* path, const String& json) {
  if (WiFi.status() != WL_CONNECTED) return;

  http.post(path, "application/json", json);

  int statusCode = http.responseStatusCode();
  // Les body for å tømme respons (hindrer at neste request blir rar)
  String body = http.responseBody();

  Serial.print(path);
  Serial.print(" -> ");
  Serial.println(statusCode);
}

void sendHeartbeat() {
  String json = "{";
  json += "\"device_id\":\"nano33iot-1\",";
  json += "\"uptime_s\":" + String(millis() / 1000) + ",";
  json += "\"rssi\":" + String(WiFi.RSSI());
  json += "}";

  postJson("/heartbeat", json);
}

void sendData(float t, float h, int soil_raw, int soil_pct) {
  unsigned long uptime_s = millis() / 1000;
  int rssi = WiFi.RSSI();

  String json = "{";
  json += "\"device_id\":\"nano33iot-1\",";
  json += "\"temperature\":" + String(t, 1) + ",";
  json += "\"humidity\":" + String(h, 1) + ",";
  json += "\"uptime_s\":" + String(uptime_s) + ",";
  json += "\"rssi\":" + String(rssi) + ",";
  json += "\"soil_raw\":" + String(soil_raw) + ",";
  json += "\"soil_pct\":" + String(soil_pct);
  json += "}";

  postJson("/data", json);
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  analogReadResolution(10);

  Serial.begin(115200);
  unsigned long s0 = millis();
  while (!Serial && (millis() - s0) < 15000) {}

  dht.begin();

  // Watchdog: 8 sek
  Watchdog.enable(8000);

  connectWiFi();
}

void loop() {
  Watchdog.reset();

  // LED livstegn
  digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));

  connectWiFi();
  if (WiFi.status() != WL_CONNECTED) {
    delay(500);
    return;
  }

  // Heartbeat hver 10. sek
  static unsigned long lastHb = 0;
  if (millis() - lastHb > 10000) {
    lastHb = millis();
    sendHeartbeat();
  }

  float h = dht.readHumidity();
  float t = dht.readTemperature();
  if (isnan(h) || isnan(t)) {
    delay(2000);
    return;
  }

  int soil_raw = readSoilRaw();
  int soil_pct = soilPercentFromRaw(soil_raw);

  sendData(t, h, soil_raw, soil_pct);

  delay(5000);
}
