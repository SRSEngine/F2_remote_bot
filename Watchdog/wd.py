# -*- coding: utf-8 -*-
r"""
wd.py - Watchdog tool for the local agent (Claude) and for the scheduled runner.

    python wd.py status            all live remotes: bot state, health, last report event -> JSON
    python wd.py need              exit 0 + names if some remote needs help, else exit 1 (cheap pre-check)
    python wd.py snap NAME         save a screenshot of the remote -> prints the PNG path
    python wd.py press NAME a down down a ...   tap buttons in order (--hold MS, --gap MS)
    python wd.py resume NAME       same as the panel's Start/Resume (paused -> resume, stopped -> relaunch Play)
    python wd.py record NAME --problem "..." --action "..." --result "..."   append to Fixes.md + fixes.jsonl
    python wd.py history [NAME]    last fixes (to reuse what worked before)

Talks raw to the remote's pipe (\\.\pipe\xbrp-<name>), opening and closing per command, so it never blocks
on the bot's pause like xbox.press / founder.snap would.
"""
from __future__ import annotations

import argparse
import ctypes
import glob
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REMOTES = os.path.join(ROOT, "Controller", "remotes")
REPORT = os.path.join(ROOT, "Report")
SNAPS = os.path.join(HERE, "snaps")
FIXES_MD = os.path.join(HERE, "Fixes.md")
FIXES_JSONL = os.path.join(HERE, "fixes.jsonl")

BUTTONS = {"a", "b", "x", "y", "up", "down", "left", "right", "lb", "rb", "lt", "rt", "ls", "rs",
           "view", "menu", "nexus", "lsup", "lsdown", "lsleft", "lsright", "rsup", "rsdown", "rsleft", "rsright"}

k32 = ctypes.windll.kernel32
u32 = ctypes.windll.user32

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ---------- remotes ----------
def _alive(pid):
    if not pid:
        return False
    h = k32.OpenProcess(0x1000, False, int(pid))
    if not h:
        return False
    c = ctypes.c_ulong()
    ok = k32.GetExitCodeProcess(h, ctypes.byref(c))
    k32.CloseHandle(h)
    return bool(ok) and c.value == 259


def remotes():
    out = []
    for p in glob.glob(os.path.join(REMOTES, "*.json")):
        try:
            with open(p, encoding="utf-8") as f:
                i = json.load(f)
        except (OSError, ValueError):
            continue
        if not i.get("pipe") or not _alive(i.get("pid")):
            continue
        h = int(i.get("hwnd") or 0)
        if h and not u32.IsWindow(h):          # window closed, process left behind
            continue
        i["name"] = i.get("name") or os.path.splitext(os.path.basename(p))[0]
        out.append(i)
    out.sort(key=lambda i: i["name"])
    return out


def find(name):
    for i in remotes():
        if i["name"].lower() == name.lower():
            return i
    sys.exit(f"no live remote named {name}")


def send(info, line, tries=2):
    data = (line.strip() + "\n").encode("utf-8")
    for _ in range(tries):
        try:
            with open(info["pipe"], "r+b", buffering=0) as f:
                f.write(data)
                return f.read(4096).decode("utf-8", "replace").strip()
        except OSError:
            time.sleep(0.3)
    return ""


def bot_state(info):
    r = send(info, "bot")
    return r[3:].strip() if r.startswith("ok ") else "?"


def health(info):
    r = send(info, "health")
    p = r.split()
    return p[1] if r.startswith("ok ") and len(p) > 1 else "?"


# ---------- report ----------
EVENT = re.compile(r"^(\d\d:\d\d:\d\d)\s+(✗|↻|⏸|▶|✓|·|■|‼)\s*(.*)$")


def report_tail(name):
    """Last run block of Report/<name>.log: header, important events, end line, newest shot."""
    path = os.path.join(REPORT, name + ".log")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()[-60000:]
    last = text.split("\n════ ")[-1]
    lines = last.splitlines()
    ended = ""
    for ln in lines:
        if "پایان:" in ln[:20]:
            ended = ln.strip("═ ").strip()
    events, shot = [], ""
    for ln in lines:
        m = EVENT.match(ln)
        if m:
            events.append(f"{m.group(1)} {m.group(2)} {m.group(3)[:200]}")
        s = ln.strip()
        if s.startswith("عکس:"):
            shot = os.path.join(REPORT, s.split(":", 1)[1].strip())
    age = int(time.time() - os.path.getmtime(path))
    return {"run_header": lines[0][:160] if lines else "", "ended": ended,
            "events": events[-8:], "last_shot": shot, "log_age_s": age, "log": path}


