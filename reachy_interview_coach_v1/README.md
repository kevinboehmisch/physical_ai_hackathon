---
title: Reachy Interview Coach
emoji: 🤖
colorFrom: purple
colorTo: gray
sdk: static
pinned: false
tags:
  - reachy_mini
  - reachy_mini_python_app
---

# Reachy Interview Coach

Bewerbungsgesprächs-Trainer für Software-Jobs auf dem Reachy Mini. Reachy führt ein Übungsinterview (Deutsch,
Zielrolle „Software Engineering Intern (Master), Google, Sommer 2027“), hört aktiv zu, wertet nur beobachtbares
Verhalten aus und gibt am Ende mündliches Kurzfeedback plus einen ausführlichen HTML-Bericht.

Fork der Reachy Mini Conversation App (Hugging Face Realtime Speech-to-Speech). Die ursprüngliche README liegt in
`README_OLD.md`.

## Ablauf

1. Begrüßung, Erklärung des Ablaufs, Frage nach Einwilligung zur Analyse.
2. Interview mit 5 Fragen: Vorstellung, 2 Verhaltensfragen, 2 leichte Fachfragen. Bei vagen Antworten genau eine Nachfrage.
3. Während der Antworten: Face-Tracking (Daemon), gelegentliches Nicken, kleine „attentive“-Emotionen.
4. Auswertung (~1 min) und Feedback: pro Kategorie eine Stärke und ein konkreter Tipp; Bericht unter `reports/`.

## Was ausgewertet wird

| Kategorie | Quelle | Kennzahlen |
| --- | --- | --- |
| Körpersprache | Reachy-Kamera → MediaPipe (Face + Pose Landmarker, lokal) | Blickkontakt-Anteil (Kopfpose + Iris), Lächeln, Kopfbewegung, Handaktivität, Schulterneigung, Haltung, auffällige Momente mit Zeitstempel |
| Sprache | Mikrofon → faster-whisper `small` (lokal, Wort-Zeitstempel) | Wörter/Minute, Füllwörter (äh/ähm/also/halt …), Pausen > 3 s, Antwortlänge |
| Inhalt | Transkript + Kennzahlen → Hugging Face Inference API | STAR-Struktur, Konkretheit, fachliche Richtigkeit, Stärke + Tipp |

Keine Emotions- oder Persönlichkeitsdiagnosen. Kategorien ohne Kennzahlen (z. B. ohne Kamera) werden im Feedback
weggelassen, auch wenn das Sprachmodell dazu etwas schreibt.

## Datenschutz

- Audio und Video werden nur im Arbeitsspeicher analysiert; es werden keine Audio- oder Videodateien gespeichert.
- Der Bericht enthält nur Kennzahlen und Transkript (`reports/`, in `.gitignore`).
- An das Sprachmodell für die Inhaltsanalyse gehen ausschließlich Transkript und Kennzahlen, niemals Bilder.
- Die Dialogführung selbst läuft über das Hugging Face Realtime-Backend (Sprache zu Sprache), wie in der Conversation App.

## Voraussetzungen

- Windows/PowerShell, Python 3.12, `reachy-mini` 1.11.0; Daemon läuft über die Reachy Mini Control App.
- Hugging Face Login (`hf auth login`) mit Zugriff auf die Inference API.
- MediaPipe-Modelle werden beim ersten Start nach `~/.cache/reachy_interview_coach/models/` geladen, Whisper nach dem
  Hugging Face Cache.

```powershell
pip install -e .
```

## Konfiguration (`.env`)

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `REALTIME_TRANSCRIPTION_LANGUAGE` | `de` | Sprache des Realtime-Backends |
| `INTERVIEW_LANGUAGE` | `de` | Interviewsprache (`de` oder `en`), wählt Fragenpool, Füllwortliste, Berichtssprache |
| `INTERVIEW_WHISPER_MODEL` | `small` | faster-whisper-Modell (CPU, int8) |
| `INTERVIEW_CONTENT_MODEL` | `Qwen/Qwen2.5-72B-Instruct` | Chat-Modell der Inhaltsanalyse über die HF Inference API |
| `INTERVIEW_REPORTS_DIR` | `<App>/reports` | Ablage der HTML-Berichte |
| `INTERVIEW_ARDUINO_PORT` | leer (Autoerkennung) | Serieller Port der optionalen RedBoard |

## Live-Test

Daemon in der Control App starten, dann im App-Ordner:

```powershell
$env:PYTHONUTF8 = "1"
python src/reachy_interview_coach/main.py
```

Im Log erscheinen `Tool call: interview_control action=…`, `Listening gesture: …` (Debug) und am Ende
`Report written to …`. Ohne Kamera (`--no-camera`) entfällt die Körpersprache-Kategorie.

## Optional: SparkFun RedBoard

Sketch: `arduino/interview_display/interview_display.ino` (16x2-LCD an D12/D11/D5/D4/D3/D2, LEDs grün/gelb/rot an
D8/D9/D10). Die App zeigt Fragenummer und Timer auf dem LCD und schaltet nach jeder Antwort die Ampel nach Sprechtempo
(grün 110–160 WPM). Ohne Board läuft alles unverändert; der Reachy-Mini-Lite-Port (`1a86:55d3`) wird bei der
Autoerkennung ausgeschlossen.

## Aufbau

```
src/reachy_interview_coach/
  interview/
    settings.py         .env → InterviewSettings
    questions.py        Fragenpool (de/en), Rollenbeschreibung
    session.py          Zustand: Einwilligung, Fragen, Äußerungen, Transkript, Events
    stream.py           LocalStream-Variante: Audio-Tee + Session-Observer
    audio_metrics.py    Aufnahme pro Frage (RAM) + faster-whisper-Kennzahlen
    video_metrics.py    MediaPipe-Analyse der Kameraframes (Thread)
    listening.py        Nicken/Emotions während der Antwort, Head-Tracking
    content_analysis.py HF Inference API (nur Text + Kennzahlen)
    report.py           HTML-Bericht (Jinja2)
    arduino.py          optionale Ampel/LCD
    coordinator.py      verbindet alles; evaluate() für das Tool
  tools/interview_control.py   Tool für das Realtime-LLM (Einwilligung, nächste Frage, Abschluss)
profiles/_reachy_interview_coach_locked_profile/profile.md   Interviewer-Prompt
```
