# -*- coding: utf-8 -*-
"""
core.py — داده‌ها و مدیریت ریموت‌ها برای پنل (بدون رابط گرافیکی).

- خواندن/نوشتن اکانت‌ها از CSV و ذخیره در data/accounts.json
- گروه‌بندی اکانت‌ها بر حسب کنسول (یک ریموت به ازای هر کنسول، نه هر اکانت)
- استارت/استاپ ریموت xbrp برای هر کنسول، با توکن جدای همان اکانت
"""
from __future__ import annotations

import contextlib
import copy
import csv
import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
TOKENS_DIR = HERE / "tokens"
LOGS_DIR = HERE / "logs"
for d in (DATA_DIR, TOKENS_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)

ACCOUNTS_FILE = DATA_DIR / "accounts.json"
STATE_FILE = DATA_DIR / "state.json"
SBCS_FILE = DATA_DIR / "sbcs.json"           # desired SBC list (name + enabled)
PROGRESS_FILE = DATA_DIR / "sbc_progress.json"  # per-ACCOUNT completed SBCs (written by the bot)
ACTIVE_FILE = DATA_DIR / "active.json"       # which account the bot is running right now
ACCOUNT_STATUS_FILE = DATA_DIR / "account_status.json"  # per account: last bot error + out-of-coins flag
LOCK_FILE = DATA_DIR / ".data.lock"          # one lock for every shared data file (panel + all bots)


# ---------- safe shared JSON (the panel and every bot read/write these files at once) ----------
# - data_lock(): cross-process lock (msvcrt byte lock on LOCK_FILE), re-entrant inside one thread.
# - write_json(): atomic (temp file + os.replace), so a reader never sees a half-written file.
# - read_json(): retries a broken read (an old writer mid-write) and falls back to the last good copy,
#   so a failed read never looks like "empty" and never gets saved back over the real data.

_tl = threading.local()
_tlock = threading.RLock()
_cache: dict = {}        # path -> last good parsed value
_stat_cache: dict = {}   # path -> ((mtime_ns, size), parsed): skip re-reading an unchanged file


@contextlib.contextmanager
def data_lock(timeout: float = 10.0):
    depth = getattr(_tl, "depth", 0)
    if depth:
        _tl.depth = depth + 1
        try:
            yield
        finally:
            _tl.depth -= 1
        return
    with _tlock:
        import msvcrt
        f = open(LOCK_FILE, "a+b")
        locked = False
        try:
            end = time.time() + timeout
            while True:
                try:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                except OSError:
                    if time.time() > end:
                        break            # never hang the bot: go on without the lock
                    time.sleep(0.02)
            _tl.depth = 1
            yield
        finally:
            _tl.depth = 0
            if locked:
                try:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            f.close()


class DataReadError(Exception):
    pass


def read_json(path, default, strict: bool = False):
    """Parsed JSON of path; default when the file does not exist.
    A broken read is retried; then the last good copy is returned (strict=True raises instead)."""
    path = Path(path)
    key = str(path)
    for attempt in range(6):
        try:
            st = path.stat()
        except FileNotFoundError:
            return default
        except OSError:
            time.sleep(0.05)
            continue
        sig = (st.st_mtime_ns, st.st_size)
        hit = _stat_cache.get(key)
        if hit is not None and hit[0] == sig:          # unchanged on disk: no read, no parse
            return copy.deepcopy(hit[1])
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            _cache[key] = data
            _stat_cache[key] = (sig, data)
            return copy.deepcopy(data)
        except (OSError, ValueError):
            time.sleep(0.05)
    if strict:
        raise DataReadError(f"cannot read {path.name}")
    return copy.deepcopy(_cache.get(key, default))


