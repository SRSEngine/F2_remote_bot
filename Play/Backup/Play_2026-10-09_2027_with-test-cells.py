#%%
import sys
sys.path.insert(0, r"C:\Users\Reach\Desktop\New Remote\Controller")
sys.path.insert(0, r"C:\Users\Reach\Desktop\New Remote\Founder")
from xbox import *
from founder import Remote, Screen
import bisect
import csv
import os
# ===== تنظیمات: اسم کنسول و روش ارسال =====
# روش‌ها: "pipe" (پیشنهادی، سریع‌ترین) | "udp" | "wmcopy" | "tcp" | "keys" | "xinput" | "cloud"
REMOTE = "XBOX"
setup(remote=REMOTE, method="pipe")

# ===== تصویر =====
# همه‌ی عددها نسبت به تصویر خود ریموت هستند (1280x720، گوشه‌ی بالا-چپ تصویر = 0,0)،
# نه صفحه‌ی کامپیوتر. جا و اندازه‌ی پنجره‌ی ریموت و پنل آن هیچ اثری ندارد.
# گرفتن عددها و ساختن تصویر نمونه:  python "C:\Users\Reach\Desktop\New Remote\Founder\pick.py" XBOX
cam = Remote(REMOTE)
scr = Screen(cam, templates=r"C:\Users\Reach\Desktop\New Remote\Screenshot\Shots")    # تصویرهای نمونه 1280x720 (RemoteShot)
# old = Screen(cam, templates=r"C:\Users\Reach\Desktop\New Remote\Founder\Templates\1080", ref=(1920, 1080))
#   ↑ فقط برای کد و عددهای قدیمی پروژه‌ی Transfer (صفحه‌ی 1920x1080 مرورگر)

# ===== دکمه =====
# A()  B()  X()  Y()  Up()  Down()  Left()  Right()
# LB() RB() LT() RT() LS() RS()  View()  Menu()  Xbox()
# LsUp() LsDown() LsLeft() LsRight()   RsUp() RsDown() RsLeft() RsRight()
# A(500)                 = A را ۵۰۰ میلی‌ثانیه نگه دار
# press("lb", "rb")      = چند دکمه با هم
# stick("L", 0.5, 1)     = استیک چپ (x و y بین ‎-1 تا 1)، stick("L", 0, 0) = وسط
# trigger("R", 1)        = ماشه‌ی راست کامل، trigger("R", 0) = رها
# wait(1000)             = یک ثانیه صبر

# ===== تصویر: پیدا کردن =====   (x, y, w, h = گوشه‌ی بالا-چپ، عرض، ارتفاع؛ بدون ناحیه = کل صفحه)
# scr.find("Cancel", x,y,w,h)        = پیدا کردن تصویر. در if درست/غلط؛  ok, X, Y = ... مرکزش
# scr.find(..., threshold=0.9)       = سخت‌گیرتر (پیش‌فرض 0.8)؛ color=True اگر فرق فقط در رنگ است
# scr.find_all("TRA", x,y,w,h)       = همه‌ی جاهای یک تصویر (لیست)
# scr.find_any(["Bid","BuyNow"], …)  = بهترین از چند تصویر؛ m.name = کدام
# scr.find_text("Transfer")          = جای یک کلمه روی صفحه، بدون تصویر نمونه

# ===== تصویر: خواندن =====
# scr.read(x,y,w,h)                  = متن ناحیه
# scr.read_number(x,y,w,h)           = عدد (15,750 → 15750) یا None
# scr.contains("Home", x,y,w,h)      = آیا کلمه در ناحیه هست
# scr.read_all()                     = همه‌ی خط‌های متن با جایشان (line.text, line.x, line.y)
# scr.pixel(x,y)                     = رنگ نقطه (B,G,R)؛  scr.is_blank() = صفحه سیاه/یکدست (لودینگ)

# ===== تصویر یا متن (هر دو) =====
# scr.see("Cancel", x,y,w,h)                   = اگر تصویر Cancel.png پیدا شد یا کلمه‌ی Cancel خوانده شد
# scr.see("BuyNow", x,y,w,h, text="Buy Now")   = وقتی متن با اسم تصویر فرق دارد (یا لیست چند متن)
#     m.by = "image" یا "text" (با کدام پیدا شد)؛  ok, X, Y = scr.see(...) مرکزش
# scr.wait_see("Cancel", x,y,w,h, timeout=5)   = صبر تا تصویر یا متن بیاید

