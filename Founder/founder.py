# -*- coding: utf-8 -*-
"""
founder.py — پیدا کردن تصویر و خواندن متن روی تصویر ریموت ایکس‌باکس (xbrp)

نسخه‌ی بازنویسی‌شده‌ی Pfind / Pfind2 / ReadText از پروژه‌ی Transfer.

    from founder import Remote, Screen

    scr = Screen(Remote("XBOX"))            # تصویر را از ریموت xbrp می‌گیرد (1280x720)
    scr.grab()                              # یک فریم تازه
    if scr.find("Cancel", 850, 600, 200, 200):          # مثل Pfind
        ...
    ok, x, y = scr.find("UTCoin", 1400, 60, 200, 50)     # مثل Pfind2
    text = scr.read(316, 71, 140, 40)                   # مثل ReadText
    coins = scr.read_number(1420, 60, 150, 40)          # عدد (int) یا None

همه‌ی مختصات (x, y, w, h) هستند: گوشه‌ی بالا-چپ، عرض، ارتفاع.
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import re
from difflib import SequenceMatcher
import threading
import time
from contextlib import contextmanager
from typing import Iterable, Optional, Sequence

import cv2
import numpy as np

import functools
import hashlib
from collections import OrderedDict
import sys as _sys

# کنترل ربات از پنل ریموت (لاگ، شروع/توقف موقت/توقف، اتصال دوباره) — در پوشه‌ی Controller
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Controller"))
try:
    from remotectl import Control, BotStopped, RemoteDown
    try:
        from remotectl import input_seq
    except ImportError:      # remotectl قدیمی
        def input_seq():
            return 0
except ImportError:          # بدون remotectl: همه‌چیز مثل قبل
    Control = None

    def input_seq():
        return 0

    class BotStopped(Exception):
        pass

    class RemoteDown(Exception):
        pass

__all__ = [
    "Match", "Remote", "FileSource", "ArraySource", "Screen", "Templates",
    "WindowsOcr", "TesseractOcr", "make_ocr", "BotStopped", "RemoteDown",
]

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATES = os.path.join(HERE, "Templates")
DEFAULT_REMOTES = r"C:\Users\Reach\Desktop\New Remote\Controller\remotes"
TESSERACT_EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# =====================================================================
# Match — نتیجه‌ی جستجو
#   if m:            → پیدا شد یا نه (مثل Pfind)
#   ok, x, y = m     → مثل Pfind2 (x, y = مرکز تصویر پیدا شده)
# =====================================================================
class Match:
    __slots__ = ("found", "x", "y", "score", "left", "top", "w", "h", "name", "text", "by")

    def __init__(self, found=False, x=None, y=None, score=0.0,
                 left=None, top=None, w=0, h=0, name="", text=""):
        self.found, self.x, self.y, self.score = found, x, y, score
        self.left, self.top, self.w, self.h = left, top, w, h
        self.name, self.text = name, text
        self.by = ""   # "image" یا "text": با کدام پیدا شد (فقط در see)

    def __bool__(self):
        return self.found

    def __iter__(self):  # ok, x, y = scr.find(...)
        return iter((self.found, self.x, self.y))

    @property
    def rect(self):
        return (self.left, self.top, self.w, self.h)

    def __repr__(self):
        if not self.found:
            return f"Match(not found, best={self.score:.3f} {self.name})"
        return (f"Match({self.name or self.text!r} at ({self.x},{self.y}) "
                f"score={self.score:.3f} rect={self.rect})")


NOT_FOUND = Match()


# =====================================================================
# منبع تصویر
# =====================================================================
class Remote:
    """اتصال به ریموت xbrp از طریق named pipe همان کنسول.

    snap()  → فریم BGR با اندازه‌ی واقعی استریم (1280x720)
    send()  → هر دستور هاب (press a, stick L 0 1, ...) و جواب آن
    اتصال باز می‌ماند و اگر قطع شد خودش دوباره وصل می‌شود.
    """

    def __init__(self, console: str = "XBOX", remotes_dir: str = DEFAULT_REMOTES,
                 snap_dir: Optional[str] = None):
        self.console = console
        self.remotes_dir = remotes_dir
        self.pipe = self._find_pipe() or rf"\\.\pipe\xbrp-{console}"
        snap_dir = snap_dir or os.environ.get("TEMP") or HERE
        self.snap_path = os.path.join(snap_dir, f"founder-{console}-{os.getpid()}.png")
        self._f = None
        self._lock = threading.Lock()
        self.control = Control(self.send) if Control else None   # لاگ/توقف/سلامت از پنل ریموت

    @staticmethod
    def _pid_alive(pid) -> bool:
        if not pid:
            return True
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE

    def _find_pipe(self) -> Optional[str]:
        """pipe of the running remote with this name, else the newest running remote of this console.

        A remote opened again while this program still held the old connection gets another name
        (XBOX-2, XBOX-3, ...), so the name alone is not enough.
        """
        want = self.console.lower()
        exact, same = None, []
        for path in glob.glob(os.path.join(self.remotes_dir, "*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    info = json.load(f)
            except (OSError, ValueError):
                continue
            if not info.get("pipe") or not self._pid_alive(info.get("pid")):
                continue
            name = (info.get("name") or os.path.splitext(os.path.basename(path))[0]).lower()
            if name == want:
                exact = info
            elif (info.get("console") or "").lower() == want or name.startswith(want + "-"):
                same.append(info)
        if exact:
            return exact["pipe"]
        if same:
            return max(same, key=lambda i: i.get("started", ""))["pipe"]
        return None

    def _open(self):
        if self._f is None:
            self._f = open(self.pipe, "r+b", buffering=0)
        return self._f

    def close(self):
        with self._lock:
            if self._f is not None:
                try:
                    self._f.close()
                finally:
                    self._f = None

    def send(self, command: str) -> str:
        """یک دستور می‌فرستد و جواب یک‌خطی را برمی‌گرداند ("ok ..." یا "err ...")."""
        data = (command.strip() + "\n").encode("utf-8")
        with self._lock:
            for attempt in (1, 2):
                try:
                    f = self._open()
                    f.write(data)
                    return f.read(4096).decode("utf-8", "replace").strip()
                except OSError:
                    if self._f is not None:
                        try:
                            self._f.close()
                        except OSError:
                            pass
                        self._f = None
                    # the remote may have been opened again under another pipe name
                    self.pipe = self._find_pipe() or self.pipe
                    if attempt == 2:
                        raise ConnectionError(
                            f"ریموت {self.console} در دسترس نیست ({self.pipe}). xbrp باز است؟")
        return ""

    def press(self, buttons: str, ms: Optional[int] = None) -> str:
        return self.send(f"press {buttons}" + (f" {ms}" if ms else ""))

    def snap(self) -> np.ndarray:
        reply = self.send(f"snap {self.snap_path}")
        tries = 0
        while not reply.startswith("ok") and self.control and tries < 3:
            # تصویر نرسید: سلامت ریموت را چک کن (صبر / اتصال دوباره) و دوباره بگیر
            tries += 1
            self.control.log(f"✗ No picture ({tries}/3)")
            self.control.check_bot()
            self.control.check_health()
            reply = self.send(f"snap {self.snap_path}")
        if not reply.startswith("ok"):
            raise RuntimeError(f"snap failed: {reply}")
        img = cv2.imread(self.snap_path, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError(f"snap file not readable: {self.snap_path}")
        return img

    __call__ = snap


class FileSource:
    """برای تست بدون ریموت: هر بار همان عکس (یا عکس‌های پوشه به ترتیب)."""

    def __init__(self, path_or_glob: str, loop: bool = True):
        self.files = sorted(glob.glob(path_or_glob)) or [path_or_glob]
        self.i, self.loop = 0, loop

    def __call__(self) -> np.ndarray:
        path = self.files[min(self.i, len(self.files) - 1)]
        self.i = (self.i + 1) % len(self.files) if self.loop else self.i + 1
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            raise FileNotFoundError(path)
        return img


class ArraySource:
    """فریم را خودتان می‌دهید (مثلاً از منبع دیگر): src.frame = ndarray"""

    def __init__(self, frame: Optional[np.ndarray] = None):
        self.frame = frame

    def __call__(self) -> np.ndarray:
        if self.frame is None:
            raise RuntimeError("ArraySource has no frame")
        return self.frame


# =====================================================================
# Templates — کش تصویرها (یک بار از دیسک، thread-safe، با هر مقیاس)
# =====================================================================
class Templates:
    def __init__(self, folder: str = DEFAULT_TEMPLATES):
        self.folder = folder
        self._cache: dict = {}
        self._lock = threading.Lock()

    def path(self, name: str) -> str:
        if os.path.isabs(name) or os.path.exists(name):
            return name
        p = os.path.join(self.folder, name)
        return p if os.path.splitext(p)[1] else p + ".png"

    def get(self, name: str, scale: float = 1.0, color: bool = False):
        """(تصویر, ماسک یا None) — ماسک فقط وقتی PNG پیکسل شفاف دارد."""
        key = (name, round(scale, 4), color)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                return hit
            raw = cv2.imread(self.path(name), cv2.IMREAD_UNCHANGED)
            if raw is None:
                raise FileNotFoundError(f"template not found: {self.path(name)}")
            mask = None
            if raw.ndim == 3 and raw.shape[2] == 4:
                if raw[:, :, 3].min() < 255:
                    mask = raw[:, :, 3]
                raw = raw[:, :, :3]
            if raw.ndim == 2:
                img = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR) if color else raw
            else:
                img = raw if color else cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
            if scale != 1.0:
                interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
                img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=interp)
                if mask is not None:
                    mask = cv2.resize(mask, (img.shape[1], img.shape[0]),
                                      interpolation=cv2.INTER_NEAREST)
            if mask is not None:
                mask = (mask > 127).astype(np.uint8) * 255
                if color:
                    mask = cv2.merge([mask, mask, mask])
            hit = (img, mask)
            self._cache[key] = hit
            return hit

    def has(self, name: str) -> bool:
        """آیا فایل تصویر نمونه وجود دارد؟"""
        return os.path.exists(self.path(name))

    def names(self) -> list:
        return sorted(os.path.splitext(os.path.basename(p))[0]
                      for p in glob.glob(os.path.join(self.folder, "*.png")))


# =====================================================================
# OCR
# =====================================================================
def _prep_for_ocr(gray: np.ndarray, binarize: bool, min_height: int) -> np.ndarray:
    """بزرگ کردن ناحیه‌های کوچک + (اختیاری) سیاه‌وسفید با متن تیره روی زمینه‌ی روشن."""
    h = gray.shape[0]
    if h and h < min_height:
        f = min(4.0, min_height / h)
        gray = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    if binarize:
        gray = cv2.bilateralFilter(gray, 9, 75, 75)
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # متن معمولاً کمتر از نصف ناحیه است؛ اگر بیشتر پیکسل‌ها سیاه است، زمینه تیره است → برعکس کن
        if np.count_nonzero(th) < th.size / 2:
            th = cv2.bitwise_not(th)
        gray = th
    # حاشیه‌ی سفید کمک می‌کند حروف لبه بریده نشوند
    border = int(gray[0, 0]) if gray.size else 255
    return cv2.copyMakeBorder(gray, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=border)


def _text_rows(gray: np.ndarray, pad: int = 3) -> list:
    """ردیف‌های متن یک ناحیه (بالا، پایین) با نگاه به پیکسل‌های روشن/تیره‌ی هر سطر."""
    if gray.shape[0] < 2:
        return [(0, gray.shape[0])]
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.count_nonzero(th) > th.size / 2:          # متن = رنگ کمتر
        th = cv2.bitwise_not(th)
    ink = np.count_nonzero(th, axis=1) > max(1, gray.shape[1] // 40)
    rows, top = [], None
    for i, on in enumerate(list(ink) + [False]):
        if on and top is None:
            top = i
        elif not on and top is not None:
            if rows and top - rows[-1][1] <= 2:     # فاصله‌ی خیلی کم = همان ردیف
                rows[-1] = (rows[-1][0], i)
            else:
                rows.append((top, i))
            top = None
    rows = [(t, b) for t, b in rows if b - t >= 5]  # خط‌های نازک زمینه نه
    H = gray.shape[0]
    return [(max(0, t - pad), min(H, b + pad)) for t, b in rows]


class WindowsOcr:
    """OCR داخلی ویندوز (Windows.Media.Ocr). حدود 2–12 ms برای هر ناحیه، بدون فرایند جدا.
    برای هر thread موتور جدا ساخته می‌شود، پس چند ربات هم‌زمان مشکلی ندارند."""

    name = "windows"

    def __init__(self, language: str = "en-US"):
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat
        from winrt.windows.storage.streams import DataWriter
        self._OcrEngine, self._Language = OcrEngine, Language
        self._SB, self._PF, self._DW = SoftwareBitmap, BitmapPixelFormat, DataWriter
        self.language = language
        if OcrEngine.try_create_from_language(Language(language)) is None:
            raise RuntimeError(f"Windows OCR language {language} is not installed")
        self._tls = threading.local()

    def _engine(self):
        t = self._tls
        if getattr(t, "engine", None) is None:
            t.engine = self._OcrEngine.try_create_from_language(self._Language(self.language))
            t.loop = asyncio.new_event_loop()
        return t.engine, t.loop

    def _bitmap(self, gray: np.ndarray):
        bgra = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGRA)
        dw = self._DW()
        dw.write_bytes(bgra.tobytes())
        return self._SB.create_copy_from_buffer(dw.detach_buffer(), self._PF.BGRA8,
                                                bgra.shape[1], bgra.shape[0])

    def lines(self, gray: np.ndarray):
        """[(متن خط, [(کلمه, x, y, w, h), ...]), ...] — مختصات نسبت به همین تصویر."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return self._lines(gray)
        # Jupyter / VS Code Interactive already runs an event loop in this thread:
        # do the OCR on our own worker thread (it has its own engine and loop).
        if getattr(self, "_worker", None) is None:
            from concurrent.futures import ThreadPoolExecutor
            self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="founder-ocr")
        return self._worker.submit(self._lines, gray).result()

    def _lines(self, gray: np.ndarray):
        engine, loop = self._engine()
        bmp = self._bitmap(np.ascontiguousarray(gray))

        async def run():
            return await engine.recognize_async(bmp)

        res = loop.run_until_complete(run())
        out = []
        for line in res.lines:
            words = []
            for w in line.words:
                r = w.bounding_rect
                words.append((w.text, r.x, r.y, r.width, r.height))
            out.append((line.text, words))
        return out

    def text(self, gray: np.ndarray, single_line: bool = True) -> str:
        lines = [t for t, _ in self.lines(gray)]
        return (" " if single_line else "\n").join(lines).strip()


