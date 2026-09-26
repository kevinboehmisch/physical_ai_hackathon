# Plan: Reachy Interview Coach (Bewerbungsgesprächs-Trainer für Software-Jobs)

Status: **Umgesetzt am 2026-09-26 – alle Schritte aus 3.6 (inkl. optionalem Arduino) offline getestet; Live-Test am
Roboter steht aus (siehe README „Live-Test“).**

---

## 1. Mein Verständnis

Reachy Mini führt ein simuliertes Bewerbungsgespräch (4–5 Fragen) für eine Software-Zielrolle,
zeigt dabei aktives Zuhören (Face-Tracking, Nicken, Emotions-Moves) und wertet am Ende nur
**beobachtbares Verhalten** aus: Blickkontakt, Lächeln, Kopfbewegung, Gesten/Zappeln, Haltung
(Video), Sprechtempo, Füllwörter, Pausen, Antwortlänge (Audio) und Struktur/Konkretheit/
Fachlichkeit der Antworten (LLM, nur Text). Ergebnis: kurzes mündliches Feedback + HTML-Bericht.
Keine Emotions-/Persönlichkeitsdiagnosen, keine Video-/Audiodateien auf Platte, keine Bilder ans LLM.

Rahmen: Python-App aus dem Conversation-Template (reachy-mini 1.11.0), lokal ohne `--publish`,
Windows/PowerShell, Daemon über die Reachy Mini Control App. Optional Arduino (Ampel + 16x2-LCD),
App muss ohne Arduino laufen.

---

## 2. Was das Template bereits mitbringt (gelesen, nicht geraten)

| Baustein | Woher | Nutzung im Projekt |
|---|---|---|
| Speech-to-Speech-Dialog (STT + LLM + TTS + Tool-Calls) | Hugging-Face-Realtime-Backend (`huggingface_realtime.py`) | Interview-Dialog, Nachfragen, mündliches Feedback |
| Transkripte (User final, Assistant final) | `handler.set_transcript_observer(role, text, final)` | Gesprächsprotokoll, Antwortsegmente |
| Sprechaktivität | `handler.set_activity_observer(reason)`: `user_speech_started/stopped`, `assistant_audio_delta`, … | Zuhör-Verhalten triggern, Antwortzeiten stempeln |
| Mikrofon-Frames | `LocalStream.record_loop` → `media.get_audio_sample()` | Abzweig (Tee) in RAM-Ringpuffer für Whisper |
| Kamerabild | `reachy.media.get_frame()` (BGR-Array) | MediaPipe-Analyse + optional eigenes Face-Tracking |
| Bewegung | `MovementManager` (einziger `set_target`-Aufrufer, 60 Hz), `queue_move(Move)` | Nicken als eigener `Move`, Emotions über `EmotionQueueMove` |
| Face-Tracking | `movement_manager.set_head_tracking(True)` → daemon-seitig `start_head_tracking()` | Standard-Option (siehe Frage 5) |
| Emotions-Library | `RecordedMoves("pollen-robotics/reachy-mini-emotions-library")`, Tool `play_emotion` | `attentive1/2`, `understanding2`, `thoughtful1`, `yes1`, `welcoming2` … |
| Tools | `tools/<name>.py`, `Tool`-Subklasse, `async __call__(deps, **kwargs) -> dict` | Neues Tool `interview_control` |
| Profil | `profiles/_reachy_interview_coach_locked_profile/profile.md` (TOML-Header + Prompt) | Interviewer-Persona, Ablauf, Sprache, Rolle |

---

## 3. Technischer Ansatz

### 3.1 Modulstruktur (neu in `src/reachy_interview_coach/`)

