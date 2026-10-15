"""release.py - let go of every button and center the sticks on a remote (after a killed run)"""
import sys

import football_ai as f

rm = f.Remote(sys.argv[1] if len(sys.argv) > 1 else "C31")
print(rm.cmd("release"))