class TesseractOcr:
    """همان روش قبلی (pytesseract). هر خواندن یک tesseract.exe اجرا می‌کند (~90 ms).
    هر فراخوانی فایل موقت جدا دارد، پس قفل سراسری لازم نیست."""

    name = "tesseract"

    def __init__(self, exe: str = TESSERACT_EXE, lang: str = "eng"):
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = exe
        self._pt, self.lang = pytesseract, lang

    def text(self, gray: np.ndarray, single_line: bool = True, whitelist: Optional[str] = None) -> str:
        cfg = "--oem 3 --psm " + ("7" if single_line else "6")
        if whitelist:
            cfg += f" -c tessedit_char_whitelist={whitelist}"
        return self._pt.image_to_string(gray, lang=self.lang, config=cfg).strip()

    def lines(self, gray: np.ndarray):
        d = self._pt.image_to_data(gray, lang=self.lang, config="--oem 3 --psm 11",
                                   output_type=self._pt.Output.DICT)
        groups: dict = {}
        for i, word in enumerate(d["text"]):
            if word.strip() and float(d["conf"][i]) > 0:
                key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
                groups.setdefault(key, []).append(
                    (word, d["left"][i], d["top"][i], d["width"][i], d["height"][i]))
        return [(" ".join(w[0] for w in ws), ws) for _, ws in sorted(groups.items())]


