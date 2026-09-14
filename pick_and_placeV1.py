#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 Pick-and-Place Steuerung:  Asyril EYE+  +  igus ReBeL 6-DOF  (Produktion)
================================================================================

Ablauf:
  1.  Mit EYE+ und Roboter verbinden.
  2.  Recipe-Liste holen -> gewaehlte Recipe-ID -> Production starten.
  3.  Erstes Bild ausloesen; Cube befuellen falls keine Teile erkannt.
  4.  Solange noch Teile zu holen sind (NUM_PARTS):
        a) Kandidat holen (get_part -> x, y, rz).
        b) SAFE-TO-PICK anfahren (mittig ueber Entnahmebereich, z = 150 mm).
        c) Greifer nach unten (A, B fest), C = TOOL_C_DOWN + rz (Teildrehung).
        d) Auf Greifhoehe (z = 140 mm) fahren, greifen.
        e) Zurueck SAFE-TO-PICK.
        f) Einfahren -> SAFE-TO-ROTATE (A6 behaelt grip_c).
        g) A1 um ROTATE_DEG drehen.
        h) Ausfahren, Teil ablegen (PLACE_X + picked * PLACE_X_STEP, PLACE_Y).
        i) Zurueck SAFE-TO-PICK-Hoehe (hoch), dann einfahren -> Safe-Rotate,
           dann A1 zurueckrotieren.
      Parallel: waehrend der Roboter arbeitet, sucht EYE+ bereits das
      naechste Teil (prepare_part, asynchron). Vor dem naechsten SAFE-TO-PICK
      wird geprueft, ob die Analyse fertig ist (Arm stoert Bild nicht).
