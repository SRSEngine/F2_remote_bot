# -*- coding: utf-8 -*-
"""
run_bot.py — اجرای Play.py بدون VS Code (دکمه‌ی «شروع» پنل ریموت همین را اجرا می‌کند).

مثل VS Code سلول‌به‌سلول: همه‌ی سلول‌های Play.py از اول تا آخر سلول «# %% Main» اجرا می‌شوند؛
سلول‌های بعد از Main (تست‌ها) اجرا نمی‌شوند. Play.py را مثل همیشه ویرایش کنید؛ این فایل تغییری نمی‌خواهد.

دستی:  python run_bot.py
خروجی وقتی از پنل اجرا شود: run_bot.log کنار همین فایل.
"""
import os
import re
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PLAY = os.path.join(HERE, "Play.py")
CELL = re.compile(r"^\s*#\s*%%(.*)$")           # خط شروع سلول: "# %%" یا "#%%" با عنوان دلخواه


def main_part(src):
    """متن Play.py از اول تا آخر سلول Main (سلول بعدی یا آخر فایل)."""
    lines = src.splitlines(keepends=True)
    main_at = None
    for i, line in enumerate(lines):
        m = CELL.match(line)
        if m and m.group(1).strip().lower().startswith("main"):
            main_at = i
            break
    if main_at is None:
        raise SystemExit("سلول «# %% Main» در Play.py پیدا نشد")
    end = len(lines)
    for i in range(main_at + 1, len(lines)):
        if CELL.match(lines[i]):
            end = i
            break
    return "".join(lines[:end]), end


def main():
    print(time.strftime("%Y-%m-%d %H:%M:%S"), "run_bot: Play.py تا آخر سلول Main")
    with open(PLAY, encoding="utf-8") as f:
        code, end = main_part(f.read())
    print(f"run_bot: {end} خط اول Play.py اجرا می‌شود")
    os.chdir(HERE)
    sys.path.insert(0, HERE)
    g = {"__name__": "__main__", "__file__": PLAY}
    try:
        exec(compile(code, PLAY, "exec"), g)
    except Exception as e:
        if type(e).__name__ == "BotStopped":
            print("run_bot: توقف از پنل")
            return 0
        traceback.print_exc()
        try:                                         # خطا را در لاگ پنل هم نشان بده
            g.get("log", print)(f"✗ خطا: {type(e).__name__}: {e}")
        except Exception:
            pass
        return 1
    print("run_bot: Main تمام شد")
    return 0


if __name__ == "__main__":
    sys.exit(main())