```
interview/
  session.py           # Zustand: Einwilligung, Fragen (Nr, Typ, Text, t_start), Antworten (Transkript, t_start, t_end)
  audio_metrics.py     # RAM-Ringpuffer (float32) je Antwort, faster-whisper word_timestamps → WPM, Füllwörter, Pausen>3s, Dauer
  video_metrics.py     # Thread ~10 fps: MediaPipe FaceLandmarker (+Blendshapes, Kopf-Transform) + PoseLandmarker
                       #  → Blickkontakt-Anteil, Lächel-Anteil, Kopfbewegung, Handaktivität/Zappeln, Haltung; auffällige Zeitpunkte
  listening.py         # Zuhör-Verhalten: NodMove (eigener Move), gelegentliche Emotions während user_speech, Anker beim Sprechen
  content_analysis.py  # LLM-Auswertung nur mit Text+Kennzahlen → JSON (STAR je Verhaltensfrage, Konkretheit, fachliche Korrektheit, Stärke+Tipp je Kategorie)
  report.py            # Jinja2 → reports/interview_<YYYYMMDD_HHMM>.html (Kennzahlen, Zeitachse, Transkript, Feedback)
  arduino.py           # optional: pyserial, Ampel (WPM) + LCD (Fragen-Nr, Timer); No-op wenn kein Board
  questions.py         # Fragenpool je Rolle/Sprache (Vorstellung, 2 Verhaltensfragen, 1–2 Technikfragen)
tools/
  interview_control.py # LLM-Tool: consent_given | question_asked(number, kind, text) | finish_interview
```

Die restlichen Template-Dateien bleiben unverändert (Minimal-Diff-Regel aus dem Template-AGENTS.md).
Anpassungen nur in `main.py` (Verdrahtung), `console.py` (Audio-Tee, wenige Zeilen), `profile.md`, `pyproject.toml` (neue Abhängigkeiten), `.gitignore` (`reports/`).

### 3.2 Ablauf zur Laufzeit

1. **Start**: Roboter aufwachen (Template), Face-Tracking an, Video-Thread startet (nur Kennzahlen-Aggregation, kein Speichern).
2. **Begrüßung + Einwilligung**: Prompt lässt Reachy den Ablauf erklären und um Zustimmung bitten.
   Bei „Ja“ ruft das LLM `interview_control(action="consent_given")`; erst dann startet die Analyse-Erfassung.
   Bei „Nein“: Gespräch ohne Analyse (nur Übung), kein Bericht.
3. **Interview**: Bei jeder neuen Frage ruft das LLM `interview_control(action="question_asked", number, kind, text)`
   → Zeitstempel, LCD-Anzeige. Nachfragen bei vagen Antworten steuert der Prompt (STAR-Hinweis).
   Antwortsegmente werden über `user_speech_started/stopped` + finale User-Transkripte gebildet.
4. **Zuhören**: Während `user_speech_*`: Face-Tracking aktiv, alle 6–12 s ein kurzes Nicken (`NodMove`, Pitch ±6°, 0,8 s),
   gelegentlich `attentive1`/`understanding2`. Beim Sprechen von Reachy: Tracking pausiert (Template-Verhalten).
5. **Abschluss**: LLM ruft `interview_control(action="finish_interview")` →
   Whisper über alle Antwortpuffer, Video-Aggregation, Content-LLM → kompaktes Ergebnis-Dict zurück ans Realtime-Modell
   (mündliches Kurzfeedback: je Kategorie eine Stärke + ein Tipp) und HTML-Bericht schreiben; Pfad wird geloggt/gesagt.

### 3.3 Analyse-Details

- **Audio**: faster-whisper (CTranslate2, CPU-tauglich, Modell `small`, `word_timestamps=True`, Sprache fest).
  WPM = Wörter / Sprechdauer (ohne Pausen > 1 s). Füllwörter: DE `äh, ähm, hm, also, halt, quasi, sozusagen, irgendwie`;
  EN `um, uh, like, you know, basically, actually, kind of`. Pausen: Lücken > 3 s zwischen Wörtern (mit Zeitstempel).
  Puffer wird nach der Auswertung verworfen.
- **Video**: MediaPipe Tasks (`FaceLandmarker` mit `output_face_blendshapes` + `output_facial_transformation_matrixes`,
  `PoseLandmarker lite`). Blickkontakt: Kopf-Yaw/Pitch innerhalb ±15° **und** Iris-Offset klein → „Richtung Kamera“.
  Lächeln: Blendshapes `mouthSmileLeft/Right` > Schwelle. Kopfbewegung: Varianz der Kopfrotation. Zappeln: Handgelenks-
  Geschwindigkeit (Pose). Haltung: Schulterlinien-Neigung + Kopf-Schulter-Abstand relativ. Nur Anteile/Zähler + Zeitstempel
  auffälliger Momente (z. B. > 5 s ohne Blickkontakt) werden gehalten; kein Frame verlässt den Speicher.
