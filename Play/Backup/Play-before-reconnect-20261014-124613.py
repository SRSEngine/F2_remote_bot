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
def my_remote(default="XBOX"):
    """ریموتی که این ربات را اجرا کرده. «شروع» پنل ریموت run_bot را اجرا می‌کند، پس پروسه‌ی پدر
    همان ریموت است: pid آن در Controller\\remotes\\<اسم>.json آمده (مثلاً C11 یا C12).
    اگر پیدا نشد (اجرا از VS Code): متغیر محیطی XBRP_REMOTE، وگرنه default.
    بدون این، با چند ریموت روشن، ربات به جدیدترین ریموت وصل می‌شد، نه ریموت خودش."""
    import glob, json
    ppid = os.getppid()
    for path in glob.glob(r"C:\Users\Reach\Desktop\New Remote\Controller\remotes\*.json"):
        try:
            with open(path, encoding="utf-8") as f:
                info = json.load(f)
        except (OSError, ValueError):
            continue
        if info.get("pid") == ppid:
            return info.get("name") or os.path.splitext(os.path.basename(path))[0]
    return os.environ.get("XBRP_REMOTE") or default


REMOTE = my_remote()                    # C11 / C12 / ... ؛ از VS Code: "XBOX"
# Second remote of a console is named "C32-2": the PIPE uses REMOTE, everything the panel stores
# (accounts, active account, SBC progress, report) uses the console name.
import re as _re
CONSOLE = _re.sub(r"-\d+$", "", REMOTE)  # C32-2 -> C32
print(f"Remote: {REMOTE}" + (f" (console {CONSOLE})" if CONSOLE != REMOTE else ""))
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
        if scr.see("PLAY (2)", 147,604,48,19) or scr.see("RESUME", 129,595,91,36):
            A()
            wait(3000)
            if scr.see("CLOSE", 157,531,62,29):
                A()
            return True
        wait(1000)
    print("'PLAY' پیدا نشد")
    return False

LETS_PLAY = ("Let", 587,474,112,25)          # دکمه‌ی «A Let's Play!» هنگام ورود به Ultimate
EMAIL_POPUP = ("email up to date", 400,150,480,50)   # عنوان «Is your email up to date?» (EA) هنگام ورود به Ultimate


PRESS_ANY = ("Any Button", 20,655,300,35)        # صفحه‌ی شروع FC: «Press Any Button» پایین-چپ
WELCOME_BACK = ("Start building", 530,600,220,38) # «WELCOME BACK, ...» با «A Start building my Squad»
XBOX_RESUME = ("RESUME", 50,585,240,55)           # صفحه‌ی بازی در داشبورد Xbox: دکمه‌ی سبز RESUME
FUT_LIMIT = ("Limit Reached", 340,235,600,40)     # «You've reached the limit for FUT Account Creation on this console»


class AccountSkip(Exception):
    """این اکانت روی این کنسول قابل اجرا نیست (مثلاً Limit Reached): اکانت بعدی."""


def entry_screens():
    """صفحه‌های بین راه ورود به Ultimate. True اگر کاری شد. Limit Reached → AccountSkip."""
    if scr.contains(*FUT_LIMIT, fuzzy=0.85):
        log("FUT: 'Limit Reached' (FUT account creation limit on this console)")
        B()
        wait(1000)
        raise AccountSkip("FUT account creation limit reached on this console")
    for box, what in ((PRESS_ANY, "Press Any Button"), (WELCOME_BACK, "Welcome back: Start building my Squad"),
                      (XBOX_RESUME, "Xbox: RESUME the game")):
        if scr.contains(*box, fuzzy=0.85):
            print(what)
            A()
            wait(2000)
            return True
    return False


def email_popup():
    """پیغام EA «Is your email up to date?»: Right (از «Update email» به «Yes») و A. True اگر دیده شد."""
    if not scr.contains(*EMAIL_POPUP, fuzzy=0.85):
        return False
    log("EA: 'Is your email up to date?' -> Yes")
    Right()
    wait(500)
    A()
    wait(1500)
    return True


def FindUltimate():
    for i in range(15):
        wait(100)
        print("Looking for 'Ultimate'")

        if scr.see("Advanced", 32,677,93,32):
            A()
            continue

        if scr.see("Ok", 620,410,64,29):
            A()
            continue

        if scr.see("Ok (2)", 607,464,67,26):
            A()
            continue

        if scr.see(*LETS_PLAY):                  # «A Let's Play!» هنگام ورود به Ultimate
            A()
            wait(1000)
            continue

        if email_popup():                        # «Is your email up to date?» → Right، A (Yes)
            continue

        if entry_screens():                      # Press Any Button / Welcome back / RESUME (Limit Reached → رد اکانت)
            continue

        if scr.see("Two", 403,153,472,48) or scr.see("Enter", 498,154,279,44):
            # تأیید دومرحله‌ای EA: Mobile App → Continue → تایپ کد ۶ رقمی (EAGauth اکانت) → XMenu
            if not ea_two_factor():
                fail_shot("EA two-factor")
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

        if scr.see("Continue (4)", 550,500,205,300) :
            A()
            wait(1000)


        if scr.see("Ultimate", 379,533,500,32) or scr.see("Ultimate (2)", 411,300,600,600):
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

        if scr.see(*LETS_PLAY):                  # «A Let's Play!» در چرخش ورود به Ultimate
            A()
            wait(1000)

        email_popup()                            # «Is your email up to date?» → Right، A (Yes)
        entry_screens()                          # Press Any Button / Welcome back / RESUME (Limit Reached → رد اکانت)

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


SBC_WELCOME = ("Advance (4)", 25,675,100,34)   # «A Advance» پیام‌های Welcome to SBC هنگام ورود به صفحه‌ی ست‌ها


def open_set(name, tries=10):
    """ست SBC با اسم name را در صفحه‌ی SBC پیدا می‌کند و با A بازش می‌کند (مثل open_marquee قبلی).
    اگر تصویر نمونه‌ای به همین اسم باشد (مثلاً Marquee.png) با تصویر، وگرنه با خواندن متن کادرها."""
    for _ in range(tries):
        wait(100)
        # ورود به صفحه‌ی ست‌ها: گاهی پیام‌های «Welcome to SBC» (چند صفحه، «A Advance») جلوی آن است
        for _ in range(6):
            if not scr.see(*SBC_WELCOME):
                break
            print("SBC welcome: Advance")
            A()
            wait(1500)
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
        if scr.see("Swap (5)", 33,650,151,56):
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


def reward_popup():
    """پنجره‌ی «Congratulations! ... Claim» بعد از Submit. صفحه‌ی ست پشت آن (کم‌نور) هنوز دیده می‌شود."""
    return bool(scr.see("Congratulations", 304,181,246,36) or scr.see("Claim", 598,492,78,24))


def on_set_page(name=None):
    """آیا صفحه‌ی چالش‌های ست name (پیش‌فرض: ست فعلی) باز است؟
    اسم ست را در نوار آبی بالای صفحه می‌خواند؛ برای Marquee لوگوی V هم قبول است.
    بدون اسم ست: مثل قبل، فقط «View Rewards».
    اگر پنجره‌ی Claim رویش باز است، False (اول باید Claim شود)."""
    name = name or CURRENT_SET
    if reward_popup():
        return False
    if not name:
        return bool(scr.see(*CHALLENGES_PAGE))
    if name.lower().startswith("marquee") and scr.find(*MARQUEE_LOGO):
        return True
    return scr.contains(name, *SET_BANNER, fuzzy=0.9)


SBC_INTRO = ("Advance (2)", 32,682,167,24)   # نوار پایین «A Advance  B Back» صفحه‌ی معرفی SBC
SET_ADVANCE = ("Advance (3)", 27,677,92,35)  # «A Advance» پایین-چپ: صفحه‌ی پایان ست (MARQUEE MATCHUPS بعد از ۴/۴)،
                                             # و Welcome to SBC؛ در هر دو A درست است
SBC_HUB_TITLE = ("SBC", 150,42,70,30)        # عنوان «SBC» کنار Main بالا-چپ = صفحه‌ی ست‌ها (هاب SBC)


def store_open():
    """صفحه‌ی Store (بعد از گرفتن جایزه بازی آنجا می‌رود؛ B برمی‌گرداند)."""
    return bool(scr.see("Store", 158,47,57,20))


def on_sbc_hub():
    """صفحه‌ی ست‌های SBC (همه‌ی ست‌ها، هر تبی: All / Challenges / ...)."""
    return scr.contains(*SBC_HUB_TITLE)


def wait_set_page(timeout=15, name=None):
    """صبر تا صفحه‌ی چالش‌های ست بیاید. اولین بار که هر اکانت یک ست را باز می‌کند صفحه‌ی معرفی SBC
    («Review Players / Select & Submit / Get Your Reward» با «A Advance») جلوی آن است: هر بار A تا رد شود."""
    end = time.monotonic() + timeout
    presses = 0                                  # سقف A، تا اگر پنجره بسته نشد حلقه بی‌پایان نشود
    while time.monotonic() < end:
        wait(100)
        if on_set_page(name):
            return True
        if presses >= 8:
            break
        if reward_popup():
            presses += 1
            print("Reward: Claim")
            A()
            wait(1500)
            end = max(end, time.monotonic() + 5)
            continue
        if scr.see(*SBC_INTRO):
            presses += 1
            print("SBC intro: Advance")
            A()
            wait(1500)
            end = max(end, time.monotonic() + 5)   # بعد از هر Advance کمی وقت برای آمدن صفحه
            continue
        if store_open():                         # بعد از Claim بازی به Store می‌رود: B
            presses += 1
            print("Store after reward: Back")
            B()
            wait(1500)
            end = max(end, time.monotonic() + 5)
            continue
        if scr.see(*SET_ADVANCE):                # صفحه‌ی پایان ست / Welcome to SBC
            presses += 1
            print("Advance")
            A()
            wait(1500)
            end = max(end, time.monotonic() + 5)
            continue
        wait(400)
    return on_set_page(name)


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
BUY_MAX_EXTRA = 1000    # حداکثر چقدر بالاتر از قیمت CSV (بیشتر نشود)
NO_CARDS = ("Custom", 695,352,203,35)   # صفحه‌ی «کارتی پیدا نشد» در Market


def price_step(p):
    """فاصله‌ی قیمت‌های قابل انتخاب در Market در این بازه."""
    return 50 if p < 1000 else 100 if p < 10000 else 250 if p < 50000 else 500 if p < 100000 else 1000


