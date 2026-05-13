#include <Arduino_RouterBridge.h>
#include <OneWire.h>
#include <DallasTemperature.h>


// ── Pin definitions ─────────────────────────────────────────────────────────
#define ONE_WIRE_BUS  2   // DS18B20 data pin (D2)
#define PH_PIN        A0  // pH analog output pin

// ── Sensor objects ───────────────────────────────────────────────────────────
OneWire           oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// ── State ────────────────────────────────────────────────────────────────────
float g_temperature = 0.0f;
float g_ph          = 0.0f;



float get_temperature() {
    return g_temperature;
}


float get_ph() {
    return g_ph;
}



void get_sensors(float &out_temp, float &out_ph) {
    out_temp = g_temperature;
    out_ph   = g_ph;
}

float read_temperature() {
#ifdef SIMULATE_SENSORS
    return simulate_temperature();
#else
    sensors.requestTemperatures();
    float t = sensors.getTempCByIndex(0);
    if (t == DEVICE_DISCONNECTED_C || t < -40.0f || t > 85.0f) {
        return -999.0f; 
    }
    return t;
#endif
}

float read_ph() {
#ifdef SIMULATE_SENSORS
    return simulate_ph();
#else
    long sum = 0;
    for (int i = 0; i < 10; i++) {
        sum += analogRead(PH_PIN);
        delay(5);
    }
    float adc_value = (float)(sum / 10);
    float voltage   = (adc_value / 1023.0f) * 3.3f;
    float ph_value  = (voltage * 14.0f) / 3.3f;
    // Clamp to valid pH range
    if (ph_value < 0.0f)  ph_value = 0.0f;
    if (ph_value > 14.0f) ph_value = 14.0f;
    return ph_value;
#endif
}

bool linux_ready_flag = false;

bool linux_ready() {
    linux_ready_flag = true;
    return true;
}

void setup() {
    Bridge.begin();

    Bridge.provide("get_temperature", get_temperature);
    Bridge.provide("get_ph",          get_ph);
    Bridge.provide("linux_ready",     linux_ready);

#ifndef SIMULATE_SENSORS
    sensors.begin();
    analogReadResolution(10);  
#endif

    delay(3000);
    bool started = false;
    while (!started) {
        Bridge.call("python_ready").result(started);
        delay(500);
    }
}

void loop() {
    g_temperature = read_temperature();
    g_ph          = read_ph();

    Bridge.notify("sensor_update", g_temperature, g_ph);

    delay(2000);
}
