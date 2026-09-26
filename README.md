# physical_ai_hackathon

# Links
position: https://www.google.com/about/careers/applications/jobs/results/94172495052972742-software-engineering-intern-ms-summer-2027?ca 
  tegory=DATA_CENTER_OPERATIONS&category=DEVELOPER_RELATIONS&category=HARDWARE_ENGINEERING&category=INFORMATION_TECHNOLOGY&category=MANUFACTURING_SUPPLY_CHAIN&category=NETWORK_ENGINEERING&cat 
  egory=PRODUCT_MANAGEMENT&category=PROGRAM_MANAGEMENT&category=SOFTWARE_ENGINEERING&category=TECHNICAL_INFRASTRUCTURE_ENGINEERING&category=TECHNICAL_SOLUTIONS&category=TECHNICAL_WRITING&cate 
  gory=USER_EXPERIENCE&jex=ENTRY_LEVEL&target_level=INTERN_AND_APPRENTICE&page=2 

  Google interview Structure:
  -  https://igotanoffer.com/blogs/tech/google-behavioral-interview
  -  https://www.tryexponent.com/guides/google-software-engineer-intern-interview

=> one behavioral interview and one technical (leetcode with blanc document)

------

## Setup & Installation (Windows)

Navigiere in deinen Projektordner und führe die folgenden Befehle in der PowerShell aus:

### 1. Virtuelle Umgebung erstellen und aktivieren
```powershell
python -m venv venv
.\venv\Scripts\activate
```

> Falls PowerShell das Aktivieren blockiert (`running scripts is disabled`), einmalig ausführen:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 2. Reachy Mini inklusive Simulation installieren

```powershell
python -m pip install "reachy-mini[mujoco]"
```

## Simulation starten & testen

Für die Ausführung der Simulation werden **zwei getrennte Terminal-Fenster** benötigt:

### Terminal 1: Simulations-Daemon starten

Starte den Hintergrunddienst, der den 3D-Roboter lädt. Das Fenster muss während der gesamten Entwicklung geöffnet bleiben:

```powershell
.\venv\Scripts\activate
reachy-mini-daemon --sim
```

Der Daemon läuft dann auf `localhost:8000`. Zeilen wie `GET /api/daemon/status ... 200` im Log sind normal.

> **Wichtig:** Immer nur **einen** Daemon gleichzeitig laufen lassen – entweder `reachy-mini-daemon --sim` **oder** die Reachy Mini Desktop-App, nicht beides (beide nutzen Port 8000).

### Terminal 2: Test-Skript ausführen

Öffne ein neues Terminal im selben Projektordner und führe das Test-Skript gegen die laufende Simulation aus:

```powershell
.\venv\Scripts\activate
python mini_test.py
```

Das Skript weckt den Roboter auf, bewegt die Antennen und legt ihn wieder schlafen. Die Bewegung siehst du im 3D-Fenster der Simulation. Erwartete Ausgabe:

```
Connected, waking up...
Moving antennas...
Antenna positions: [0.80..., -0.80...]
Going to sleep...
Done!
```

Meldungen wie `Audio system is not initialized.` sind in der Simulation harmlos (es gibt keine Kamera/Audio-Hardware).

## Eigenen Code schreiben

Verbindung zur lokalen Simulation aufbauen:

```python
from reachy_mini import ReachyMini

with ReachyMini(host='localhost', connection_mode='localhost_only', media_backend='no_media') as robot:
    robot.wake_up()
    robot.goto_target(antennas=[0.8, -0.8], duration=1.0)  # Werte in Radiant
    robot.goto_sleep()
```

Hinweise:
- `ReachyMini('localhost')` funktioniert **nicht** – der erste Parameter ist der Robotername, nicht der Host. Immer `host='localhost'` angeben.
- Winkel werden in **Radiant** angegeben (0.8 rad ≈ 45°).
- Für den echten Roboter später keinen Sim-Daemon starten und `ReachyMini()` ohne `host`/`connection_mode` verwenden – dann wird der Roboter unter `reachy-mini.local` im Netzwerk gesucht (und `media_backend='no_media'` weglassen, wenn Kamera/Audio gebraucht werden).
