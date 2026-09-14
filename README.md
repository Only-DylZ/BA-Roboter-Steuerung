# Pick & Place Steuerung — igus ReBeL 6-DOF + Asyril EYE+

Grafische Steuerung für eine Pick-and-Place-Zelle: Eine Asyril-EYE+-Kamera
erkennt Bauteile auf einer Zuführplatte (Asycube), ein igus-ReBeL-Roboterarm
greift sie und legt sie an definierten Positionen ab.

Das Programm richtet sich an Anwender, die die Anlage **bedienen**, ohne den
Quellcode zu kennen. Alle Parameter lassen sich in der Oberfläche eingeben.

---

## Inhalt

1. [Schnellstart](#1-schnellstart)
2. [Voraussetzungen](#2-voraussetzungen)
3. [Die drei Betriebsmodi](#3-die-drei-betriebsmodi)
4. [Die Oberfläche im Detail](#4-die-oberfläche-im-detail)
5. [Alle Einstellungen erklärt](#5-alle-einstellungen-erklärt)
6. [Was der Roboter tatsächlich tut](#6-was-der-roboter-tatsächlich-tut)
7. [Änderungen vornehmen](#7-änderungen-vornehmen)
8. [Projektstruktur](#8-projektstruktur)
9. [Fehlerbehebung](#9-fehlerbehebung)

---

## 1. Schnellstart

### Variante A — fertige EXE (kein Python nötig)

1. Lade `PickAndPlace.exe` aus dem aktuellen Release runter und öffne es.
2. Oben den **Modus** wählen.
3. Links die Parameter prüfen (Standardwerte sind bereits gesetzt).
4. **START** drücken.

> **Wichtig:** Die EXE enthält eine **eingefrorene Kopie** des Programmcodes.
> Änderungen am Python-Skript wirken sich **nicht** auf eine bereits gebaute
> EXE aus — sie muss danach neu erzeugt werden. Siehe
> [Abschnitt 7.3](#73-die-exe-nach-änderungen-neu-bauen).

### Variante B — direkt aus Python

```bat
cd BA_PY_Skript
python pick_and_place_gui_v2.py
```

Das Programm muss **aus seinem eigenen Ordner** gestartet werden, sonst findet
es die Roboter-Bibliothek in `libs/` nicht.

### Der erste Versuch: immer erst in der Simulation

Wer die Anlage noch nicht kennt, startet im Modus **Simulation**. Dort bewegt
sich nur der virtuelle Roboter im iRC-Simulator — echte Hardware wird nicht
angesprochen, es kann nichts beschädigt werden.

---

## 2. Voraussetzungen

### 2.1 Der Rechner muss im selben Netz hängen wie die Geräte

Roboter und Kamera sind über Ethernet angebunden und haben feste IP-Adressen:

| Gerät | Standard-IP | Port | Wofür |
|---|---|---|---|
| igus ReBeL (Robotersteuerung) | `192.168.3.11` | `3920` | Bewegungsbefehle (CRI-Protokoll) |
| Asyril EYE+ (Kamera/Controller) | `192.168.3.20` | `7171` | Bauteilkoordinaten |
| iRC-Simulator (lokal) | `127.0.0.1` | `3921` | nur Simulationsmodus |

Damit die Verbindung klappt, braucht der PC eine **feste IP im selben
Subnetz**, z. B. `192.168.3.100` mit Subnetzmaske `255.255.255.0`.

**Verbindung vorab testen** (Eingabeaufforderung):

```bat
ping 192.168.3.11
ping 192.168.3.20
```

Antwortet ein Gerät nicht, stimmt etwas mit Verkabelung, IP-Einstellung oder
Stromversorgung nicht — das Programm kann das nicht ausgleichen.

### 2.2 Muss die iRC-Software offen sein?

Das hängt vom Modus ab:

| Modus | iRC nötig? |
|---|---|
| **Simulation** | **Ja, zwingend.** Der simulierte Roboter *ist* das iRC-Programm. Ohne laufenden Simulator auf Port `3921` schlägt die Verbindung fehl. |
| **Produktion** | **Nicht zwingend für die Verbindung.** Das Programm spricht über Port `3920` direkt mit der Robotersteuerung. |
| **Genauigkeitstest** | wie Produktion |

**Empfehlung trotzdem: iRC offen lassen.** Gründe:

- Der Roboter muss **referenziert** (eingemessen) und **fehlerfrei** sein,
  bevor er Bewegungsbefehle annimmt. Das prüft und behebt man in iRC.
- Fehlermeldungen der Steuerung sind in iRC im Klartext zu sehen.
- Die Not-Aus- und Freigabefunktionen sind dort erreichbar.

Wenn iRC läuft, hält es zunächst die Kontrolle über den Roboter. Das Programm
fordert sie beim Start automatisch an (`SetActive`), anschließend folgen
`Reset` und `Enable` — darum muss man in iRC nichts von Hand umschalten.

> Diese Angaben stammen aus dem Programmcode und der Herstellerbibliothek. Wie
> sich die Anlage im Detail verhält, sollte beim ersten Produktionslauf
> beobachtet werden.

### 2.3 Vor dem Produktionslauf prüfen

- [ ] Roboter eingeschaltet, referenziert, keine Fehler in iRC
- [ ] Not-Aus erreichbar und frei
- [ ] Arbeitsbereich frei von Hindernissen
- [ ] Greifer (Druckluft) angeschlossen
- [ ] Asycube eingeschaltet, Bauteile auf der Platte
- [ ] EYE+ per `ping` erreichbar
- [ ] Geschwindigkeit (Override) beim ersten Lauf **niedrig** setzen, z. B. 20 %

### 2.4 Für Variante B zusätzlich

- **Python 3.10 oder neuer** (entwickelt mit 3.13), Windows
- Keine Zusatzpakete nötig — das Programm nutzt nur die Standardbibliothek
  (`tkinter`, `socket`, `threading`) und die mitgelieferte Roboter-Bibliothek
  in `libs/`

---

## 3. Die drei Betriebsmodi

Der Modus wird oben im Fenster gewählt. Die Oberfläche färbt sich passend und
blendet nur die relevanten Einstellungen ein. Beim Wechsel fragt das Programm,
ob die Standardwerte des neuen Modus geladen werden sollen.

### Simulation — *„iRC-Sim + simulierter EYE+"*

Nichts an echter Hardware bewegt sich. Der Roboter fährt im iRC-Simulator.

Die Kamera wird ebenfalls nur simuliert: Immer wenn das Programm ein Bauteil
„sehen" würde, erscheint unten das Eingabefeld **EYE+ Koordinaten** und der
Ablauf hält an. Dort gibt man die Koordinaten von Hand ein:

```
440 -5 0
```

Das bedeutet `x=440`, `y=-5`, `rz=0` (Drehwinkel des Teils in Grad). Ein
**leeres** Feld plus **OK** bedeutet „kein Teil gefunden" — damit lässt sich
auch das Nachfüll-Verhalten testen.

**Wofür:** Bewegungsabläufe und Ablagepositionen gefahrlos prüfen, bevor die
echte Anlage läuft.

### Produktion — *„echte Hardware"*

Der Vollbetrieb: EYE+ erkennt Teile, der echte Roboter greift und legt ab.
Nur in diesem Modus sichtbar sind das **Asyril-Rezept**-Feld, die
**EYE+-Protokoll**-Fenster und die EYE+-Statusanzeige.

Innerhalb der Produktion gibt es drei Varianten:

| Variante | Einstellung | Verhalten |
|---|---|---|
| **Normal** | Standard | Legt genau *Anzahl Teile* ab, jedes an einer eigenen Position (nebeneinander, Abstand = *X-Schritt*), dann Ende. |
| **Endlos** | Haken *Endlos-Modus* | Läuft bis **STOP**. Alle Teile kommen auf **dieselbe** Position (Sektion *Ablageposition (Endlos-Modus)*). |
| **Test** | Haken *Test-Modus* | Greift **genau ein** Teil und hört auf. Nutzt automatisch das Rezept `Rezept_Testmodus`; die Produktion am EYE+ wird sofort nach dem Bild gestoppt, damit der Asycube nicht weiter vibriert. Zum Prüfen von Greifpunkt und Orientierung. |

### Genauigkeitstest — *„Roboter ohne EYE+"*

Die Kamera wird gar nicht gebraucht. Der Roboter transportiert **ein** Bauteil
endlos zwischen zwei Positionen hin und her — Ablageort 1 → Ablageort 2 →
zurück → usw. Das Teil wird einmal von Hand eingelegt.

**Wofür:** Wiederholgenauigkeit messen. Nach vielen Zyklen zeigt sich, ob das
Teil noch exakt an derselben Stelle landet.

Der Test läuft **endlos** und wird über **STOP** beendet. Die Zahl der
abgeschlossenen Transfers steht in der Statuszeile.

---

## 4. Die Oberfläche im Detail

```
+--------------------------------------------------------------+
|  Pick & Place Steuerung - Asyril EYE+ + igus ReBeL 6-DOF      |
+--------------------------------------------------------------+
|  Modus:  ( ) Simulation   ( ) Produktion   ( ) Genauigkeit    |
+---------------------+----------------------------------------+
| [Standardwerte      |  Live-Terminal        o Roboter o EYE+  |
|  laden]             |  +----------------------------------+   |
|                     |  | [1] Verbinde ...                 |   |
| > Netzwerk          |  | [ROBOT] verbunden 192.168.3.11   |   |
| > Aufgabe           |  | ==== Teil 1/4  x=440 y=-5 ====   |   |
| > Asyril Rezept     |  |   -> SAFE-TO-PICK                |   |
| > Pick-Geometrie    |  +----------------------------------+   |
| > Werkzeug          |  EYE+ Protokoll   [Stop Production]     |
| > Rotation & Safe   |  +---------------+------------------+   |
| > Ablageposition    |  | Befehle       | Analyse-Status   |   |
| > Cube-Fuellung     |  +---------------+------------------+   |
| > Bewegungsparam.   |  Fortschritt: [####....]   2 / 4        |
+---------------------+----------------------------------------+
|      [ START ]      [ PAUSE ]      [ STOP / ABBRECHEN ]       |
+--------------------------------------------------------------+
|  Laeuft ...                                                   |
+--------------------------------------------------------------+
```

### Die drei Hauptknöpfe

| Knopf | Wirkung |
|---|---|
| **START** | Prüft die Eingaben, verbindet sich und startet den Ablauf. |
| **PAUSE** | Hält den Ablauf an — **nach Ende der laufenden Bewegung**, nicht mitten darin. Der Knopf heißt dann **WEITER**. |
| **STOP / ABBRECHEN** | Bricht sofort ab: Das Programm schickt umgehend einen Stoppbefehl an die Robotersteuerung und beendet danach den Ablauf. |

> **Zum STOP-Knopf:** Er stoppt die Bewegung, lässt die Motoren aber
> bestromt — der Roboter ist danach ohne Neustart wieder fahrbereit. Wie
> schnell er physisch zum Stillstand kommt, bestimmt die Bremsrampe der
> Steuerung.
>
> **Der STOP-Knopf ersetzt keinen Not-Aus.** Bei Gefahr für Personen oder
> Material gehört der Not-Aus-Schalter betätigt.

### Statusanzeigen

- **Roboter / EYE+ (Punkte)** — rot = nicht verbunden, grün = verbunden.
  Die EYE+-Anzeige erscheint nur in der Produktion.
- **Live-Terminal** — jeder Schritt mitprotokolliert, farbig nach Art
  (grün = erfolgreich, rot = Fehler, türkis = Bewegung, orange = Warnung).
  **Leeren** löscht die Anzeige.
- **EYE+ Protokoll** (nur Produktion) — links die Befehle an die Kamera, rechts
  der Analyse-Status. Nützlich, wenn die Bilderkennung klemmt.
- **Stop Production** (nur Produktion) — schickt der Kamera sofort einen
  Produktionsstopp, ohne den Roboterablauf zu beenden. Praktisch, wenn der
  Asycube weiter vibriert, obwohl genug Teile liegen.
- **Fortschritt** — z. B. `2 / 4`. Im Endlos-Modus und im Genauigkeitstest gibt
  es kein festes Ziel, der Balken zählt nur mit.

---

## 5. Alle Einstellungen erklärt

Alle Maße sind **Millimeter**, alle Winkel **Grad**. Die Werte sind
Koordinaten im Roboter-Basiskoordinatensystem.

> **Eingaben sind temporär.** Was hier eingetippt wird, gilt nur für den
> aktuellen Programmlauf und wird **nicht gespeichert**. Nach einem Neustart
> stehen wieder die Standardwerte da. Wie man Werte dauerhaft ändert, steht in
> [Abschnitt 7.2](#72-dauerhaft--standardwerte-ändern).

**Standardwerte laden** setzt alle Felder auf die Vorgaben des aktuellen Modus
zurück.

> **Zu den genannten Standardwerten:** Sie geben den Stand wieder, den die
> Skripte aktuell enthalten, und sind hier zur Orientierung aufgeführt. Da die
> Oberfläche ihre Vorgaben beim Start aus den Skriptkonstanten liest, ändern
> sie sich mit, sobald dort jemand etwas anpasst
> (siehe [7.2](#72-dauerhaft--standardwerte-ändern)). **Maßgeblich ist immer
> der Wert, der im Feld steht** — nicht der in dieser Tabelle.

### Netzwerk

| Feld | Bedeutung |
|---|---|
| **EYE+ IP / Port** | Adresse der Asyril-Kamera. Nur in der Produktion aktiv (sonst ausgegraut). Standard `192.168.3.20` : `7171` |
| **Roboter IP / Port** | Adresse der Robotersteuerung. Produktion `192.168.3.11` : `3920`, Simulation `127.0.0.1` : `3921` |

### Aufgabe

| Feld | Bedeutung |
|---|---|
| **Anzahl Teile** | Wie viele Teile im Normal-Modus abgelegt werden. Ohne Wirkung bei Endlos oder Test. |
| **Endlos-Modus** | Läuft bis STOP, alle Teile auf dieselbe Position. |
| **Test-Modus** | Nur Produktion. Ein einzelnes Teil zum Prüfen des Greifvorgangs. |

### Asyril Rezept *(nur Produktion)*

Ein Rezept ist ein am EYE+ hinterlegtes Erkennungsprogramm — es legt fest,
welches Bauteil gesucht wird und wie der Asycube rüttelt.

**Rezeptliste laden** holt die aktuell verfügbaren Rezepte vom EYE+. Beim
ersten Wechsel in den Produktionsmodus passiert das automatisch; schlägt es
fehl (Kamera nicht erreichbar), bleibt die Vorbelegung stehen:

- `23217` — Rezept_Produktion *(Standard für Normal/Endlos)*
- `11818` — Rezept_Testmodus *(wird im Test-Modus automatisch genutzt)*

Steht das gewählte Rezept nicht in der Liste des EYE+, bricht der Start mit
einer Fehlermeldung ab.

### Genauigkeitstest *(nur im Modus Genauigkeitstest)*

| Feld | Bedeutung |
|---|---|
| **Ablageort 1 — X / Y / Z** | Erste Position. Standard `-10.3 / -296.1 / 80.2` |
| **Ablageort 2 — X / Y / Z** | Zweite Position. Standard `110.6 / -389.3 / 80.2` |
| **Anfahr-Offset Z** | Wie weit über der Position angefahren wird, bevor es senkrecht heruntergeht. Standard `20` — also 20 mm Sicherheitsabstand. |

### Pick-Geometrie

Beschreibt den Bereich, in dem die Kamera Teile findet (den Asycube).

| Feld | Bedeutung |
|---|---|
| **Mitte X / Mitte Y** | Mittelpunkt der Zuführplatte. Diese Position wird vor jedem Griff sicher angefahren. Standard `440 / -5` |
| **Z-Safe** | Sichere Höhe über der Platte, in der gefahrlos verfahren werden kann. Produktion `170`, Simulation `150` |
| **Z-Greifen** | Höhe, auf der der Greifer zupackt. Produktion `158`, Simulation `140` |

> **Z-Greifen ist der heikelste Wert.** Zu hoch → das Teil wird nicht erfasst.
> Zu tief → der Greifer drückt auf die Platte. Beim Einrichten in kleinen
> Schritten herantasten, am besten im Test-Modus.

### Werkzeug-Orientierung

**A / B / C** — die Ausrichtung des Greifers in Grad. Standard `180 / 0 / 180`
entspricht „senkrecht nach unten". Diese Werte betreffen die Grundhaltung des
Werkzeugs; die Drehung des einzelnen Bauteils wird separat über das Gelenk A6
ausgeglichen.

### Rotation & Safe-Joints

| Feld | Bedeutung |
|---|---|
| **A1-Drehung** | Um wie viel Grad sich der Roboter am Sockel dreht, um von der Zuführplatte zur Ablage zu schwenken. Standard `-90` |
| **Safe-Joints A1..A6** | Sechs Gelenkwinkel, die eine eingefahrene, kollisionsfreie Haltung beschreiben. In diese Stellung fährt der Roboter **vor jeder Drehung**, damit der ausgestreckte Arm nirgends anstößt. Standard `0.0 -18.7 108.0 0.0 90.0 0.0` (leerzeichengetrennt) |

### Ablageposition (Normal-Modus)

| Feld | Bedeutung |
|---|---|
| **X-Start** | X der ersten Ablage. Produktion `-132.8`, Simulation `0` |
| **X-Schritt** | Abstand zur nächsten Ablage. Produktion `40`, Simulation `50` — bei X-Start `-132.8` und Schritt `40` also `-132.8`, `-92.8`, `-52.8` … |
| **Y** | Gemeinsame Y-Koordinate. Produktion `-392.5`, Simulation `-300` |
| **Z-Safe** | Anfahrhöhe über der Ablage. Produktion `90`, Simulation `150` |
| **Z-Ablegen** | Höhe, auf der losgelassen wird. Produktion `80.2`, Simulation `140` |

### Ablageposition (Endlos-Modus)

Dieselbe Bedeutung, aber **eine feste Position** für alle Teile (kein
X-Schritt). Standard in allen Modi `X=0 / Y=-300`, Z-Safe `150`,
Z-Ablegen `140`.

> Diese Werte weichen von der Normal-Ablage ab und sind **nicht** an die
> Skriptkonstanten gekoppelt (siehe [7.2](#72-dauerhaft--standardwerte-ändern)).
> Wer den Endlos-Modus an der echten Anlage nutzt, muss sie an die
> tatsächliche Ablagestelle anpassen.

### Cube-Füllung

Steuert, was passiert, wenn die Kamera **kein** Teil findet.

| Feld | Bedeutung |
|---|---|
| **Feeder-Befehl** | Befehl an das EYE+, der Teile nachfördert. Standard `feeder 1` |
| **Wartezeit [s]** | Pause nach dem Nachfüllen, bevor neu fotografiert wird. Standard `2.0` |
| **Min. Teile auf Platte** | **Ohne Funktion.** Das Feld existiert in der Oberfläche, wird aber vom Ablauf nicht ausgewertet. Eine Änderung bewirkt nichts. |

### Bewegungsparameter

**Override / Geschwindigkeit [%]** — begrenzt die Geschwindigkeit aller
Bewegungen, wie der Schieberegler in iRC. Standard: Produktion `50`,
Simulation `80`, Genauigkeitstest `40`.

**Jetzt setzen** überträgt den Wert **sofort an den laufenden Roboter** — der
einzige Parameter, der sich mitten im Betrieb ändern lässt. Praktisch, um
langsam anzufangen und dann hochzudrehen.

> Beim Einrichten mit **20 %** oder weniger beginnen.

---

## 6. Was der Roboter tatsächlich tut

Ablauf pro Bauteil in der Produktion (Normal-Modus):

```
 1.  Anfahren:      Mitte der Zufuehrplatte auf sicherer Hoehe (Z-Safe)
 2.  Absenken:      ueber das erkannte Teil, dann auf Z-Greifen
 3.  Ausrichten:    Gelenk A6 dreht auf den Winkel des Teils (rz)
 4.  Greifen:       Greifer schliesst
 5.  Anheben:       senkrecht auf Z-Safe (A6 bleibt gedreht)
 6.  Zurueckdrehen: A6 in Grundstellung - auf dem Weg nach oben,
                    nicht ueber der Platte
 7.  Einfahren:     Safe-To-Rotate-Stellung (kollisionsfreie Haltung)
 8.  [parallel]     EYE+ beginnt bereits, das naechste Teil zu suchen
 9.  Schwenken:     A1 dreht um die eingestellte Gradzahl
10.  Ablegen:       Ablageposition auf Z-Safe -> Z-Ablegen -> Greifer oeffnet
11.  Abheben:       zurueck auf Z-Safe
12.  Zurueck:       Safe-To-Rotate -> A1 zurueck in Grundstellung
```

Zwei Details, die den Ablauf robuster machen:

- **Safe-To-Rotate vor jeder Drehung.** Der Arm fährt erst ein, bevor der
  Sockel schwenkt — ein ausgestreckter Arm könnte sonst anstoßen.
- **Die Kamera arbeitet parallel** (Schritt 8). Sie sucht das nächste Teil,
  während der Roboter noch ablegt. Das läuft aber erst an, wenn der Arm die
  Platte verlassen hat — sonst stünde er im Bild.

**Wenn kein Teil gefunden wird:** Das Programm schickt den Feeder-Befehl,
wartet die eingestellte Zeit, fotografiert erneut. Ist die Platte dann immer
noch leer, bricht der Lauf mit einer Meldung ab.

---

## 7. Änderungen vornehmen

### 7.1 Für einen einzelnen Lauf

Werte einfach in die Oberfläche eintippen. Sie gelten bis zum Programmende und
werden nicht gespeichert.

### 7.2 Dauerhaft — Standardwerte ändern

Die Vorgabewerte stehen **nicht in der Oberfläche**, sondern als Konstanten
oben in den Ablaufskripten. Die Oberfläche liest sie beim Start von dort:

| Modus | Datei mit den Standardwerten |
|---|---|
| Produktion | `pick_and_placeV1.py` |
| Simulation | `pick_and_placeV1_SIM.py` |
| Genauigkeitstest | `genauigkeitstestV1.py` |

Beispiel — Greifhöhe dauerhaft auf 138 mm:

1. `pick_and_placeV1.py` in einem Texteditor öffnen
2. Die Zeile mit `GRIP_Z` suchen und ändern:
   ```python
   GRIP_Z = 138.0
   ```
3. Speichern, Programm neu starten — der neue Wert steht im Feld *Z-Greifen*.

Die Zuordnung Feld → Konstante:

| Feld in der Oberfläche | Konstante |
|---|---|
| EYE+ IP / Port | `EYE_IP` / `EYE_PORT` |
| Roboter IP / Port | `ROBOT_IP` / `ROBOT_PORT` |
| Anzahl Teile | `NUM_PARTS` |
| Mitte X / Y | `PICK_CENTER_X` / `PICK_CENTER_Y` |
| Z-Safe (Pick) | `SAFE_PICK_Z` |
| Z-Greifen | `GRIP_Z` |
| Werkzeug A / B / C | `TOOL_A_DOWN` / `TOOL_B_DOWN` / `TOOL_C_DOWN` |
| A1-Drehung | `ROTATE_DEG` |
| Safe-Joints | `SAFE_ROTATE_JOINTS` |
| X-Start / X-Schritt / Y | `PLACE_X_START` / `PLACE_X_STEP` / `PLACE_Y` |
| Z-Safe / Z-Ablegen (Ablage) | `PLACE_Z_SAFE` / `PLACE_Z_DROP` |
| Feeder-Befehl / Wartezeit | `FILL_FEEDER_CMD` / `FILL_WAIT_S` |
| Override | `MOVE_VELOCITY` |
| Ablageort 1 / 2 (Genauigkeit) | `PLACE1_X…` / `PLACE2_X…` in `genauigkeitstestV1.py` |
| Anfahr-Offset Z | `SAFE_Z_OFFSET` |

Die Rezept-IDs stehen dagegen ganz oben in `pick_and_place_gui_v2.py`:

```python
RECIPE_ID_TEST = "11818"   # Rezept_Testmodus
RECIPE_ID_PROD = "23217"   # Rezept_Produktion
```

### 7.3 Die EXE nach Änderungen neu bauen

**Eine bereits gebaute `PickAndPlace.exe` übernimmt keine Änderungen.** Beim
Bauen wird der gesamte Python-Code in die EXE hineinkopiert — sie ist ein
Schnappschuss vom Zeitpunkt des Builds. Wer danach ein Skript bearbeitet,
ändert die EXE nicht.

> **Merksatz: Skript geändert → EXE neu bauen.**
>
> Sonst läuft weiter der alte Stand, ohne jede Warnung. Das ist eine häufige
> Fehlerquelle: Man ändert einen Wert, startet die EXE — und nichts passiert
> anders.

**Neu bauen:** `build_exe.bat` doppelklicken. Das Skript prüft Python,
installiert bei Bedarf PyInstaller und erzeugt `dist\PickAndPlace.exe`.
Der Vorgang dauert einige Minuten.

Alternativ von Hand:

```bat
python -m PyInstaller --onefile --windowed --name PickAndPlace --clean pick_and_place_gui_v2.py
```

### 7.4 Die EXE läuft ohne Konsole — Startfehler bleiben unsichtbar

Die EXE wird mit `--windowed` gebaut, damit beim Start kein schwarzes
Konsolenfenster erscheint. Das hat einen Preis: **Stürzt sie beim Start ab,
passiert scheinbar gar nichts.** Kein Fenster, keine Meldung, kein Hinweis.

Wenn ein Doppelklick wirkungslos bleibt, das Programm stattdessen direkt aus
Python starten — dort sind alle Fehlermeldungen sichtbar:

```bat
cd BA_PY_Skript
python pick_and_place_gui_v2.py
```

Fehler **während** des Betriebs sind davon nicht betroffen: Die landen im
Live-Terminal im Fenster.

---

## 8. Projektstruktur

```
BA_PY_Skript/
|
+-- pick_and_place_gui_v2.py     <-- HAUPTPROGRAMM (die Oberflaeche)
|
+-- pick_and_placeV1.py              Ablauf + Standardwerte Produktion
+-- pick_and_placeV1_SIM.py          Ablauf + Standardwerte Simulation
+-- genauigkeitstestV1.py            Ablauf + Standardwerte Genauigkeitstest
|
+-- rz_check.py                      eigenstaendig: Drehwinkel-Auswertung
+-- wiederholgenauigkeit_x_achse.py  eigenstaendig: Messung X-Achse
+-- wiederholgenauigkeit_y_achse.py  eigenstaendig: Messung Y-Achse
|
+-- libs/CRI_Python_Lib/             Roboter-Bibliothek (CRI-Protokoll)
|
+-- build_exe.bat                    erzeugt die EXE
+-- PickAndPlace.spec                Bau-Konfiguration
+-- dist/PickAndPlace.exe            die fertige EXE (nach dem Bauen)
|
+-- archiv/                          alte Versionen, nicht mehr in Benutzung
```

Die drei Ablaufskripte in der Mitte werden vom Hauptprogramm gebraucht — sie
dürfen weder umbenannt noch verschoben werden. Die Skripte darunter sind
eigenständige Messwerkzeuge und laufen unabhängig von der Oberfläche.

Was in `archiv/` liegt, wird nicht mehr verwendet; eine eigene
[README](archiv/README.md) dort erklärt, was es damit auf sich hat.

---

## 9. Fehlerbehebung

### Doppelklick auf die EXE bewirkt nichts

Sie stürzt beim Start ab, kann es aber mangels Konsole nicht anzeigen. Über
Python starten, dann steht die Ursache im Klartext da — siehe
[Abschnitt 7.4](#74-die-exe-läuft-ohne-konsole--startfehler-bleiben-unsichtbar).

### „libs/CRI_Python_Lib konnte nicht geladen werden"

Das Programm wurde aus dem falschen Ordner gestartet oder `libs/` fehlt.
Aus `BA_PY_Skript` heraus starten und prüfen, ob der Ordner `libs` vorhanden
ist.

### Verbindung zum Roboter schlägt fehl

1. `ping 192.168.3.11` — antwortet er?
2. IP und Port in der Oberfläche gegenprüfen (Produktion `3920`,
   Simulation `3921` — eine häufige Verwechslung)
3. Ist der PC im richtigen Subnetz (`192.168.3.x`)?
4. Ist der Roboter eingeschaltet und in iRC fehlerfrei?

### Simulation verbindet nicht

Der iRC-Simulator muss laufen, bevor START gedrückt wird. Adresse dort:
`127.0.0.1`, Port `3921`.

### Roboter verbindet, bewegt sich aber nicht

Die Steuerung nimmt Befehle nur an, wenn sie freigegeben und fehlerfrei ist.
In iRC nachsehen: Liegt ein Fehler an? Ist der Roboter referenziert? Ist der
Not-Aus gelöst? Das Programm fordert die Kontrolle beim Start automatisch an —
wenn trotzdem nichts passiert, liegt es meist an einem der drei Punkte.

### EYE+ findet keine Teile

- Liegen überhaupt Teile auf der Platte?
- Passt das gewählte **Rezept** zum eingelegten Bauteil?
- Im rechten EYE+-Protokollfenster mitlesen, was die Kamera meldet
- **Rezeptliste laden** drücken — antwortet die Kamera?

### Der Greifer erfasst das Teil nicht

**Z-Greifen** stimmt nicht. Im **Test-Modus** (ein Teil pro Durchlauf) in
Schritten von 1–2 mm herantasten, bis er sicher greift.

### Der Roboter stößt beim Schwenken an

Die **Safe-Joints** passen nicht zum Aufbau. Diese Stellung muss so gewählt
sein, dass der eingefahrene Arm frei drehen kann. In iRC eine geeignete
Haltung anfahren, die sechs Gelenkwinkel ablesen und eintragen.

### STOP wirkt verzögert

Der Stoppbefehl geht sofort an die Steuerung; wie schnell der Roboter
tatsächlich steht, hängt von der Bremsrampe ab. Bei hoher
Override-Geschwindigkeit dauert es entsprechend länger. **Bei Gefahr den
Not-Aus benutzen.**

### Ich habe etwas geändert, es ändert sich nichts

Vermutlich läuft die alte EXE. Neu bauen — siehe
[Abschnitt 7.3](#73-die-exe-nach-änderungen-neu-bauen).

---

*Bachelorarbeit — Pick-and-Place-Zelle mit igus ReBeL 6-DOF und Asyril EYE+*
