"""
Pick & Place Skript für igus ReBeL 6DOF
Steuerung via CRI-Protokoll (Python → iRC → Roboter)
Koordinaten vom EYE+ System (aktuell: zufällig generiert)
4 feste Ablagepositionen, 50mm Abstand voneinander

Voraussetzungen:
    pip install git+https://github.com/CommonplaceRobotics/CRI-Python-Lib
"""

import logging
import random
from ultragay.CRI_Python_Lib.cri_lib import CRIController, CRIConnectionError

logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s: %(message)s")
# ─────────────────────────────────────────────────────────────────────────────
# KONFIGURATION – hier deine Werte anpassen
# ─────────────────────────────────────────────────────────────────────────────

IRC_HOST = "127.0.0.1"   # Simulation: 127.0.0.1 | echter Roboter: 192.168.3.11
IRC_PORT = 3921           # Simulation: 3921      | echter Roboter: 3920

# Z-Höhen in mm (in iRC per Jog-Tab ausmessen!)
Z_HOVER  = 200   # sichere Fahrhöhe über allem
Z_PICK   = 170    # Höhe zum Greifen auf dem Asycube
Z_PLACE  = 100    # Höhe zum Ablegen in der Vorrichtung

SPEED    =  100    # Geschwindigkeit in % (für erste Tests niedrig lassen!)

# TCP-Orientierung beim Greifen/Ablegen (A=Rx, B=Ry, C=Rz in Grad)
# → in iRC prüfen ob Greifer senkrecht nach unten zeigt
PICK_A,  PICK_B,  PICK_C  = 0, 89, 0
PLACE_A, PLACE_B, PLACE_C = 0, 90, 88

# Bereitschaftsposition in Gelenkwinkeln (Grad) – Greifer zeigt schräg nach vorne-unten
# → in iRC per Jog-Tab eine sinnvolle Startpose anfahren und die Winkel hier eintragen!
READY_JOINTS = (-5, -52.5, 122.9, 0, 19.6, 0)   # A1..A6 (igus ReBeL Richtwert – anpassen!)

# Sichere Zwischenposition: A2–A6 eingezogen (Arm nahe Robotermitte)
# Bewegungsablauf beim Seitenwechsel:
#   1. A2–A6 → SAFE_A2_TO_A6  (Arm einziehen, A1 bleibt)
#   2. A1    → Zielseite       (Rotation um Hochachse)
# → in iRC per Jog-Tab ausmessen und eintragen!
SAFE_A1_PICK  = -5
SAFE_A1_PLACE = -70
SAFE_A2_TO_A6 = (-52.5, 122.9, 0, 19.6, 0)

# Hover-Position über dem Asycube als Gelenkwinkel (A1..A6)
# → in iRC anfahren: Greifer horizontal über Asycube-Mitte, Z=Z_HOVER
# → Gelenkwinkel aus iRC ablesen und eintragen!
PICK_HOVER_JOINTS = (-6.4, 32.8, 114.7, -2.4, -56.7, 0.6)   # ANPASSEN!

# Ablage-Positionen als Gelenkwinkel (A1..A6) – je eine pro Ablageposition
# → jede Position in iRC manuell anfahren (Greifer auf Ablageposition, Z=Z_PLACE)
# → Gelenkwinkel ablesen und eintragen!
PLACE_JOINTS = [
    (-52.5, 58.3, 100.3, 37.4, -72.7, -12.9),   # Position 1 – ANPASSEN! X/Y/Z: 200/-490/100
    (-46, 61.5, 91.7, 45.3, -70.4, -18.8),   # Position 2 – ANPASSEN! X/Y/Z: 250/-490/100
    (-40.6, 65.8, 81.1, 52.4, -68.3, -25.7),   # Position 3 – ANPASSEN! X/Y/Z: 300/-490/100
    (-36.2, 71.6, 68.1, 59.1, -66.4, -33.8),   # Position 4 – ANPASSEN! X/Y/Z: 350/-490/100
]