def write_json(path, data) -> None:
    path = Path(path)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    for attempt in range(40):
        try:
            os.replace(tmp, path)
            _cache[str(path)] = data
            return
        except PermissionError:          # a reader has it open right now
            time.sleep(0.05)
    try:
        path.write_text(text, encoding="utf-8")
        _cache[str(path)] = data
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def update_json(path, fn, default):
    """Locked read-modify-write: fn(data) changes data in place (or returns a new value)."""
    with data_lock():
        data = read_json(path, default, strict=True)
        out = fn(data)
        if out is not None:
            data = out
        write_json(path, data)
        return data


# ---------- remote name -> console ----------
# xbrp names a second remote of the same -ctlname "C32-2", "C32-3"... Everything stored for the panel
# (accounts, active.json, progress, reports) is keyed by the CONSOLE, so strip that suffix.

def console_of(name: str, known=None) -> str:
    name = (name or "").strip()
    if not name:
        return name
    if known is None:
        known = {(a.Console or "").strip() for a in load_accounts() if a.Console}
    low = {k.lower(): k for k in known}
    if name.lower() in low:
        return low[name.lower()]
    base = re.sub(r"-\d+$", "", name)
    if base.lower() in low:
        return low[base.lower()]
    return base

import re as _re

# An SBC entry = {"set": str, "challenge": str, "csv": str, "enabled": bool}.
# Single-challenge SBC: challenge and csv are empty, only the set name matters.
# The matching key used for progress = sbc_name(entry).


def sbc_name(entry: dict) -> str:
    """Unique name used to match the bot's progress. 'Set Challenge' or just 'Set'."""
    s = (entry.get("set") or entry.get("name") or "").strip()
    c = (entry.get("challenge") or "").strip()
    return f"{s} {c}".strip() if c else s


def discover_marquees() -> list[dict]:
    """The Marquee challenges we have = Marquee{n}.csv files in MARQUEE_DIR."""
    found = []
    try:
        for p in MARQUEE_DIR.glob("Marquee*.csv"):
            m = _re.match(r"(?i)marquee\s*(\d+)", p.stem)
            if m:
                found.append((int(m.group(1)), str(p)))
    except Exception:
        pass
    found.sort()
    return [{"set": "Marquee", "challenge": str(n), "csv": path, "enabled": True}
            for n, path in found]


def default_sbcs() -> list[dict]:
    return discover_marquees() or [{"set": "Marquee", "challenge": "", "csv": "", "enabled": True}]

# محل ریموت (xbrp چندحسابه با فلگ -token)
XBRP_DIR = Path(r"C:\Users\Reach\Desktop\New Remote\CPU Decode")
XBRP_EXE = XBRP_DIR / "xbrp-multi.exe"   # اگر نبود، به xbrp.exe برمی‌گردد

# محل CSVهای Marquee که Play.py می‌خواند (Marquee1.csv .. MarqueeN.csv)
MARQUEE_DIR = Path(r"C:\Users\Reach\Desktop\New Remote")

# ===== حالت «یک ریموت ثابت برای هر کنسول» =====
# True : هر کنسول یک ریموت دارد که همیشه با «اکانت ریموت» همان کنسول باز است (ستون Remote در CSV؛
#        اگر هیچ ردیفی علامت نداشت، اولین اکانت آن کنسول). اکانت‌های بازی روی کنسول دستی عوض می‌شوند؛
#        ربات (Play.py) خودش اکانت‌ها را یکی‌یکی می‌رود و گیمرتگ Home را چک می‌کند.
# False: حالت قبلی — پنل برای هر اکانت ریموت را می‌بندد و با توکن اکانت بعدی باز می‌کند.
SHARED_REMOTE = True

CSV_FIELDS = ["Console", "Gamertag", "MicrosoftEmail", "MicrosoftPass", "MicrosoftGauth",
              "EAEmail", "EAPass", "EAGauth", "Platform", "Remote"]
SECRET_FIELDS = {"MicrosoftPass", "MicrosoftGauth", "EAPass", "EAGauth"}

# Accepted CSV header spellings for a field (besides the exact name, case-insensitive).
CSV_ALIASES = {
    "Gamertag": {"gamertag", "xboxgamertag", "xbox gamertag", "gamer tag", "gt", "xbl", "xboxgt"},
    "Remote": {"remote", "remote account", "remoteaccount", "stream", "host", "ریموت"},
}


