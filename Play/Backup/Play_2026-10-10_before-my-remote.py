#%%
import sys
sys.path.insert(0, r"C:\Users\Reach\Desktop\New Remote\Controller")
sys.path.insert(0, r"C:\Users\Reach\Desktop\New Remote\Founder")
from xbox import *
from founder import Remote, Screen
import bisect
import csv
import os
import time
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
# scr.grab()                         = فریم تازه (خودکار هم بعد از هر دکمه، یا اگر فریم از ۰٫۳ ثانیه قدیمی‌تر باشد)
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
        wait(100)
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
        wait(100)
        cur = cursor(P)
        if cur is None:
            return False
        dc = col - cur[0]
        dr = round((y - cur[1]) / ROW_H)
        if dc == 0 and dr == 0:
            return True
        for _ in range(abs(dr)):
            wait(100)
            (Down if dr > 0 else Up)()
            wait(delay)
        for _ in range(abs(dc)):
            wait(100)
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
        wait(100)
        where = locate(P, name)
        if where:
            for _ in range(3):
                wait(100)
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
            wait(100)
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
NO_RESULT = ("Custom Filters", 693,355,210,33)   # جستجوی Club نتیجه نداشت


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
        wait(100)
        print("Looking for 'Rarity'")
        if not GoFilter(1, 0, club):
            continue
        wait(1000)
        X()                                      # پاک کردن انتخاب قبلی
        wait(1000)
        if is_off(name):
            return True
        A()                                      # باز کردن لیست
        wait(1000)
        for i in range(10):
            wait(100)
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
    if not GoFilter(*xy, club):
        return False
    wait(1000)
    X()
    wait(1000)
    if is_off(name):
        return True
    for _ in range(10):
        wait(100)
        A()
        wait(2000)
        if scr.see(*marker):
            print(f"Found {marker[0]!r}")
            break
    else:
        print(f"لیست {marker[0]!r} باز نشد")
        return False
    wait(settle)
    if tab == "letter":
        tab = None if locate(P, name) else letter_tab(P, name)
    if pick(P, name, tab, select):
        return True
    if scr.see(*marker):                         # لیست باز مانده: ببند تا تلاش بعدی از صفحه‌ی فیلترها شروع شود
        B()
        wait(1000)
    return False


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
        wait(100)
        if scr.see("My games", 479, 104, 117, 18):
            print("Found 'My games' -> entering")
            A()
            break
        Up()
        wait(1500)
    else:
        print("'My games' پیدا نشد")   # شاید از قبل در Games باشیم؛ ادامه

        
    # بالای فایل؛ اگر عوض شد فقط همین‌جا عوضش کنید


    for i in range(10):
        wait(100)
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
    else:
        print(f"بازی {PLATFORM!r} پیدا نشد")
        return False

    for i in range(10):
        wait(100)
        if scr.see("PLAY (2)", 147,604,48,19):
            A()
            wait(3000)
            if scr.see("CLOSE", 157,531,62,29):
                A()
            return True
        wait(1000)
    print("'PLAY' پیدا نشد")
    return False

def FindUltimate():
    for i in range(10):
        wait(100)
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
            return True
        else:
            Down()
            wait(1000)
    return False


def MainUltimate():
    for i in range(10):
        wait(100)
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
            return True
    return False



def FindSBC():
    print("Looking for 'SBC'")
    for i in range (20):
        wait(100)
        if not scr.see("Open SBC", 391,598,124,30):
            RB()
            wait(1000)
        else:
            print("Found 'SBC'")
            A()
            wait(1000)
            return True
    return False




SET_COLS = [100, 372, 650, 921]        # صفحه‌ی SBC: لبه‌ی چپ هر ستون
SET_ROW = (100, 187, 1045, 73)         # ردیف کادرهای ست‌ها: از x=100 تا 1145، از y=187 تا 260


def open_set(name, tries=10):
    """ست SBC با اسم name را در صفحه‌ی SBC پیدا می‌کند و با A بازش می‌کند (مثل open_marquee قبلی).
    اگر تصویر نمونه‌ای به همین اسم باشد (مثلاً Marquee.png) با تصویر، وگرنه با خواندن متن کادرها."""
    for _ in range(tries):
        wait(100)
        print(f"Looking for set '{name}'")
        m = scr.wait_see(name, *SET_ROW, timeout=1)   # تا ۱ ثانیه صبر، هر ۰٫۱ ثانیه نگاه
        if m:
            col = bisect.bisect_right(SET_COLS, m.x) - 1   # m.x = مرکز چیزی که پیدا شد
            for _ in range(col):
                wait(100)
                Right(); wait(500)
            A()
            return True
        for _ in range(4):                             # ردیف بعدی
            wait(100)
            Right(); wait(500)
        wait(1000)
    return False


def open_marquee(tries=10):
    """همان قبلی: ست Marquee."""
    return open_set("Marquee", tries)


def back_to_sbc(tries=8):
    """از صفحه‌ی چالش‌های یک ست به صفحه‌ی SBC برمی‌گردد (B تا دکمه‌ی Open SBC، بعد A)؛
    این‌طور نشانگر صفحه‌ی SBC از اول ردیف شروع می‌کند، مثل بار اول."""
    for _ in range(tries):
        wait(100)
        if scr.see("Open SBC", 391,598,124,30):
            A()
            wait(1500)
            return True
        B()
        wait(1500)
    return FindSBC()


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
            return True
        if scr.see("Advance (2)", 32,682,167,24):
            print("Found 'Advance (2)' , Start Challenge")
            wait(100)
            A()
    return False



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
    if GoPanel(target, MARKET_PANELS):
        return True
    print(f"FindFilter: به {target} نرسید")
    return False


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
        wait(100)
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