# Hover-Positionen über jeder Ablageposition als Gelenkwinkel (A1..A6)
# → gleiche X,Y wie PLACE_JOINTS aber höhere Z → Gelenkwinkel ablesen!
PLACE_HOVER_JOINTS = [
    (-52.5, 36.5, 108.6, 41, -62.3, -22),   # Hover über P1 – ANPASSEN! X/Y/Z: 200/-490/200
    (-46, 41.3, 99.8, 49.2, -62.2, -28.4),   # Hover über P2 – ANPASSEN! X/Y/Z: 250/-490/200
    (-40.6, 47.1, 89.2, 56.4, -62.1, -35.2),   # Hover über P3 – ANPASSEN! X/Y/Z: 300/-490/200
    (-36.2, 53.9, 76.6, 63, -61.9, -42.7),   # Hover über P4 – ANPASSEN! X/Y/Z: 350/-490/200
]

# Arbeitsbereich des Asycube 240 in mm
# → an deinen tatsächlichen Aufbau anpassen
ASYCUBE_X_MIN = 450
ASYCUBE_X_MAX = 610
ASYCUBE_Y_MIN =  -150
ASYCUBE_Y_MAX =  50

# Kartesischer Arbeitsraum des Roboters in mm – HARD LIMITS
# → in iRC per Jog-Tab den tatsächlichen erreichbaren Bereich ausmessen!
WORKSPACE = {
    "X": (-600, 650),
    "Y": (-600, 200),
    "Z": (  0,  500),
}


# ─────────────────────────────────────────────────────────────────────────────
# HILFSFUNKTIONEN
# ─────────────────────────────────────────────────────────────────────────────

def check_cartesian_limits(x, y, z, label=""):
    """Wirft ValueError wenn X/Y/Z außerhalb des definierten Arbeitsraums liegt."""
    violations = []
    for axis, value in (("X", x), ("Y", y), ("Z", z)):
        lo, hi = WORKSPACE[axis]
        if not (lo <= value <= hi):
            violations.append(f"  {axis}={value:.1f} außerhalb [{lo}, {hi}]")
    if violations:
        raise ValueError(
            f"Achsgrenze überschritten bei '{label}':\n" + "\n".join(violations)
        )



def get_pick_coordinates():
    """
    Gibt (x, y, theta) zurück – Position und Orientierung des Teils in Grad.
    theta wird auf PICK_C addiert, sodass der Greifer das Teil korrekt ausgerichtet greift.

    Später ersetzen durch echte TCP/IP-Abfrage an EYE+:

        eye_socket.send(b"GET_PICKPOINT\\n")
        response = eye_socket.recv(1024).decode()
        x, y, theta = parse_eye_response(response)
        return x, y, theta
    """
    x = round(random.uniform(ASYCUBE_X_MIN, ASYCUBE_X_MAX), 1)
    y = round(random.uniform(ASYCUBE_Y_MIN, ASYCUBE_Y_MAX), 1)
    theta = 0.0   # Platzhalter – später vom EYE+ geliefert (Grad, z.B. -90..90)
    print(f"  [EYE+] Pick-Koordinaten: X={x}, Y={y}, Theta={theta}°")
    return x, y, theta


def move(robot, x, y, z, a, b, c, label=""):
    """
    Fährt kartesisch zu einer Position und wartet bis die Bewegung fertig ist.
    Prüft Ziel-XYZ vor der Bewegung und Gelenkwinkel danach (IK-Ergebnis unbekannt vorher).
    """
    check_cartesian_limits(x, y, z, label)
    print(f"  → {label:25s}  X={x:7.1f}  Y={y:7.1f}  Z={z:7.1f}")
    ok = robot.move_cartesian(
        X=x, Y=y, Z=z,
        A=a, B=b, C=c,
        E1=0.0, E2=0.0, E3=0.0,
        velocity=SPEED,
        wait_move_finished=True
    )
    if not ok:
        raise RuntimeError(f"Bewegung fehlgeschlagen bei: {label}")


