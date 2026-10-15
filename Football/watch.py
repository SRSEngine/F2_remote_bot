"""watch.py - take N pictures of a remote, every S seconds, into debug/watch_XX.jpg (half size)"""
import os
import sys
import time

import cv2

import football_ai as f

name = sys.argv[1] if len(sys.argv) > 1 else "C31"
n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
gap = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
rm = f.Remote(name)
rm.snap_path = os.path.join(f.HERE, "debug", "_watch.png")
for i in range(n):
    fr = rm.snap()
    if fr is not None:
        cv2.imwrite(os.path.join(f.HERE, "debug", "watch_%02d.jpg" % i), fr)
    time.sleep(gap)
print("done")
