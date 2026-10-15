"""mainview.py - read the main picture (not the radar): where is our controlled player (the small
triangle above him) and is the ball at his feet. Used when the radar is hidden or faded."""
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_TPL = None


def _templates():
    global _TPL
    if _TPL is None:
        import glob
        _TPL = [cv2.imread(p, cv2.IMREAD_GRAYSCALE) for p in sorted(glob.glob(os.path.join(HERE, "marker_tpl*.png")))]
    return _TPL


def make_template(frame, x, y, tag=""):
    """cut the marker centred at (x, y) out of a frame and save it as a template"""
    c = cv2.cvtColor(frame[y - 7:y + 7, x - 8:x + 8], cv2.COLOR_BGR2GRAY)
    cv2.imwrite(os.path.join(HERE, "marker_tpl%s.png" % tag), c)


def find_marker(frame, thr=0.72):
    """(x, y) of the control marker in the 1280x720 frame, or None"""
    g = cv2.cvtColor(frame[95:600], cv2.COLOR_BGR2GRAY)
    best = (thr, None)
    for tpl in _templates():
        r = cv2.matchTemplate(g, tpl, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(r)
        if mx > best[0]:
            best = (mx, (loc[0] + tpl.shape[1] // 2, loc[1] + 95 + tpl.shape[0] // 2))
    return best[1]


def ball_at_feet(frame, marker):
    """True if a small white round blob (the ball) is just below the marker, at the player's feet"""
    if marker is None:
        return None
    x, y = marker
    x0, x1, y0, y1 = max(0, x - 40), min(1280, x + 40), y + 25, min(720, y + 105)
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    m = ((hsv[..., 2] > 185) & (hsv[..., 1] < 60)).astype(np.uint8)
    n, _, st, cen = cv2.connectedComponentsWithStats(m)
    for i in range(1, n):
        a, w, h = st[i, 4], st[i, 2], st[i, 3]
        if 8 <= a <= 70 and w <= 11 and h <= 11 and 0.6 <= w / max(h, 1) <= 1.7:
            # the ball sits low (feet), not at the shirt/shorts height
            if cen[i][1] + y0 > y + 40:
                # a real ball lies on grass: most of a ring around it is green (shorts/socks are not)
                bx, by = int(cen[i][0]), int(cen[i][1])
                ring = hsv[max(0, by - 9):by + 10, max(0, bx - 9):bx + 10]
                hh, ss = ring[..., 0], ring[..., 1]
                grass = ((hh >= 30) & (hh <= 90) & (ss > 60)).mean()
                if grass > 0.45:
                    return True
    return False