CHALLENGES_PAGE = ("View Rewards", 1016,575,177,28)   # نشانه‌ی صفحه‌ی چالش‌ها (کادر سمت راست)
SET_BANNER = (630, 112, 520, 50)      # نوار آبی بالای صفحه‌ی چالش‌های هر ست: "6 Days Remaining | Marquee Matchups | 1/4 ..."
MARQUEE_LOGO = ("V", 1154,122,23,30)  # لوگوی مخصوص Marquee کنار همان نوار
CURRENT_SET = None                    # ستی که الان روی آن کار می‌کنیم (حلقه‌ی Main پرش می‌کند)


def on_set_page(name=None):
    """آیا صفحه‌ی چالش‌های ست name (پیش‌فرض: ست فعلی) باز است؟
    اسم ست را در نوار آبی بالای صفحه می‌خواند؛ برای Marquee لوگوی V هم قبول است.
    بدون اسم ست: مثل قبل، فقط «View Rewards»."""
    name = name or CURRENT_SET
    if not name:
        return bool(scr.see(*CHALLENGES_PAGE))
    if name.lower().startswith("marquee") and scr.find(*MARQUEE_LOGO):
        return True
    return scr.contains(name, *SET_BANNER, fuzzy=0.9)


def wait_set_page(timeout=15, name=None):
    """صبر تا صفحه‌ی چالش‌های ست بیاید."""
    return bool(scr.until(lambda s: on_set_page(name), timeout=timeout))


def OpenChallenge(n):
    """به چالش n (۱ تا ۴) می‌رود و با A وارد می‌شود.
    خروجی: True = وارد شد،  "completed" = قبلاً کامل شده (وارد نمی‌شود)،  False = به آن نرسید.
    اول صبر می‌کند صفحه‌ی چالش‌ها کامل بیاید؛ وگرنه برچسب Completed هنوز کشیده نشده و
    چالش کامل‌شده دوباره باز می‌شد."""
    if not wait_set_page(15):
        print(f"Challenge {n}: challenge page of {CURRENT_SET or 'the set'} not shown")
        return False
    scr.wait_stable(timeout=3)                   # انیمیشن آمدن کادرها تمام شود
    if scr.until(lambda s: challenge_done(n), timeout=1.5):   # چند فریم، نه فقط یکی
        print(f"Challenge {n}: قبلاً کامل شده (Completed)")
        return "completed"
    if not GoPanel(n, CHALLENGE_PANELS):
        print(f"Challenge {n}: به آن نرسید (الان روی {current_challenge()})")
        return False
    if challenge_done(n):                        # یک بار دیگر، درست قبل از A
        print(f"Challenge {n}: قبلاً کامل شده (Completed)")
        return "completed"
    print(f"Challenge {n}: وارد شد")
    A()
    return True




# شماره‌ای که تابع‌ها می‌دهند → اسم کادر در صفحه‌ی Club
CLUB_BY_XY = {(0, 0): "Name", (1, 0): "Rarity", (2, 0): "Position",
              (1, 1): "Country", (2, 1): "League", (3, 1): "Club"}


def GoFilter(tx, ty, club=False):
    """رفتن به فیلتر (tx, ty).  club=False: Transfer Market با FindFilter،  club=True: صفحه‌ی Club با GoPanel."""
    if club:
        if GoPanel(CLUB_BY_XY[(tx, ty)], CLUB_PANELS):
            return True
        print(f"GoFilter: به {CLUB_BY_XY[(tx, ty)]} نرسید")
        return False
    return FindFilter(tx, ty)


def Position(Position, club=False):
    """فقط OFF را پاک می‌کند (مثل قبل). اسم پست هنوز تنظیم نمی‌شود و True برمی‌گرداند."""
    print("Looking for 'Position'")
    if not is_off(Position):
        return True
    # فلش ◀ انتخاب‌گر Position: در Market پایین کادر بلند است، در Club وسط کادر کوتاه (حدود y=264)
    arrow = CLUB_PANELS["Position"] if club else (700,362,70,22)
    GoFilter(2,0,club)
    for i in range(3):
        wait(300)
        GoFilter(2,0,club)
        wait(300)
        X()
        if scr.see("Position (3)", *arrow, threshold=0.85):
            return True
    wait(500)
    return bool(scr.see("Position (3)", *arrow, threshold=0.85))


def Pricing(price, club=False):
    if club:                       # صفحه‌ی Club قیمت ندارد
        print("Pricing: club=True، قیمت نادیده گرفته شد")
        return True
    prc=0
    if not FindFilter(0,1):
        return False
    wait(1000)
    X()
    wait(1000)
    A()
    wait(1000)
    for i in range(4):
        wait(100)
        print("Looking for 'Pricing'")
        if scr.see("BuyNow", 211,573,29,20):
            break
        Up()
        wait(1000)
    if not scr.see("BuyNow", 211,573,29,20):
        print("Pricing: خانه‌ی BuyNow پیدا نشد")
        if scr.see("Min", 582,683,120,23):   # پنجره‌ی قیمت باز مانده: ببند
            B()
            wait(1000)
        return False
    for i in range(50):
        wait(100)
        if (prc := scr.read_number(239, 576, 74, 16, default=0))==price:
            break
        print(prc)
        if prc>price:
            Left()
            wait(300)
        elif prc<price:
            Right()
            wait(300)
    reached = scr.read_number(239, 576, 74, 16, default=0) == price
    if not reached:
        print(f"Pricing: به {price} نرسید (الان {prc})")
    for i in range(4):
        wait(100)
        if scr.see("Min", 582,683,120,23):
            wait(1000)
            B()
            wait(1000)
            return reached
        wait(500)
    print("Pricing: 'Min' پیدا نشد")
    return False