def make_ocr(kind: str = "auto"):
    """"auto" = اول OCR ویندوز، اگر نبود Tesseract."""
    if kind in ("auto", "windows"):
        try:
            return WindowsOcr()
        except Exception:
            if kind == "windows":
                raise
    return TesseractOcr()


# ---- مصرف CPU ----
MAX_AGE = 0.3       # فریم تا این‌قدر (ثانیه) دوباره استفاده می‌شود؛ بعد از هر دکمه همیشه فریم تازه
POLL = 0.25         # فاصله‌ی نگاه کردن در wait / wait_see / wait_gone / until (قبلاً 0.1)
OCR_CACHE = 512     # تعداد نتیجه‌ی OCR که برای ناحیه‌های عوض‌نشده نگه داشته می‌شود

# حد شباهت پیش‌فرض see / wait_see / wait_gone
SEE_IMAGE = 0.90   # تصویر (۰ تا ۱)
SEE_TEXT = 0.95    # متن، بعد از یکی کردن حروف شبیه (q=g، 0=o، ...)

# اصلاح اشتباه‌های رایج OCR وقتی فقط عدد می‌خواهیم
_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "I": "1", "l": "1",
                            "|": "1", "!": "1", "i": "1", "S": "5", "s": "5", "B": "8",
                            "Z": "2", "z": "2", "G": "6", "g": "9", "q": "9", "T": "7"})


