# -*- coding: utf-8 -*-
"""
remotectl.py — کنترل ربات از پنل ریموت xbrp (مشترک بین xbox.py و founder.py)

قبل از هر دکمه، هر جستجوی تصویر/متن و در هر wait، این کارها انجام می‌شود:
  1) لاگ:      یک خط در پنل ریموت (دکمه، جستجو و نتیجه‌ی آن). تکرار همان خط فقط شمرده می‌شود (×N).
  2) وضعیت ربات (دکمه‌های پنل):
       شروع  → ادامه
       توقف موقت → همین‌جا صبر تا «ادامه» زده شود، بعد از همین‌جا ادامه
       توقف  → خطای BotStopped (سلول/اسکریپت تمیز متوقف می‌شود؛ تا «شروع» زده نشود هر کار بعدی هم متوقف می‌شود)
  3) سلامت ریموت: اگر تصویر نمی‌رسد (قطع)، کمی صبر؛ اگر درست نشد «اتصال دوباره» و صبر تا سالم شود، بعد ادامه.

ریموت قدیمی که این دستورها را نمی‌شناسد: همه‌چیز خاموش می‌شود و ربات مثل قبل کار می‌کند.
"""
from __future__ import annotations

import os
import time
import uuid

# ---- تنظیمات ----
DOWN_GRACE_S = 8          # قطع کوتاه را این‌قدر تحمل کن، بعد «اتصال دوباره»
RECONNECT_WAIT_S = 45     # بعد از اتصال دوباره تا این‌قدر صبر تا سالم شود
RECONNECT_TRIES = 3       # چند بار اتصال دوباره، بعد خطای RemoteDown
POLL_S = 0.25             # فاصله‌ی نگاه کردن به وضعیت هنگام صبر

_BAD = ("down", "connecting", "reconnecting")   # بقیه (ok / weak / none / نامعلوم) = سالم

# شماره‌ی «اجرا»: در هر پروسه یکی؛ در VS Code / Jupyter با هر بار اجرای سلول عوض می‌شود.
# ریموت با آن می‌فهمد ربات الان مشغول است (و «شروع» دوباره Play را اجرا نکند)، و «توقف» فقط همان اجرا را
# متوقف می‌کند: اجرای دوباره‌ی سلول خودش ادامه می‌دهد.
_run = {"id": uuid.uuid4().hex[:8]}


def _new_run(*_a, **_k):
    _run["id"] = uuid.uuid4().hex[:8]


try:                                    # VS Code Interactive / Jupyter: هر سلول = اجرای جدید
    _ip = get_ipython()                 # noqa: F821  (فقط داخل IPython تعریف شده)
    if not getattr(_ip, "_xbrp_run_hook", False):
        _ip.events.register("pre_run_cell", _new_run)
        _ip._xbrp_run_hook = True
except Exception:
    pass

# شمارنده‌ی دکمه‌ها: xbox.py با هر دکمه یکی زیادش می‌کند. founder.py با آن می‌فهمد فریمی که دارد مال قبل از
# دکمه است و باید فریم تازه بگیرد.
_input = {"n": 0}


def mark_input():
    _input["n"] += 1


def input_seq():
    return _input["n"]


_STOPPED = "Bot stopped from the remote panel (to run again: run the cell again or press Start)"


class BotStopped(Exception):
    """دکمه‌ی «توقف» پنل زده شد."""


class RemoteDown(Exception):
    """ریموت بعد از چند بار اتصال دوباره هم سالم نشد."""