BUY_STEP = 100          # هر بار که کارت پیدا نشد یا ۳ بار خرید نشد، قیمت این‌قدر بالاتر
BUY_MAX_EXTRA = 500     # حداکثر چقدر بالاتر از قیمت CSV (بیشتر نشود)
NO_CARDS = ("Custom", 695,352,203,35)   # صفحه‌ی «کارتی پیدا نشد» در Market


def price_step(p):
    """فاصله‌ی قیمت‌های قابل انتخاب در Market در این بازه."""
    return 50 if p < 1000 else 100 if p < 10000 else 250 if p < 50000 else 500 if p < 100000 else 1000


def valid_price(p):
    """گرد کردن رو به بالا به نزدیک‌ترین قیمتی که در بازی هست (مثلاً 10100 → 10250)."""
    s = price_step(p)
    return -(-p // s) * s


def BUY(price):
    """Buy Now با قیمت price. اگر کارتی نبود (صفحه‌ی Custom) یا ۳ بار خرید نشد
    (Expired / The bid / Sorry)، قیمت BUY_STEP بالاتر می‌رود (هر بار روی قیمت قبلی)،
    تا حداکثر BUY_MAX_EXTRA بالاتر از قیمت اول. True = خریده شد."""
    start, fails = price, 0
    print(f"Looking for 'BuyNow' (قیمت {price})")
    for i in range(10):
        wait(100)
        if on_results() or scr.see(*NO_CARDS):   # نتیجه آمد، یا کارتی نبود (پایین قیمت را بالا می‌برد)
            break
        Y()
        wait(3000)
    else:
        if not (on_results() or scr.see(*NO_CARDS)):
            print("BUY: صفحه‌ی نتیجه نیامد")
            return False

    for i in range(20):
        wait(100)
        if scr.see(*NO_CARDS) or fails >= 3:
            why = "کارتی پیدا نشد" if fails < 3 else "۳ بار خرید نشد"
            new = valid_price(price + BUY_STEP)
            if new > start + BUY_MAX_EXTRA:
                print(f"BUY: {why} و قیمت به سقف رسید ({start + BUY_MAX_EXTRA})")
                return False
            log(f"BUY: {why} → قیمت {price} ← {new}")
            price, fails = new, 0
            if on_results():
                B()                            # از صفحه‌ی نتیجه به فیلترها
            else:
                Y()                            # از صفحه‌ی «کارتی پیدا نشد» به فیلترها
            wait(1000)
            if not Pricing(price):
                print(f"BUY: قیمت {price} تنظیم نشد")
                return False
            Y()                                # جستجو با قیمت تازه
            wait(3000)
            continue
        wait(1000)
        if on_results():
            Right()
            wait(300)                 # بدون مکث، دکمه‌ی دوم گاهی گم می‌شد
            Down()
            wait(300)
            print("Found 'BuyNow (2)'")
            A()
        wait(1000)
        if scr.find("No", 610,434,55,32):
            print("Found 'No'")
            Up()
            wait(1000)
        if scr.find("Yes", 607,383,64,29):
            print("Found 'Yes'")
            A()
            wait(3000)
        if scr.see("Expired", 278,517,60,18):
            print("expired")
            fails += 1
            A()
            continue
        if scr.see("The bid", 316,298,115,39):
            print("Error")
            fails += 1
            A()
            wait(1000)
            continue
        if scr.see("Sorry", 430,303,90,33):
            fails += 1
            A()
            continue
        if scr.see("Sub (5)", 24,680,835,30):
            print(f"Bought (قیمت {price})")
            return True
        if scr.see("Confirm (2)", 29,681,87,27):
            B()
            print(f"Bought (قیمت {price})")
            return True
        if on_results():
            continue
        else:
            Y()
            wait(3000)
    print("BUY: خرید انجام نشد")
    return False

def FindClub():
    for i in range (10):
        wait(100)
        if scr.see("Player Search", 72,110,152,28):
            return True
        else:
            Y()
        wait(2000)
    return bool(scr.see("Player Search", 72,110,152,28))


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
            return True
        if scr.see(*REFRESH) and not scr.see(*FUT2):
            LB()
            wait(1000)
    return False


def search_club():
    """Search در صفحه‌ی Club تا نتیجه (Multi) بیاید."""
    for _ in range(10):
        wait(100)
        if scr.see(*MULTI) or scr.see(*NO_RESULT):
            return True
        Y()
        wait(2000)
    return bool(scr.see(*MULTI) or scr.see(*NO_RESULT))


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
            return True
        if scr.see(*REFRESH) and not scr.see(*FUT2):
            LB()
            wait(1000)
    return False


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
            return True
    return False


def use_club_card():
    """کارت در Club پیدا شد: A تا صفحه‌ی Swap بیاید."""
    for _ in range(10):
        wait(100)
        if scr.find(*SWAP):
            return True
        A()
        wait(2000)
    return bool(scr.find(*SWAP))


def SetFilters(row, last, club=False, tries=2):
    """تنظیم فیلترها طبق ردیف CSV. فقط فیلترهایی که با دفعه‌ی قبل فرق دارند تنظیم می‌شوند.
    last : دیکشنری آخرین مقدارهای تنظیم‌شده (بیرون از حلقه یک بار last = {} بسازید)
    club : True = صفحه‌ی جستجوی Club (قیمت ندارد)
    هر فیلتر tries بار امتحان می‌شود. مقدار فقط بعد از موفقیت در last ذخیره می‌شود؛
    اگر نشد از last پاک می‌شود تا دفعه‌ی بعد حتماً دوباره تنظیم شود.
    خروجی: True اگر همه تنظیم شدند، وگرنه False (بقیه‌ی فیلترها تنظیم نمی‌شوند)."""
    def changed(key):
        return row[key] != last.get(key)

    def apply(key, fn, n=tries):
        for t in range(n):
            wait(100)
            if fn(row[key], club=club):
                last[key] = row[key]
                return True
            print(f"فیلتر {key}={row[key]!r}: تلاش {t + 1} نشد")
        last.pop(key, None)
        return False

    league_changed = changed("League")

    for t in range(tries):                       # قیمت همیشه از نو (در Club کاری نمی‌کند)
        wait(100)
        if Pricing(int(row["Price"]), club=club):
            break
        print(f"فیلتر Price: تلاش {t + 1} نشد")
    else:
        return False
    if changed("Region") and not apply("Region", Region):
        return False
    if changed("Rarity") and not apply("Rarity", Rarity, n=1):   # Rarity خودش ۱۰ بار امتحان می‌کند
        return False
    if changed("Pos") and not apply("Pos", Position):
        return False
    if league_changed and not apply("League", League):
        last.pop("Club", None)                   # لیگ تنظیم نشد → باشگاه هم بعداً از نو
        return False
    if (league_changed or changed("Club")) and not apply("Club", Club):   # با عوض شدن لیگ، باشگاه هم دوباره
        return False
    return True

def Submit(single=False):
    """ثبت اسکواد. True وقتی برگشت به صفحه‌ی چالش‌های همین ست (اسم ست در نوار بالا، یا V برای Marquee).
    single=True (ست تک‌چالشی، صفحه‌ی چالش ندارد): بعد از Congratulations/Claim و بیرون آمدن از اسکواد."""
    claimed = False
    for i in range(10):
        wait(100)
        if scr.see("Submit", 1071,253,85,29):
            XMenu()
            wait(1000)
        if scr.see("Cancel", 526,557,84,23):
            Right()
            wait(1000)
        if scr.see("Submit (2)", 622,557,133,27):
            A()
            wait(1000)
        if scr.see("No (2)", 612,200,55,500):
            Up()
            wait(1000)
        if scr.find("Yes (2)", 609,200,59,500):
            A()
            wait(1000)
        if scr.see("Congratulations", 304,181,246,36) or scr.see("Claim", 598,492,78,24):
            claimed = True
            A()
            wait(1000)
        if scr.see("Store", 158,47,57,20) or scr.see("Open", 33,681,65,26):
            B()
            wait(1000)
        if on_set_page():
            return True
        if single and claimed and not at_squad():
            return True
    return False

def GotoHome():
    for i in range(10):
        wait(100)
        if scr.find("LIB", 525,65,25,23):
            return True
        if scr.see("Home", 77,135,113,45) or scr.find("X", 77,42,34,34):
            A()
            wait(2000)
        else:
            Xbox()
            wait(2000)
    return bool(scr.find("LIB", 525,65,25,23))


def CloseRecent(tries=5):
    """بازی اخیر را از راهنمای Xbox می‌بندد: Xbox → سه بار Down → Menu → Quit.
    True = بسته شد، یا بازی‌ای برای بستن نبود.  False = بعد از tries بار نشد.
    آخر کار راهنما بسته است (مثل بعد از GotoHome)."""
    GAME_CARD = ("Game card", 491,239,298,55)
    QUIT = ("Quit", 507,442,90,33)

    def guide_open():
        return scr.see("Home", 77,135,113,45) or scr.find("X", 77,42,34,34)

    def close_all():
        """با B منوی بازی و راهنما را می‌بندد، تا وقتی هیچ‌کدام دیده نشوند."""
        for _ in range(4):
            wait(100)
            if not (scr.see(*GAME_CARD) or guide_open()):
                return
            B()
            wait(1000)

    for i in range(tries):
        wait(100)
        print("Looking for 'Recent game'")
        if not guide_open():
            Xbox()                               # راهنما باز نیست: بازش کن
            wait(2000)
            continue
        for j in range(3):
            wait(100)
            Down()
            wait(500)
        XMenu()
        if not scr.wait_see(*GAME_CARD, timeout=3):      # تا ۳ ثانیه صبر، نه فقط ۱ ثانیه
            print("منوی بازی باز نشد؛ بازی اخیری نیست")
            close_all()                          # اگر منو دیر باز شد، آن را هم ببند
            return True
        if not scr.wait_see(*QUIT, timeout=2):
            print("Quit نیست؛ بازی اجرا نمی‌شود")
            close_all()                          # بستن منو و راهنما
            return True
        for p in range(4):
            wait(100)
            Down()
            wait(300)
        A()                                      # Quit
        wait(3000)
        if not scr.see(*GAME_CARD):              # منو رفت = Quit زده شد
            print("بازی بسته شد")
            close_all()                          # بستن راهنما
            return True
        print("Quit اثر نکرد؛ دوباره")
        B()                                      # منو هنوز باز است: ببند و از اول
        wait(1000)
    return False


# دیالوگ «Would you like to clear your squad?» — تصویرها حالت انتخاب‌شده‌ی دکمه‌اند.
# ناحیه کمی بزرگ‌تر از تصویر (دکمه چند پیکسل جابه‌جا می‌شود)، ولی Yes و No روی هم نمی‌افتند.
# فقط با تصویر (find)، نه متن: کلمه‌ی Yes/No همیشه دیده می‌شود، چه انتخاب شده باشد چه نه.
CLEAR_NO = ("No (3)", 598,408,84,52)
CLEAR_YES = ("Yes (3)", 593,354,92,52)


def Clear_Squad():
    """همه‌ی بازیکن‌های اسکواد چالش را برمی‌دارد: LS → Clear → Yes.
    بعد نشانگر را با ۶ بار Down و یک Up روی خانه‌ی اول می‌برد تا چیدن از اول شروع شود.
    True = پاک شد،  False = بعد از ۱۰ بار نشد (مثلاً روی صفحه‌ی اسکواد نبودیم)."""
    print("Looking for 'Clear Squad'")
    cleared = False
    for i in range(10):
        wait(100)
        # هر دور فقط یک کار، از آخرین مرحله به اول؛ وگرنه با منوی باز LS دوباره زده می‌شد و منو بسته می‌شد
        if scr.find(*CLEAR_NO, threshold=0.85):      # پنجره‌ی تأیید، روی No
            Up()
            wait(1000)
            continue
        if scr.find(*CLEAR_YES, threshold=0.85):     # پنجره‌ی تأیید، روی Yes
            A()
            wait(1000)
            cleared = True
            break
        if scr.see("Clear", 73,206,81,19):           # منوی اسکواد باز است
            A()
            wait(1000)
            continue
        if scr.see("Team", 52,174,155,25):           # صفحه‌ی اسکواد: باز کردن منو (زیر دیالوگ هم دیده می‌شود؛ برای همین آخر)
            LS()
            wait(1000)
            continue
        wait(1000)
    if not cleared:
        print("Clear Squad: نشد")
        return False
    print("Squad cleared")
    for i in range(6):
        wait(100)
        Down()
        wait(500)
    Up()
    wait(1000)
    return True


# %% Main
# ===== تنظیمات اجرا =====
START_GAME = True        # True = اول: GotoHome → CloseRecent → find_platform → FindUltimate → MainUltimate → FindSBC
                         # False = فقط وقتی دستی روی صفحه‌ی چالش‌ها هستید (برای تست)
ROW_TRIES = 3            # هر بازیکن چند بار خودکار امتحان شود، بعد توقف موقت برای درست کردن دستی
CHALLENGE_TRIES = 2      # باز کردن هر چالش چند بار خودکار امتحان شود
REPORT_DIR = r"C:\Users\Reach\Desktop\New Remote\Report"   # گزارش: Report\<ریموت>.log ، عکس‌ها: Report\shots\<ریموت>\

CSV_DIR = r"C:\Users\Reach\Desktop\New Remote"

last_club = {}      # آخرین فیلترهای صفحه‌ی Club (اول هر چالش خالی می‌شود)
last_market = {}    # آخرین فیلترهای Transfer Market
league = "OFF"      # لیگ ردیف فعلی (Club() این را می‌خواند)


class Abort(Exception):
    """ربات نمی‌تواند ادامه دهد و توقف موقت هم ممکن نیست (ریموت قدیمی). اجرا تمام می‌شود."""


# ===== گزارش (Report\<ریموت>.log) =====
sys.path.insert(0, r"C:\Users\Reach\Desktop\New Remote\Play")
import builtins
import xbox as _xbox
from report import Reporter
rep = Reporter(REMOTE, REPORT_DIR)


def print(*a, **k):
    """مثل print؛ خط را برای «آخرین کارها»ی گزارش هم نگه می‌دارد (همه‌ی تابع‌های این فایل)."""
    rep.remember(" ".join(map(str, a)))
    builtins.print(*a, **k)


def log(text):
    """مثل log پنل؛ خط را برای گزارش هم نگه می‌دارد."""
    rep.remember(text)
    _xbox.log(text)


def _callers(skip=2, n=4):
    """اسم تابع‌هایی که الان در حال اجرا هستند: "do_row ← run_row ← run_challenge"."""
    f, names = sys._getframe(skip), []
    while f and len(names) < n:
        if f.f_code.co_name != "<module>":
            names.append(f.f_code.co_name)
        f = f.f_back
    return " ← ".join(names)


def shot(name):
    """عکس صفحه‌ی فعلی در Report/shots/<ریموت>. مسیر فایل یا None."""
    try:
        path = rep.shot_path(name)
        scr.save(path)
        return path if os.path.exists(path) else None
    except Exception as e:                       # عکس نشد؛ ربات نباید به خاطرش بایستد
        print("عکس ذخیره نشد:", e)
        return None


def fail_shot(what):
    """مرحله نشد: در لاگ پنل و فایل گزارش بنویس، عکس بگیر، False برگردان."""
    path = shot(what)
    rep.fail(what, path, func=f"{what} ← {_callers()}")
    log(f"✗ {what} نشد" + (f"  (عکس: {os.path.basename(path)})" if path else ""))
    return False


def pause_fix(what, hint):
    """توقف موقت برای درست کردن دستی. ربات همین‌جا صبر می‌کند تا «ادامه» پنل زده شود،
    بعد همان مرحله را دوباره امتحان می‌کند.  hint = صفحه را قبل از «ادامه» کجا بگذارید.
    «توقف» پنل = تمام.  ریموت بدون توقف موقت → Abort."""
    since = rep.pause(what, hint, shot("pause_" + what))
    if not bot_pause(f"⏸ {what} نشد. دستی درست کنید و {hint}، بعد «ادامه»"):
        raise Abort(what)
    rep.resumed(since)
    wait(1000)


# پنجره‌های پیام که با A بسته می‌شوند
POPUPS = [
    ("Ok", 620,410,64,29),
    ("Ok (2)", 607,464,67,26),
    ("Ok (3)", 610,427,60,28),
    ("Ok (4)", 609,408,64,32),
    ("Sorry", 430,303,90,33),
    ("The bid", 316,298,115,39),
    ("Expired", 278,517,60,18),
]


def handle_popups():
    """اگر پنجره‌ی پیامی باز است با A می‌بندد. True اگر چیزی بسته شد."""
    with scr.frozen():
        if scr.find(*CLEAR_NO, threshold=0.85):  # دیالوگ پاک کردن اسکواد باز مانده، روی No
            hit = "Clear squad → No"
        else:
            hit = next((p[0] for p in POPUPS if scr.see(*p)), None)
    if not hit:
        return False
    print(f"پاپ‌آپ {hit!r} بسته شد")
    A()
    wait(1000)
    return True


def at_squad():
    """نقطه‌ی امن: صفحه‌ی اسکواد چالش (نوار پایین Sub (2) یا Sub (5))، یا کادر Swap که enter_slot از آن شروع می‌کند."""
    with scr.frozen():
        return bool(scr.see("Sub (2)", 29,680,447,33) or scr.see("Sub (5)", 24,680,835,30)
                    or scr.find(*SWAP))


def back_to_squad(tries=8):
    """از هر جای جستجو / مارکت با B (و بستن پاپ‌آپ‌ها) به صفحه‌ی اسکواد برمی‌گردد.
    قبل از هر B چک می‌کند که هنوز به اسکواد نرسیده باشد، تا از چالش بیرون نرود."""
    for _ in range(tries):
        wait(100)
        if at_squad():
            return True
        if handle_popups():
            continue
        B()
        wait(1500)
    return at_squad() or fail_shot("back_to_squad")


SBCS_FILE = r"C:\Users\Reach\Desktop\New Remote\Pannel\data\sbcs.json"   # فهرست SBCهای پنل


def sbc_name(e):
    """اسم یک SBC مثل پنل: "Marquee 1" یا فقط اسم ست."""
    return f"{e['set']} {e['challenge']}".strip() if e.get("challenge") else e["set"]


def load_plan():
    """SBCهای فعال پنل، به ترتیب، گروه‌شده بر اساس ست: [(اسم ست، [ورودی‌ها])].
    ورودی = {"set", "challenge", "csv"}. فایل پنل نبود → Marquee 1 تا 4 مثل قبل."""
    import json
    entries = []
    try:
        with open(SBCS_FILE, encoding="utf-8") as f:
            for r in json.load(f):
                if isinstance(r, str):
                    r = {"set": r}
                st = str(r.get("set") or r.get("name") or "").strip()
                if st and r.get("enabled", True):
                    entries.append({"set": st, "challenge": str(r.get("challenge") or "").strip(),
                                    "csv": str(r.get("csv") or "").strip()})
    except (OSError, ValueError) as e:
        print("SBC list of the panel not read:", e)
    if not entries:
        entries = [{"set": "Marquee", "challenge": str(n), "csv": ""} for n in range(1, 5)]
    plan = []
    for e in entries:
        if plan and plan[-1][0].lower() == e["set"].lower():
            plan[-1][1].append(e)
        else:
            plan.append((e["set"], [e]))
    return plan


def load_rows(e):
    """بازیکن‌های یک SBC: فایل csv پنل؛ اگر خالی بود <ست><چالش>.csv (مثلاً Marquee1.csv) یا <ست>.csv."""
    cands = [e.get("csv")] if e.get("csv") else []
    cands += [os.path.join(CSV_DIR, f"{e['set']}{e.get('challenge', '')}.csv"),
              os.path.join(CSV_DIR, f"{e['set']}.csv")]
    for path in cands:
        if path and os.path.exists(path):
            with open(path, newline="", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))      # هر ردیف = دیکشنری با ستون‌های عنوان
            print(f"{os.path.basename(path)}: {len(rows)} rows")
            return rows
    return None


