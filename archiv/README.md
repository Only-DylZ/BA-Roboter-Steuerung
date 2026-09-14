# Archiv

Hier liegen Skripte, die **nicht** mehr zum aktiven Projekt gehoeren. Das
Hauptprogramm `pick_and_place_gui_v2.py` verwendet keine dieser Dateien.
Sie sind nur zu Dokumentationszwecken aufgehoben (Bachelorarbeit).

## Ueberholte Versionen

| Datei | Ersetzt durch |
|---|---|
| `pick_and_placeV0.py` | `pick_and_placeV1.py` bzw. `pick_and_placeV1_SIM.py` |
| `pick_and_place_gui.py` | `pick_and_place_gui_v2.py` (Hauptprogramm) |

## Einzelne Hilfsskripte

| Datei | Zweck |
|---|---|
| `asyril_get_part.py` | Erster Test der EYE+ Socket-Kommunikation |
| `asyril_get_part1.py` | Erweiterte Fassung davon |
| `test_greifer.py` | Manueller Greifer-Test (DOut31/32 gegen die iRC-Anzeige) |

## Hinweis zum Ausfuehren

Skripte, die Projektmodule brauchen (`libs.CRI_Python_Lib`, `pick_and_placeV1`),
haben oben einen kleinen sys.path-Eintrag, der den Projekt-Root ergaenzt. Damit
laufen sie auch aus diesem Unterordner heraus unveraendert weiter.