- **Inhalt**: Ein LLM-Aufruf mit Transkript (Frage/Antwort-Paare) + Kennzahlen, strenges JSON-Schema. Nie Bilder.
- **Feedback**: konstruktiv, je Kategorie (Blick/Mimik, Körper, Sprache, Inhalt) eine Stärke + ein konkreter Tipp.

### 3.4 Datenschutz

- Alles lokal außer: (a) der Sprachdialog selbst über das HF-Realtime-Backend (siehe Frage 9) und
  (b) der eine Text-LLM-Aufruf für die Inhaltsanalyse (siehe Frage 4).
- Keine WAV/MP4 auf Platte. Bericht enthält Transkript + Kennzahlen. Einwilligung ist Voraussetzung für die Erfassung.

### 3.5 Neue Abhängigkeiten (werden erst nach Freigabe installiert)

`faster-whisper 1.2.1`, `mediapipe 1.0.1` (Modelle `face_landmarker.task`, `pose_landmarker_lite.task` werden beim
ersten Start heruntergeladen und lokal gecacht), `opencv-python` (Bildvorverarbeitung), `jinja2` (bereits vorhanden),
`pyserial` (bereits vorhanden, optional genutzt).

### 3.6 Umsetzungsreihenfolge (jeder Schritt einzeln testbar)

1. ✅ Interview-Schleife nur mit Sprache: Profil-Prompt, `questions.py`, `interview_control`-Tool, `session.py`. Test: Offline-Simulation der Tool-Calls bestanden; Gespräch am Roboter steht aus.
2. ✅ Audio-Analyse: `InterviewStream.record_loop` → `AnswerAudioRecorder`, `audio_metrics.py`. Test: SAPI-Testclip → Whisper `small` erkennt „Ähm“, 4-s-Pause und WPM; Unit-Test Füllwort-/Pausenlogik.
3. ✅ Video-Analyse: `video_metrics.py`. Test: Porträt-Testbild → Gesicht, Blickkontakt, Lächeln, Schultern 2°; Collector-Thread mit Fake-Kamera. Erkenntnis: Pose-`lite` jittert Handgelenke stark → `full`-Modell (~57 ms/Frame).
4. ✅ Zuhör-Verhalten: `listening.py` (NodMove, attentive/understanding-Emotions, Tracking an). Test: Fake-MovementManager, Zeitplan/Sperren geprüft; Feinabstimmung am Roboter offen.
5. ✅ Bericht: `content_analysis.py` (HF `InferenceClient`, JSON-Modus), `report.py` (Jinja2-HTML). Test: End-to-End offline inkl. echtem LLM-Aufruf; Kategorien ohne Kennzahlen werden verworfen.
6. ✅ Optional: `arduino.py` (Ampel + LCD, Port-Autoerkennung schließt Reachy Lite `1a86:55d3` aus), Sketch `arduino/interview_display/`. Test: Fake-Serial.

---

## 4. Risiken / Hinweise

- **Windows + App-Assistent**: `create` scheiterte zweimal (read-only Git-Dateien, cp1252). Scaffold wurde über dieselbe
  Assistent-Funktion mit `python -X utf8` und Read-only-Fix erzeugt; Details in `agents.local.md`.
- **CPU-Last**: MediaPipe + Whisper + Realtime-Audio gleichzeitig. Video auf ~10 fps begrenzen, Whisper erst am Ende laufen lassen.
- **Realtime-Transkript vs. Whisper**: Das HF-Backend liefert Transkripte ohne Wort-Zeitstempel → Whisper ist für WPM/Pausen nötig.
  Beide Transkripte können im Bericht abweichen; Bericht zeigt das Whisper-Transkript, Dialogführung nutzt das HF-Transkript.
- **Simulation** kann Kamera/Audio nicht liefern; Schritte 2–4 nur am echten Roboter testbar.
- **Wireless**: Kamera-Frames kommen dann per WebRTC zum Laptop (SDK wählt Backend automatisch); leichte Latenz/Qualitätsverlust.

---

## 5. Klärende Fragen (bitte ausfüllen)

Bei jeder Frage steht mein Vorschlag als Standard. Wer alles so will, schreibt einfach „Standard“ hinter jede Frage.

1. **Reachy-Version**: Lite (USB) oder Wireless?
   Antwort: **Lite**

2. **Gesprächssprache**: Deutsch oder Englisch? (Standard: Deutsch → `REALTIME_TRANSCRIPTION_LANGUAGE=de`, Whisper `de`, deutsche Füllwörter)
   Antwort: **Deutsch**

