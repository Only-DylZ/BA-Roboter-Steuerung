#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 Diagnose: EYE+ rz-Winkel pruefen (180-Grad-Ambiguitaet der Bilderkennung)
================================================================================

Zweck:
  Klaeren, ob die 180-Grad-Fehlgriffe aus der Bilderkennung kommen.
  Der Roboter wird NICHT bewegt -- es wird nur EYE+ abgefragt.

Funktioniert auch mit MEHREREN Teilen auf der Platte:
  Pro Messung werden ALLE erkannten Teile ausgelesen (get_part wiederholt,
  bis keins mehr kommt) und als Tabelle mit x/y/rz angezeigt. Beim ersten
  Durchgang waehlst du dein Referenzteil per Nummer aus; danach wird es
  automatisch ueber seine x/y-Position wiedergefunden (naechstes Teil zur
  letzten bekannten Position).

Vorgehen:
  1. Skript starten (startet Production mit dem Produktions-Rezept).
  2. Referenzteil in bekannter Orientierung auflegen, Enter -> Teil waehlen.
  3. Teil von Hand um exakt 180 Grad drehen (Position moeglichst beibehalten).
  4. Wieder Enter -> angezeigte rz-Differenz muss ~180 Grad sein.

Bewertung:
  - rz folgt der 180-Grad-Drehung  -> Erkennung eindeutig, Fehler woanders.
  - Differenz ~0 Grad              -> EYE+ erkennt das Teil 180-Grad-symmetrisch
                                      (Rezept/Teilemodell in EYE+ Studio pruefen:
                                      Symmetrie-Einstellung bzw. das
                                      asymmetrische Merkmal muss im Modell
                                      enthalten und kontrastreich genug sein).
  - rz springt ohne Drehen         -> Merkmal zu schwach, Erkennung raet.
    (mehrfach Enter ohne Anfassen)
================================================================================
"""

import math

from pick_and_placeV1 import EyePlusClient, EYE_IP, EYE_PORT, RECIPE_ID_PROD

# Teile, die weiter als so viele mm von der letzten Position des
# Referenzteils entfernt sind, gelten nicht mehr als dasselbe Teil.
MATCH_MAX_DIST_MM = 40.0


def parse_part(payload):
    """Antwort-Payload von get_part in ein Feld-Dict wandeln (Rohwerte)."""
    fields = {}
    text = " ".join(payload) if isinstance(payload, list) else str(payload)
    for tok in text.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            try:
                fields[k] = float(v)
            except ValueError:
                pass
    return fields if ("x" in fields and "y" in fields) else None


def get_all_parts(eye, max_parts=20):
    """Alle im letzten Bild erkannten Teile abholen (get_part bis Fehlcode)."""
    parts = []
    for _ in range(max_parts):
        code, payload = eye.send("get_part")
        if code != 200:
            break
        fields = parse_part(payload)
        if fields is None:
            break
        parts.append(fields)
    return parts


def print_parts(parts):
    print(f"    {len(parts)} Teil(e) erkannt:")
    for i, p in enumerate(parts):
        print(f"      [{i}]  x={p['x']:7.1f}  y={p['y']:7.1f}"
              f"  rz(roh)={p.get('rz', 0.0):7.2f}")


def nearest_part(parts, ref_xy):
    """Teil mit kleinstem Abstand zu ref_xy; (index, distanz) oder (None, _)."""
    best_i, best_d = None, float("inf")
    for i, p in enumerate(parts):
        d = math.hypot(p["x"] - ref_xy[0], p["y"] - ref_xy[1])
        if d < best_d:
            best_i, best_d = i, d
    return best_i, best_d


def choose_part(parts):
    """Benutzer waehlt das Referenzteil per Index."""
    while True:
        raw = input(f"    Nummer des Referenzteils (0..{len(parts) - 1}): ")
        try:
            idx = int(raw.strip())
            if 0 <= idx < len(parts):
                return idx
        except ValueError:
            pass
        print("    Ungueltige Eingabe.")


def main():
    eye = EyePlusClient(EYE_IP, EYE_PORT)
    eye.connect()
    try:
        eye.start_production(RECIPE_ID_PROD)
        print("\nReferenzteil in bekannter Orientierung auflegen, dann Enter."
              "\nZwischen den Messungen das Teil um 180 Grad drehen"
              "\n(Position moeglichst beibehalten). Beenden mit Strg+C.\n")
        ref_xy = None       # letzte bekannte Position des Referenzteils
        prev_rz = None
        n = 0
        while True:
            input(f"--- Messung {n + 1}: Enter druecken ---")
            eye.force_take_image()
            parts = get_all_parts(eye)
            if not parts:
                print("    kein Teil erkannt -> Beleuchtung/Lage pruefen, "
                      "nochmal versuchen.\n")
                continue
            print_parts(parts)

            if ref_xy is None:
                idx = choose_part(parts) if len(parts) > 1 else 0
            else:
                idx, dist = nearest_part(parts, ref_xy)
                if dist > MATCH_MAX_DIST_MM:
                    print(f"    WARN: naechstes Teil ist {dist:.0f} mm von der "
                          f"letzten Position entfernt (Platte vibriert?).")
                    idx = choose_part(parts)
                else:
                    print(f"    Referenzteil wiedergefunden: [{idx}] "
                          f"(Abstand {dist:.1f} mm)")

            p  = parts[idx]
            rz = p.get("rz", 0.0)
            line = (f"    >>> Referenzteil:  x={p['x']:7.1f}  y={p['y']:7.1f}"
                    f"  rz(roh)={rz:7.2f}")
            if prev_rz is not None:
                # Differenz zur letzten Messung, auf (-180, 180] normalisiert
                d = ((rz - prev_rz + 180.0) % 360.0) - 180.0
                line += f"\n    >>> Differenz zur letzten Messung: {d:+.1f} Grad"
            print(line + "\n")
            ref_xy  = (p["x"], p["y"])
            prev_rz = rz
            n += 1
    except KeyboardInterrupt:
        print("\n[ENDE] durch Benutzer.")
    finally:
        try:
            eye.stop_production()
        except Exception:
            pass
        eye.close()


if __name__ == "__main__":
    main()
