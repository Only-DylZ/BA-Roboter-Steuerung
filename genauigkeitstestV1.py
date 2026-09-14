#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 Genauigkeitstest  —  igus ReBeL 6-DOF
================================================================================

Der Roboter bewegt EIN Bauteil wiederholt zwischen zwei Ablageorten hin und
her (greifen / ablegen), um die Wiederhol-Genauigkeit zu pruefen. Es ist KEINE
Asyril-EYE+-Verbindung noetig — nur der Roboter wird angesteuert.

Bewegungsablauf (Endlosschleife, per STOP / Strg+C abbrechbar):
  - Zu Beginn faehrt der Roboter IMMER zuerst in seinen Safe-To-Rotate
    (eingefahrenen) Zustand.
  - Das Teil liegt in Ablageort 1 bereit.
  - GREIFEN @1 :  ueber das Teil fahren (Safe-Hoehe = Z + Offset) -> gerade
    nach unten (Pick-Hoehe Z) -> greifen -> gerade nach oben -> einfahren.
  - ABLEGEN @2 :  ausfahren ueber Ort 2 (Safe-Hoehe) -> gerade runter (Z) ->
    loslassen -> gerade hoch -> einfahren (ohne Teil).
  - GREIFEN @2 / ABLEGEN @1 / GREIFEN @1 / ABLEGEN @2 / ...  (endlos).

