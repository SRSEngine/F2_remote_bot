"""radar2.py - experimental radar reader: one colour mask, then classify each blob by its median hue.
Run:  python radar2.py debug/watch_00.jpg ...   -> prints blobs and writes debug/r2_<name>.png"""
import os
import sys

import cv2
import numpy as np

import football_ai as f


def read2(frame):
    if not f.radar_visible(frame):
        return [], [], None, None
    x0, y0, x1, y1 = f.ROI
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    col = ((S >= 55) & (V >= 115)).astype(np.uint8)
    n, lab, st, cen = cv2.connectedComponentsWithStats(col)
    ours, opp, balls, active = [], [], [], None
    for i in range(1, n):
        a, w, h = st[i, 4], st[i, 2], st[i, 3]
        if a < 4 or w > 16 or h > 16:
            continue
        hh = H[lab == i]
        red = np.mean((hh <= 12) | (hh >= 165))
        yel = np.mean((hh >= 16) & (hh <= 36))
        grn = np.mean((hh >= 38) & (hh <= 88))
        p = f.to_m(cen[i][0] + x0, cen[i][1] + y0)
        if not (-2 <= p[0] <= f.PITCH_W + 2 and -2 <= p[1] <= f.PITCH_H + 2):
            continue
        if grn > 0.6:
            if a > 48:
                active = p
            ours.append(p)
        elif yel > 0.5 and a >= 6:
            balls.append((a, p))
        elif red > 0.4:
            opp.append(p)
    ball = max(balls)[1] if balls else None
    return ours, opp, ball, active


if __name__ == "__main__":
    for n in sys.argv[1:]:
        im = cv2.imread(n)
        o, p, b, act = read2(im)
        print(n, len(o), len(p), b and tuple(round(v) for v in b), act and tuple(round(v) for v in act))
        if f.radar_visible(im):
            out = f.draw(im, o, p, b, "%d/%d" % (len(o), len(p)))
            cv2.imwrite(os.path.join("debug", "r2_" + os.path.basename(n).split(".")[0] + ".png"), out)
