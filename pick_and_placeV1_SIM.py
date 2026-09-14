#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 SIMULATION:  Pick-and-Place  igus ReBeL 6-DOF  +  Asyril EYE+ (simuliert)
================================================================================

Diese Variante ist zum Testen OHNE Labor-Hardware gedacht:

  * ASYRIL EYE+  ->  wird durch INTERAKTIVE KONSOLEN-EINGABE ersetzt.
        Du wirst nach den Koordinaten gefragt und gibst sie ein:
              x y rz     (z.B.  "12.5 -6.8 45")
        Druckst du nur ENTER (leere Eingabe), bedeutet das
        "KEIN TEIL GEFUNDEN" -> das Skript verhaelt sich exakt so wie
        beim echten System: es loest das Fuell-Verhalten aus bzw. wartet
        weiter auf ein Teil.

  * IGUS ROBOTER ->  verbindet sich mit dem iRC-Simulator (Desktop-Software)
        auf 127.0.0.1:3921 und fuehrt die Bewegungen dort aus.
        Voraussetzung: iRC laeuft, Projekt geladen, "Aktivieren" gedrueckt.
        Robotersteuerung erfolgt ueber die CRI-Python-Lib (identisch zur
        echten Produktiv-Version).

Unterschiede zur Produktiv-Version:
  - Roboter-IP:  127.0.0.1 / Port 3921   (iRC-Simulation)
                 statt 192.168.3.11 / 3920 (echte Steuerung)
  - keine Verbindung zu Asyril-Komponenten
  - Eye+ Antworten kommen von dir ueber die Tastatur