def rep_name(rep):
    return os.path.splitext(os.path.basename(rep.get("log", "")))[0]


def classify(state, rep):
    """What the agent should do with this remote."""
    ended = rep.get("ended", "")
    if state == "pause":
        return "FIX_AND_RESUME"
    if ended:                               # the last Play run is over (state may still say "run")
        if "توقف از پنل" in ended:
            return "FIX_AND_RESTART (agent restart did not start)" if agent_stopped(rep_name(rep), rep) else "LEAVE (user pressed Stop)"
        if "✓" in ended:
            return "LEAVE (all done)"
        if "Authenticator" in ended:
            return "LEAVE (EA authenticator code rejected 3x: user must check EAGauth)"
        return "FIX_AND_RESTART"            # remote lost, code error, ... -> bot process is gone
    if state == "wait":
        return "LEAVE (waiting for user Start)"
    if state == "stop":
        return "CHECK (stopped mid-run)"
    if state == "run" and rep and rep.get("log_age_s", 0) > 1800:
        return "WATCH (running, no report event for 30+ min)"
    return "OK"


# ---------- commands ----------
def cmd_status(a):
    out = []
    for i in remotes():
        st = bot_state(i)
        rep = report_tail(i["name"])
        out.append({"name": i["name"], "pid": i["pid"], "bot": st, "health": health(i),
                    "todo": classify(st, rep), "report": rep})
    print(json.dumps(out, ensure_ascii=False, indent=1))


def waiting_human(name, rep):
    """The agent already recorded NEEDS HUMAN for this remote and the bot's report did not move since."""
    if not os.path.exists(FIXES_JSONL) or not rep.get("log"):
        return False
    last = None
    with open(FIXES_JSONL, encoding="utf-8") as f:
        for l in f:
            if l.strip():
                r = json.loads(l)
                if r["remote"].lower() == name.lower():
                    last = r
    if not last or not last["result"].startswith("NEEDS HUMAN"):
        return False
    at = time.mktime(time.strptime(last["at"], "%Y-%m-%d %H:%M:%S"))
    return os.path.getmtime(rep["log"]) <= at


def cmd_need(a):
    need = []
    for i in remotes():
        st = bot_state(i)
        rep = report_tail(i["name"])
        todo = classify(st, rep)
        if todo.startswith(("FIX", "CHECK", "WATCH")):
            need.append(f"{i['name']}: bot={st} -> {todo}")
    print("\n".join(need) or "nothing to do")
    sys.exit(0 if need else 1)


def cmd_snap(a):
    i = find(a.name)
    os.makedirs(SNAPS, exist_ok=True)
    path = os.path.join(SNAPS, f"{i['name']}_{time.strftime('%m%d_%H%M%S')}.png")
    r = send(i, "snap " + path)
    if not r.startswith("ok") or not os.path.exists(path):
        sys.exit("snap failed: " + (r or "no reply"))
    print(path)


def cmd_press(a):
    i = find(a.name)
    keys = [k.lower() for k in a.buttons]
    for k in keys:
        if any(p not in BUTTONS for p in k.split("+")):
            sys.exit(f"unknown button {k}; use: {' '.join(sorted(BUTTONS))}")
    send(i, "log 🛠 Agent: " + " ".join(k.upper() for k in keys))
    for k in keys:
        r = send(i, f"press {k} {a.hold}")
        print(k, "->", r)
        if not r.startswith("ok"):
            sys.exit(1)
        time.sleep((a.hold + a.gap) / 1000.0)


def cmd_resume(a):
    i = find(a.name)
    before = bot_state(i)
    send(i, "log 🛠 Agent: Resume")
    r = send(i, "bot start")
    time.sleep(2)
    print(json.dumps({"before": before, "reply": r, "after": bot_state(i)}))
    time.sleep(max(0, a.wait - 2))          # let the bot work, then show what it reported
    rep = report_tail(i["name"])
    print("bot now:", bot_state(i), "| ended:", rep.get("ended") or "-")
    print("\n".join(rep.get("events", [])[-4:]))


