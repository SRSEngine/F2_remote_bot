# -*- coding: utf-8 -*-
"""
xbox.py - press Xbox controller buttons on a running xbrp remote.

    import xbox
    xbox.setup(remote="XBOX", method="pipe")   # once, at the top
    A()            # tap A
    A(500)         # hold A for 500 ms
    Down(); Down(); A()

Methods (all tested 2026-10-02):
    "pipe"    named pipe            fastest, recommended
    "udp"     local UDP
    "wmcopy"  WM_COPYDATA window message
    "tcp"     local TCP
    "keys"    keyboard keys posted to the remote window (sticks/triggers only all-or-nothing)
    "xinput"  virtual Xbox 360 pad (ViGEmBus + ViGEmClient.dll)
    "cloud"   Xbox Live InjectKey: no remote needed, ~1.3 s, only A B X Y Up Down Left Right Xbox Menu View

Every remote has its own endpoints (Controller\\remotes\\<console>.json), so buttons only reach the
console of the remote you named in setup(). For several consoles use Pad objects:
    p1 = xbox.Pad("XBOX", "pipe"); p2 = xbox.Pad("XBOX2", "pipe"); p1.A(); p2.B()
No extra Python packages are needed.
"""

import ctypes
import ctypes.wintypes as wt
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REMOTES_DIR = os.path.join(HERE, "remotes")
TOKEN_FILE = os.path.join(HERE, "..", "CPU Decode", "xbrp_token.json")

HOLD_MS = 80   # how long a tap holds the button
GAP_MS = 60    # pause after each tap, so two taps never merge into one long press

METHODS = ("pipe", "udp", "wmcopy", "tcp", "keys", "xinput", "cloud")

# کنترل ربات از پنل ریموت: لاگ، شروع / توقف موقت / توقف، اتصال دوباره (remotectl.py کنار همین فایل)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from remotectl import Control, BotStopped, RemoteDown  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def _sleep_ms(ms):
    if ms > 0:
        time.sleep(ms / 1000.0)


def _pid_alive(pid):
    """True if the process still runs (a remote that crashed can leave its .json behind)."""
    if not pid:
        return True  # unknown: assume yes
    h = kernel32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = wt.DWORD()
    ok = kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    kernel32.CloseHandle(h)
    return bool(ok) and code.value == 259  # STILL_ACTIVE


def _remote_info(name):
    """Find the running remote for a name or console name.

    When a remote is closed and opened again while this program still holds the old connection,
    the new one gets another name (XBOX-2, XBOX-3, ...). So: exact name first, then any running
    remote of that console, newest first.
    """
    want = name.lower()
    exact, same_console, found = None, [], []
    for f in os.listdir(REMOTES_DIR) if os.path.isdir(REMOTES_DIR) else []:
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(REMOTES_DIR, f), encoding="utf-8") as fh:
                info = json.load(fh)
        except (OSError, ValueError):
            continue
        if not _pid_alive(info.get("pid")):
            continue
        found.append(f[:-5])
        if info.get("name", f[:-5]).lower() == want:
            exact = info
        elif info.get("console", "").lower() == want or info.get("name", "").lower().startswith(want + "-"):
            same_console.append(info)
    if exact:
        return exact
    if same_console:
        return max(same_console, key=lambda i: i.get("started", ""))
    raise RuntimeError("remote %r is not running (running: %s)" % (name, ", ".join(found) or "none"))


# ---------------- transports: send(text) -> reply ----------------

class _Pipe:
    def __init__(self, info):
        self.path = info["pipe"]
        self.f = None

    def send(self, line):
        for attempt in range(2):
            try:
                if self.f is None:
                    self.f = open(self.path, "r+b", buffering=0)
                self.f.write((line + "\n").encode())
                return self.f.read(4096).decode().strip()
            except OSError:
                self.close()
                if attempt:
                    raise
                time.sleep(0.05)

    def close(self):
        if self.f:
            try:
                self.f.close()
            except OSError:
                pass
        self.f = None


