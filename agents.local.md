# Reachy Mini Local Configuration

## Setup Status
Setup complete: YES (2026-09-26)

## User Environment
- Robot type: Lite (USB; Motorbus meldet sich als USB-Serial `1a86:55d3`, nie von anderen
  Tools öffnen)
- OS: Windows 10/11 (win32 10.0.26200)
- Shell: PowerShell
- Python: 3.12.10, **global** (kein venv aktiv; `python`/`pip` zeigen auf
  `C:\Users\Christian Luan\AppData\Local\Programs\Python\Python312`)
- Python env tool: pip (global)
- reachy-mini: 1.11.0 (+ reachy_mini_motor_controller 1.5.6, rust_kinematics 1.0.3)
- Daemon: läuft über die Reachy Mini Control App auf `localhost:8000`
  (nie gleichzeitig `reachy-mini-daemon --sim` starten, gleicher Port)
- Hugging Face: eingeloggt als `PianZu` (`hf auth whoami`)
- Resources path: `C:\Users\Christian Luan\reachy_mini_resources\`
  - `reachy_mini/` (SDK-Quelle + docs + skills, shallow clone)
  - `reachy_mini_conversation_app/` (Referenz für Conversation-Template, shallow clone)

## Projekt
- Workspace: `C:\Users\Christian Luan\Documents\projects\physical_ai_hackathon` (Git-Repo)
- App: `reachy_interview_coach/` (Conversation-Template, lokal, ohne --publish)
  - Paket: `src/reachy_interview_coach/`, Klasse `ReachyInterviewCoach`
  - Locked Profile: `profiles/_reachy_interview_coach_locked_profile/profile.md`
  - Installiert mit `pip install -e .` (zieht openai 2.28.0, mcp, reachy_mini_dances_library)
  - Das vom Assistenten erzeugte leere `.git` im App-Ordner wurde entfernt, damit die App
    Teil des Hackathon-Repos ist.
- Sprache der Antworten an den Nutzer: laut User-Regel Chinesisch (vereinfacht); die
  Projektdateien (plan.md, README, Profil) sind auf Deutsch, die Interviewsprache ist Deutsch.
- Stand 2026-09-26: Schritte 1–6 aus plan.md 3.6 implementiert und offline getestet
  (Fake-Kamera/-MovementManager/-Serial, echter Whisper- und HF-Inference-Aufruf).
  Live-Test am Roboter steht aus. Start: `$env:PYTHONUTF8=1; python src/reachy_interview_coach/main.py`.
- Analyse-Entscheidungen: MediaPipe Pose `full` statt `lite` (lite jittert Handgelenke um mehrere cm
  bei identischen Frames); Modelle in `~/.cache/reachy_interview_coach/models/`; Whisper `small` int8
  wird bei `coordinator.start()` vorgeladen; LLM-Kategorien ohne Kennzahlen
  werden in `content_analysis.py` verworfen, weil das Modell sonst Körpersprache erfindet.
- Auswertungs-Ablauf (nach Live-Tests 2026-09-26): Tools dürfen NIE lange blockieren – solange ein
  function_call_output aussteht, antwortet das HF-Realtime-Backend dem User mit
  „Cannot generate a response while function call outputs are pending". Deshalb: Coordinator-Executor
  (1 Worker) lädt Whisper vor, transkribiert Antwort N-1 sobald Frage N gestellt ist
  (`session.subscribe`), `no_more_questions`/`finish_interview` starten `begin_evaluation()` und kehren
  sofort zurück (`evaluation_running`); das fertige Ergebnis wird per `coordinator.on_result` →
  `InterviewStream.announce()` → `handler.say()` (run_coroutine_threadsafe) als User-Nachricht
  „[System message …]" ins Gespräch geschoben; späteres `finish_interview` liefert `already_presented`.
  Frühere Live-Probleme: Modell rief `finish_interview` nie auf / behauptete keine Kameradaten →
  Tool-Beschreibung + Profilregel. Dritte im Raum werden vom VAD als User transkribiert → ruhiger Raum.
  Reports: `load_interview_settings()` ohne instance_path → `<App>/reports`.

- `reachy_interview_coach_v1/` (2026-09-26 16:25): vom User gewünschte Kopie des Stands vor der
  Hintergrund-Auswertung (siehe dortige `VERSION_NOTE.md`); erzeugt durch Rückgängigmachen der
  Transkript-Edits ab Zeile 196. Läuft nur mit `PYTHONPATH=<v1>/src`, da das Editable-Install auf
  `reachy_interview_coach/` zeigt. Nicht mitpflegen, wenn nicht ausdrücklich verlangt.

## Notes for Future Sessions
- `reachy-mini-app-assistant create --template conversation` schlägt unter Windows fehl:
  1) `shutil.rmtree` auf read-only Git-Pack-Dateien (PermissionError),
  2) `Path.read_text()` ohne Encoding -> cp1252 UnicodeDecodeError.
  Workaround, der funktioniert hat: `create_from_conversation_app()` aus einem Wegwerf-Skript mit
  `python -X utf8` aufrufen und `shutil.rmtree` mit einem `onexc`-Handler versehen, der
  `os.chmod(path, stat.S_IWRITE)` setzt. Upstream-Bug wert zu melden.
- `reachy-mini-app-assistant check .` baut ein Temp-venv und installiert die App komplett neu:
  dauert ~5 Minuten, kein Hänger. Unter Windows **`$env:PYTHONUTF8=1` setzen**, sonst bricht
  Rich beim Spinner mit cp1252-UnicodeEncodeError ab. Mit UTF-8: alle Checks bestanden (2026-09-26).
- Generell für Python-Tools im Projekt in PowerShell: `$env:PYTHONUTF8=1` setzen.
- SDK 1.11.0 API-Fakten (aus installiertem Paket gelesen, nicht geraten):
  - Kamera: `reachy.media.get_frame()` -> BGR `np.ndarray (H, W, 3)` oder `None`
  - Mikro: `reachy.media.start_recording()`, `get_audio_sample()` (float32), `get_input_audio_samplerate()`
  - Lautsprecher: `media.start_playing()`, `push_audio_sample()`, `play_sound(path)`
  - Face-Tracking daemon-seitig: `reachy.start_head_tracking(weight)`, `stop_head_tracking()`,
    `get_tracked_face(wait=False).detected`
  - `look_at_image(u, v, duration=0, perform_movement=False)` liefert Kopfpose aus Pixelkoordinate
    (braucht Kamera-Kalibrierung `media.camera.K/D` vom Daemon)
  - Emotions: `RecordedMoves("pollen-robotics/reachy-mini-emotions-library")`, `.get(name)`, `.list_moves()`
  - `release_media()` gibt Kamera/Mikro für direkten OpenCV/sounddevice-Zugriff frei (hier nicht nötig)
- Conversation-App (Template) Architektur:
  - Backend: nur Hugging Face Realtime (Speech-to-Speech, OpenAI-Realtime-kompatibel),
    `HF_REALTIME_CONNECTION_MODE=deployed|local`, `REALTIME_TRANSCRIPTION_LANGUAGE=de`
  - `MovementManager` (moves.py) ist der EINZIGE `set_target`-Aufrufer (60 Hz); Moves über
    `queue_move(Move)`, Face-Tracking über `set_head_tracking(bool)` -> daemon-seitig
  - Hooks: `handler.set_transcript_observer((role, text, final))`,
    `handler.set_activity_observer(reason)` mit `user_speech_started/stopped`,
    `user_transcription_completed`, `assistant_audio_delta`, `assistant_transcript_done`
  - Mic-Audio fließt in `LocalStream.record_loop` (console.py) -> `handler.receive()`
  - Tools: `tools/<name>.py`, Klasse erbt `Tool`, `name/description/parameters_schema`,
    `async __call__(deps, **kwargs) -> dict`, Fehler als `{"error": ...}`
  - Profil-Tools in `profile.md` (`default_tools = [...]`), Prompt = Markdown-Body
- Installierte Analyse-Pakete (global, Py3.12/Win): mediapipe 1.0.1, faster-whisper 1.2.1,
  opencv-python 5.0.0, jinja2 3.1.6, pyserial 3.5, huggingface_hub 1.33.0 (Chat-Completion mit
  `response_format={"type": "json_object"}` funktioniert über `router.huggingface.co`).
- **Daemon-Verbindung unter Windows**: `localhost` löst zuerst zu `::1` auf, die Verbindung zu
  `[::1]:8000` hängt bis zum Timeout (kein Refuse), der Daemon lauscht nur auf `127.0.0.1`.
  Das SDK verwendet fest "localhost" (`_connect_single(host="localhost")`), daher
  `ConnectionError: Could not connect to daemon on localhost`. Fix in der App:
  `prefer_ipv4_for_localhost()` in `main.py` (getaddrinfo-Wrapper, IPv4 zuerst). Für eigene
  Testskripte denselben Wrapper vorschalten oder `ReachyMini(host="127.0.0.1", connection_mode="network")`
  vermeiden (network erzwingt WebRTC-Media). HTTP-Status: `http://127.0.0.1:8000/api/daemon/status`.
- IDE-Browser kann keine `file://`-URLs öffnen; HTML-Berichte zum Ansehen kurz per
  `python -m http.server` bereitstellen und den Server danach beenden.
- Simulation (`--sim`) kann Kamera/Audio nicht testen; Analyse nur am echten Roboter prüfbar.