def is_single(e):
    """ست تک‌چالشی (در پنل چالش خالی): مرحله‌ی انتخاب چالش ندارد."""
    return not e.get("challenge")


def open_sbc_challenge(e):
    """وارد شدن به چالش یک ورودی پنل. True / "completed" / False.
    عدد (1 تا 4) → همان کادر صفحه‌ی چالش‌ها؛ اسم → کادری که آن اسم را دارد؛
    خالی (تک‌چالشی) → این مرحله رد می‌شود."""
    ch = e.get("challenge", "")
    if is_single(e):
        print(f"{e['set']}: single challenge, no challenge page")
        return True
    if ch.isdigit():
        return OpenChallenge(int(ch))
    if not wait_set_page(15):
        return False
    for k, (x, y, w, h) in CHALLENGE_PANELS.items():     # کادری که اسم چالش را دارد (عنوان بالای کادر)
        if scr.contains(ch, x, y, w, 80, fuzzy=0.9):
            return OpenChallenge(k)
    print(f"Challenge '{ch}' not found on the page of {e['set']}")
    return False


def run_challenge(e):
    """یک SBC (ورودی پنل): باز کردن، بازیکن‌ها، Submit. هر جا نشد → توقف موقت و بعد از «ادامه» همان مرحله دوباره."""
    n = sbc_name(e)
    print(f"===== {n} =====")
    rep.ctx(challenge=n, row=None)
    rows = load_rows(e)
    while rows is None:
        pause_fix(f"CSV {n}", "set the CSV of this SBC in the panel")
        rows = load_rows(e)
    while True:
        wait(100)
        res = False
        for t in range(CHALLENGE_TRIES):
            wait(100)
            res = open_sbc_challenge(e)
            if res:
                break
            handle_popups()
            wait(2000)
        if res == "completed":
            rep.info("قبلاً کامل شده (Completed)، رد شد")
            rep.challenge_done(n)               # برای پنل: این Marquee کامل است
            return True                         # قبلاً کامل شده
        if res:
            break
        pause_fix(f"باز کردن چالش {n}", "صفحه را روی لیست چالش‌ها بگذارید")

    while not open_challenge():                 # شروع چالش (Start Challenge)
        wait(100)
        pause_fix(f"شروع چالش {n}", "صفحه را روی اسکواد چالش بگذارید")
    if Clear_Squad():                           # اول کار اسکواد خالی شود (بازیکن‌های مانده از قبل)
        rep.info("اسکواد اول کار پاک شد")
    else:
        fail_shot("Clear_Squad اول چالش")       # شاید اسکواد از قبل خالی بود؛ ادامه
    last_club.clear()                           # بازی در هر چالش فیلترها را ریست می‌کند
    last_market.clear()

    fill_squad(n, rows)

    rebuilt = False
    while True:                                 # ثبت و برگشت به صفحه‌ی چالش‌ها
        wait(100)
        for t in range(2):
            wait(100)
            if Submit(single=is_single(e)):
                rep.ok("Submit شد، چالش تمام شد" + (" (بعد از چیدن دوباره)" if rebuilt else ""))
                rep.challenge_done(n)           # برای پنل: این Marquee کامل شد
                return True
            handle_popups()
        if not rebuilt and at_squad():          # Submit پیدا نشد: یک بار پاک کن و از نو بچین
            rebuilt = True
            fail_shot(f"Submit چالش {n}")
            rep.info("Submit پیدا نشد → پاک کردن اسکواد و چیدن دوباره (یک بار)")
            log("Submit پیدا نشد؛ پاک کردن اسکواد و چیدن دوباره")
            if Clear_Squad():
                last_club.clear()
                last_market.clear()
                fill_squad(n, rows)
                continue
            fail_shot("Clear_Squad برای چیدن دوباره")
        pause_fix(f"Submit چالش {n}", "Submit را دستی بزنید یا صفحه را روی اسکواد کامل بگذارید")