class _TCP:
    def __init__(self, info):
        host, port = info["tcp"].rsplit(":", 1)
        self.addr = (host, int(port))
        self.s = None
        self.buf = b""

    def send(self, line):
        if self.s is None:
            self.s = socket.create_connection(self.addr, timeout=3)
            self.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.s.sendall((line + "\n").encode())
        while b"\n" not in self.buf:
            self.buf += self.s.recv(4096)
        out, self.buf = self.buf.split(b"\n", 1)
        return out.decode().strip()

    def close(self):
        if self.s:
            self.s.close()
        self.s = None


class _UDP:
    def __init__(self, info):
        host, port = info["udp"].rsplit(":", 1)
        self.addr = (host, int(port))
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.settimeout(2)

    def send(self, line):
        self.s.sendto(line.encode(), self.addr)
        return self.s.recvfrom(2048)[0].decode()

    def close(self):
        self.s.close()


class _COPYDATA(ctypes.Structure):
    _fields_ = [("dwData", ctypes.c_size_t), ("cbData", wt.DWORD), ("lpData", ctypes.c_void_p)]


user32.SendMessageTimeoutW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, ctypes.c_void_p, wt.UINT, wt.UINT,
                                       ctypes.POINTER(ctypes.c_size_t)]
user32.SendMessageTimeoutW.restype = ctypes.c_size_t
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.MapVirtualKeyW.argtypes = [wt.UINT, wt.UINT]


class _WMCopy:
    def __init__(self, info):
        self.hwnd = info["hwnd"]

    def send(self, line):
        data = ctypes.create_string_buffer(line.encode())
        cds = _COPYDATA(0x50524258, len(line.encode()), ctypes.cast(data, ctypes.c_void_p))
        res = ctypes.c_size_t(0)
        ok = user32.SendMessageTimeoutW(self.hwnd, 0x004A, 0, ctypes.byref(cds), 0x0002, 3000, ctypes.byref(res))
        if not ok:
            raise RuntimeError("remote window does not answer")
        return "ok" if res.value == 1 else "err"

    def close(self):
        pass


# ---------------- the pad ----------------

_BUTTONS = {"a", "b", "x", "y", "up", "down", "left", "right", "lb", "rb", "lt", "rt", "ls", "rs",
            "view", "menu", "nexus", "lsup", "lsdown", "lsleft", "lsright", "rsup", "rsdown", "rsleft", "rsright"}

_KEY_VK = {"up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "a": 0x0D, "b": 0x1B, "x": ord("X"), "y": ord("Y"),
           "lb": ord("Q"), "rb": ord("E"), "lt": ord("Z"), "rt": ord("C"), "lsup": ord("W"), "lsdown": ord("S"),
           "lsleft": ord("A"), "lsright": ord("D"), "rsup": ord("I"), "rsdown": ord("K"), "rsleft": ord("J"),
           "rsright": ord("L"), "ls": ord("F"), "rs": ord("H"), "view": 0x09, "menu": ord("M"), "nexus": ord("G")}

_XUSB = {"up": 0x0001, "down": 0x0002, "left": 0x0004, "right": 0x0008, "menu": 0x0010, "view": 0x0020,
         "ls": 0x0040, "rs": 0x0080, "lb": 0x0100, "rb": 0x0200, "nexus": 0x0400,
         "a": 0x1000, "b": 0x2000, "x": 0x4000, "y": 0x8000}

_CLOUD = {"a": "A", "b": "B", "x": "X", "y": "Y", "up": "Up", "down": "Down", "left": "Left", "right": "Right",
          "nexus": "Nexus", "menu": "Menu", "view": "View"}


class _XUSBReport(ctypes.Structure):
    _fields_ = [("wButtons", ctypes.c_ushort), ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte),
                ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short),
                ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short)]