def move_safe(robot, from_a1, to_a1):
    """
    Sicherer Seitenwechsel in zwei Schritten:
      1. A2–A6 einziehen (Arm zur Robotermitte), A1 bleibt auf from_a1
      2. A1 auf to_a1 drehen (Rotation um Hochachse ohne Hindernis)
    """
    a2, a3, a4, a5, a6 = SAFE_A2_TO_A6

    print(f"  → {'Arm einziehen':25s}  A1={from_a1}°")
    ok = robot.move_joints(
        A1=from_a1, A2=a2, A3=a3, A4=a4, A5=a5, A6=a6,
        E1=0.0, E2=0.0, E3=0.0,
        velocity=SPEED,
        wait_move_finished=True
    )
    if not ok:
        raise RuntimeError("Arm einziehen fehlgeschlagen")

    print(f"  → {'A1 drehen':25s}  A1={from_a1}° → {to_a1}°")
    ok = robot.move_joints(
        A1=to_a1, A2=a2, A3=a3, A4=a4, A5=a5, A6=a6,
        E1=0.0, E2=0.0, E3=0.0,
        velocity=SPEED,
        wait_move_finished=True
    )
    if not ok:
        raise RuntimeError("A1-Rotation fehlgeschlagen")


# ─────────────────────────────────────────────────────────────────────────────
# PICK & PLACE ZYKLUS
# ─────────────────────────────────────────────────────────────────────────────

def move_joints_labeled(robot, joints, label):
    """Fährt eine bekannte Gelenkwinkel-Position an."""
    a1, a2, a3, a4, a5, a6 = joints
    print(f"  → {label:25s}  A1={a1} A2={a2} A3={a3} A4={a4} A5={a5} A6={a6}")
    ok = robot.move_joints(
        A1=a1, A2=a2, A3=a3, A4=a4, A5=a5, A6=a6,
        E1=0.0, E2=0.0, E3=0.0,
        velocity=SPEED,
        wait_move_finished=True
    )
    if not ok:
        raise RuntimeError(f"Gelenkbewegung fehlgeschlagen: {label}")


def pick_and_place_cycle(robot, pick_x, pick_y, pick_theta, place_index, cycle_nr, place_nr, skip_initial_safe=False):
    """
    Feste Positionen (Hover/Place) werden per Gelenkwinkel angefahren → kein IK-Solver,
    keine Singularitäten. Nur der variable Pick-Punkt vom EYE+ bleibt kartesisch.

    pick_theta: Orientierung des Teils (vom EYE+), wird auf PICK_C addiert.
    place_index: Index in PLACE_JOINTS / PLACE_HOVER_JOINTS (0–3).
    """
    pick_c = PICK_C + pick_theta
    print(f"\n  Zyklus {cycle_nr} | Ablageposition {place_nr} | Greiferwinkel C={pick_c:.1f}°")

    # 1. Arm einziehen → A1 zur Pick-Seite drehen
    if not skip_initial_safe:
        move_safe(robot, from_a1=SAFE_A1_PLACE, to_a1=SAFE_A1_PICK)

    # 2. Hover über Pick (Gelenkwinkel – bekannte sichere Pose)
    move_joints_labeled(robot, PICK_HOVER_JOINTS, "Hover über Pick")

    # 3. Runter zum Greifen (kartesisch – X,Y vom EYE+, Z_PICK fix)
    move(robot, pick_x, pick_y, Z_PICK,
         PICK_A, PICK_B, pick_c, "Pick (greifen)")

    # → Greifer schließen:
    robot.set_active_control(True)
    robot.set_dout(30, False)
    import time; time.sleep(0.5)
    

    # 4. Zurück zur Hover-Pose über Pick
    move_joints_labeled(robot, PICK_HOVER_JOINTS, "Hoch nach Pick")

    # 5. Arm einziehen → A1 zur Place-Seite drehen
    move_safe(robot, from_a1=SAFE_A1_PICK, to_a1=SAFE_A1_PLACE)

    # 6. Hover über Ablageposition (Gelenkwinkel – kein IK!)
    move_joints_labeled(robot, PLACE_HOVER_JOINTS[place_index], "Hover über Place")

    # 7. Ablegen (Gelenkwinkel – kein IK!)
    move_joints_labeled(robot, PLACE_JOINTS[place_index], "Place (ablegen)")

    # → Greifer öffnen:
    robot.set_active_control(True)
    robot.set_dout(30, True)
    import time; time.sleep(0.5)
    

    # 8. Zurück zur Hover-Pose über Place
    move_joints_labeled(robot, PLACE_HOVER_JOINTS[place_index], "Hoch nach Place")

    print(f"  ✓ Zyklus {cycle_nr} abgeschlossen")