def do_row(row):
    """یک بازیکن: اول در Club بگرد، نبود از Market بخر. هر مرحله نشد → False (بقیه اجرا نمی‌شوند)."""
    global league
    league = row["League"]

    if not enter_slot():                        # از اسکواد به خانه‌ی بازیکن
        return fail_shot("enter_slot")
    if not FindClub():
        return fail_shot("FindClub")
    if not SetFilters(row, last_club, club=True):   # اول در Club بگرد
        return fail_shot("فیلترهای Club")
    if not search_club():
        return fail_shot("search_club")

    if scr.see(*NO_RESULT):                     # در Club نبود → از Market بخر
        if not clear_slot():
            return fail_shot("clear_slot")
        if not back_to_market():
            return fail_shot("back_to_market")
        if not SetFilters(row, last_market):
            return fail_shot("فیلترهای Market")
        if not BUY(int(row["Price"])):
            return fail_shot("BUY")
        return True

    print('Found in Club')
    return use_club_card() or fail_shot("use_club_card")


def run_row(challenge, i, row):
    """یک بازیکن را تا ROW_TRIES بار خودکار امتحان می‌کند (بین تلاش‌ها برگشت به اسکواد).
    نشد → توقف موقت؛ بعد از «ادامه» همین بازیکن دوباره (رفتن به بازیکن بعدی خانه‌ی اشتباه را پر می‌کند)."""
    tag = f"[{challenge}:{i}]"
    while True:
        wait(100)
        for t in range(1, ROW_TRIES + 1):
            wait(100)
            if do_row(row):
                rep.ok("بازیکن اضافه شد" + (f" (تلاش {t})" if t > 1 else ""))
                return True
            if t < ROW_TRIES:                   # تلاش آخر «دوباره» ندارد؛ بعدش توقف موقت است
                rep.retry("بازیکن", t, ROW_TRIES)
            log(f"{tag} تلاش {t} از {ROW_TRIES} نشد؛ برگشت به اسکواد")
            last_club.clear()                   # معلوم نیست فیلترها در چه حالی مانده‌اند: همه از نو
            last_market.clear()
            if not back_to_squad():
                break                           # به اسکواد نرسید: تلاش دیگر فایده ندارد
        pause_fix(f"{tag} بازیکن", "صفحه را روی اسکواد، روی خانه‌ی همین بازیکن بگذارید")
        last_club.clear()                       # شاید دستی فیلترها را عوض کرده‌اید
        last_market.clear()