@dataclass
class Account:
    Console: str = ""
    Gamertag: str = ""
    MicrosoftEmail: str = ""
    MicrosoftPass: str = ""
    MicrosoftGauth: str = ""
    EAEmail: str = ""
    EAPass: str = ""
    EAGauth: str = ""
    Platform: str = ""
    Remote: str = ""          # yes / 1 / x = the remote (stream) of this console signs in with this account

    def key(self) -> str:
        return (self.MicrosoftEmail or self.EAEmail or self.Gamertag or "").strip().lower()

    def is_remote(self) -> bool:
        return (self.Remote or "").strip().lower() in ("1", "y", "yes", "x", "true", "remote", "✓", "بله")

    def label(self) -> str:
        return (self.Gamertag or "").strip() or self.MicrosoftEmail or self.EAEmail or "?"


def remote_account(accounts: list["Account"]) -> Optional["Account"]:
    """The account the remote of a console signs in with: the row marked in the Remote column,
    else the first account of that console."""
    for a in accounts:
        if a.is_remote():
            return a
    return accounts[0] if accounts else None


# ---------- gamertag on the Xbox Home screen (SHARED_REMOTE: which account is on the console) ----------

def _letters(s: str) -> str:
    return _re.sub(r"[^a-z]", "", (s or "").lower())


def gamertag_names(a: "Account") -> list[str]:
    """Names that may appear as this account's gamertag on Home: Gamertag column and the part of each
    email before @ (only letters compared, so 'phan_tyra83' == 'phan tyra')."""
    names = [a.Gamertag] + [e.split("@")[0] for e in (a.MicrosoftEmail, a.EAEmail) if e and "@" in e]
    out = []
    for n in names:
        n = _letters(n)
        if len(n) >= 3 and n not in out:
            out.append(n)
    return out


def gamertag_matches(text: str, a: "Account", fuzzy: float = 0.75) -> bool:
    """True when OCR text from the Home gamertag box is this account (tolerates OCR slips like p→O, y→v)."""
    from difflib import SequenceMatcher
    t = _letters(text)
    if len(t) < 3:
        return False
    for n in gamertag_names(a):
        if t == n or SequenceMatcher(None, t, n).ratio() >= fuzzy:
            return True
    return False


def load_accounts() -> list[Account]:
    try:
        rows = read_json(ACCOUNTS_FILE, [])
        return [Account(**{k: r.get(k, "") for k in CSV_FIELDS}) for r in rows]
    except Exception:
        return []


def save_accounts(accounts: list[Account]) -> None:
    with data_lock():
        write_json(ACCOUNTS_FILE, [asdict(a) for a in accounts])


def import_csv(path: str | Path, replace: bool = True) -> list[Account]:
    """CSV را می‌خواند. سرستون‌ها نسبت به حروف بزرگ/کوچک و فاصله مقاوم‌اند."""
    path = Path(path)
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        norm = {}
        for name in (reader.fieldnames or []):
            key = name.strip().lower()
            for want in CSV_FIELDS:
                if key == want.lower() or key in CSV_ALIASES.get(want, set()):
                    norm[name] = want
                    break
        out: list[Account] = []
        for row in reader:
            data = {}
            for raw, want in norm.items():
                data[want] = (row.get(raw) or "").strip()
            if not any(data.values()):
                continue
            if not data.get("EAEmail"):            # EA email empty -> use the Microsoft email
                data["EAEmail"] = data.get("MicrosoftEmail", "")
            out.append(Account(**{k: data.get(k, "") for k in CSV_FIELDS}))
    if replace:
        save_accounts(out)
        return out
    existing = load_accounts()
    existing.extend(out)
    save_accounts(existing)
    return existing