3. **Zielrolle** (steuert Fragenpool und Technikfragen): z. B. „Junior Java-Entwickler“ (Standard)
   Antwort: **Google „Software Engineering Intern, MS, Summer 2027“**
   (Quelle: careers.google.com, Job-ID 94172495052972742). Abgeleitetes Anforderungsprofil:
   - Master-Studium Informatik o. ä.; Programmierung in ≥ 2 Allzwecksprachen (C/C++/Java/JS/Python …), bevorzugt ≥ 3
   - Datenstrukturen & Algorithmen (aus Studium, Projekten oder Arbeit)
   - Bevorzugt: AI/ML, Infrastruktur, Webentwicklung, Unix/Linux, verteilte/parallele Systeme, Networking, Security
   - Aufgaben: Skripte zur Automatisierung, Probleme analysieren und Lösungen bewerten, CS-Wissen auf reale Probleme
     anwenden, Zusammenarbeit mit Peers/Managern/Teams
   - Hinweis: Google verlangt für die Rolle Englisch; das Training läuft wie gewünscht auf Deutsch, die Sprache bleibt
     per Konfiguration umschaltbar.

4. **LLM für die Inhaltsanalyse** (Text-only, ein Aufruf am Ende). Optionen:
   a) Hugging Face Inference API über den vorhandenen Login `PianZu` (z. B. `Qwen/Qwen2.5-72B-Instruct`), kein weiterer Key nötig **(Standard)**
   b) OpenAI API (eigener Key in `.env`)
   c) Lokal über Ollama (z. B. `qwen2.5:7b`, komplett offline, braucht Ollama-Installation)
   d) Das Realtime-Modell selbst (kein Extra-Aufruf, aber schwächere/unsichere JSON-Struktur)
   Antwort: **a) Hugging Face Inference API (Login PianZu)**

5. **Face-Tracking**: 
   a) Daemon-seitiges Tracking (`start_head_tracking`), wie im Template, robust, blendet sauber mit Moves **(Standard)**
   b) Eigene Schleife: MediaPipe-Gesichtsmitte → `look_at_image(u, v, perform_movement=False)` → Pose als Move in den
      `MovementManager` (nutzt `set_target` direkt, wie im Auftrag formuliert; mehr Code, mehr CPU)
   Antwort: **a) Daemon-seitig (start_head_tracking)**

6. **Whisper-Modell**: `small` (Standard, gute Balance auf CPU) oder `base` (schneller, ungenauer) / `medium` (langsamer). GPU (CUDA) vorhanden?
   Antwort: **Standard: `small`, CPU (int8)**

7. **Berichtsablage**: `reachy_interview_coach/reports/` (Standard, in `.gitignore`) oder anderer Ordner?
   Antwort: **Standard**

8. **Arduino (optional)**: Ist die SparkFun RedBoard vor Ort? Welcher COM-Port? LCD 16x2 per I2C (PCF8574) oder parallel (4-Bit)?
   Standard: erst umsetzen, wenn 1–5 laufen; Auto-Erkennung des Ports, App läuft ohne Board.
   Antwort: **Standard (erst nach Schritt 5, Port-Autoerkennung, LCD-Variante offen)**

9. **Datenschutz-Hinweis zum Sprachdialog**: Im Standardmodus `deployed` streamt die Conversation-App das Mikrofon-Audio
   zum Hugging-Face-Realtime-Server (das ist die Sprachpipeline selbst, nicht die Analyse). Alternative: eigenes
   `speech-to-speech`-Backend lokal (`HF_REALTIME_CONNECTION_MODE=local`), deutlich mehr Setup/Hardware.
   Ist `deployed` für den Hackathon in Ordnung? (Standard: ja; im Bericht/Begrüßung wird das transparent gesagt)
   Antwort: **Ja, deployed**

10. **Fragenpool**: Feste Fragen je Rolle in `questions.py`, das LLM formuliert sie natürlich aus und stellt Nachfragen
    (Standard, deterministische Anzahl) – oder das LLM soll die Fragen frei erfinden?
    Antwort: **Standard (fester Pool)**

11. **Stimme**: Template-Standard „Aiden“ oder eine andere aus `Aiden, Ryan, Dylan, Eric, Ono_Anna, Serena, Sohee, Uncle_Fu, Vivian`?
    Antwort: **Standard (Aiden)**