class Pad:
    """One remote + one method. Use the module functions for the common single-remote case."""

    def __init__(self, remote="XBOX", method="pipe"):
        method = method.lower()
        if method not in METHODS:
            raise ValueError("method must be one of " + ", ".join(METHODS))
        self.method = method
        self.remote = remote
        self.info = _remote_info(remote) if method != "cloud" or os.path.exists(os.path.join(REMOTES_DIR, remote + ".json")) else {}
        self._ctl = None
        # لاگ و وضعیت ربات روی یک اتصال pipe جدا (برای همه‌ی روش‌ها، اگر ریموت pipe دارد)
        # روش pipe: همان اتصال دکمه‌ها (ریموت فقط چند اتصال هم‌زمان دارد)؛ بقیه‌ی روش‌ها: اتصال pipe جدا
        if method == "pipe":
            self.ctl = Control(self._raw)
        else:
            self.ctl = Control(self._control if self.info.get("pipe") else (lambda line: "err unknown"))
        if method == "pipe":
            self._t = _Pipe(self.info)
        elif method == "tcp":
            self._t = _TCP(self.info)
        elif method == "udp":
            self._t = _UDP(self.info)
        elif method == "wmcopy":
            self._t = _WMCopy(self.info)
        elif method == "keys":
            self._ctl = _Pipe(self.info)
            self._ctl.send("keys on")  # the remote accepts keyboard keys from now on
            self.hwnd = self.info["hwnd"]
        elif method == "xinput":
            self._xinput_start()
        elif method == "cloud":
            self._cloud_auth = None
            self._console_id = self.info.get("serverId") or remote

    # ----- button pressing -----

    def press(self, *names, hold=None, wait=True):
        """Tap one or more buttons together. hold = ms (default HOLD_MS)."""
        hold = HOLD_MS if hold is None else hold
        keys = self._names(names)
        self.ctl.checkpoint("دکمه " + "+".join(k.upper() for k in keys))
        if self.method in ("pipe", "tcp", "udp", "wmcopy"):
            self._cmd("press %s %d" % ("+".join(keys), hold))
            if wait:
                _sleep_ms(hold + GAP_MS)
        elif self.method == "cloud":
            for k in keys:
                self._cloud_key(k)
        else:
            self.down(*keys)
            _sleep_ms(hold)
            self.up(*keys)
            if wait:
                _sleep_ms(GAP_MS)

    def down(self, *names):
        """Hold buttons until up() is called."""
        keys = self._names(names)
        self.ctl.checkpoint("نگه‌داشتن " + "+".join(k.upper() for k in keys))
        if self.method in ("pipe", "tcp", "udp", "wmcopy"):
            self._cmd("down " + "+".join(keys))
        elif self.method == "keys":
            for k in keys:
                user32.PostMessageW(self.hwnd, 0x0100, _KEY_VK[k], self._lparam(_KEY_VK[k], False))
        elif self.method == "xinput":
            for k in keys:
                self._xset(k, True)
            self._xupdate()
        else:
            raise RuntimeError("cloud can only tap buttons")

    def up(self, *names):
        keys = self._names(names)
        if self.method in ("pipe", "tcp", "udp", "wmcopy"):
            self._cmd("up " + "+".join(keys))
        elif self.method == "keys":
            for k in keys:
                user32.PostMessageW(self.hwnd, 0x0101, _KEY_VK[k], self._lparam(_KEY_VK[k], True))
        elif self.method == "xinput":
            for k in keys:
                self._xset(k, False)
            self._xupdate()
        else:
            raise RuntimeError("cloud can only tap buttons")

    def stick(self, side, x, y):
        """side 'L' or 'R', x and y from -1 to 1 (y = up). Stays until changed; stick('L', 0, 0) centers it."""
        self.ctl.checkpoint("استیک %s %.2f %.2f" % (side, x, y))
        if self.method in ("pipe", "tcp", "udp", "wmcopy"):
            self._cmd("stick %s %.3f %.3f" % (side, x, y))
        elif self.method == "xinput":
            fx, fy = ("sThumbLX", "sThumbLY") if side.upper().startswith("L") else ("sThumbRX", "sThumbRY")
            setattr(self._rep, fx, int(max(-1, min(1, x)) * 32767))
            setattr(self._rep, fy, int(max(-1, min(1, y)) * 32767))
            self._xupdate()
        else:
            raise RuntimeError("method %s has no analog sticks (use LsUp() etc.)" % self.method)

    def trigger(self, side, value):
        """side 'L' or 'R', value from 0 to 1. Stays until changed."""
        if self.method in ("pipe", "tcp", "udp", "wmcopy"):
            self._cmd("trigger %s %.3f" % (side, value))
        elif self.method == "xinput":
            setattr(self._rep, "bLeftTrigger" if side.upper().startswith("L") else "bRightTrigger", int(max(0, min(1, value)) * 255))
            self._xupdate()
        else:
            raise RuntimeError("method %s has no analog triggers (use LT()/RT())" % self.method)

    def release(self):
        """Let go of everything."""
        if self.method in ("pipe", "tcp", "udp", "wmcopy"):
            self._cmd("release")
        elif self.method == "xinput":
            self._rep = _XUSBReport()
            self._xupdate()
        elif self.method == "keys":
            for vk in set(_KEY_VK.values()):
                user32.PostMessageW(self.hwnd, 0x0101, vk, self._lparam(vk, True))

    def snap(self, path):
        """Save the remote's current picture as PNG."""
        return self._control("snap " + os.path.abspath(path))

    def close(self):
        if self.method == "xinput":
            self._xinput_stop()
        for t in (getattr(self, "_t", None), self._ctl):
            if t:
                t.close()

    # one function per button
    def A(self, hold=None): self.press("a", hold=hold)
    def B(self, hold=None): self.press("b", hold=hold)
    def X(self, hold=None): self.press("x", hold=hold)
    def Y(self, hold=None): self.press("y", hold=hold)
    def Up(self, hold=None): self.press("up", hold=hold)
    def Down(self, hold=None): self.press("down", hold=hold)
    def Left(self, hold=None): self.press("left", hold=hold)
    def Right(self, hold=None): self.press("right", hold=hold)
    def LB(self, hold=None): self.press("lb", hold=hold)
    def RB(self, hold=None): self.press("rb", hold=hold)
    def LT(self, hold=None): self.press("lt", hold=hold)
    def RT(self, hold=None): self.press("rt", hold=hold)
    def LS(self, hold=None): self.press("ls", hold=hold)
    def RS(self, hold=None): self.press("rs", hold=hold)
    def View(self, hold=None): self.press("view", hold=hold)
    def Menu(self, hold=None): self.press("menu", hold=hold)
    def Xbox(self, hold=None): self.press("nexus", hold=hold)
    def LsUp(self, hold=None): self.press("lsup", hold=hold)
    def LsDown(self, hold=None): self.press("lsdown", hold=hold)
    def LsLeft(self, hold=None): self.press("lsleft", hold=hold)
    def LsRight(self, hold=None): self.press("lsright", hold=hold)
    def RsUp(self, hold=None): self.press("rsup", hold=hold)
    def RsDown(self, hold=None): self.press("rsdown", hold=hold)
    def RsLeft(self, hold=None): self.press("rsleft", hold=hold)
    def RsRight(self, hold=None): self.press("rsright", hold=hold)

    # ----- internals -----

    @staticmethod
    def _names(names):
        out = []
        for n in names:
            for k in str(n).lower().replace(" ", "").split("+"):
                k = {"guide": "nexus", "xbox": "nexus", "home": "nexus", "start": "menu", "back": "view", "select": "view"}.get(k, k)
                if k not in _BUTTONS:
                    raise ValueError("unknown button %r" % n)
                out.append(k)
        return out

    def _reconnect(self):
        """The remote was closed and opened again: find it again and rebuild the connection."""
        for t in (getattr(self, "_t", None), self._ctl):
            if t is not None:
                try:
                    t.close()
                except Exception:
                    pass
        self.info = _remote_info(self.remote)
        self._ctl = None
        kinds = {"pipe": _Pipe, "tcp": _TCP, "udp": _UDP, "wmcopy": _WMCopy}
        if self.method in kinds:
            self._t = kinds[self.method](self.info)
        if self.method == "keys":
            self.hwnd = self.info["hwnd"]
            self._control("keys on")

    def _cmd(self, line):
        try:
            r = self._t.send(line)
        except (OSError, RuntimeError):  # pipe gone, socket refused/timeout, window gone
            self._reconnect()
            r = self._t.send(line)
        if not r.startswith("ok"):
            raise RuntimeError("remote said: " + r)
        return r

    def _raw(self, line):
        """یک دستور روی همان اتصال اصلی، جواب هر چه باشد (برای لاگ / وضعیت ربات)."""
        try:
            return self._t.send(line)
        except (OSError, RuntimeError):
            self._reconnect()
            return self._t.send(line)

    def _control(self, line):
        if self._ctl is None:
            self._ctl = _Pipe(self.info)
        try:
            return self._ctl.send(line)
        except OSError:  # the remote was opened again under another pipe name
            self._ctl.close()
            self.info = _remote_info(self.remote)
            self._ctl = _Pipe(self.info)
            return self._ctl.send(line)

    @staticmethod
    def _lparam(vk, up):
        sc = user32.MapVirtualKeyW(vk, 0)
        lp = 1 | (sc << 16)
        if 0x21 <= vk <= 0x28:
            lp |= 1 << 24
        if up:
            lp |= 0xC0000000
        return ctypes.c_long(lp & 0xFFFFFFFF).value

    # xinput (ViGEm virtual pad)
    def _xinput_start(self):
        self._vg = ctypes.WinDLL(os.path.join(HERE, "ViGEmClient.dll"))
        vg = self._vg
        vg.vigem_alloc.restype = ctypes.c_void_p
        vg.vigem_target_x360_alloc.restype = ctypes.c_void_p
        for f in ("vigem_connect", "vigem_target_add", "vigem_target_remove", "vigem_disconnect"):
            getattr(vg, f).restype = ctypes.c_uint
        vg.vigem_connect.argtypes = [ctypes.c_void_p]
        vg.vigem_target_add.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        vg.vigem_target_remove.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        vg.vigem_target_free.argtypes = [ctypes.c_void_p]
        vg.vigem_disconnect.argtypes = [ctypes.c_void_p]
        vg.vigem_free.argtypes = [ctypes.c_void_p]
        vg.vigem_target_x360_update.argtypes = [ctypes.c_void_p, ctypes.c_void_p, _XUSBReport]
        vg.vigem_target_x360_update.restype = ctypes.c_uint
        vg.vigem_target_x360_get_user_index.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        vg.vigem_target_x360_get_user_index.restype = ctypes.c_uint
        self._client = vg.vigem_alloc()
        if vg.vigem_connect(self._client) != 0x20000000:
            raise RuntimeError("ViGEmBus is not available")
        self._target = vg.vigem_target_x360_alloc()
        if vg.vigem_target_add(self._client, self._target) != 0x20000000:
            raise RuntimeError("could not create the virtual controller")
        idx = ctypes.c_ulong(0)
        for _ in range(20):
            time.sleep(0.05)
            if vg.vigem_target_x360_get_user_index(self._client, self._target, ctypes.byref(idx)) == 0x20000000:
                break
        self.xinput_index = idx.value
        self._rep = _XUSBReport()
        self._control("xinput %d" % self.xinput_index)  # this remote now follows our virtual pad
        time.sleep(0.6)

    def _xinput_stop(self):
        try:
            self._control("xinput off")
        except OSError:
            pass
        self._vg.vigem_target_remove(self._client, self._target)
        self._vg.vigem_target_free(self._target)
        self._vg.vigem_disconnect(self._client)
        self._vg.vigem_free(self._client)

    def _xset(self, k, down):
        if k in _XUSB:
            if down:
                self._rep.wButtons |= _XUSB[k]
            else:
                self._rep.wButtons &= ~_XUSB[k] & 0xFFFF
            return
        full = 32767 if down else 0
        m = {"lt": ("bLeftTrigger", 255 if down else 0), "rt": ("bRightTrigger", 255 if down else 0),
             "lsup": ("sThumbLY", full), "lsdown": ("sThumbLY", -full), "lsleft": ("sThumbLX", -full),
             "lsright": ("sThumbLX", full), "rsup": ("sThumbRY", full), "rsdown": ("sThumbRY", -full),
             "rsleft": ("sThumbRX", -full), "rsright": ("sThumbRX", full)}[k]
        setattr(self._rep, m[0], m[1])

    def _xupdate(self):
        self._vg.vigem_target_x360_update(self._client, self._target, self._rep)

    # cloud (Xbox Live)
    def _post_json(self, url, body, headers):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers=dict({"Content-Type": "application/json", "Accept": "application/json",
                                                   "User-Agent": "Go-http-client/1.1"}, **headers))
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise RuntimeError("%s -> HTTP %d %s" % (url, e.code, e.read()[:200])) from None

    def _cloud_login(self):
        with open(TOKEN_FILE, encoding="utf-8") as fh:
            saved = json.load(fh)
        form = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": saved["refresh_token"],
                                       "client_id": saved.get("client_id") or "000000004C12AE6F",
                                       "scope": "service::user.auth.xboxlive.com::MBI_SSL"}).encode()
        with urllib.request.urlopen("https://login.live.com/oauth20_token.srf", form, timeout=15) as r:
            t = json.loads(r.read())
        if t.get("refresh_token"):  # keep the login file current, like xbrp does
            saved["access_token"], saved["refresh_token"] = t["access_token"], t["refresh_token"]
            with open(TOKEN_FILE, "w", encoding="utf-8") as fh:
                json.dump(saved, fh, indent=2)
        ut = self._post_json("https://user.auth.xboxlive.com/user/authenticate",
                             {"RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT",
                              "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": t["access_token"]}},
                             {"x-xbl-contract-version": "1"})["Token"]
        xs = self._post_json("https://xsts.auth.xboxlive.com/xsts/authorize",
                             {"RelyingParty": "http://xboxlive.com", "TokenType": "JWT",
                              "Properties": {"SandboxId": "RETAIL", "UserTokens": [ut]}},
                             {"x-xbl-contract-version": "1"})
        self._cloud_auth = "XBL3.0 x=%s;%s" % (xs["DisplayClaims"]["xui"][0]["uhs"], xs["Token"])
        self._cloud_session = str(uuid.uuid4())
        self._cloud_time = time.time()

    def _cloud_key(self, k):
        if k not in _CLOUD:
            raise RuntimeError("cloud has no %r button (only A B X Y Up Down Left Right Xbox Menu View)" % k)
        if self._cloud_auth is None or time.time() - self._cloud_time > 3600:
            self._cloud_login()
        r = self._post_json("https://xccs.xboxlive.com/commands",
                            {"destination": "Xbox", "type": "Shell", "command": "InjectKey", "sessionId": self._cloud_session,
                             "sourceId": "com.microsoft.smartglass", "parameters": [{"keyType": _CLOUD[k]}],
                             "linkedXboxId": self._console_id},
                            {"Authorization": self._cloud_auth, "x-xbl-contract-version": "4", "skillplatform": "RemoteManagement"})
        if r.get("status", {}).get("errorCode") != "OK":
            raise RuntimeError("cloud: %s" % r.get("status"))


