#include <Arduino_RouterBridge.h>
#include <OneWire.h>
#include <DallasTemperature.h>


#define ONE_WIRE_BUS  2   // DS18B20 DATA pin (D2)
#define PH_PIN        A2  // PH-4502C PO through voltage divider

const float PH_CALIBRATION_VALUE = 27.17f;
const float ADC_REFERENCE_VOLTAGE = 3.3f;
const float PH_DIVIDER_TOP_OHMS = 10000.0f;
const float PH_DIVIDER_BOTTOM_OHMS = 20000.0f;
const float PH_DIVIDER_RATIO =
    PH_DIVIDER_BOTTOM_OHMS / (PH_DIVIDER_TOP_OHMS + PH_DIVIDER_BOTTOM_OHMS);

// ── Sensor objects ───────────────────────────────────────────────────────────
OneWire           oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// ── State ────────────────────────────────────────────────────────────────────
float g_temperature = 0.0f;
float g_ph          = 0.0f;
float g_ph_raw      = 0.0f;
float g_ph_voltage  = 0.0f;



float get_temperature() {
    return g_temperature;
}


float get_ph() {
    return g_ph;
}

float get_ph_raw() {
    return g_ph_raw;
}



void get_sensors(float &out_temp, float &out_ph) {
    out_temp = g_temperature;
    out_ph   = g_ph;
}

float read_temperature() {
    sensors.requestTemperatures();
    float t = sensors.getTempCByIndex(0);
    if (t == DEVICE_DISCONNECTED_C || t < -40.0f || t > 85.0f) {
        return -999.0f; 
    }
    return t;
}

float read_ph() {
    int buffer_arr[10];
    int temp;
    unsigned long int avgval = 0;

    for (int i = 0; i < 10; i++) {
        buffer_arr[i] = analogRead(PH_PIN);
        delay(30);
    }

    for (int i = 0; i < 9; i++) {
        for (int j = i + 1; j < 10; j++) {
            if (buffer_arr[i] > buffer_arr[j]) {
                temp = buffer_arr[i];
                buffer_arr[i] = buffer_arr[j];
                buffer_arr[j] = temp;
            }
        }
    }

    for (int i = 2; i < 8; i++) {
        avgval += buffer_arr[i];
    }

    g_ph_raw = avgval / 6.0f;
    float a2_voltage = g_ph_raw * ADC_REFERENCE_VOLTAGE / 1024.0f;
    g_ph_voltage = a2_voltage / PH_DIVIDER_RATIO;
    float ph_value = -5.70f * g_ph_voltage + PH_CALIBRATION_VALUE;
    if (ph_value < 0.0f)  ph_value = 0.0f;
    if (ph_value > 14.0f) ph_value = 14.0f;
    return ph_value;
}

bool linux_ready_flag = false;

bool linux_ready() {
    linux_ready_flag = true;
    return true;
}

void setup() {
    Serial.begin(9600);
    Bridge.begin();

    Bridge.provide("get_temperature", get_temperature);
    Bridge.provide("get_ph",          get_ph);
    Bridge.provide("get_ph_raw",      get_ph_raw);
    Bridge.provide("linux_ready",     linux_ready);

    sensors.begin();
    analogReadResolution(10);  

    delay(3000);
    bool started = false;
    while (!started) {
        Bridge.call("python_ready_ack").result(started);
        delay(500);
    }
}

void loop() {
    g_temperature = read_temperature();
    g_ph          = read_ph();

    Serial.print("Medida: ");
    Serial.print((int)g_ph_raw);
    Serial.print("\tVolt: ");
    Serial.print(g_ph_voltage, 3);
    Serial.print("\tPH: ");
    Serial.println(g_ph);

    Bridge.notify("sensor_update", g_temperature, g_ph);

    delay(2000);
}