Wichtig:  Der Roboter rotiert (A1) nur im eingefahrenen (Safe-To-Rotate)
Zustand. Vor jedem Aus-/Anfahren wird zuerst eingefahren und — falls noetig —
A1 gedreht; erst dann faehrt der Arm gerade zum Ablageort.
================================================================================
"""

import socket
import time
import threading
import math


# ------------------------------------------------------------------------------
#  KONFIGURATION  -- hier alles anpassen (Default-Werte fuer die GUI)
# ------------------------------------------------------------------------------

# --- Netzwerk ---
ROBOT_IP   = "192.168.3.11"
ROBOT_PORT = 3920

# --- Ablageort 1 [mm] ---
PLACE1_X = -10.3
PLACE1_Y = -296.1
PLACE1_Z = 80.2

# --- Ablageort 2 [mm] ---
PLACE2_X = 110.6
PLACE2_Y = -389.3
PLACE2_Z = 80.2

# --- Anfahr-Offset [mm] ---  (Safe-Hoehe ueber dem Ablageort = Z + Offset)
SAFE_Z_OFFSET = 20.0

# --- Werkzeug-Orientierung [Grad] ---  (Greifer senkrecht nach unten)
TOOL_A_DOWN = 180.0
TOOL_B_DOWN = 0.0
TOOL_C_DOWN = 180.0

# --- Safe-To-Rotate (eingefahren) A1..A6 ---
SAFE_ROTATE_JOINTS = [0.0, -18.7, 108.0, 0.0, 90.0, 0.0]

# --- Bewegungsparameter ---
MOVE_VELOCITY = 40.0                # Override in %

# --- Greifer ---
# Zusaetzliche Wartezeit (Sekunden) NACH jedem Greifen/Oeffnen, bevor sich der
# Roboter wieder bewegt. Stellt sicher, dass die Greifer-Mechanik wirklich
# fertig (geschlossen/geoeffnet) ist. Bei Bedarf erhoehen, falls der Greifer
# langsamer ist. (Kommt zusaetzlich zur kurzen Grundwartezeit im Greifer-Befehl.)
GRIPPER_SETTLE_S = 1.5


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
        # Move-/DOUT-Befehle (die IRC-Software haelt sonst die Kontrolle).
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
        self._wait_motion_done()

    def move_joints(self, joints, velocity=100.0):
        j    = " ".join(f"{v:.3f}" for v in joints)
        body = f"CMD Move Joint {j} 0.0 0.0 0.0 {velocity:.1f}"
        self._send_raw(body)
        js = " ".join(f"{v:5.1f}" for v in joints)
        print(f"   [MOVE Joint] [{js}]")
        self._wait_motion_done()

    def gripper(self, close):
        self._send_raw("CMD SetActive true", wait_answer=False)
        self._send_raw(f"CMD DOUT 30 {'true' if close else 'false'}")
        self._send_raw(f"CMD DOUT 31 {'false' if close else 'true'}")
        print(f"   [GREIFER   ] {'>>> SCHLIESSEN (greifen)' if close else '<<< OEFFNEN (loslassen)'}")
        time.sleep(1.2)   # warten bis Greifer-Mechanik fertig, bevor weiterbewegt wird

    def _wait_motion_done(self, timeout=120.0):
        # Warten bis der Controller das Bewegungsende meldet (EXECEND-Frame).
        deadline = time.time() + timeout
        self.sock.settimeout(1.0)
        while time.time() < deadline:
            text = self._buf.decode("ascii", errors="replace")
            if "EXECEND" in text or "EXECERROR" in text:
                self._buf = b""
                return
            try:
                chunk = self.sock.recv(4096)
                if chunk:
                    self._buf += chunk
            except socket.timeout:
                pass
        print("   [ROBOT     ] WARN: Timeout beim Warten auf Bewegungsende (EXECEND).")


# ==============================================================================
#  BEWEGUNGSABLAUF
# ==============================================================================

def _default_log(text, tag=None):
    print(text)


def _azimuth_a1(base_joints, x, y):
    # A1-Winkel (Grad), damit der eingefahrene Arm zum Punkt (x, y) zeigt.
    # base_joints[0] ist die Home-Azimut (A1 in Safe-To-Rotate, zeigt zu
    # Azimut 0 / +X). Fuer einen Punkt im Azimut atan2(y, x) wird A1 relativ
    # dazu gedreht. So findet die Drehung ausschliesslich im eingefahrenen
    # Zustand statt; das anschliessende kartesische Ausfahren ist (nahezu)
    # rein radial, ohne grosse A1-Aenderung.
    return base_joints[0] + math.degrees(math.atan2(y, x))


def run_genauigkeitstest(robot, place1, place2, safe_z_offset, tool,
                         safe_joints, cart_vel=500.0, joint_vel=100.0,
                         log=_default_log, check=None, on_cycle=None,
                         max_cycles=None, gripper_settle=None):
    """Bewegt ein Teil endlos (oder max_cycles mal) zwischen place1 und place2.

    place1 / place2 : (x, y, z) in mm.
    tool            : (a, b, c) Werkzeug-Orientierung in Grad.
    safe_joints     : Safe-To-Rotate-Gelenkwinkel A1..A6.
    check           : Callable ohne Argumente; darf eine Exception werfen, um
                      den Ablauf (STOP/Pause) abzubrechen. Wird vor jeder
                      Bewegung aufgerufen.
    on_cycle        : Callable(n) nach jedem abgeschlossenen Hin-und-Her-Schritt.
    gripper_settle  : Wartezeit [s] nach jedem Greifen/Oeffnen, bevor sich der
                      Roboter weiterbewegt (Default: GRIPPER_SETTLE_S).
    """
    if check is None:
        check = lambda: None
    if on_cycle is None:
        on_cycle = lambda n: None
    if gripper_settle is None:
        gripper_settle = GRIPPER_SETTLE_S

    a, b, c = tool
    base    = list(safe_joints)

    def isleep(seconds):
        # Unterbrechbares Warten: bei STOP wirft check() sofort eine Exception.
        end = time.time() + seconds
        while time.time() < end:
            check()
            time.sleep(min(0.1, max(0.0, end - time.time())))

    def grip(close):
        # Greifen/Oeffnen und SICHER warten, bis die Mechanik fertig ist, bevor
        # die naechste Bewegung startet (sonst faehrt der Arm zu frueh weiter).
        check()
        robot.gripper(close=close)
        log(f"  -> warte {gripper_settle:.1f}s (Greifer "
            f"{'schliessen' if close else 'oeffnen'}) ...", "info")
        isleep(gripper_settle)

    def retract(a1):
        # In den eingefahrenen Zustand mit gegebener A1-Stellung fahren.
        j    = list(base)
        j[0] = a1
        check()
        robot.move_joints(j, velocity=joint_vel)

    def pick(x, y, z):
        check(); robot.move_cartesian(x, y, z + safe_z_offset, a, b, c, velocity=cart_vel)
        check(); robot.move_cartesian(x, y, z,                 a, b, c, velocity=cart_vel)
        grip(close=True)
        check(); robot.move_cartesian(x, y, z + safe_z_offset, a, b, c, velocity=cart_vel)

    def place(x, y, z):
        check(); robot.move_cartesian(x, y, z + safe_z_offset, a, b, c, velocity=cart_vel)
        check(); robot.move_cartesian(x, y, z,                 a, b, c, velocity=cart_vel)
        grip(close=False)
        check(); robot.move_cartesian(x, y, z + safe_z_offset, a, b, c, velocity=cart_vel)

    # Zu Beginn IMMER zuerst Safe-To-Rotate (eingefahren).
    log("  -> Safe-To-Rotate (einfahren)", "info")
    check()
    robot.move_joints(base, velocity=joint_vel)

    src, dst = place1, place2          # Teil liegt anfangs in Ablageort 1
    n = 0
    while max_cycles is None or n < max_cycles:
        a1_src = _azimuth_a1(base, src[0], src[1])
        a1_dst = _azimuth_a1(base, dst[0], dst[1])

        # --- Teil greifen (Quelle) ---
        log(f"  -> A1 drehen (eingefahren) {a1_src:+.1f} Grad -> Ablageort", "move")
        retract(a1_src)                # Drehung NUR im eingefahrenen Zustand
        log(f"  -> greifen   X={src[0]:.1f} Y={src[1]:.1f} Z={src[2]:.1f}", "info")
        pick(*src)
        log("  -> einfahren (mit Teil)", "info")
        retract(a1_src)                # nur einfahren, A1 unveraendert

        # --- Teil ablegen (Ziel) ---
        log(f"  -> A1 drehen (eingefahren) {a1_dst:+.1f} Grad -> Ablageort", "move")
        retract(a1_dst)                # Drehung NUR im eingefahrenen Zustand
        log(f"  -> ablegen   X={dst[0]:.1f} Y={dst[1]:.1f} Z={dst[2]:.1f}", "info")
        place(*dst)
        log("  -> einfahren (ohne Teil)", "info")
        retract(a1_dst)                # nur einfahren, A1 unveraendert

        n += 1
        on_cycle(n)
        src, dst = dst, src            # Hin und Her: Quelle/Ziel tauschen


# ==============================================================================
#  HAUPTABLAUF  (Standalone)
# ==============================================================================

def main():
    robot = CriRobot(ROBOT_IP, ROBOT_PORT)

    print("=" * 64)
    print("  Genauigkeitstest  (igus ReBeL 6-DOF)")
    print(f"  Ort 1: ({PLACE1_X}, {PLACE1_Y}, {PLACE1_Z})"
          f"   Ort 2: ({PLACE2_X}, {PLACE2_Y}, {PLACE2_Z})")
    print(f"  Roboter: {ROBOT_IP}:{ROBOT_PORT}")
    print("=" * 64)

    try:
        robot.connect()
        robot.init()
        robot.set_override(MOVE_VELOCITY)

        run_genauigkeitstest(
            robot,
            (PLACE1_X, PLACE1_Y, PLACE1_Z),
            (PLACE2_X, PLACE2_Y, PLACE2_Z),
            SAFE_Z_OFFSET,
            (TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN),
            SAFE_ROTATE_JOINTS,
            on_cycle=lambda n: print(f"\n=== Transfer {n} abgeschlossen ===\n"),
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