# ---------------- simple module-level API ----------------

_pad = None


def setup(remote="XBOX", method="pipe"):
    """Choose the remote (console name) and the method once, at the top of your program."""
    global _pad
    if _pad:
        _pad.close()
    _pad = Pad(remote, method)
    return _pad


def _p():
    if _pad is None:
        setup()
    return _pad


def press(*names, hold=None): _p().press(*names, hold=hold)
def down(*names): _p().down(*names)
def up(*names): _p().up(*names)
def stick(side, x, y): _p().stick(side, x, y)
def trigger(side, value): _p().trigger(side, value)
def release(): _p().release()
def snap(path): return _p().snap(path)
def wait(ms):
    """صبر ms میلی‌ثانیه؛ «توقف» پنل آن را قطع و «توقف موقت» نگهش می‌دارد."""
    if _pad is not None:
        _pad.ctl.sleep(ms)
    else:
        _sleep_ms(ms)


def log(text):
    """یک خط دلخواه در لاگ پنل ریموت (و در خروجی)."""
    print(text)
    _p().ctl.log(text)


def wait_start():
    """ربات را «منتظر شروع» می‌گذارد و صبر می‌کند تا دکمه‌ی «شروع» پنل زده شود."""
    _p().ctl.wait_start()


def platform(default="Ser"):
    """تیک «XS» پنل ریموت: روشن = "Ser" (Series X|S)، خاموش = "One". ریموت قدیمی → default."""
    r = _p().ctl._ask("platform")
    return r.split()[1] if r and r.startswith("ok ") and len(r.split()) > 1 else default


