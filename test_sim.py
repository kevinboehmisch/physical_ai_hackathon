from reachy_mini import ReachyMini
import time

print("Starte Verbindung zur Simulation...")

# use_sim=True startet die Simulation
with ReachyMini(use_sim=True) as mini:
    print("Verbunden! Der Roboter bewegt jetzt kurz die Antennen.")
    
    # Antennen bewegen (Werte in Radiant)
    mini.goto_target(antennas=[0.5, -0.5], duration=1.0)
    time.sleep(1.0)
    
    # Zurück in die Ausgangsposition
    mini.goto_target(antennas=[0.0, 0.0], duration=1.0)
    time.sleep(1.0)

print("Fertig!")