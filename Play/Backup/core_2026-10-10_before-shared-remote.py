# -*- coding: utf-8 -*-
"""
core.py — داده‌ها و مدیریت ریموت‌ها برای پنل (بدون رابط گرافیکی).

- خواندن/نوشتن اکانت‌ها از CSV و ذخیره در data/accounts.json
- گروه‌بندی اکانت‌ها بر حسب کنسول (یک ریموت به ازای هر کنسول، نه هر اکانت)
- استارت/استاپ ریموت xbrp برای هر کنسول، با توکن جدای همان اکانت
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
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

CSV_FIELDS = ["Console", "Gamertag", "MicrosoftEmail", "MicrosoftPass", "MicrosoftGauth",
              "EAEmail", "EAPass", "EAGauth", "Platform"]
SECRET_FIELDS = {"MicrosoftPass", "MicrosoftGauth", "EAPass", "EAGauth"}

# Accepted CSV header spellings for a field (besides the exact name, case-insensitive).
CSV_ALIASES = {
    "Gamertag": {"gamertag", "xboxgamertag", "xbox gamertag", "gamer tag", "gt", "xbl", "xboxgt"},
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

    def key(self) -> str:
        return (self.MicrosoftEmail or self.EAEmail or self.Gamertag or "").strip().lower()


def load_accounts() -> list[Account]:
    if ACCOUNTS_FILE.exists():
        try:
            rows = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
            return [Account(**{k: r.get(k, "") for k in CSV_FIELDS}) for r in rows]
        except Exception:
            return []
    return []


def save_accounts(accounts: list[Account]) -> None:
    ACCOUNTS_FILE.write_text(
        json.dumps([asdict(a) for a in accounts], ensure_ascii=False, indent=2),
        encoding="utf-8")


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
                    "ea@example.com", "EaPass123", "", "Xbox"])


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
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


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
            rows = json.loads(SBCS_FILE.read_text(encoding="utf-8"))
            out = [e for e in (_normalize_sbc(r) for r in rows) if e]
            if out:
                return out
        except Exception:
            pass
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
    SBCS_FILE.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")


def enabled_sbc_names() -> list[str]:
    return [sbc_name(s) for s in load_sbcs() if s.get("enabled", True)]


# ---------- per-ACCOUNT SBC progress (written by the bot) ----------
# Keyed by the account's key (Microsoft email, lowercased). Multiple accounts can
# share a console, so progress is per account, not per console.

def acct_slug(key: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in (key or "").lower())[:80]


def load_progress() -> dict:
    """{'<account_key>': {'done': ['Marquee Matchups 1', ...]}}."""
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_progress(progress: dict) -> None:
    PROGRESS_FILE.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def mark_sbc_done(account_key: str, sbc_name: str) -> None:
    """Called (via report.py) when an SBC is completed for the active account."""
    prog = load_progress()
    done = prog.setdefault(account_key, {}).setdefault("done", [])
    if sbc_name not in done:
        done.append(sbc_name)
    save_progress(prog)


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


# ---------- which account the bot is running right now (one at a time) ----------

# active.json = {console: {"account", "console", "gamertag", "email", "at"}} — one entry PER CONSOLE.
# (It used to hold a single account for the whole panel, so with two consoles running the bot of one
#  console credited its SBCs to the account last started on the other console.)

def _read_active() -> dict:
    if not ACTIVE_FILE.exists():
        return {}
    try:
        data = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(data, dict) and "account" in data:          # old single-account format
        return {data.get("console") or "": data}
    return data if isinstance(data, dict) else {}


def _write_active(data: dict) -> None:
    ACTIVE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def set_active(account: "Account", console: str) -> None:
    data = _read_active()
    data[console] = {
        "account": account.key(), "console": console,
        "gamertag": account.Gamertag, "email": account.MicrosoftEmail,
        "at": time.time(),
    }
    _write_active(data)


def get_active(console: str = "") -> dict:
    """Active account entry of one console, or {console: entry} for all when console is empty."""
    data = _read_active()
    return data.get(console, {}) if console else data


def clear_active(console: str = "") -> None:
    """Forget the active account of one console (or of all consoles when console is empty)."""
    try:
        if not console:
            ACTIVE_FILE.unlink(missing_ok=True)
            return
        data = _read_active()
        if data.pop(console, None) is not None:
            _write_active(data)
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
