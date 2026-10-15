# -*- coding: utf-8 -*-
r"""
report.py — گزارش خطاها و توقف‌های ربات، برای هر ریموت یک فایل جدا.

    Report\<ریموت>.log          متن ساده (UTF-8)، هر اجرا با یک خط ════ شروع می‌شود
    Report\shots\<ریموت>\       عکس صفحه در لحظه‌ی هر خطا / توقف

هر خط: ساعت، نوع، «کجا» (چالش › بازیکن › مرحله)، و توضیح.
برای خطا و توقف، چند خط آخری که ربات چاپ کرده بود هم نوشته می‌شود تا معلوم باشد
داخل کدام تابع (مثلاً pick یا Pricing) گیر کرد.

    rep = Reporter("XBOX", r"...\Report")
    rep.start()
    rep.ctx(challenge=1, row="3/11 (Bronze | England | GK ...)")
    rep.fail("SetFilters", shot_path)       # ✗
    rep.retry("بازیکن", 2, 3)              # ↻
    t = rep.pause("…"); rep.resumed(t)      # ⏸ / ▶
    rep.ok("چالش 1 تمام شد")                # ✓
    rep.end("تمام شد")
"""
import collections
import os
import re
import time
import traceback

MAX_BYTES = 2 * 1024 * 1024      # فایل بزرگ‌تر شد → <ریموت>.old.log و فایل تازه
RECENT_LINES = 12                # چند خط آخر چاپ‌شده که کنار هر خطا نوشته می‌شود
IND = " " * 10                   # تورفتگی خط‌های توضیح زیر هر رویداد