================================================================================
"""

import socket
import time
import threading


# ------------------------------------------------------------------------------
#  KONFIGURATION  -- hier alles anpassen
# ------------------------------------------------------------------------------

# --- Netzwerk ---
EYE_IP        = "192.168.3.20"
EYE_PORT      = 7171
ROBOT_IP      = "192.168.3.11"
ROBOT_PORT    = 3920

# --- Aufgabe ---
NUM_PARTS     = 4

# Produktionsbetrieb -> immer Rezept_Produktion.
RECIPE_ID_PROD = "20870"            # Rezept_Produktion

# --- Pick-Geometrie [mm / Grad] ---
PICK_CENTER_X = 440.0
PICK_CENTER_Y = -5.0
SAFE_PICK_Z   = 170.0
GRIP_Z        = 158.0

TOOL_A_DOWN   = 180.0
TOOL_B_DOWN   = 0.0
TOOL_C_DOWN   = 180.0               # Basis; Teil-rz wird additiv addiert

SAFE_ROTATE_JOINTS = [0.0, -18.7, 108.0, 0.0, 90.0, 0.0]
ROTATE_DEG    = -90.0

# --- Ablage [mm] ---
PLACE_X_START = -132.8
PLACE_X_STEP  = 40.0                # Schritt pro abgelegtem Teil
PLACE_Y       = -392.5
PLACE_Z_SAFE  = 90
PLACE_Z_DROP  = 80.2

# --- Cube-Fuellung ---
MIN_PARTS_ON_PLATE = 1
FILL_FEEDER_CMD    = "feeder 1"
FILL_WAIT_S        = 2.0

# --- Bewegungsparameter ---
MOVE_VELOCITY = 50.0                # Override in % (wird per CMD Override gesetzt)


# ==============================================================================
#  EYE+  TCP/IP CLIENT
# ==============================================================================

class EyePlusClient:
    def __init__(self, ip, port, timeout=35.0):
        self.ip      = ip
        self.port    = port
        self.timeout = timeout
        self.sock    = None
        self._buf    = b""
        self._lock   = threading.Lock()

    def connect(self):
        self.sock = socket.create_connection((self.ip, self.port), timeout=10)
        self.sock.settimeout(self.timeout)
        print(f"[EYE+] verbunden  {self.ip}:{self.port}")

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _read_line(self):
        while b"\n" not in self._buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("[EYE+] Verbindung getrennt")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line.decode("ascii", errors="replace").strip()

    def send(self, command):
        with self._lock:
            self.sock.sendall((command + "\n").encode("ascii"))
            first = self._read_line()
        parts = first.split(" ")
        code  = int(parts[0])
        rest  = parts[1:]
        if rest and rest[0].isdigit():
            nlines  = int(rest[0])
            payload = [" ".join(rest[1:])] if len(rest) > 1 else []
            for _ in range(max(0, nlines - len(payload))):
                payload.append(self._read_line())
            return code, payload
        return code, rest

    def get_recipe_list(self):
        code, payload = self.send("get_recipe_list")
        if code != 200:
            raise RuntimeError(f"[EYE+] get_recipe_list -> {code} {payload}")
        recipes = []
        for line in payload:
            line = line.strip()
            if not line:
                continue
            toks = line.split(" ", 1)
            rid  = toks[0]
            name = toks[1].strip("'\"") if len(toks) > 1 else ""
            recipes.append((rid, name))
        return recipes

    def start_production(self, recipe_id):
        code, payload = self.send(f"start production {recipe_id}")
        if code != 200:
            raise RuntimeError(f"[EYE+] start production -> {code} {payload}")
        print(f"[EYE+] Production gestartet  (Recipe {recipe_id})")

    def stop_production(self):
        code, _ = self.send("stop production")
        print(f"[EYE+] stop production -> {code}")

    def force_take_image(self):
        code, _ = self.send("force_take_image")
        return code == 200

    def prepare_part(self):
        return self.send("prepare_part")

    def get_part(self):
        code, payload = self.send("get_part")
        if code != 200:
            return False, None, None, None
        fields = {}
        text   = " ".join(payload) if isinstance(payload, list) else str(payload)
        for tok in text.split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                try:
                    fields[k] = float(v)
                except ValueError:
                    pass
        if "x" in fields and "y" in fields:
            rz = fields.get("rz", 0.0)
            # Greifer dreht nur +/-180 Grad, Teil-rz laeuft 0..359.99 und hat
            # genau eine richtige Greif-Orientierung. Bei rz > 180 den
            # aequivalenten negativen Winkel anfahren (rz-360, Bereich -180..0),
            # also in die andere Richtung drehen. Bsp: rz=270 -> 270-360 = -90.
            if rz > 180.0:
                rz -= 360.0
            return True, fields["x"], fields["y"], rz
        return False, None, None, None


class EyePlusPoller:
    def __init__(self, ip, port):
        self.client = EyePlusClient(ip, port, timeout=10.0)

    def connect(self):
        self.client.connect()

    def close(self):
        self.client.close()

    def is_analysis_running(self):
        try:
            code, payload = self.client.send("get_parameter is_analysis_running")
            if code != 200:
                return False
            return "true" in " ".join(payload).lower()
        except Exception:
            return False


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

    def set_axis(self, axis_index, value, base_joints, velocity=100.0):
        joints             = list(base_joints)
        joints[axis_index] = value
        print(f"   [AXIS  A{axis_index + 1}  ] -> {value:.1f} Grad")
        self.move_joints(joints, velocity)
        return joints

    def rotate_a6(self, deg, velocity=100.0):
        # Dreht A6 um deg -- aber als ABSOLUTER Joint-Befehl (Ziel = Ist + deg)
        # statt "Move RelativeJoint". Ein expliziter "CMD Move Joint" laesst
        # dem Controller keinen Spielraum, auf eine aequivalente (um 180 Grad
        # verdrehte) Loesung oder den "kuerzeren Weg" auszuweichen.
        # Nach der Bewegung wird der erreichte Winkel verifiziert und bei
        # Abweichung einmal nachkorrigiert.
        j = self.read_joints()
        if j is None:
            # Fallback ohne Joint-Daten: relativer Befehl wie bisher.
            body = (f"CMD Move RelativeJoint 0.0 0.0 0.0 0.0 0.0 {deg:.3f} "
                    f"0.0 0.0 0.0 {velocity:.1f}")
            self._send_raw(body)
            print(f"   [A6 rel    ] {deg:+.1f} Grad (keine Joint-Daten, unverifiziert!)")
            self._wait_motion_done()
            return
        target = j[5] + deg
        # In den gueltigen A6-Bereich schieben (+/-360 ist dieselbe
        # Orientierung, aendert also nichts am Greif-Winkel).
        if target > 179.0:
            target -= 360.0
        elif target < -179.0:
            target += 360.0
        joints    = list(j)
        joints[5] = target
        print(f"   [A6 abs    ] {j[5]:+.1f} -> {target:+.1f} Grad  (delta {deg:+.1f})")
        self.move_joints(joints, velocity)
        self._verify_a6(target)

    def _verify_a6(self, target, tol=2.0):
        # Kontrolliert, ob A6 wirklich auf dem Sollwinkel steht. Faengt genau
        # den Fall ab, dass der Controller eine andere (z.B. um 180 Grad
        # gedrehte) Loesung gefahren ist.
        j = self.read_joints(prefer_current=True)
        if j is None:
            print("   [A6 CHECK  ] WARN: keine Joint-Daten zur Verifikation.")
            return
        err = ((j[5] - target + 180.0) % 360.0) - 180.0
        if abs(err) <= tol:
            return
        print(f"   [A6 CHECK  ] FEHLER: Ist {j[5]:+.1f}, Soll {target:+.1f}"
              f" (Abweichung {err:+.1f} Grad) -> korrigiere.")
        joints    = list(j)
        joints[5] = j[5] - err
        self.move_joints(joints)
        j2 = self.read_joints(prefer_current=True)
        if j2 is not None:
            err2 = ((j2[5] - joints[5] + 180.0) % 360.0) - 180.0
            if abs(err2) > tol:
                raise RuntimeError(
                    f"A6 laesst sich nicht auf den Sollwinkel stellen "
                    f"(Restabweichung {err2:+.1f} Grad)")

    def move_base_relative(self, dx, dy, dz, velocity=500.0):
        # Relative kartesische Bewegung im Basis-Koordinatensystem. Orientierung
        # bleibt unveraendert (A=B=C=0) -> A6 bleibt gehalten. So kann das Teil
        # senkrecht hochgezogen werden, ohne dass die IK die Greifer-Drehung
        # (A6) vorzeitig zurueckdreht.
        body = (f"CMD Move RelativeBase "
                f"{dx:.3f} {dy:.3f} {dz:.3f} 0.0 0.0 0.0 "
                f"0.0 0.0 0.0 {velocity:.1f}")
        self._send_raw(body)
        print(f"   [MOVE RelB ] dX={dx:+.1f} dY={dy:+.1f} dZ={dz:+.1f}")
        self._wait_motion_done()

    def gripper(self, close):
        self._send_raw("CMD SetActive true", wait_answer=False)
        self._send_raw(f"CMD DOUT 30 {'true' if close else 'false'}")
        self._send_raw(f"CMD DOUT 31 {'false' if close else 'true'}")
        print(f"   [GREIFER   ] {'>>> SCHLIESSEN (greifen)' if close else '<<< OEFFNEN (loslassen)'}")
        time.sleep(1.2)   # warten bis Greifer-Mechanik fertig, bevor weiterbewegt wird

    def _wait_motion_done(self, timeout=120.0):
        # Warten bis der Controller das Bewegungsende meldet (EXECEND-Frame).
        # Der vorausgegangene _send_raw hat den Puffer bereits geleert, daher
        # kann hier kein altes EXECEND einer frueheren Bewegung haengenbleiben.
        deadline = time.time() + timeout
        self.sock.settimeout(1.0)
        while time.time() < deadline:
            text = self._buf.decode("ascii", errors="replace")
            if "EXECERROR" in text:
                # Bewegung ist fehlgeschlagen (z.B. Achsgrenze, Singularitaet,
                # MNE_OC). Frueher wurde das wie Erfolg behandelt -> Roboter
                # greift dann in falscher Orientierung weiter. Jetzt abbrechen.
                self._buf = b""
                raise RuntimeError(
                    "Controller meldet EXECERROR: Bewegung nicht ausgefuehrt. "
                    "Naechster Schritt wuerde in falscher Pose ausgefuehrt.")
            if "EXECEND" in text:
                self._buf = b""
                return
            try:
                chunk = self.sock.recv(4096)
                if chunk:
                    self._buf += chunk
            except socket.timeout:
                pass
        print("   [ROBOT     ] WARN: Timeout beim Warten auf Bewegungsende (EXECEND).")

    def read_joints(self, timeout=2.0, prefer_current=False):
        """Liest die aktuellen Achswinkel [A1..A6] aus dem CRI-STATUS-Frame.
        Zwischen Bewegungen aufrufen. prefer_current=True bevorzugt die
        Ist-Winkel (POSJOINTCURRENT) statt der Soll-Winkel -- noetig, um zu
        pruefen, ob der Controller wirklich dorthin gefahren ist, wohin er
        sollte. Gibt eine Liste mit 6 Werten zurueck oder None.
        """
        if prefer_current:
            keys = ("POSJOINTCURRENT", "POSJOINTSETPOINT")
        else:
            keys = ("POSJOINTSETPOINT", "POSJOINTCURRENT")
        deadline = time.time() + timeout
        self.sock.settimeout(0.3)
        while time.time() < deadline:
            try:
                chunk = self.sock.recv(4096)
                if chunk:
                    self._buf += chunk
            except socket.timeout:
                pass
            text = self._buf.decode("ascii", errors="replace")
            for key in keys:
                best  = None
                start = 0
                while True:
                    idx = text.find(key, start)
                    if idx < 0:
                        break
                    end = text.find("CRIEND", idx)
                    if end < 0:          # Frame noch unvollstaendig
                        break
                    vals = []
                    for t in text[idx + len(key):end].split():
                        try:
                            vals.append(float(t))
                        except ValueError:
                            break
                    if len(vals) >= 6:
                        best = vals[:6]
                    start = end + 6
                if best is not None:
                    return best
        return None

    def log_joints(self, tag):
        """Diagnose: aktuelle Achswinkel loggen. A5-Vorzeichen = Handgelenk-
        Konfiguration, A6 = tatsaechlich gefahrener Drehwinkel."""
        j = self.read_joints()
        if j is None:
            snippet = self._buf.decode("ascii", errors="replace")[-160:]
            print(f"   [JOINTS {tag:9}] <keine POSJOINT-Daten>  RAW: {snippet!r}")
        else:
            print(f"   [JOINTS {tag:9}] "
                  f"A1={j[0]:7.2f} A2={j[1]:7.2f} A3={j[2]:7.2f} "
                  f"A4={j[3]:7.2f} A5={j[4]:7.2f} A6={j[5]:7.2f}")


# ==============================================================================
#  HAUPTABLAUF
# ==============================================================================

def main():
    eye    = EyePlusClient(EYE_IP, EYE_PORT)
    poller = EyePlusPoller(EYE_IP, EYE_PORT)
    robot  = CriRobot(ROBOT_IP, ROBOT_PORT)

    print("=" * 64)
    print("  Pick-and-Place  (echte Hardware)")
    print(f"  Teile: {NUM_PARTS}   |   EYE+: {EYE_IP}:{EYE_PORT}"
          f"   |   Roboter: {ROBOT_IP}:{ROBOT_PORT}")
    print("=" * 64)

    try:
        # --- 1. Verbinden ---
        eye.connect()
        poller.connect()
        robot.connect()
        robot.init()
        robot.set_override(MOVE_VELOCITY)

        # --- 2. Recipe-Liste -> Production starten ---
        recipe_id = RECIPE_ID_PROD
        recipes = eye.get_recipe_list()
        print(f"\n[EYE+] {len(recipes)} Rezept(e) gefunden:")
        for i, (rid, name) in enumerate(recipes):
            mark = "  <== AKTIV" if str(rid) == recipe_id else ""
            print(f"  [{i}]  {rid}  '{name}'{mark}")
        if recipes and not any(str(rid) == recipe_id for rid, _ in recipes):
            raise RuntimeError(
                f"Rezept-ID {recipe_id} nicht in der EYE+-Rezeptliste gefunden."
            )
        eye.start_production(recipe_id)

        # --- 3. Erstes Bild + ggf. Cube befuellen ---
        eye.force_take_image()
        print("\n>>> Erstes Bild: liegt ein Teil bereit?")
        found, x, y, rz = eye.get_part()

        if not found:
            print(f"[FILL] Kein Teil -> Feeder '{FILL_FEEDER_CMD}'.")
            eye.send(FILL_FEEDER_CMD)
            time.sleep(FILL_WAIT_S)
            eye.force_take_image()
            found, x, y, rz = eye.get_part()
        else:
            print("[FILL] Teile vorhanden -> kein Fuellen noetig.")

        # --- 4. Pick-and-Place Schleife ---
        picked    = 0
        next_part = (found, x, y, rz) if found else None

        # Definierte Start-Konfiguration: einmal ueber SAFE-TO-ROTATE fahren,
        # damit die erste SAFE-TO-PICK-Anfahrt reproduzierbar dieselbe
        # Handgelenk-Konfiguration liefert wie alle folgenden (sonst koennte das
        # erste Teil in einer geflippten Konfiguration gegriffen werden).
        print("  Schritt: definierte Start-Konfiguration (SAFE-TO-ROTATE)")
        robot.move_joints(list(SAFE_ROTATE_JOINTS))

        while picked < NUM_PARTS:

            # Kandidat sicherstellen
            if next_part is None or not next_part[0]:
                found, x, y, rz = eye.get_part()
                next_part = (found, x, y, rz)

            if not next_part[0]:
                print("[LOOP] Kein Kandidat -> nachfuellen + neuer Versuch.")
                eye.send(FILL_FEEDER_CMD)
                time.sleep(FILL_WAIT_S)
                eye.force_take_image()
                found, x, y, rz = eye.get_part()
                next_part = (found, x, y, rz)
                if not next_part[0]:
                    print("[LOOP] Weiterhin kein Teil -> warte erneut.")
                    continue

            found, x, y, rz = next_part

            print(f"\n#################  Teil {picked + 1}/{NUM_PARTS}"
                  f"  (x={x:.1f}  y={y:.1f}  rz={rz:.1f})  #################")

            print("  Schritt: SAFE-TO-PICK anfahren")
            robot.move_cartesian(PICK_CENTER_X, PICK_CENTER_Y, SAFE_PICK_Z,
                                 TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN)
            robot.log_joints("safe-pick")

            # Absolute kartesische Anfahrt (bewaehrt). Die zuvor getestete
            # RelativeBase-Fahrt in X/Y hat den MNE_OC-Fehler ausgeloest
            # (Singularitaet / nicht ausfuehrbare Konfiguration). Erst per
            # Diagnose klaeren, WO der 180-Grad-Flip entsteht, dann gezielt fixen.
            print("  Schritt: ueber Teil + auf Greifhoehe, greifen (rz per A6)")
            robot.move_cartesian(x, y, SAFE_PICK_Z,
                                 TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN)
            robot.move_cartesian(x, y, GRIP_Z,
                                 TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN)
            robot.log_joints("vor-A6")
            # Teil-Drehung rz nur ueber A6 (Greifer bleibt senkrecht). A6 bleibt
            # zunaechst gedreht: erst senkrecht hochfahren, dann auf dem Weg zur
            # Safe-To-Rotate-Position die Orientierung korrigieren (A6 zurueck).
            # 90-Grad = fester Greifer-Montage-Offset zwischen rz und A6.
            a6 = 90.0 - rz
            # Auf (-180, 180] normalisieren: rz in (-180, 180] ergibt sonst
            # a6 in [-90, 270) -- Werte > 180 liegen ausserhalb des A6-
            # Verfahrbereichs, der Controller weicht dann auf eine
            # Ersatzloesung aus (Ursache fuer 180-Grad-Fehlgriffe).
            # a6 - 360 ist dieselbe Orientierung, also greif-identisch.
            if a6 > 180.0:
                a6 -= 360.0
            print(f"   [DIAG      ] rz={rz:.2f} -> a6 kommandiert={a6:.2f}")
            robot.rotate_a6(a6)
            robot.log_joints("greif")
            robot.gripper(close=True)

            print("  Schritt: senkrecht hoch (Greifer-Orientierung gehalten)")
            robot.move_base_relative(0.0, 0.0, SAFE_PICK_Z - GRIP_Z)

            print("  Schritt: Orientierung korrigieren (A6 zurueck)")
            robot.rotate_a6(-a6)
            robot.log_joints("derot")

            print("  Schritt: einfahren -> SAFE-TO-ROTATE")
            rotate_base = list(SAFE_ROTATE_JOINTS)
            robot.move_joints(rotate_base)

            # Erst jetzt (Arm in Safe-To-Rotate, weg von der Platte) das
            # naechste Teil analysieren lassen -- sonst stoert der Arm ueber der
            # Platte die Bildaufnahme. Laeuft parallel zum Ablegen (Pipelining).
            if picked + 1 < NUM_PARTS:
                eye.prepare_part()

            print(f"  Schritt: A1 drehen {ROTATE_DEG:.0f} Grad")
            a1_target = rotate_base[0] + ROTATE_DEG
            rotated   = robot.set_axis(0, a1_target, rotate_base)

            place_x = PLACE_X_START + picked * PLACE_X_STEP

            print(f"  Schritt: ausfahren + ablegen  X={place_x:.1f}  Y={PLACE_Y:.1f}")
            robot.move_cartesian(place_x, PLACE_Y, PLACE_Z_SAFE,
                                 TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN)
            robot.move_cartesian(place_x, PLACE_Y, PLACE_Z_DROP,
                                 TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN)
            robot.gripper(close=False)
            robot.move_cartesian(place_x, PLACE_Y, PLACE_Z_SAFE,
                                 TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN)

            print("  Schritt: einfahren Safe-Rotate (A1 noch rotiert)")
            robot.move_joints(rotated)

            print("  Schritt: A1 zurueckrotieren -> Safe-Rotate")
            robot.set_axis(0, rotate_base[0], rotated)

            picked += 1

            # Vor naechstem SAFE-TO-PICK: warten bis EYE+ Analyse fertig
            if picked < NUM_PARTS:
                print("[SYNC] warte, bis EYE+ Analyse fertig ist "
                      "(Arm soll Bild nicht stoeren) ...")
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
    except Exception as e:
        print(f"\n[FEHLER] {type(e).__name__}: {e}")
    finally:
        try:
            eye.stop_production()
        except Exception:
            pass
        eye.close()
        poller.close()
        robot.close()
        print("[ENDE] Verbindungen geschlossen.")


if __name__ == "__main__":
    main()