def write_template_csv(path: str | Path) -> None:
    path = Path(path)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_FIELDS)
        w.writerow(["1", "MyGamerTag", "example@outlook.com", "Password123", "ABCDEF1234567890",
                    "ea@example.com", "EaPass123", "", "Xbox", "yes"])   # Remote: yes = remote signs in with this one


# ---------- گروه‌بندی بر حسب کنسول ----------

def consoles(accounts: list[Account]) -> dict[str, list[Account]]:
    """نگاشت شماره‌ی کنسول → لیست اکانت‌هایی که آن کنسول را دارند (به ترتیب ورود)."""
    groups: dict[str, list[Account]] = {}
    for a in accounts:
        c = (a.Console or "").strip()
        if not c:
            continue
        groups.setdefault(c, []).append(a)
    return groups


# ---------- وضعیت انتخاب اکانت برای هر کنسول ----------

def load_state() -> dict:
    d = read_json(STATE_FILE, {})
    return d if isinstance(d, dict) else {}


def save_state(state: dict) -> None:
    with data_lock():
        write_json(STATE_FILE, state)


# ---------- SBC list (desired challenges + enable flag) ----------

def _normalize_sbc(r) -> Optional[dict]:
    """Accept old ({'name',...}) and new ({'set','challenge','csv',...}) shapes."""
    if isinstance(r, str):
        return {"set": r, "challenge": "", "csv": "", "enabled": True}
    if not isinstance(r, dict):
        return None
    s = str(r.get("set") or r.get("name") or "").strip()
    if not s:
        return None
    return {"set": s,
            "challenge": str(r.get("challenge") or "").strip(),
            "csv": str(r.get("csv") or "").strip(),
            "enabled": bool(r.get("enabled", True))}


def load_sbcs() -> list[dict]:
    """List of {'set','challenge','csv','enabled'}. Seeds the Marquee CSVs the first time."""
    if SBCS_FILE.exists():
        try:
            rows = read_json(SBCS_FILE, None, strict=True)
        except DataReadError:
            return []                    # unreadable right now: never re-seed over the user's list
        out = [e for e in (_normalize_sbc(r) for r in (rows or [])) if e]
        if out:
            return out
    seed = default_sbcs()
    save_sbcs(seed)
    return [dict(s) for s in seed]


def sync_marquees(sbcs: list[dict]) -> list[dict]:
    """Add any Marquee{n}.csv that is not already in the list (enabled by default)."""
    have = {sbc_name(s).lower() for s in sbcs}
    for e in discover_marquees():
        if sbc_name(e).lower() not in have:
            sbcs.append(e)
    return sbcs


def save_sbcs(sbcs: list[dict]) -> None:
    clean = [e for e in (_normalize_sbc(s) for s in sbcs) if e]
    with data_lock():
        write_json(SBCS_FILE, clean)


def enabled_sbc_names() -> list[str]:
    return [sbc_name(s) for s in load_sbcs() if s.get("enabled", True)]


# ---------- per-ACCOUNT SBC progress (written by the bot) ----------
# Keyed by the account's key (Microsoft email, lowercased). Multiple accounts can
# share a console, so progress is per account, not per console.

def acct_slug(key: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in (key or "").lower())[:80]


def load_progress() -> dict:
    """{'<account_key>': {'done': ['Marquee Matchups 1', ...]}}."""
    d = read_json(PROGRESS_FILE, {})
    return d if isinstance(d, dict) else {}


def save_progress(progress: dict) -> None:
    with data_lock():
        write_json(PROGRESS_FILE, progress)


def mark_sbc_done(account_key: str, sbc_name: str) -> None:
    """Called (via report.py) when an SBC is completed for the active account."""
    def add(prog):
        done = prog.setdefault(account_key, {}).setdefault("done", [])
        if sbc_name not in done:
            done.append(sbc_name)
    update_json(PROGRESS_FILE, add, {})


def reset_progress(account_keys) -> None:
    """Locked: forget the completed SBCs of these accounts."""
    def drop(prog):
        for k in account_keys:
            prog.pop(k, None)
    update_json(PROGRESS_FILE, drop, {})


