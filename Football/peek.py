"""peek.py - print bot/health state of a remote and save its current picture to debug/now.png"""
import os
import sys

import football_ai as f

rm = f.Remote(sys.argv[1] if len(sys.argv) > 1 else "C31")
print("bot:", rm.cmd("bot"), "| health:", rm.cmd("health"))
out = os.path.join(f.HERE, "debug", "now.png")
print(rm.cmd("snap " + out))
fr = rm.snap()
print("radar visible:", f.radar_visible(fr))
