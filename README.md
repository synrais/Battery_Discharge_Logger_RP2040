# Battery Discharge Logger (RP2040)

## Overview
This system measures battery voltage using a voltage divider connected to an RP2040 microcontroller.

## Hardware Requirements
- 2 resistors (for voltage divider)
- 100nF capacitor

## Wiring Instructions
- The voltage divider is used to scale higher voltages down to a safe level for the RP2040.
- Connect the voltage divider output to **pin 29**.
- Connect **GND** on the RP2040 to the battery negative terminal.
- Place a **100nF capacitor** between **pin 29** and **GND** to improve measurement accuracy.

## Default Configuration
- The supplied UF2 firmware is configured for:
  - **10kΩ (+ resistor)**
  - **1kΩ (- resistor)**
- This setup allows safe measurement of voltages up to approximately **21V** on a **3.3V system**.

## Customization
If your:
- Input voltage range higher, or
- Resistor values are changed

Then you must:
1. Update the values in `main.cpp`
2. Recompile the firmware
3. Flash a new UF2 file to the device

## Notes
- Ensure voltage levels do not exceed the RP2040 ADC limits.
- Incorrect resistor values may damage the microcontroller.