def bot_pause(text=None):
    """ربات را «توقف موقت» می‌کند و صبر می‌کند تا «ادامه» پنل زده شود (برای درست کردن دستی).
    True = ادامه داده شد، False = ریموت توقف موقت ندارد. «توقف» پنل → BotStopped."""
    return _p().ctl.pause(text)


def bot_check():
    """فقط چک: توقف → BotStopped، توقف موقت → صبر، ریموت قطع → اتصال دوباره."""
    _p().ctl.checkpoint()


def A(hold=None): _p().A(hold)
def B(hold=None): _p().B(hold)
def X(hold=None): _p().X(hold)
def Y(hold=None): _p().Y(hold)
def Up(hold=None): _p().Up(hold)
def Down(hold=None): _p().Down(hold)
def Left(hold=None): _p().Left(hold)
def Right(hold=None): _p().Right(hold)
def LB(hold=None): _p().LB(hold)
def RB(hold=None): _p().RB(hold)
def LT(hold=None): _p().LT(hold)
def RT(hold=None): _p().RT(hold)
def LS(hold=None): _p().LS(hold)
def RS(hold=None): _p().RS(hold)
def View(hold=None): _p().View(hold)
def XMenu(hold=None): _p().Menu(hold)
def Xbox(hold=None): _p().Xbox(hold)
def LsUp(hold=None): _p().LsUp(hold)
def LsDown(hold=None): _p().LsDown(hold)
def LsLeft(hold=None): _p().LsLeft(hold)
def LsRight(hold=None): _p().LsRight(hold)
def RsUp(hold=None): _p().RsUp(hold)
def RsDown(hold=None): _p().RsDown(hold)
def RsLeft(hold=None): _p().RsLeft(hold)
def RsRight(hold=None): _p().RsRight(hold)

__all__ = ["setup", "Pad", "press", "down", "up", "stick", "trigger", "release", "snap", "wait",
           "log", "wait_start", "bot_pause", "bot_check", "platform", "BotStopped", "RemoteDown",
           "A", "B", "X", "Y", "Up", "Down", "Left", "Right", "LB", "RB", "LT", "RT", "LS", "RS",
           "View", "XMenu", "Xbox", "LsUp", "LsDown", "LsLeft", "LsRight", "RsUp", "RsDown", "RsLeft", "RsRight"]