RESTARTS = os.path.join(HERE, "restarts.json")


def _restarts():
    try:
        with open(RESTARTS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def agent_stopped(name, rep):
    """The last run ended with 'Stop from panel' because the AGENT pressed it (restart), not the user."""
    t = _restarts().get(name.upper())
    return bool(t and rep.get("log") and os.path.getmtime(rep["log"]) - t < 600 and os.path.getmtime(rep["log"]) >= t - 5)


def cmd_restart(a):
    """Stop the Play run and start a fresh one: Play goes Home -> SBC -> opens the challenge -> Clear Squad ->
    refills (players bought before are in the Club, so no extra coins). For a squad in a wrong state."""
    i = find(a.name)
    rep = report_tail(i["name"])
    m = re.search(r"pid (\d+)", rep.get("run_header", ""))
    pid = int(m.group(1)) if m else 0
    r = _restarts(); r[i["name"].upper()] = time.time()
    with open(RESTARTS, "w", encoding="utf-8") as f:
        json.dump(r, f)
    send(i, "log 🛠 Agent: restart Play (fresh run, squad will be cleared)")
    send(i, "bot stop")
    end = time.time() + 90
    while pid and _alive(pid) and time.time() < end:
        time.sleep(1)
    if pid and _alive(pid):
        sys.exit(f"old Play run (pid {pid}) did not stop in 90 s; bot={bot_state(i)}")
    time.sleep(2)
    print("stopped old run", pid, "->", send(i, "bot start"))
    time.sleep(a.wait)
    rep = report_tail(i["name"])
    print("bot now:", bot_state(i), "| ended:", rep.get("ended") or "-")
    print(rep.get("run_header", ""))
    print("\n".join(rep.get("events", [])[-4:]))


def cmd_record(a):
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    rec = {"at": now, "remote": a.name, "problem": a.problem, "action": a.action, "result": a.result,
           "shot": a.shot or ""}
    with open(FIXES_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    new = not os.path.exists(FIXES_MD)
    with open(FIXES_MD, "a", encoding="utf-8") as f:
        if new:
            f.write("# Watchdog — مشکلات ریموت‌ها و کاری که ایجنت کرد\n\n")
        f.write(f"## {now} — {a.name}\n- مشکل: {a.problem}\n- کار انجام‌شده: {a.action}\n- نتیجه: {a.result}\n")
        if a.shot:
            f.write(f"- عکس: {a.shot}\n")
        f.write("\n")
    print("recorded")


def cmd_history(a):
    if not os.path.exists(FIXES_JSONL):
        print("no history yet")
        return
    with open(FIXES_JSONL, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    if a.name:
        rows = [r for r in rows if r["remote"].lower() == a.name.lower()]
    for r in rows[-a.n:]:
        print(f"{r['at']} {r['remote']} | {r['problem']} | {r['action']} | {r['result']}")


def main():
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("status").set_defaults(f=cmd_status)
    s.add_parser("need").set_defaults(f=cmd_need)
    x = s.add_parser("snap"); x.add_argument("name"); x.set_defaults(f=cmd_snap)
    x = s.add_parser("press"); x.add_argument("name"); x.add_argument("buttons", nargs="+")
    x.add_argument("--hold", type=int, default=80); x.add_argument("--gap", type=int, default=400)
    x.set_defaults(f=cmd_press)
    x = s.add_parser("resume"); x.add_argument("name"); x.add_argument("--wait", type=int, default=25)
    x.set_defaults(f=cmd_resume)
    x = s.add_parser("restart"); x.add_argument("name"); x.add_argument("--wait", type=int, default=40)
    x.set_defaults(f=cmd_restart)
    x = s.add_parser("record"); x.add_argument("name"); x.add_argument("--problem", required=True)
    x.add_argument("--action", required=True); x.add_argument("--result", required=True)
    x.add_argument("--shot", default=""); x.set_defaults(f=cmd_record)
    x = s.add_parser("history"); x.add_argument("name", nargs="?"); x.add_argument("-n", type=int, default=30)
    x.set_defaults(f=cmd_history)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