class Reporter:
    def __init__(self, remote, folder):
        self.remote = remote
        self.folder = folder
        self.path = os.path.join(folder, f"{_safe(remote) or 'remote'}.log")
        self.shots = os.path.join(folder, "shots", _safe(remote) or "remote")
        self.recent = collections.deque(maxlen=RECENT_LINES)
        self.where = {}          # challenge / row / step
        self.counts = collections.Counter()
        self.t0 = None
        self.n_shots = 0

    # ---------- پایه ----------
    def _write(self, text):
        try:
            os.makedirs(self.folder, exist_ok=True)
            if os.path.exists(self.path) and os.path.getsize(self.path) > MAX_BYTES:
                old = self.path[:-4] + ".old.log"
                if os.path.exists(old):
                    os.remove(old)
                os.replace(self.path, old)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(text.rstrip("\n") + "\n")
        except OSError as e:                     # گزارش نباید ربات را بخواباند
            print("گزارش نوشته نشد:", e)

    def remember(self, line):
        """یک خط از خروجی ربات (print / log) برای «آخرین کارها»."""
        line = " ".join(str(line).split())
        if line:
            self.recent.append(time.strftime("%H:%M:%S ") + line[:200])

    def ctx(self, **kw):
        """«کجا» را عوض می‌کند. مقدار None آن قسمت را پاک می‌کند."""
        for k, v in kw.items():
            if v is None:
                self.where.pop(k, None)
            else:
                self.where[k] = v

    def place(self):
        parts = []
        if "account" in self.where:
            parts.append(f"اکانت {self.where['account']}")
        if "step" in self.where and "challenge" not in self.where:
            parts.append(f"شروع بازی › {self.where['step']}")
        if "challenge" in self.where:
            parts.append(f"چالش {self.where['challenge']}")
        if "row" in self.where:
            parts.append(f"بازیکن {self.where['row']}")
        return " › ".join(parts) or "-"

    def event(self, mark, kind, text, details=(), recent=False):
        lines = [f"{time.strftime('%H:%M:%S')}  {mark} {kind:<10} {self.place()}  |  {text}"]
        lines += [IND + d for d in details if d]
        if recent and self.recent:
            lines.append(IND + "آخرین کارها (از رویداد قبلی تا اینجا):")
            lines += [IND + "  " + r for r in self.recent]
            self.recent.clear()                  # رویداد بعدی فقط خط‌های تازه را نشان دهد
        self._write("\n".join(lines))

    def _rel(self, path):
        """مسیر عکس نسبت به پوشه‌ی Report (کوتاه‌تر)."""
        try:
            return os.path.relpath(path, self.folder)
        except ValueError:
            return path

    # ---------- رویدادها ----------
    def start(self, note=""):
        self.t0 = time.monotonic()
        self.counts.clear()
        self.recent.clear()
        self.where.clear()
        self._write(f"\n════ {time.strftime('%Y-%m-%d %H:%M:%S')}  شروع اجرا  "
                    f"(ریموت {self.remote}، pid {os.getpid()}) {note}".rstrip() + " ════")

    # ---------- panel: last error of the account now on this console ----------
    def _panel(self):
        import sys
        pan = r"C:\Users\Reach\Desktop\New Remote\Pannel"
        if pan not in sys.path:
            sys.path.insert(0, pan)
        import core as panel_core
        return panel_core

    def _where_en(self):
        parts = []
        if "challenge" in self.where:
            parts.append(str(self.where["challenge"]))
        if "row" in self.where:
            parts.append("row " + str(self.where["row"]).split(" (")[0])
        if "step" in self.where and "challenge" not in self.where:
            parts.append("start " + str(self.where["step"]))
        return " > ".join(parts)

    def panel_error(self, text, kind="error"):
        """Last error (English) for the panel's Status tab, on the account active on this console."""
        try:
            pc = self._panel()
            key = pc.get_active(pc.console_of(str(self.remote))).get("account")
            if key:
                where = self._where_en()
                pc.set_last_error(key, text + (f" @ {where}" if where else ""), kind)
        except Exception as e:                    # the report must never crash the bot
            print("panel error not saved:", e)

    def no_coins(self, account_key, text=""):
        """Out of coins: recorded in the panel (Status: Last error + Auto skips the account)."""
        try:
            pc = self._panel()
            key = account_key or pc.get_active(pc.console_of(str(self.remote))).get("account")
            if key:
                pc.set_no_coins(key, text)
        except Exception as e:
            print("panel no-coins not saved:", e)

    def fail(self, what, shot=None, func=None):
        """یک مرحله نشد."""
        self.panel_error(f"{what} failed", "error")
        self.counts["fail"] += 1
        self.event("✗", "خطا", f"{what} نشد",
                   [f"تابع: {func}" if func else "", f"عکس: {self._rel(shot)}" if shot else ""], recent=True)

    def retry(self, what, n, of):
        self.counts["retry"] += 1
        self.event("↻", "تلاش دوباره", f"{what}: تلاش {n} از {of} نشد، دوباره")

    def pause(self, what, hint, shot=None):
        """توقف موقت شروع شد. خروجی را به resumed بدهید."""
        self.counts["pause"] += 1
        self.panel_error(f"Paused: {what}", "pause")
        self.event("⏸", "توقف موقت", f"{what} نشد — منتظر درست کردن دستی و «ادامه»",
                   [f"راهنما: {hint}", f"عکس: {self._rel(shot)}" if shot else ""], recent=True)
        return time.monotonic()

    def resumed(self, since):
        self.event("▶", "ادامه", f"بعد از {_dur(time.monotonic() - since)} توقف")

    def ok(self, text):
        self.event("✓", "انجام شد", text)

    def info(self, text):
        self.event("·", "", text)

    def challenge_done(self, n):
        """Record that SBC n is complete for the account now on this console (panel SBC progress).
        Locked + atomic write through Pannel/core.py, keyed by active.json's account of THIS console
        (remote "C32-2" counts as console "C32"); fallback key = the console name."""
        try:
            import sys
            pan = r"C:\Users\Reach\Desktop\New Remote\Pannel"
            if pan not in sys.path:
                sys.path.insert(0, pan)
            import core as panel_core
            console = panel_core.console_of(str(self.remote))
            key = panel_core.get_active(console).get("account") or console
            name = n if isinstance(n, str) else f"Marquee {n}"   # SBC name (as the panel) or Marquee number
            panel_core.mark_sbc_done(key, name)
        except Exception as e:                    # the report must never crash the bot
            print("SBC progress not saved:", e)

    def stopped(self, text, en=None):
        """en = English reason for the panel's Last error (None = not an error, e.g. Stop pressed)."""
        if en:
            self.panel_error(en, "stop")
        self.event("■", "توقف", text, recent=True)

    def crash(self, exc):
        """خطای پیش‌بینی‌نشده‌ی پایتون (باگ کد)."""
        self.counts["crash"] += 1
        self.panel_error(f"Code error: {type(exc).__name__}: {exc}", "crash")
        tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
        tb = "".join(tb).rstrip().splitlines()[-12:]
        self.event("‼", "خطای کد", f"{type(exc).__name__}: {exc}", tb, recent=True)

    def end(self, text):
        took = _dur(time.monotonic() - self.t0) if self.t0 else "?"
        c = self.counts
        self._write(f"════ پایان: {text}  |  مدت {took}  |  خطا {c['fail']}، تلاش دوباره {c['retry']}، "
                    f"توقف موقت {c['pause']}، خطای کد {c['crash']} ════")

    def shot_path(self, name):
        """مسیر عکس تازه (فقط حروف لاتین؛ cv2 روی ویندوز اسم فارسی را ذخیره نمی‌کند)."""
        os.makedirs(self.shots, exist_ok=True)
        self.n_shots += 1                         # دو عکس در یک ثانیه روی هم ننشینند
        return os.path.join(self.shots, time.strftime("%m%d_%H%M%S_") + f"{self.n_shots:03d}_"
                            + (_safe(name) or "shot") + ".png")


def _safe(s):
    """فقط حروف لاتین، عدد، - و _ (برای اسم فایل)."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(s)).strip("_")[:60]


def _dur(sec):
    sec = int(sec)
    h, m, s = sec // 3600, sec // 60 % 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
