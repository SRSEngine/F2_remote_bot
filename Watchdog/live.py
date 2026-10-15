# -*- coding: utf-8 -*-
r"""
live.py - real-time watchdog: watches every live remote all the time and starts the agent (Claude, AGENT.md)
for a remote the moment its bot pauses / stops / its Play run dies. No 10-minute wait.

    pythonw live.py          run in the background (one instance only; a second one exits with code 3)
    python live.py --once    one check, print what it would do, no agent (test)

How it works
- Every POLL seconds: bot state (pipe 'bot') + last report block of every live remote -> wd.classify().
- FIX_* / CHECK that stays for GRACE seconds -> one agent run for THAT remote only (logs\run_<stamp>_<NAME>.md).
  Several remotes can be fixed at the same time (MAX_AGENTS parallel runs, the rest wait in a queue).
- Same problem again after an agent run (same step in the report) -> retry after RETRY_AFTER seconds, at most
  MAX_TRIES runs; then HOLD seconds pause for that problem (toast "still stuck"), then it tries again.
- WATCH (running but no report line for 30+ min) -> agent at most once per WATCH_EVERY seconds per remote.
- live.json = heartbeat + what is going on (panel header + run_watchdog.ps1 read it).
  Task Scheduler "F2 Watchdog" (every 10 min) and the F2 panel start this script when it is not running.
  Disabling that task turns the watchdog off: live.py notices within a minute and exits.
"""
from __future__ import annotations

import glob
import json
import msvcrt
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import wd  # noqa: E402

POLL = 3              # seconds between checks
GRACE_PAUSE = 3       # a bot pause must last this long before the agent starts
GRACE_OTHER = 20      # stopped / run ended: give the panel's own Stop time to write its 'ended' line
RETRY_AFTER = 60      # same problem still there after an agent run -> next run after this
MAX_TRIES = 3         # agent runs for the same problem before holding it
HOLD = 30 * 60        # then wait this long before trying the same problem again
WATCH_EVERY = 30 * 60
MAX_AGENTS = 3        # parallel agent runs (each is one Claude session)
AGENT_TIMEOUT = 30 * 60

LOGS = os.path.join(HERE, "logs")
LOG = os.path.join(LOGS, "watchdog.log")
STATUS = os.path.join(HERE, "live.json")
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def stamp():
    return time.strftime("%Y%m%d_%H%M%S")


def log(line):
    os.makedirs(LOGS, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{stamp()} {line}\n")


def toast(title, text):
    """Windows notification (same as run_watchdog.ps1). Text goes through env vars: no quoting problems."""
    ps = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;"
        "$t=[Security.SecurityElement]::Escape($env:WD_T); $b=[Security.SecurityElement]::Escape($env:WD_B);"
        "$x=New-Object Windows.Data.Xml.Dom.XmlDocument;"
        "$x.LoadXml(\"<toast><visual><binding template='ToastGeneric'><text>$t</text><text>$b</text></binding></visual></toast>\");"
        "$app='{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe';"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($x))"
    )
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", ps], creationflags=CREATE_NO_WINDOW,
                         env={**os.environ, "WD_T": title, "WD_B": text},
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def claude_exe():
    exe = shutil.which("claude")
    if exe:
        return exe
    c = glob.glob(os.path.expanduser(r"~\.vscode\extensions\anthropic.claude-code-*\resources\native-binary\claude.exe"))
    return max(c, key=os.path.getmtime) if c else None


def task_disabled():
    """Task Scheduler "F2 Watchdog" disabled = the user turned the watchdog off -> live.py stops too."""
    try:
        r = subprocess.run(["schtasks", "/Query", "/TN", "F2 Watchdog", "/FO", "CSV", "/NH"], capture_output=True,
                           text=True, timeout=20, creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and "disabled" in r.stdout.lower()


def single_instance():
    f = open(os.path.join(HERE, "live.lock"), "a+")
    try:
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        return f
    except OSError:
        f.close()
        return None


def problem_key(todo, rep):
    """Same problem = same kind + same last report event (without its time) or same end line."""
    ev = (rep.get("events") or [""])[-1]
    ev = ev.split(" ", 1)[1] if " " in ev else ev
    return f"{todo.split(' ')[0]}|{rep.get('ended', '')}|{ev[:160]}"


class Agent:
    def __init__(self, name, need):
        self.name, self.need, self.started = name, need, time.time()
        self.stamp = stamp()
        self.out = os.path.join(LOGS, f"run_{self.stamp}_{name}.md")
        prompt = (f"Read AGENT.md in this folder and do ONE watchdog run now for remote {name} ONLY "
                  f"(other remotes are handled by their own runs - do not touch them). It needs help right now:\n{need}")
        exe = claude_exe()
        self.proc = None
        if not exe:
            log(f"ERROR: claude.exe not found (agent for {name} not started)")
            return
        os.makedirs(LOGS, exist_ok=True)
        self.fh = open(self.out, "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [exe, "-p", prompt, "--model", "opus",
             "--allowedTools", "Bash(python wd.py:*)", "PowerShell(python wd.py:*)", "Read", "Glob", "Grep",
             "--add-dir", os.path.join(ROOT, "Report"), os.path.join(ROOT, "Play"), "--max-turns", "80"],
            cwd=HERE, stdout=self.fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, creationflags=CREATE_NO_WINDOW)

    def done(self):
        if self.proc is None:
            return True
        if self.proc.poll() is None and time.time() - self.started > AGENT_TIMEOUT:
            self.proc.kill()
            log(f"agent for {self.name} killed after {AGENT_TIMEOUT // 60} min")
        if self.proc.poll() is None:
            return False
        self.fh.close()
        return True


