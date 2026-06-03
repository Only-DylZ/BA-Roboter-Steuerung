#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pick & Place GUI — igus ReBeL 6-DOF Simulation"""

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

try:
    from ultragay.CRI_Python_Lib.cri_lib import CRIController, CRIConnectionError
    CRI_AVAILABLE = True
except ImportError:
    CRI_AVAILABLE = False
    CRIController = None
    CRIConnectionError = Exception


# ── Standardwerte (entsprechen pick_and_placeV1_SIM.py) ──────────────────────
DEFAULTS = {
    "ip":           "127.0.0.1",
    "port":         "3921",
    "num_parts":    "4",
    "velocity":     "80",
    "pick_cx":      "440.0",
    "pick_cy":      "-5.0",
    "pick_z_safe":  "150.0",
    "pick_z_grip":  "140.0",
    "tool_a":       "180.0",
    "tool_b":       "0.0",
    "tool_c":       "180.0",
    "place_xs":     "0.0",
    "place_xst":    "50.0",
    "place_y":      "-300.0",
    "place_zs":     "150.0",
    "place_zd":     "140.0",
    "rotate_deg":   "-90.0",
    "safe_joints":  "0.0 -18.7 108.0 0.0 90.0 0.0",
}


class _StopException(Exception):
    pass