def done_count(account_key: str) -> tuple[int, int]:
    """(# of enabled SBCs completed by this account, # of enabled SBCs)."""
    enabled = enabled_sbc_names()
    done = set(load_progress().get(account_key, {}).get("done", []))
    got = sum(1 for n in enabled if n in done)
    return got, len(enabled)


def is_complete(account_key: str) -> bool:
    """True when this account has done every enabled SBC."""
    got, total = done_count(account_key)
    return total > 0 and got >= total


def console_complete(accounts: list["Account"]) -> bool:
    """True when every account on a console is complete (nothing left to run)."""
    keys = [a.key() for a in accounts if a.key()]
    return bool(keys) and all(is_complete(k) for k in keys)


def next_account(accounts: list["Account"], after_key: str = "") -> Optional["Account"]:
    """First account (after `after_key`) that is not complete yet, else None."""
    order = [a for a in accounts if a.key()]
    start = 0
    if after_key:
        for i, a in enumerate(order):
            if a.key() == after_key:
                start = i + 1
                break
    ring = order[start:] + order[:start]
    for a in ring:
        if not is_complete(a.key()):
            return a
    return None


# ---------- per-account bot status: last error + out of coins (written by the bot) ----------
# account_status.json = {account_key: {"last_error": {"kind","text","at"}, "no_coins": {"text","at"},
#                                      "coins": {"start","start_at","end","end_at"}}}
# kind: error | pause | stop | crash | coins. Text is English (the panel UI is English).

def load_account_status() -> dict:
    d = read_json(ACCOUNT_STATUS_FILE, {})
    return d if isinstance(d, dict) else {}


def set_last_error(account_key: str, text: str, kind: str = "error") -> None:
    if not account_key:
        return
    entry = {"kind": kind, "text": (text or "").strip()[:300], "at": time.time()}

    def put(d):
        d.setdefault(account_key, {})["last_error"] = entry
    update_json(ACCOUNT_STATUS_FILE, put, {})


def set_no_coins(account_key: str, text: str = "") -> None:
    """The bot found this account out of coins: recorded for the panel; Auto skips it until cleared."""
    if not account_key:
        return
    now = time.time()
    msg = ("Out of coins" + (f" ({text})" if text else "")).strip()[:300]

    def put(d):
        e = d.setdefault(account_key, {})
        e["no_coins"] = {"text": msg, "at": now}
        e["last_error"] = {"kind": "coins", "text": msg, "at": now}
    update_json(ACCOUNT_STATUS_FILE, put, {})


def set_coins(account_key: str, coins, start: bool = False) -> None:
    """My Coins read by the bot in the Transfer Market.
    start=True (first read of this account in this bot run) -> Start Coin, and End Coin is cleared (new run);
    every read -> Coin (current).  End Coin is written by finish_coins when the account's run ends.
    account_status.json[key]["coins"] = {start, start_at, now, now_at, end, end_at}."""
    if not account_key or coins is None:
        return
    t = time.time()

    def put(d):
        c = d.setdefault(account_key, {}).setdefault("coins", {})
        if start or "start" not in c:
            c["start"], c["start_at"] = int(coins), t
            c.pop("end", None); c.pop("end_at", None)
        c["now"], c["now_at"] = int(coins), t
    update_json(ACCOUNT_STATUS_FILE, put, {})


def finish_coins(account_key: str) -> None:
    """The bot's run of this account ended (done, out of coins or stopped): End Coin = current Coin."""
    if not account_key:
        return

    def put(d):
        c = (d.get(account_key) or {}).get("coins")
        if c and "now" in c:
            c["end"], c["end_at"] = c["now"], time.time()
    update_json(ACCOUNT_STATUS_FILE, put, {})


def has_no_coins(account_key: str) -> bool:
    return bool(load_account_status().get(account_key, {}).get("no_coins"))


