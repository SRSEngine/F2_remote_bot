"""pipecheck.py - remote input health: stats, health, bot state, last command"""
import sys

import football_ai as f

rm = f.Remote(sys.argv[1] if len(sys.argv) > 1 else "C31")
for c in ("health", "bot", "stats", "state", "last"):
    print(c, "->", rm.cmd(c)[:300])