# ===== تصویر: صبر و هوشمند =====
# scr.wait("Cancel", x,y,w,h, timeout=5)      = صبر تا تصویر بیاید
# scr.wait_gone("Cancel", x,y,w,h)            = صبر تا تصویر برود
# scr.wait_text("Market", x,y,w,h)            = صبر تا کلمه بیاید
# b = scr.snapshot(); A(); scr.wait_change(before=b)   = آیا دکمه اثر کرد (صفحه عوض شد)
# scr.wait_stable()                           = صبر تا انیمیشن تمام شود
# scr.act_until(Down, lambda s: s.contains("Transfer", x,y,w,h), tries=10)
#                                             = دکمه را تکرار کن تا شرط درست شود (حرکت در منو)
# scr.until(lambda s: ..., timeout=10)        = هر شرط دلخواه را تا درست شدن تکرار کن
# scr.detect([("Home", "text:Home"), ("Popup", ("Cancel", x,y,w,h)), ...])
#                                             = تشخیص صفحه روی یک فریم؛ اسم اولین قانون درست
# همه‌ی صبرها stop=lambda: … هم می‌گیرند تا با پرچم توقف ربات قطع شوند

# ===== تصویر: فریم و ابزار =====
# scr.grab()                         = فریم تازه (خودکار هم اگر فریم از ۰٫۱۵ ثانیه قدیمی‌تر باشد)
# with scr.frozen(): ...             = همه‌ی بررسی‌های داخل بلوک روی یک فریم (سریع و هم‌زمان)
# scr.save("frame.png")              = ذخیره‌ی کل فریم، برای پیدا کردن مختصات
# scr.save_template("Name", x,y,w,h) = ساختن تصویر نمونه از فریم فعلی → Founder\Templates\Name.png
# scr.Pfind / scr.Pfind2 / scr.ReadText = همان اسم‌های قدیمی، با مختصات ریموت


import re
import unicodedata
import cv2
import numpy as np
from difflib import SequenceMatcher

# ===== تنظیمات هر پنجره =====
REGION_PICK = dict(
    tabs=["Top 9", "A", "B", "C", "D-G", "H-L", "M-O", "P-R", "S", "T-Z"],
    tab_x=[352, 426, 476, 527, 591, 666, 742, 820, 881, 940],   # مرکز هر تب
    grid=(200, 158, 870, 458),                                   # x, y, w, h کل جدول
    cols=[200, 490, 779],                                        # لبه‌ی چپ هر ستون
)
LEAGUE_PICK = dict(
    tabs=["Default", "Alphabetical: League", "Alphabetical: Country/Region"],
    tab_x=[321, 510, 819],
    grid=(191, 158, 870, 458),
    cols=[191, 481, 769],
)
RARITY_PICK = dict(                # چندانتخابی: خانه‌ی انتخاب‌شده تیک سبز دارد
    tabs=["ALL", "A-C", "D-F", "G-H", "I-J", "K-N", "O-R", "S-T", "U-Z"],
    tab_x=[348, 424, 499, 573, 643, 711, 787, 861, 933],
    tab_y=(115, 150),
    grid=(200, 165, 870, 458),
    cols=[200, 490, 779],
    check=True,
)
CLUB_PICK = dict(                  # تب ندارد؛ بالایش فقط اسم لیگ است
    tabs=None,
    grid=(181, 158, 870, 458),
    cols=[181, 470, 759],
)
TAB_Y = (110, 142)     # بالا و پایین نوار تب‌ها (اگر پنجره tab_y نداشت)
ROW_H = 91.5           # فاصله‌ی ردیف‌ها
TEXT_X = 70            # متن هر خانه از این فاصله بعد از لبه‌ی چپ شروع می‌شود (قبلش پرچم/لوگو)




def _norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _keys(text):
    """شکل‌های قابل مقایسه‌ی متن یک خانه: کامل، بدون پرانتز، فقط داخل پرانتز.
    "Premier League (ENG 1)" → premierleagueeng1, premierleague, eng1"""
    keys = [_norm(text), _norm(re.sub(r"\(.*?\)", "", text))]
    keys += [_norm(m) for m in re.findall(r"\((.*?)\)", text)]
    return [k for k in keys if k]


def current_tab(P):
    """شماره‌ی تب سبز (فعال)، یا None."""
    x0 = P["tab_x"][0] - 60
    y0, y1 = P.get("tab_y", TAB_Y)
    img = scr.frame[y0:y1, x0:P["tab_x"][-1] + 60].astype(int)
    b, g, r = img[..., 0], img[..., 1], img[..., 2]
    xs = ((g > 150) & (g - r > 30) & (g - b > 30)).nonzero()[1]
    if len(xs) < 5:
        return None
    x = xs.mean() + x0
    return min(range(len(P["tab_x"])), key=lambda i: abs(P["tab_x"][i] - x))


def cursor(P):
    """خانه‌ی انتخاب‌شده (زمینه‌ی روشن‌تر): (ستون، y مرکز) یا None."""
    g = scr.gray
    x0, y0, w, h = P["grid"]
    best = None
    for c, left in enumerate(P["cols"]):
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