def valid_price(p):
    """گرد کردن رو به بالا به نزدیک‌ترین قیمتی که در بازی هست (مثلاً 10100 → 10250)."""
    s = price_step(p)
    return -(-p // s) * s


COINS_BOX = (194, 130, 138, 25)          # عدد «My Coins» بالا-چپ Transfer Market (۱۴۳ تکه‌ای از سکه را می‌گرفت: 97 → 974)
ACTIONS = ("Actions", 27,675,95,35)      # پایین-چپ به‌جای BuyNow: احتمالاً کوین برای خرید کافی نیست
NO_COINS = "no_coins"                    # خروجی BUY / do_row وقتی کوین اکانت تمام شده


COIN_LABEL = ("My Coins", 85,125,110,32)  # برچسب کنار عدد کوین (صفحه‌ی نتیجه / «کارتی پیدا نشد» در Market)
_coins_started = set()                     # اکانت‌هایی که Start Coin آن‌ها در همین اجرا ذخیره شد


def save_coins(coins):
    """کوین اکانت فعلی در پنل (account_status.json): اولین بار در این اجرا = Start Coin، هر بار = End Coin."""
    acc = CURRENT_ACCOUNT
    if acc is None or coins is None:
        return
    key = acc.key()
    try:
        panel_core.set_coins(key, coins, start=key not in _coins_started)
        _coins_started.add(key)
    except Exception as e:                     # پنل نشد؛ ربات نباید به خاطرش بایستد
        print("coins not saved:", e)


TOP_COIN = ("FUT coin", 700, 38, 570, 40)   # سکه‌ی بالا-راست (Main / Store): y ثابت، x جابه‌جا می‌شود → کل نوار
_tess = None                                # Tesseract برای عددهای کوتاه مثل «4K» (OCR ویندوز آن‌ها را نمی‌بیند)


def coins_value(text):
    """'485' → 485،  '12,827' → 12827،  '4K' → 4000،  '12.5K' → 12500،  '1.2M' → 1200000؛ نشد → None."""
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*([KkMm]?)", (text or "").replace(" ", ""))
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    return int(round(n * {"": 1, "k": 1000, "m": 1000000}[m.group(2).lower()]))


def read_top_coins():
    """کوین از نوار بالا-راست: سکه‌ی FUT را در نوار y پیدا می‌کند و عدد بعد از آن را تا آیکون سبز بعدی
    می‌خواند. 'K' = هزار (4K = 4000). نشد → None."""
    global _tess
    m = scr.find(*TOP_COIN)
    if not m:
        print("Top coins: FUT coin not found")
        return None
    x0, y0, h = m.left + m.w + 2, m.top, m.h
    strip = scr.crop(x0, y0, 160, h).astype(int)            # تا آیکون سبز (حداکثر ۱۶۰ پیکسل)
    b, g, r = strip[..., 0], strip[..., 1], strip[..., 2]
    green = ((g > 120) & (g - r > 50) & (g - b > 10)).sum(axis=0) > 2
    end = int(np.argmax(green)) if green.any() else 120
    if end < 8:
        return None
    text = ""
    try:                                                     # اول Tesseract (4K را هم می‌خواند)
        from founder import TesseractOcr, _prep_for_ocr
        _tess = _tess or TesseractOcr()
        gray = scr.crop(x0, y0 - 2, end - 2, h + 4, color=False)
        text = _tess.text(_prep_for_ocr(gray, True, 90), True, "0123456789,.KkMm")
    except Exception as e:
        print("Top coins: Tesseract failed:", e)
    v = coins_value(text)
    if v is None:                                            # بعد OCR ویندوز
        text = scr.read(x0, y0 - 2, end - 2, h + 4)
        v = coins_value(text)
    print(f"Top coins: {text!r} -> {v}")
    return v


def read_coins_step():
    """مرحله‌ی شروع (قبل از FindSBC): کوین بالا-راست → پنل (Start Coin این اکانت در این اجرا)."""
    v = read_top_coins()
    if v is None:
        return False
    log(f"Coins: {v}")
    save_coins(v)
    return True


def note_coins():
    """عدد My Coins را می‌خواند (فقط اگر برچسب My Coins دیده شود) و در پنل ذخیره می‌کند."""
    if not scr.contains(*COIN_LABEL):
        return None
    coins = scr.read_number(*COINS_BOX)
    if coins is not None:
        print(f"My Coins: {coins}")
        save_coins(coins)
    return coins


def finish_coins(acc):
    """End Coin در پنل = آخرین کوین خوانده‌شده، وقتی کار این اکانت در این اجرا تمام شد."""
    if acc is None or acc.key() not in _coins_started:
        return
    try:
        panel_core.finish_coins(acc.key())
    except Exception as e:
        print("end coins not saved:", e)


class OutOfCoins(Exception):
    """کوین اکانت تمام شد: بقیه‌ی این اکانت رد می‌شود و ربات سراغ اکانت بعدی می‌رود."""


def out_of_coins(price):
    """«Actions» پایین-چپ دیده شد و کوین باقی‌مانده کمتر از قیمت کارت است؟
    کوین فقط وقتی خوانده می‌شود که Actions دیده شده (روی صفحه‌ی اسکواد آن ناحیه عدد دیگری دارد)."""
    if not scr.see(*ACTIONS):
        return False
    coins = scr.read_number(*COINS_BOX)
    if coins is None:
        print("BUY: 'Actions' seen but the coins could not be read")
        return False
    save_coins(coins)                            # End Coin = همین مقدار
    if coins < price:
        log(f"BUY: out of coins ({coins} < {price})")
        return True
    print(f"BUY: 'Actions' seen, coins {coins} >= {price}")
    return False


# ===== اسم بازیکن‌های اسکواد چالش (تا در Market بازیکن تکراری خریده نشود) =====
CLUB_NAME_BOX = (236,200,90,19)        # اسم کارت انتخاب‌شده در نتیجه‌ی جستجوی Club (کنار عکس کوچک بازیکن)
MARKET_NAME_BOX = (90,312,290,30)      # اسم کارت انتخاب‌شده در نتیجه‌ی Transfer Market (زیر کارت کوچک چپ)؛
                                       # پهن: اسم وسط‌چین است و کادر چپ گاهی ~۶۵ پیکسل جابه‌جاست (با / بدون «Market»)
EXPIRED_BOX = ("Expired", 278,517,60,18)   # Time Remaining: Expired (کارت انتخاب‌شده دیگر خریدنی نیست)
PICK_TRIES = 20                        # چند کارت در نتیجه‌ی Market بررسی شود، بعد reprice
PICK_PATH = "RRRRDLLLLD"               # مسیر مار: ۴ راست، پایین، ۴ چپ، پایین، ... (تکرار)
SQUAD_NAMES = []                       # اسم بازیکن‌های اسکواد چالش فعلی (از Club آمده یا خریده شده)


def _text_box(box, pad=8):
    """برش دقیق دور متن روشن داخل box (OCR ویندوز روی ناحیه‌ی پهن حرف اول را جا می‌انداخت: Smith → mith)."""
    x, y, w, h = box
    g = scr.crop(x, y, w, h, color=False)
    m = g > 170
    cols, rows = np.where(m.sum(0) > 0)[0], np.where(m.sum(1) > 0)[0]
    if not len(cols):
        return None
    x0, x1 = max(0, cols[0] - pad), min(w, cols[-1] + pad + 1)
    y0, y1 = max(0, rows[0] - 4), min(h, rows[-1] + 5)
    return (x + x0, y + y0, x1 - x0, y1 - y0)


def card_name(box):
    """اسم کارت انتخاب‌شده: برش دقیق دور متن، اول Tesseract (روی ۱۱۸ عکس واقعی بهترین بود)، بعد OCR ویندوز."""
    global _tess
    t = _text_box(box) or box
    name = ""
    try:
        from founder import TesseractOcr, _prep_for_ocr
        _tess = _tess or TesseractOcr()
        name = _tess.text(_prep_for_ocr(scr.crop(*t, color=False), True, 90), True)
    except Exception as e:
        print("card_name: Tesseract failed:", e)
    name = (name or "").strip()
    if len(_norm(name)) < 2:
        name = (scr.read(*t) or "").strip()
    return name


def _name_key(n):
    # «rn» → «m» در هر دو طرف: OCR گاهی m را rn می‌خواند (Smith → Srnith)
    return _norm(re.sub(r"(\.{2,}|…)\s*$", "", n or "")).replace("rn", "m")


def _name_words(n):
    return [w for w in (_norm(x).replace("rn", "m") for x in re.sub(r"(\.{2,}|…)\s*$", "", n or "").split()) if w]


def same_player(a, b):
    """یک بازیکن؟ بدون حروف خاص و فاصله؛ اسم کوتاه‌شده با «...» = اول اسم؛ تحمل اشتباه OCR (0.85).
    Club و Transfer یک بازیکن را گاهی کوتاه‌تر / کامل‌تر نشان می‌دهند («Ampadu» / «Ethan Ampadu»):
    اگر همه‌ی کلمه‌های اسم کوتاه‌تر در اسم بلندتر باشند، یکی است."""
    ka, kb = _name_key(a), _name_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    wa, wb = _name_words(a), _name_words(b)
    short, long_ = sorted((wa, wb), key=len)
    if short and len(short) < len(long_) and all(
            len(w) >= 3 and any(SequenceMatcher(None, w, x).ratio() >= 0.85 for x in long_) for w in short):
        return True
    cut = any(re.search(r"(\.{2,}|…)\s*$", x) for x in (a, b))    # «Pedro Bic...» (OCR گاهی «..»)
    if cut and min(len(ka), len(kb)) >= 4:     # کوتاه‌شده: فقط ابتدای اسم بلندتر، با تحمل اشتباه OCR
        short, long_ = sorted((ka, kb), key=len)
        if SequenceMatcher(None, short, long_[:len(short)]).ratio() >= 0.85:
            return True
    return SequenceMatcher(None, ka, kb).ratio() >= 0.85


def in_squad(name):
    return any(same_player(name, n) for n in SQUAD_NAMES)


def remember_player(name, where):
    """اسم بازیکنی که به اسکواد آمد (Club یا خرید)."""
    if name and not in_squad(name):
        SQUAD_NAMES.append(name)
    log(f"Squad players ({where}): {', '.join(SQUAD_NAMES) or '-'}")


def pick_card(tries=PICK_TRIES):
    """در نتیجه‌ی Market کارتی پیدا می‌کند که Expired نیست و بازیکنش در اسکواد نیست، و A (Buy Now) می‌زند.
    مسیر: اول کارت انتخاب‌شده، بعد ۴ راست، پایین، ۴ چپ، پایین، ... تا tries کارت.
    خروجی: ("picked", اسم) | ("none", "") = کارت مناسبی نبود (reprice) | ("lost", "") = صفحه‌ی نتیجه نیست."""
    moves = {"R": Right, "L": Left, "D": Down}
    for i in range(tries):
        wait(100)
        if not on_results():
            return "lost", ""
        name = card_name(MARKET_NAME_BOX)
        expired = bool(scr.see(*EXPIRED_BOX))
        dup = in_squad(name)
        if not expired and not dup:
            log(f"Card {i + 1}: {name or '?'} -> buy")
            A()
            return "picked", name
        log(f"Card {i + 1}: {name or '?'} " + ("expired" if expired else "already in the squad") + " -> next")
        moves[PICK_PATH[i % len(PICK_PATH)]]()
        wait(500)                              # کادر چپ (اسم / زمان) کارت تازه بیاید
    return "none", ""


# ---- قیمت زنده‌ی بازار (Prices\sbc_prices.py که پنل در پس‌زمینه اجرا می‌کند) ----
PRICES_FILE = r"C:\Users\Reach\Desktop\New Remote\Prices\sbc_prices.json"
USE_MARKET_PRICES = True     # False = فقط قیمت CSV مثل قبل
PRICE_MAX_AGE = 20 * 60      # ثانیه؛ قیمت FUT.GG قدیمی‌تر از این → قیمت CSV
_prices_cache = {"mtime": None, "doc": None}


def tag_rows(e, rows):
    """قیمت اصلی CSV و جای ردیف (ست / چالش / شماره) را در خود ردیف نگه می‌دارد تا market_price پیدایش کند."""
    for i, row in enumerate(rows, 1):
        row.setdefault("_csv_price", row["Price"])
        row["_set"], row["_challenge"], row["_row"] = e["set"], e.get("challenge", ""), i
    return rows


def _prices_doc():
    """sbc_prices.json (فقط وقتی فایل عوض شده دوباره خوانده می‌شود). None = نیست / خوانده نشد."""
    import json
    for t in range(5):
        try:
            m = os.path.getmtime(PRICES_FILE)
            if m != _prices_cache["mtime"]:
                with open(PRICES_FILE, encoding="utf-8") as f:
                    _prices_cache["doc"] = json.load(f)
                _prices_cache["mtime"] = m
            return _prices_cache["doc"]
        except FileNotFoundError:
            return None
        except (OSError, ValueError):          # همان لحظه در حال نوشتن است
            time.sleep(0.2)
    return None


def _fut_price(row):
    """ارزان‌ترین قیمت این ردیف از sbc_prices.json → (قیمت یا None، دلیل به انگلیسی برای لاگ)."""
    import datetime
    doc = _prices_doc()
    if not doc:
        return None, "no price file"
    try:
        pub = datetime.datetime.fromisoformat(doc.get("prices_published") or doc["updated"])
        age = (datetime.datetime.now() - pub).total_seconds()
    except (KeyError, ValueError, TypeError):
        return None, "bad price file"
    if age > PRICE_MAX_AGE:
        return None, f"prices are {int(age // 60)} min old"

    def same(a, b):
        return str(a or "").strip().lower() == str(b or "").strip().lower()
    for r in doc.get("rows", []):
        if same(r.get("set"), row.get("_set")) and same(r.get("challenge"), row.get("_challenge")) \
                and r.get("row") == row.get("_row"):
            if not all(same(r["filter"].get(k), row.get(k)) for k in ("Rarity", "Region", "Pos", "Club", "League")):
                return None, "CSV row changed after the last price update"
            if r.get("cheapest") is None:
                return None, "; ".join(r.get("problems") or []) or "no card on FUT.GG"
            return int(r["cheapest"]), f"FUT.GG {r['cheapest']}"
    return None, "row not in the price file"


def market_price(row):
    """قیمت شروع و سقف BUY برای این ردیف. شروع = ارزان‌ترین قیمت FUT.GG (اگر تازه باشد) وگرنه قیمت CSV.
    سقف همیشه CSV + BUY_MAX_EXTRA (یک قیمت اشتباه کوین را هدر ندهد). row["Price"] هم به‌روز می‌شود
    (فیلتر Price در SetFilters همین را می‌گذارد)."""
    csv_p = int(row.get("_csv_price", row["Price"]))
    cap = valid_price(csv_p + BUY_MAX_EXTRA)
    start, why = csv_p, "market prices off"
    if USE_MARKET_PRICES:
        fut, why = _fut_price(row)
        if fut:
            start = min(valid_price(fut), cap)
    row["Price"] = str(start)
    log(f"Price {start} ({why}; CSV {csv_p}, cap {cap})")
    return start, cap


def BUY(price, cap=None):
    """Buy Now با قیمت price. اگر کارتی نبود (صفحه‌ی Custom) یا ۳ بار خرید نشد
    (Expired / The bid / Sorry)، قیمت BUY_STEP بالاتر می‌رود (هر بار روی قیمت قبلی)،
    تا حداکثر cap (پیش‌فرض: BUY_MAX_EXTRA بالاتر از قیمت اول). True = خریده شد، NO_COINS = کوین تمام شد."""
    start, fails = price, 0
    cap = cap or start + BUY_MAX_EXTRA
    print(f"Looking for 'BuyNow' (قیمت {price})")
    for i in range(20):
        wait(100)
        if out_of_coins(price):                  # بعد از Y: Actions و کوین کمتر از قیمت
            return NO_COINS
        if on_results() or scr.see(*NO_CARDS):   # نتیجه آمد، یا کارتی نبود (پایین قیمت را بالا می‌برد)
            break
        Y()
        wait(3000)
    else:
        if not (on_results() or scr.see(*NO_CARDS)):
            print("BUY: صفحه‌ی نتیجه نیامد")
            return False
    note_coins()                                 # My Coins → پنل (Start Coin اولین بار، End Coin هر بار)

    def back_on_squad():
        """بعد از خرید، بازی بازیکن را در خانه می‌گذارد و به اسکواد برمی‌گردد (نوار پایین «A Swap  B Back»)."""
        return scr.see("Swap (5)", 33,650,151,56) or scr.see("Sub (5)", 24,680,835,30)

    confirmed = False                            # Yes زده شده و هنوز خطای خرید (Expired / The bid / Sorry) نیامده
    chosen, no_new = "", False                   # اسم کارتی که برای خرید انتخاب شد / در فهرست کارت تازه‌ای نبود

    def bought():
        print(f"Bought (قیمت {price})")
        remember_player(chosen, "bought")
        return True
    for i in range(60):                          # تا ۱۰ بار reprice + خریدها
        wait(100)
        # اول موفقیت: بعد از خرید آخرین کارت فهرست، صفحه‌ی خالی «Custom Filters» لحظه‌ای می‌آید و
        # قبلاً «no cards found» حساب می‌شد → reprice بی‌مورد و Y روی اسکواد (= Search باشگاه)
        if confirmed and back_on_squad():
            return bought()
        if out_of_coins(price):                  # مثلاً بعد از reprice یا جستجوی تازه
            return NO_COINS
        if scr.see(*NO_CARDS) or fails >= 3:
            why = "no new card in the list" if no_new else "no cards found" if fails < 3 else "3 buys failed"
            new = valid_price(price + BUY_STEP)
            if new > cap:
                print(f"BUY: {why} and the price cap was reached ({cap})")
                return False
            log(f"BUY: {why} -> price {price} to {new}")
            price, fails, no_new = new, 0, False
            # اول «کارتی پیدا نشد»: آن صفحه هم پایینش «Y Search» دارد و on_results() را True می‌کند؛
            # B آنجا بازار را می‌بندد و به اسکواد می‌برد (برای همین قبلاً reprice هیچ‌وقت انجام نمی‌شد)
            # بعد از Yes صفحه گاهی هنوز در حال عوض شدن است (نه نتیجه، نه «کارتی پیدا نشد») و هیچ دکمه‌ای
            # زده نمی‌شد → Pricing روی صفحه‌ی نتیجه دنبال فیلتر می‌گشت (D11 21:00). تا ۳ ثانیه صبر، پاپ‌آپ‌ها با A.
            for _ in range(10):
                if scr.see(*NO_CARDS) or on_results():
                    break
                if scr.see("Sorry", 430,303,90,33) or scr.see("The bid", 316,298,115,39):
                    A()
                wait(300)
            if scr.see(*NO_CARDS):
                Y()                            # از صفحه‌ی «کارتی پیدا نشد» به فیلترها
            elif on_results():
                B()                            # از صفحه‌ی نتیجه به فیلترها
            else:
                print("BUY: reprice: neither results nor no-cards page")
            wait(1000)
            if not Pricing(price):
                print(f"BUY: قیمت {price} تنظیم نشد")
                return False
            Y()                                # جستجو با قیمت تازه
            wait(2000)
            continue
        wait(300)
        if on_results():
            # به‌جای Right / Down / A: اول اسم کارت؛ تکراری (در اسکواد) یا Expired → کارت بعدی (مسیر مار)
            status, name = pick_card()
            if status == "none":                 # ۲۰ کارت دیده شد و هیچ‌کدام مناسب نبود → reprice
                no_new, fails = True, 3
                continue
            if status == "picked":
                chosen = name
        wait(300)
        if scr.see("No", 600,424,75,52):
            print("Found 'No'")
            Up()
            wait(300)
            print("Found 'Yes'")
            A()
            confirmed = True
            for _ in range(10):                  # تا حدود ۳ ثانیه (هر ۰٫۳ ثانیه): برگشت به اسکواد = خرید درست انجام شد
                wait(300)
                if back_on_squad():
                    return bought()
                if (scr.see("Expired", 278,517,60,18) or scr.see("The bid", 316,298,115,39)
                        or scr.see("Sorry", 430,303,90,33)):
                    break                        # خرید نشد: پایین‌تر fails زیاد می‌شود
        # اول Coin (2): نوار پایین همین منو هم «Change Player» دارد و شرط Change زودتر B می‌زد
        if scr.find("Coin (2)", 555,184,55,54):  # منوی دایره‌ای کارت (Quick Sell) باز است: A = فروش کارت!
            fail_shot("Quick Sell menu")
            pause_fix("BUY: card menu (Quick Sell) is open",
                      "close the card menu with B, put the screen on the search results, then press Resume")
            continue
        if scr.see("Change", 341,683,124,22):
            B()
            wait(500)
            continue

        if scr.see("Expired", 278,517,60,18):
            print("expired")
            confirmed = False
            fails += 1
            A()
            continue
        if scr.see("The bid", 316,298,115,39):
            print("Error")
            confirmed = False
            fails += 1
            A()
            wait(500)
            continue
        if scr.see("Sorry", 430,303,90,33):
            confirmed = False
            fails += 1
            A()
            continue
        if scr.see("Sub (5)", 24,680,835,30):
            return bought()
        if scr.see("Confirm (2)", 29,681,87,27):
            B()
            return bought()
        if on_results():
            continue
        else:
            Y()
            wait(2000)
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
    # صفحه‌ی Club Search فیلتر Club را هر بار ریست می‌کند → آنجا هر بار از نو (OFF لازم نیست، ریست شده).
    # در Transfer Market مثل بقیه فقط اگر عوض شده باشد (یا لیگ عوض شده باشد).
    club_again = club and not is_off(row["Club"])
    if (club_again or league_changed or changed("Club")) and not apply("Club", Club):   # با عوض شدن لیگ، باشگاه هم دوباره
        return False
    return True

def Submit(single=False, timeout=40):
    """ثبت اسکواد. True وقتی برگشت به صفحه‌ی چالش‌های همین ست (اسم ست در نوار بالا، یا V برای Marquee).
    single=True (ست تک‌چالشی، صفحه‌ی چالش ندارد): بعد از Congratulations/Claim و بیرون آمدن از اسکواد.
    تا timeout ثانیه صبر می‌کند (Store و صفحه‌ی ست با تأخیر می‌آیند)."""
    claimed, pressed, stored = False, False, False
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        wait(300)
        acted = False
        if scr.see("Submit", 1000,200,180,150) or scr.see("Submit (3)",1017,175,211,149):
            XMenu(); wait(1000); acted = pressed = True
        if scr.see("Cancel", 526,557,84,23):
            Right(); wait(1000); acted = True
        if scr.see("Submit (2)", 622,557,133,27):
            A(); wait(1000); acted = pressed = True
        if scr.see("No (2)", 612,200,55,500):
            Up(); wait(1000); acted = True
        if scr.find("Yes (2)", 609,200,59,500):
            A(); wait(1000); acted = True
        if reward_popup():
            claimed = True
            A(); wait(1000); acted = True
        if store_open() or (scr.see("Open", 33,681,65,26) and not on_sbc_hub()):
            B(); wait(1000); acted = stored = True
        if scr.see(*SET_ADVANCE):                # بعد از ۴/۴: صفحه‌ی پایان ست و پیام‌های اضافه، هر بار A
            A(); wait(1500); acted = True
        if scr.see("Open SBC", 391,598,124,30):  # صفحه‌ی Main: کادر SBC → صفحه‌ی ست‌ها
            A(); wait(1500); acted = True
        if on_set_page():
            # صفحه‌ی ست بعد از Submit لحظه‌ای می‌آید و Congratulations/Claim و Store بعدش روی آن باز می‌شوند:
            # فقط وقتی True که بعد از ۲٫۵ ثانیه (بعد از Claim و قبل از Store: ۵ ثانیه) هنوز صفحه‌ی ست است
            wait(5000 if claimed and not stored else 2500)
            if not (reward_popup() or store_open() or scr.see(*SET_ADVANCE)) and on_set_page():
                return True
            continue
        if single and claimed and not at_squad():
            return True
        if on_sbc_hub():                         # به صفحه‌ی ست‌ها برگشت (مثلاً بعد از ۴/۴): دوباره داخل ست
            if single:
                return True
            log(f"Submit: back on the SBC page, opening set {CURRENT_SET} again")
            return bool(open_set(CURRENT_SET) and wait_set_page(15))
        if not pressed and time.monotonic() - start > 5 and at_squad():
            return False        # ۵ ثانیه روی اسکواد و دکمه‌ی Submit نیامد: شرایط چالش کامل نیست
        if not acted:
            wait(700)           # صفحه‌ی بعدی (Store / صفحه‌ی ست) هنوز نیامده
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
        if scr.see("Team", 52,174,155,25) or scr.see("Swap (4)", 25,648,160,62):           # صفحه‌ی اسکواد: باز کردن منو (زیر دیالوگ هم دیده می‌شود؛ برای همین آخر)
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


# ===== تأیید دومرحله‌ای EA: انتخاب Mobile App Authenticator =====
def twofa_list():
    """لیست باز «Choose how to get your code» (تأیید دومرحله‌ای EA) را پیدا می‌کند — بدون مختصات ثابت:
    بزرگ‌ترین کادر تقریباً مشکی صفحه = لیست؛ ردیفی که زمینه‌اش خاکستری روشن‌تر است = انتخاب‌شده.
    خروجی: None اگر لیست باز نیست، وگرنه {"box": (x,y,w,h), "selected": (y0,y1) یا None,
    "mobile": y مرکز «Mobile App Authenticator» یا None}."""
    g = scr.gray
    dark = (g < 14).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(dark, 8)
    box = None
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if w >= 200 and 40 <= h <= 400 and area > 0.3 * w * h and (box is None or area > box[4]):
            box = (x, y, w, h, area)
    if box is None:
        return None
    x, y, w, h, _ = box
    inner = g[y:y + h, x + 4:x + w - 4]
    # ستون‌های بدون متن (کم‌نور) برای سنجیدن زمینه‌ی هر ردیف: میانه‌ی هر خط افقی
    prof = np.median(inner, axis=1)
    sel = None
    run = 0
    for i, v in enumerate(list(prof) + [0]):
        if v > 18:                          # زمینه‌ی ردیف انتخاب‌شده (حدود ۳۰)؛ بقیه‌ی لیست حدود ۲
            run += 1
        else:
            if run >= 12 and (sel is None or run > sel[1] - sel[0]):
                sel = (y + i - run, y + i)
            run = 0
    mobile = None
    for line in scr.read_all(x, y, w, h):
        if "mobile" in line.text.lower() or "authenticator" in line.text.lower():
            mobile = line.y
            break
    return {"box": (x, y, w, h), "selected": sel, "mobile": mobile}


def choose_mobile_app(tries=4):
    """تأیید دومرحله‌ای EA، لیست «Choose how to get your code» باز است:
    با Down پایین می‌رود تا «Mobile App Authenticator» انتخاب شود، بعد A.
    True = Mobile App انتخاب شد،  False = لیست باز نبود یا بعد از tries بار Down نرسید."""
    print("Looking for 'Mobile App Authenticator'")
    for i in range(tries + 1):
        wait(100)
        info = twofa_list()
        if info is None:
            print("2FA: the method list is not open")
            return False
        sel, mob = info["selected"], info["mobile"]
        if sel and mob is not None and sel[0] <= mob <= sel[1]:
            print("Found 'Mobile App Authenticator' (selected) -> A")
            A()
            wait(1000)
            return True
        if i < tries:
            Down()
            wait(600)
    print("2FA: Mobile App Authenticator not reached")
    return False


# ===== قاب انتخاب Xbox (هر رنگ تم) =====
def focus_rect(area, min_w=200, min_h=25, max_h=140, edge=3):
    """قاب انتخاب (focus) Xbox در ناحیه‌ی area = (x, y, w, h)، بدون وابستگی به رنگ — رنگ قاب همان
    رنگ تم (accent) پروفایل است و ممکن است سبز، آبی، نارنجی، ... باشد.
    قاب = دو خط افقی باریک و پیوسته (حداقل min_w پیکسل) که هر کدام هم با بالا و هم با پایینِ خود فرق دارند،
    هم‌رنگ هستند، و دو لبه‌ی عمودی هم‌رنگ دارند. خط‌های جداکننده‌ی کم‌نور، لبه‌ی زمینه‌ی ردیف و متن رد می‌شوند.
    خروجی: (x0, y0, x1, y1) در تصویر ریموت، یا None."""
    x0, y0, w, h = area
    a = scr.frame[y0:y0 + h, x0:x0 + w].astype(np.int16)
    if a.shape[0] < 2 * edge + 3:
        return None
    up = np.zeros_like(a); up[edge:] = a[:-edge]
    dn = np.zeros_like(a); dn[:-edge] = a[edge:]
    line = ((a.max(axis=2) > 90)
            & (np.abs(a - up).sum(axis=2) > 70)
            & (np.abs(a - dn).sum(axis=2) > 70))
    line[:edge] = False; line[-edge:] = False

    def longest_run(row):
        best = cur = 0; best_end = 0
        for i, v in enumerate(row):
            cur = cur + 1 if v else 0
            if cur > best:
                best, best_end = cur, i
        return best, best_end - best + 1, best_end

    cands = []                                   # (y, x_start, x_end, رنگ)
    for y in np.nonzero(line.sum(axis=1) >= min_w)[0]:
        n, xs, xe = longest_run(line[y])
        if n >= min_w:
            color = np.median(a[y, xs:xe + 1].reshape(-1, 3), axis=0)
            cands.append((y, xs, xe, color))
    best = None
    for i, (ty, txs, txe, tc) in enumerate(cands):
        for by, bxs, bxe, bc in cands[i + 1:]:
            if not (min_h <= by - ty <= max_h):
                continue
            if np.abs(tc - bc).sum() > 60 or abs(txs - bxs) > 12 or abs(txe - bxe) > 12:
                continue
            # لبه‌های عمودی: نزدیک دو سر خط، ستونی که در بیشتر ارتفاع همان رنگ است
            seg = a[ty:by + 1]
            same = np.abs(seg - tc).sum(axis=2) < 70
            frac = same.mean(axis=0)
            lo, hi = max(0, min(txs, bxs) - 6), min(w, max(txe, bxe) + 7)
            left = frac[lo:min(w, lo + 16)].max(initial=0)
            right = frac[max(0, hi - 16):hi].max(initial=0)
            if left >= 0.7 and right >= 0.7:
                r = (x0 + min(txs, bxs), y0 + ty, x0 + max(txe, bxe), y0 + by)
                if best is None or (r[2] - r[0]) * (r[3] - r[1]) > (best[2] - best[0]) * (best[3] - best[1]):
                    best = r
    return best


# ===== کیبورد صفحه‌ی Xbox: تایپ متن =====
# مختصات در تصویر ریموت (1280x720)، اندازه‌گیری روی عکس صفحه‌ی «Enter your code».
KB_COL_X = [353] + [round(418.5 + 49.4 * i) for i in range(10)] + [928]   # ستون ۰ = کلید چپ، ۱..۱۰ = کاراکترها، ۱۱ = کلید راست
KB_ROW_Y = [508, 545, 582, 620, 656]                                       # ردیف ۴ = Space
KB_AREA = (300, 480, 680, 220)                                             # کل کیبورد (x, y, w, h)
KB_PAGES = [                                                               # LT بین این دو صفحه جابه‌جا می‌کند
    ["1234567890", "QWERTYUIOP", "ASDFGHJKL\"", "ZXCVBNM;:!"],              # ۰: حروف و عدد
    ["!@#$%&()-_", "=+\\;:\"*/•©", "€£µ½<>[]{}", "|¦¶°~^',.?"],            # ۱: نمادها
]
KB_TOPLEFT = (308, 486, 90, 44)       # کلید بالا-چپ: «#+=» در صفحه‌ی حروف، شکلک در صفحه‌ی نمادها
# (OCR حرف‌های تکی کیبورد را نمی‌خواند؛ صفحه با تصویر نمونه‌ی KB letters / KB symbols تشخیص داده می‌شود)


def kb_focus():
    """کلیدی که قاب انتخاب رویش است: (ردیف، ستون) یا None اگر کیبورد دیده نمی‌شود.
    (رنگ قاب = رنگ تم؛ focus_rect به رنگ وابسته نیست)"""
    r = focus_rect(KB_AREA, min_w=40, min_h=25, max_h=90)
    if r is None:
        return None
    cx = (r[0] + r[2]) / 2
    cy = (r[1] + r[3]) / 2
    row = min(range(len(KB_ROW_Y)), key=lambda r: abs(KB_ROW_Y[r] - cy))
    col = min(range(len(KB_COL_X)), key=lambda c: abs(KB_COL_X[c] - cx))
    return row, col


def kb_page():
    """صفحه‌ی فعلی کیبورد: ۰ = حروف، ۱ = نمادها، None = هیچ‌کدام دیده نشد."""
    with scr.frozen():
        a = scr.find("KB letters", *KB_TOPLEFT, threshold=0).score
        b = scr.find("KB symbols", *KB_TOPLEFT, threshold=0).score
    if max(a, b) < 0.7:
        return None
    return 0 if a >= b else 1


def kb_find(ch):
    """جای یک کاراکتر: [(صفحه، ردیف، ستون), ...]. فاصله = ردیف Space."""
    if ch == " ":
        return [(p, 4, 6) for p in (0, 1)]
    out = []
    for p, rows in enumerate(KB_PAGES):
        for r, keys in enumerate(rows):
            i = keys.find(ch.upper() if p == 0 else ch)
            if i >= 0:
                out.append((p, r, i + 1))
    return out


def kb_goto(row, col, max_moves=25):
    """با جهت‌ها قاب سبز را به (row, col) می‌برد؛ بعد از هر حرکت جای قاب دوباره دیده می‌شود."""
    for _ in range(max_moves):
        wait(100)
        cur = kb_focus()
        if cur is None:
            return False
        r, c = cur
        if r == row and (c == col or (row == 4 and 1 <= c <= 10)):   # Space یک کلید پهن است
            return True
        if r != row:
            (Down if r < row else Up)()
        else:
            (Right if c < col else Left)()
        wait(250)
    return False


def type_text(text, field=None):
    """متن را با کیبورد صفحه‌ی Xbox تایپ می‌کند (حرکت قاب سبز + A).
    کاراکترهای نماد با LT به صفحه‌ی نمادها می‌روند. field = (x, y, w, h) کادر متن برای تأیید آخر کار.
    True = تایپ شد (و اگر field داده شد، متن کادر همان است)."""
    print(f"Typing {len(text)} chars")
    if kb_focus() is None:
        print("Keyboard: not visible")
        return False
    page = kb_page()
    if page is None:
        print("Keyboard: letters/symbols page not recognised")
        return False
    for ch in text:
        wait(100)
        spots = kb_find(ch)
        if not spots:
            print(f"Keyboard: {ch!r} is not on the keyboard")
            return False
        spot = next((s for s in spots if s[0] == page), spots[0])   # اول صفحه‌ی فعلی
        for _ in range(3):
            wait(100)
            if page == spot[0]:
                break
            LT()                                                     # حروف ↔ نمادها
            wait(500)
            page = kb_page()
        if page != spot[0]:
            print("Keyboard: could not switch letters/symbols page")
            return False
        if not kb_goto(spot[1], spot[2]):
            print(f"Keyboard: key {ch!r} not reached")
            return False
        A()
        wait(300)
    if field is None:
        return True
    wait(500)
    got = scr.read(*field).replace(" ", "")
    ok = got.lower() == text.replace(" ", "").lower()
    print(f"Keyboard: field shows {got!r} - {'OK' if ok else 'differs from the text'}")
    return ok


def kb_clear(n=30):
    """پاک کردن کادر: X = پاک کردن یک کاراکتر (کلید ⌫)، n بار."""
    for _ in range(n):
        wait(100)
        X()
        wait(120)


CODE_FIELD = (445, 293, 376, 46)   # کادر «Code» صفحه‌ی Enter your code


def type_code(code, tries=2):
    """کد ۶ رقمی EA را در صفحه‌ی «Enter your code» تایپ می‌کند و با خواندن کادر چک می‌کند.
    اشتباه بود → پاک و دوباره. True = کد درست در کادر است (Continue / Enter را جدا بزنید)."""
    code = str(code).strip()
    for t in range(tries):
        wait(100)
        if type_text(code, field=CODE_FIELD):
            return True
        kb_clear(len(code) + 4)
    return False


# ===== کد ۶ رقمی EA (اپ Authenticator) از ستون EAGauth اکانت =====
def totp(secret, t=None, step=30, digits=6):
    """کد TOTP (RFC 6238، SHA1) — همان عددی که اپ Authenticator نشان می‌دهد. secret = کلید base32 (EAGauth)."""
    import base64, hashlib, hmac, struct
    key = str(secret).replace(" ", "").replace("-", "").upper()
    key = base64.b32decode(key + "=" * (-len(key) % 8))
    counter = int((time.time() if t is None else t) // step)
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    n = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(n).zfill(digits)


def fresh_totp(secret, min_left=15, step=30):
    """کدی که حداقل min_left ثانیه وقت دارد (تایپ با کیبورد چند ثانیه طول می‌کشد)؛ وگرنه صبر تا کد بعدی."""
    left = step - time.time() % step
    if left < min_left:
        print(f"EA code: {left:.0f}s left, waiting for the next code")
        wait(int(left * 1000) + 300)
    return totp(secret, step=step)


def ea_account():
    """اکانتی که الان روی کنسول است (کد EA مال آن است): اکانت این دور ربات، وگرنه اکانت فعال پنل
    برای همین ریموت، وگرنه اولین اکانت کنسول."""
    acc = globals().get("CURRENT_ACCOUNT")
    if acc is not None:
        return acc
    try:
        accs = console_accounts()
        key = panel_core.get_active(CONSOLE).get("account", "")
        return next((a for a in accs if a.key() == key), None) or (accs[0] if accs else None)
    except Exception:
        return None


ENTER_CODE = ("Enter", 498,154,279,44)          # عنوان «Enter your code»


def enter_ea_code(tries=3):
    """صفحه‌ی «Enter your code»: کیبورد را باز می‌کند (A روی کادر)، کد ۶ رقمی اکانت را تایپ می‌کند،
    XMenu (Enter کیبورد) می‌زند و صبر می‌کند صفحه برود. کد اشتباه/منقضی → پاک و دوباره با کد تازه.
    True = صفحه‌ی کد رد شد."""
    acc = ea_account()
    if acc is None or not (acc.EAGauth or "").strip():
        print("EA code: no account or no EAGauth for it")
        return False
    for t in range(tries):
        wait(100)
        if kb_focus() is None:                  # کیبورد هنوز باز نیست: A روی کادر Code
            A()
            wait(1500)
        if kb_focus() is None:
            print("EA code: keyboard did not open")
            continue
        code = fresh_totp(acc.EAGauth)
        print(f"EA code for {acc.label()} (try {t + 1})")
        if not type_text(code):
            kb_clear(10)
            continue
        XMenu()                                  # کلید → (≡) کیبورد = Enter
        wait(1000)
        Down()
        wait(1000)
        A()
        wait(1000)
        if scr.until(lambda s: not s.see(*ENTER_CODE), timeout=10):
            print("EA code: accepted")
            return True
        print("EA code: page did not move on (wrong or expired code), clearing and retrying")
        kb_clear(10)
    return False


def ea_two_factor(tries=15):
    """تأیید دومرحله‌ای EA از اول تا آخر. هر دور فقط یک کار، از آخرین مرحله به اول؛
    چون عنوان «Two-factor» در همه‌ی مراحل صفحه دیده می‌شود (A روی آن با لیست باز، Email را انتخاب می‌کرد).
    True = کد وارد شد و صفحه رد شد."""
    print("Looking for 'Two-factor'")
    for j in range(tries):
        wait(100)
        if scr.see(*ENTER_CODE):                         # ۵) صفحه‌ی کد: تایپ کد + XMenu
            return enter_ea_code()
        if scr.find("Continue (3)", 590,514,108,32):      # ۴) Continue انتخاب شده
            A()
            wait(2000)
            continue
        if scr.see("Mobile (2)", 456,302,231,31):        # ۳) Mobile در کادر انتخاب شد → پایین تا Continue
            Down()
            wait(1000)
            continue
        if scr.see("Mobile", 459,403,163,31):            # ۲) لیست باز است → Mobile App
            choose_mobile_app()
            wait(1000)
            continue
        if scr.see("Two", 403,153,472,48):               # ۱) باز کردن لیست روش‌ها
            A()
            wait(1000)
            continue
        wait(1000)                                       # هیچ‌کدام: شاید صفحه هنوز لود می‌شود
    print("Two-factor: not finished")
    return False


# ===== سوئیچ اکانت روی کنسول: راهنما → Profile & system → Add or switch → Who are you? → گیمرتگ =====
GUIDE_AREA = (40, 30, 460, 690)      # ستون راهنما و لیست «Who are you?» (قاب سبز همین‌جاست)
WHO_LIST = (105, 60, 370, 660)       # اسم‌های لیست «Who are you?» (بدون ستون محو سمت چپ)


def guide_focus():
    """قاب انتخاب در راهنما و لیست «Who are you?»: (x0, y0, x1, y1) یا None.
    به رنگ وابسته نیست (رنگ قاب = رنگ تم پروفایل)."""
    return focus_rect(GUIDE_AREA, min_w=200, min_h=25, max_h=140)


def guide_open():
    """راهنمای Xbox باز است؟"""
    with scr.frozen():
        return bool(scr.see("Home", 77,135,113,45) or scr.find("X", 77,42,34,34)
                    or scr.find_text("Profile & system", 40, 100, 420, 110)
                    or scr.find_text("Who are you?", 100, 20, 380, 80))


def focus_on(y):
    """قاب سبز روی خطی با مرکز y است؟"""
    f = guide_focus()
    return bool(f and f[1] <= y <= f[3])


def who_lines():
    """خط‌های لیست «Who are you?»: [(متن، x، y)]."""
    return [(l.text, l.x, l.y) for l in scr.read_all(*WHO_LIST)]


def _gt_letters(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def who_match(text, gamertag, email=""):
    """این خط لیست مال اکانت است؟ «Chester#2832» ↔ Chester (دقیق، فقط حروف قبل از #)،
    یا خط ایمیل زیر اسم انتخاب‌شده («Chester.mand456@outlook.com»)."""
    t = text.strip()
    if email and "@" in t:
        return t.lower().replace(" ", "") == email.lower()
    name = re.split(r"[#/]", t)[0]
    return bool(_gt_letters(gamertag)) and _gt_letters(name) == _gt_letters(gamertag)


def switch_account(gamertag, email="", max_pages=12):
    """اکانت روی کنسول را عوض می‌کند: راهنما (Xbox) → RB تا «Profile & system» → «Add or switch» → A →
    در لیست «Who are you?» گیمرتگ را پیدا و انتخاب می‌کند؛ اگر نبود RT (پرش به پایین) و دوباره.
    True = انتخاب شد،  False = اکانت در لیست نیست (روی کنسول اد نشده) یا یکی از مراحل نشد."""
    print(f"Switch account -> {gamertag}")
    # ۱) راهنما
    if not guide_open():
        Xbox()
        wait(1500)
    if not scr.until(lambda s: guide_open(), timeout=4):
        print("Switch: Xbox guide did not open")
        return False
    # ۲) تب Profile & system با RB
    for _ in range(8):
        wait(100)
        if scr.find_text("Profile & system", 40, 100, 420, 110) or scr.find_text("Who are you?", 100, 20, 380, 80):
            break
        RB()
        wait(700)
    else:
        print("Switch: Profile & system tab not reached")
        return False
    # ۳) Add or switch
    for _ in range(8):
        wait(100)
        if scr.find_text("Who are you?", 100, 20, 380, 80):
            break
        m = scr.find_text("Add or switch", 40, 200, 420, 200)
        if not m:
            print("Switch: 'Add or switch' not found")
            return False
        if focus_on(m.y):
            A()
            wait(1500)
            continue
        f = guide_focus()
        (Up if f and f[1] > m.y else Down)()
        wait(500)
    if not scr.until(lambda s: s.find_text("Who are you?", 100, 20, 380, 80), timeout=5):
        print("Switch: 'Who are you?' list did not open")
        return False
    # ۴) پیدا کردن گیمرتگ در لیست؛ نبود → RT
    last = None
    for page in range(max_pages):
        wait(100)
        for _ in range(12):                       # حرکت قاب روی اسم (لیست با Down/Up اسکرول هم می‌شود)
            wait(100)
            lines = who_lines()
            hit = next((l for l in lines if who_match(l[0], gamertag, email)), None)
            if hit is None:
                break
            f = guide_focus()
            if f and f[1] <= hit[2] <= f[3]:
                print(f"Switch: found {hit[0]!r} -> A")
                A()
                wait(3000)
                return True
            (Up if f and f[1] > hit[2] else Down)()
            wait(500)
        else:
            print("Switch: could not move the focus onto the account")
            return False
        names = [l[0] for l in lines]
        at_end = any("add new" in n.lower() or "add guest" in n.lower() for n in names)
        if at_end or names == last:               # ته لیست، یا RT دیگر چیزی را عوض نکرد
            break
        last = names
        RT()                                      # پرش یک صفحه به پایین
        wait(800)
    print(f"Switch: account {gamertag} is not added on this console (not in the Who are you? list)")
    B()                                           # بستن لیست
    wait(800)
    return False


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


# ===== قطع ارتباط با سرور FUT / اینترنت → بازیابی =====
# هر جا (Transfer، Club، اسکواد، ...) ممکن است پیغامی مثل «There was a problem connecting to the Football Ultimate
# Team servers» یا «You have lost your online connection» بیاید؛ بعد از Ok بازی به صفحه‌ی اصلی Ultimate یا منوی
# اصلی FC پرت می‌شود. چک خودکار داخل wait (هر SERVER_CHECK_EVERY ثانیه): Ok، ۲ ثانیه صبر، ServerLost.
# run_plan آن را می‌گیرد: recover_to_set (از هر جا به صفحه‌ی چالش‌های ست) و همان چالش از اول (بازیکن‌های خریده‌شده
# حالا در Club هستند، پس دوباره خریده نمی‌شوند).
class ServerLost(Exception):
    """پیغام قطع ارتباط با سرور / اینترنت دیده شد (یا از Ultimate بیرون پرت شدیم)."""


SERVER_BOX = (220, 200, 840, 220)          # متن پیغام وسط صفحه
SERVER_BTN = (520, 370, 240, 170)          # دکمه‌ی روشن Ok زیر پیغام (پیش‌فیلتر ارزان، قبل از OCR)
SERVER_WORDS = ("server", "connect", "communicat", "network", "disconnect", "session", "offline",
                "login", "log in", "sign in", "signed out", "sign-in")   # Login Failed و مشابه (هنگام ورود)
SERVER_CTX = ("ultimate team", "try again", "main menu", "ea ", "online", "servers", "fail", "unable")
EXIT_FUT = ("want to exit", 300, 240, 680, 100)   # «Are you sure you want to exit Football Ultimate Team?» (No روی A)
SERVER_CHECK_EVERY = 1.5                   # ثانیه
SERVER_RETRIES = 4                         # چند بار پشت سر هم بازیابی، بعد توقف موقت
_srv = {"last": 0.0, "busy": False}
if "_xbox_wait" not in globals():          # اجرای دوباره‌ی سلول در VS Code: wait اصلی را دوباره نپوشان (حلقه‌ی بی‌پایان)
    _xbox_wait = wait                      # wait اصلی (xbox)؛ wait زیر همان است + چک پیغام قطع ارتباط


def modal_button():
    """دکمه‌ی روشن یکدست (Ok) زیر پیغام: حداقل ۸ ردیف با ۶۰ پیکسل روشن پشت سر هم.
    روی ۱۲۱۰ عکس، OCR بی‌مورد را از ۲۳۶ به ۱۳۹ رساند، بدون از دست دادن پیغام‌های واقعی."""
    b = (scr.crop(*SERVER_BTN, color=False) > 215).astype(np.int32)
    if b.shape[1] < 60:
        return False
    cs = np.concatenate([np.zeros((b.shape[0], 1), np.int32), np.cumsum(b, axis=1)], axis=1)
    run60 = (cs[:, 60:] - cs[:, :-60]).max(axis=1) >= 60
    return int(run60.sum()) >= 8               # دکمه در حال روشن شدن (کم‌نور) را چک ۱٫۵ ثانیه بعد می‌گیرد


def server_text():
    """متن پیغام قطع ارتباط، یا "" . پیغام‌های ندیده هم: کلمه‌ای مثل server / connect / network و ربط به
    Ultimate Team / EA / online / try again. روی ۱۲۱۰ عکس گزارش فقط ۱۳ پیغام واقعی قطع ارتباط را گرفت."""
    if not modal_button():
        return ""
    t = (scr.read(*SERVER_BOX, single_line=False) or "").replace("\n", " ")
    low = " " + t.lower() + " "
    if any(w in low for w in SERVER_WORDS) and any(c in low for c in SERVER_CTX):
        return t.strip()
    return ""


def check_server(force=False):
    """پیغام قطع ارتباط → Ok، ۲ ثانیه، ServerLost.  پنجره‌ی «exit Football Ultimate Team?» → No، ServerLost
    (یعنی به صفحه‌ی اصلی Ultimate پرت شده‌ایم).  حداکثر هر SERVER_CHECK_EVERY ثانیه یک بار."""
    if _srv["busy"] or "rep" not in globals():
        return
    now = time.monotonic()
    if not force and now - _srv["last"] < SERVER_CHECK_EVERY:
        return
    _srv["last"] = now
    _srv["busy"] = True
    try:
        if not modal_button():
            return
        t = server_text()
        if t:
            log(f"⚠ Connection lost: {t[:100]}")
            path = shot("server_lost")
            rep.info(f"قطع ارتباط با سرور / اینترنت: {t[:120]}" + (f"  (عکس: {rep._rel(path)})" if path else ""))
            A()
            _xbox_wait(2000)
            raise ServerLost(t[:120])
        if scr.contains(*EXIT_FUT, fuzzy=0.85):
            log("Exit Ultimate Team dialog -> No")
            A()                                   # A روی «No»
            _xbox_wait(1500)
            raise ServerLost("on the Ultimate Team home page")
    finally:
        _srv["busy"] = False


def wait(ms):
    """wait اصلی + چک پیغام قطع ارتباط (همه‌ی حلقه‌ها wait دارند، پس هر جا پیغام بیاید گرفته می‌شود)."""
    _xbox_wait(ms)
    check_server()


def where_am_i(set_name=None):
    """کجای بازی هستیم؟ squad / set / hub / fut / fc / None."""
    if at_squad():
        return "squad"
    if on_set_page(set_name):
        return "set"
    if on_sbc_hub():
        return "hub"
    if scr.see("Open SBC", 391,598,124,30) or scr.see("FUT", 29,28,42,55):
        return "fut"                              # صفحه‌ی اصلی Ultimate (یا صفحه‌ی دیگری از آن)
    if scr.see("Setting", 37,116,20,83) or scr.contains("Enter Ultimate", 360,520,240,60, fuzzy=0.85):
        return "fc"                               # منوی اصلی FC، بیرون از Ultimate
    return None


def recover_to_set(set_name, single=False):
    """بعد از قطع ارتباط: از هر جا به صفحه‌ی چالش‌های ست set_name (ست تک‌چالشی: تا باز شدن ست).
    منوی FC → FindUltimate + MainUltimate؛ صفحه‌ی اصلی Ultimate → FindSBC؛ صفحه‌ی ست‌ها → open_set.
    نشد → بازی از اول (start_game). True = رسید. ServerLost تازه از اینجا بالا می‌رود (run_plan می‌شمارد)."""
    log(f"Recover: back to set {set_name}")
    for _ in range(12):
        wait(500)
        if handle_popups():
            continue
        place = where_am_i(set_name)
        print(f"Recover: on {place or 'an unknown screen'}")
        if place == "set":
            return True
        if place == "squad":                      # هنوز داخل اسکواد چالش: بیرون، به صفحه‌ی چالش‌ها
            B()
            wait(2000)
            continue
        if place == "hub":
            return bool(open_set(set_name) and (single or wait_set_page(15)))
        if place == "fut":
            FindSBC()
            wait(1500)
            continue
        if place == "fc":
            if FindUltimate():
                MainUltimate()
            continue
        B()                                       # صفحه‌ی ناشناخته: یک قدم عقب
        wait(1500)
    log("Recover: unknown place, restarting the game")
    if start_game() is None:                      # Home → ... → FindSBC (صفحه‌ی ست‌ها)
        return bool(open_set(set_name) and (single or wait_set_page(15)))
    return False


# ===== گزارش (Report\<ریموت>.log) =====
sys.path.insert(0, r"C:\Users\Reach\Desktop\New Remote\Play")
import builtins
import xbox as _xbox
from report import Reporter
rep = Reporter(CONSOLE, REPORT_DIR)


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
    log(f"✗ {what} failed" + (f"  (shot: {os.path.basename(path)})" if path else ""))
    return False


def pause_fix(what, hint):
    """توقف موقت برای درست کردن دستی. ربات همین‌جا صبر می‌کند تا «ادامه» پنل زده شود،
    بعد همان مرحله را دوباره امتحان می‌کند.  hint = صفحه را قبل از «ادامه» کجا بگذارید.
    «توقف» پنل = تمام.  ریموت بدون توقف موقت → Abort."""
    since = rep.pause(what, hint, shot("pause_" + what))
    if not bot_pause(f"⏸ {what} failed. Fix it by hand: {hint}, then press Resume"):
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
            # «Expired» در 278,517 همان «Time Remaining: Expired» کادر کارت است: روی صفحه‌ی نتیجه پاپ‌آپ نیست
            # (وگرنه back_to_squad به‌جای B مدام A می‌زد و ربات متوقف می‌شد، D11 21:00)
            results = on_results()
            hit = next((p[0] for p in POPUPS if not (p[0] == "Expired" and results) and scr.see(*p)), None)
    if not hit:
        return False
    print(f"پاپ‌آپ {hit!r} بسته شد")
    A()
    wait(1000)
    return True


def at_squad():
    """نقطه‌ی امن: صفحه‌ی اسکواد چالش (نوار پایین Sub (2) یا Sub (5))، یا کادر Swap که enter_slot از آن شروع می‌کند."""
    with scr.frozen():
        return bool(scr.see("Swap (5)", 33,650,151,56) or scr.see("Sub (5)", 24,680,835,30)
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
    tag_rows(e, rows)
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
        pause_fix(f"Open challenge {n}", "put the screen on the challenge list")

    while not open_challenge():                 # شروع چالش (Start Challenge)
        wait(100)
        pause_fix(f"Start challenge {n}", "put the screen on the challenge squad")
    if Clear_Squad():                           # اول کار اسکواد خالی شود (بازیکن‌های مانده از قبل)
        rep.info("اسکواد اول کار پاک شد")
    else:
        fail_shot("Clear_Squad اول چالش")       # شاید اسکواد از قبل خالی بود؛ ادامه
    last_club.clear()                           # بازی در هر چالش فیلترها را ریست می‌کند
    last_market.clear()
    SQUAD_NAMES.clear()                         # اسکواد خالی: فهرست اسم بازیکن‌ها از نو

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
            log("Submit not found: clearing the squad and filling it again")
            if Clear_Squad():
                last_club.clear()
                last_market.clear()
                SQUAD_NAMES.clear()
                fill_squad(n, rows)
                continue
            fail_shot("Clear_Squad برای چیدن دوباره")
        pause_fix(f"Submit challenge {n}", "press Submit by hand or put the screen on the full squad")


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
        start, cap = market_price(row)          # قیمت تازه‌ی بازار درست قبل از جستجو
        if not SetFilters(row, last_market):
            return fail_shot("فیلترهای Market")
        bought = BUY(start, cap)
        if bought == NO_COINS:
            return NO_COINS                     # run_row اکانت را رها می‌کند
        if not bought:
            return fail_shot("BUY")
        return True

    print('Found in Club')
    name = card_name(CLUB_NAME_BOX)             # اسم بازیکن Club → فهرست اسکواد (در Market تکراری خریده نشود)
    log(f"Club player: {name or '?'}")
    if not use_club_card():
        return fail_shot("use_club_card")
    remember_player(name, "club")
    return True


def run_row(challenge, i, row):
    """یک بازیکن را تا ROW_TRIES بار خودکار امتحان می‌کند (بین تلاش‌ها برگشت به اسکواد).
    نشد → توقف موقت؛ بعد از «ادامه» همین بازیکن دوباره (رفتن به بازیکن بعدی خانه‌ی اشتباه را پر می‌کند)."""
    tag = f"[{challenge}:{i}]"
    while True:
        wait(100)
        for t in range(1, ROW_TRIES + 1):
            wait(100)
            res = do_row(row)
            if res == NO_COINS:                 # تلاش دوباره فایده ندارد: اکانت بعدی
                raise OutOfCoins(f"{tag} price {row['Price']}")
            if res:
                rep.ok("بازیکن اضافه شد" + (f" (تلاش {t})" if t > 1 else ""))
                return True
            if t < ROW_TRIES:                   # تلاش آخر «دوباره» ندارد؛ بعدش توقف موقت است
                rep.retry("بازیکن", t, ROW_TRIES)
            log(f"{tag} try {t} of {ROW_TRIES} failed, back to the squad")
            last_club.clear()                   # معلوم نیست فیلترها در چه حالی مانده‌اند: همه از نو
            last_market.clear()
            if not back_to_squad():
                break                           # به اسکواد نرسید: تلاش دیگر فایده ندارد
        pause_fix(f"{tag} player", "put the screen on the squad, on this player's slot")
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

TURN_OFF_AT_END = True      # وقتی همه‌ی اکانت‌های این کنسول تمام شد، کنسول خاموش شود (فقط اجرا از پنل)
CLOSE_REMOTE = False        # بعد از خاموش کردن کنسول True می‌شود: آخر کار پنجره‌ی ریموت بسته می‌شود
REMOTES_DIR = r"C:\Users\Reach\Desktop\New Remote\Controller\remotes"


def close_my_remote(timeout=10):
    """پنجره‌ی ریموت همین ربات را می‌بندد (WM_CLOSE، مثل بستن دستی پنجره)؛ اگر تا timeout ثانیه پروسه بسته
    نشد، TerminateProcess. بعد از خاموش کردن کنسول لازم است: وگرنه ریموت دوباره وصل می‌شود و کنسول را
    روشن می‌کند. فقط print (نه log): log از pipe همین ریموت می‌گذرد. خود ریموت هیچ تغییری نمی‌کند."""
    import ctypes, json
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    path = os.path.join(REMOTES_DIR, f"{REMOTE}.json")
    try:
        with open(path, encoding="utf-8") as f:
            info = json.load(f)
    except (OSError, ValueError) as e:
        print("close remote: no registry file:", e)
        return False
    pid, hwnd = int(info.get("pid") or 0), int(info.get("hwnd") or 0)

    def alive():
        h = kernel32.OpenProcess(0x1000, False, pid)          # QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        kernel32.CloseHandle(h)
        return bool(ok) and code.value == 259                   # STILL_ACTIVE

    if hwnd and user32.IsWindow(hwnd):
        user32.PostMessageW(hwnd, 0x0010, 0, 0)                 # WM_CLOSE
    end = time.monotonic() + timeout
    while alive() and time.monotonic() < end:
        time.sleep(0.5)
    if alive():                                                 # پنجره بسته نشد: پایان پروسه
        h = kernel32.OpenProcess(1, False, pid)                 # PROCESS_TERMINATE
        if h:
            kernel32.TerminateProcess(h, 0)
            kernel32.CloseHandle(h)
        try:
            os.remove(path)
        except OSError:
            pass
    print(f"close remote {REMOTE}: {'closed' if not alive() else 'still running'}")
    return not alive()
POWER_MENU = ("What", 81,151,491,49)   # منوی پاور («What would you like to do?») بعد از ۳ ثانیه نگه داشتن Xbox


def TurnOff(tries=10):
    """کنسول را خاموش می‌کند: ۳ ثانیه Xbox → منوی پاور → دو بار Up → A.
    True = گزینه انتخاب و A زده شد،  False = منوی پاور بعد از tries بار نیامد."""
    for i in range(tries):
        wait(100)
        if not scr.see(*POWER_MENU):
            Xbox(3000)                         # نگه داشتن دکمه‌ی Xbox ۳ ثانیه
            wait(2000)
            continue
        Up()
        wait(300)
        Up()
        wait(300)
        A()                                    # تأیید گزینه (قبلاً زده نمی‌شد: انتخاب می‌شد ولی خاموش نمی‌شد)
        wait(2000)
        return True
    return False


# ===== اکانت‌های کنسول =====
# در حالت «یک ریموت ثابت برای هر کنسول» (Pannel/core.py: SHARED_REMOTE = True) ریموت همیشه با یک اکانت باز
# است و اکانت‌های بازی روی کنسول دستی عوض می‌شوند. ربات اکانت‌های همین کنسول (ستون Console = اسم ریموت)
# را یکی‌یکی می‌رود: انتخاب دستی پنل، وگرنه هر اکانتی که SBCهایش تمام نشده. اول هر اکانت گیمرتگ Home را
# می‌خواند؛ اگر تا GAMERTAG_WAIT ثانیه آن اکانت نبود، توقف موقت با پیام «روی فلان اکانت سوئیچ کنید».
sys.path.insert(0, r"C:\Users\Reach\Desktop\New Remote\Pannel")
import core as panel_core
SHARED = panel_core.SHARED_REMOTE
GAMERTAG_BOX = (104, 54, 170, 28)   # گیمرتگ بالا-چپ Home: اندازه‌گیری 110,58,146,20 + چند پیکسل حاشیه برای OCR
GAMERTAG_WAIT = 5                   # ثانیه
AUTO_SWITCH = True                  # گیمرتگ اشتباه → اول خود ربات اکانت را عوض کند (switch_account)؛ False = فقط توقف
CURRENT_ACCOUNT = None              # اکانتی که الان باید روی کنسول باشد (None = بدون چک)


def console_accounts():
    """اکانت‌های پنل که Console آن‌ها همین ریموت است (C11، C12، ...)."""
    return panel_core.consoles(panel_core.load_accounts()).get(CONSOLE, [])


def next_bot_account(done):
    """اکانت بعدی این کنسول. انتخاب دستی پنل (منوی کارت) = فقط همان یکی؛
    Auto = اولین اکانتی که SBCهایش تمام نشده. done = کلید اکانت‌هایی که در همین اجرا رفتیم."""
    accs = console_accounts()
    pick = panel_core.load_state().get("pick", {}).get(CONSOLE)
    if pick:
        return next((a for a in accs if a.key() == pick and a.key() not in done), None)
    # Auto: skip finished accounts and accounts the bot found out of coins (panel Status: Clear to retry)
    return next((a for a in accs if a.key() not in done and not panel_core.is_complete(a.key())
                 and not panel_core.has_no_coins(a.key())), None)


def read_gamertag():
    """متن گیمرتگ بالا-چپ صفحه‌ی Home."""
    return scr.read(*GAMERTAG_BOX)


def check_account(acc):
    """تا GAMERTAG_WAIT ثانیه گیمرتگ را می‌خواند. خروجی: (درست است؟، متنی که دیده شد)."""
    seen = ""
    end = time.monotonic() + GAMERTAG_WAIT
    while True:
        seen = read_gamertag() or seen
        if panel_core.gamertag_matches(seen, acc):
            return True, seen
        if time.monotonic() >= end:
            return False, seen
        wait(500)


def ensure_account(acc=None):
    """اکانت acc (پیش‌فرض CURRENT_ACCOUNT) روی کنسول است؟ بله → در پنل ثبت می‌شود (active.json، ستون Used).
    نه → توقف موقت «روی acc سوئیچ کنید»؛ بعد از «ادامه» دوباره Home و چک. همیشه True (یا توقف از پنل)."""
    acc = acc or CURRENT_ACCOUNT
    if acc is None:
        return True
    name = acc.label()
    switched, missing = False, False
    while True:
        wait(100)
        ok, seen = check_account(acc)
        if ok:
            panel_core.set_active(acc, CONSOLE)  # پنل: این اکانت الان روی این کنسول است
            rep.ok(f"اکانت {name} روی کنسول است (گیمرتگ: {seen})")
            log(f"Account OK: {name} ({seen})")
            return True
        rep.info(f"گیمرتگ روی Home: {seen!r} — اکانت لازم: {name}")
        if AUTO_SWITCH and not switched:              # اول خود ربات سوئیچ کند (راهنما → Add or switch)
            switched = True
            log(f"Account: {seen!r} on console, switching to {name}")
            if switch_account(acc.Gamertag or name, acc.MicrosoftEmail):
                wait(3000)
                GotoHome()
                continue
            missing = True                             # در لیست Who are you? نبود
        hint = (f"could not switch to {name} ({acc.MicrosoftEmail or acc.EAEmail}) automatically - it is not in the "
                f"Who are you? list (not added) or the switch failed; add/switch it and put the screen on Home") if missing else \
               f"switch the console to {name} ({acc.MicrosoftEmail or acc.EAEmail}) and put the screen on Home"
        pause_fix(f"Account {name} on console", hint)
        switched, missing = False, False               # بعد از «ادامه» دوباره (و دوباره سوئیچ خودکار)
        GotoHome()


# مراحل شروع: (اسم، تابع، لازم است؟) — مرحله‌ی «لازم نیست» اگر نشد فقط رد می‌شود
START_STEPS = [
    ("GotoHome", GotoHome, True),
    ("CheckAccount", ensure_account, True),                        # گیمرتگ Home = اکانت این دور؟
    ("CloseRecent", CloseRecent, True),                            # بستن بازی اخیر، تا از اول باز شود
    ("find_platform", lambda: find_platform(platform()), False),   # تیک XS پنل: روشن = Ser، خاموش = One
    ("FindUltimate", FindUltimate, False),                         # اگر نشد MainUltimate خودش دوباره صدایش می‌زند
    ("MainUltimate", MainUltimate, True),
    ("ReadCoins", read_coins_step, False),                         # کوین بالا-راست → Start Coin پنل
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
            try:
                if fn():
                    continue
            except ServerLost as x:             # قطع ارتباط وسط شروع: این دور نشد، دور بعد از FindUltimate
                rep.info(f"{name}: قطع ارتباط — {x}")
                fail_shot(name)
                break
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
        fu = next(i for i, st in enumerate(START_STEPS) if st[0] == "FindUltimate")
        start = fu if k > fu else 0             # بعد از باز شدن بازی: از FindUltimate؛ وگرنه از Home
    return k


def run_plan(manual_first=False):
    """همه‌ی SBCهای فعال پنل برای اکانتی که الان روی کنسول است.
    manual_first: تست دستی، صفحه‌ی چالش‌های ست اول از قبل باز است."""
    global CURRENT_SET
    plan = load_plan()                          # SBCهای فعال پنل، گروه‌شده بر اساس ست
    log("Plan: " + ", ".join(f"{name} ({len(es)})" for name, es in plan))
    for k, (set_name, entries) in enumerate(plan):
        wait(100)
        rep.ctx(challenge=set_name, row=None)
        CURRENT_SET = set_name
        single = all(is_single(e) for e in entries)
        opened = k == 0 and manual_first        # تست دستی: صفحه‌ی چالش‌های ست اول از قبل باز است
        recovered = False                       # بعد از بازیابی به صفحه‌ی ست رسیدیم: back_to_sbc لازم نیست
        lost, i, need_recover = 0, 0, False
        while i < len(entries):
            wait(100)
            try:
                if need_recover:                # بعد از قطع ارتباط: از هر جا به صفحه‌ی ست (اگر خودش قطع شد، دوباره)
                    need_recover = False
                    SQUAD_NAMES.clear()
                    last_club.clear()
                    last_market.clear()
                    opened = recovered = recover_to_set(set_name, single)
                    if not opened:
                        raise ServerLost(f"could not get back to the set {set_name}")
                if not opened:
                    if k > 0 and not recovered:     # بار اول FindSBC همین الان صفحه‌ی SBC را باز کرده
                        while not back_to_sbc():
                            pause_fix("back to SBC", "put the screen on the SBC page")
                    while not (open_set(set_name) and (single or wait_set_page(15))):
                        # ست باز نشد، یا صفحه‌ای که باز شد مال این ست نیست (اسمش در نوار بالا نیست)
                        pause_fix(f"open set {set_name}", "open the set by hand (its challenge page)")
                    opened = True
                    log(f"Set {set_name}: {len(entries)} challenge(s)")
                run_challenge(entries[i])
                i += 1
                lost = 0
            except ServerLost as x:             # قطع ارتباط: برگشت به صفحه‌ی ست و همین چالش از اول
                lost += 1
                rep.info(f"قطع ارتباط ({lost}/{SERVER_RETRIES}): برگشت به ست {set_name} و چالش از اول — {x}")
                log(f"Connection lost ({lost}/{SERVER_RETRIES}): recovering to {set_name}")
                if lost > SERVER_RETRIES:       # چند بار پشت سر هم: توقف موقت تا شما درست کنید
                    try:
                        pause_fix("Server connection lost",
                                  f"wait until the game is online again, open the set {set_name} (its challenge page)")
                    except ServerLost:
                        pass
                    lost = 0
                    opened = recovered = on_set_page(set_name)
                    need_recover = not opened       # صفحه‌ی ست نیست: بازیابی خودکار از همان‌جا
                    continue
                need_recover = True             # دور بعد: recover_to_set و همین چالش از اول
    rep.ctx(challenge=None, row=None, step=None)


def open_game():
    """مراحل شروع (Home → چک اکانت → بستن بازی → باز کردن → SBC)، با توقف موقت هر جا نشد."""
    failed = start_game()
    while failed is not None:
        wait(100)
        name = START_STEPS[failed][0]
        pause_fix(f"Start game ({name})", f"put the screen where {name} starts")
        failed = start_game(tries=1, start=failed)   # بعد از «ادامه» از همان مرحله


rep.start(f"START_GAME={START_GAME}  SHARED={SHARED}")
status = "ناتمام"
try:
    accounts_mode = SHARED and bool(console_accounts())   # از VS Code (ریموت XBOX) یا حالت قبلی: بدون اکانت
    if SHARED and not accounts_mode:
        log(f"No panel accounts for console {CONSOLE}: running without account check")
    done_accounts, first, ran, no_coins, skipped = [], True, [], [], []
    while True:
        wait(100)
        acc = next_bot_account(done_accounts) if accounts_mode else None
        if accounts_mode and acc is None:
            break                               # اکانتی نمانده (یا انتخاب دستی انجام شد)
        CURRENT_ACCOUNT = acc
        rep.ctx(account=acc.label() if acc else None, challenge=None, row=None, step=None)
        if acc:
            log(f"===== Account: {acc.label()} ({acc.MicrosoftEmail}) =====")
        try:
            if START_GAME or not first:
                open_game()                     # بعد از اکانت اول همیشه از Home (سوئیچ دستی اکانت)
            elif acc:
                panel_core.set_active(acc, CONSOLE)  # تست دستی: گیمرتگ قابل چک نیست، همین اکانت فرض می‌شود
            run_plan(manual_first=first and not START_GAME)
        except AccountSkip as e:                # مثلاً Limit Reached: این اکانت روی این کنسول نمی‌شود
            name = acc.label() if acc else "(no account)"
            path = shot("account_skip")
            rep.event("✗", "اکانت رد شد", f"اکانت {name} رد شد: {e}",
                      [f"عکس: {rep._rel(path)}" if path else ""], recent=True)
            rep.panel_error(f"Account skipped: {e}", "error")
            log(f"✗ Account skipped: {name} ({e}) - moving to the next account")
            skipped.append(name)
            if acc is None:
                break
            done_accounts.append(acc.key())
            first = False
            continue
        except OutOfCoins as e:                 # کوین تمام شد: این اکانت رها، اکانت بعدی
            name = acc.label() if acc else "(no account)"
            path = shot("no_coins")
            rep.event("✗", "کوین تمام", f"کوین اکانت {name} تمام شد؛ بقیه‌ی SBCهای این اکانت رد شد ({e})",
                      [f"عکس: {rep._rel(path)}" if path else ""], recent=True)
            log(f"✗ Out of coins: {name} ({e}) - moving to the next account")
            no_coins.append(name)
            rep.no_coins(acc.key() if acc else None, str(e))   # panel: Status "Last error" + Auto skips it
            if acc is None:
                break
            finish_coins(acc)                   # panel End Coin
            done_accounts.append(acc.key())
            first = False
            continue
        if acc is None:
            break
        finish_coins(acc)                       # panel End Coin
        done_accounts.append(acc.key())
        ran.append(acc.label())
        rep.ok(f"اکانت {acc.label()} تمام شد")
        log(f"✓ Account done: {acc.label()}")
        first = False
    rep.ctx(account=None, challenge=None, row=None, step=None)
    if accounts_mode and not ran and not no_coins and not skipped:
        log(f"Nothing to run on {CONSOLE}: every account is complete")
        status = "✓ همه‌ی اکانت‌ها از قبل کامل بودند"
    else:
        log("✓ All challenges done" + (f" ({', '.join(ran)})" if ran else "")
            + (f" | out of coins: {', '.join(no_coins)}" if no_coins else ""))
        status = ("✓ همه‌ی چالش‌ها تمام شد" + (f" — اکانت‌ها: {', '.join(ran)}" if ran else "")
                  + (f" — کوین تمام: {', '.join(no_coins)}" if no_coins else "")
                  + (f" — رد شد: {', '.join(skipped)}" if skipped else ""))
    if accounts_mode and TURN_OFF_AT_END:       # همه‌ی اکانت‌ها تمام شد (نه توقف / خطا): خاموش کردن کنسول
        log(f"All accounts done on {CONSOLE}: turning the console off")
        rep.info("همه‌ی اکانت‌ها تمام شد: خاموش کردن کنسول")
        try:
            if TurnOff():
                status += " — کنسول خاموش شد"
                CLOSE_REMOTE = True
            else:
                log("Turn off: power menu not found")
                rep.info("خاموش کردن کنسول نشد: منوی پاور نیامد")
        except RemoteDown:                      # با خاموش شدن کنسول ریموت قطع می‌شود: یعنی خاموش شد
            status += " — کنسول خاموش شد"
            CLOSE_REMOTE = True
        except ServerLost:                      # پیغام قطع ارتباط هنگام خاموش کردن: مهم نیست
            pass
        if CLOSE_REMOTE:
            log("Console off: closing the remote window")   # آخرین log: بعد از این ریموت بسته می‌شود
except Abort as e:
    rep.stopped(f"ربات متوقف شد (توقف موقت ممکن نبود): {e}", en=f"Bot stopped: {e}")
    shot("Abort")
    log(f"✗ Bot stopped: {e}")
    status = f"✗ Abort: {e}"
except BotStopped:
    rep.stopped("«توقف» از پنل")
    status = "■ توقف از پنل"
    raise
except RemoteDown as e:
    rep.stopped(f"ریموت وصل نشد: {e}", en=f"Remote down: {e}")
    status = "✗ ریموت قطع"
    raise
except Exception as e:                          # باگ کد: کامل در گزارش
    rep.crash(e)
    shot("crash")
    status = f"‼ خطای کد: {type(e).__name__}"
    raise
finally:
    if CURRENT_ACCOUNT is not None and CURRENT_ACCOUNT.key() not in globals().get("done_accounts", ()):
        finish_coins(CURRENT_ACCOUNT)           # stopped mid-account: End Coin = last coins seen
    rep.end(status)
    if CLOSE_REMOTE:                            # کنسول خاموش شد: ریموت را ببند تا دوباره وصل نشود و روشنش نکند
        close_my_remote()



