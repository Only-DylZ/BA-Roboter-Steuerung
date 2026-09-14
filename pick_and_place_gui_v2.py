#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pick & Place GUI — Asyril EYE+ + igus ReBeL 6-DOF
Simulation (iRC-Sim) und Produktion (echte Hardware) in einem Fenster.
"""

import queue
import socket
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from libs.CRI_Python_Lib.cri_lib import CRIController, CRIConnectionError
    CRI_AVAILABLE = True
except ImportError:
    CRI_AVAILABLE = False
    CRIController = None
    CRIConnectionError = Exception


# ══════════════════════════════════════════════════════════════════════════════
#  REZEPT-IDs  (Asyril EYE+)
# ══════════════════════════════════════════════════════════════════════════════
#  Test-Modus    -> Rezept_Testmodus
#  Normal/Endlos -> Rezept_Produktion
RECIPE_ID_TEST = "11818"   # Rezept_Testmodus
RECIPE_ID_PROD = "23217"   # Rezept_Produktion


# ══════════════════════════════════════════════════════════════════════════════
#  STANDARD-PARAMETER  (zwei Sätze)
# ══════════════════════════════════════════════════════════════════════════════

# Diese beiden Dicts sind nur die FALLBACK-Werte (fuer UI-Felder, die es in den
# Skripten nicht als Konstante gibt, z.B. Endlos-/Test-Modus). Die eigentlichen
# Standardwerte kommen aus den Skript-Konstanten oben in pick_and_placeV1.py
# (Produktion) bzw. pick_and_placeV1_SIM.py (Simulation) -- siehe unten. Aenderst
# du dort einen Wert, aendert sich auch der UI-Standard. UI-Eingaben sind nur
# temporaere Overrides.
DEFAULTS_SIM_BASE = {
    "eye_ip":           "",
    "eye_port":         "",
    "robot_ip":         "127.0.0.1",
    "robot_port":       "3921",
    "num_parts":        "4",
    "endlos":           "0",
    "test_mode":        "0",
    "endlos_x":         "0.0",    # = place_x (erster Ablageort)
    "endlos_y":         "-300.0", # = place_y
    "endlos_z_safe":    "150.0",
    "endlos_z_drop":    "140.0",
    "pick_cx":          "440.0",
    "pick_cy":          "-5.0",
    "safe_pick_z":      "150.0",
    "grip_z":           "140.0",
    "tool_a":           "180.0",
    "tool_b":           "0.0",
    "tool_c":           "180.0",
    "rotate_deg":       "-90.0",
    "safe_joints":      "0.0 -18.7 108.0 0.0 90.0 0.0",
    "place_x":          "0.0",
    "place_x_step":     "50.0",
    "place_y":          "-300.0",
    "place_z_safe":     "150.0",
    "place_z_drop":     "140.0",
    "min_parts":        "1",
    "fill_cmd":         "feeder 1",
    "fill_wait":        "2.0",
    "velocity":         "80.0",
    # Genauigkeitstest (zwei Ablageorte + Anfahr-Offset)
    "acc_p1x":          "0.0",
    "acc_p1y":          "-300.0",
    "acc_p1z":          "140.0",
    "acc_p2x":          "100.0",
    "acc_p2y":          "-300.0",
    "acc_p2z":          "140.0",
    "acc_offset":       "20.0",
}

DEFAULTS_PROD_BASE = {
    "eye_ip":           "192.168.3.20",
    "eye_port":         "7171",
    "robot_ip":         "192.168.3.11",
    "robot_port":       "3920",
    "num_parts":        "4",
    "endlos":           "0",
    "test_mode":        "0",
    "endlos_x":         "0.0",
    "endlos_y":         "-300.0",
    "endlos_z_safe":    "150.0",
    "endlos_z_drop":    "140.0",
    "pick_cx":          "440.0",
    "pick_cy":          "-5.0",
    "safe_pick_z":      "150.0",
    "grip_z":           "140.0",
    "tool_a":           "180.0",
    "tool_b":           "0.0",
    "tool_c":           "180.0",
    "rotate_deg":       "-90.0",
    "safe_joints":      "0.0 -18.7 108.0 0.0 90.0 0.0",
    "place_x":          "0.0",
    "place_x_step":     "50.0",
    "place_y":          "-300.0",
    "place_z_safe":     "150.0",
    "place_z_drop":     "140.0",
    "min_parts":        "1",
    "fill_cmd":         "feeder 1",
    "fill_wait":        "2.0",
    "velocity":         "80.0",
    # Genauigkeitstest (zwei Ablageorte + Anfahr-Offset)
    "acc_p1x":          "0.0",
    "acc_p1y":          "-300.0",
    "acc_p1z":          "140.0",
    "acc_p2x":          "100.0",
    "acc_p2y":          "-300.0",
    "acc_p2z":          "140.0",
    "acc_offset":       "20.0",
}

# Genauigkeitstest-Defaults (eigener Modus). Netzwerk/Werkzeug/Safe-Joints wie
# Produktion; die Ablageorte kommen aus genauigkeitstestV1.py.
DEFAULTS_ACC_BASE = {
    "eye_ip":           "",
    "eye_port":         "",
    "robot_ip":         "192.168.3.11",
    "robot_port":       "3920",
    "num_parts":        "4",
    "endlos":           "0",
    "test_mode":        "0",
    "endlos_x":         "0.0",
    "endlos_y":         "-300.0",
    "endlos_z_safe":    "150.0",
    "endlos_z_drop":    "140.0",
    "pick_cx":          "440.0",
    "pick_cy":          "-5.0",
    "safe_pick_z":      "150.0",
    "grip_z":           "140.0",
    "tool_a":           "180.0",
    "tool_b":           "0.0",
    "tool_c":           "180.0",
    "rotate_deg":       "-90.0",
    "safe_joints":      "0.0 -18.7 108.0 0.0 90.0 0.0",
    "place_x":          "0.0",
    "place_x_step":     "50.0",
    "place_y":          "-300.0",
    "place_z_safe":     "150.0",
    "place_z_drop":     "140.0",
    "min_parts":        "1",
    "fill_cmd":         "feeder 1",
    "fill_wait":        "2.0",
    "velocity":         "60.0",
    "acc_p1x":          "0.0",
    "acc_p1y":          "-300.0",
    "acc_p1z":          "140.0",
    "acc_p2x":          "100.0",
    "acc_p2y":          "-300.0",
    "acc_p2z":          "140.0",
    "acc_offset":       "20.0",
}


# ── Standardwerte aus den Skript-Konstanten ───────────────────────────────────
# Mapping: UI-Feld  ->  Konstantenname oben im jeweiligen Skript.
# Felder, die hier nicht auftauchen (endlos*, test_mode), behalten den Fallback.
_SCRIPT_PARAM_MAP = {
    "eye_ip":       "EYE_IP",
    "eye_port":     "EYE_PORT",
    "robot_ip":     "ROBOT_IP",
    "robot_port":   "ROBOT_PORT",
    "num_parts":    "NUM_PARTS",
    "pick_cx":      "PICK_CENTER_X",
    "pick_cy":      "PICK_CENTER_Y",
    "safe_pick_z":  "SAFE_PICK_Z",
    "grip_z":       "GRIP_Z",
    "tool_a":       "TOOL_A_DOWN",
    "tool_b":       "TOOL_B_DOWN",
    "tool_c":       "TOOL_C_DOWN",
    "rotate_deg":   "ROTATE_DEG",
    "safe_joints":  "SAFE_ROTATE_JOINTS",
    "place_x":      "PLACE_X_START",
    "place_x_step": "PLACE_X_STEP",
    "place_y":      "PLACE_Y",
    "place_z_safe": "PLACE_Z_SAFE",
    "place_z_drop": "PLACE_Z_DROP",
    "min_parts":    "MIN_PARTS_ON_PLATE",
    "fill_cmd":     "FILL_FEEDER_CMD",
    "fill_wait":    "FILL_WAIT_S",
    "velocity":     "MOVE_VELOCITY",
}


def _fmt_default(val):
    # UI-Vars sind StringVars -> alles zu String. Listen (z.B. Safe-Joints)
    # werden leerzeichengetrennt, damit sie zum UI-Format passen.
    if isinstance(val, (list, tuple)):
        return " ".join(_fmt_default(v) for v in val)
    return str(val)


# Mapping fuer den Genauigkeitstest -> Konstanten in genauigkeitstestV1.py.
_ACC_PARAM_MAP = {
    "robot_ip":   "ROBOT_IP",
    "robot_port": "ROBOT_PORT",
    "tool_a":     "TOOL_A_DOWN",
    "tool_b":     "TOOL_B_DOWN",
    "tool_c":     "TOOL_C_DOWN",
    "safe_joints": "SAFE_ROTATE_JOINTS",
    "velocity":   "MOVE_VELOCITY",
    "acc_p1x":    "PLACE1_X",
    "acc_p1y":    "PLACE1_Y",
    "acc_p1z":    "PLACE1_Z",
    "acc_p2x":    "PLACE2_X",
    "acc_p2y":    "PLACE2_Y",
    "acc_p2z":    "PLACE2_Z",
    "acc_offset": "SAFE_Z_OFFSET",
}


def _defaults_from_script(base, module, param_map=None):
    # Startet von den Fallback-Werten und ueberschreibt jedes Feld, fuer das im
    # Skript eine Konstante existiert. Fehlt das Modul (Import fehlgeschlagen)
    # oder eine Konstante, bleibt der Fallback erhalten.
    if param_map is None:
        param_map = _SCRIPT_PARAM_MAP
    d = dict(base)
    if module is not None:
        for gui_key, attr in param_map.items():
            if hasattr(module, attr):
                d[gui_key] = _fmt_default(getattr(module, attr))
    return d


try:
    import pick_and_placeV1 as _prod_script
except Exception:
    _prod_script = None
try:
    import pick_and_placeV1_SIM as _sim_script
except Exception:
    _sim_script = None
try:
    import genauigkeitstestV1 as _acc_script
except Exception:
    _acc_script = None

DEFAULTS_SIM  = _defaults_from_script(DEFAULTS_SIM_BASE,  _sim_script)
DEFAULTS_PROD = _defaults_from_script(DEFAULTS_PROD_BASE, _prod_script)
DEFAULTS_ACC  = _defaults_from_script(DEFAULTS_ACC_BASE,  _acc_script, _ACC_PARAM_MAP)


class _StopException(Exception):
    pass


# ══════════════════════════════════════════════════════════════════════════════
#  EYE+ CLIENT  (Produktion)
# ══════════════════════════════════════════════════════════════════════════════

class EyePlusClient:
    def __init__(self, ip, port, log_fn=None, timeout=35.0, cmd_log_fn=None):
        self.ip        = ip
        self.port      = port
        self.timeout   = timeout
        self._log      = log_fn or (lambda t, tag=None: print(t))
        self._cmd_log  = cmd_log_fn   # logs raw protocol to EYE+ terminal
        self.sock      = None
        self._buf      = b""
        self._lock     = threading.Lock()

    def connect(self):
        self.sock = socket.create_connection((self.ip, self.port), timeout=10)
        self.sock.settimeout(self.timeout)
        self._log(f"[EYE+] verbunden  {self.ip}:{self.port}", "ok")

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
            if self._cmd_log:
                self._cmd_log(f">>> {command}", "cmd_out")
            first = self._read_line()
        parts = first.split(" ")
        code  = int(parts[0])
        rest  = parts[1:]
        if rest and rest[0].isdigit():
            nlines  = int(rest[0])
            payload = [" ".join(rest[1:])] if len(rest) > 1 else []
            for _ in range(max(0, nlines - len(payload))):
                payload.append(self._read_line())
            if self._cmd_log:
                self._cmd_log(f"<<< {code}  {' '.join(payload)}", "cmd_in")
            return code, payload
        if self._cmd_log:
            self._cmd_log(f"<<< {code}  {' '.join(rest)}", "cmd_in")
        return code, rest

    def get_recipe_list(self):
        code, payload = self.send("get_recipe_list")
        if not (200 <= code < 300):
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
        if not (200 <= code < 300):
            raise RuntimeError(f"[EYE+] start production -> {code} {payload}")
        self._log(f"[EYE+] Production gestartet  (Recipe {recipe_id})", "ok")

    def stop_production(self):
        code, _ = self.send("stop production")
        self._log(f"[EYE+] stop production -> {code}", "info")

    def force_take_image(self):
        code, _ = self.send("force_take_image")
        return 200 <= code < 300

    def prepare_part(self):
        return self.send("prepare_part")

    def get_part(self):
        code, payload = self.send("get_part")
        if not (200 <= code < 300):
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
            # Greifer dreht max. 180 Grad; bei rz > 180 wuerde er ueberdrehen.
            if rz > 180.0:
                rz -= 180.0
            return True, fields["x"], fields["y"], rz
        return False, None, None, None


class EyePlusPoller:
    def __init__(self, ip, port, status_log_fn=None):
        self._status_log  = status_log_fn
        self._last_state  = None
        self.client = EyePlusClient(ip, port,
                                    log_fn=lambda t, tag=None: None,
                                    timeout=10.0)

    def connect(self):
        self.client.connect()

    def close(self):
        self.client.close()

    def is_analysis_running(self):
        try:
            code, payload = self.client.send("get_parameter is_analysis_running")
            if not (200 <= code < 300):
                result = False
            else:
                result = "true" in " ".join(payload).lower()
        except Exception:
            result = False
        if self._status_log and result != self._last_state:
            self._last_state = result
            if result:
                self._status_log("  Analyse laeuft ...", "running")
            else:
                self._status_log("  Analyse fertig.", "done")
        return result


# ══════════════════════════════════════════════════════════════════════════════
#  SIMULIERTER EYE+  (Simulation)
# ══════════════════════════════════════════════════════════════════════════════

class SimulatedEyePlus:
    def __init__(self, request_coord_fn, log_fn=None):
        self._request_coord    = request_coord_fn
        self._log              = log_fn or (lambda t, tag=None: print(t))
        self._analysis_running = False
        self._lock             = threading.Lock()
        self._fake_recipes     = [
            (RECIPE_ID_TEST, "Rezept_Testmodus"),
            (RECIPE_ID_PROD, "Rezept_Produktion"),
        ]

    def connect(self):
        self._log("[SIM-EYE+] simuliert — keine echte Verbindung noetig.", "info")

    def close(self):
        pass

    def get_recipe_list(self):
        self._log("[SIM-EYE+] get_recipe_list (simuliert).", "info")
        return list(self._fake_recipes)

    def start_production(self, recipe_id):
        self._log(f"[SIM-EYE+] start production {recipe_id} -> OK (200)", "ok")

    def stop_production(self):
        self._log("[SIM-EYE+] stop production -> OK", "info")

    def force_take_image(self):
        self._log("[SIM-EYE+] force_take_image (simuliert).", "info")
        return True

    def prepare_part(self):
        def _run():
            with self._lock:
                self._analysis_running = True
            time.sleep(1.0)
            with self._lock:
                self._analysis_running = False
        self._log("[SIM-EYE+] prepare_part -> Analyse gestartet.", "info")
        threading.Thread(target=_run, daemon=True).start()
        return 200, []

    def is_analysis_running(self):
        with self._lock:
            return self._analysis_running

    def get_part(self):
        self._log("\n" + "─" * 50, None)
        self._log("  EYE+ get_part  ->  Koordinaten eingeben:", "info")
        self._log("  Format:  x  y  rz    (z.B.  440 -5 0)", "info")
        self._log("  Leer + OK  =  kein Teil gefunden", "info")
        self._log("─" * 50, None)
        raw = self._request_coord()
        if not raw:
            self._log("  -> kein Teil erkannt.", "warn")
            return False, None, None, None
        toks = raw.replace(",", " ").split()
        try:
            x  = float(toks[0])
            y  = float(toks[1])
            rz = float(toks[2]) if len(toks) >= 3 else 0.0
        except (IndexError, ValueError):
            self._log("  [!] Ungueltige Eingabe -> kein Teil.", "err")
            return False, None, None, None
        # Greifer dreht max. 180 Grad; bei rz > 180 wuerde er ueberdrehen.
        if rz > 180.0:
            rz -= 180.0
        self._log(f"  -> Teil: x={x:.2f}  y={y:.2f}  rz={rz:.2f}", "ok")
        return True, x, y, rz

    def send(self, command):
        self._log(f"[SIM-EYE+] Feeder-Befehl: {command} (simuliert).", "info")
        return 200, []


class SimEyePoller:
    def __init__(self, sim_eye):
        self._eye = sim_eye

    def connect(self):
        pass

    def close(self):
        pass

    def is_analysis_running(self):
        return self._eye.is_analysis_running()


# ══════════════════════════════════════════════════════════════════════════════
#  CRI ROBOT  (Produktion — eigener Client ohne externe Lib)
# ══════════════════════════════════════════════════════════════════════════════

class CriRobot:
    def __init__(self, ip, port, log_fn=None):
        self.ip      = ip
        self.port    = port
        self._log    = log_fn or (lambda t, tag=None: print(t))
        self.sock    = None
        self._buf    = b""
        self._msg_id = 1
        self._lock   = threading.Lock()
        self._alive  = False

    def connect(self):
        self.sock = socket.create_connection((self.ip, self.port), timeout=10)
        self.sock.settimeout(15.0)
        self._alive = True
        self._log(f"[ROBOT] verbunden  {self.ip}:{self.port}", "ok")
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
        self._log("[ROBOT] SetActive + Reset + Enable", "ok")

    def move_cartesian(self, x, y, z, a, b, c, velocity=30.0):
        body = (f"CMD Move Cart "
                f"{x:.3f} {y:.3f} {z:.3f} {a:.3f} {b:.3f} {c:.3f} "
                f"0.0 0.0 0.0 {velocity:.1f}")
        self._send_raw(body)
        self._log(
            f"   [Cart ] X={x:7.1f} Y={y:7.1f} Z={z:6.1f}"
            f"  A={a:5.1f} B={b:5.1f} C={c:6.1f}", "move")
        self._wait_motion_done()

    def move_joints(self, joints, velocity=30.0):
        j    = " ".join(f"{v:.3f}" for v in joints)
        body = f"CMD Move Joint {j} 0.0 0.0 0.0 {velocity:.1f}"
        self._send_raw(body)
        js = " ".join(f"{v:5.1f}" for v in joints)
        self._log(f"   [Joint] [{js}]", "move")
        self._wait_motion_done()

    def set_axis(self, axis_index, value, base_joints, velocity=30.0):
        joints             = list(base_joints)
        joints[axis_index] = value
        self.move_joints(joints, velocity)
        return joints

    def rotate_a6(self, deg, velocity=100.0):
        # Dreht nur A6 relativ (Wrist), Greifer bleibt senkrecht. So wird die
        # Teil-Orientierung rz realisiert, ohne die kartesische Orientierung zu
        # aendern (vermeidet das A6-Ueberdrehen durch IK-Mehrdeutigkeit).
        body = (f"CMD Move RelativeJoint 0.0 0.0 0.0 0.0 0.0 {deg:.3f} "
                f"0.0 0.0 0.0 {velocity:.1f}")
        self._send_raw(body)
        self._log(f"   [A6 rel] {deg:+.1f} Grad", "move")
        self._wait_motion_done()

    def move_base_relative(self, dx, dy, dz, velocity=30.0):
        # Relative kartesische Bewegung im Basis-Koordinatensystem. Orientierung
        # bleibt unveraendert (A=B=C=0) -> A6 bleibt gehalten. So kann das Teil
        # senkrecht hochgezogen werden, ohne dass die IK die Greifer-Drehung
        # (A6) vorzeitig zurueckdreht.
        body = (f"CMD Move RelativeBase "
                f"{dx:.3f} {dy:.3f} {dz:.3f} 0.0 0.0 0.0 "
                f"0.0 0.0 0.0 {velocity:.1f}")
        self._send_raw(body)
        self._log(f"   [RelB ] dX={dx:+.1f} dY={dy:+.1f} dZ={dz:+.1f}", "move")
        self._wait_motion_done()

    def set_override(self, percentage: float):
        self._send_raw(f"CMD Override {percentage:.0f}", wait_answer=False)
        self._log(f"[ROBOT] Override gesetzt: {percentage:.0f} %", "ok")

    def gripper(self, close):
        self._send_raw("CMD SetActive true", wait_answer=False)
        self._send_raw(f"CMD DOUT 30 {'true' if close else 'false'}")
        self._send_raw(f"CMD DOUT 31 {'false' if close else 'true'}")
        action = "SCHLIESSEN (greifen)" if close else "OEFFNEN (loslassen)"
        self._log(f"   [Greifer] {action}", "ok" if close else "info")
        time.sleep(1.2)   # warten bis Greifer-Mechanik fertig, bevor weiterbewegt wird

    def _wait_motion_done(self, timeout=120.0):
        # Warten bis der Controller das Bewegungsende meldet (EXECEND-Frame).
        # Der vorausgegangene _send_raw hat den Puffer bereits geleert, daher
        # kann hier kein altes EXECEND einer frueheren Bewegung haengenbleiben.
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
        self._log("[ROBOT] WARN: Timeout beim Warten auf Bewegungsende (EXECEND).",
                  "warn")


# ══════════════════════════════════════════════════════════════════════════════
#  CRI CONTROLLER WRAPPER  (Simulation — wraps CRIController)
# ══════════════════════════════════════════════════════════════════════════════

class CriControllerWrapper:
    def __init__(self, ip, port, log_fn=None):
        self.ip    = ip
        self.port  = port
        self._log  = log_fn or (lambda t, tag=None: print(t))
        self._ctrl = CRIController() if CRI_AVAILABLE else None

    def connect(self):
        self._ctrl.connect(host=self.ip, port=self.port)
        self._log(f"[ROBOT] verbunden  {self.ip}:{self.port}", "ok")

    def close(self):
        for fn in (
            lambda: self._ctrl.disable(),
            lambda: self._ctrl.set_active_control(False),
            lambda: self._ctrl.close(),
        ):
            try:
                fn()
            except Exception:
                pass

    def init(self):
        self._log("[ROBOT] Warte auf Kinematik ...", "info")
        if not self._ctrl.wait_for_kinematics_ready(timeout=30):
            raise RuntimeError("Kinematik nicht bereit (Timeout 30 s).")
        if not self._ctrl.set_active_control(True):
            raise RuntimeError("Active Control fehlgeschlagen.")
        self._ctrl.reset()
        if not self._ctrl.enable():
            raise RuntimeError("Enable fehlgeschlagen.")
        self._log("[ROBOT] bereit.", "ok")

    def move_cartesian(self, x, y, z, a, b, c, velocity=80.0):
        ok = self._ctrl.move_cartesian(
            X=x, Y=y, Z=z, A=a, B=b, C=c,
            E1=0.0, E2=0.0, E3=0.0,
            velocity=velocity, wait_move_finished=True,
        )
        if not ok:
            raise RuntimeError("Kartesische Bewegung fehlgeschlagen.")
        self._log(
            f"   [Cart ] X={x:7.1f} Y={y:7.1f} Z={z:6.1f}"
            f"  A={a:5.1f} B={b:5.1f} C={c:6.1f}", "move")

    def move_joints(self, joints, velocity=80.0):
        a1, a2, a3, a4, a5, a6 = joints
        ok = self._ctrl.move_joints(
            A1=a1, A2=a2, A3=a3, A4=a4, A5=a5, A6=a6,
            E1=0.0, E2=0.0, E3=0.0,
            velocity=velocity, wait_move_finished=True,
        )
        if not ok:
            raise RuntimeError("Gelenkbewegung fehlgeschlagen.")
        js = " ".join(f"{v:5.1f}" for v in joints)
        self._log(f"   [Joint] [{js}]", "move")

    def set_axis(self, axis_index, value, base_joints, velocity=80.0):
        joints             = list(base_joints)
        joints[axis_index] = value
        self.move_joints(joints, velocity)
        return joints

    def rotate_a6(self, deg, velocity=100.0):
        # Dreht nur A6 relativ (Wrist), Greifer bleibt senkrecht.
        ok = self._ctrl.move_joints_relative(
            A1=0.0, A2=0.0, A3=0.0, A4=0.0, A5=0.0, A6=deg,
            E1=0.0, E2=0.0, E3=0.0,
            velocity=velocity, wait_move_finished=True,
        )
        if not ok:
            raise RuntimeError("A6-Drehung fehlgeschlagen.")
        self._log(f"   [A6 rel] {deg:+.1f} Grad", "move")

    def move_base_relative(self, dx, dy, dz, velocity=80.0):
        # Relative kartesische Bewegung im Basis-Koordinatensystem; Orientierung
        # bleibt gehalten (A6 bleibt gedreht). Senkrechtes Hochziehen ohne dass
        # die IK die Greifer-Drehung vorzeitig zurueckdreht.
        ok = self._ctrl.move_base_relative(
            X=dx, Y=dy, Z=dz, A=0.0, B=0.0, C=0.0,
            E1=0.0, E2=0.0, E3=0.0,
            velocity=velocity, wait_move_finished=True,
        )
        if not ok:
            raise RuntimeError("Relative Basisbewegung fehlgeschlagen.")
        self._log(f"   [RelB ] dX={dx:+.1f} dY={dy:+.1f} dZ={dz:+.1f}", "move")

    def set_override(self, percentage: float):
        ok = self._ctrl.set_override(percentage)
        if ok:
            self._log(f"[ROBOT] Override gesetzt: {percentage:.0f} %", "ok")
        else:
            self._log(f"[ROBOT] Override setzen fehlgeschlagen!", "warn")

    def gripper(self, close):
        self._ctrl.set_active_control(True)
        self._ctrl.set_dout(30, close)
        self._ctrl.set_dout(31, not close)
        time.sleep(1.2)   # warten bis Greifer-Mechanik fertig, bevor weiterbewegt wird
        action = "SCHLIESSEN (greifen)" if close else "OEFFNEN (loslassen)"
        self._log(f"   [Greifer] {action}", "ok" if close else "info")


# ══════════════════════════════════════════════════════════════════════════════
#  HAUPT-APP
# ══════════════════════════════════════════════════════════════════════════════

class PickPlaceApp:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Pick & Place  |  Asyril EYE+  +  igus ReBeL 6-DOF")
        self.root.minsize(1080, 680)

        self._log_q       = queue.Queue()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._stop_event  = threading.Event()
        self._worker: threading.Thread | None = None

        self._mode = tk.StringVar(value="sim")

        self._vars: dict[str, tk.StringVar] = {
            k: tk.StringVar(value=v) for k, v in DEFAULTS_SIM.items()
        }

        self._coord_event    = threading.Event()
        self._coord_result: str | None = None
        self._eye_entries:  list       = []
        self._robot_ref:    object | None = None
        self._test_cb_widget = None

        # Asyril-Rezept-Auswahl (nur Produktion). Liste der (id, name)-Tupel und
        # die im Dropdown gewaehlte Anzeige.
        self._recipes: list[tuple[str, str]] = []
        self._recipe_var = tk.StringVar()
        self._recipe_combo = None
        self._recipe_sec   = None
        # Merkt sich, ob die Rezeptliste in dieser Sitzung schon automatisch
        # geladen wurde -> Auto-Laden feuert nur einmal.
        self._recipe_autoloaded = False

        self._build_ui()
        self._poll()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(2, weight=1)

        # Titelzeile
        tb = tk.Frame(self.root, bg="#1c3f6e")
        tb.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(
            tb,
            text="  Pick & Place Steuerung  —  Asyril EYE+  +  igus ReBeL 6-DOF",
            bg="#1c3f6e", fg="white",
            font=("Segoe UI", 11, "bold"), pady=6,
        ).pack(side="left")

        # Modus-Leiste
        self._mode_bar = tk.Frame(self.root, pady=6, padx=10)
        self._mode_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self._mode_bar.columnconfigure(4, weight=1)

        tk.Label(self._mode_bar, text="Modus:",
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0, padx=(0, 10))

        for col, val, lbl in [
            (1, "sim",  "Simulation  (iRC-Sim + simulierter EYE+)"),
            (2, "prod", "Produktion  (echte Hardware)"),
            (3, "acc",  "Genauigkeitstest  (Roboter ohne EYE+)"),
        ]:
            tk.Radiobutton(
                self._mode_bar,
                text=lbl, variable=self._mode, value=val,
                command=self._on_mode_change,
                font=("Segoe UI", 9),
            ).grid(row=0, column=col, padx=(0, 20))

        self._file_var = tk.StringVar()
        tk.Label(self._mode_bar, textvariable=self._file_var,
                 font=("Segoe UI", 9, "italic"), fg="#555").grid(
            row=0, column=4, sticky="w")

        ttk.Separator(self.root).grid(row=1, column=0, columnspan=2,
                                      sticky="sew")

        # ── Linke Spalte (scrollbar) ──────────────────────────────────────────
        outer = ttk.Frame(self.root)
        outer.grid(row=2, column=0, sticky="ns", padx=(8, 0), pady=8)

        canv = tk.Canvas(outer, width=315, highlightthickness=0)
        sb   = ttk.Scrollbar(outer, orient="vertical", command=canv.yview)
        canv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canv.pack(side="left", fill="both", expand=True)

        left = ttk.Frame(canv, padding=(2, 2, 4, 4))
        win  = canv.create_window((0, 0), window=left, anchor="nw")
        left.bind("<Configure>",
                  lambda e: canv.configure(scrollregion=canv.bbox("all")))
        canv.bind("<Configure>",
                  lambda e: canv.itemconfig(win, width=e.width))
        canv.bind_all("<MouseWheel>",
                      lambda e: canv.yview_scroll(-1*(e.delta//120), "units"))

        pr = 0

        def sec(title):
            nonlocal pr
            lf = ttk.LabelFrame(left, text=title, padding=(8, 4, 8, 6))
            lf.grid(row=pr, column=0, sticky="ew", pady=(0, 6), padx=2)
            pr += 1
            return lf

        def fld(parent, label, key, row, col=0, w=10):
            ttk.Label(parent, text=label, anchor="w").grid(
                row=row, column=col*2, sticky="w", padx=(0, 4), pady=2)
            e = ttk.Entry(parent, textvariable=self._vars[key], width=w)
            e.grid(row=row, column=col*2+1, sticky="w", padx=(0, 8), pady=2)
            return e

        rf = ttk.Frame(left)
        rf.grid(row=pr, column=0, sticky="ew", padx=2, pady=(0, 4))
        pr += 1
        ttk.Button(rf, text="Standardwerte laden",
                   command=self._reset_defaults).pack(fill="x")

        # Netzwerk
        f = sec("Netzwerk")
        e1 = fld(f, "EYE+ IP:",    "eye_ip",     0, 0, 14)
        e2 = fld(f, "Port:",       "eye_port",   0, 1,  6)
        fld(f,     "Roboter IP:", "robot_ip",    1, 0, 14)
        fld(f,     "Port:",       "robot_port",  1, 1,  6)
        self._eye_entries = [e1, e2]

        f = sec("Aufgabe")
        self._sec_aufgabe = f
        fld(f, "Anzahl Teile:",  "num_parts",    0, 0, 6)
        ttk.Checkbutton(
            f, text="Endlos-Modus  (laeuft bis STOP)",
            variable=self._vars["endlos"], onvalue="1", offvalue="0",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 0))
        self._test_cb_widget = ttk.Checkbutton(
            f, text="Test-Modus  (Einzelgreiftest, kein Befuellen)",
            variable=self._vars["test_mode"], onvalue="1", offvalue="0",
        )
        self._test_cb_widget.grid(row=2, column=0, columnspan=4,
                                  sticky="w", pady=(2, 0))
        self._test_cb_widget.grid_remove()

        # Asyril-Rezept (nur Produktion, Normal-/Endlos-Modus). Im Test-Modus
        # wird weiterhin automatisch RECIPE_ID_TEST verwendet.
        self._recipe_sec = sec("Asyril Rezept  (Normal/Endlos)")
        self._recipe_sec.columnconfigure(0, weight=1)
        self._recipe_combo = ttk.Combobox(
            self._recipe_sec, textvariable=self._recipe_var,
            state="readonly", width=26, values=[])
        self._recipe_combo.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Button(self._recipe_sec, text="Rezeptliste laden",
                   command=self._load_recipe_list).grid(
            row=1, column=0, sticky="ew")
        # Vorbefuellen mit den bekannten Rezept-IDs, bis live geladen wird.
        self._set_recipe_values([
            (RECIPE_ID_PROD, "Rezept_Produktion"),
            (RECIPE_ID_TEST, "Rezept_Testmodus"),
        ])

        # ── Genauigkeitstest (nur Modus "acc") ────────────────────────────────
        f = sec("Genauigkeitstest  [mm]")
        self._sec_acc = f
        ttk.Label(f, text="Ablageort 1:", font=("Segoe UI", 8, "bold")).grid(
            row=0, column=0, columnspan=6, sticky="w", pady=(0, 1))
        fld(f, "X:", "acc_p1x", 1, 0, 8)
        fld(f, "Y:", "acc_p1y", 1, 1, 8)
        fld(f, "Z:", "acc_p1z", 1, 2, 8)
        ttk.Label(f, text="Ablageort 2:", font=("Segoe UI", 8, "bold")).grid(
            row=2, column=0, columnspan=6, sticky="w", pady=(6, 1))
        fld(f, "X:", "acc_p2x", 3, 0, 8)
        fld(f, "Y:", "acc_p2y", 3, 1, 8)
        fld(f, "Z:", "acc_p2z", 3, 2, 8)
        fld(f, "Anfahr-Offset Z:", "acc_offset", 4, 0, 8)

        f = sec("Pick-Geometrie  [mm]")
        self._sec_pickgeom = f
        fld(f, "Mitte X:",   "pick_cx",     0, 0, 8)
        fld(f, "Mitte Y:",   "pick_cy",     0, 1, 8)
        fld(f, "Z-Safe:",    "safe_pick_z", 1, 0, 8)
        fld(f, "Z-Greifen:", "grip_z",      1, 1, 8)

        f = sec("Werkzeug-Orientierung  [Grad]")
        fld(f, "A:", "tool_a", 0, 0, 7)
        fld(f, "B:", "tool_b", 0, 1, 7)
        fld(f, "C:", "tool_c", 0, 2, 7)

        f = sec("Rotation & Safe-Joints")
        fld(f, "A1-Drehung [Grad]:", "rotate_deg", 0, 0, 8)
        ttk.Label(f, text="Safe-Joints  A1..A6  (leerzeichen-getrennt):").grid(
            row=1, column=0, columnspan=6, sticky="w", pady=(6, 1))
        ttk.Entry(f, textvariable=self._vars["safe_joints"], width=28).grid(
            row=2, column=0, columnspan=6, sticky="ew")

        f = sec("Ablageposition  [mm]  (Normal-Modus)")
        self._sec_place_normal = f
        fld(f, "X-Start:",   "place_x",      0, 0, 8)
        fld(f, "X-Schritt:", "place_x_step", 0, 1, 8)
        fld(f, "Y:",         "place_y",      1, 0, 8)
        fld(f, "Z-Safe:",    "place_z_safe", 2, 0, 8)
        fld(f, "Z-Ablegen:", "place_z_drop", 2, 1, 8)

        f = sec("Ablageposition  [mm]  (Endlos-Modus)")
        self._sec_place_endlos = f
        fld(f, "X:",         "endlos_x",      0, 0, 8)
        fld(f, "Y:",         "endlos_y",      0, 1, 8)
        fld(f, "Z-Safe:",    "endlos_z_safe", 1, 0, 8)
        fld(f, "Z-Ablegen:", "endlos_z_drop", 1, 1, 8)

        f = sec("Cube-Fuellung")
        self._sec_cube = f
        fld(f, "Min. Teile auf Platte:", "min_parts", 0, 0, 4)
        fld(f, "Wartezeit [s]:",         "fill_wait", 0, 1, 5)
        ttk.Label(f, text="Feeder-Befehl:").grid(row=1, column=0, sticky="w", pady=(4, 1))
        ttk.Entry(f, textvariable=self._vars["fill_cmd"], width=20).grid(
            row=1, column=1, columnspan=3, sticky="ew")

        f = sec("Bewegungsparameter")
        fld(f, "Override / Geschwindigkeit [%]:", "velocity", 0, 0, 7)
        ttk.Button(f, text="Jetzt setzen",
                   command=self._update_override_live, width=13).grid(
            row=0, column=2, padx=(8, 0), pady=2)

        # ── Rechte Spalte (Terminal) ──────────────────────────────────────────
        right = ttk.Frame(self.root, padding=(8, 8, 8, 0))
        right.grid(row=2, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        hdr = ttk.Frame(right)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        hdr.columnconfigure(0, weight=1)
        ttk.Label(hdr, text="Live-Terminal",
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(hdr, text="Leeren", width=8,
                   command=self._clear_log).grid(row=0, column=1)

        led_robot_f = tk.Frame(hdr)
        led_robot_f.grid(row=0, column=2, padx=(16, 4))
        self._led_robot_dot = ttk.Label(led_robot_f, text="●", foreground="#d94f4f",
                                        font=("Segoe UI", 11))
        self._led_robot_dot.pack(side="left", padx=(0, 3))
        ttk.Label(led_robot_f, text="Roboter", font=("Segoe UI", 8)).pack(side="left")

        led_eye_f = tk.Frame(hdr)
        led_eye_f.grid(row=0, column=3, padx=(0, 6))
        self._led_eye_dot = ttk.Label(led_eye_f, text="●", foreground="#d94f4f",
                                      font=("Segoe UI", 11))
        self._led_eye_dot.pack(side="left", padx=(0, 3))
        ttk.Label(led_eye_f, text="EYE+", font=("Segoe UI", 8)).pack(side="left")
        self._led_eye_frame = led_eye_f

        mono = self._pick_mono()
        self._term = scrolledtext.ScrolledText(
            right, state="disabled", font=mono, wrap="none",
            bg="#0c0c0c", fg="#cccccc",
            insertbackground="white", selectbackground="#264f78",
        )
        self._term.grid(row=1, column=0, sticky="nsew")

        for tag, color in [
            ("err",  "#f48771"), ("ok",   "#6db96d"), ("info", "#9cdcfe"),
            ("move", "#4ec9b0"), ("warn", "#ce9178"), ("head", "#dcdcaa"),
            ("ts",   "#3a3a3a"),
        ]:
            self._term.tag_config(tag, foreground=color)

        # EYE+ Protokoll-Terminals (nur PROD)
        eye_sec = ttk.LabelFrame(right, text="EYE+ Protokoll", padding=(6, 4, 6, 6))
        eye_sec.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        eye_sec.columnconfigure(0, weight=1)
        eye_sec.columnconfigure(1, weight=1)
        self._eye_section_frame = eye_sec

        eye_hdr = ttk.Frame(eye_sec)
        eye_hdr.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 3))
        eye_hdr.columnconfigure(1, weight=1)
        ttk.Label(eye_hdr, text="Haupt-Client  (Befehle)",
                  font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(eye_hdr, text="Poller  (Analyse-Status)",
                  font=("Segoe UI", 8, "bold")).grid(row=0, column=1, sticky="w",
                                                      padx=(12, 0))
        self._btn_stop_prod = ttk.Button(eye_hdr, text="Stop Production",
                                         command=self._stop_production_live, width=18)
        self._btn_stop_prod.grid(row=0, column=2, padx=(12, 0))

        self._eye_main_term = scrolledtext.ScrolledText(
            eye_sec, state="disabled", font=mono, wrap="none",
            bg="#0c0c0c", fg="#cccccc", height=6,
        )
        self._eye_main_term.grid(row=1, column=0, sticky="ew", padx=(0, 4))

        self._eye_poll_term = scrolledtext.ScrolledText(
            eye_sec, state="disabled", font=mono, wrap="none",
            bg="#0c0c0c", fg="#cccccc", height=6,
        )
        self._eye_poll_term.grid(row=1, column=1, sticky="ew")

        for tag, color in [
            ("cmd_out", "#ce9178"), ("cmd_in", "#4ec9b0"),
            ("running", "#f48771"), ("done",   "#6db96d"),
            ("ts",      "#3a3a3a"),
        ]:
            self._eye_main_term.tag_config(tag, foreground=color)
            self._eye_poll_term.tag_config(tag, foreground=color)

        # Koordinaten-Eingabe (nur SIM)
        self._coord_frame = ttk.LabelFrame(
            right, text="EYE+ Koordinaten  (x  y  rz)", padding=6)
        self._coord_frame.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        self._coord_frame.columnconfigure(0, weight=1)
        self._coord_var   = tk.StringVar()
        self._coord_entry = ttk.Entry(
            self._coord_frame, textvariable=self._coord_var, width=28)
        self._coord_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._coord_entry.bind("<Return>", lambda _: self._submit_coord())
        ttk.Label(self._coord_frame, text="(leer = kein Teil)").grid(
            row=0, column=1, padx=(0, 8))
        ttk.Button(self._coord_frame, text="OK",
                   command=self._submit_coord, width=8).grid(row=0, column=2)
        self._coord_frame.grid_remove()

        # Fortschritt
        pf = ttk.Frame(right)
        pf.grid(row=4, column=0, sticky="ew", pady=(6, 2))
        pf.columnconfigure(1, weight=1)
        ttk.Label(pf, text="Fortschritt:").grid(row=0, column=0, padx=(0, 8))
        self._pbar = ttk.Progressbar(pf, mode="determinate", maximum=100, value=0)
        self._pbar.grid(row=0, column=1, sticky="ew")
        self._plbl = tk.StringVar(value="0 / 0")
        ttk.Label(pf, textvariable=self._plbl, width=9).grid(
            row=0, column=2, padx=(8, 0))

        # Steuerknöpfe
        bb = ttk.Frame(self.root, padding=(8, 4, 8, 4))
        bb.grid(row=3, column=0, columnspan=2, sticky="ew")
        bb.columnconfigure((0, 1, 2), weight=1)

        self._btn_start = ttk.Button(bb, text="START",
                                     command=self._on_start, width=20)
        self._btn_start.grid(row=0, column=0, padx=8, ipady=6)

        self._btn_pause = ttk.Button(bb, text="PAUSE",
                                     command=self._on_pause,
                                     width=20, state="disabled")
        self._btn_pause.grid(row=0, column=1, padx=8, ipady=6)

        self._btn_stop = ttk.Button(bb, text="STOP / ABBRECHEN",
                                    command=self._on_stop,
                                    width=20, state="disabled")
        self._btn_stop.grid(row=0, column=2, padx=8, ipady=6)

        self._status = tk.StringVar(value="Bereit.")
        ttk.Label(self.root, textvariable=self._status,
                  relief="sunken", anchor="w", padding=(8, 3)).grid(
            row=4, column=0, columnspan=2, sticky="ew")

        self._apply_mode_ui()

    @staticmethod
    def _pick_mono():
        import tkinter.font as tkf
        fam = set(tkf.families())
        for n in ("Consolas", "Cascadia Code", "Courier New", "Lucida Console"):
            if n in fam:
                return (n, 9)
        return ("TkFixedFont", 9)

    # ── Modus ────────────────────────────────────────────────────────────────

    def _on_mode_change(self):
        self._apply_mode_ui()
        mode     = self._mode.get()
        defaults = {"sim": DEFAULTS_SIM, "prod": DEFAULTS_PROD,
                    "acc": DEFAULTS_ACC}[mode]
        label    = {"sim": "Simulation", "prod": "Produktion (echte Hardware)",
                    "acc": "Genauigkeitstest"}[mode]
        if messagebox.askyesno(
            "Standardwerte laden?",
            f"Standardwerte fuer '{label}' laden?\n"
            "(ueberschreibt aktuelle Parameterwerte)",
        ):
            self._load_defaults(defaults)

    def _apply_mode_ui(self):
        mode = self._mode.get()
        if mode == "sim":
            bg        = "#e8f4f8"
            file_text = "Datei:  pick_and_placeV1_SIM.py   (iRC-Simulator + simulierter EYE+)"
            eye_state = "disabled"
        elif mode == "acc":
            bg        = "#eaf7ea"
            file_text = "Datei:  genauigkeitstestV1.py   (Genauigkeits-/Wiederholtest, ohne EYE+)"
            eye_state = "disabled"
        else:
            bg        = "#fff8e8"
            file_text = "Datei:  pick_and_placeV1.py   (echte Hardware)"
            eye_state = "normal"

        self._mode_bar.config(bg=bg)
        for w in self._mode_bar.winfo_children():
            try:
                w.config(bg=bg)
            except Exception:
                pass
        self._file_var.set(file_text)
        for e in self._eye_entries:
            e.config(state=eye_state)

        # EYE+-bezogene Anzeige nur in der Produktion sichtbar.
        show_eye = (mode == "prod")
        try:
            for w in (self._led_eye_frame, self._eye_section_frame, self._recipe_sec):
                w.grid() if show_eye else w.grid_remove()
        except AttributeError:
            pass

        # Beim ersten Wechsel in die Produktion die echte EYE+-Rezeptliste
        # einmal automatisch holen, damit alle Rezepte (inkl. V2) ohne Klick auf
        # "Rezeptliste laden" im Dropdown stehen. Still, d.h. bei fehlender
        # IP/Port oder nicht erreichbarem EYE+ kein Popup -- nur Log-Ausgabe.
        # Danach nicht mehr automatisch (manueller Button bleibt moeglich).
        if show_eye and not self._recipe_autoloaded:
            if self._load_recipe_list(silent=True):
                self._recipe_autoloaded = True

        # Pick-and-Place-Sektionen (Aufgabe, Pick-Geometrie, Ablageorte, Cube)
        # sind im Genauigkeitstest nicht relevant -> ausblenden. Stattdessen die
        # Genauigkeitstest-Sektion mit den beiden Ablageorten zeigen.
        is_acc = (mode == "acc")
        try:
            for w in (self._sec_aufgabe, self._sec_pickgeom,
                      self._sec_place_normal, self._sec_place_endlos,
                      self._sec_cube):
                w.grid_remove() if is_acc else w.grid()
            self._sec_acc.grid() if is_acc else self._sec_acc.grid_remove()
        except AttributeError:
            pass

        if self._test_cb_widget is not None:
            if mode == "prod":
                self._test_cb_widget.grid()
            else:
                self._vars["test_mode"].set("0")
                self._test_cb_widget.grid_remove()

    def _load_defaults(self, d: dict):
        for k, v in d.items():
            if k in self._vars:
                self._vars[k].set(v)

    def _reset_defaults(self):
        self._load_defaults(
            {"sim": DEFAULTS_SIM, "prod": DEFAULTS_PROD,
             "acc": DEFAULTS_ACC}[self._mode.get()])

    def _set_led(self, which: str, state: str):
        color = "#44cc44" if state == "green" else "#d94f4f"
        if which == "robot":
            self._led_robot_dot.config(foreground=color)
        elif which == "eye":
            self._led_eye_dot.config(foreground=color)

    def _update_override_live(self):
        try:
            val = float(self._vars["velocity"].get())
        except ValueError:
            messagebox.showerror("Eingabefehler",
                                 "'Geschwindigkeit' muss eine Zahl (0–100) sein.")
            return
        robot = self._robot_ref
        if robot is None:
            messagebox.showinfo("Nicht verbunden",
                                "Kein laufender Roboter — erst START druecken.")
            return
        threading.Thread(
            target=lambda: robot.set_override(val), daemon=True).start()

    # ── Asyril-Rezept-Auswahl ─────────────────────────────────────────────────

    def _set_recipe_values(self, recipes):
        # Befuellt die Combobox aus einer Liste von (id, name)-Tupeln. Anzeige:
        # "<id>  <name>". Behaelt die aktuelle Auswahl, falls noch vorhanden,
        # sonst Default = Rezept_Produktion (RECIPE_ID_PROD) bzw. erster Eintrag.
        self._recipes = list(recipes)
        display = [f"{rid}  {name}".strip() for rid, name in self._recipes]
        self._recipe_combo["values"] = display
        if self._recipe_var.get() not in display:
            default = ""
            for disp, (rid, _name) in zip(display, self._recipes):
                if rid == RECIPE_ID_PROD:
                    default = disp
                    break
            if not default and display:
                default = display[0]
            self._recipe_var.set(default)

    def _selected_recipe_id(self) -> str:
        # Erster Token der Anzeige ("<id>  <name>") ist die Rezept-ID.
        disp = self._recipe_var.get().strip()
        return disp.split()[0] if disp else ""

    def _load_recipe_list(self, silent=False):
        # silent=True wird beim automatischen Laden (Wechsel in die Produktion)
        # genutzt: keine Fehler-Popups, stattdessen nur Log-Ausgaben.
        # Rueckgabe: True, wenn ein Ladevorgang gestartet wurde, sonst False
        # (IP/Port fehlt oder ungueltig). Das Auto-Laden setzt seinen One-Shot-
        # Flag nur bei True, sodass es bei fehlender Konfiguration spaeter erneut
        # versucht.
        ip   = self._vars["eye_ip"].get().strip()
        port = self._vars["eye_port"].get().strip()
        if not ip or not port:
            if not silent:
                messagebox.showinfo("Nicht verbunden",
                                    "EYE+ IP/Port nicht konfiguriert.")
            return False
        try:
            port_int = int(port)
        except ValueError:
            if not silent:
                messagebox.showerror("Fehler", "Ungültiger EYE+ Port.")
            return False

        def do_load():
            try:
                c = EyePlusClient(
                    ip, port_int,
                    log_fn=lambda t, tag=None: self._log_q.put(("log", (t, tag))),
                    cmd_log_fn=lambda t, tag=None: self._log_q.put(
                        ("eye_main", (t, tag))),
                )
                c.connect()
                recipes = c.get_recipe_list()
                c.close()
                self._log_q.put(("recipes", recipes))
                self._log_q.put(
                    ("log", (f"[EYE+] {len(recipes)} Rezept(e) geladen.", "ok")))
            except Exception as e:
                self._log_q.put(
                    ("log", (f"[EYE+] Rezeptliste laden fehlgeschlagen: {e}", "err")))

        threading.Thread(target=do_load, daemon=True).start()
        return True

    # ── Koordinaten-Eingabe ───────────────────────────────────────────────────

    def _request_coord_from_worker(self) -> str:
        self._coord_event.clear()
        self._coord_result = None
        self._log_q.put(("cmd", "SHOW_COORD"))
        self._coord_event.wait()
        self._log_q.put(("cmd", "HIDE_COORD"))
        return self._coord_result or ""

    def _submit_coord(self):
        self._coord_result = self._coord_var.get().strip()
        self._coord_var.set("")
        self._coord_event.set()

    # ── Callbacks ────────────────────────────────────────────────────────────

    def _on_start(self):
        if not self._validate():
            return
        if self._mode.get() == "sim" and not CRI_AVAILABLE:
            messagebox.showerror(
                "CRI-Bibliothek fehlt",
                "libs/CRI_Python_Lib konnte nicht geladen werden.\n"
                "Starte das Programm aus dem Ordner 'BA_PY_Skript'.",
            )
            return
        self._stop_event.clear()
        self._pause_event.set()
        self._clear_log()
        if self._mode.get() == "prod":
            self._clear_eye_logs()
        self._set_running(True)
        self._set_led("robot", "red")
        self._set_led("eye", "red")
        n = int(self._vars["num_parts"].get())
        self._pbar.config(value=0)
        self._plbl.set(f"0 / {n}")
        self._status.set("Verbinde ...")
        cfg          = {k: v.get() for k, v in self._vars.items()}
        cfg["_mode"] = self._mode.get()
        cfg["_recipe_id"] = self._selected_recipe_id()
        self._worker = threading.Thread(
            target=self._worker_fn, args=(cfg,), daemon=True)
        self._worker.start()

    def _on_pause(self):
        if self._pause_event.is_set():
            self._pause_event.clear()
            self._btn_pause.config(text="WEITER")
            self._status.set("Pausiert — wartet auf Ende der aktuellen Bewegung ...")
        else:
            self._pause_event.set()
            self._btn_pause.config(text="PAUSE")
            self._status.set("Lauft ...")

    def _on_stop(self):
        self._stop_event.set()
        self._pause_event.set()
        self._coord_event.set()
        self._coord_result = None
        self._status.set("Abbruch wird ausgefuehrt ...")

    # ── Hilfsmethoden ────────────────────────────────────────────────────────

    def _validate(self) -> bool:
        mode   = self._mode.get()
        errors = []
        for key, label in [("num_parts", "Anzahl Teile"),
                            ("robot_port", "Roboter Port")]:
            try:
                int(self._vars[key].get())
            except ValueError:
                errors.append(f"  '{label}' muss eine ganze Zahl sein.")
        if mode == "prod":
            try:
                int(self._vars["eye_port"].get())
            except ValueError:
                errors.append("  'EYE+ Port' muss eine ganze Zahl sein.")
        for key, label in [
            ("pick_cx", "Pick Mitte X"), ("pick_cy", "Pick Mitte Y"),
            ("safe_pick_z", "Z-Safe Pick"), ("grip_z", "Z-Greifen"),
            ("tool_a", "Tool A"), ("tool_b", "Tool B"), ("tool_c", "Tool C"),
            ("rotate_deg", "A1-Drehung"), ("velocity", "Geschwindigkeit"),
            ("place_x", "Ablage X-Start"), ("place_x_step", "Ablage X-Schritt"),
            ("place_y", "Ablage Y"),
            ("place_z_safe", "Ablage Z-Safe"), ("place_z_drop", "Ablage Z-Ablegen"),
            ("endlos_x", "Endlos X"), ("endlos_y", "Endlos Y"),
            ("endlos_z_safe", "Endlos Z-Safe"), ("endlos_z_drop", "Endlos Z-Ablegen"),
            ("fill_wait", "Fuell-Wartezeit"),
        ]:
            try:
                float(self._vars[key].get())
            except ValueError:
                errors.append(f"  '{label}' muss eine Zahl sein.")
        try:
            joints = [float(v) for v in self._vars["safe_joints"].get().split()]
            if len(joints) != 6:
                errors.append("  'Safe-Joints' braucht genau 6 Werte.")
        except ValueError:
            errors.append("  'Safe-Joints' enthaelt ungueltige Werte.")
        if mode == "acc":
            for key, label in [
                ("acc_p1x", "Ablageort 1 X"), ("acc_p1y", "Ablageort 1 Y"),
                ("acc_p1z", "Ablageort 1 Z"), ("acc_p2x", "Ablageort 2 X"),
                ("acc_p2y", "Ablageort 2 Y"), ("acc_p2z", "Ablageort 2 Z"),
                ("acc_offset", "Anfahr-Offset Z"),
            ]:
                try:
                    float(self._vars[key].get())
                except ValueError:
                    errors.append(f"  '{label}' muss eine Zahl sein.")
        if errors:
            messagebox.showerror("Eingabefehler",
                                 "Bitte korrigieren:\n\n" + "\n".join(errors))
            return False
        return True

    def _set_running(self, running: bool):
        self._btn_start.config(state="disabled" if running else "normal")
        self._btn_pause.config(state="normal"   if running else "disabled")
        self._btn_stop .config(state="normal"   if running else "disabled")
        if not running:
            self._btn_pause.config(text="PAUSE")

    def _clear_log(self):
        self._term.config(state="normal")
        self._term.delete("1.0", "end")
        self._term.config(state="disabled")

    def _clear_eye_logs(self):
        for t in (self._eye_main_term, self._eye_poll_term):
            t.config(state="normal")
            t.delete("1.0", "end")
            t.config(state="disabled")

    def _write_eye_log(self, term, text: str, tag):
        term.config(state="normal")
        term.insert("end", f"[{datetime.now():%H:%M:%S}] ", "ts")
        term.insert("end", text, tag or "")
        if not text.endswith("\n"):
            term.insert("end", "\n")
        term.see("end")
        term.config(state="disabled")

    def _stop_production_live(self):
        ip   = self._vars["eye_ip"].get().strip()
        port = self._vars["eye_port"].get().strip()
        if not ip or not port:
            messagebox.showinfo("Nicht verbunden",
                                "EYE+ IP/Port nicht konfiguriert.")
            return
        try:
            port_int = int(port)
        except ValueError:
            messagebox.showerror("Fehler", "Ungültiger EYE+ Port.")
            return

        def do_stop():
            try:
                c = EyePlusClient(ip, port_int)
                c.connect()
                c.stop_production()
                c.close()
                self._log_q.put(("log", ("[EYE+] Stop Production manuell ausgloest.", "warn")))
            except Exception as e:
                self._log_q.put(("log", (f"[EYE+] Stop Production fehlgeschlagen: {e}", "err")))

        threading.Thread(target=do_stop, daemon=True).start()

    def _write_log(self, text: str, tag):
        self._term.config(state="normal")
        self._term.insert("end", f"[{datetime.now():%H:%M:%S}] ", "ts")
        self._term.insert("end", text, tag or "")
        if not text.endswith("\n"):
            self._term.insert("end", "\n")
        self._term.see("end")
        self._term.config(state="disabled")

    def _set_progress(self, done: int, total: int):
        self._pbar.config(value=(done / total * 100) if total else 0)
        self._plbl.set(f"{done} / {total}")

    # ── Poll ─────────────────────────────────────────────────────────────────

    def _poll(self):
        try:
            while True:
                key, data = self._log_q.get_nowait()
                if key == "log":
                    self._write_log(data[0], data[1])
                elif key == "status":
                    self._status.set(data)
                elif key == "progress":
                    self._set_progress(*data)
                elif key == "led":
                    self._set_led(data[0], data[1])
                elif key == "eye_main":
                    self._write_eye_log(self._eye_main_term, data[0], data[1])
                elif key == "eye_poll":
                    self._write_eye_log(self._eye_poll_term, data[0], data[1])
                elif key == "recipes":
                    self._set_recipe_values(data)
                elif key == "cmd":
                    if data == "SHOW_COORD":
                        self._coord_frame.grid()
                        self._coord_entry.focus_set()
                    elif data == "HIDE_COORD":
                        self._coord_frame.grid_remove()
        except queue.Empty:
            pass

        if self._worker is not None and not self._worker.is_alive():
            self._worker = None
            self._set_running(False)
            st = self._status.get()
            if not st.startswith("Abgebrochen") and "FEHLER" not in st:
                self._status.set("Fertig.")

        self.root.after(40, self._poll)

    # ── Worker ───────────────────────────────────────────────────────────────

    def _worker_fn(self, cfg: dict):
        q    = self._log_q
        mode = cfg["_mode"]

        def log(text: str, tag=None):
            q.put(("log", (text, tag)))

        def status(text: str):
            q.put(("status", text))

        def prog(done: int, total: int):
            q.put(("progress", (done, total)))

        def led(which: str, state: str):
            q.put(("led", (which, state)))

        def eye_main_log(text: str, tag=None):
            q.put(("eye_main", (text, tag)))

        def eye_poll_log(text: str, tag=None):
            q.put(("eye_poll", (text, tag)))

        def check():
            if self._stop_event.is_set():
                raise _StopException()
            self._pause_event.wait()
            if self._stop_event.is_set():
                raise _StopException()

        def isleep(s: float):
            for _ in range(max(1, int(s / 0.1))):
                check()
                time.sleep(0.1)

        EYE_IP             = cfg["eye_ip"]
        EYE_PORT           = int(cfg["eye_port"]) if cfg["eye_port"] else 7171
        ROBOT_IP           = cfg["robot_ip"]
        ROBOT_PORT         = int(cfg["robot_port"])
        NUM_PARTS          = int(cfg["num_parts"])
        PICK_CENTER_X      = float(cfg["pick_cx"])
        PICK_CENTER_Y      = float(cfg["pick_cy"])
        SAFE_PICK_Z        = float(cfg["safe_pick_z"])
        GRIP_Z             = float(cfg["grip_z"])
        TOOL_A_DOWN        = float(cfg["tool_a"])
        TOOL_B_DOWN        = float(cfg["tool_b"])
        TOOL_C_DOWN        = float(cfg["tool_c"])
        ROTATE_DEG         = float(cfg["rotate_deg"])
        SAFE_ROTATE_JOINTS = [float(v) for v in cfg["safe_joints"].split()]
        ENDLOS         = cfg["endlos"] == "1"
        ENDLOS_X       = float(cfg["endlos_x"])
        ENDLOS_Y       = float(cfg["endlos_y"])
        ENDLOS_Z_SAFE  = float(cfg["endlos_z_safe"])
        ENDLOS_Z_DROP  = float(cfg["endlos_z_drop"])
        PLACE_X        = float(cfg["place_x"])
        PLACE_X_STEP   = float(cfg["place_x_step"])
        PLACE_Y        = float(cfg["place_y"])
        PLACE_Z_SAFE   = float(cfg["place_z_safe"])
        PLACE_Z_DROP   = float(cfg["place_z_drop"])
        FILL_FEEDER_CMD    = cfg["fill_cmd"]
        FILL_WAIT_S        = float(cfg["fill_wait"])
        MOVE_VELOCITY      = float(cfg["velocity"])
        TEST_MODE          = cfg.get("test_mode") == "1" and mode == "prod"

        # ── GENAUIGKEITSTEST ──────────────────────────────────────────────────
        # Eigener Modus: Roboter bewegt EIN Teil endlos zwischen zwei Ablageorten
        # hin und her. Keine EYE+-Verbindung; Bewegungsablauf in genauigkeitstestV1.
        if mode == "acc":
            P1 = (float(cfg["acc_p1x"]), float(cfg["acc_p1y"]), float(cfg["acc_p1z"]))
            P2 = (float(cfg["acc_p2x"]), float(cfg["acc_p2y"]), float(cfg["acc_p2z"]))
            ACC_OFFSET = float(cfg["acc_offset"])
            TOOL       = (TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN)

            robot = CriRobot(ROBOT_IP, ROBOT_PORT, log_fn=log)
            self._robot_ref = robot
            _CART_VEL_MAX  = 500.0
            _JOINT_VEL_MAX = 100.0

            log("=" * 56, "head")
            log("  Genauigkeitstest  |  Roboter ohne EYE+", "head")
            log(f"  Ort 1: {P1}   Ort 2: {P2}", "head")
            log(f"  Roboter: {ROBOT_IP}:{ROBOT_PORT}", "head")
            log("=" * 56, "head")

            try:
                if _acc_script is None:
                    raise RuntimeError(
                        "genauigkeitstestV1.py konnte nicht importiert werden.")

                status("Verbinde ...")
                log("\n[1] Verbinde Roboter ...", "info")
                robot.connect()
                check()
                robot.init()
                robot.set_override(MOVE_VELOCITY)
                check()
                led("robot", "green")

                status("Genauigkeitstest laeuft (Endlos) ...")
                log("\n[2] Genauigkeitstest startet (endlos — STOP zum Beenden) ...",
                    "info")
                prog(0, 0)   # Endlos: kein festes Ziel -> Balken neutral lassen

                def on_cycle(n):
                    q.put(("status", f"Genauigkeitstest laeuft — {n} Transfer(s)"))
                    log(f"  === Transfer {n} abgeschlossen ===", "ok")

                _acc_script.run_genauigkeitstest(
                    robot, P1, P2, ACC_OFFSET, TOOL, SAFE_ROTATE_JOINTS,
                    cart_vel=_CART_VEL_MAX, joint_vel=_JOINT_VEL_MAX,
                    log=log, check=check, on_cycle=on_cycle)

            except _StopException:
                log("\n[ABBRUCH] durch Benutzer.", "err")
                status("Abgebrochen.")
            except Exception as exc:
                msg = f"{type(exc).__name__}: {exc}"
                log(f"\n[FEHLER]  {msg}", "err")
                status(f"FEHLER: {msg}")
            finally:
                self._robot_ref = None
                led("robot", "red")
                try:
                    robot.close()
                except Exception:
                    pass
                log("\n[ENDE] Verbindung getrennt.", "info")
            return

        if mode == "sim":
            eye    = SimulatedEyePlus(self._request_coord_from_worker, log_fn=log)
            poller = SimEyePoller(eye)
            robot  = CriControllerWrapper(ROBOT_IP, ROBOT_PORT, log_fn=log)
        else:
            eye    = EyePlusClient(EYE_IP, EYE_PORT, log_fn=log,
                                   cmd_log_fn=eye_main_log)
            poller = EyePlusPoller(EYE_IP, EYE_PORT,
                                   status_log_fn=eye_poll_log)
            robot  = CriRobot(ROBOT_IP, ROBOT_PORT, log_fn=log)
        self._robot_ref = robot

        # Geschwindigkeit wird ausschliesslich ueber den iRC-Override gesteuert
        # (set_override setzt den sichtbaren Schieberegler auf MOVE_VELOCITY %).
        # Die velocity-Parameter hier sind Maximalwerte; der Override skaliert alles
        # gleichmaessig, sodass Kartesisch- und Gelenk-Moves dieselbe relative
        # Geschwindigkeit haben.
        _CART_VEL_MAX  = 500.0   # mm/s  (wird durch Override % begrenzt)
        _JOINT_VEL_MAX = 100.0   # %     (wird durch Override % begrenzt)

        def move_cart(x, y, z, a, b, c):
            check()
            robot.move_cartesian(x, y, z, a, b, c, velocity=_CART_VEL_MAX)

        def move_jnt(joints):
            check()
            robot.move_joints(joints, velocity=_JOINT_VEL_MAX)

        def rot_a6(deg):
            check()
            robot.rotate_a6(deg, velocity=_JOINT_VEL_MAX)

        def grip_aligned(x, y, rz):
            # Senkrechte Anfahrt (Basis-Orientierung); die Teil-Drehung rz wird
            # ausschliesslich ueber das A6-Gelenk realisiert. Nach dem Greifen
            # wird das Teil zuerst senkrecht hochgezogen (A6 bleibt gedreht),
            # erst danach die Orientierung korrigiert (A6 zurueck) -- die
            # Rueckdrehung passiert also auf dem Weg nach oben, nicht auf der
            # Platte. Endpose: SAFE_PICK_Z in Basis-Orientierung.
            # 90-Grad = fester Greifer-Montage-Offset zwischen rz und A6.
            a6 = 90.0 - rz
            move_cart(x, y, SAFE_PICK_Z, TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN)
            move_cart(x, y, GRIP_Z,      TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN)
            rot_a6(a6)
            robot.gripper(close=True)
            check()
            robot.move_base_relative(0.0, 0.0, SAFE_PICK_Z - GRIP_Z,
                                     velocity=_CART_VEL_MAX)
            rot_a6(-a6)

        def set_axis(idx, val, base):
            j      = list(base)
            j[idx] = val
            log(f"   [Achse A{idx+1}] -> {val:.1f} Grad", "move")
            move_jnt(j)
            return j

        try:
            if TEST_MODE:
                mode_label  = "PRODUKTION  — TEST-MODUS  (Einzelgreiftest)"
                task_label  = "  [KEIN BEFUELLEN — Teil manuell einlegen]"
            elif mode == "sim":
                mode_label  = "SIMULATION  (iRC-Sim + simulierter EYE+)"
                task_label  = "  [ENDLOS-MODUS]" if ENDLOS else f"  {NUM_PARTS} Teile"
            else:
                mode_label  = "PRODUKTION  (echte Hardware)"
                task_label  = "  [ENDLOS-MODUS]" if ENDLOS else f"  {NUM_PARTS} Teile"
            log("=" * 56, "head")
            log(f"  Pick & Place  |  {mode_label}", "head")
            log(f"{task_label}  |  Roboter: {ROBOT_IP}:{ROBOT_PORT}", "head")
            if mode == "prod":
                log(f"  EYE+: {EYE_IP}:{EYE_PORT}", "head")
            log("=" * 56, "head")

            status("Verbinde ...")
            log("\n[1] Verbinde ...", "info")
            eye.connect()
            check()
            if mode == "prod":
                poller.connect()
                check()
                led("eye", "green")
            robot.connect()
            check()
            robot.init()
            robot.set_override(MOVE_VELOCITY)
            check()
            led("robot", "green")

            status("Recipe-Liste laden ...")
            log("\n[2] Recipe-Liste ...", "info")
            # Rezept-Auswahl nach Modus:
            #   Test-Modus    -> Rezept_Testmodus  (RECIPE_ID_TEST, automatisch)
            #   Normal/Endlos -> im GUI-Dropdown gewaehltes Rezept
            #                    (Fallback: RECIPE_ID_PROD)
            if TEST_MODE:
                recipe_id = RECIPE_ID_TEST
            else:
                recipe_id = cfg.get("_recipe_id") or RECIPE_ID_PROD
            recipes = eye.get_recipe_list()
            log(f"    {len(recipes)} Rezept(e) gefunden:", "ok")
            for i, (rid, name) in enumerate(recipes):
                mark = "  <== AKTIV" if str(rid) == recipe_id else ""
                log(f"    [{i}]  {rid}  '{name}'{mark}", "info")
            log(f"    -> {'TEST-MODUS' if TEST_MODE else 'NORMAL/ENDLOS'}: "
                f"verwende Rezept-ID {recipe_id}", "ok")
            if recipes and not any(str(rid) == recipe_id for rid, _ in recipes):
                raise RuntimeError(
                    f"Rezept-ID {recipe_id} nicht in der EYE+-Rezeptliste gefunden."
                )
            eye.start_production(recipe_id)
            check()

            if TEST_MODE:
                # ── TEST-MODUS: einmaliger Greiftest. Bild aufnehmen + Teil
                #    holen. Ob befuellt wird, steuert das EYE+-Rezept.
                status("Test-Modus: Bild aufnehmen ...")
                log("\n[3] Test-Modus — Bild aufnehmen ...", "info")
                eye.force_take_image()
                found, x, y, rz = eye.get_part()
                # Test-Modus = genau EIN Teil. Production sofort stoppen, damit
                # der EYE+ nicht parallel schon das naechste Teil sucht/vibriert.
                eye.stop_production()
                check()

                if not found:
                    log("[TEST] Kein Teil gefunden — Test abgebrochen.", "err")
                    status("Test: kein Teil gefunden.")
                else:
                    log(f"[TEST] Teil erkannt: x={x:.2f}  y={y:.2f}  rz={rz:.2f}", "ok")
                    prog(0, 1)

                    rotate_base = list(SAFE_ROTATE_JOINTS)
                    plc_a, plc_c = TOOL_A_DOWN, TOOL_C_DOWN

                    log(f"\n{'='*10}  TEST-GREIF  x={x:.1f}  y={y:.1f}"
                        f"  rz={rz:.1f}  {'='*10}", "head")

                    log("  -> SAFE-TO-PICK", "info")
                    move_cart(PICK_CENTER_X, PICK_CENTER_Y, SAFE_PICK_Z,
                              TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN)

                    log("  -> ueber Teil + greifen + senkrecht hoch (rz per A6)", "info")
                    grip_aligned(x, y, rz)
                    check()

                    log("  -> SAFE-TO-ROTATE einfahren", "info")
                    move_jnt(rotate_base)

                    log(f"  -> A1 drehen {ROTATE_DEG:.0f} Grad", "info")
                    rotated = set_axis(0, rotate_base[0] + ROTATE_DEG, rotate_base)

                    log(f"  -> ausfahren + ablegen  X={ENDLOS_X:.1f}"
                        f"  Y={ENDLOS_Y:.1f}", "info")
                    move_cart(ENDLOS_X, ENDLOS_Y, ENDLOS_Z_SAFE,
                              plc_a, TOOL_B_DOWN, plc_c)
                    move_cart(ENDLOS_X, ENDLOS_Y, ENDLOS_Z_DROP,
                              plc_a, TOOL_B_DOWN, plc_c)
                    robot.gripper(close=False)
                    check()
                    move_cart(ENDLOS_X, ENDLOS_Y, ENDLOS_Z_SAFE,
                              plc_a, TOOL_B_DOWN, plc_c)

                    log("  -> einfahren Safe-Rotate (A1 noch rotiert)", "info")
                    move_jnt(rotated)

                    log("  -> A1 zurueckrotieren -> Safe-Rotate", "info")
                    set_axis(0, rotate_base[0], rotated)

                    prog(1, 1)
                    log(f"\n{'='*56}", "ok")
                    log("  TEST abgeschlossen.", "ok")
                    log(f"{'='*56}", "ok")
                    status("Test abgeschlossen.")

            else:
                # ── NORMAL / ENDLOS ───────────────────────────────────────────
                status("Erstes Bild ...")
                log("\n[3] Erstes Bild ...", "info")
                eye.force_take_image()
                found, x, y, rz = eye.get_part()
                check()

                if not found:
                    log(f"[FILL] Keine Teile -> Feeder '{FILL_FEEDER_CMD}'", "warn")
                    eye.send(FILL_FEEDER_CMD)
                    isleep(FILL_WAIT_S)
                    eye.force_take_image()
                    found, x, y, rz = eye.get_part()
                    check()
                else:
                    log("[FILL] Teile vorhanden -> kein Fuellen.", "ok")

                picked    = 0
                next_part = (found, x, y, rz) if found else None
                if ENDLOS:
                    status("Lauft (Endlos-Modus) ...")
                else:
                    status("Lauft ...")

                while ENDLOS or picked < NUM_PARTS:
                    check()
                    if ENDLOS:
                        prog(picked, max(picked, 1))
                    else:
                        prog(picked, NUM_PARTS)

                    if next_part is None or not next_part[0]:
                        found, x, y, rz = eye.get_part()
                        next_part = (found, x, y, rz)
                        check()

                    if not next_part[0]:
                        log("[LOOP] Kein Kandidat -> nachfullen ...", "warn")
                        eye.send(FILL_FEEDER_CMD)
                        isleep(FILL_WAIT_S)
                        eye.force_take_image()
                        found, x, y, rz = eye.get_part()
                        next_part = (found, x, y, rz)
                        check()
                        if not next_part[0]:
                            log("[LOOP] Weiterhin kein Teil — Abbruch.", "err")
                            break

                    found, x, y, rz = next_part

                    # Orientierung bleibt senkrecht (Basis); rz wird per A6
                    # realisiert (siehe grip_aligned).
                    rotate_base  = list(SAFE_ROTATE_JOINTS)
                    plc_a, plc_c = TOOL_A_DOWN, TOOL_C_DOWN

                    log(f"\n{'='*12}  Teil {picked+1}/{NUM_PARTS}"
                        f"  x={x:.1f}  y={y:.1f}  rz={rz:.1f}  {'='*12}", "head")

                    log("  -> SAFE-TO-PICK", "info")
                    move_cart(PICK_CENTER_X, PICK_CENTER_Y, SAFE_PICK_Z,
                              TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN)

                    log("  -> ueber Teil + greifen + senkrecht hoch (rz per A6)", "info")
                    grip_aligned(x, y, rz)
                    check()

                    log("  -> SAFE-TO-ROTATE einfahren", "info")
                    move_jnt(rotate_base)

                    # Erst jetzt (Arm in Safe-To-Rotate, weg von der Platte) das
                    # naechste Teil analysieren lassen -- sonst stoert der Arm
                    # ueber der Platte die Bildaufnahme. Laeuft parallel zum
                    # Ablegen (Pipelining).
                    if picked + 1 < NUM_PARTS:
                        log("[EYE+] prepare_part -> naechstes Teil ...", "info")
                        eye.prepare_part()

                    log(f"  -> A1 drehen {ROTATE_DEG:.0f} Grad", "info")
                    rotated = set_axis(0, rotate_base[0] + ROTATE_DEG, rotate_base)

                    if ENDLOS:
                        plx, ply   = ENDLOS_X, ENDLOS_Y
                        plzs, plzd = ENDLOS_Z_SAFE, ENDLOS_Z_DROP
                    else:
                        plx, ply   = PLACE_X + picked * PLACE_X_STEP, PLACE_Y
                        plzs, plzd = PLACE_Z_SAFE, PLACE_Z_DROP

                    log(f"  -> ausfahren + ablegen  X={plx:.1f}  Y={ply:.1f}", "info")
                    move_cart(plx, ply, plzs, plc_a, TOOL_B_DOWN, plc_c)
                    move_cart(plx, ply, plzd, plc_a, TOOL_B_DOWN, plc_c)
                    robot.gripper(close=False)
                    check()
                    move_cart(plx, ply, plzs, plc_a, TOOL_B_DOWN, plc_c)

                    log("  -> einfahren Safe-Rotate (A1 noch rotiert)", "info")
                    move_jnt(rotated)

                    log("  -> A1 zurueckrotieren", "info")
                    set_axis(0, rotate_base[0], rotated)

                    picked += 1
                    if ENDLOS:
                        prog(picked, picked)
                        log(f"  Teil {picked} abgelegt (Endlos).", "ok")
                    else:
                        prog(picked, NUM_PARTS)
                        log(f"  Teil {picked}/{NUM_PARTS} abgelegt.", "ok")

                    if ENDLOS or picked < NUM_PARTS:
                        log("[SYNC] Warte auf EYE+ Analyse ...", "info")
                        t0 = time.time()
                        while poller.is_analysis_running():
                            check()
                            if time.time() - t0 > 30:
                                log("[SYNC] Timeout!", "warn")
                                break
                            time.sleep(0.1)
                        found, x, y, rz = eye.get_part()
                        next_part = (found, x, y, rz)
                        check()

                log(f"\n{'='*56}", "ok")
                if ENDLOS:
                    log(f"  GESTOPPT:  {picked} Teil(e) abgelegt.", "ok")
                else:
                    log(f"  FERTIG:  {picked} Teil(e) abgelegt.", "ok")
                log(f"{'='*56}", "ok")
                status("Fertig.")

        except _StopException:
            log("\n[ABBRUCH] durch Benutzer.", "err")
            status("Abgebrochen.")

        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            log(f"\n[FEHLER]  {msg}", "err")
            status(f"FEHLER: {msg}")

        finally:
            self._robot_ref = None
            led("robot", "red")
            if mode == "prod":
                led("eye", "red")
            try:
                eye.stop_production()
            except Exception:
                pass
            for obj in (eye, poller, robot):
                try:
                    obj.close()
                except Exception:
                    pass
            log("\n[ENDE] Verbindungen getrennt.", "info")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.2)
    except Exception:
        pass
    PickPlaceApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