class Control:
    """send(line) -> reply : همان کانال pipe ریموت (xbox._Pipe.send یا founder.Remote.send)."""

    def __init__(self, send):
        self._send = send
        self.supported = None      # None = هنوز معلوم نیست، False = ریموت قدیمی
        self._seen = True          # ریموت «bot seen» را می‌شناسد؟
        self.enabled = True        # control.enabled = False → فقط کار قبلی، بدون لاگ/چک

    # ---------- پایه ----------
    def _ask(self, line):
        """جواب ریموت، یا None اگر ریموت این دستور را نمی‌شناسد / در دسترس نیست."""
        if not self.enabled or self.supported is False:
            return None
        try:
            r = self._send(line) or ""
        except Exception:
            return None
        if r.startswith("err unknown"):
            self.supported = False
            return None
        self.supported = True
        return r

    def log(self, text):
        """یک خط در لاگ پنل ریموت."""
        text = " ".join(str(text).split())
        if text:
            self._ask("log " + text[:160])

    def state(self):
        """run / pause / stop / wait، یا None. (به ریموت می‌گوید این اجرا الان مشغول است)"""
        r = None
        if self._seen:
            r = self._ask("bot seen %d %s" % (os.getpid(), _run["id"]))
            if r and r.startswith("err"):          # ریموت نسخه‌ی قبل: فقط «bot»
                self._seen, r = False, None
        if r is None:
            r = self._ask("bot")
        return r.split()[1] if r and r.startswith("ok ") and len(r.split()) > 1 else None

    def health(self):
        """ok / weak / down / connecting / reconnecting، یا None."""
        r = self._ask("health")
        return r.split()[1] if r and r.startswith("ok ") and len(r.split()) > 1 else None

    # ---------- وضعیت ربات ----------
    def check_bot(self):
        """توقف → BotStopped؛ توقف موقت / منتظر شروع → صبر همین‌جا."""
        st = self.state()
        if st is None or st == "run":
            return
        if st == "stop":
            raise BotStopped(_STOPPED)
        self.log("⏸ Waiting for Resume" if st == "pause" else "⏳ Waiting for Start")
        while True:
            time.sleep(POLL_S)
            st = self.state()
            if st is None or st == "run":
                return
            if st == "stop":
                raise BotStopped(_STOPPED)

    # ---------- سلامت ریموت ----------
    def _wait_healthy(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.health() not in _BAD:
                return True
            self.check_bot()
            time.sleep(POLL_S)
        return False

    def check_health(self):
        """اگر ریموت سالم نیست: صبر، اتصال دوباره، صبر تا سالم شود. نشد → RemoteDown."""
        h = self.health()
        if h not in _BAD:
            return
        # قطع کوتاه یا در حال اتصال: اول کمی صبر
        self.log(f"⚠ Remote: {h} — waiting")
        if self._wait_healthy(DOWN_GRACE_S):
            self.log("✓ Remote is healthy again")
            return
        for n in range(1, RECONNECT_TRIES + 1):
            self.log(f"↻ Reconnect ({n}/{RECONNECT_TRIES})")
            self._ask("reconnect")
            time.sleep(1)
            if self._wait_healthy(RECONNECT_WAIT_S):
                self.log("✓ Remote reconnected")
                return
        self.log("✗ Remote did not reconnect")
        raise RemoteDown("Remote still not healthy after %d reconnects" % RECONNECT_TRIES)

    def checkpoint(self, text=None):
        """قبل از هر کار: لاگ، وضعیت ربات، سلامت ریموت."""
        if not self.enabled or self.supported is False:
            return
        if text:
            self.log(text)
        self.check_bot()
        self.check_health()

    def sleep(self, ms):
        """wait(ms) که با «توقف» قطع و با «توقف موقت» نگه داشته می‌شود."""
        end = time.monotonic() + ms / 1000.0
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return
            time.sleep(min(left, 0.2))
            if self.enabled and self.supported is not False and left > 0.2:
                self.check_bot()

    def pause(self, text=None):
        """ربات خودش «توقف موقت» می‌شود (دکمه‌ی پنل «ادامه» می‌شود) و همین‌جا صبر می‌کند.
        True = «ادامه» زده شد.  False = ریموت این را ندارد (ریموت قدیمی / بدون پنل).
        «توقف» در این حالت → BotStopped."""
        r = self._ask("bot pause")
        if not r or not r.startswith("ok"):
            return False
        if text:
            self.log(text)
        self.check_bot()
        self.log("▶ Resume")
        return True

    def wait_start(self):
        """ربات را «منتظر شروع» می‌گذارد و صبر می‌کند تا «شروع» در پنل زده شود."""
        if self._ask("bot wait") is None:
            return
        self.log("⏳ Waiting for Start in the panel")
        self.check_bot()
        self.log("▶ Bot started")