def cells(P, scale=1.5):
    """اسم‌های روی صفحه: [(متن، ستون، y مرکز), ...]  اسم دوخطی = یک خانه."""
    x0, y0, w, h = P["grid"]
    img = scr.gray[y0:y0 + h, x0:x0 + w].copy()
    bg = int(np.median(img))
    for left in P["cols"]:                          # پرچم/لوگو را با رنگ زمینه بپوشان
        img[:, max(0, left - x0 - 5):left - x0 + TEXT_X] = bg
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    pad = 10
    img = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=bg)

    per_col = [[] for _ in P["cols"]]
    for _, ws in scr.ocr.lines(img):
        for word, L, T, W, H in ws:
            L = x0 + (L - pad) / scale
            y = y0 + (T + H / 2 - pad) / scale
            c = max([i for i, left in enumerate(P["cols"]) if L >= left] or [0])
            per_col[c].append((y, L, word))

    res = []
    for c, words in enumerate(per_col):
        cell = []                                    # کلمه‌های یک خانه
        for y, L, word in sorted(words) + [(1e9, 0, None)]:
            if cell and y - cell[-1][0] >= 35:       # فاصله‌ی زیاد = خانه‌ی بعدی
                lines = []                           # خط‌های داخل خانه، هر خط به ترتیب x
                for wy, wl, wt in cell:
                    if lines and abs(wy - lines[-1][0]) < 10:
                        lines[-1][1].append((wl, wt))
                    else:
                        lines.append([wy, [(wl, wt)]])
                text = " ".join(t for _, ws in lines for _, t in sorted(ws))
                res.append((text, c, sum(t[0] for t in cell) / len(cell)))
                cell = []
            if word is not None:
                cell.append((y, L, word))
    return res


def _parts(text):
    """تکه‌های پشت‌سرهم اسم: "AFC Bournemouth" → afc, bournemouth, afcbournemouth"""
    w = [_norm(x) for x in re.sub(r"\(.*?\)", "", text).split()]
    w = [x for x in w if x]
    return [''.join(w[i:j]) for i in range(len(w)) for j in range(i + 1, len(w) + 1)]


def locate(P, name, fuzzy=0.85):
    """جای اسم در جدول: (ستون، y مرکز) یا None.
    ترتیب: اسم دقیق → اسم با تحمل اشتباه OCR → بخشی از اسم ("Bournemouth" برای "AFC Bournemouth")."""
    want = _norm(name)
    found = cells(P)
    for text, c, y in found:
        if want in _keys(text):
            return c, y

    def ratio(keys):
        return max([SequenceMatcher(None, want, k).ratio() for k in keys] or [0])

    for keys in (_keys, _parts):
        best = max(found, key=lambda t: ratio(keys(t[0])), default=None)
        if best and ratio(keys(best[0])) >= fuzzy:
            return best[1], best[2]
    return None


def checked(P, col, y):
    """آیا خانه‌ی (col, y) تیک سبز دارد؟ (گوشه‌ی بالا-راست خانه)"""
    left = P["cols"][col]
    y = int(y)
    img = scr.frame[y - 45:y - 10, left + 245:left + 285].astype(int)
    b, g, r = img[..., 0], img[..., 1], img[..., 2]
    return int(((g > 150) & (g - r > 40) & (g - b > 40)).sum()) > 20


def go_tab(P, target, delay=700):
    """با RB (یا LB اگر رد شد) به تب شماره‌ی target می‌رود."""
    for _ in range(12):
        cur = current_tab(P)
        if cur == target:
            return True
        if cur is None or cur < target:
            RB()
        else:
            LB()
        wait(delay)
    return current_tab(P) == target


def go_cell(P, col, y, delay=300):
    """از خانه‌ی فعلی با Right/Left/Up/Down به خانه‌ی (col, y) می‌رود."""
    for _ in range(3):
        cur = cursor(P)
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
    return False


def pick(P, name, tab, select=True, max_down=40, delay=300):
    """در پنجره‌ی P به تب tab می‌رود و name را پیدا و انتخاب می‌کند. True اگر رسید."""
    if is_off(name):
        return True
    if tab is not None and not go_tab(P, tab):
        print(f"به تب {P['tabs'][tab]!r} نرسید")
        return False
    wait(500)

    first = True
    last_seen = None
    for _ in range(max_down + 1):
        where = locate(P, name)
        if where:
            for _ in range(3):
                go_cell(P, *where, delay=delay)
                where2 = locate(P, name)          # بعد از اسکرول جای اسم عوض می‌شود
                cur = cursor(P)
                if where2 and cur and cur[0] == where2[0] and abs(cur[1] - where2[1]) < ROW_H / 2:
                    print(f"{name} پیدا شد")
                    if select and not (P.get("check") and checked(P, *where2)):
                        A()                       # اگر از قبل تیک داشت، A تیکش را برمی‌داشت
                        wait(500)
                    return True
                where = where2 or where
            return False

        seen = (sorted(t for t, _, _ in cells(P)), cursor(P))
        if seen == last_seen:                     # نه لیست جابه‌جا شد نه نشانگر = ته لیست
            break
        last_seen = seen
        for _ in range(5 if first else 1):        # بار اول ۵ تا، بعد یکی‌یکی
            Down()
            wait(delay)
        first = False
        wait(300)

    print(f"{name!r} پیدا نشد")
    return False


