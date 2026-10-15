"""checkin.py - one periodic check of the bot: saves the screen to debug/check_latest.jpg and prints
a one-line summary (clock/score text, radar state, last bot actions)."""
import os
import sys
import time

import cv2

import football_ai as f

name = sys.argv[1] if len(sys.argv) > 1 else "C31"
log = sys.argv[2] if len(sys.argv) > 2 else os.path.join(f.HERE, "debug", "run21.log")
rm = f.Remote(name)
rm.snap_path = os.path.join(f.HERE, "debug", "_check.png")
fr = None
for _ in range(3):
    fr = rm.snap()
    if fr is not None:
        break
    time.sleep(0.3)
if fr is None:
    print("no picture")
    sys.exit(0)
cv2.imwrite(os.path.join(f.HERE, "debug", "check_latest.jpg"), fr)
sb = ""
if f.scoreboard(fr) and f.OCR:
    g = cv2.resize(cv2.cvtColor(fr[38:90, 60:200], cv2.COLOR_BGR2GRAY), None, fx=3, fy=3)
    sb = f.OCR.text(g)
try:
    lines = open(log, encoding="utf-8", errors="replace").read().splitlines()[-40:]
except OSError:
    lines = []
acts = {}
for l in lines:
    for w in ("shoot", "pass", "tackle", "dribble", "chase", "press", "switch", "blind", "skip", "menu", "corner", "set", "half", "no radar"):
        if w in l:
            acts[w] = acts.get(w, 0) + 1
            break
print(time.strftime("%H:%M:%S"), "| scoreboard:", sb or "-", "| radar:", f.radar_visible(fr), "| last40:", acts)
