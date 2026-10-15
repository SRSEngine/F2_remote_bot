"""انتخاب کشور (Region) در پنجره‌ی پرچم‌ها.

    from region import Region
    Region(scr, "Sweden")            # پنجره‌ی کشورها باید باز باشد

مراحل: با RB/LB به تب حرف اول اسم می‌رود، اسم را روی صفحه پیدا می‌کند و با
Right/Left/Up/Down به آن خانه می‌رود و A می‌زند. اگر اسم دیده نشد، بار اول ۵ بار
Down و بعد یکی‌یکی Down می‌زند و هر بار دوباره می‌گردد.
همه‌ی عددها برای تصویر ریموت 1280x720 هستند.
"""
import re
import unicodedata
from difflib import SequenceMatcher

from xbox import RB, LB, Up, Down, Left, Right, A, wait

# ---------- تب‌ها ----------
TABS   = ["Top 9", "A", "B", "C", "D-G", "H-L", "M-O", "P-R", "S", "T-Z"]
TAB_X  = [352, 426, 476, 527, 591, 666, 742, 820, 881, 940]   # مرکز هر تب
TAB_Y  = (110, 142)                                            # بالا و پایین نوار تب‌ها

# ---------- جدول ----------
GRID   = (200, 158, 870, 458)              # x, y, w, h کل جدول
COLS   = [200, 490, 779]                    # لبه‌ی چپ هر ستون
COL_W  = 289
ROW_H  = 91.5                               # فاصله‌ی ردیف‌ها


def _norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())


def _tab_of(name):
    """تب حرف اول اسم."""
    c = _norm(name)[:1].upper()
    for i, t in enumerate(TABS[1:], 1):
        if len(t) == 1 and c == t:
            return i
        if len(t) == 3 and t[0] <= c <= t[2]:
            return i
    return None


def current_tab(scr):
    """شماره‌ی تب سبز (فعال)، یا None."""
    img = scr.frame[TAB_Y[0]:TAB_Y[1], TAB_X[0] - 40:TAB_X[-1] + 40].astype(int)
    b, g, r = img[..., 0], img[..., 1], img[..., 2]
    green = (g > 150) & (g - r > 30) & (g - b > 30)
    xs = green.nonzero()[1]
    if len(xs) < 5:
        return None
    x = xs.mean() + TAB_X[0] - 40
    return min(range(len(TAB_X)), key=lambda i: abs(TAB_X[i] - x))


def cursor(scr):
    """خانه‌ای که الان انتخاب شده (زمینه‌ی روشن‌تر): (ستون، y مرکز) یا None."""
    g = scr.gray
    x0, y0, w, h = GRID
    best = None
    for c, left in enumerate(COLS):
        prof = g[y0:y0 + h, left + 210:left + 270].mean(axis=1)
        run = 0
        for i, v in enumerate(list(prof) + [0]):
            if v > 58:
                run += 1
            else:
                if run > 40 and (best is None or run > best[2]):
                    best = (c, y0 + i - run / 2, run)
                run = 0
    return (best[0], best[1]) if best else None


def cells(scr):
    """اسم‌های روی صفحه: [(متن, ستون, y مرکز), ...]  (اسم دوخطی = یک خانه)"""
    words = []
    for _, ws in scr._words(*GRID):
        for word, L, T, W, H in ws:
            cx = L + W / 2
            c = max([i for i, left in enumerate(COLS) if cx >= left - 5] or [0])
            words.append((c, T + H / 2, L, word))
    words.sort()
    groups = []                                   # [ستون, [(y, L, کلمه), ...]]
    for c, y, L, word in words:
        if groups and groups[-1][0] == c and y - groups[-1][1][-1][0] < 35:
            groups[-1][1].append((y, L, word))
        else:
            groups.append([c, [(y, L, word)]])
    res = []
    for c, ws in groups:
        ws.sort(key=lambda t: (round(t[0] / 10), t[1]))
        res.append((" ".join(w for _, _, w in ws), c, sum(y for y, _, _ in ws) / len(ws)))
    return res


def locate(scr, name, fuzzy=0.85):
    """جای اسم در جدول: (ستون، y مرکز) یا None. اول دقیق، بعد با تحمل اشتباه OCR."""
    want = _norm(name)
    found = cells(scr)
    for text, c, y in found:
        if _norm(text) == want:
            return c, y
    best = max(found, key=lambda t: SequenceMatcher(None, want, _norm(t[0])).ratio(), default=None)
    if best and SequenceMatcher(None, want, _norm(best[0])).ratio() >= fuzzy:
        return best[1], best[2]
    return None


def go_tab(scr, name, delay=700):
    target = _tab_of(name)
    if target is None:
        print(f"Region: تب برای {name!r} پیدا نشد")
        return False
    for _ in range(12):
        cur = current_tab(scr)
        if cur == target:
            return True
        if cur is None or cur < target:
            RB()
        else:
            LB()
        wait(delay)
    return current_tab(scr) == target


def go_cell(scr, col, y, delay=300):
    """از خانه‌ی فعلی با Right/Left/Up/Down به خانه‌ی (col, y) می‌رود."""
    for _ in range(3):
        cur = cursor(scr)
        if cur is None:
            return False
        dc = col - cur[0]
        dr = round((y - cur[1]) / ROW_H)
        if dc == 0 and dr == 0:
            return True
        for _ in range(abs(dr)):
            (Down if dr > 0 else Up)()
            wait(delay)
        for _ in range(abs(dc)):
            (Right if dc > 0 else Left)()
            wait(delay)
        wait(300)
        # بعد از اسکرول جای اسم عوض می‌شود؛ دوباره پیدا کن
    return False


def Region(scr, name, select=True, max_down=40, delay=300):
    """کشور name را در پنجره‌ی پرچم‌ها انتخاب می‌کند. True اگر رسید."""
    if not name or name.upper() == "OFF":
        return True
    if not go_tab(scr, name):
        print(f"Region: به تب {name!r} نرسید")
        return False
    wait(500)

    first = True
    last_seen = None
    for _ in range(max_down + 1):
        where = locate(scr, name)
        if where:
            for _ in range(3):
                go_cell(scr, *where, delay=delay)
                where2 = locate(scr, name)
                cur = cursor(scr)
                if where2 and cur and cur[0] == where2[0] and abs(cur[1] - where2[1]) < ROW_H / 2:
                    print(f"Region: {name} پیدا شد")
                    if select:
                        A()
                        wait(500)
                    return True
                where = where2 or where
            return False

        seen = (sorted(t for t, _, _ in cells(scr)), cursor(scr))
        if seen == last_seen:                     # Down زدیم و نه لیست نه نشانگر جابه‌جا شد = ته لیست
            break
        last_seen = seen
        for _ in range(5 if first else 1):
            Down()
            wait(delay)
        first = False
        wait(300)

    print(f"Region: {name!r} پیدا نشد")
    return False
