# physical_ai_hackathon


## Setup & Installation (Windows)

Navigiere in deinen Projektordner und führe die folgenden Befehle in der PowerShell aus:

### 1. Virtuelle Umgebung erstellen und aktivieren
```powershell
python -m venv venv
.\venv\Scripts\activate

```

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

### Terminal 2: Eigenen Python-Code ausführen

Öffne ein neues Terminal im selben Projektordner, um deine Skripte gegen die laufende Simulation auszuführen:

```powershell
.\venv\Scripts\activate
python test_sim.py
```
