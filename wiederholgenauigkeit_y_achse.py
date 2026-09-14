#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 Wiederholgenauigkeitstest  —  igus ReBeL 6-DOF  (Y-Achse)
================================================================================

Prueft die (unidirektionale) Wiederholgenauigkeit des Roboters entlang der
Basis-Y-Achse: Eine feste Pruefkoordinate P wird immer aus derselben Richtung
10x linear angefahren. Die tatsaechlich erreichte Position wird von Hand
vermessen, z. B. als Abstand zwischen der planaren Flaeche vorne am Greifer
und einer fest montierten Referenzkante.

Einrichten (VOR jedem Lauf):
  1. Roboter in iRC von Hand an die zu pruefende Position fahren. Dabei
     Werkzeug-Orientierung pruefen: die vordere plane Flaeche des Greifers
     muss parallel zur X-Z-Ebene stehen und in Richtung der negativen
     Y-Achse schauen. Die dabei in iRC angezeigten A/B/C-Werte mit
     TOOL_A / TOOL_B / TOOL_C unten vergleichen und bei Abweichung anpassen
     (siehe Kommentar dort).
  2. Die abgelesenen X/Y/Z-Werte der Pruefposition unten bei CHECK_X /
     CHECK_Y / CHECK_Z eintragen.
  3. Skript starten. Vor dem eigentlichen Testlauf werden alle Werte
     ausgegeben und muessen per Enter bestaetigt werden.

Bewegungsablauf (10 Zyklen):
  - Start: Startposition anfahren (= Pruefkoordinate, aber 200 mm/20 cm in
    +Y versetzt).
  - Je Zyklus:
      1. 200 mm in -Y zur Pruefkoordinate P fahren (Anfahren der Flaeche).
      2. 2 s warten (Position von Hand vermessen).
      3. 200 mm in +Y zurueck zur Startposition fahren.
      4. 10 s warten.
  - Nach 10 Zyklen steht der Roboter wieder auf der Startposition.

