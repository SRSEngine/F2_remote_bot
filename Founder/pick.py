# -*- coding: utf-8 -*-
"""
pick.py — گرفتن مختصات از روی تصویر خود ریموت (نه صفحه‌ی کامپیوتر)

    python pick.py            ریموت XBOX
    python pick.py TEST       ریموت دیگر
    python pick.py --file frame.png   روی یک عکس ذخیره‌شده

تصویر استریم در اندازه‌ی واقعی (1280x720) نشان داده می‌شود. مهم نیست پنجره‌ی ریموت کجای صفحه
یا چه اندازه‌ای باشد. عددهایی که این ابزار می‌دهد همان عددهایی است که به scr.find / scr.read می‌دهید.

موس:  حرکت = مختصات و رنگ نقطه در عنوان پنجره
       کشیدن = انتخاب ناحیه → x, y, w, h + متن خوانده‌شده در ترمینال، و کپی در کلیپ‌بورد
کلید:  Space یا R = فریم تازه      L = زنده (هر ۰٫۳ ثانیه فریم تازه)
       S = ذخیره‌ی ناحیه به‌عنوان تصویر نمونه (Templates\اسم.png)
       F = امتحان: آن تصویر نمونه در همین ناحیه پیدا می‌شود؟
       Q یا Esc = خروج
"""
import os
import sys
import time

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from founder import FileSource, Remote, Screen  # noqa: E402

WIN = "Founder pick"

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def copy_to_clipboard(text: str):
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
    except Exception:
        pass


def ask_name(default: str) -> str:
    try:
        import tkinter as tk
        from tkinter import simpledialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        name = simpledialog.askstring("Founder", "اسم تصویر نمونه:", initialvalue=default, parent=root)
        root.destroy()
        return (name or "").strip()
    except Exception:
        return input("اسم تصویر نمونه: ").strip()


def describe(scr: Screen, rect) -> str:
    x, y, w, h = rect
    text = scr.read(x, y, w, h)
    num = scr.read_number(x, y, w, h)
    lines = [f"ناحیه:  {x}, {y}, {w}, {h}",
             f"متن:    {text!r}"]
    if num is not None:
        lines.append(f"عدد:    {num}")
    lines.append(f"نمونه:  scr.read({x}, {y}, {w}, {h})   scr.find(\"Name\", {x}, {y}, {w}, {h})")
    return "\n".join(lines)


class Picker:
    def __init__(self, scr: Screen, label: str):
        self.scr, self.label = scr, label
        self.start = None
        self.rect = None        # (x, y, w, h) انتخاب نهایی
        self.drag = None        # مستطیل در حال کشیدن
        self.mouse = (0, 0)
        self.live = False
        self.last_template = None
        self.found = None

    def refresh(self):
        self.scr.grab()
        self.found = None

    def on_mouse(self, event, x, y, flags, _):
        H, W = self.scr.frame.shape[:2]
        x, y = max(0, min(W - 1, x)), max(0, min(H - 1, y))
        self.mouse = (x, y)
        if event == cv2.EVENT_LBUTTONDOWN:
            self.start, self.drag = (x, y), None
        elif event == cv2.EVENT_MOUSEMOVE and self.start:
            self.drag = self._norm(self.start, (x, y))
        elif event == cv2.EVENT_LBUTTONUP and self.start:
            r = self._norm(self.start, (x, y))
            self.start, self.drag = None, None
            if r[2] >= 3 and r[3] >= 3:
                self.rect, self.found = r, None
                copy_to_clipboard(f"{r[0]}, {r[1]}, {r[2]}, {r[3]}")
                print("\n" + describe(self.scr, r) + "\n(در کلیپ‌بورد کپی شد)")

    @staticmethod
    def _norm(a, b):
        x0, y0 = min(a[0], b[0]), min(a[1], b[1])
        return (x0, y0, abs(a[0] - b[0]), abs(a[1] - b[1]))

    def draw(self):
        img = self.scr.frame.copy()
        if self.rect:
            x, y, w, h = self.rect
            cv2.rectangle(img, (x, y), (x + w, y + h), (255, 200, 0), 2)
            cv2.putText(img, f"{x},{y},{w},{h}", (x, max(14, y - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (255, 200, 0), 1, cv2.LINE_AA)
        if self.found is not None:
            m = self.found
            color = (0, 220, 0) if m else (0, 0, 255)
            if m:
                cv2.rectangle(img, (m.left, m.top), (m.left + m.w, m.top + m.h), color, 2)
            cv2.putText(img, f"{self.last_template}: {m.score:.3f}", (10, img.shape[0] - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
        if self.drag:
            x, y, w, h = self.drag
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 255), 1)
        mx, my = self.mouse
        b, g, r = self.scr.frame[my, mx]
        live = "  LIVE" if self.live else ""
        cv2.setWindowTitle(WIN, f"{self.label}  x={mx} y={my}  BGR=({b},{g},{r}){live}"
                                f"   [Space=new  L=live  S=save  F=test  Q=quit]")
        cv2.imshow(WIN, img)

    def save(self):
        if not self.rect:
            print("اول یک ناحیه بکشید.")
            return
        name = ask_name(self.last_template or "")
        if not name:
            return
        path = self.scr.save_template(name, *self.rect)
        self.scr.templates._cache.clear()
        self.last_template = name
        print(f"ذخیره شد: {path}")

    def test(self):
        if not self.last_template:
            print("اول با S یک تصویر نمونه ذخیره کنید.")
            return
        region = self.rect or (None, None, None, None)
        # کمی بزرگ‌تر از تصویر، مثل استفاده‌ی واقعی
        if self.rect:
            x, y, w, h = self.rect
            region = (x - 40, y - 40, w + 80, h + 80)
        self.found = self.scr.find(self.last_template, *region, threshold=0.0)
        print(f"{self.last_template}: {self.found}")

    def run(self):
        cv2.namedWindow(WIN, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(WIN, self.on_mouse)
        last = time.monotonic()
        while True:
            if self.live and time.monotonic() - last > 0.3:
                self.refresh()
                last = time.monotonic()
            self.draw()
            k = cv2.waitKey(30) & 0xFF
            if k in (ord("q"), ord("Q"), 27):
                break
            if cv2.getWindowProperty(WIN, cv2.WND_PROP_VISIBLE) < 1:
                break
            if k in (ord(" "), ord("r"), ord("R")):
                self.refresh()
            elif k in (ord("l"), ord("L")):
                self.live = not self.live
            elif k in (ord("s"), ord("S")):
                self.save()
            elif k in (ord("f"), ord("F")):
                self.test()
        cv2.destroyAllWindows()


def main(argv):
    if len(argv) > 1 and argv[0] == "--file":
        src, label = FileSource(argv[1]), os.path.basename(argv[1])
    else:
        console = argv[0] if argv else "XBOX"
        src, label = Remote(console), console
    scr = Screen(src, max_age=1e9)   # فریم فقط با Space/L عوض می‌شود
    try:
        scr.grab()
    except Exception as e:
        print(f"تصویر گرفته نشد: {e}")
        return 1
    print(__doc__)
    Picker(scr, label).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
