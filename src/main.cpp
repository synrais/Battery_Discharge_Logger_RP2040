/*
 * Battery Discharge Curve Logger
 * RP2040 Zero (Waveshare) — PlatformIO
 *
 * WIRING:
 *   Battery+ ──── R1 ──── GPIO29/ADC3 ──── R2 ──── Battery-
 *   Battery- ──── GND on RP2040
 *   1nF capacitor across R2 (ADC pin to GND) to reduce noise
 *
 * LED:
 *   Blue             = booting
 *   Green→Yellow→Red = live battery level
 *   Magenta          = write error
 *
 * SERIAL COMMANDS (sent from GUI):
 *   RESET   — restart elapsed timer, print new CSV header
 */

#include <Arduino.h>
#include <Adafruit_NeoPixel.h>

// ── Resistor values — set to your measured values ─────────────────────────────
const float R1_OHMS    =  9950.0f;
const float R2_OHMS    =  1000.0f;

// ── ADC ──────────────────────────────────────────────────────────────────────
const int   ADC_PIN    = 29;
const float ADC_REF    = 3.3f;
const float ADC_MAX    = 4095.0f;
const int   OVERSAMPLE = 64;

// ── Sample rate ───────────────────────────────────────────────────────────────
const int   INTERVAL_S = 1;

// ── LED ───────────────────────────────────────────────────────────────────────
const int   LED_PIN    = 16;
const int   BRIGHTNESS = 60;
const float V_MAX      = 21.0f;
const float V_MIN      =  8.0f;

Adafruit_NeoPixel px(1, LED_PIN, NEO_GRB + NEO_KHZ800);

void setLED(uint8_t r, uint8_t g, uint8_t b) {
    px.setPixelColor(0, px.Color(r, g, b));
    px.show();
}

void voltageColour(float v) {
    float f = constrain((v - V_MIN) / (V_MAX - V_MIN), 0.0f, 1.0f);
    uint8_t r, g;
    if (f >= 0.5f) { r = (uint8_t)(255 * (1.0f - f) * 2); g = 255; }
    else           { r = 255; g = (uint8_t)(255 * f * 2); }
    setLED(r, g, 0);
}

// ── Voltage reading ───────────────────────────────────────────────────────────
float readVoltage() {
    uint32_t sum = 0;
    for (int i = 0; i < OVERSAMPLE; i++) {
        sum += analogRead(ADC_PIN);
        delayMicroseconds(200);
    }
    float pin_v = ((float)sum / OVERSAMPLE / ADC_MAX) * ADC_REF;
    return pin_v * (R1_OHMS + R2_OHMS) / R2_OHMS;
}

// ── State ─────────────────────────────────────────────────────────────────────
unsigned long startMs    = 0;
unsigned long lastSample = 0;

void startSession() {
    startMs    = millis();
    lastSample = 0;
    Serial.println("# RESET");
    Serial.println("elapsed_s,voltage_v");
}

// ═════════════════════════════════════════════════════════════════════════════
void setup() {
    Serial.begin(115200);
    px.begin();
    px.setBrightness(BRIGHTNESS);
    setLED(0, 0, 255);
    analogReadResolution(12);
    delay(2000);
    startSession();
}

void loop() {
    // Handle serial commands from GUI
    if (Serial.available()) {
        String cmd = Serial.readStringUntil('\n');
        cmd.trim();
        if (cmd == "RESET") startSession();
        return;
    }

    unsigned long now = millis();
    if (now - lastSample >= (unsigned long)INTERVAL_S * 1000UL) {
        lastSample = now;
        float v         = readVoltage();
        unsigned long t = (now - startMs) / 1000UL;
        Serial.printf("%lu,%.4f\n", t, v);
        voltageColour(v);
    }
}
