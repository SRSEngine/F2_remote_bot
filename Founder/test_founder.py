# -*- coding: utf-8 -*-
"""تست بدون ریموت: یک صفحه‌ی 1280x720 مصنوعی از روی تصویرهای Templates/1080 می‌سازد.
اجرا:  python test_founder.py"""
import os
import threading
import time

import cv2
import numpy as np

from founder import ArraySource, Screen, Templates, Match

HERE = os.path.dirname(os.path.abspath(__file__))
OLD = os.path.join(HERE, "Templates", "1080")
ok_count = fail_count = 0


def check(name, cond, info=""):
    global ok_count, fail_count
    if cond:
        ok_count += 1
        print(f"  OK   {name} {info}")
    else:
        fail_count += 1
        print(f"  FAIL {name} {info}")


def paste(screen, name, x, y):
    img = cv2.imread(os.path.join(OLD, name + ".png"), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    screen[y:y + h, x:x + w] = img
    return w, h


# ---- صفحه‌ی 1920x1080 قدیمی، بعد کوچک به 1280x720 (مثل استریم جدید) ----
rng = np.random.default_rng(1)
big = (rng.integers(20, 60, (1080, 1920, 3))).astype(np.uint8)
paste(big, "Cancel", 900, 650)
paste(big, "UTCoin", 1450, 70)
paste(big, "QuickSellNow", 120, 420)
paste(big, "Ultimate", 790, 430)
for i in range(4):
    paste(big, "TRA", 300 + i * 200, 800)
frame720 = cv2.resize(big, (1280, 720), interpolation=cv2.INTER_AREA)

print("1) مختصات قدیمی 1920x1080 روی فریم 1280x720 (ref)")
scr = Screen(ArraySource(frame720), templates=OLD, ref=(1920, 1080))
m = scr.find("Cancel", 850, 600, 200, 200)
check("find Cancel", bool(m), repr(m))
check("center ~ (964, 668)", m and abs(m.x - 964) <= 3 and abs(m.y - 668) <= 3)
check("Pfind", scr.Pfind("Cancel", 850, 600, 200, 200) is True)
ok, x, y = scr.Pfind2("UTCoin", 1400, 60, 200, 50)
check("Pfind2 UTCoin", ok and abs(x - 1466) <= 3 and abs(y - 88) <= 3, f"{ok},{x},{y}")
check("not found elsewhere", not scr.find("Cancel", 0, 0, 300, 300))
check("region outside frame is safe", not scr.find("Cancel", 1800, 1000, 500, 500))
allm = scr.find_all("TRA", 0, 700, 1920, 200)
check("find_all TRA = 4", len(allm) == 4, str([(a.x, a.y) for a in allm]))
fa = scr.find_any(["Bid", "Cancel", "BuyNow"], 850, 600, 200, 200)
check("find_any -> Cancel", fa.name == "Cancel", repr(fa))

print("2) OCR")
for label, region, want in [("Cancel", (900, 650, 128, 36), "cancel"),
                            ("Quick Sell Now", (120, 420, 360, 60), "quick sell now"),
                            ("ULTIMATE", (790, 430, 342, 47), "ultimate")]:
    t0 = time.perf_counter()
    got = scr.read(*region)
    ms = (time.perf_counter() - t0) * 1000
    check(f"read {label}", want in got.lower(), f"{got!r} {ms:.1f} ms [{scr.ocr.name}]")
check("ReadText old name", "cancel" in scr.ReadText(900, 650, 128, 36).lower())
check("contains", scr.contains("Sell", 120, 420, 360, 60))
ft = scr.find_text("Sell")
check("find_text Sell (whole screen)", bool(ft) and 120 < ft.x < 480 and 420 < ft.y < 480, repr(ft))

# عدد
num = np.full((60, 260, 3), 30, np.uint8)
cv2.putText(num, "15,750", (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3)
scr2 = Screen(ArraySource(num), templates=OLD)
check("read_number 15,750", scr2.read_number() == 15750, str(scr2.read(None)))

print("3) چند thread هم‌زمان (هر ربات Screen خودش)")
errors = []


def worker():
    s = Screen(ArraySource(frame720), templates=OLD, ref=(1920, 1080))
    for _ in range(10):
        if "cancel" not in s.read(900, 650, 128, 36).lower() or not s.find("Cancel", 850, 600, 200, 200):
            errors.append(1)


ths = [threading.Thread(target=worker) for _ in range(6)]
t0 = time.perf_counter()
[t.start() for t in ths]
[t.join() for t in ths]
check("6 threads x 10 (read+find)", not errors, f"{(time.perf_counter() - t0) * 1000:.0f} ms total")

print("4) سرعت")
scr.grab()
t0 = time.perf_counter()
for _ in range(100):
    scr.find("Cancel", 850, 600, 200, 200)
check("find (small region)", True, f"{(time.perf_counter() - t0) * 10:.2f} ms each")
t0 = time.perf_counter()
for _ in range(20):
    scr.find("Cancel")
check("find (whole screen)", True, f"{(time.perf_counter() - t0) * 50:.2f} ms each")
t0 = time.perf_counter()
for _ in range(20):
    scr.read(316, 71, 140, 40)
check("read (small region)", True, f"{(time.perf_counter() - t0) * 50:.2f} ms each")

print("5) save_template و استفاده بدون ref")
tmp = Templates(os.path.join(os.environ.get("TEMP", HERE), "founder_test_tpl"))
s720 = Screen(ArraySource(frame720), templates=tmp)
s720.save_template("CancelNew", 600, 433, 86, 24)
m = s720.find("CancelNew", 550, 400, 200, 100)
check("own 720 template", bool(m) and m.score > 0.99, repr(m))

print("6) Match")
check("unpack not found", tuple(Match()) == (False, None, None))

print(f"\nنتیجه: {ok_count} OK, {fail_count} FAIL")
raise SystemExit(1 if fail_count else 0)