def letter_tab(P, name):
    """تب حرف اول اسم: "S" یا بازه‌ای مثل "D-G". اگر نبود، تب اول (Top 9 / ALL)."""
    c = _norm(name)[:1].upper()
    for i, t in enumerate(P["tabs"]):
        if (len(t) == 1 and c == t) or (len(t) == 3 and t[1] == "-" and t[0] <= c <= t[2]):
            return i
    return 0


# ===== ناحیه‌های پرتکرار (اگر مختصاتی عوض شد، فقط همین‌جا) =====
MULTI   = ("Multi", 185,468,76,39)
SWAP    = ("Swap (3)", 26,626,165,88)
REFRESH = ("REFRESH", 165,467,115,40)
FUT2    = ("Fut (2)", 134,136,60,40)
BUYNOW  = ("BuyNow (2)", 29,683,93,25)
SEARCH  = ("Search", 30,682,81,25)
STATS   = (139, 243, 47, 176)          # ستون عددهای بازیکن (read_number)


def is_off(v):
    """مقدار خالی یا OFF (با هر حروف بزرگ/کوچک) = این فیلتر را تنظیم نکن."""
    return not v or str(v).strip().upper() == "OFF"


def on_results():
    """صفحه‌ی نتیجه‌ی جستجو (دکمه‌ی BuyNow یا Search پایین صفحه)."""
    return scr.see(*BUYNOW) or scr.see(*SEARCH)


def Rarity(name, tries=10, club=False):
    """Rarity را تنظیم می‌کند: فیلتر را باز می‌کند، با X پاکش می‌کند، اسم را پیدا و تیک می‌زند.
    "OFF" = فقط پاک کردن فیلتر.  club=True: صفحه‌ی جستجوی Club."""
    ok = False
    for _ in range(tries):
        print("Looking for 'Rarity'")
        GoFilter(1, 0, club)
        wait(1000)
        X()                                      # پاک کردن انتخاب قبلی
        wait(1000)
        if is_off(name):
            return True
        A()                                      # باز کردن لیست
        wait(1000)
        for i in range(10):
            if scr.see("ALL", 317,116,655,35):
                # Bronze/Silver/Gold همان اول در تب ALL هستند؛ اگر دیده شد تب را عوض نکن
                tab = None if locate(RARITY_PICK, name) else letter_tab(RARITY_PICK, name)
                ok = pick(RARITY_PICK, name, tab)
                break
            else:
                A()
                wait(1000)
        B()                                      # بستن لیست (چندانتخابی است و خودش بسته نمی‌شود)
        wait(1000)
        if ok:
            return True
    return False



def set_list_filter(xy, name, P, marker, tab, club=False, select=True, settle=0):
    """فیلترهای لیستی (Region / League / Club): رفتن به فیلتر، پاک کردن با X،
    باز کردن لیست با A تا marker دیده شود، و انتخاب name با pick.
    tab: شماره‌ی تب، None = تب فعلی، "letter" = اگر اسم همان اول دیده شد همان‌جا، وگرنه تب حرف اول."""
    GoFilter(*xy, club)
    wait(1000)
    X()
    wait(1000)
    if is_off(name):
        return True
    for _ in range(10):
        A()
        wait(2000)
        if scr.see(*marker):
            print(f"Found {marker[0]!r}")
            break
    wait(settle)
    if tab == "letter":
        tab = None if locate(P, name) else letter_tab(P, name)
    return pick(P, name, tab, select)


def Region(name, select=True, club=False):
    """کشور را انتخاب می‌کند. کشورهای Top 9 همان اول دیده می‌شوند و تب عوض نمی‌شود."""
    return set_list_filter((1, 1), name, REGION_PICK, ("Top9", 317,107,651,36), "letter", club, select)


def League(name, select=True, club=False):
    """لیگ را انتخاب می‌کند: "Premier League (ENG 1)"، "Premier League" یا "ENG 1"."""
    return set_list_filter((2, 1), name, LEAGUE_PICK, ("Default", 271,104,358,43), 0, club, select)