# ─────────────────────────────────────────────────────────────────────────────
# HAUPTPROGRAMM
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  igus ReBeL Pick & Place")
    print("=" * 60)

    robot = CRIController()

    print(f"\nVerbinde mit iRC auf {IRC_HOST}:{IRC_PORT} ...")
    try:
        robot.connect(host=IRC_HOST, port=IRC_PORT)
    except CRIConnectionError:
        print("FEHLER: Verbindung fehlgeschlagen!")
        print("→ Ist iRC geöffnet und der Roboter aktiviert?")
        return

    print("✓ Verbunden")

    print("Warte auf Kinematik ...")
    if not robot.wait_for_kinematics_ready(timeout=30):
        print("FEHLER: Kinematik nicht bereit!")
        robot.close()
        return

    print("Aktiviere Steuerung ...")
    if not robot.set_active_control(True):
        print("FEHLER: Active Control konnte nicht gesetzt werden!")
        robot.close()
        return

    print("Setze Controller zurück ...")
    robot.reset()

    print("Aktiviere Motoren ...")
    if not robot.enable():
        print("FEHLER: Enable fehlgeschlagen!")
        robot.close()
        return

    print("✓ Roboter bereit")

    # print("Referenziere Achsen ...")
    # robot.reference_all_joints()
    # print("✓ Referenziert\n")

    print("Fahre Bereitschaftsposition an ...")
    a1, a2, a3, a4, a5, a6 = READY_JOINTS
    ok = robot.move_joints(
        A1=a1, A2=a2, A3=a3, A4=a4, A5=a5, A6=a6,
        E1=0.0, E2=0.0, E3=0.0,
        velocity=SPEED,
        wait_move_finished=True
    )
    if not ok:
        print("FEHLER: Bereitschaftsposition nicht erreichbar – READY_JOINTS anpassen!")
        robot.disable()
        robot.set_active_control(False)
        robot.close()
        return
    print("✓ Bereitschaftsposition erreicht\n")

    cycle = 0

    def go_ready():
        print("Fahre Bereitschaftsposition an ...")
        a1, a2, a3, a4, a5, a6 = READY_JOINTS
        robot.move_joints(
            A1=a1, A2=a2, A3=a3, A4=a4, A5=a5, A6=a6,
            E1=0.0, E2=0.0, E3=0.0,
            velocity=SPEED,
            wait_move_finished=True
        )
        print("✓ Bereitschaftsposition erreicht")

    try:
        print("\n" + "─" * 60)
        print("  Starte Durchlauf durch alle 4 Ablagepositionen")
        print("─" * 60)

        for place_index in range(len(PLACE_JOINTS)):
            cycle += 1

            pick_x, pick_y, pick_theta = get_pick_coordinates()

            pick_and_place_cycle(
                robot,
                pick_x, pick_y, pick_theta,
                place_index,
                cycle_nr=cycle,
                place_nr=place_index + 1,
                skip_initial_safe=(place_index == 0)
            )
        move_safe(robot, from_a1=SAFE_A1_PLACE, to_a1=SAFE_A1_PICK)
        print("\n✓ Alle 4 Positionen belegt.")
        go_ready()

    except KeyboardInterrupt:
        print("\n\nStopp durch Benutzer (Ctrl+C).")
        go_ready()

    except (RuntimeError, ValueError) as e:
        print(f"\nFEHLER: {e}")

    finally:
        robot.disable()
        robot.set_active_control(False)
        robot.close()
        print("Verbindung getrennt. Auf Wiedersehen!")


if __name__ == "__main__":
    main()