def clear_account_status(account_keys=None) -> None:
    """Forget last error + out-of-coins of these accounts (None = every account). Start/End coins are kept."""
    def drop(d):
        for k in (list(d) if account_keys is None else account_keys):
            e = d.get(k)
            coins = e.get("coins") if isinstance(e, dict) else None
            if coins:
                d[k] = {"coins": coins}
            else:
                d.pop(k, None)
    update_json(ACCOUNT_STATUS_FILE, drop, {})


# ---------- which account the bot is running right now (one at a time) ----------

# active.json = {console: {"account", "console", "gamertag", "email", "at"}} — one entry PER CONSOLE.
# (It used to hold a single account for the whole panel, so with two consoles running the bot of one
#  console credited its SBCs to the account last started on the other console.)

def _read_active() -> dict:
    return _norm_active(read_json(ACTIVE_FILE, {}))


def _norm_active(data) -> dict:
    if isinstance(data, dict) and "account" in data:          # old single-account format
        return {data.get("console") or "": data}
    return data if isinstance(data, dict) else {}


def _write_active(data: dict) -> None:
    with data_lock():
        write_json(ACTIVE_FILE, data)


def set_active(account: "Account", console: str) -> None:
    console = console_of(console)
    entry = {
        "account": account.key(), "console": console,
        "gamertag": account.Gamertag, "email": account.MicrosoftEmail,
        "at": time.time(),
    }

    def put(data):
        data = _norm_active(data)
        data[console] = entry
        return data
    update_json(ACTIVE_FILE, put, {})


def get_active(console: str = "") -> dict:
    """Active account entry of one console, or {console: entry} for all when console is empty."""
    data = _read_active()
    return data.get(console_of(console), {}) if console else data


def clear_active(console: str = "") -> None:
    """Forget the active account of one console (or of all consoles when console is empty)."""
    try:
        if not console:
            ACTIVE_FILE.unlink(missing_ok=True)
            return
        console = console_of(console)

        def drop(data):
            data = _norm_active(data)
            data.pop(console, None)
            return data
        update_json(ACTIVE_FILE, drop, {})
    except Exception:
        pass


# ---------- مدیریت یک ریموت در حال اجرا ----------

@dataclass
class Remote:
    console: str
    account: Account
    proc: Optional[subprocess.Popen] = None
    status: str = "stopped"      # stopped | login | running | error | exited
    message: str = ""
    started_at: float = 0.0

    def token_path(self) -> Path:
        # token is per ACCOUNT (each account has its own Microsoft login)
        return TOKENS_DIR / f"acct_{acct_slug(self.account.key())}.json"

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def has_token(self) -> bool:
        return self.token_path().exists()

    def uptime(self) -> str:
        if not self.started_at:
            return "-"
        s = int(time.time() - self.started_at)
        return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"

    def platform_is_series(self) -> bool:
        """Platform column -> xbrp -xs flag. 'One'/'Xbox One' => One (False); else Series (True)."""
        p = (self.account.Platform or "").strip().lower()
        if "one" in p:
            return False
        return True

    def launch_xbrp(self, window="1280x720", drawfps=5, preset="cpu", minimized=True):
        exe = XBRP_EXE if XBRP_EXE.exists() else (XBRP_DIR / "xbrp.exe")
        args = [
            str(exe),
            "-token", str(self.token_path()),
            "-preset", preset,
            "-panel",
            "-window", window,
            "-drawfps", str(drawfps),
            "-label", self.console,
            "-ctlname", self.console,
            f"-xs={'true' if self.platform_is_series() else 'false'}",
        ]
        creation = 0
        if os.name == "nt":
            creation = subprocess.CREATE_NEW_PROCESS_GROUP
        self.proc = subprocess.Popen(args, cwd=str(XBRP_DIR), creationflags=creation)
        self.status = "running"
        self.started_at = time.time()
        self.message = f"PID {self.proc.pid}"

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except Exception:
                    self.proc.kill()
            except Exception:
                pass
        self.status = "stopped"
        self.message = ""
        self.started_at = 0.0