def Club(name, select=True, club=False):
    """باشگاه را انتخاب می‌کند. اگر لیگ (متغیر league حلقه) OFF باشد کاری نمی‌کند."""
    if is_off(league):
        return True
    return set_list_filter((3, 1), name, CLUB_PICK, ("Any (4)", 203,167,101,68), None, club, select, settle=1000)




def find_platform(PLATFORM):
    for i in range(10):
        if scr.see("My games", 479, 104, 117, 18):
            print("Found 'My games' -> entering")
            A()
            break
        Up()
        wait(1500)
    else:
        print("'My games' پیدا نشد")

        
    # بالای فایل؛ اگر عوض شد فقط همین‌جا عوضش کنید


    for i in range(10):
        if not scr.see("Games", 338, 47, 109, 42):
            wait(1000)
            if scr.see("See in Micro", 75, 144, 177, 31):
                B()
                wait(1000)
            continue
        print("Found 'Games'")

        Right()
        wait(1000)
        if not scr.see("Manage game", 924, 648, 159, 38):
            wait(1000)
            continue

        View()
        wait(2000)
        if not scr.see("See in Micro", 75, 144, 177, 31):
            wait(1000)
            continue

        print("Text in box:", repr(scr.read(410, 46, 177, 39)))
        if not scr.see(f"27 XBOX {PLATFORM}", 410, 46, 177, 39):
            B()             # بازی اشتباه است: منو را ببند و دوباره امتحان کن
            wait(1000)
            continue

        print(f"Found '{PLATFORM}'")
        B()
        wait(1000)
        if scr.wait_see("Manage game", 924, 648, 159, 38, timeout=10):
            A()
            wait(1000)
        break


    for i in range(10):
        print(repr(scr.read(410, 46, 177, 39)))
        if scr.see("PLAY (2)", 147,604,48,19):
            A()
            wait(3000)
            if scr.see("CLOSE", 157,531,62,29):
                A()
            break
        else:
            wait(1000)

def FindUltimate():
    for i in range(10):
        print("Looking for 'Ultimate'")
        if scr.see("Ok", 620,410,64,29):
            A()
            continue

        if scr.see("Ok (2)", 607,464,67,26):
            A()
            continue

        if not scr.see("Setting", 37,116,20,83):
            wait(10000)
            continue
        else:
            print("Found 'Setting'")

        if scr.see("Continue (2)", 584,621,110,29):
            A()
            wait(1000)
            continue

        if scr.see("Ultimate", 379,533,500,32):
            print("Found 'Ultimate'")
            A()
            break
        else:
            Down()
            wait(1000)


def MainUltimate():
    for i in range(10):
        print("Looking for 'Main Ultimate'")
        wait(10000)
        if scr.see("Ok (3)", 610,427,60,28):
            A()
            FindUltimate()
            continue

        if scr.see("setting", 37,116,20,83):
            FindUltimate()
            continue

        if scr.see("Continue", 586,619,107,26):
            A()
            wait(1000)

        if scr.see("Advance", 33,680,88,31):
            A()
            wait(1000)

        if scr.see("Ok (4)", 609,408,64,32):
            A()
            wait(1000)

        if scr.see("FUT", 29,28,42,55):
            break



def FindSBC():
    print("Looking for 'SBC'")
    for i in range (20):
        if not scr.see("Open SBC", 391,598,124,30):
            RB()
            wait(1000)
        else:
            print("Found 'SBC'")
            A()
            wait(1000)
            break




def open_marquee(tries=10):

    COLS = [100, 372, 650, 921]        # لبه‌ی چپ هر ستون
    ROW  = (100, 187, 1045, 73)        # کل ردیف: از x=100 تا 1145، از y=187 تا 260
    for _ in range(tries):
        print("Looking for 'Marquee'")
        m = scr.wait_see("Marquee", *ROW, timeout=1)   # تا ۱ ثانیه صبر، هر ۰٫۱ ثانیه نگاه
        if m:
            col = bisect.bisect_right(COLS, m.x) - 1   # m.x = مرکز چیزی که پیدا شد
            for _ in range(col):
                Right(); wait(500)
            A()
            return True
        for _ in range(4):                             # ردیف بعدی
            Right(); wait(500)
        wait(1000)
    return False


def open_challenge(tries=10):
    print("Looking for 'Challenge'")
    for i in range(10):
        wait(2000)
        if scr.see("Sub", 28,679,247,28):
            print("Found 'Sub'")
            A()
        if scr.see("Create Your", 558,354,164,36):
            print("Found 'Continue'")
            A()
        if scr.see("Sub (2)", 29,680,447,33):
            print("Found 'Sub (2)' , Start Challenge")
            wait(1000)
            break
        if scr.see("Advance (2)", 32,682,167,24):
            print("Found 'Advance (2)' , Start Challenge")
            wait(100)
            A()