def fill_squad(n, rows):
    """همه‌ی بازیکن‌های چالش n را به ترتیب می‌چیند (هر کدام با تلاش دوباره و توقف موقت)."""
    for i, row in enumerate(rows, 1):           # یک دور برای هر بازیکن
        wait(100)
        desc = " | ".join(row[k] for k in ("Rarity", "Region", "Pos", "Club", "League", "Price"))
        print(f"[{n}:{i}/{len(rows)}] " + desc)
        rep.ctx(row=f"{i}/{len(rows)} ({desc})")
        run_row(n, i, row)
    rep.ctx(row=None)


# مراحل شروع: (اسم، تابع، لازم است؟) — مرحله‌ی «لازم نیست» اگر نشد فقط رد می‌شود
START_STEPS = [
    ("GotoHome", GotoHome, True),
    ("CloseRecent", CloseRecent, True),                            # بستن بازی اخیر، تا از اول باز شود
    ("find_platform", lambda: find_platform(platform()), False),   # تیک XS پنل: روشن = Ser، خاموش = One
    ("FindUltimate", FindUltimate, False),                         # اگر نشد MainUltimate خودش دوباره صدایش می‌زند
    ("MainUltimate", MainUltimate, True),
    ("FindSBC", FindSBC, True),
]


def start_game(tries=3, start=0):
    """مراحل شروع از مرحله‌ی start. هر بار نشد، از Home دوباره (تا tries بار).
    خروجی: None = همه شد، وگرنه شماره‌ی مرحله‌ای که نشد."""
    for t in range(1, tries + 1):
        wait(100)
        print(f"===== باز کردن بازی (تلاش {t}) =====")
        for k in range(start, len(START_STEPS)):
            wait(100)
            name, fn, must = START_STEPS[k]
            rep.ctx(step=name)
            if fn():
                continue
            if not must:
                print(f"{name} نشد؛ ادامه")
                rep.info(f"{name} نشد (لازم نیست، ادامه)")
                continue
            fail_shot(name)
            break
        else:
            rep.ctx(step=None)
            rep.ok("بازی باز شد و صفحه‌ی SBC آمد")
            return None
        if t < tries:
            rep.retry("شروع بازی از Home", t, tries)
        start = 0                               # تلاش بعدی از Home
    return k


