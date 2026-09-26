# Stand: Version vor der Hintergrund-Auswertung (26.09.2026, ~15:13)

Kopie der App im Zustand nach dem Live-Test „es funktioniert jetzt alles" (ToolCallRoutine-Fix), also **vor**:

- Hintergrund-Auswertung / Whisper-Vorladen / frühes Transkribieren (`coordinator.py`),
- nicht-blockierendem `finish_interview` und automatischer Ergebnis-Zustellung (`interview_control.py`, `stream.py`),
- den Profilregeln zu Auswertung/Kamera/Hintergrundgesprächen,
- der Korrektur des Report-Pfads (hier landen Berichte unter `src/reachy_interview_coach/reports/`).

Bekanntes Verhalten dieser Version: `finish_interview` blockiert bis Whisper + LLM fertig sind (~1 min);
solange antwortet das Realtime-Backend nicht auf Zwischenfragen.

## Starten

Das Paket ist per `pip install -e` auf `../reachy_interview_coach` installiert. Damit diese Kopie ihren eigenen
Code lädt, `PYTHONPATH` auf ihren `src`-Ordner setzen:

```powershell
cd reachy_interview_coach_v1
$env:PYTHONUTF8 = "1"; $env:PYTHONPATH = "$PWD\src"; python src/reachy_interview_coach/main.py
```