MARKET_PANELS = {                     # x, y, w, h هر کادر در Transfer Market
    "Name":       (74, 186, 277, 205),
    "Pricing":    (74, 401, 277, 205),
    "Rarity":     (360, 186, 277, 205),
    "Country":    (360, 401, 277, 205),
    "Position":   (644, 186, 277, 205),
    "League":     (644, 401, 277, 205),
    "PlayStyles": (930, 186, 277, 99),
    "Chemistry":  (930, 293, 277, 99),
    "Club":       (930, 401, 277, 205),
}

# شماره‌ای که تابع‌ها می‌دهند → اسم کادر در Transfer Market
MARKET_BY_XY = {(0, 0): "Name", (0, 1): "Pricing", (1, 0): "Rarity", (1, 1): "Country",
                (2, 0): "Position", (2, 1): "League", (3, 0): "PlayStyles", (3, 1): "Club"}


def FindFilter(tx, ty):
    """رفتن به فیلتر (tx, ty) در Transfer Market، با تشخیص کادر روشن (مثل صفحه‌ی Club)."""
    target = MARKET_BY_XY[(tx, ty)]
    if not GoPanel(target, MARKET_PANELS):
        print(f"FindFilter: به {target} نرسید")


CLUB_PANELS = {                       # x, y, w, h هر کادر
    "Name":       (75, 185, 277, 207),
    "Rarity":     (360, 185, 277, 207),
    "Position":   (645, 185, 277, 99),
    "Role":       (645, 292, 277, 99),
    "Overall":    (930, 185, 277, 207),
    "Advanced":   (75, 400, 277, 207),
    "Country":    (360, 400, 277, 207),
    "League":     (645, 400, 277, 99),
    "Club":       (645, 508, 277, 99),
    "PlayStyle":  (930, 400, 277, 99),
    "Chemistry":  (930, 508, 277, 99),
}

def selected_panel(panels):
    """اسم کادری که الان انتخاب شده (روشن‌ترین)، یا None."""
    g = scr.gray
    best, val = None, 0
    for name, (x, y, w, h) in panels.items():
        v = float(np.median(g[y + 5:y + h - 5, x + 5:x + w - 5]))
        if v > val:
            best, val = name, v
    return best if val > 65 else None

def GoPanel(target, panels, tries=12, delay=700):
    """با Up/Down/Left/Right به کادر target می‌رود."""
    tx, ty, tw, th = panels[target]
    for _ in range(tries):
        cur = selected_panel(panels)
        if cur == target:
            return True
        if cur is None:
            wait(delay)
            continue
        x, y, w, h = panels[cur]
        dx = (tx + tw / 2) - (x + w / 2)
        dy = (ty + th / 2) - (y + h / 2)
        if abs(dx) > w / 2:
            (Right if dx > 0 else Left)()
        else:
            (Down if dy > 0 else Up)()
        wait(delay)
    return selected_panel(panels) == target


# ===== چالش‌های Marquee (۴ کادر: ۱ ۲ بالا، ۳ ۴ پایین) =====
CHALLENGE_PANELS = {                  # x, y, w, h هر کادر
    1: (73, 185, 411, 213),
    2: (484, 185, 411, 213),
    3: (73, 398, 411, 213),
    4: (484, 398, 411, 213),
}


def current_challenge():
    """شماره‌ی چالشی که الان انتخاب شده (۱ تا ۴)، یا None."""
    return selected_panel(CHALLENGE_PANELS)


def challenge_done(n):
    """آیا چالش n برچسب سبز «Completed» دارد؟ (گوشه‌ی بالا-راست کادر)"""
    x, y, w, h = CHALLENGE_PANELS[n]
    b = scr.frame[y + 2:y + 30, x + w - 120:x + w - 4].astype(int)
    green = (b[..., 1] > 150) & (b[..., 1] - b[..., 2] > 60) & (b[..., 1] - b[..., 0] > 30)
    return green.mean() > 0.5


def OpenChallenge(n):
    """به چالش n (۱ تا ۴) می‌رود و با A وارد می‌شود.
    خروجی: True = وارد شد،  "completed" = قبلاً کامل شده (وارد نمی‌شود)،  False = به آن نرسید."""
    if challenge_done(n):
        print(f"Challenge {n}: قبلاً کامل شده (Completed)")
        return "completed"
    if not GoPanel(n, CHALLENGE_PANELS):
        print(f"Challenge {n}: به آن نرسید (الان روی {current_challenge()})")
        return False
    print(f"Challenge {n}: وارد شد")
    A()
    return True




# شماره‌ای که تابع‌ها می‌دهند → اسم کادر در صفحه‌ی Club
CLUB_BY_XY = {(0, 0): "Name", (1, 0): "Rarity", (2, 0): "Position",
              (1, 1): "Country", (2, 1): "League", (3, 1): "Club"}