class PickPlaceApp:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Pick & Place — igus ReBeL Simulation")
        self.root.resizable(True, True)

        self._log_q: queue.Queue = queue.Queue()
        self._coord_event = threading.Event()
        self._coord_result: str | None = None
        self._pause_event = threading.Event()
        self._pause_event.set()           # nicht pausiert beim Start
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None

        self._vars: dict[str, tk.StringVar] = {
            k: tk.StringVar(value=v) for k, v in DEFAULTS.items()
        }

        self._build_ui()
        self._poll()

    # ── UI-Aufbau ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        # ── Linke Spalte: Parameter ───────────────────────────────────────────
        left = ttk.Frame(self.root, padding=8)
        left.grid(row=0, column=0, sticky="ns")

        def section(title, row):
            lf = ttk.LabelFrame(left, text=title, padding=6)
            lf.grid(row=row, column=0, sticky="ew", pady=(0, 6))
            return lf

        def field(parent, label, key, r, c=0):
            ttk.Label(parent, text=label).grid(
                row=r, column=c * 2, sticky="w", padx=(0, 4), pady=2)
            ttk.Entry(parent, textvariable=self._vars[key], width=9).grid(
                row=r, column=c * 2 + 1, padx=(0, 10), pady=2)

        # Verbindung
        f = section("Verbindung", 0)
        field(f, "IP:",   "ip",   0, 0)
        field(f, "Port:", "port", 0, 1)

        # Ablauf
        f = section("Ablauf", 1)
        field(f, "Anzahl Teile:",    "num_parts", 0, 0)
        field(f, "Geschw. (mm/s):", "velocity",  0, 1)

        # Pick
        f = section("Pick", 2)
        field(f, "Mitte X:",    "pick_cx",     0, 0)
        field(f, "Mitte Y:",    "pick_cy",     0, 1)
        field(f, "Z-Safe:",     "pick_z_safe", 1, 0)
        field(f, "Z-Greifen:", "pick_z_grip",  1, 1)

        # Place
        f = section("Place", 3)
        field(f, "X-Start:",    "place_xs",  0, 0)
        field(f, "X-Schritt:", "place_xst",  0, 1)
        field(f, "Y:",          "place_y",   1, 0)
        field(f, "Z-Safe:",     "place_zs",  2, 0)
        field(f, "Z-Ablegen:", "place_zd",   2, 1)

        # Werkzeug-Orientierung
        f = section("Werkzeug (A  B  C)", 4)
        field(f, "A:", "tool_a", 0, 0)
        field(f, "B:", "tool_b", 0, 1)
        field(f, "C:", "tool_c", 0, 2)

        # Rotation
        f = section("Rotation / Safe-Joints", 5)
        field(f, "A1-Drehung °:", "rotate_deg", 0, 0)
        ttk.Label(f, text="Safe-Joints  A1..A6 (Leerzeichen-getrennt):").grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Entry(f, textvariable=self._vars["safe_joints"], width=32).grid(
            row=2, column=0, columnspan=4, sticky="ew", pady=2)

        # ── Rechte Spalte: Log + Eingabe ──────────────────────────────────────
        right = ttk.Frame(self.root, padding=(0, 8, 8, 8))
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        ttk.Label(right, text="Protokoll").grid(row=0, column=0, sticky="w")

        self._log_widget = scrolledtext.ScrolledText(
            right, width=58, height=32, state="disabled",
            font=("Courier New", 9),
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="white",
        )
        self._log_widget.grid(row=1, column=0, sticky="nsew")

        # Tag-Farben für den Log
        self._log_widget.tag_config("err",  foreground="#f48771")
        self._log_widget.tag_config("ok",   foreground="#89d185")
        self._log_widget.tag_config("info", foreground="#9cdcfe")
        self._log_widget.tag_config("head", foreground="#dcdcaa")

        # EYE+ Koordinaten-Eingabe (anfangs versteckt)
        self._coord_frame = ttk.LabelFrame(
            right, text="EYE+ Koordinaten eingeben  (x  y  rz)", padding=6)
        self._coord_frame.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self._coord_frame.columnconfigure(0, weight=1)

        self._coord_var = tk.StringVar()
        self._coord_entry = ttk.Entry(
            self._coord_frame, textvariable=self._coord_var, width=28)
        self._coord_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._coord_entry.bind("<Return>", lambda _: self._submit_coord())

        ttk.Label(self._coord_frame, text="(leer = kein Teil)").grid(
            row=0, column=1, padx=(0, 8))
        self._coord_btn = ttk.Button(
            self._coord_frame, text="OK", command=self._submit_coord, width=8)
        self._coord_btn.grid(row=0, column=2)

        self._coord_frame.grid_remove()   # versteckt bis benötigt

        # ── Untere Leiste: Steuerknöpfe ───────────────────────────────────────
        btn_bar = ttk.Frame(self.root, padding=(8, 4, 8, 8))
        btn_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        btn_bar.columnconfigure((0, 1, 2), weight=1)

        self._btn_start = ttk.Button(
            btn_bar, text="▶  START", command=self._on_start, width=16)
        self._btn_start.grid(row=0, column=0, padx=6)

        self._btn_pause = ttk.Button(
            btn_bar, text="⏸  PAUSE", command=self._on_pause,
            width=16, state="disabled")
        self._btn_pause.grid(row=0, column=1, padx=6)

        self._btn_stop = ttk.Button(
            btn_bar, text="⏹  STOP", command=self._on_stop,
            width=16, state="disabled")
        self._btn_stop.grid(row=0, column=2, padx=6)

        # Statuszeile
        self._status_var = tk.StringVar(value="Bereit.")
        ttk.Label(self.root, textvariable=self._status_var,
                  relief="sunken", anchor="w", padding=(6, 2)).grid(
            row=2, column=0, columnspan=2, sticky="ew")

    # ── Button-Callbacks ──────────────────────────────────────────────────────

    def _on_start(self):
        if not CRI_AVAILABLE:
            messagebox.showerror(
                "CRI-Lib nicht gefunden",
                "ultragay/CRI_Python_Lib konnte nicht importiert werden.\n"
                "Starte das Programm aus dem Projektordner:\n"
                "  BA_PY_Skript\\"
            )
            return

        self._stop_event.clear()
        self._pause_event.set()
        self._clear_log()
        self._set_buttons_running(True)
        self._status_var.set("Läuft …")

        cfg = {k: v.get() for k, v in self._vars.items()}
        self._worker = threading.Thread(
            target=self._robot_worker, args=(cfg,), daemon=True)
        self._worker.start()

    def _on_pause(self):
        if self._pause_event.is_set():
            self._pause_event.clear()
            self._btn_pause.config(text="▶  WEITER")
            self._status_var.set("Pausiert — wartet auf Ende der aktuellen Bewegung …")
        else:
            self._pause_event.set()
            self._btn_pause.config(text="⏸  PAUSE")
            self._status_var.set("Läuft …")

    def _on_stop(self):
        self._stop_event.set()
        self._pause_event.set()      # Pause-Blockierung aufheben
        self._coord_event.set()      # Koordinaten-Eingabe-Blockierung aufheben
        self._coord_result = None
        self._status_var.set("Abbruch wird durchgeführt …")

    # ── Hilfsmethoden (Main-Thread) ───────────────────────────────────────────

    def _set_buttons_running(self, running: bool):
        self._btn_start.config(state="disabled" if running else "normal")
        self._btn_pause.config(state="normal"   if running else "disabled")
        self._btn_stop.config( state="normal"   if running else "disabled")
        if not running:
            self._btn_pause.config(text="⏸  PAUSE")

    def _clear_log(self):
        self._log_q.put(("\x00CLEAR", None))

    def _append_log(self, text: str, tag: str | None = None):
        """Main-Thread: Text in das Log-Widget schreiben."""
        self._log_widget.config(state="normal")
        self._log_widget.insert("end", text, tag or "")
        self._log_widget.see("end")
        self._log_widget.config(state="disabled")

    # ── EYE+-Koordinaten-Eingabe (thread-safe) ────────────────────────────────

    def _request_coord_from_worker(self) -> str:
        """Worker-Thread: blockiert bis der Nutzer Koordinaten eingibt."""
        self._coord_event.clear()
        self._coord_result = None
        self._log_q.put(("\x00SHOW_INPUT", None))
        self._coord_event.wait()
        self._log_q.put(("\x00HIDE_INPUT", None))
        return self._coord_result or ""

    def _submit_coord(self):
        """Main-Thread: Nutzer klickt OK oder drückt Enter."""
        self._coord_result = self._coord_var.get().strip()
        self._coord_var.set("")
        self._coord_event.set()

    # ── Poll-Timer (Main-Thread, alle 40 ms) ─────────────────────────────────

    def _poll(self):
        try:
            while True:
                msg, tag = self._log_q.get_nowait()
                if msg == "\x00CLEAR":
                    self._log_widget.config(state="normal")
                    self._log_widget.delete("1.0", "end")
                    self._log_widget.config(state="disabled")
                elif msg == "\x00SHOW_INPUT":
                    self._coord_frame.grid()
                    self._coord_entry.focus_set()
                elif msg == "\x00HIDE_INPUT":
                    self._coord_frame.grid_remove()
                else:
                    self._append_log(msg, tag)
        except queue.Empty:
            pass

        # Worker fertig?
        if self._worker is not None and not self._worker.is_alive():
            self._worker = None
            self._set_buttons_running(False)
            if not self._status_var.get().startswith("Abgebrochen"):
                if "FEHLER" not in self._status_var.get():
                    self._status_var.set("Fertig.")

        self.root.after(40, self._poll)

    # ── Robot-Worker (Hintergrund-Thread) ────────────────────────────────────

    def _robot_worker(self, cfg: dict):

        def log(text: str, tag: str | None = None):
            self._log_q.put((text + "\n", tag))

        def check():
            """Pause abwarten + Stop prüfen."""
            if self._stop_event.is_set():
                raise _StopException()
            self._pause_event.wait()
            if self._stop_event.is_set():
                raise _StopException()

        # ── Konfiguration parsen ──────────────────────────────────────────────
        ROBOT_IP          = cfg["ip"]
        ROBOT_PORT        = int(cfg["port"])
        NUM_PARTS         = int(cfg["num_parts"])
        MOVE_VELOCITY     = float(cfg["velocity"])
        PICK_CENTER_X     = float(cfg["pick_cx"])
        PICK_CENTER_Y     = float(cfg["pick_cy"])
        SAFE_PICK_Z       = float(cfg["pick_z_safe"])
        GRIP_Z            = float(cfg["pick_z_grip"])
        TOOL_A_DOWN       = float(cfg["tool_a"])
        TOOL_B_DOWN       = float(cfg["tool_b"])
        TOOL_C_DOWN       = float(cfg["tool_c"])
        PLACE_X_START     = float(cfg["place_xs"])
        PLACE_X_STEP      = float(cfg["place_xst"])
        PLACE_Y           = float(cfg["place_y"])
        PLACE_Z_SAFE      = float(cfg["place_zs"])
        PLACE_Z_DROP      = float(cfg["place_zd"])
        ROTATE_DEG        = float(cfg["rotate_deg"])
        SAFE_ROTATE_JOINTS = [float(v) for v in cfg["safe_joints"].split()]
        FILL_WAIT_S       = 2.0

        robot: CRIController = CRIController()

        # ── Bewegungsfunktionen ───────────────────────────────────────────────

        def move_cart(x, y, z, a, b, c, label=""):
            check()
            log(f"   [MOVE  Cart ] X={x:7.1f} Y={y:7.1f} Z={z:6.1f}"
                f" | A={a:5.1f} B={b:5.1f} C={c:6.1f}", "info")
            ok = robot.move_cartesian(
                X=x, Y=y, Z=z, A=a, B=b, C=c,
                E1=0.0, E2=0.0, E3=0.0,
                velocity=MOVE_VELOCITY,
                wait_move_finished=True,
            )
            if not ok:
                raise RuntimeError(f"Kartesische Bewegung fehlgeschlagen: {label}")

        def move_jnt(joints, label=""):
            check()
            js = " ".join(f"{v:6.1f}" for v in joints)
            log(f"   [MOVE  Joint] A1..A6 = [{js} ]", "info")
            a1, a2, a3, a4, a5, a6 = joints
            ok = robot.move_joints(
                A1=a1, A2=a2, A3=a3, A4=a4, A5=a5, A6=a6,
                E1=0.0, E2=0.0, E3=0.0,
                velocity=MOVE_VELOCITY,
                wait_move_finished=True,
            )
            if not ok:
                raise RuntimeError(f"Gelenkbewegung fehlgeschlagen: {label}")

        def set_axis(axis_idx, value, base_joints):
            joints = list(base_joints)
            joints[axis_idx] = value
            log(f"   [AXIS  A{axis_idx+1}  ] -> {value:.1f} Grad", "info")
            move_jnt(joints, f"Achse {axis_idx+1} -> {value:.1f}")
            return joints

        def do_gripper(close: bool):
            action = ">>> SCHLIESSEN" if close else "<<< OEFFNEN"
            log(f"   [GRIPPER    ] {action}", "ok" if close else "info")
            robot.set_active_control(True)
            robot.set_dout(30, not close)
            time.sleep(0.5)

        # ── EYE+-Simulation ───────────────────────────────────────────────────

        def get_part():
            log("\n" + "-" * 60)
            log("  EYE+ get_part -> Koordinaten eingeben (x  y  rz)")
            log("  Leer + OK     -> kein Teil gefunden")
            log("-" * 60)

            raw = self._request_coord_from_worker()

            if self._stop_event.is_set():
                raise _StopException()

            if not raw:
                log("  -> kein Teil erkannt.")
                return False, None, None, None

            toks = raw.replace(",", " ").split()
            try:
                x  = float(toks[0])
                y  = float(toks[1])
                rz = float(toks[2]) if len(toks) >= 3 else 0.0
            except (IndexError, ValueError):
                log("  [!] Ungültige Eingabe -> kein Teil.", "err")
                return False, None, None, None

            log(f"  -> Teil: x={x:.2f}  y={y:.2f}  rz={rz:.2f}", "ok")
            return True, x, y, rz

        # ── Hauptablauf ───────────────────────────────────────────────────────
        try:
            log(f"Verbinde mit iRC-Sim {ROBOT_IP}:{ROBOT_PORT} …", "head")
            robot.connect(host=ROBOT_IP, port=ROBOT_PORT)
            log("[ROBOT] verbunden.", "ok")
            check()

            log("[ROBOT] Warte auf Kinematik …")
            if not robot.wait_for_kinematics_ready(timeout=30):
                raise RuntimeError("Kinematik nicht bereit (Timeout 30 s).")
            check()

            log("[ROBOT] Aktiviere Steuerung …")
            if not robot.set_active_control(True):
                raise RuntimeError("Active Control fehlgeschlagen.")
            robot.reset()
            if not robot.enable():
                raise RuntimeError("Enable fehlgeschlagen.")
            log("[ROBOT] bereit.\n", "ok")

            log("[EYE+] Simulation gestartet.\n", "head")

            # Erstes Bild
            found, x, y, rz = get_part()
            if not found:
                log("[FILL] Kein Teil -> Cube befüllen (simuliert).")
                time.sleep(FILL_WAIT_S)
                check()
                found, x, y, rz = get_part()
            else:
                log("[FILL] Teil vorhanden -> kein Füllen nötig.")

            picked    = 0
            next_part = (found, x, y, rz) if found else None

            while picked < NUM_PARTS:
                check()

                if next_part is None or not next_part[0]:
                    found, x, y, rz = get_part()
                    next_part = (found, x, y, rz)

                if not next_part[0]:
                    log("[LOOP] Kein Kandidat -> nachfüllen + neuer Versuch.")
                    time.sleep(FILL_WAIT_S)
                    check()
                    found, x, y, rz = get_part()
                    next_part = (found, x, y, rz)
                    if not next_part[0]:
                        continue

                found, x, y, rz = next_part
                grip_a = TOOL_A_DOWN + rz

                log(f"\n{'#'*14}  Teil {picked+1}/{NUM_PARTS}"
                    f"  (x={x:.1f}  y={y:.1f}  rz={rz:.1f})  {'#'*14}", "head")

                log("  Schritt: SAFE-TO-PICK anfahren")
                move_cart(PICK_CENTER_X, PICK_CENTER_Y, SAFE_PICK_Z,
                          grip_a, TOOL_B_DOWN, TOOL_C_DOWN, "Safe-Pick")

                log("  Schritt: über Teil absenken + greifen")
                move_cart(x, y, SAFE_PICK_Z,
                          grip_a, TOOL_B_DOWN, TOOL_C_DOWN, "Hover Pick")
                move_cart(x, y, GRIP_Z,
                          grip_a, TOOL_B_DOWN, TOOL_C_DOWN, "Greifhöhe")
                do_gripper(close=True)
                check()

                if picked + 1 < NUM_PARTS:
                    log("[EYE+] prepare_part -> nächstes Teil wird analysiert.")

                log("  Schritt: zurück SAFE-TO-PICK")
                move_cart(x, y, SAFE_PICK_Z,
                          grip_a, TOOL_B_DOWN, TOOL_C_DOWN, "Hoch nach Pick")

                log("  Schritt: einfahren -> SAFE-TO-ROTATE")
                rotate_base = list(SAFE_ROTATE_JOINTS)
                move_jnt(rotate_base, "Safe-Rotate")

                log("  Schritt: A1 drehen")
                a1_target = rotate_base[0] + ROTATE_DEG
                rotated   = set_axis(0, a1_target, rotate_base)

                place_x = PLACE_X_START + picked * PLACE_X_STEP
                log(f"  Schritt: ausfahren + ablegen  (X={place_x:.0f})")
                move_cart(place_x, PLACE_Y, PLACE_Z_SAFE,
                          TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN, "Hover Ablage")
                move_cart(place_x, PLACE_Y, PLACE_Z_DROP,
                          TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN, "Ablagehöhe")
                do_gripper(close=False)
                check()
                move_cart(place_x, PLACE_Y, PLACE_Z_SAFE,
                          TOOL_A_DOWN, TOOL_B_DOWN, TOOL_C_DOWN, "Hoch nach Ablage")

                log("  Schritt: einfahren -> Safe-Rotate (A1 noch rotiert)")
                move_jnt(rotated, "Safe-Rotate rotiert")

                log("  Schritt: A1 zurückrotieren")
                set_axis(0, rotate_base[0], rotated)

                picked += 1

                if picked < NUM_PARTS:
                    log("[SYNC] Warte auf EYE+ Analyse …")
                    time.sleep(1.0)
                    check()
                    found, x, y, rz = get_part()
                    next_part = (found, x, y, rz)

            log(f"\n=== FERTIG: {picked} Teil(e) abgelegt. ===", "ok")
            self._status_var_safe("Fertig.")

        except _StopException:
            log("\n[ABBRUCH] durch Benutzer.", "err")
            self._status_var_safe("Abgebrochen.")

        except (Exception) as e:
            msg = f"{type(e).__name__}: {e}"
            log(f"\n[FEHLER] {msg}", "err")
            self._status_var_safe(f"FEHLER: {msg}")

        finally:
            for fn in (
                lambda: robot.disable(),
                lambda: robot.set_active_control(False),
                lambda: robot.close(),
            ):
                try:
                    fn()
                except Exception:
                    pass
            log("\n[ENDE] Verbindung getrennt.")

    def _status_var_safe(self, text: str):
        """Status aus Worker-Thread setzen (via after)."""
        self.root.after(0, lambda: self._status_var.set(text))


# ── Einstiegspunkt ────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.25)   # etwas größere UI auf FullHD
    except Exception:
        pass
    app = PickPlaceApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
