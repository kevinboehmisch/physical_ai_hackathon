/*
 * Reachy Interview Coach - companion display for SparkFun RedBoard (Arduino Uno compatible).
 *
 * Hardware
 *   16x2 character LCD (HD44780, 4-bit mode):
 *     RS -> D12, EN -> D11, D4 -> D5, D5 -> D4, D6 -> D3, D7 -> D2, RW -> GND, V0 -> 10k pot
 *   Traffic light LEDs (each with 220 ohm resistor to GND):
 *     green -> D8, yellow -> D9, red -> D10
 *
 * Serial protocol, 115200 baud, one ASCII command per line:
 *   LED G|Y|R|OFF      set the traffic light
 *   L1 <text>          write LCD line 1 (max 16 chars)
 *   L2 <text>          write LCD line 2 (max 16 chars)
 */

#include <LiquidCrystal.h>

const uint8_t PIN_GREEN = 8;
const uint8_t PIN_YELLOW = 9;
const uint8_t PIN_RED = 10;
const uint8_t LCD_COLS = 16;

LiquidCrystal lcd(12, 11, 5, 4, 3, 2);
String lineBuffer;

void setLed(char color) {
  digitalWrite(PIN_GREEN, color == 'G' ? HIGH : LOW);
  digitalWrite(PIN_YELLOW, color == 'Y' ? HIGH : LOW);
  digitalWrite(PIN_RED, color == 'R' ? HIGH : LOW);
}

void writeLine(uint8_t row, const String &text) {
  lcd.setCursor(0, row);
  String padded = text.substring(0, LCD_COLS);
  while (padded.length() < LCD_COLS) {
    padded += ' ';
  }
  lcd.print(padded);
}

void handleCommand(const String &line) {
  if (line.startsWith("LED ")) {
    String value = line.substring(4);
    value.trim();
    setLed(value.length() > 0 && value != "OFF" ? value.charAt(0) : 0);
  } else if (line.startsWith("L1 ")) {
    writeLine(0, line.substring(3));
  } else if (line.startsWith("L2 ")) {
    writeLine(1, line.substring(3));
  } else if (line == "L1" || line == "L2") {
    writeLine(line.charAt(1) - '1', "");
  }
}

void setup() {
  pinMode(PIN_GREEN, OUTPUT);
  pinMode(PIN_YELLOW, OUTPUT);
  pinMode(PIN_RED, OUTPUT);
  setLed(0);
  lcd.begin(LCD_COLS, 2);
  writeLine(0, "Reachy Coach");
  writeLine(1, "waiting...");
  Serial.begin(115200);
  lineBuffer.reserve(40);
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      lineBuffer.trim();
      if (lineBuffer.length() > 0) {
        handleCommand(lineBuffer);
      }
      lineBuffer = "";
    } else if (c != '\r' && lineBuffer.length() < 40) {
      lineBuffer += c;
    }
  }
}
