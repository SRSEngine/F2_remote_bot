"""step.py - press one button on the remote, wait, save the screen to debug/step.jpg and print its text
    python step.py C31 x        python step.py C31 none   (just look)"""
import os
import sys
import time

import cv2

import football_ai as f

name, btn = sys.argv[1], sys.argv[2]
wait = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
rm = f.Remote(name)
rm.snap_path = os.path.join(f.HERE, "debug", "_step.png")
if btn != "none":
    print(rm.cmd("press %s 90" % btn))
    time.sleep(wait)
fr = rm.snap()
cv2.imwrite(os.path.join(f.HERE, "debug", "step.jpg"), fr)
print(f.screen_text(fr)[:300])
