"""nudge_test.py - does a small left-stick move bring a faded radar back? prints radar state over time"""
import time

import football_ai as f

rm = f.Remote("C31")
rm.cmd("release")


def state(tag):
    fr = rm.snap()
    print("%-12s radar visible: %s" % (tag, f.radar_visible(fr)), flush=True)


state("before")
for i in range(6):
    rm.cmd("stick l %.2f 0" % (0.35 if i % 2 == 0 else -0.35))
    time.sleep(0.15)
rm.cmd("stick l 0 0")
for k in range(8):
    time.sleep(0.25)
    state("after %.2fs" % (0.25 * (k + 1)))
rm.cmd("release")
