# Battery_Discharge_Logger_RP2040

Sytem requires 2 resistors as a voltage divider to bring high voltages to a safe level.
It also needs a 100n cap across pin 29 and GND for better accuracy.
Voltage divider feed goes to pin 29
GND on the RP2040 links to the battery negative - terminal
Supplied UF2 is set for 10k 1k resistors, safe for 21v on a 3.3v system.
If your voltage or resistors differ change the values in the main.cpp and compile a fresh UF2 to suit.