Die Werkzeug-Orientierung (A/B/C) bleibt waehrend des gesamten Ablaufs
konstant. Geschwindigkeit: 20 % Override (siehe OVERRIDE_PERCENT).
Abbruch jederzeit mit Strg+C.
================================================================================
"""

import socket
import time
import threading


# ------------------------------------------------------------------------------
#  KONFIGURATION  -- hier alles anpassen
# ------------------------------------------------------------------------------

# --- Netzwerk ---
ROBOT_IP   = "192.168.3.11"
ROBOT_PORT = 3920

# --- Pruefkoordinate P [mm] ---  HIER die von Hand angefahrene und in iRC
# abgelesene Position eintragen. Das ist der Punkt, der 10x angefahren wird.
CHECK_X = 400.0
CHECK_Y = -100.0
CHECK_Z = 150.0

# --- Anfahrweg [mm] ---  Abstand der Startposition von der Pruefkoordinate,
# entlang der Pruefachse (Y). Die Startposition liegt bei Y = CHECK_Y +
# APPROACH_DISTANCE; von dort wird in -Y-Richtung auf P zugefahren.
APPROACH_DISTANCE = 200.0     # 20 cm

# --- Werkzeug-Orientierung [Grad] ---  Vordere plane Flaeche des Greifers
# parallel zur X-Z-Ebene, schauend in -Y-Richtung.
# Berechnet mit derselben Euler-Konvention (Rz(A)*Ry(B)*Rx(C), Werkzeug-Z =
# Blickrichtung des Greifers), die in genauigkeitstestV1.py / pick_and_placeV1.py
# fuer TOOL_A/B/C_DOWN = 180/0/180 verwendet wird (dort: Greifer zeigt
# senkrecht nach unten). Rechnerisch ergibt A=0, B=90, C=90 eine
# Blickrichtung von -Y mit derselben "oben/unten"-Referenz wie beim
# Nach-unten-Zeigen.
# WICHTIG: Vor dem ersten automatischen Lauf in iRC anfahren und mit der
# geforderten Ausrichtung (Flaeche parallel X-Z, Blick -Y) visuell
# vergleichen; bei Abweichung hier die tatsaechlichen iRC-Werte eintragen.
TOOL_A = 0.0
TOOL_B = 90.0
TOOL_C = 90.0

# --- Bewegungsparameter ---
OVERRIDE_PERCENT = 20.0       # Geschwindigkeit: 20 % (CMD Override)
CART_VELOCITY    = 250.0      # mm/s, vor Anwendung des Override

# --- Zeiten [s] ---
WAIT_AT_CHECK_S = 2.0          # Wartezeit an der Pruefkoordinate
WAIT_AT_START_S = 10.0         # Wartezeit an der Startposition
NUM_CYCLES      = 10           # Anzahl Wiederholungen


# ==============================================================================
#  igus ReBeL  CRI CLIENT
# ==============================================================================

class CriRobot:
    def __init__(self, ip, port):
        self.ip      = ip
        self.port    = port
        self.sock    = None
        self._buf    = b""
        self._msg_id = 1
        self._lock   = threading.Lock()
        self._alive  = False

    def connect(self):
        self.sock = socket.create_connection((self.ip, self.port), timeout=10)
        self.sock.settimeout(15.0)
        self._alive = True
        print(f"[ROBOT] verbunden  {self.ip}:{self.port}")
        threading.Thread(target=self._keepalive_loop, daemon=True).start()

    def close(self):
        self._alive = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _next_id(self):
        self._msg_id += 1
        return self._msg_id

    def _wrap(self, body):
        mid = self._next_id()
        return f"CRISTART {mid} {body} CRIEND".encode("ascii"), mid

    def _send_raw(self, body, wait_answer=True, timeout=30.0):
        with self._lock:
            data, _ = self._wrap(body)
            self.sock.sendall(data)
            if not wait_answer:
                return None
            return self._read_status(timeout=timeout)

    def _read_status(self, timeout=30.0):
        deadline = time.time() + timeout
        self.sock.settimeout(1.0)
        while time.time() < deadline:
            try:
                chunk = self.sock.recv(4096)
                if chunk:
                    self._buf += chunk
            except socket.timeout:
                pass
            text = self._buf.decode("ascii", errors="replace")
            if "CRIEND" in text:
                self._buf = b""
                return text
        return ""

    def _keepalive_loop(self):
        while self._alive and self.sock:
            try:
                with self._lock:
                    data, _ = self._wrap("ALIVEJOG 0 0 0 0 0 0 0 0 0")
                    self.sock.sendall(data)
            except OSError:
                break
            time.sleep(0.05)

    def init(self):
        # Active Control zuerst anfordern, sonst ignoriert der Controller alle
        # Move-Befehle (die IRC-Software haelt sonst die Kontrolle).
        self._send_raw("CMD SetActive true", wait_answer=False)
        time.sleep(0.3)
        self._send_raw("CMD Reset")
        time.sleep(0.3)
        self._send_raw("CMD Enable")
        time.sleep(1.5)
        print("[ROBOT] SetActive + Reset + Enable")

    def set_override(self, percentage: float):
        self._send_raw(f"CMD Override {percentage:.0f}", wait_answer=False)
        print(f"[ROBOT] Override gesetzt: {percentage:.0f} %")

    def move_cartesian(self, x, y, z, a, b, c, velocity=500.0):
        body = (f"CMD Move Cart "
                f"{x:.3f} {y:.3f} {z:.3f} {a:.3f} {b:.3f} {c:.3f} "
                f"0.0 0.0 0.0 {velocity:.1f}")
        self._send_raw(body)
        print(f"   [MOVE Cart ] X={x:7.1f} Y={y:7.1f} Z={z:6.1f}"
              f"  A={a:5.1f} B={b:5.1f} C={c:6.1f}")
        status = self._wait_motion_done()
        # Bewegungsfehler NICHT stillschweigend uebergehen: fuer einen
        # Wiederholgenauigkeitstest wuerde eine abgelehnte/abgebrochene Fahrt
        # zu falschen Messwerten fuehren, ohne dass man es merkt. Darum
        # sauber abbrechen (main() faengt die Exception und schliesst).
        if status == "error":
            raise RuntimeError(
                f"Roboter meldet Bewegungsfehler (EXECERROR) beim Anfahren von "
                f"X={x:.1f} Y={y:.1f} Z={z:.1f}  A={a:.1f} B={b:.1f} C={c:.1f}. "
                f"Moegliche Ursache: Ziel unerreichbar, Gelenkgrenze oder "
                f"Singularitaet (bei B=90 Grad besonders wahrscheinlich).")
        if status == "timeout":
            raise RuntimeError(
                f"Timeout beim Warten auf Bewegungsende (EXECEND) beim Anfahren "
                f"von X={x:.1f} Y={y:.1f} Z={z:.1f}. Bewegung nicht bestaetigt "
                f"-- Ablauf abgebrochen.")

    def _wait_motion_done(self, timeout=60.0):
        # Warten bis der Controller das Bewegungsende meldet.
        # Rueckgabe: "ok" (EXECEND), "error" (EXECERROR) oder "timeout".
        deadline = time.time() + timeout
        self.sock.settimeout(1.0)
        while time.time() < deadline:
            text = self._buf.decode("ascii", errors="replace")
            if "EXECERROR" in text:
                self._buf = b""
                return "error"
            if "EXECEND" in text:
                self._buf = b""
                return "ok"
            try:
                chunk = self.sock.recv(4096)
                if chunk:
                    self._buf += chunk
            except socket.timeout:
                pass
        return "timeout"


# ==============================================================================
#  BEWEGUNGSABLAUF
# ==============================================================================

def _default_log(text, tag=None):
    print(text)


def run_wiederholgenauigkeit_y(robot, check_xyz, approach_distance, tool,
                                cart_vel=250.0, wait_check=2.0, wait_start=10.0,
                                num_cycles=10, log=_default_log, check=None):
    """Faehrt die Pruefkoordinate entlang -Y num_cycles mal linear an.

    check_xyz         : (x, y, z) der Pruefkoordinate P [mm].
    approach_distance : Abstand [mm] der Startposition von P entlang Y.
    tool              : (a, b, c) Werkzeug-Orientierung in Grad (konstant).
    check             : Callable ohne Argumente; darf eine Exception werfen,
                        um den Ablauf (STOP/Pause) abzubrechen. Wird vor
                        jeder Bewegung aufgerufen.
    """
    if check is None:
        check = lambda: None

    a, b, c = tool
    cx, cy, cz = check_xyz
    start = (cx, cy + approach_distance, cz)
    ziel  = (cx, cy, cz)

    def isleep(seconds):
        # Unterbrechbares Warten: bei STOP wirft check() sofort eine Exception.
        end = time.time() + seconds
        while time.time() < end:
            check()
            time.sleep(min(0.1, max(0.0, end - time.time())))

    log(f"Pruefkoordinate P : X={ziel[0]:8.2f} Y={ziel[1]:8.2f} Z={ziel[2]:8.2f}")
    log(f"Startposition     : X={start[0]:8.2f} Y={start[1]:8.2f} Z={start[2]:8.2f}")
    log(f"Werkzeug A/B/C    : {a:.1f} / {b:.1f} / {c:.1f}")

    log("-> Startposition anfahren ...")
    check(); robot.move_cartesian(*start, a, b, c, velocity=cart_vel)

    for n in range(1, num_cycles + 1):
        log(f"\n=== Zyklus {n}/{num_cycles} ===")
        log("  -> vor zur Pruefkoordinate (-Y)")
        check(); robot.move_cartesian(*ziel, a, b, c, velocity=cart_vel)
        log(f"  *** MESSUNG {n}/{num_cycles}: jetzt messen "
            f"(Roboter haelt {wait_check:.0f}s) ***")
        isleep(wait_check)
        log("  -> zurueck zur Startposition (+Y)")
        check(); robot.move_cartesian(*start, a, b, c, velocity=cart_vel)
        # Nach dem letzten Zyklus nicht mehr warten -- Roboter steht bereits
        # auf der Startposition, der Test ist beendet.
        if n < num_cycles:
            log(f"  -> warte {wait_start:.1f}s ...")
            isleep(wait_start)

    log("\nTest abgeschlossen -- Roboter steht auf der Startposition.")


# ==============================================================================
#  HAUPTABLAUF  (Standalone)
# ==============================================================================

def main():
    robot = CriRobot(ROBOT_IP, ROBOT_PORT)

    print("=" * 70)
    print("  Wiederholgenauigkeitstest -- Y-Achse  (igus ReBeL 6-DOF)")
    print(f"  Pruefkoordinate P : ({CHECK_X}, {CHECK_Y}, {CHECK_Z})")
    print(f"  Anfahrweg         : {APPROACH_DISTANCE:.0f} mm entlang Y, "
          f"Anfahrtrichtung -Y")
    print(f"  Werkzeug A/B/C    : {TOOL_A} / {TOOL_B} / {TOOL_C}")
    print(f"  Override          : {OVERRIDE_PERCENT:.0f} %")
    print(f"  Zyklen            : {NUM_CYCLES}  "
          f"(Warten {WAIT_AT_CHECK_S:.0f}s an P / {WAIT_AT_START_S:.0f}s am Start)")
    print(f"  Roboter           : {ROBOT_IP}:{ROBOT_PORT}")
    print("=" * 70)

    input("\nWerte oben pruefen (insb. Pruefkoordinate und Werkzeug-"
          "Orientierung -- Flaeche muss parallel zur X-Z-Ebene stehen und "
          "in -Y-Richtung schauen). Arbeitsbereich frei? Enter zum Start, "
          "Strg+C zum Abbrechen ...")

    try:
        robot.connect()
        robot.init()
        robot.set_override(OVERRIDE_PERCENT)

        run_wiederholgenauigkeit_y(
            robot,
            (CHECK_X, CHECK_Y, CHECK_Z),
            APPROACH_DISTANCE,
            (TOOL_A, TOOL_B, TOOL_C),
            cart_vel=CART_VELOCITY,
            wait_check=WAIT_AT_CHECK_S,
            wait_start=WAIT_AT_START_S,
            num_cycles=NUM_CYCLES,
        )

    except KeyboardInterrupt:
        print("\n[STOP] durch Benutzer.")
    except Exception as e:
        print(f"\n[FEHLER] {type(e).__name__}: {e}")
    finally:
        robot.close()
        print("[ENDE] Verbindung geschlossen.")


if __name__ == "__main__":
    main()
