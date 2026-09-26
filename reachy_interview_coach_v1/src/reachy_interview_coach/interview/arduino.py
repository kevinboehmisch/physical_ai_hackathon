"""Optional SparkFun RedBoard companion: traffic-light LEDs for speaking pace, 16x2 LCD for question and timer.

The app works without a board: if no port is configured or detected, every method is a no-op.
Serial protocol (ASCII lines, 115200 baud), see ``arduino/interview_display/interview_display.ino``:

    LED G|Y|R|OFF          traffic light
    L1 <text>              LCD line 1 (max 16 chars)
    L2 <text>              LCD line 2 (max 16 chars)
"""

import time
import logging
import threading
from typing import Any

import serial
from serial.tools import list_ports

from reachy_interview_coach.interview.session import SessionEvent, InterviewSession


logger = logging.getLogger(__name__)

BAUD_RATE = 115200
# USB vendor ids of boards we accept when auto-detecting: FTDI (classic RedBoard), CH340 clones, Arduino, SparkFun.
KNOWN_VENDOR_IDS = {0x0403, 0x1A86, 0x2341, 0x1B4F}
# The Reachy Mini Lite motor bus is a CH340-family device (see reachy_mini.daemon.utils); never touch it.
EXCLUDED_VID_PID = {(0x1A86, 0x55D3)}
# Words-per-minute bands per language: (green_low, green_high, yellow_margin); outside yellow -> red.
PACE_BANDS = {"de": (110.0, 160.0, 25.0), "en": (130.0, 170.0, 25.0)}
MIN_UTTERANCE_S = 2.5
TIMER_PERIOD_S = 1.0
LCD_WIDTH = 16

LABELS = {
    "de": {"ready": "Reachy Coach", "waiting": "Bereit", "question": "Frage", "done": "Fertig", "thanks": "Danke!"},
    "en": {"ready": "Reachy Coach", "waiting": "Ready", "question": "Question", "done": "Done", "thanks": "Thanks!"},
}


def detect_port(preferred: str | None = None) -> str | None:
    """Return the configured port, else the first serial device that looks like an Arduino-compatible board."""
    if preferred:
        return preferred
    for port in list_ports.comports():
        if (port.vid, port.pid) in EXCLUDED_VID_PID:
            continue
        description = (port.description or "").lower()
        if port.vid in KNOWN_VENDOR_IDS or "arduino" in description or "usb serial" in description:
            logger.info("Arduino candidate: %s (%s)", port.device, port.description)
            return port.device
    return None


def pace_color(words_per_minute: float, language: str) -> str:
    """Map a speaking pace to G/Y/R."""
    low, high, margin = PACE_BANDS.get(language, PACE_BANDS["en"])
    if low <= words_per_minute <= high:
        return "G"
    if low - margin <= words_per_minute <= high + margin:
        return "Y"
    return "R"


class ArduinoDisplay:
    """Mirror interview state to the board; silently disabled when no board is present."""

    def __init__(self, session: InterviewSession, port: str | None) -> None:
        """Open ``port`` (already resolved via :func:`detect_port`); ``None`` leaves the display disabled."""
        self.session = session
        self.language = session.settings.language if session.settings.language in LABELS else "en"
        self._labels = LABELS[self.language]
        self._serial: serial.Serial | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._question_started_at: float | None = None
        if port is None:
            logger.info("No Arduino port configured or detected; LED/LCD feedback disabled")
            return
        try:
            self._serial = serial.Serial(port, BAUD_RATE, timeout=0.2, write_timeout=0.5)
        except serial.SerialException as exc:
            logger.warning("Could not open Arduino port %s: %s (continuing without board)", port, exc)
            return
        session.subscribe(self._on_session_event)
        logger.info("Arduino display connected on %s", port)

    @property
    def enabled(self) -> bool:
        """True while a board is connected."""
        return self._serial is not None

    def start(self) -> None:
        """Show the idle screen and start the timer thread."""
        if not self.enabled:
            return
        time.sleep(1.5)  # RedBoard resets on serial open; let the sketch boot
        self._send("LED", "OFF")
        self._send("L1", self._labels["ready"])
        self._send("L2", self._labels["waiting"])
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._timer_loop, name="arduino-display", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the timer thread, clear the board and close the port."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._serial is not None:
            self._send("LED", "OFF")
            self._send("L1", self._labels["ready"])
            self._send("L2", "")
            try:
                self._serial.close()
            except serial.SerialException as exc:
                logger.debug("Closing Arduino port failed: %s", exc)
            self._serial = None

    # Session events

    def _on_session_event(self, event: SessionEvent, payload: dict[str, Any]) -> None:
        if event == "question_asked":
            self._question_started_at = time.monotonic()
            self._send("LED", "OFF")
            self._send("L1", f"{self._labels['question']} {payload.get('number')}/{payload.get('total')}")
            self._send("L2", "00:00")
        elif event == "user_transcript":
            duration = payload.get("duration")
            text = payload.get("text") or ""
            words = len(text.split())
            if duration and duration >= MIN_UTTERANCE_S and words:
                wpm = words / duration * 60.0
                self._send("LED", pace_color(wpm, self.language))
        elif event == "finished":
            self._question_started_at = None
            self._send("LED", "OFF")
            self._send("L1", self._labels["done"])
            self._send("L2", self._labels["thanks"])

    def _timer_loop(self) -> None:
        while not self._stop_event.wait(TIMER_PERIOD_S):
            started = self._question_started_at
            if started is None:
                continue
            elapsed = int(time.monotonic() - started)
            self._send("L2", f"{elapsed // 60:02d}:{elapsed % 60:02d}")

    def _send(self, command: str, value: str) -> None:
        if self._serial is None:
            return
        value = value[:LCD_WIDTH] if command.startswith("L") else value
        line = f"{command} {value}\n".encode("ascii", errors="replace")
        with self._lock:
            try:
                self._serial.write(line)
            except serial.SerialException as exc:
                logger.warning("Arduino write failed, disabling board: %s", exc)
                try:
                    self._serial.close()
                finally:
                    self._serial = None
