#!/usr/bin/env python3
"""Greifer-Test: oeffnen und schliessen ohne den vollen Pick-and-Place-Ablauf."""

from pick_and_placeV1 import CriRobot, ROBOT_IP, ROBOT_PORT
import time

robot = CriRobot(ROBOT_IP, ROBOT_PORT)
robot.connect()
robot.init()   # CMD Reset + CMD Enable  -- ohne das werden DOUT-Befehle ignoriert
time.sleep(0.5)

print("Greifer OEFFNEN  ->  IRC erwartet: DOut31=0, DOut32=1")
robot.gripper(close=False)
input("Stimmt die IRC-Anzeige? [Enter druecken]")

print("Greifer SCHLIESSEN  ->  IRC erwartet: DOut31=1, DOut32=0")
robot.gripper(close=True)
input("Stimmt die IRC-Anzeige? [Enter druecken]")

print("Test abgeschlossen.")
robot.close()
