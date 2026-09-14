#!/usr/bin/env python3
"""
Asyril EYE+ - Teil-Koordinaten abfragen
=========================================
Verbindet sich mit dem EYE+ Controller, fordert ein Teil an (get_part)
und gibt die Koordinaten + Orientierung im ROBOTER-Koordinatensystem aus.

Voraussetzung: Setup ist komplett kalibriert (Hand-Auge-Kalibrierung +
Rezept) und EYE+ laeuft im Produktionsmodus (start production).

Es wird NOCH KEIN Roboter angesteuert - das Skript zeigt nur die
Koordinaten, damit du pruefen kannst, ob sie stimmen.
"""

import socket

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
EYE_IP   = "192.168.3.20"   # IP des EYE+ Controllers
EYE_PORT = 7171             # Standard-TCP-Port von EYE+
TIMEOUT  = 35.0             # Sekunden (get_part hat selbst 30s Default-Timeout)
EOL      = "\n"             # Standard-Delimiter laut Asyril-Doku (LF)

# Feste Z-Hoehe des Roboters beim Greifen (vom Nutzer vorgegeben)
ROBOT_Z_PICK = 140.0

# Rezept-ID. Wenn None, versucht das Skript die ID automatisch aus
# get_recipe_list zu ermitteln (nimmt das erste gefundene Rezept).
# Falls du mehrere Rezepte hast, trage hier deine gewuenschte ID fest ein,
# z.B. RECIPE_ID = 21180
RECIPE_ID = None


def send_command(sock: socket.socket, command: str) -> str:
    """Sendet einen ASCII-Befehl und liest die Antwortzeile."""
    sock.sendall((command + EOL).encode("ascii"))

    # Antwort lesen, bis ein LF kommt (eine Zeile)
    buffer = b""
    while not buffer.endswith(b"\n"):
        chunk = sock.recv(4096)
        if not chunk:
            break
        buffer += chunk
    return buffer.decode("ascii").strip()


def parse_get_part(response: str) -> dict:
    """
    Zerlegt die get_part-Antwort.
    Format:  200 x=<x> y=<y> rz=<rz>
    Gibt dict mit x, y, rz zurueck (oder wirft bei Fehler eine Exception).
    """
    parts = response.split()
    code = parts[0]
    if code != "200":
        raise RuntimeError(f"EYE+ Fehlerantwort: {response}")

    values = {}
    for token in parts[1:]:
        if "=" in token:
            key, val = token.split("=", 1)
            values[key] = float(val)

    if not all(k in values for k in ("x", "y", "rz")):
        raise RuntimeError(f"Unerwartetes Antwortformat: {response}")

    return {"x": values["x"], "y": values["y"], "rz": values["rz"]}


def main():
    print(f"Verbinde mit EYE+ unter {EYE_IP}:{EYE_PORT} ...")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(TIMEOUT)
        sock.connect((EYE_IP, EYE_PORT))
        print("Verbunden.\n")

        # Aktuellen Zustand pruefen
        state_resp = send_command(sock, "get_parameter state")
        print(f"Aktueller Zustand: {state_resp}")

        if "production" not in state_resp:
            # Nicht in Produktion -> Rezept-ID ermitteln und Produktion starten
            recipe_id = RECIPE_ID
            if recipe_id is None:
                print("Frage Rezeptliste ab (get_recipe_list) ...")
                list_resp = send_command(sock, "get_recipe_list")
                print(f"Rezeptliste: {list_resp}")
                # Letzte Zahl in der Antwort als Rezept-ID interpretieren
                digits = [t for t in list_resp.replace("=", " ").split() if t.isdigit()]
                recipe_id = digits[-1] if digits else None
                if recipe_id is None:
                    raise RuntimeError(
                        "Keine Rezept-ID gefunden. Trage RECIPE_ID manuell oben im Skript ein."
                    )
                print(f"Verwende Rezept-ID: {recipe_id}")

            print(f"Starte Produktion (start production {recipe_id}) ...")
            start_resp = send_command(sock, f"start production {recipe_id}")
            print(f"Antwort: {start_resp}")
            if not start_resp.startswith("200"):
                raise RuntimeError(f"Produktionsstart fehlgeschlagen: {start_resp}")
        else:
            print("EYE+ ist bereits in Produktion - kein Neustart noetig.")
        print()

        # Teil anfordern. get_part nimmt bei Bedarf automatisch ein Bild auf
        # und vibriert, bis ein gutes Teil gefunden wird (oder Timeout).
        print("Sende 'get_part' (EYE+ nimmt ggf. Bild auf / vibriert) ...")
        response = send_command(sock, "get_part")
        print(f"Rohantwort: {response}\n")

        coords = parse_get_part(response)

        # EYE+ liefert dank Hand-Auge-Kalibrierung bereits Roboterkoordinaten.
        # Z setzen wir selbst, da das Vision-System keine Hoehe liefert.
        robot_x  = coords["x"]
        robot_y  = coords["y"]
        robot_rz = coords["rz"]
        robot_z  = ROBOT_Z_PICK

        print("=" * 50)
        print("  GEFUNDENES TEIL - Roboterkoordinaten")
        print("=" * 50)
        print(f"  X  = {robot_x:10.5f} mm")
        print(f"  Y  = {robot_y:10.5f} mm")
        print(f"  Z  = {robot_z:10.5f} mm  (fest vorgegeben)")
        print(f"  Rz = {robot_rz:10.2f} Grad  (Orientierung)")
        print("=" * 50)

        # ---- Hier spaeter die Roboteransteuerung einbauen ----
        # 1) Move nach (robot_x, robot_y, robot_z) mit Orientierung robot_rz
        # 2) Greifer schliessen
        # 3) Senkrecht nach oben fahren (nur Z erhoehen, X/Y/Rz gleich)
        # ------------------------------------------------------


if __name__ == "__main__":
    main()