def GoFilter(tx, ty, club=False):
    """رفتن به فیلتر (tx, ty).  club=False: Transfer Market با FindFilter،  club=True: صفحه‌ی Club با GoPanel."""
    if club:
        if not GoPanel(CLUB_BY_XY[(tx, ty)], CLUB_PANELS):
            print(f"GoFilter: به {CLUB_BY_XY[(tx, ty)]} نرسید")
    else:
        FindFilter(tx, ty)


def Position(Position, club=False):
    print("Looking for 'Position'")
    if is_off(Position):
        GoFilter(2,0,club)
        for i in range(3):
            wait(300)
            if is_off(Position):
                GoFilter(2,0,club)
                wait(300)
                X()
            if scr.see("Position (3)", 700,362,70,22,threshold=0.85):
                break


def Pricing(price, club=False):
    if club:                       # صفحه‌ی Club قیمت ندارد
        print("Pricing: club=True، قیمت نادیده گرفته شد")
        return
    prc=0
    FindFilter(0,1)
    wait(1000)
    X()
    wait(1000)
    A()
    wait(1000)
    for i in range(4):
        print("Looking for 'Pricing'")
        if scr.see("BuyNow", 211,573,29,20):
            break
        Up()
        wait(1000)
    for i in range(50):
        if (prc := scr.read_number(239, 576, 74, 16, default=0))==price:
            break
        print(prc)
        if prc>price:
            Left()
            wait(300)
        elif prc<price:
            Right()
            wait(300)
    for i in range(4):
        if scr.see("Min", 582,683,120,23):
            wait(1000)
            B()
            wait(1000)
            break





def BUY():
    print("Looking for 'BuyNow'")
    for i in range(10):
        if on_results():
            break
        else:
            Y()
            wait(3000)

    for i in range (20):
        wait(1000)
        if on_results():
            Right()
            Down()
            wait(300)
            print("Found 'BuyNow (2)'")
            A()
        wait(1000)
        if scr.see("No", 610,434,55,32):
            print("Found 'No'")
            Up()
            wait(1000)
        if scr.see("Yes", 607,383,64,29):
            print("Found 'Yes'")
            A()
            wait(3000)
        if scr.see("Expired", 278,517,60,18):
            print("expired")
            A()
            continue
        if scr.see("The bid", 316,298,115,39):
            print("Error")
            A()
            wait(1000)
            continue
        if scr.see("Sorry", 430,303,90,33):
            A()
            continue
        if scr.see("Sub (5)", 24,680,835,30):
            print("Bought")
            break
        if scr.see("Confirm (2)", 29,681,87,27):
            B()
            print("Bought")
            break
        if on_results():
            continue
        else:
            Y()
            wait(3000)

def FindClub():
    for i in range (10):
        if scr.see("Player Search", 72,110,152,28):
            break
        else:
            Y()
        wait(2000)


def enter_slot():
    """از اسکواد وارد خانه‌ی بازیکن می‌شود (Swap / Confirm / Multi) تا عددهای بازیکن دیگر دیده نشوند."""
    for _ in range(10):
        wait(1000)
        if scr.find(*SWAP):
            A()
            wait(1000)
        if scr.see("Confirm (3)", 33,631,176,76):
            RB()
            wait(3000)
        if scr.see(*MULTI):
            XMenu()
            wait(1000)
        if scr.read_number(*STATS) is None:
            B()
            wait(1000)
            break
        if scr.see(*REFRESH) and not scr.see(*FUT2):
            LB()
            wait(1000)


def search_club():
    """Search در صفحه‌ی Club تا نتیجه (Multi) بیاید."""
    for _ in range(10):
        if scr.see(*MULTI):
            break
        Y()
        wait(2000)


def clear_slot():
    """بعد از جستجوی بی‌نتیجه در Club: بستن Multi و برگشت تا عددهای بازیکن دیده نشوند."""
    for _ in range(10):
        wait(1000)
        if scr.see(*MULTI):
            XMenu()
            wait(1000)
            continue
        if scr.read_number(*STATS) is None:
            B()
            wait(1000)
            break
        if scr.see(*REFRESH) and not scr.see(*FUT2):
            LB()
            wait(1000)


def back_to_market():
    """برگشت به صفحه‌ی فیلترهای Transfer Market (کادر Name دیده شود)."""
    for _ in range(10):
        wait(1000)
        if scr.see(*MULTI):
            B()
        if scr.find(*SWAP):
            A()
            wait(1000)
        if scr.see("Confirm", 27,679,93,31):
            LB()
            wait(1000)
        if scr.see("Name (3)", 166,197,90,191):
            break


def use_club_card():
    """کارت در Club پیدا شد: A تا صفحه‌ی Swap بیاید."""
    for _ in range(10):
        if scr.find(*SWAP):
            break
        A()
        wait(2000)