rep.start(f"START_GAME={START_GAME}")
status = "ناتمام"
try:
    if START_GAME:
        failed = start_game()
        while failed is not None:
            wait(100)
            name = START_STEPS[failed][0]
            pause_fix(f"شروع بازی ({name})", f"صفحه را جایی بگذارید که {name} از آن شروع می‌کند")
            failed = start_game(tries=1, start=failed)   # بعد از «ادامه» از همان مرحله
    plan = load_plan()                          # SBCهای فعال پنل، گروه‌شده بر اساس ست
    log("Plan: " + ", ".join(f"{name} ({len(es)})" for name, es in plan))
    for k, (set_name, entries) in enumerate(plan):
        wait(100)
        rep.ctx(challenge=set_name, row=None)
        CURRENT_SET = set_name
        if k == 0 and not START_GAME:
            pass                                # تست دستی: صفحه‌ی چالش‌های ست اول از قبل باز است
        else:
            if k > 0:                           # بار اول FindSBC همین الان صفحه‌ی SBC را باز کرده
                while not back_to_sbc():
                    pause_fix("back to SBC", "put the screen on the SBC page")
            while not (open_set(set_name) and (all(is_single(e) for e in entries) or wait_set_page(15))):
                # ست باز نشد، یا صفحه‌ای که باز شد مال این ست نیست (اسمش در نوار بالا نیست)
                pause_fix(f"open set {set_name}", "open the set by hand (its challenge page)")
        log(f"Set {set_name}: {len(entries)} challenge(s)")
        for e in entries:
            wait(100)
            run_challenge(e)
    rep.ctx(challenge=None, row=None, step=None)
    log("✓ همه‌ی چالش‌ها تمام شد")
    status = "✓ همه‌ی چالش‌ها تمام شد"
except Abort as e:
    rep.stopped(f"ربات متوقف شد (توقف موقت ممکن نبود): {e}")
    shot("Abort")
    log(f"✗ ربات متوقف شد: {e}")
    status = f"✗ Abort: {e}"
except BotStopped:
    rep.stopped("«توقف» از پنل")
    status = "■ توقف از پنل"
    raise
except RemoteDown as e:
    rep.stopped(f"ریموت وصل نشد: {e}")
    status = "✗ ریموت قطع"
    raise
except Exception as e:                          # باگ کد: کامل در گزارش
    rep.crash(e)
    shot("crash")
    status = f"‼ خطای کد: {type(e).__name__}"
    raise
finally:
    rep.end(status)


# %%
