# -*- coding: utf-8 -*-
"""
remoteio.py — پل بین پنل و ریموت‌های xbrp در حال اجرا.

- گرفتن فریم (snap) برای تصویر کوچک هر ریموت
- کنترل ربات روی هر ریموت از طریق pipe: شروع / توقف موقت / توقف / وضعیت / سلامت
- نمایش/مخفی کردن پنجره‌ی ریموت (Minimize/Restore) با hwnd

از founder.Remote همان کنسول استفاده می‌کند (همان pipe که ربات هم با آن کار می‌کند).
"""
from __future__ import annotations

import ctypes
import glob
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Optional

# مسیر ابزارهای موجود کاربر
_CTRL = r"C:\Users\Reach\Desktop\New Remote\Controller"
_FND = r"C:\Users\Reach\Desktop\New Remote\Founder"
for p in (_FND, _CTRL):
    if p not in sys.path:
        sys.path.insert(0, p)

import founder  # noqa: E402  (snap + pipe)

REMOTES_DIR = founder.DEFAULT_REMOTES

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

SW_MINIMIZE = 6
SW_RESTORE = 9
SW_SHOW = 5


# ---------- پیدا کردن ریموت در حال اجرا ----------

def _pid_alive(pid) -> bool:
    if not pid:
        return False
    h = kernel32.OpenProcess(0x1000, False, int(pid))  # QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    ok = kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    kernel32.CloseHandle(h)
    return bool(ok) and code.value == 259  # STILL_ACTIVE


def running_remote(console: str) -> Optional[dict]:
    """اطلاعات ریموتِ زنده‌ی این کنسول (از فایل‌های Controller\\remotes)، وگرنه None."""
    want = (console or "").strip().lower()
    exact, same = None, []
    for path in glob.glob(os.path.join(REMOTES_DIR, "*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                info = json.load(f)
        except (OSError, ValueError):
            continue
        if not _pid_alive(info.get("pid")):
            continue
        name = (info.get("name") or Path(path).stem).lower()
        if name == want:
            exact = info
        elif (info.get("console") or "").lower() == want or name.startswith(want + "-"):
            same.append(info)
    if exact:
        return exact
    if same:
        return max(same, key=lambda i: i.get("started", ""))
    return None


def is_running(console: str) -> bool:
    return running_remote(console) is not None


# ---------- اتصال به یک ریموت (snap + دستور) ----------

class RemoteLink:
    """نگه‌دارنده‌ی یک founder.Remote برای یک کنسول. همه‌ی کار pipe در نخ ناظر انجام می‌شود."""

    def __init__(self, console: str):
        self.console = console
        self._remote: Optional[founder.Remote] = None

    def _r(self) -> founder.Remote:
        if self._remote is None:
            self._remote = founder.Remote(self.console, remotes_dir=REMOTES_DIR)
        return self._remote

    def drop(self):
        try:
            if self._remote:
                self._remote.close()
        except Exception:
            pass
        self._remote = None

    def snap_bgr(self):
        """یک فریم BGR (numpy) یا None."""
        try:
            return self._r().snap()
        except Exception:
            self.drop()
            return None

    def send(self, cmd: str) -> str:
        try:
            return self._r().send(cmd)
        except Exception:
            self.drop()
            return ""

    # --- ربات ---
    def bot_state(self) -> str:
        """run | pause | stop | wait | '' (ریموت قدیمی/بی‌پاسخ)."""
        r = self.send("bot")
        return r[3:].strip() if r.startswith("ok ") else ""

    def bot_start(self) -> str:
        return self.send("bot start")

    def bot_pause(self) -> str:
        return self.send("bot pause")

    def bot_resume(self) -> str:
        return self.send("bot run")

    def bot_stop(self) -> str:
        return self.send("bot stop")

    def health(self) -> str:
        """ok | weak | down | connecting | reconnecting | none | ''."""
        r = self.send("health")
        if not r.startswith("ok "):
            return ""
        return r.split()[1] if len(r.split()) > 1 else ""


# ---------- نمایش/مخفی کردن پنجره ----------

def window_hwnd(console: str) -> int:
    info = running_remote(console)
    return int(info.get("hwnd", 0)) if info else 0


def is_minimized(hwnd: int) -> bool:
    return bool(hwnd) and bool(user32.IsIconic(hwnd))


def is_window(hwnd: int) -> bool:
    return bool(hwnd) and bool(user32.IsWindow(hwnd))


def show_window(hwnd: int):
    if hwnd:
        user32.ShowWindow(hwnd, SW_RESTORE)
        try:
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass


def hide_window(hwnd: int):
    if hwnd:
        user32.ShowWindow(hwnd, SW_MINIMIZE)


def toggle_window(hwnd: int) -> bool:
    """نمایش/مخفی. True اگر حالا نمایش داده شد، False اگر مخفی شد."""
    if not hwnd:
        return False
    if is_minimized(hwnd):
        show_window(hwnd)
        return True
    hide_window(hwnd)
    return False