def SetFilters(row, last, club=False):
    """تنظیم فیلترها طبق ردیف CSV. فقط فیلترهایی که با دفعه‌ی قبل فرق دارند تنظیم می‌شوند.
    last : دیکشنری آخرین مقدارهای تنظیم‌شده (بیرون از حلقه یک بار last = {} بسازید)
    club : True = صفحه‌ی جستجوی Club (قیمت ندارد)"""
    def changed(key):
        return row[key] != last.get(key)

    league_changed = changed("League")

    Pricing(int(row["Price"]), club=club)        # قیمت همیشه از نو (در Club کاری نمی‌کند)
    if changed("Region"):
        Region(row["Region"], club=club)
        last["Region"] = row["Region"]
    if changed("Rarity"):
        Rarity(row["Rarity"], club=club)
        last["Rarity"] = row["Rarity"]
    if changed("Pos"):
        Position(row["Pos"], club=club)
        last["Pos"] = row["Pos"]
    if league_changed:
        League(row["League"], club=club)
        last["League"] = row["League"]
    if league_changed or changed("Club"):        # با عوض شدن لیگ، باشگاه هم دوباره
        Club(row["Club"], club=club)
        last["Club"] = row["Club"]

def Submit():
    for i in range(10):
        if scr.see("Submit", 1071,253,85,29):
            XMenu()
            wait(1000)
        if scr.see("Cancel", 526,557,84,23):
            Right()
            wait(1000)
        if scr.see("Submit (2)", 622,557,133,27):
            A()
            wait(1000)
        if scr.see("No (2)", 612,491,55,27):
            Up()
            wait(1000)
        if scr.see("Yes (2)", 609,439,59,29):
            A()
            wait(1000)
        if scr.see("Congratulations", 304,181,246,36) or scr.see("Claim", 598,492,78,24):
            A()
            wait(1000)
        if scr.see("Store", 158,47,57,20) or scr.see("Open", 33,681,65,26):
            B()
            wait(1000)
        if scr.see("View Rewards", 1016,575,177,28) or scr.see("V", 1154,122,23,30):
            break

def GotoHome():
    for i in range(10):
        if scr.find("LIB", 525,65,25,23):
            break
        if scr.see("Home", 77,135,113,45) or scr.find("X", 77,42,34,34):
            A()
            wait(2000)
        else:
            Xbox()
            wait(2000)


# %% Main
#GotoHome()
#find_platform(platform())          # تیک XS پنل: روشن = Ser، خاموش = One
#FindUltimate()
#MainUltimate()
#FindSBC()
#open_marquee(tries=10)

CSV_DIR = r"C:\Users\Reach\Desktop\New Remote"

last_club = {}      # آخرین فیلترهای صفحه‌ی Club (اول هر چالش خالی می‌شود)
last_market = {}    # آخرین فیلترهای Transfer Market


def load_rows(n):
    """ردیف‌های Marquee{n}.csv (۱۱ بازیکن چالش n)."""
    path = os.path.join(CSV_DIR, f"Marquee{n}.csv")
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))          # هر ردیف = دیکشنری با ستون‌های عنوان
    print(f"Marquee{n}.csv: {len(rows)} ردیف")
    return rows


for challenge in range(1, 5):                   # چالش ۱ تا ۴
    print(f"===== چالش {challenge} =====")
    res = OpenChallenge(challenge)
    if res == "completed":
        continue                                # قبلاً کامل شده
    if not res:
        print(f"چالش {challenge}: باز نشد، رد شد")
        continue
    open_challenge()                            # شروع چالش (Start Challenge)
    last_club.clear()                           # بازی در هر چالش فیلترها را ریست می‌کند
    last_market.clear()

    rows = load_rows(challenge)
    for i, row in enumerate(rows, 1):           # یک دور برای هر بازیکن
        league = row["League"]                  # Club() این را می‌خواند
        print(f"[{challenge}:{i}/{len(rows)}] " + " | ".join(row[k] for k in ("Rarity", "Region", "Pos", "Club", "League", "Price")))

        enter_slot()                            # از اسکواد به خانه‌ی بازیکن
        FindClub()
        SetFilters(row, last_club, club=True)   # اول در Club بگرد
        search_club()

        if scr.see("Custom Filters", 693,355,210,33):   # در Club نبود → از Market بخر
            clear_slot()
            back_to_market()
            SetFilters(row, last_market)
            BUY()
        else:
            print('Found in Club')
            use_club_card()

    Submit()                                    # ثبت و برگشت به صفحه‌ی چالش‌ها



#%%
FindSBC()
# %%
scr.see("Open SBC", 391,598,124,30)
# %%
open_marquee(tries=10)
# %%