class Live:
    def __init__(self):
        self.agents: dict[str, Agent] = {}
        self.queue: list[tuple[str, str, str]] = []     # (name, need, key)
        self.seen: dict[str, tuple[str, float]] = {}    # name -> (key, first seen)
        self.tries: dict[tuple[str, str], list] = {}    # (name, key) -> [count, last end time, hold until]
        self.watch_at: dict[str, float] = {}
        self.last_states: dict[str, dict] = {}
        self._rep_cache: dict[str, tuple[float, dict]] = {}

    def report(self, name):
        p = os.path.join(wd.REPORT, name + ".log")
        try:
            m = os.path.getmtime(p)
        except OSError:
            return {}
        c = self._rep_cache.get(name)
        if c and c[0] == m:
            rep = dict(c[1])
        else:
            rep = wd.report_tail(name)
            self._rep_cache[name] = (m, rep)
            rep = dict(rep)
        rep["log_age_s"] = int(time.time() - m)
        return rep

    def wants(self, name, todo, key, now):
        """Should an agent start for this remote now?"""
        if name in self.agents or any(q[0] == name for q in self.queue):
            return False
        if todo.startswith("WATCH"):
            return now - self.watch_at.get(name, 0) >= WATCH_EVERY
        k, since = self.seen.get(name, ("", now))
        grace = GRACE_PAUSE if "RESUME" in todo else GRACE_OTHER
        if k != key or now - since < grace:
            return False
        t = self.tries.get((name, key))
        if not t:
            return True
        count, ended, hold = t
        if now < hold:
            return False
        if hold and now >= hold:                 # hold is over: a fresh set of tries
            self.tries[(name, key)] = [0, 0, 0]
            return True
        return count < MAX_TRIES and now - ended >= RETRY_AFTER

    def tick(self, dry=False):
        now = time.time()
        states = {}
        for i in wd.remotes():
            name = i["name"]
            st = wd.bot_state(i)
            rep = self.report(name)
            todo = wd.classify(st, rep)
            key = problem_key(todo, rep)
            states[name] = {"bot": st, "todo": todo}
            if not todo.startswith(("FIX", "CHECK", "WATCH")):
                self.seen.pop(name, None)
                continue
            if self.seen.get(name, ("",))[0] != key:
                self.seen[name] = (key, now)
            if dry:
                print(f"{name}: bot={st} -> {todo}  (key {key[:80]})")
                continue
            if self.wants(name, todo, key, now):
                need = f"{name}: bot={st} -> {todo}"
                if todo.startswith("WATCH"):
                    self.watch_at[name] = now
                self.queue.append((name, need, key))
                log(f"need: {need}")
        self.last_states = states
        if dry:
            return
        # finished agents
        for name, ag in list(self.agents.items()):
            if ag.done():
                del self.agents[name]
                took = int((time.time() - ag.started) / 60)
                code = ag.proc.returncode if ag.proc else -1
                log(f"agent done {name} -> logs\\{os.path.basename(ag.out)} (exit {code}, {took} min)")
                t = self.tries.setdefault((name, ag.key), [0, 0, 0])
                t[0] += 1
                t[1] = time.time()
                if t[0] >= MAX_TRIES:
                    t[2] = time.time() + HOLD
                    log(f"{name}: same problem after {t[0]} agent runs - next try in {HOLD // 60} min")
                    toast(f"F2 Watchdog: {name} still stuck",
                          f"{t[0]} agent runs did not fix it - see Watchdog\\Fixes.md. Next try in {HOLD // 60} min.")
                else:
                    toast(f"F2 Watchdog: {name} done ({took} min)", "Details in Watchdog\\Fixes.md")
        # start queued agents
        while self.queue and len(self.agents) < MAX_AGENTS:
            name, need, key = self.queue.pop(0)
            ag = Agent(name, need)
            ag.key = key
            if ag.proc is None:
                continue
            self.agents[name] = ag
            log(f"agent started {name} -> logs\\{os.path.basename(ag.out)}")
            toast(f"F2 Watchdog: fixing {name}", need.split("-> ", 1)[-1])
        self.write_status()

    def write_status(self):
        doc = {"pid": os.getpid(), "heartbeat": time.time(), "poll": POLL,
               "agents": {n: {"started": a.started, "need": a.need, "log": a.out} for n, a in self.agents.items()},
               "queue": [q[0] for q in self.queue],
               "remotes": self.last_states,
               "held": sorted({n for (n, _k), t in self.tries.items() if t[2] > time.time()})}
        tmp = STATUS + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
            os.replace(tmp, STATUS)
        except OSError:
            pass


def main():
    if "--once" in sys.argv:
        Live().tick(dry=True)
        return 0
    lock = single_instance()
    if not lock:
        return 3                                  # already running
    log(f"live watcher started (pid {os.getpid()}, check every {POLL} s)")
    live = Live()
    checked = 0.0
    while True:
        if time.time() - checked > 60:
            checked = time.time()
            if task_disabled():
                log("live watcher stopped: task 'F2 Watchdog' is disabled")
                return 0
        try:
            live.tick()
        except Exception as e:                    # noqa: BLE001 - never die; log and keep watching
            log(f"live watcher error: {e!r}")
        time.sleep(POLL)


if __name__ == "__main__":
    sys.exit(main())