# حروفی که OCR با هم اشتباه می‌گیرد؛ برای مقایسه‌ی متن یکی می‌شوند
_LOOKALIKE = str.maketrans({"q": "g", "0": "o", "1": "l", "i": "l", "|": "l", "!": "l",
                            "5": "s", "8": "b", "$": "s", "’": "'", "`": "'"})


def _norm_text(t: str) -> str:
    t = t.lower().replace("rn", "m").replace("vv", "w").translate(_LOOKALIKE)
    t = re.sub(r"[^\w' ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _base_name(name: str) -> str:
    """اسم تصویر بدون شماره‌ی تکراری ویندوز: "ANY (2)" → "ANY"، "Sub (10)" → "Sub"."""
    return re.sub(r"\s*\(\d+\)$", "", name.strip()) or name


def text_match(want: str, got: str, fuzzy: float = 0.8) -> float:
    """امتیاز 0 تا 1 که want چقدر در got دیده می‌شود (با تحمل اشتباه‌های OCR)."""
    w, g = _norm_text(want), _norm_text(got)
    if not w:
        return 0.0
    if w in g:
        return 1.0
    if fuzzy >= 1.0:
        return 0.0
    best, n = 0.0, len(w)
    for L in (n - 1, n, n + 1):
        if L <= 0:
            continue
        for k in range(0, max(1, len(g) - L + 1)):
            r = SequenceMatcher(None, w, g[k:k + L]).ratio()
            if r > best:
                best = r
    return best


# =====================================================================
# Screen — همه‌ی توابع پیدا کردن و خواندن
# =====================================================================
class Screen:
    """
    source     : Remote("XBOX") یا FileSource(...) یا هر تابعی که فریم BGR بدهد
    templates  : پوشه‌ی تصویرها (پیش‌فرض Founder/Templates)
    ref        : اندازه‌ی مرجعی که مختصات و تصویرها با آن گرفته شده‌اند، مثلاً (1920, 1080)
                 برای کدهای قدیمی Transfer. None یعنی همان اندازه‌ی فریم (1280x720).
    max_age    : اگر فریم فعلی از این قدیمی‌تر باشد (ثانیه)، خودکار فریم تازه گرفته می‌شود.
    ocr        : "auto" | "windows" | "tesseract" | یک شیء OCR
    """

    def __init__(self, source, templates: str | Templates = DEFAULT_TEMPLATES,
                 ref: Optional[Sequence[int]] = None, max_age: float = MAX_AGE,
                 ocr="auto", threshold: float = 0.8):
        self.source = source
        self.templates = templates if isinstance(templates, Templates) else Templates(templates)
        self.ref = tuple(ref) if ref else None
        self.max_age = max_age
        self.threshold = threshold
        self._ocr_kind = ocr
        self._ocr = None if isinstance(ocr, str) else ocr
        self._tess = None          # Tesseract کمکی برای read_number
        self._lock = threading.RLock()
        self._bgr = None
        self._gray = None
        self._t = 0.0
        self._frozen = 0
        self._seq = -1             # شماره‌ی دکمه‌ی آخر هنگام گرفتن فریم
        self._cache = OrderedDict()   # نتیجه‌ی OCR بر اساس پیکسل‌های ناحیه
        self._ctl = getattr(source, "control", None) or getattr(getattr(source, "__self__", None), "control", None)
        self._act = threading.local()   # عمق صدا زدن (فقط بیرونی‌ترین کار لاگ می‌شود)

    # ---------------- فریم ----------------
    def grab(self) -> np.ndarray:
        """یک فریم تازه از منبع می‌گیرد و برمی‌گرداند (BGR)."""
        seq = input_seq()          # قبل از گرفتن: دکمه‌ای که وسط گرفتن زده شود، فریم بعدی را تازه می‌کند
        img = self.source()
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        elif img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        with self._lock:
            self._bgr, self._gray, self._t, self._seq = img, None, time.monotonic(), seq
        return img

    def set_frame(self, img: np.ndarray):
        """فریمی که از جای دیگر دارید را مستقیم بدهید."""
        with self._lock:
            self._bgr = img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            self._gray, self._t = None, time.monotonic()

    def _ensure(self):
        if self._bgr is None or (not self._frozen and (
                time.monotonic() - self._t > self.max_age or input_seq() != self._seq)):
            self.grab()

    def _cached(self, kind, gray, extra, compute):
        """نتیجه‌ی OCR برای همین پیکسل‌ها، اگر قبلاً حساب شده. ناحیه‌ای که عوض نشده دوباره خوانده نمی‌شود."""
        h = hashlib.blake2b(np.ascontiguousarray(gray).data, digest_size=16)
        h.update(repr((kind, gray.shape, extra)).encode())
        key = h.digest()
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            return hit[0]
        r = compute()
        self._cache[key] = (r,)
        if len(self._cache) > OCR_CACHE:
            self._cache.popitem(last=False)
        return r

    @property
    def frame(self) -> np.ndarray:
        with self._lock:
            self._ensure()
            return self._bgr

    @property
    def gray(self) -> np.ndarray:
        with self._lock:
            self._ensure()
            if self._gray is None:
                self._gray = cv2.cvtColor(self._bgr, cv2.COLOR_BGR2GRAY)
            return self._gray

    @contextmanager
    def frozen(self, fresh: bool = True):
        """همه‌ی بررسی‌های داخل این بلوک روی یک فریم انجام می‌شوند (سریع و هم‌زمان).

            with scr.frozen():
                if scr.find("Cancel", ...): ...
                elif "Home" in scr.read(...): ...
        """
        with self._lock:
            if fresh:
                self.grab()
            self._frozen += 1
        try:
            yield self
        finally:
            with self._lock:
                self._frozen -= 1

    # ---------------- مقیاس و ناحیه ----------------
    @property
    def scale(self) -> float:
        if not self.ref:
            return 1.0
        return self.frame.shape[1] / float(self.ref[0])

    def _region(self, x, y, w, h, img):
        """ناحیه از مختصات مرجع به مختصات فریم + بریدن به اندازه‌ی تصویر."""
        s = self.scale
        H, W = img.shape[:2]
        if w is None:
            x0, y0, x1, y1 = 0, 0, W, H
        else:
            x0, y0 = int(round(x * s)), int(round(y * s))
            x1, y1 = int(round((x + w) * s)), int(round((y + h) * s))
            x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
        return x0, y0, x1, y1

    def _to_ref(self, v):
        s = self.scale
        return int(round(v / s)) if s != 1.0 else int(v)

    def crop(self, x=None, y=None, w=None, h=None, color: bool = True) -> np.ndarray:
        img = self.frame if color else self.gray
        x0, y0, x1, y1 = self._region(x, y, w, h, img)
        return img[y0:y1, x0:x1]

    # ---------------- پیدا کردن تصویر ----------------
    def _match_map(self, name, x, y, w, h, color):
        with self._lock:
            img = self.frame if color else self.gray
        tpl, mask = self.templates.get(name, self.scale, color)
        x0, y0, x1, y1 = self._region(x, y, w, h, img)
        region = img[y0:y1, x0:x1]
        th, tw = tpl.shape[:2]
        if th > region.shape[0] or tw > region.shape[1] or th == 0 or tw == 0:
            return None, (x0, y0, tw, th)
        if mask is not None:
            res = cv2.matchTemplate(region, tpl, cv2.TM_CCOEFF_NORMED, mask=mask)
            res = np.nan_to_num(res, nan=-1.0, posinf=-1.0, neginf=-1.0)
        else:
            res = cv2.matchTemplate(region, tpl, cv2.TM_CCOEFF_NORMED)
        return res, (x0, y0, tw, th)

    def _make_match(self, name, score, lx, ly, x0, y0, tw, th, found):
        left, top = x0 + lx, y0 + ly
        return Match(found, self._to_ref(left + tw / 2), self._to_ref(top + th / 2), float(score),
                     self._to_ref(left), self._to_ref(top), self._to_ref(tw), self._to_ref(th), name)

    def find(self, name: str, x=None, y=None, w=None, h=None,
             threshold: Optional[float] = None, color: bool = False) -> Match:
        """بهترین جای تصویر name در ناحیه (x, y, w, h). بدون ناحیه = کل صفحه.

        if scr.find("Cancel", 850, 600, 200, 200): ...      ← مثل Pfind
        ok, X, Y = scr.find("UTCoin", 1400, 60, 200, 50)    ← مثل Pfind2
        m.score امتیاز شباهت است (0 تا 1).
        color=True وقتی فرق دو حالت فقط در رنگ است (کمی کندتر).
        """
        threshold = self.threshold if threshold is None else threshold
        res, (x0, y0, tw, th) = self._match_map(name, x, y, w, h, color)
        if res is None:
            return Match(name=name)
        _, best, _, loc = cv2.minMaxLoc(res)
        if best < threshold:
            return Match(score=float(best), name=name)
        return self._make_match(name, best, loc[0], loc[1], x0, y0, tw, th, True)

    def exists(self, name, x=None, y=None, w=None, h=None, threshold=None, color=False) -> bool:
        return bool(self.find(name, x, y, w, h, threshold, color))

    def find_all(self, name: str, x=None, y=None, w=None, h=None,
                 threshold: Optional[float] = None, color: bool = False,
                 max_results: int = 50) -> list:
        """همه‌ی جاهایی که تصویر هست (مثلاً همه‌ی کارت‌های یک لیست)، از بالا-چپ مرتب شده."""
        threshold = self.threshold if threshold is None else threshold
        res, (x0, y0, tw, th) = self._match_map(name, x, y, w, h, color)
        if res is None:
            return []
        out = []
        res = res.copy()
        for _ in range(max_results):
            _, best, _, loc = cv2.minMaxLoc(res)
            if best < threshold:
                break
            out.append(self._make_match(name, best, loc[0], loc[1], x0, y0, tw, th, True))
            # اطراف این مورد را پاک کن تا دوباره پیدا نشود
            lx, ly = loc
            res[max(0, ly - th // 2):ly + th // 2 + 1, max(0, lx - tw // 2):lx + tw // 2 + 1] = -1
        out.sort(key=lambda m: (m.top, m.left))
        return out

    def find_any(self, names: Iterable[str], x=None, y=None, w=None, h=None,
                 threshold: Optional[float] = None, color: bool = False) -> Match:
        """از چند تصویر، آن که بیشترین شباهت را دارد (m.name می‌گوید کدام)."""
        best = Match()
        for n in names:
            m = self.find(n, x, y, w, h, threshold, color)
            if m.score > best.score or (m and not best):
                best = m
        return best

    def wait(self, name: str, x=None, y=None, w=None, h=None, timeout: float = 10.0,
             interval: float = POLL, threshold: Optional[float] = None, color: bool = False,
             stop=None) -> Match:
        """صبر تا تصویر ظاهر شود. اگر نشد Match خالی برمی‌گرداند.
        stop: تابعی که اگر True برگرداند صبر قطع می‌شود (مثل stop_flag ربات)."""
        end = time.monotonic() + timeout
        while True:
            self.grab()
            m = self.find(name, x, y, w, h, threshold, color)
            if m or time.monotonic() >= end or (stop and stop()):
                return m
            time.sleep(interval)

    def wait_gone(self, name: str, x=None, y=None, w=None, h=None, timeout: float = 10.0,
                  interval: float = POLL, threshold: Optional[float] = None, stop=None,
                  text=None) -> bool:
        """صبر تا تصویر/متن name برود. مثل see: اگر تصویر نمونه نبود، متن را نگاه می‌کند."""
        end = time.monotonic() + timeout
        while True:
            self.grab()
            if not self.see(name, x, y, w, h, text, threshold):
                return True
            if time.monotonic() >= end or (stop and stop()):
                return False
            time.sleep(interval)

    # ---------------- خواندن متن ----------------
    @property
    def ocr(self):
        if self._ocr is None:
            self._ocr = make_ocr(self._ocr_kind)
        return self._ocr

    def read(self, x=None, y=None, w=None, h=None, whitelist: Optional[str] = None,
             single_line: bool = True, binarize: Optional[bool] = None) -> str:
        """متن داخل ناحیه. whitelist فقط این حروف را نگه می‌دارد (مثلاً "0123456789,").
        binarize: None = خودکار (Tesseract بله، ویندوز نه)."""
        gray = self.crop(x, y, w, h, color=False)
        if gray.size == 0:
            return ""
        ocr = self.ocr
        if binarize is None:
            binarize = ocr.name == "tesseract"

        def compute():
            img = _prep_for_ocr(gray, binarize, 40 if ocr.name == "windows" else 90)
            if ocr.name == "tesseract":
                return ocr.text(img, single_line, whitelist)
            return ocr.text(img, single_line)

        text = self._cached("read", gray, (ocr.name, binarize, single_line, whitelist), compute)
        if whitelist:
            text = "".join(c for c in text if c in whitelist)
        return text

    def read_number(self, x=None, y=None, w=None, h=None, default=None):
        """عدد ناحیه (int). "15,000" → 15000. اگر عددی نبود default.
        اگر ناحیه چند ردیف عدد زیر هم دارد، لیست عددها برمی‌گردد (ردیف ناخوانا = default):
            scr.read_number(139,243,47,176)  → [64, 63, 63, 65, 64, 27, 64]
        اول OCR ویندوز؛ اگر عددی ندید، Tesseract (ویندوز عددهای کوتاه تنها را اغلب نمی‌بیند)."""
        gray = self.crop(x, y, w, h, color=False)
        if gray.size == 0:
            return default
        rows = _text_rows(gray)
        if len(rows) <= 1:
            n = self._number_in(gray)
            return default if n is None else n
        out = []
        for top, bot in rows:
            n = self._number_in(gray[top:bot])
            out.append(default if n is None else n)
        return out

    def _number_in(self, gray: np.ndarray):
        """اولین عدد یک تکه‌ی خاکستری یک‌خطی، یا None."""
        return self._cached("number", gray, self.ocr.name, lambda: self._number_in_raw(gray))

    def _number_in_raw(self, gray: np.ndarray):
        engines = [self.ocr]
        if self.ocr.name != "tesseract":
            try:
                if self._tess is None:
                    self._tess = TesseractOcr()
                engines.append(self._tess)
            except Exception:
                pass
        for ocr in engines:
            tess = ocr.name == "tesseract"
            img = _prep_for_ocr(gray, tess, 90 if tess else 40)
            text = ocr.text(img, True)
            for token in text.split():
                if any(c.isdigit() for c in token):
                    digits = re.sub(r"\D", "", token.translate(_DIGIT_FIX))
                    if digits:
                        return int(digits)
        return None

    def contains(self, text: str, x=None, y=None, w=None, h=None, case: bool = False,
                 fuzzy: float = 1.0) -> bool:
        """آیا متن در ناحیه هست؟  ('Home' in ReadText(...) قدیمی)
        fuzzy: تحمل اشتباه OCR (q به‌جای g و ...). 1.0 = دقیقاً همان متن. case=True حساس به حروف بزرگ."""
        got = self.read(x, y, w, h)
        if case:
            return text in got
        return text_match(text, got, fuzzy) >= fuzzy

    def _words(self, x, y, w, h):
        """کلمه‌های ناحیه با مختصات فریم: [(متن خط, [(کلمه, L, T, W, H), ...]), ...]"""
        gray = self.crop(x, y, w, h, color=False)
        if gray.size == 0:
            return []
        x0, y0, _, _ = self._region(x, y, w, h, self.gray)
        ocr = self.ocr
        f = 1.0
        min_h = 40 if ocr.name == "windows" else 90
        if gray.shape[0] < min_h:
            f = min(4.0, min_h / gray.shape[0])
        lines = self._cached("words", gray, ocr.name,
                             lambda: ocr.lines(_prep_for_ocr(gray, ocr.name == "tesseract", min_h)))
        pad = 8
        out = []
        for line, words in lines:
            ws = [(t, x0 + (l - pad) / f, y0 + (tp - pad) / f, ww / f, hh / f)
                  for t, l, tp, ww, hh in words]
            out.append((line, ws))
        return out

    def _box(self, group, text, score=1.0):
        L = min(g[1] for g in group); T = min(g[2] for g in group)
        R = max(g[1] + g[3] for g in group); B = max(g[2] + g[4] for g in group)
        return Match(True, self._to_ref((L + R) / 2), self._to_ref((T + B) / 2), score,
                     self._to_ref(L), self._to_ref(T), self._to_ref(R - L), self._to_ref(B - T),
                     text=text)

    def find_text(self, text: str, x=None, y=None, w=None, h=None, case: bool = False,
                  fuzzy: float = 0.8) -> Match:
        """جای یک کلمه/عبارت را روی صفحه پیدا می‌کند (بدون تصویر نمونه).
        m.x, m.y = مرکز متن، m.score = شباهت. fuzzy مثل contains."""
        n = max(1, len(text.split()))
        best = Match(text=text)
        for _, words in self._words(x, y, w, h):
            for size in (n, n + 1, n - 1):
                if size < 1:
                    continue
                for i in range(len(words) - size + 1):
                    group = words[i:i + size]
                    phrase = " ".join(g[0] for g in group)
                    if case:
                        sc = 1.0 if text in phrase else 0.0
                    else:
                        sc = text_match(text, phrase, fuzzy)
                    if sc >= fuzzy and sc > best.score:
                        best = self._box(group, phrase, sc)
                        if sc == 1.0:
                            return best
        return best

    def read_all(self, x=None, y=None, w=None, h=None) -> list:
        """همه‌ی خط‌های متن ناحیه با جایشان: [Match(text=..., x, y, ...), ...]"""
        return [self._box(words, line) for line, words in self._words(x, y, w, h) if words]

    # ---------------- هر دو: تصویر یا متن ----------------
    def see(self, name: str, x=None, y=None, w=None, h=None, text=None,
            threshold: Optional[float] = None, color: bool = False, fuzzy: float = SEE_TEXT) -> Match:
        """اگر تصویر نمونه‌ی name پیدا شد، یا متن در ناحیه خوانده شد، جواب می‌دهد.

        scr.see("Cancel", x,y,w,h)                    ← تصویر Cancel.png یا کلمه‌ی "Cancel"
        scr.see("BuyNow", x,y,w,h, text="Buy Now")    ← متن با اسم تصویر فرق دارد
        scr.see("Home", x,y,w,h, text=["Home", "خانه"])  ← هر کدام از چند متن
        scr.see("Coin", x,y,w,h, text=False)          ← فقط تصویر
        scr.see("27 XBOX Series", ..., fuzzy=1.0)     ← متن دقیق (26 با 27 قاطی نشود)
        scr.see("ANY (2)", x,y,w,h)                   ← تصویر "ANY (2).png" یا کلمه‌ی "ANY" (شماره حذف می‌شود)

        اول تصویر گشته می‌شود (سریع‌تر)، اگر نبود یا پیدا نشد متن.
        خروجی Match است: در if درست/غلط، ok, X, Y = ... مرکز، و m.by = "image" یا "text"."""
        best = Match(name=name)
        with self._lock:
            self._ensure()          # فریم کهنه را تازه کن (داخل frozen بیرونی دست نمی‌زند)
        with self.frozen(fresh=False):
            if self.templates.has(name):
                m = self.find(name, x, y, w, h, SEE_IMAGE if threshold is None else threshold, color)
                if m:
                    m.by = "image"
                    return m
                best = m
            if text is False:
                return best
            # "ANY (2)" → "ANY": شماره‌ی تکراری فقط مال اسم فایل تصویر است، نه متن روی صفحه
            words = [_base_name(name)] if text is None else ([text] if isinstance(text, str) else list(text))
            for word in words:
                m = self.find_text(word, x, y, w, h, fuzzy=fuzzy)
                if m:
                    m.name, m.by = name, "text"
                    return m
        return best

    def wait_see(self, name: str, x=None, y=None, w=None, h=None, text=None,
                 timeout: float = 10.0, interval: float = POLL, threshold: Optional[float] = None,
                 stop=None, fuzzy: float = SEE_TEXT) -> Match:
        """صبر تا see درست شود (تصویر یا متن). اگر نشد Match خالی."""
        return self.until(lambda s: s.see(name, x, y, w, h, text, threshold, fuzzy=fuzzy),
                          timeout, interval, stop) or Match(name=name)

    # ---------------- هوشمند: صبر و تکرار ----------------
    def until(self, check, timeout: float = 10.0, interval: float = POLL, stop=None):
        """check(scr) را روی فریم تازه تکرار می‌کند تا مقدار درست بدهد. همان مقدار را برمی‌گرداند،
        یا None اگر وقت تمام شد."""
        end = time.monotonic() + timeout
        while True:
            if self._ctl:
                self._ctl.check_bot()       # توقف / توقف موقت از پنل، وسط صبرهای طولانی هم
            self.grab()
            r = check(self)
            if r:
                return r
            if time.monotonic() >= end or (stop and stop()):
                return None
            time.sleep(interval)

    def wait_text(self, text: str, x=None, y=None, w=None, h=None, timeout: float = 10.0,
                  interval: float = POLL, stop=None) -> bool:
        """صبر تا کلمه در ناحیه دیده شود."""
        return bool(self.until(lambda s: s.contains(text, x, y, w, h), timeout, interval, stop))

    def wait_change(self, x=None, y=None, w=None, h=None, timeout: float = 3.0,
                    percent: float = 4.0, diff: int = 12, before: Optional[np.ndarray] = None) -> bool:
        """صبر تا ناحیه عوض شود. برای فهمیدن اینکه دکمه اثر کرد.
        before را قبل از زدن دکمه بگیرید: b = scr.snapshot(...)؛ بدون آن، فریم فعلی مبنا است."""
        if before is None:
            before = self.snapshot(x, y, w, h)
        return bool(self.until(lambda s: s.changed(before, x, y, w, h, diff, percent),
                               timeout, 0.03))

    def wait_stable(self, x=None, y=None, w=None, h=None, still: float = 0.3,
                    timeout: float = 5.0, percent: float = 1.0) -> bool:
        """صبر تا انیمیشن تمام شود: ناحیه به مدت still ثانیه تقریباً ثابت بماند."""
        end = time.monotonic() + timeout
        self.grab()
        last, since = self.snapshot(x, y, w, h), time.monotonic()
        while time.monotonic() < end:
            time.sleep(0.05)
            self.grab()
            if self.changed(last, x, y, w, h, percent=percent):
                last, since = self.snapshot(x, y, w, h), time.monotonic()
            elif time.monotonic() - since >= still:
                return True
        return False

    def act_until(self, action, check, tries: int = 10, delay: float = 0.4, stop=None):
        """action() را تکرار می‌کند تا check(scr) درست شود. برای حرکت در منو:
            scr.act_until(Down, lambda s: s.contains("Transfer", ...))
        نتیجه‌ی check را برمی‌گرداند، یا None اگر بعد از tries بار نشد."""
        for _ in range(tries):
            self.grab()
            r = check(self)
            if r:
                return r
            if stop and stop():
                return None
            action()
            time.sleep(delay)
        self.grab()
        return check(self) or None

    def detect(self, rules, default: str = ""):
        """تشخیص صفحه‌ی فعلی روی یک فریم. rules = [(اسم, check), ...] به ترتیب اولویت.
        check یکی از این‌هاست:
            "Cancel"                         → تصویر روی کل صفحه
            ("Cancel", x, y, w, h)           → تصویر در ناحیه
            ("text:Home", x, y, w, h)        → کلمه در ناحیه
            ("see:Cancel", x, y, w, h)       → تصویر یا کلمه (see)
            lambda s: ...                    → هر شرط دلخواه
        اسم اولین قانونی که درست باشد برمی‌گردد."""
        with self.frozen():
            for name, chk in rules:
                if self._rule(chk):
                    return name
        return default

    def _rule(self, chk) -> bool:
        if callable(chk):
            return bool(chk(self))
        if isinstance(chk, str):
            chk = (chk,)
        key, region = chk[0], tuple(chk[1:5])
        if key.startswith("text:"):
            return self.contains(key[5:], *region)
        if key.startswith("see:"):
            return bool(self.see(key[4:], *region))
        return bool(self.find(key, *region))

    def snapshot(self, x=None, y=None, w=None, h=None) -> np.ndarray:
        """کپی خاکستری ناحیه برای مقایسه‌ی بعدی با changed / wait_change."""
        return self.crop(x, y, w, h, color=False).copy()

    def is_blank(self, x=None, y=None, w=None, h=None, spread: float = 8.0) -> bool:
        """آیا ناحیه یکدست است؟ (صفحه‌ی سیاه، لودینگ، قطع تصویر)"""
        g = self.crop(x, y, w, h, color=False)
        return g.size == 0 or float(g.std()) < spread

    # ---------------- رنگ ----------------
    def pixel(self, x, y):
        """رنگ یک نقطه (B, G, R)."""
        s = self.scale
        b, g, r = self.frame[int(round(y * s)), int(round(x * s))]
        return int(b), int(g), int(r)

    def color_near(self, x, y, bgr, tol: int = 30) -> bool:
        return all(abs(a - b) <= tol for a, b in zip(self.pixel(x, y), bgr))

    def changed(self, before: np.ndarray, x=None, y=None, w=None, h=None, diff: int = 12,
                percent: float = 4.0) -> bool:
        """آیا ناحیه نسبت به crop قبلی (scr.crop(..., color=False)) عوض شده؟"""
        now = self.crop(x, y, w, h, color=False)
        if now.shape != before.shape:
            return True
        d = cv2.absdiff(now, before)
        return np.count_nonzero(d > diff) * 100.0 / max(1, d.size) >= percent

    # ---------------- ابزار ----------------
    def save_template(self, name: str, x, y, w, h) -> str:
        """تکه‌ای از فریم فعلی را به‌عنوان تصویر نمونه ذخیره می‌کند (Templates/name.png).
        بهترین راه ساختن تصویر نمونه: دقیقاً همان پیکسل‌های استریم، بدون پنل و بدون بزرگ‌نمایی پنجره.
        نکته: با ref تنظیم‌شده، مختصات مرجع است ولی تصویر در اندازه‌ی واقعی فریم ذخیره می‌شود؛
        پس تصویرهای نو را با Screen بدون ref استفاده کنید."""
        img = self.crop(x, y, w, h, color=True)
        path = self.templates.path(name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cv2.imwrite(path, img)
        return path

    def save(self, path: str = "frame.png") -> str:
        cv2.imwrite(path, self.frame)
        return path

    # ---------------- نام‌های قدیمی (کد Transfer بدون تغییر کار کند) ----------------
    def Pfind(self, template_name, x, y, w, h, threshold=0.7) -> bool:
        return bool(self.find(template_name, x, y, w, h, threshold))

    def Pfind2(self, template_name, x, y, w, h, threshold=0.7):
        return tuple(self.find(template_name, x, y, w, h, threshold))

    def ReadText(self, x, y, w, h, whitelist=None) -> str:
        return self.read(x, y, w, h, whitelist)


# ---------------- لاگ و کنترل از پنل ریموت ----------------
def _short(v, n=40):
    v = " ".join(str(v).split())
    return v if len(v) <= n else v[:n - 1] + "…"


def _describe(kind, args, kw, r):
    """یک خط لاگ برای پنل: کار، ورودی و نتیجه."""
    name = args[0] if args else kw.get("name", kw.get("text", ""))
    if kind in ("see", "find", "wait", "wait_see", "find_text", "contains", "wait_text"):
        label = {"see": "See", "find": "Image", "wait": "Wait image", "wait_see": "Wait",
                 "find_text": "Text", "contains": "Text", "wait_text": "Wait text"}[kind]
        return f"{label} {_short(name, 30)} → {'✓' if r else '✗'}"
    if kind == "wait_gone":
        return f"Wait gone {_short(name, 30)} → {'✓' if r else '✗'}"
    if kind == "find_any":
        return f"Images {_short(','.join(map(str, name)), 30)} → {getattr(r, 'name', '') if r else '✗'}"
    if kind == "find_all":
        return f"All {_short(name, 30)} → {len(r)}"
    if kind == "read":
        return f"Read {tuple(args[:4])} → {_short(repr(r))}"
    if kind == "read_number":
        return f"Number {tuple(args[:4])} → {_short(r)}"
    if kind == "read_all":
        return f"Read all → {len(r)} lines"
    return kind


def _controlled(kind, fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kw):
        ctl = self._ctl
        depth = getattr(self._act, "depth", 0)
        if ctl is None or depth:
            return fn(self, *args, **kw)
        self._act.depth = 1
        try:
            ctl.checkpoint()                 # توقف / توقف موقت / سلامت ریموت
            r = fn(self, *args, **kw)
        finally:
            self._act.depth = 0
        try:
            ctl.log(_describe(kind, args, kw, r))
        except Exception:
            pass
        return r
    return wrapper


for _name in ("see", "find", "find_all", "find_any", "wait", "wait_gone", "wait_see", "wait_text",
              "read", "read_number", "read_all", "contains", "find_text"):
    setattr(Screen, _name, _controlled(_name, getattr(Screen, _name)))
del _name