Der gesamte Ablauf (Reihenfolge, Safe-Positionen, Rotation, Pipelining-
Logik, Fuell-Entscheidung, Wartelogik vor dem naechsten Bild) ist identisch
zur echten Version -- nur die Datenquelle ist simuliert.
================================================================================
"""

import logging
import time
import threading

from libs.CRI_Python_Lib.cri_lib import CRIController, CRIConnectionError

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")

# ------------------------------------------------------------------------------
#  KONFIGURATION
# ------------------------------------------------------------------------------

ROBOT_IP   = "127.0.0.1"           # iRC-Simulation (statt 192.168.3.11)
ROBOT_PORT = 3921                  # iRC-Sim-Port    (statt 3920)

NUM_PARTS    = 4                   # <<< Anzahl zu holender Teile (frei aenderbar)

# Produktionsbetrieb -> immer Rezept_Produktion.
RECIPE_ID_PROD = "23217"           # Rezept_Produktion

PICK_CENTER_X = 440.0               # X-Koordinate des Pick-Bereichs (Mitte) - muss zum iRC-Projekt passen
PICK_CENTER_Y = -5.0                # Y-Koordinate des Pick-Bereichs (Mitte) - muss zum iRC-Projekt passen
SAFE_PICK_Z   = 150.0
GRIP_Z        = 140.0

TOOL_A_DOWN   = 180.0
TOOL_B_DOWN   = 0.0
TOOL_C_DOWN   = 180.0

SAFE_ROTATE_JOINTS = [0.0, -18.7, 108.0, 0.0, 90.0, 0.0]
ROTATE_DEG    = -90.0

PLACE_X_START = 0.0
PLACE_X_STEP  = 50.0
PLACE_Y       = -300.0
PLACE_Z_SAFE  = 150.0
PLACE_Z_DROP  = 140.0

FILL_WAIT_S   = 2.0
MOVE_VELOCITY = 80.0               # mm/s fuer Cart-Moves; % fuer Joint-Moves


# ------------------------------------------------------------------------------
#  SIMULIERTER EYE+ (Tastatureingabe statt echtes Geraet)
# ------------------------------------------------------------------------------

class SimulatedEyePlus:
    def __init__(self):
        self._analysis_running = False
        self._lock = threading.Lock()
        self._fake_recipes = [
            ("11818", "Rezept_Testmodus"),
            (RECIPE_ID_PROD, "Rezept_Produktion"),
        ]

    def connect(self):
        print("[SIM-EYE+] (simuliert) - keine echte Verbindung noetig.")

    def close(self):
        print("[SIM-EYE+] geschlossen.")

    def get_recipe_list(self):
        print("[SIM-EYE+] get_recipe_list ->")
        for i, (rid, name) in enumerate(self._fake_recipes):
            mark = "  <== Produktion" if rid == RECIPE_ID_PROD else ""
            print(f"          [{i}] {rid}  '{name}'{mark}")
        return list(self._fake_recipes)

    def start_production(self, recipe_id):
        print(f"[SIM-EYE+] start production {recipe_id} -> OK (200)")

    def stop_production(self):
        print("[SIM-EYE+] stop production -> OK")

    def force_take_image(self):
        print("[SIM-EYE+] force_take_image -> Bild aufgenommen.")
        return True

    def prepare_part(self):
        def _run():
            with self._lock:
                self._analysis_running = True
            time.sleep(1.0)
            with self._lock:
                self._analysis_running = False
        print("[SIM-EYE+] prepare_part -> Analyse gestartet (asynchron).")
        threading.Thread(target=_run, daemon=True).start()
        return 200, []

    def is_analysis_running(self):
        with self._lock:
            return self._analysis_running

    def get_part(self):
        print("\n" + "-" * 64)
        print("  EYE+ get_part  ->  Bitte Teil-Koordinaten eingeben:")
        print("     Format:  x y rz     (z.B.  12.5 -6.8 45)")
        print("     Leer + ENTER       =  KEIN Teil gefunden")
        print("-" * 64)
        try:
            raw = input("  Koordinaten > ").strip()
        except EOFError:
            return False, None, None, None

        if raw == "":
            print("  -> kein Teil erkannt.")
            return False, None, None, None

        toks = raw.replace(",", " ").split()
        try:
            x  = float(toks[0])
            y  = float(toks[1])
            rz = float(toks[2]) if len(toks) >= 3 else 0.0
        except (IndexError, ValueError):
            print("  [!] Ungueltige Eingabe -> als 'kein Teil' gewertet.")
            return False, None, None, None

        # Greifer dreht max. 180 Grad; bei rz > 180 wuerde er ueberdrehen.
        if rz > 180.0:
            rz -= 180.0
        print(f"  -> Teil: x={x:.2f}  y={y:.2f}  rz={rz:.2f}")
        return True, x, y, rz


class SimEyePoller:
    def __init__(self, sim_eye):
        self._eye = sim_eye

    def connect(self):
        pass

    def close(self):
        pass

    def is_analysis_running(self):
        return self._eye.is_analysis_running()


# ------------------------------------------------------------------------------
#  ROBOTER-HILFSFUNKTIONEN (CRIController-Wrapper)
# ------------------------------------------------------------------------------

def move_cart(robot: CRIController, x, y, z, a, b, c, label=""):
    print(f"   [MOVE  Cart ] X={x:7.1f} Y={y:7.1f} Z={z:6.1f} | "
          f"A={a:5.1f} B={b:5.1f} C={c:6.1f}")
    ok = robot.move_cartesian(
        X=x, Y=y, Z=z, A=a, B=b, C=c,
        E1=0.0, E2=0.0, E3=0.0,
        velocity=MOVE_VELOCITY,
        wait_move_finished=True,
    )
    if not ok:
        raise RuntimeError(f"Kartesische Bewegung fehlgeschlagen: {label}")


def move_jnt(robot: CRIController, joints, label=""):
    js = " ".join(f"{v:6.1f}" for v in joints)
    print(f"   [MOVE  Joint] A1..A6 = [{js} ]")
    a1, a2, a3, a4, a5, a6 = joints
    ok = robot.move_joints(
        A1=a1, A2=a2, A3=a3, A4=a4, A5=a5, A6=a6,
        E1=0.0, E2=0.0, E3=0.0,
        velocity=MOVE_VELOCITY,
        wait_move_finished=True,
    )
    if not ok:
        raise RuntimeError(f"Gelenkbewegung fehlgeschlagen: {label}")


def set_axis(robot: CRIController, axis_index, value, base_joints):
    joints = list(base_joints)
    joints[axis_index] = value
    print(f"   [AXIS  A{axis_index + 1}  ] -> {value:.1f} Grad")
    move_jnt(robot, joints, f"Achse {axis_index + 1} -> {value:.1f}")
    return joints


def rotate_a6(robot: CRIController, deg):
    # Dreht nur A6 relativ (Wrist), Greifer bleibt senkrecht.
    print(f"   [A6 rel    ] {deg:+.1f} Grad")
    ok = robot.move_joints_relative(
        A1=0.0, A2=0.0, A3=0.0, A4=0.0, A5=0.0, A6=deg,
        E1=0.0, E2=0.0, E3=0.0,
        velocity=MOVE_VELOCITY,
        wait_move_finished=True,
    )
    if not ok:
        raise RuntimeError("A6-Drehung fehlgeschlagen.")


def move_base_rel(robot: CRIController, dx, dy, dz):
    # Relative kartesische Bewegung im Basis-Koordinatensystem; Orientierung
    # bleibt gehalten (A6 bleibt gedreht). Senkrechtes Hochziehen, ohne dass die
    # IK die Greifer-Drehung vorzeitig zurueckdreht.
    print(f"   [MOVE  RelB ] dX={dx:+.1f} dY={dy:+.1f} dZ={dz:+.1f}")
    ok = robot.move_base_relative(
        X=dx, Y=dy, Z=dz, A=0.0, B=0.0, C=0.0,
        E1=0.0, E2=0.0, E3=0.0,
        velocity=MOVE_VELOCITY,
        wait_move_finished=True,
    )
    if not ok:
        raise RuntimeError("Relative Basisbewegung fehlgeschlagen.")


def gripper(robot: CRIController, close: bool):
    print(f"   [GRIPPER    ] "
          f"{'>>> SCHLIESSEN (greifen)' if close else '<<< OEFFNEN (loslassen)'}")
    robot.set_active_control(True)
    robot.set_dout(30, not close)
    time.sleep(1.2)   # warten bis Greifer-Mechanik fertig, bevor weiterbewegt wird


# ------------------------------------------------------------------------------
#  HAUPTPROGRAMM
# ------------------------------------------------------------------------------

def main():
    eye    = SimulatedEyePlus()
    poller = SimEyePoller(eye)
    robot  = CRIController()

    print("=" * 64)
    print("  SIMULATION  Pick-and-Place   (Eye+ = Tastatur, Roboter = iRC-Sim)")
    print(f"  Teile zu holen: {NUM_PARTS}   |   Verbinde mit {ROBOT_IP}:{ROBOT_PORT}")
    print("=" * 64)

    try:
        eye.connect()
        poller.connect()

        print(f"\nVerbinde mit iRC-Sim auf {ROBOT_IP}:{ROBOT_PORT} ...")
        robot.connect(host=ROBOT_IP, port=ROBOT_PORT)
        print("[ROBOT] verbunden.")

        print("[ROBOT] Warte auf Kinematik ...")
        if not robot.wait_for_kinematics_ready(timeout=30):
            raise RuntimeError("Kinematik nicht bereit (Timeout 30 s).")

        print("[ROBOT] Aktiviere Steuerung ...")
        if not robot.set_active_control(True):
            raise RuntimeError("Active Control konnte nicht gesetzt werden.")

        print("[ROBOT] Reset ...")
        robot.reset()

        print("[ROBOT] Enable ...")
        if not robot.enable():
            raise RuntimeError("Enable fehlgeschlagen.")

        print("[ROBOT] bereit.\n")

        eye.get_recipe_list()
        recipe_id = RECIPE_ID_PROD
        print(f"[EYE+] verwende Rezept_Produktion (ID {recipe_id})")
        eye.start_production(recipe_id)

        eye.force_take_image()
        print("\n>>> Erstes Bild: liegt ein Teil bereit?")
        found, x, y, rz = eye.get_part()
        if not found:
            print("[FILL] Kein Teil -> Cube befuellen (simuliert).")
            time.sleep(FILL_WAIT_S)
            eye.force_take_image()
            found, x, y, rz = eye.get_part()
        else:
            print("[FILL] Teil vorhanden -> kein Fuellen noetig.")

        picked    = 0
        next_part = (found, x, y, rz) if found else None

        while picked < NUM_PARTS:

            if next_part is None or not next_part[0]:
                found, x, y, rz = eye.get_part()
                next_part = (found, x, y, rz)

            if not next_part[0]:
                print("[LOOP] Kein Kandidat -> nachfuellen (simuliert) + neuer Versuch.")
                time.sleep(FILL_WAIT_S)
                eye.force_take_image()
                found, x, y, rz = eye.get_part()
                next_part = (found, x, y, rz)
                if not next_part[0]:
                    print("[LOOP] Weiterhin kein Teil -> warte erneut auf Eingabe.")
                    continue

            found, x, y, rz = next_part

            print(f"\n#################  Teil {picked + 1}/{NUM_PARTS}  "
                  f"(x={x:.1f} y={y:.1f} rz={rz:.1f})  #################")

            print("  Schritt: SAFE-TO-PICK anfahren")
            move_cart(robot, PICK_CENTER_X, PICK_CENTER_Y, SAFE_PICK_Z,
                      TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN, "Safe-Pick")

            print("  Schritt: ueber Teil + auf Greifhoehe (z=140), greifen (rz per A6)")
            move_cart(robot, x, y, SAFE_PICK_Z,
                      TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN, "Hover ueber Teil")
            move_cart(robot, x, y, GRIP_Z,
                      TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN, "Greifhoehe")
            # Teil-Drehung rz nur ueber A6 (Greifer bleibt senkrecht). A6 bleibt
            # zunaechst gedreht: erst senkrecht hochfahren, dann auf dem Weg zur
            # Safe-To-Rotate-Position die Orientierung korrigieren (A6 zurueck).
            # 90-Grad = fester Greifer-Montage-Offset zwischen rz und A6.
            a6 = 90.0 - rz
            rotate_a6(robot, a6)
            gripper(robot, close=True)

            print("  Schritt: senkrecht hoch (Greifer-Orientierung gehalten)")
            move_base_rel(robot, 0.0, 0.0, SAFE_PICK_Z - GRIP_Z)

            print("  Schritt: Orientierung korrigieren (A6 zurueck)")
            rotate_a6(robot, -a6)

            print("  Schritt: einfahren -> SAFE-TO-ROTATE")
            rotate_base = list(SAFE_ROTATE_JOINTS)
            move_jnt(robot, rotate_base, "Safe-Rotate")

            # Erst jetzt (Arm in Safe-To-Rotate, weg von der Platte) das naechste
            # Teil analysieren lassen -- sonst stoert der Arm ueber der Platte
            # die Bildaufnahme. Laeuft parallel zum Ablegen (Pipelining).
            if picked + 1 < NUM_PARTS:
                eye.prepare_part()

            print("  Schritt: 90 Grad im Uhrzeigersinn drehen (A1)")
            a1_target = rotate_base[0] + ROTATE_DEG
            rotated   = set_axis(robot, 0, a1_target, rotate_base)

            place_x = PLACE_X_START + picked * PLACE_X_STEP

            print("  Schritt: ausfahren + ablegen")
            move_cart(robot, place_x, PLACE_Y, PLACE_Z_SAFE,
                      TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN, "Hover ueber Ablage")
            move_cart(robot, place_x, PLACE_Y, PLACE_Z_DROP,
                      TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN, "Ablagehoehe")
            gripper(robot, close=False)
            move_cart(robot, place_x, PLACE_Y, PLACE_Z_SAFE,
                      TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN, "Hoch nach Ablage")

            print("  Schritt: einfahren -> Safe-Rotate (A1 noch -90 Grad)")
            move_jnt(robot, rotated, "Safe-Rotate rotiert")

            print("  Schritt: A1 zurueckrotieren (+90 Grad) -> Safe-Rotate")
            set_axis(robot, 0, rotate_base[0], rotated)

            picked += 1

            if picked < NUM_PARTS:
                print("[SYNC] warte, bis EYE+ Analyse fertig ist "
                      "(Arm soll Bild nicht stoeren)...")
                t0 = time.time()
                while poller.is_analysis_running():
                    if time.time() - t0 > 30:
                        print("[SYNC] Timeout.")
                        break
                    time.sleep(0.1)
                print("[SYNC] Analyse fertig -> naechstes Teil abholen.")
                found, x, y, rz = eye.get_part()
                next_part = (found, x, y, rz)

        print(f"\n=== FERTIG: {picked} Teil(e) abgelegt. ===")

    except KeyboardInterrupt:
        print("\n[ABBRUCH] durch Benutzer.")
    except (CRIConnectionError, RuntimeError) as e:
        print(f"\n[FEHLER] {type(e).__name__}: {e}")
    finally:
        try:
            eye.stop_production()
        except Exception:
            pass
        eye.close()
        poller.close()
        try:
            robot.disable()
            robot.set_active_control(False)
        except Exception:
            pass
        robot.close()
        print("[ENDE] Simulation beendet.")


if __name__ == "__main__":
    main()
