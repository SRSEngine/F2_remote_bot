# -*- coding: utf-8 -*-
"""
panel.py — Xbox Remote Panel: manage accounts (from CSV) and remotes.

Tabs:
  • Accounts — table of accounts imported from a CSV (like a database). Import CSV button.
  • Monitor  — a wall of live thumbnails of the active remotes (5 per row). Each tile has
               Start / Pause / Stop (bot) and a Show/Hide button for the remote window.
               Thumbnails refresh every 5 seconds. Paused/stopped tiles change color.

Each remote signs in with its account's Microsoft credentials and runs in xbrp (CPU Decode),
one remote per console (not per account). Platform (Series/One) comes from the CSV.

Run:  python panel.py   or double-click run.bat
"""
from __future__ import annotations

import queue
import threading
import sys
import time

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap, QImage, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QTabWidget, QFrame, QCheckBox, QComboBox, QAbstractItemView, QMessageBox,
    QScrollArea, QStyle, QSizePolicy, QLineEdit, QDialog, QDialogButtonBox, QFormLayout,
)

import core
from core import Account, Remote

# ---------- Xbox-style palette ----------
BG     = "#0b0f0c"
CARD   = "#161b16"
CARD2  = "#1d241d"
GREEN  = "#107C10"
GREEN2 = "#16a016"
TEXT   = "#eaf0ea"
MUTED  = "#8aa08a"
RED    = "#d04545"
ORANGE = "#d98b2b"
YELLOW = "#d9a73a"
BLUE   = "#3a86d9"
BORDER = "#243024"

# bot state -> (color, label)
BOT_UI = {
    "run":   (GREEN2,  "RUNNING"),
    "pause": (ORANGE,  "PAUSED"),
    "stop":  (RED,     "STOPPED"),
    "wait":  (BLUE,    "WAITING"),
    "":      (MUTED,   "NO BOT"),
}

QSS = f"""
* {{ font-family: 'Segoe UI'; color: {TEXT}; }}
QMainWindow, QWidget#root {{ background: {BG}; }}
QLabel#title {{ font-size: 20px; font-weight: 700; }}
QLabel#subtitle {{ color: {MUTED}; font-size: 12px; }}
QLabel#count {{ color: {MUTED}; font-size: 12px; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 12px; top: -1px; background: {CARD}; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 10px 22px; margin-right: 6px;
    font-size: 14px; font-weight: 600; border: 1px solid transparent; border-bottom: none;
    border-top-left-radius: 10px; border-top-right-radius: 10px; }}
QTabBar::tab:selected {{ color: {TEXT}; background: {CARD}; border: 1px solid {BORDER}; border-bottom: none; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

QPushButton {{ background: {CARD2}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 6px 12px; font-size: 12px; font-weight: 600; }}
QPushButton:hover {{ background: #26302650; border-color: {GREEN}; }}
QPushButton:pressed {{ background: #0e140e; }}
QPushButton#primary {{ background: {GREEN}; border-color: {GREEN}; color: white; }}
QPushButton#primary:hover {{ background: {GREEN2}; }}
QPushButton#danger {{ background: transparent; border-color: {RED}; color: {RED}; }}
QPushButton#danger:hover {{ background: #2a1414; }}
QPushButton#warn {{ background: transparent; border-color: {ORANGE}; color: {ORANGE}; }}
QPushButton#warn:hover {{ background: #2a2014; }}
QPushButton#ghost {{ background: transparent; }}

QTableWidget {{ background: {CARD}; border: none; gridline-color: {BORDER};
    selection-background-color: #1c2a1c; selection-color: {TEXT}; font-size: 13px; }}
QHeaderView::section {{ background: {CARD2}; color: {MUTED}; border: none;
    border-bottom: 1px solid {BORDER}; padding: 8px 10px; font-weight: 700; }}
QTableWidget::item {{ padding: 6px 10px; border-bottom: 1px solid {BORDER}; }}
QTableCornerButton::section {{ background: {CARD2}; border: none; }}

QComboBox {{ background: {CARD2}; border: 1px solid {BORDER}; border-radius: 7px; padding: 5px 10px; }}
QComboBox QAbstractItemView {{ background: {CARD2}; selection-background-color: {GREEN}; }}
QCheckBox {{ color: {MUTED}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


def dot(color: str, d: int = 10) -> QPixmap:
    pm = QPixmap(d, d); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen); p.setBrush(QColor(color)); p.drawEllipse(0, 0, d, d); p.end()
    return pm


def f2_icon(size: int = 64) -> QPixmap:
    """App/panel icon: a rounded green square with 'F2'."""
    pm = QPixmap(size, size); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen); p.setBrush(QColor(GREEN))
    r = size * 0.22
    p.drawRoundedRect(0, 0, size, size, r, r)
    p.setPen(QColor("white"))
    f = QFont("Segoe UI", int(size * 0.46), QFont.Black); p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "F2")
    p.end()
    return pm


# =================== login worker ===================
class LoginThread(QThread):
    done = Signal(str, bool, str)   # console, ok, message
    log = Signal(str, str)          # console, line

    def __init__(self, remote: Remote, show=False):
        super().__init__()
        self.remote = remote
        self.show = show

    def run(self):
        import mslogin
        a = self.remote.account
        try:
            self.log.emit(self.remote.console, "Signing in to Microsoft...")
            mslogin.ensure_token(
                self.remote.token_path(), a.MicrosoftEmail, a.MicrosoftPass,
                a.MicrosoftGauth, force=False, show=self.show,
                log=lambda m: self.log.emit(self.remote.console, m))
            self.done.emit(self.remote.console, True, "Login OK")
        except Exception as e:
            self.done.emit(self.remote.console, False, str(e))


# =================== snapshot worker ===================
class SnapWorker(QThread):
    """Background polling: ONE thread per console, so a slow or stuck remote never delays the others.
    Each console thread reads bot state/health (~1.2 s) and a snap (~interval s) from the remote the
    panel launched (pinned by pid), and runs that console's queued bot commands."""
    update = Signal(str, object, str, str, bool, int)  # console, QImage|None, botstate, health, running, #remotes

    def __init__(self, interval=5.0):
        super().__init__()
        self.interval = interval
        self.consoles: list[str] = []
        self.pids: dict = {}            # console -> pid of the remote the panel launched
        self._queues: dict = {}
        self._threads: dict = {}
        self._qlock = threading.Lock()
        self._stop = False

    def set_consoles(self, consoles):
        self.consoles = list(consoles)

    def set_pid(self, console: str, pid):
        if pid:
            self.pids[console] = int(pid)
        else:
            self.pids.pop(console, None)

    def _q(self, console) -> "queue.Queue":
        with self._qlock:
            q = self._queues.get(console)
            if q is None:
                q = self._queues[console] = queue.Queue()
            return q

    def enqueue(self, console: str, action: str):
        self._q(console).put(action)

    def stop(self):
        self._stop = True

    def _drain(self, console, link):
        q = self._q(console)
        while True:
            try:
                action = q.get_nowait()
            except queue.Empty:
                return
            if action == "start":
                link.bot_start()
            elif action == "pause":
                link.bot_pause()
            elif action == "resume":
                link.bot_resume()
            elif action == "stop":
                link.bot_stop()
            elif action == "wait":
                link.send("bot wait")   # idle until the user presses Start
            elif action == "xs_on":
                link.send("xs on")      # Series
            elif action == "xs_off":
                link.send("xs off")     # One

    @staticmethod
    def _qimage(bgr):
        if bgr is None:
            return None
        import numpy as np
        if not bgr.flags["C_CONTIGUOUS"]:
            bgr = np.ascontiguousarray(bgr)
        h, w = bgr.shape[:2]
        return QImage(bytes(bgr.data), w, h, 3 * w, QImage.Format_BGR888).copy()

    def _console_loop(self, console):
        import remoteio
        link = remoteio.RemoteLink(console)
        q = self._q(console)
        last_snap = 0.0
        poll = 1.2
        zseen: dict = {}                    # pid -> first time its window was seen gone
        while not self._stop and console in self.consoles:
            try:
                # window closed but process still alive (old xbrp kept reconnecting window-less):
                # after 8 s close it, so the tile, Start Remote and the console are free again
                now = time.time()
                for z in remoteio.zombies(console):
                    pid = int(z.get("pid") or 0)
                    first = zseen.setdefault(pid, now)
                    if now - first >= 8:
                        remoteio.kill_remote(z)
                        zseen.pop(pid, None)
                        print(f"[worker {console}] closed window-less remote {z.get('name')} (pid {pid})")
                infos = remoteio.all_running(console)
                info = remoteio.running_remote(console, self.pids.get(console))
                if info is None:
                    link.drop()
                    while not q.empty():          # commands for a remote that is gone
                        try:
                            q.get_nowait()
                        except queue.Empty:
                            break
                    self.update.emit(console, None, "", "", False, 0)
                else:
                    link.pin(info)
                    self._drain(console, link)
                    state = link.bot_state()
                    health = link.health()
                    img = None
                    now = time.time()
                    if now - last_snap >= self.interval:
                        img = self._qimage(link.snap_bgr())
                        last_snap = now
                    self.update.emit(console, img, state, health, True, len(infos))
            except Exception as e:                  # never let one console kill its thread
                print(f"[worker {console}] {e}")
            for _ in range(int(poll / 0.1)):
                if self._stop or not q.empty():
                    break
                time.sleep(0.1)
        link.drop()

    def run(self):
        import remoteio  # noqa: F401  (loads founder once, before the console threads)
        while not self._stop:
            for console in list(self.consoles):
                t = self._threads.get(console)
                if t is None or not t.is_alive():
                    t = threading.Thread(target=self._console_loop, args=(console,),
                                         name=f"poll-{console}", daemon=True)
                    self._threads[console] = t
                    t.start()
            time.sleep(0.5)


# =================== Accounts tab ===================
class AccountsTab(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.accounts: list[Account] = core.load_accounts()
        self.reveal = False
        self._build()
        self.refresh()

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 14, 18, 18); lay.setSpacing(12)
        bar = QHBoxLayout()
        imp = QPushButton("  Import CSV"); imp.setObjectName("primary")
        imp.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        imp.clicked.connect(self.on_import)
        tmpl = QPushButton("CSV template"); tmpl.setObjectName("ghost"); tmpl.clicked.connect(self.on_template)
        self.reveal_cb = QCheckBox("Show secrets"); self.reveal_cb.toggled.connect(self.on_reveal)
        self.count = QLabel(""); self.count.setObjectName("count")
        bar.addWidget(imp); bar.addWidget(tmpl); bar.addWidget(self.reveal_cb)
        bar.addStretch(1); bar.addWidget(self.count)
        lay.addLayout(bar)

        self.table = QTableWidget(0, len(core.CSV_FIELDS))
        self.table.setHorizontalHeaderLabels(core.CSV_FIELDS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setShowGrid(False)
        lay.addWidget(self.table)

    def on_reveal(self, v): self.reveal = v; self.refresh()

    def on_template(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save CSV template", str(core.HERE / "accounts-template.csv"), "CSV (*.csv)")
        if path:
            core.write_template_csv(path)
            QMessageBox.information(self, "Done", f"Template saved:\n{path}")

    def on_import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select accounts CSV", str(core.HERE), "CSV (*.csv)")
        if not path:
            return
        try:
            self.accounts = core.import_csv(path, replace=True)
        except Exception as e:
            QMessageBox.critical(self, "CSV error", str(e)); return
        self.refresh(); self.changed.emit()

    def refresh(self):
        self.table.setRowCount(0)
        for a in self.accounts:
            r = self.table.rowCount(); self.table.insertRow(r)
            for c, field in enumerate(core.CSV_FIELDS):
                val = getattr(a, field, "")
                if field in core.SECRET_FIELDS and val and not self.reveal:
                    val = "•" * min(10, max(4, len(val)))
                it = QTableWidgetItem(val)
                if field == "Console":
                    it.setForeground(QColor(GREEN2)); f = it.font(); f.setBold(True); it.setFont(f)
                elif field in core.SECRET_FIELDS:
                    it.setForeground(QColor(MUTED))
                self.table.setItem(r, c, it)
        g = core.consoles(self.accounts)
        self.count.setText(f"{len(self.accounts)} accounts  •  {len(g)} consoles")


# =================== remote tile ===================
class RemoteTile(QFrame):
    startRemote = Signal(str)
    loginBrowser = Signal(str)
    deleteToken = Signal(str)
    resetProgress = Signal(str)
    botStart = Signal(str)
    botPause = Signal(str)
    botResume = Signal(str)
    botStop = Signal(str)
    toggleWindow = Signal(str)
    pickAccount = Signal(str, str)     # console, account key ("" = Auto)

    TW, TH = 236, 133   # thumbnail size (16:9)

    def __init__(self, console: str, account: Account, accounts=None, pick: str = ""):
        super().__init__()
        self.console = console
        self.account = account
        self.accounts = list(accounts or [account])
        self.pick = pick or ""
        self.running = False
        self.botstate = ""
        self.token_saved = False
        self.complete = False
        self.starting = False    # remote launched/signing in but not answering yet
        self.dup = 0             # >1 = several remotes are open for this console
        self._btn_sig = None     # only rebuild buttons when this changes (avoid flicker/lost clicks)
        self.setFixedWidth(self.TW + 24)
        self._build()
        self.apply_state(False, "", "")

    def _build(self):
        v = QVBoxLayout(self); v.setContentsMargins(12, 10, 12, 10); v.setSpacing(8)
        # header
        head = QHBoxLayout(); head.setSpacing(6)
        name = QLabel(self.console); name.setStyleSheet(f"color:{GREEN2}; font-weight:700; font-size:15px;")
        plat = QLabel(" Series " if self._is_series() else " One ")
        plat.setStyleSheet(f"background:{CARD2}; color:{MUTED}; border-radius:6px; padding:1px 6px; font-size:10px;")
        self.name_lbl = name
        self.plat_lbl = plat
        head.addWidget(name); head.addStretch(1); head.addWidget(plat)
        v.addLayout(head)
        self.ident_lbl = QLabel("")
        self.ident_lbl.setStyleSheet(f"color:{MUTED}; font-size:10px;")
        self.ident_lbl.setMaximumWidth(self.TW); self.ident_lbl.setMinimumWidth(self.TW)
        v.addWidget(self.ident_lbl)
        self._set_ident()
        # SHARED_REMOTE: which game account the bot verified on the console (gamertag on Home)
        self.console_lbl = QLabel("On console: -")
        self.console_lbl.setStyleSheet(f"color:{TEXT}; font-size:11px;")
        self.console_lbl.setVisible(core.SHARED_REMOTE)
        v.addWidget(self.console_lbl)
        # which account to run: Auto (rotate through unfinished accounts) or one fixed account
        self.combo = QComboBox(); self.combo.setFixedWidth(self.TW)
        self.combo.setToolTip("Auto = run the next unfinished account and rotate.\n"
                              "An account = run only that one (no rotation). Change it while the remote is off.")
        self._fill_combo()
        self.combo.currentIndexChanged.connect(self._on_combo)
        v.addWidget(self.combo)
        # thumbnail
        self.thumb = QLabel(); self.thumb.setFixedSize(self.TW, self.TH)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet(f"background:#000; border-radius:8px; color:{MUTED}; font-size:12px;")
        self.thumb.setText("OFF")
        v.addWidget(self.thumb)
        # status + SBC progress
        row = QHBoxLayout(); row.setSpacing(6)
        self.status = QLabel("OFF"); self.status.setStyleSheet(f"color:{MUTED}; font-weight:700; font-size:12px;")
        self.prog = QLabel(""); self.prog.setStyleSheet(f"color:{MUTED}; font-size:11px;")
        row.addWidget(self.status); row.addStretch(1); row.addWidget(self.prog)
        v.addLayout(row)
        # buttons (two rows: bot controls, then show/hide)
        self.btnrow = QHBoxLayout(); self.btnrow.setSpacing(5)
        v.addLayout(self.btnrow)
        self.btnrow2 = QHBoxLayout(); self.btnrow2.setSpacing(5)
        v.addLayout(self.btnrow2)

    def _is_series(self):
        return "one" not in (self.account.Platform or "").strip().lower()

    def _set_ident(self):
        gt = (self.account.Gamertag or "").strip()
        mail = self.account.MicrosoftEmail or self.account.EAEmail or "-"
        ident = f"{gt}  ·  {mail}" if gt else mail
        if core.SHARED_REMOTE:
            ident = "Remote: " + ident             # the account the stream signs in with (fixed)
        self.ident_lbl.setText(self.ident_lbl.fontMetrics().elidedText(ident, Qt.ElideRight, self.TW))

    def show_console_account(self, account):
        """SHARED_REMOTE: the game account currently on the console (verified by the bot, else next to run)."""
        self.console_lbl.setText(self.console_lbl.fontMetrics().elidedText(
            f"On console: {account.label()}", Qt.ElideRight, self.TW))

    def set_account(self, account):
        self.account = account
        self._set_ident()
        self.plat_lbl.setText(" Series " if self._is_series() else " One ")

    def _fill_combo(self):
        """Auto + every account of this console with its SBC progress; selects self.pick."""
        # skip the rebuild when nothing shown would change (polling is frequent)
        sig = (tuple(a.key() for a in self.accounts),
               tuple(core.done_count(a.key()) for a in self.accounts), self.pick)
        if sig == getattr(self, "_combo_sig", None):
            return
        self._combo_sig = sig
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem("Auto — next unfinished", "")
        sel = 0
        for i, a in enumerate(self.accounts, 1):
            got, total = core.done_count(a.key())
            name = (a.Gamertag or "").strip() or a.MicrosoftEmail or a.EAEmail or "?"
            mark = "  ✓" if total and got >= total else ""
            self.combo.addItem(f"{name}  ·  SBC {got}/{total}{mark}", a.key())
            if a.key() == self.pick:
                sel = i
        self.combo.setCurrentIndex(sel)
        self.combo.blockSignals(False)

    def _on_combo(self, idx):
        self.pick = self.combo.itemData(idx) or ""
        self.pickAccount.emit(self.console, self.pick)

    def _clear_btnrow(self):
        for row in (self.btnrow, self.btnrow2):
            while row.count():
                it = row.takeAt(0)
                w = it.widget()
                if w:
                    w.hide()
                    w.setParent(None)   # detach now; deleteLater alone leaves it at (0,0)
                    w.deleteLater()

    def apply_state(self, running: bool, botstate: str, health: str, token_saved=None,
                    complete=None, progress=None, starting=False, dup=0):
        self.running = running
        self.starting = bool(starting) and not running
        self.dup = dup
        self.botstate = botstate
        if token_saved is not None:
            self.token_saved = token_saved
        if complete is not None:
            self.complete = complete
        if progress is not None:
            got, total = progress
            self._text(self.prog, f"SBC {got}/{total}" if total else "")
            self._css(self.prog, f"color:{GREEN2 if got and got >= total else MUTED}; font-size:11px;")
        color, label = BOT_UI.get(botstate, BOT_UI[""])
        if not running:
            # blue frame before start and when finished (user request)
            color = BLUE
            label = "DONE ✓ all accounts" if self.complete else "READY"
            if self.starting:
                label = "STARTING..."
        if dup > 1:
            color = RED
            label = f"⚠ {dup} remotes open — close extras"
        self._css(self, f"RemoteTile {{ background:{CARD}; border:2px solid {color}; border-radius:12px; }}")
        self._text(self.status, label)
        self._css(self.status, f"color:{color}; font-weight:700; font-size:12px;")
        if not running and getattr(self, "_thumb_off", None) != self.starting:
            self._thumb_off = self.starting
            self.thumb.setPixmap(QPixmap()); self.thumb.setText("STARTING..." if self.starting else "OFF")
        elif running:
            self._thumb_off = None
        # account picker: locked while the remote runs (its token belongs to the running account);
        # refresh the SBC counts when off, unless the list is open right now
        # (SHARED_REMOTE: always open — the remote's token does not depend on the game account;
        #  the bot reads the pick when it moves to its next account)
        self.combo.setEnabled(core.SHARED_REMOTE or not running)
        if (core.SHARED_REMOTE or not running) and not self.combo.view().isVisible():
            self._fill_combo()
        # rebuild buttons only when the mode/labels actually change (polling is frequent)
        bucket = botstate if botstate in ("run", "pause") else "idle"
        sig = (running, bool(self.complete), bucket, bool(self.token_saved), self.starting)
        if sig == self._btn_sig:
            return
        self._btn_sig = sig
        self._clear_btnrow()
        if self.starting:
            # launched, not answering yet: no "Start Remote" (a second click opened a 2nd remote "C33-2")
            b_wait = QPushButton("Starting..."); b_wait.setObjectName("ghost"); b_wait.setFixedHeight(28)
            b_wait.setEnabled(False)
            self.btnrow.addWidget(b_wait)
            return
        if running:
            active = botstate in ("run", "pause")
            if active:
                # one two-state button: green Start vs red Stop. Active -> red Stop.
                b_main = QPushButton("Stop"); b_main.setObjectName("danger")
                b_main.clicked.connect(lambda: self.botStop.emit(self.console))
                paused = botstate == "pause"
                b_sec = QPushButton("Resume" if paused else "Pause")
                b_sec.setObjectName("primary" if paused else "warn")
                b_sec.clicked.connect(
                    (lambda: self.botResume.emit(self.console)) if paused
                    else (lambda: self.botPause.emit(self.console)))
                for b in (b_main, b_sec):
                    b.setFixedHeight(30); b.setMinimumWidth(90); self.btnrow.addWidget(b)
            else:
                # bot not active -> single green Start (press turns it red "Stop")
                b_main = QPushButton("Start"); b_main.setObjectName("primary")
                b_main.setFixedHeight(30)
                b_main.clicked.connect(lambda: self.botStart.emit(self.console))
                self.btnrow.addWidget(b_main)
            eye = QPushButton("Show / Hide window"); eye.setObjectName("ghost"); eye.setFixedHeight(26)
            eye.setToolTip("Show or hide the remote window and its panel")
            eye.clicked.connect(lambda: self.toggleWindow.emit(self.console))
            self.btnrow2.addWidget(eye)
        elif self.complete:
            # all SBCs done -> do not run; offer to reset progress to run again
            b_done = QPushButton("Done — won't run"); b_done.setObjectName("ghost"); b_done.setFixedHeight(28)
            b_done.setEnabled(False)
            self.btnrow.addWidget(b_done)
            b_reset = QPushButton("Reset SBC progress"); b_reset.setObjectName("warn"); b_reset.setFixedHeight(26)
            b_reset.setToolTip("Clear this console's completed SBCs so it runs again")
            b_reset.clicked.connect(lambda: self.resetProgress.emit(self.console))
            self.btnrow2.addWidget(b_reset)
        else:
            b_start = QPushButton("Start Remote"); b_start.setObjectName("primary"); b_start.setFixedHeight(28)
            b_start.clicked.connect(lambda: self.startRemote.emit(self.console))
            self.btnrow.addWidget(b_start)
            if self.token_saved:
                # token already saved -> login button off; offer Delete token instead
                b_login = QPushButton("Token saved ✓"); b_login.setObjectName("ghost"); b_login.setFixedHeight(26)
                b_login.setEnabled(False)
                b_del = QPushButton("Delete token"); b_del.setObjectName("danger"); b_del.setFixedHeight(26)
                b_del.setToolTip("Delete the saved token so you can sign in again")
                b_del.clicked.connect(lambda: self.deleteToken.emit(self.console))
                self.btnrow2.addWidget(b_login); self.btnrow2.addWidget(b_del)
            else:
                b_login = QPushButton("Login (browser)"); b_login.setObjectName("ghost"); b_login.setFixedHeight(26)
                b_login.setToolTip("Sign in with a visible browser and save the token")
                b_login.clicked.connect(lambda: self.loginBrowser.emit(self.console))
                self.btnrow2.addWidget(b_login)

    @staticmethod
    def _css(w, css):
        if w.property("_css") != css:
            w.setProperty("_css", css)
            w.setStyleSheet(css)

    @staticmethod
    def _text(w, text):
        if w.text() != text:
            w.setText(text)

    def set_image(self, qimage):
        if qimage is None:
            return
        pm = QPixmap.fromImage(qimage).scaled(
            self.TW, self.TH, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self.thumb.setPixmap(pm)
        self.thumb.setText("")


# =================== Monitor tab ===================
class MonitorTab(QWidget):
    def __init__(self, accounts_tab: AccountsTab):
        super().__init__()
        self.accounts_tab = accounts_tab
        self.remotes: dict[str, Remote] = {}
        self.tiles: dict[str, RemoteTile] = {}
        self.threads: dict[str, LoginThread] = {}
        self.last: dict[str, tuple] = {}   # console -> (running, botstate, health)
        self._advancing: set = set()       # consoles mid account-rotation
        self._last_xs: dict = {}           # console -> last platform (Series bool) sent to xbrp
        self._pending_wait: set = set()    # consoles just launched: park the bot in 'wait' once up
        self.state = core.load_state()
        self._build()
        self.worker = SnapWorker(interval=5.0)
        self.worker.update.connect(self.on_update)
        self.rebuild()
        self.worker.start()
        self.uptimer = QTimer(self); self.uptimer.timeout.connect(self._check_exits); self.uptimer.start(1500)

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 14, 18, 18); lay.setSpacing(12)
        bar = QHBoxLayout()
        self.start_all = QPushButton("  Start all"); self.start_all.setObjectName("primary")
        self.start_all.clicked.connect(self.on_start_all)
        self.stop_all = QPushButton("Stop all remotes"); self.stop_all.setObjectName("danger")
        self.stop_all.clicked.connect(self.on_stop_all)
        self.show_cb = QCheckBox("Show browser on login"); self.show_cb.setChecked(True)
        self.summary = QLabel(""); self.summary.setObjectName("count")
        bar.addWidget(self.start_all); bar.addWidget(self.stop_all); bar.addWidget(self.show_cb)
        bar.addStretch(1); bar.addWidget(self.summary)
        lay.addLayout(bar)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(2, 2, 2, 2); self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_host)
        lay.addWidget(self.scroll)

    # ---- build/refresh tiles ----
    def rebuild(self):
        accounts = self.accounts_tab.accounts
        groups = core.consoles(accounts)
        for console in list(self.remotes.keys()):
            if console not in groups and not (self.remotes[console].proc and self.remotes[console].is_alive()):
                self.remotes.pop(console, None)
        for console, accs in groups.items():
            if console not in self.remotes:
                self.remotes[console] = Remote(console=console, account=self._pick_account(console, accs))
        # rebuild grid
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w:
                self.grid.removeWidget(w)
        self.tiles.clear()
        self._order = sorted(self.remotes.keys(), key=lambda s: (len(s), s))
        for console in self._order:
            rem = self.remotes[console]
            tile = RemoteTile(console, rem.account, self._accounts(console), self._pick_key(console))
            tile.pickAccount.connect(self.on_pick)
            tile.startRemote.connect(self.start_remote)
            tile.loginBrowser.connect(lambda c: self.start_remote(c, force_login=True, show_browser=True))
            tile.deleteToken.connect(self.on_delete_token)
            tile.resetProgress.connect(self.on_reset_progress)
            tile.botStart.connect(lambda c: (self._pending_wait.discard(c), self.worker.enqueue(c, "start")))
            tile.botPause.connect(lambda c: self.worker.enqueue(c, "pause"))
            tile.botResume.connect(lambda c: self.worker.enqueue(c, "resume"))
            tile.botStop.connect(lambda c: self.worker.enqueue(c, "stop"))
            tile.toggleWindow.connect(self.on_toggle_window)
            self.tiles[console] = tile
            shown = self._shown_account(console) or rem.account
            tile.apply_state(False, "", "", token_saved=rem.has_token(),
                             complete=self._tile_complete(console),
                             progress=core.done_count(shown.key()))
            if core.SHARED_REMOTE:
                tile.show_console_account(shown)
        self._place_tiles(force=True)
        self.worker.set_consoles(list(self.remotes.keys()))
        self._update_summary()

    def _calc_cols(self) -> int:
        tile_w = RemoteTile.TW + 24 + self.grid.spacing()   # tile width + column gap
        avail = self.scroll.viewport().width() - 4
        return max(1, avail // max(1, tile_w))

    def _place_tiles(self, force=False):
        cols = self._calc_cols()
        if not force and cols == getattr(self, "_cols", None):
            return
        self._cols = cols
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w:
                self.grid.removeWidget(w)
        for idx, console in enumerate(getattr(self, "_order", [])):
            tile = self.tiles.get(console)
            if tile:
                self.grid.addWidget(tile, idx // cols, idx % cols)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_tiles()

    def _accounts(self, console):
        return core.consoles(self.accounts_tab.accounts).get(console, [])

    def _pick_account(self, console, accs):
        # SHARED_REMOTE: the remote always signs in with the console's remote account (the bot switches
        # game accounts on the console). Otherwise: manual pick wins, else the first unfinished account.
        if core.SHARED_REMOTE:
            return core.remote_account(accs) or accs[0]
        return self._manual(console) or core.next_account(accs) or accs[0]

    def _shown_account(self, console):
        """Account whose SBC progress the tile shows: SHARED → the one the bot verified on the console
        (active.json), else the manual pick / next unfinished; otherwise the remote's own account."""
        rem = self.remotes.get(console)
        if not core.SHARED_REMOTE:
            return rem.account if rem else None
        accs = self._accounts(console)
        key = core.get_active(console).get("account", "")
        for a in accs:
            if a.key() == key:
                return a
        return self._manual(console) or core.next_account(accs) or (accs[0] if accs else None)

    # ---- manual account pick (dropdown on each tile) ----
    def _pick_key(self, console) -> str:
        return self.state.get("pick", {}).get(console, "") or ""

    def _manual(self, console):
        """The account picked by hand for this console, or None = Auto (rotate)."""
        key = self._pick_key(console)
        if key:
            for a in self._accounts(console):
                if a.key() == key:
                    return a
        return None

    def _tile_complete(self, console) -> bool:
        """'Done — won't run' only in Auto mode; a hand-picked account can always be started."""
        return core.console_complete(self._accounts(console)) and self._manual(console) is None

    def on_pick(self, console, key):
        rem = self.remotes.get(console)
        if not rem:
            return
        running = bool(rem.proc and rem.is_alive())
        if running and not core.SHARED_REMOTE:
            return                                   # per-account remote: locked while it runs
        picks = self.state.setdefault("pick", {})
        if key:
            picks[console] = key
        else:
            picks.pop(console, None)
        core.save_state(self.state)                  # SHARED: the bot reads it for its next account
        accs = self._accounts(console)
        if not core.SHARED_REMOTE:
            rem.account = self._manual(console) or core.next_account(accs) or accs[0]
        tile = self.tiles.get(console)
        if tile:
            shown = self._manual(console) or self._shown_account(console)
            if not core.SHARED_REMOTE:
                tile.set_account(rem.account)
            if not running:
                tile.apply_state(False, "", "", token_saved=rem.has_token(),
                                 complete=self._tile_complete(console),
                                 progress=core.done_count(shown.key()) if shown else None)
            self._set_status(console, "MANUAL: " + shown.label() if key and shown else "AUTO",
                             BLUE if key else MUTED)

    # ---- snapshot updates ----
    def _starting(self, console) -> bool:
        """Launched by this panel (or signing in) but its pipe is not answering yet."""
        rem = self.remotes.get(console)
        th = self.threads.get(console)
        return bool((rem and rem.is_alive()) or (th and th.isRunning()))

    def on_update(self, console, qimage, botstate, health, running, count=0):
        self.last[console] = (running, botstate, health)
        tile = self.tiles.get(console)
        if not tile:
            return
        rem = self.remotes.get(console)
        if not running and rem and rem.proc and not rem.is_alive():
            rem.proc = None                      # our remote exited: forget its pid
            self.worker.set_pid(console, None)
        accs = self._accounts(console)
        # --- rotation: active account finished all SBCs -> next account on this console ---
        # (Auto only: a hand-picked account just runs; the user decides what comes next)
        # (SHARED_REMOTE: never — the remote stays open and the bot switches accounts itself)
        if (running and rem and core.is_complete(rem.account.key()) and console not in self._advancing
                and self._manual(console) is None and not core.SHARED_REMOTE):
            self._advancing.add(console)
            QTimer.singleShot(0, lambda c=console: self._advance(c))
            return
        shown = self._shown_account(console)
        got, total = core.done_count(shown.key()) if shown else (0, 0)
        if core.SHARED_REMOTE and shown is not None:
            tile.show_console_account(shown)
        # auto XS: keep xbrp's platform in sync with the account now on the console
        if running and shown is not None:
            series = "one" not in (shown.Platform or "").strip().lower()
            if self._last_xs.get(console) != series:
                self._last_xs[console] = series
                self.worker.enqueue(console, "xs_on" if series else "xs_off")
        else:
            self._last_xs.pop(console, None)
        # just-launched remote: park the bot in 'wait' so the tile shows Start (not RUNNING)
        # until the user presses Start. xbrp defaults bot.state to 'run', hence this.
        if running and console in self._pending_wait:
            self.worker.enqueue(console, "wait")
            self._pending_wait.discard(console)
        elif not running and not self._starting(console):
            self._pending_wait.discard(console)
        tile.apply_state(running, botstate, health,
                         token_saved=rem.has_token() if rem else None,
                         complete=self._tile_complete(console),
                         progress=(got, total),
                         starting=(not running and self._starting(console)),
                         dup=count)
        if running and qimage is not None:
            tile.set_image(qimage)
        self._update_summary()

    def _advance(self, console):
        """Stop the finished account's remote and start the next unfinished account."""
        try:
            rem = self.remotes.get(console)
            accs = self._accounts(console)
            done_key = rem.account.key() if rem else ""
            self._stop_console(console)
            core.clear_active(console)
            nxt = core.next_account(accs, after_key=done_key)
            tile = self.tiles.get(console)
            if nxt is None:
                if tile:
                    tile.apply_state(False, "", "", token_saved=False,
                                     complete=True, progress=core.done_count(done_key))
                self._set_status(console, "DONE — all accounts", GREEN2)
            else:
                rem.account = nxt
                if tile:
                    tile.set_account(nxt)
                self._set_status(console, f"NEXT: {nxt.Gamertag or nxt.MicrosoftEmail}", BLUE)
                self.start_remote(console)
                # kick the bot once the next remote is up
                QTimer.singleShot(12000, lambda c=console: self.worker.enqueue(c, "start"))
        finally:
            self._advancing.discard(console)

    @staticmethod
    def _kill_pid(pid):
        try:
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(1, False, int(pid))
            if h:
                ctypes.windll.kernel32.TerminateProcess(h, 0)
                ctypes.windll.kernel32.CloseHandle(h)
        except Exception:
            pass

    def _stop_console(self, console):
        """Close every remote of this console (ours and any duplicates like C33-2)."""
        import remoteio
        rem = self.remotes.get(console)
        if rem and rem.proc and rem.is_alive():
            rem.stop()
        for info in remoteio.all_running(console) + remoteio.zombies(console):
            remoteio.kill_remote(info)
        if rem:
            rem.proc = None
            rem.status = "stopped"; rem.started_at = 0.0
        self.worker.set_pid(console, None)

    # ---- window show/hide ----
    def on_toggle_window(self, console):
        import remoteio
        hwnd = remoteio.window_hwnd(console, self.worker.pids.get(console))
        if hwnd:
            remoteio.toggle_window(hwnd)

    # ---- delete saved token ----
    def on_delete_token(self, console):
        rem = self.remotes.get(console)
        if not rem:
            return
        tok = rem.token_path()
        if tok.exists():
            res = QMessageBox.question(
                self, "Delete token",
                f"Delete the saved token for {console}?\nNext start will need a full sign-in.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if res != QMessageBox.Yes:
                return
            try:
                tok.unlink()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not delete token:\n{e}"); return
        tile = self.tiles.get(console)
        if tile:
            tile.apply_state(False, "", "", token_saved=False)
            self._set_status(console, "TOKEN DELETED", MUTED)

    # ---- reset SBC progress ----
    def on_reset_progress(self, console):
        res = QMessageBox.question(
            self, "Reset SBC progress",
            f"Clear completed SBCs for every account on {console} so it runs again?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if res != QMessageBox.Yes:
            return
        core.reset_progress([a.key() for a in self._accounts(console)])   # locked: bots write it too
        self.rebuild()

    # ---- start / login ----
    def start_remote(self, console, force_login=False, show_browser=False):
        rem = self.remotes.get(console)
        if not rem:
            return
        import remoteio
        if self._starting(console):
            self._set_status(console, "ALREADY STARTING", BLUE)
            return
        live = remoteio.running_remote(console)
        if live:                                  # a remote of this console is already open: adopt it
            self.worker.set_pid(console, live.get("pid"))
            self._set_status(console, f"ALREADY OPEN ({live.get('name')})", BLUE)
            return
        accs = self._accounts(console)
        manual = self._manual(console)
        if core.SHARED_REMOTE:
            # one fixed remote per console: always the console's remote account; the bot checks the
            # gamertag on Home and marks the active account itself (core.set_active from Play.py)
            if manual is None and core.console_complete(accs) and not force_login:
                self._set_status(console, "DONE — all accounts", GREEN2)
                return
            rem.account = core.remote_account(accs) or rem.account
        elif manual is not None:
            rem.account = manual                   # account picked in the tile's dropdown
        else:
            if core.console_complete(accs) and not force_login:
                self._set_status(console, "DONE — all accounts", GREEN2)
                return
            # Auto: run the first account that still has SBCs left
            nxt = core.next_account(accs, after_key="")
            if nxt is not None:
                rem.account = nxt
        tile = self.tiles.get(console)
        if tile:
            tile.set_account(rem.account)
        a = rem.account
        if not core.SHARED_REMOTE:
            core.set_active(a, console)    # tell the bot which account this is (SHARED: the bot does it after the gamertag check)
        if not a.MicrosoftEmail or not a.MicrosoftPass:
            tile = self.tiles.get(console)
            if tile:
                tile._text(tile.status, "NO CREDENTIALS"); tile._css(tile.status, f"color:{RED};font-weight:700;")
            return
        tok = rem.token_path()
        if force_login and tok.exists():
            try: tok.unlink()
            except Exception: pass
        if tok.exists():
            self._launch(console); return
        tile = self.tiles.get(console)
        if tile:
            tile._text(tile.status, "SIGNING IN..."); tile._css(tile.status, f"color:{BLUE};font-weight:700;")
        th = LoginThread(rem, show=self.show_cb.isChecked() or show_browser)
        th.log.connect(lambda c, line: self._set_status(c, line, BLUE))
        th.done.connect(self._on_login_done)
        self.threads[console] = th
        th.start()

    def _set_status(self, console, text, color=MUTED):
        tile = self.tiles.get(console)
        if tile:
            tile._text(tile.status, text[:40]); tile._css(tile.status, f"color:{color};font-weight:700;font-size:11px;")

    def _on_login_done(self, console, ok, message):
        if ok:
            self._launch(console)
        else:
            self._set_status(console, message, RED)

    def _launch(self, console):
        rem = self.remotes.get(console)
        try:
            rem.launch_xbrp(minimized=True)
            self.worker.set_pid(console, rem.proc.pid)   # poll/control exactly this remote
            self._pending_wait.add(console)   # park the bot in 'wait' once the remote is up
            self._set_status(console, "STARTING...", BLUE)
        except Exception as e:
            self._set_status(console, f"LAUNCH FAILED: {e}", RED)

    def on_start_all(self):
        import remoteio
        skipped = 0
        for console in list(self.remotes.keys()):
            if self._tile_complete(console):          # Auto and nothing left; a hand-picked account still runs
                skipped += 1
                continue
            if not remoteio.is_running(console):
                self.start_remote(console)
        if skipped:
            self.summary.setText(self.summary.text() + f"  •  skipped {skipped} done")

    def _terminate_all(self):
        """Close every running remote (xbrp window + its panel)."""
        for console in list(self.remotes):
            try:
                self._stop_console(console)
            except Exception:
                pass

    def on_stop_all(self):
        res = QMessageBox.question(self, "Stop all", "Close all running remotes?",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if res != QMessageBox.Yes:
            return
        self._terminate_all()

    def _check_exits(self):
        self._update_summary()

    def _update_summary(self):
        try:
            import remoteio
            run = sum(1 for c in self.remotes if (self.last.get(c) or (False,))[0])
        except Exception:
            run = 0
        self.summary.setText(f"{len(self.remotes)} consoles  •  {run} active remotes")

    def shutdown(self):
        try:
            self.worker.stop(); self.worker.wait(2000)
        except Exception:
            pass
        self._terminate_all()        # closing F2 closes all remotes (xbrp windows)


# =================== Add SBC dialog ===================
class AddSbcDialog(QDialog):
    """Asks for Set name, Challenge name and CSV path. If 'single challenge' is
    ticked, only the Set name is needed."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add SBC")
        self.setMinimumWidth(460)
        self.setStyleSheet(QSS)
        lay = QVBoxLayout(self); lay.setContentsMargins(20, 18, 20, 16); lay.setSpacing(12)

        self.single = QCheckBox("Single challenge (only the set name)")
        self.single.toggled.connect(self._on_single)
        lay.addWidget(self.single)

        form = QFormLayout(); form.setSpacing(10)
        self.set_in = QLineEdit(); self.set_in.setPlaceholderText("e.g. Marquee, Icon SBC, 85+ Upgrade")
        self.chal_in = QLineEdit(); self.chal_in.setPlaceholderText("e.g. 1, England, Top Form")
        csv_row = QHBoxLayout(); csv_row.setSpacing(6)
        self.csv_in = QLineEdit(); self.csv_in.setPlaceholderText(r"C:\Users\...\Marquee1.csv")
        browse = QPushButton("Browse"); browse.setObjectName("ghost"); browse.clicked.connect(self._browse)
        csv_row.addWidget(self.csv_in); csv_row.addWidget(browse)
        csv_wrap = QWidget(); csv_wrap.setLayout(csv_row)
        self.lbl_set = QLabel("Set name"); self.lbl_chal = QLabel("Challenge name"); self.lbl_csv = QLabel("CSV path")
        form.addRow(self.lbl_set, self.set_in)
        form.addRow(self.lbl_chal, self.chal_in)
        form.addRow(self.lbl_csv, csv_wrap)
        self.csv_wrap = csv_wrap
        lay.addLayout(form)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _on_single(self, on):
        for w in (self.chal_in, self.csv_in, self.csv_wrap, self.lbl_chal, self.lbl_csv):
            w.setVisible(not on)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select CSV", str(core.MARQUEE_DIR), "CSV (*.csv)")
        if path:
            self.csv_in.setText(path)

    def _accept(self):
        if not self.set_in.text().strip():
            QMessageBox.information(self, "Set name", "Please enter the set name."); return
        if not self.single.isChecked():
            if not self.chal_in.text().strip():
                QMessageBox.information(self, "Challenge name", "Please enter the challenge name."); return
            if not self.csv_in.text().strip():
                QMessageBox.information(self, "CSV path", "Please choose the CSV file."); return
        self.accept()

    def value(self) -> dict:
        if self.single.isChecked():
            return {"set": self.set_in.text().strip(), "challenge": "", "csv": "", "enabled": True}
        return {"set": self.set_in.text().strip(), "challenge": self.chal_in.text().strip(),
                "csv": self.csv_in.text().strip(), "enabled": True}


# =================== SBC tab ===================
class SbcTab(QWidget):
    """The desired SBC list: each row is a challenge (Set / Challenge / CSV) with a Do
    checkbox. Seeded from the Marquee CSVs we have. The bot reads this list."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.sbcs = core.load_sbcs()
        self._loading = False
        self._build()
        self.refresh()

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 14, 18, 18); lay.setSpacing(12)
        bar = QHBoxLayout()
        add = QPushButton("  Add SBC"); add.setObjectName("primary")
        add.setIcon(self.style().standardIcon(QStyle.SP_FileDialogNewFolder)); add.clicked.connect(self.on_add)
        sync = QPushButton("Sync Marquees"); sync.setObjectName("ghost")
        sync.setToolTip("Add every Marquee{n}.csv found in the New Remote folder")
        sync.clicked.connect(self.on_sync)
        self.count = QLabel(""); self.count.setObjectName("count")
        bar.addWidget(add); bar.addWidget(sync)
        bar.addStretch(1); bar.addWidget(self.count)
        lay.addLayout(bar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Do", "Set", "Challenge", "CSV", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setShowGrid(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.Stretch)
        h.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 50); self.table.setColumnWidth(4, 100)
        self.table.itemChanged.connect(self.on_item_changed)
        lay.addWidget(self.table)

    def on_add(self):
        dlg = AddSbcDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        entry = dlg.value()
        name = core.sbc_name(entry).lower()
        if any(core.sbc_name(s).lower() == name for s in self.sbcs):
            QMessageBox.information(self, "Exists", "This SBC is already in the list."); return
        self.sbcs.append(entry)
        self._save(); self.refresh()

    def on_sync(self):
        before = len(self.sbcs)
        self.sbcs = core.sync_marquees(self.sbcs)
        added = len(self.sbcs) - before
        self._save(); self.refresh()
        QMessageBox.information(self, "Sync Marquees",
                               f"Added {added} new Marquee(s)." if added else "Already up to date.")

    def on_item_changed(self, item):
        if self._loading or item.column() != 0:
            return
        r = item.row()
        if 0 <= r < len(self.sbcs):
            self.sbcs[r]["enabled"] = item.checkState() == Qt.Checked
            self._save()

    def on_remove(self, name):
        self.sbcs = [s for s in self.sbcs if core.sbc_name(s) != name]
        self._save(); self.refresh()

    def _save(self):
        core.save_sbcs(self.sbcs); self.changed.emit()

    def refresh(self):
        self._loading = True
        self.table.setRowCount(0)
        for s in self.sbcs:
            on = s.get("enabled", True)
            r = self.table.rowCount(); self.table.insertRow(r); self.table.setRowHeight(r, 38)
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked if on else Qt.Unchecked)
            self.table.setItem(r, 0, chk)
            set_it = QTableWidgetItem("  " + (s.get("set") or ""))
            f = set_it.font(); f.setBold(True); set_it.setFont(f)
            set_it.setForeground(QColor(GREEN2 if on else MUTED))
            self.table.setItem(r, 1, set_it)
            chal = s.get("challenge") or "— single —"
            chal_it = QTableWidgetItem(chal)
            chal_it.setForeground(QColor(TEXT if (on and s.get("challenge")) else MUTED))
            self.table.setItem(r, 2, chal_it)
            csv_it = QTableWidgetItem(s.get("csv") or "")
            csv_it.setForeground(QColor(MUTED))
            self.table.setItem(r, 3, csv_it)
            rm = QPushButton("Remove"); rm.setObjectName("danger"); rm.setFixedHeight(26)
            rm.clicked.connect(lambda _, n=core.sbc_name(s): self.on_remove(n))
            wrap = QWidget(); wl = QHBoxLayout(wrap); wl.setContentsMargins(6, 3, 6, 3); wl.addWidget(rm)
            self.table.setCellWidget(r, 4, wrap)
        self._loading = False
        en = sum(1 for s in self.sbcs if s.get("enabled", True))
        self.count.setText(f"{len(self.sbcs)} SBCs  •  {en} enabled")


# =================== Account status tab ===================
class StatusTab(QWidget):
    """One row per account: which console it maps to, whether it is the one used for that
    console, whether it has a saved token, and the console's live remote / bot state."""
    COLS = ["Console", "Account", "Platform", "Used", "Token", "Remote", "Bot", "SBCs", "Start coins", "End coins",
            "Last error"]
    ERR_COLOR = {"coins": "#d04545", "crash": "#d04545", "stop": "#d04545", "error": "#e08a2e", "pause": "#e08a2e"}

    def __init__(self, accounts_tab: AccountsTab, mon_tab: "MonitorTab"):
        super().__init__()
        self.accounts_tab = accounts_tab
        self.mon_tab = mon_tab
        self._build()
        self.refresh()
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(2000)

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 14, 18, 18); lay.setSpacing(12)
        bar = QHBoxLayout()
        self.count = QLabel(""); self.count.setObjectName("count")
        self.reset_all = QPushButton("Reset all SBCs"); self.reset_all.setObjectName("danger")
        self.reset_all.setToolTip("Clear the completed SBCs of EVERY account so the bot runs them all again")
        self.reset_all.clicked.connect(self.on_reset_all)
        bar.addWidget(self.reset_all); bar.addStretch(1); bar.addWidget(self.count)
        lay.addLayout(bar)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(10, QHeaderView.Stretch)
        for c in (0, 2, 3, 4, 5, 6, 7, 8, 9):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        lay.addWidget(self.table)

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()                             # fresh as soon as the tab is opened

    def _cell(self, r, c, text, color=TEXT, bold=False):
        """Update one cell in place (create it once); no change -> no repaint."""
        it = self.table.item(r, c)
        if it is None:
            it = QTableWidgetItem()
            self.table.setItem(r, c, it)
        if it.text() != text:
            it.setText(text)
        if it.foreground().color() != QColor(color):
            it.setForeground(QColor(color))
        if it.font().bold() != bold:
            f = it.font(); f.setBold(bold); it.setFont(f)

    def _build_rows(self, rows):
        """(Re)create the rows and their Reset widgets — only when the account list changes."""
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(0)
            self.table.setRowCount(len(rows))
            self._sbc_cells = []
            self._err_cells = []
            for r, a in enumerate(rows):
                box = QWidget(); hl = QHBoxLayout(box); hl.setContentsMargins(6, 0, 6, 0); hl.setSpacing(8)
                lbl = QLabel("")
                reset = QPushButton("Reset"); reset.setObjectName("ghost"); reset.setFixedHeight(22)
                reset.setToolTip("Clear this account's completed SBCs so the bot runs them again")
                reset.clicked.connect(lambda _=False, acc=a: self.on_reset(acc, self._busy.get(acc.key(), False)))
                hl.addWidget(lbl); hl.addStretch(1); hl.addWidget(reset)
                self.table.setCellWidget(r, 7, box)
                self._sbc_cells.append((lbl, reset, [None, None]))
                # Last error: text + Clear (also clears "out of coins" so Auto runs the account again)
                ebox = QWidget(); el = QHBoxLayout(ebox); el.setContentsMargins(6, 0, 6, 0); el.setSpacing(8)
                elbl = QLabel("-"); elbl.setMinimumWidth(40)
                elbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)   # long text clips, never widens
                eclr = QPushButton("Clear"); eclr.setObjectName("ghost"); eclr.setFixedHeight(22)
                eclr.setToolTip("Clear the last error (and 'out of coins': Auto runs this account again)")
                eclr.clicked.connect(lambda _=False, acc=a: self.on_clear_error(acc))
                el.addWidget(elbl, 1); el.addWidget(eclr)
                self.table.setCellWidget(r, 10, ebox)
                self._err_cells.append((elbl, eclr, [None, None, None]))
        finally:
            self.table.setUpdatesEnabled(True)

    def refresh(self):
        if not self.isVisible():                   # hidden tab: nothing to draw
            return
        accounts = self.accounts_tab.accounts
        groups = core.consoles(accounts)
        remotes = self.mon_tab.remotes
        rows = [a for a in accounts if (a.Console or "").strip()]
        sig = tuple((a.Console, a.key()) for a in rows)
        if sig != getattr(self, "_rows_sig", None):
            self._rows_sig = sig
            self._build_rows(rows)
        # one read of each data file per refresh (not several per account)
        progress = core.load_progress()
        enabled = core.enabled_sbc_names()
        active = core.get_active() if core.SHARED_REMOTE else {}
        astat = core.load_account_status()
        self._busy = {}
        online = 0
        self.table.setUpdatesEnabled(False)
        try:
            for r, a in enumerate(rows):
                console = a.Console.strip()
                rem = remotes.get(console)
                if core.SHARED_REMOTE:             # the account the bot verified on the console (gamertag)
                    used = (active.get(console) or {}).get("account", "") == a.key()
                else:
                    used = bool(rem and rem.account.key() == a.key())
                running, botstate, health = self.mon_tab.last.get(console, (False, "", ""))
                token_ok = (core.TOKENS_DIR / f"acct_{core.acct_slug(a.key())}.json").exists()
                live = bool(used and running)
                if live:
                    online += 1
                self._busy[a.key()] = live
                done = set(progress.get(a.key(), {}).get("done", []))
                total = len(enabled)
                got = sum(1 for n in enabled if n in done)
                acc_done = total > 0 and got >= total

                self._cell(r, 0, console, GREEN2, True)
                self._cell(r, 1, a.Gamertag or a.MicrosoftEmail or a.EAEmail or "-")
                self._cell(r, 2, "Series" if "one" not in (a.Platform or "").lower() else "One", MUTED)
                self._cell(r, 3, "running" if live else "yes" if used else "standby", GREEN2 if used else MUTED)
                self._cell(r, 4, "saved" if token_ok else "-", GREEN2 if token_ok else MUTED)
                self._cell(r, 5, "running" if live else "stopped", GREEN2 if live else MUTED)
                if live:
                    color, label = BOT_UI.get(botstate, BOT_UI[""])
                    self._cell(r, 6, label, color, True)
                else:
                    self._cell(r, 6, "-", MUTED)
                lbl, reset, last = self._sbc_cells[r]
                text = f"{got}/{total}" + (" ✓" if acc_done else "")
                css = (f"color:{GREEN2 if acc_done else (TEXT if got else MUTED)};"
                       f"font-weight:{700 if acc_done else 400};")
                if last[0] != text:
                    lbl.setText(text); last[0] = text
                if last[1] != css:
                    lbl.setStyleSheet(css); last[1] = css
                can = bool(done)
                if reset.isEnabled() != can:
                    reset.setEnabled(can)
                # last error / out of coins
                st = astat.get(a.key(), {})
                # Start / End coins (My Coins read by the bot: first read of the run / last read)
                co = st.get("coins") or {}
                for col, k in ((8, "start"), (9, "end")):
                    v = co.get(k)
                    self._cell(r, col, f"{v:,}" if isinstance(v, int) else "-",
                               (("#d04545" if k == "end" and v < co.get("start", v) else TEXT)
                                if isinstance(v, int) else MUTED))
                    it = self.table.item(r, col)
                    tip = time.strftime("%m-%d %H:%M", time.localtime(co[k + "_at"])) if co.get(k + "_at") else ""
                    if k == "end" and isinstance(v, int) and isinstance(co.get("start"), int):
                        tip += f"  (spent {co['start'] - v:,})"
                    if it.toolTip() != tip:
                        it.setToolTip(tip)
                le = st.get("last_error") or {}
                elbl, eclr, elast = self._err_cells[r]
                if st.get("no_coins"):
                    when = time.strftime("%m-%d %H:%M", time.localtime(st["no_coins"].get("at", 0)))
                    etext, ecolor = f"⛔ OUT OF COINS  ·  {when}", "#d04545"
                    etip = st["no_coins"].get("text", "")
                elif le:
                    when = time.strftime("%m-%d %H:%M", time.localtime(le.get("at", 0)))
                    etext, ecolor = f"{when}  {le.get('text', '')}", self.ERR_COLOR.get(le.get("kind"), TEXT)
                    etip = le.get("text", "")
                else:
                    etext, ecolor, etip = "-", MUTED, ""
                full = etext
                if elast[0] != etext:
                    elbl.setText(etext); elast[0] = etext
                if elast[1] != ecolor:
                    elbl.setStyleSheet(f"color:{ecolor}; font-weight:{700 if st.get('no_coins') else 400};")
                    elast[1] = ecolor
                if elast[2] != etip:
                    elbl.setToolTip((full + "\n" + etip) if etip else ""); elast[2] = etip
                has = bool(st.get("last_error") or st.get("no_coins"))   # coins alone: nothing to clear
                if eclr.isEnabled() != has:
                    eclr.setEnabled(has)
        finally:
            self.table.setUpdatesEnabled(True)
        self.count.setText(f"{len(accounts)} accounts  •  {len(groups)} consoles  •  {online} active")

    def on_clear_error(self, account):
        """Clear the account's last error and out-of-coins flag (e.g. after adding coins)."""
        st = core.load_account_status().get(account.key(), {})
        if st.get("no_coins"):
            if QMessageBox.question(self, "Clear out of coins",
                                    f"Clear 'out of coins' for {account.label()}?\n\n"
                                    "Auto will run this account again.",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        core.clear_account_status([account.key()])
        self.refresh()

    def on_reset_all(self):
        """Clear the SBC progress of every account (after a confirmation)."""
        self.timer.stop()
        try:
            prog = core.load_progress()
            n = sum(1 for v in prog.values() if (v or {}).get("done"))
            if not n:
                QMessageBox.information(self, "Reset all SBCs", "No account has completed SBCs.")
                return
            busy = sum(1 for v in getattr(self, "_busy", {}).values() if v)
            msg = (f"Reset SBC progress of ALL accounts ({n} with completed SBCs)?\n\n"
                   "Every account shows 0 again and the bot will run every SBC again.")
            if busy:
                msg += f"\n\n{busy} bot(s) are running right now."
            if QMessageBox.question(self, "Reset all SBCs", msg,
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            core.update_json(core.PROGRESS_FILE, lambda p: {}, {})   # locked: bots write it too
            try:
                self.mon_tab.rebuild()             # tiles: progress and "Done — won't run" state
            except Exception:
                pass
        finally:
            self.refresh()
            self.timer.start(2000)

    def on_reset(self, account, busy=False):
        """Reset one account's SBC progress (after a confirmation)."""
        self.timer.stop()                          # the table is rebuilt every 2 s; keep it still meanwhile
        try:
            name = account.label()
            msg = (f"Reset SBC progress of {name} ({account.MicrosoftEmail or account.EAEmail})?\n\n"
                   "Its completed SBCs are cleared; the panel shows 0 again and the bot will run them again.")
            if busy:
                msg += "\n\nThe bot is running this account right now."
            if QMessageBox.question(self, "Reset SBC progress", msg,
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            core.reset_progress([account.key()])
            try:
                self.mon_tab.rebuild()             # tiles: progress and "Done — won't run" state
            except Exception:
                pass
        finally:
            self.refresh()
            self.timer.start(2000)


# =================== main window ===================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("F2")
        self.setWindowIcon(QIcon(f2_icon(64)))
        self.resize(1280, 760); self.setMinimumSize(900, 560)
        root = QWidget(); root.setObjectName("root"); self.setCentralWidget(root)
        lay = QVBoxLayout(root); lay.setContentsMargins(18, 16, 18, 10); lay.setSpacing(12)
        head = QHBoxLayout()
        logo = QLabel(); logo.setPixmap(f2_icon(34))
        tbox = QVBoxLayout(); tbox.setSpacing(0)
        t = QLabel("F2"); t.setObjectName("title")
        s = QLabel("Manage accounts and remotes — xbrp / CPU Decode"); s.setObjectName("subtitle")
        tbox.addWidget(t); tbox.addWidget(s)
        head.addWidget(logo); head.addSpacing(8); head.addLayout(tbox); head.addStretch(1)
        lay.addLayout(head)

        self.tabs = QTabWidget()
        self.acc_tab = AccountsTab()
        self.mon_tab = MonitorTab(self.acc_tab)
        self.sbc_tab = SbcTab()
        self.status_tab = StatusTab(self.acc_tab, self.mon_tab)
        self.acc_tab.changed.connect(self.mon_tab.rebuild)
        self.acc_tab.changed.connect(self.status_tab.refresh)
        self.sbc_tab.changed.connect(self.status_tab.refresh)
        self.tabs.addTab(self.acc_tab, "Accounts")
        self.tabs.addTab(self.mon_tab, "Monitor")
        self.tabs.addTab(self.sbc_tab, "SBCs")
        self.tabs.addTab(self.status_tab, "Status")
        lay.addWidget(self.tabs)

    def closeEvent(self, e):
        self.mon_tab.shutdown()
        e.accept()


def main():
    # make Windows show the panel's own taskbar icon (not pythonw's)
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("f2.panel")
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    app.setFont(QFont("Segoe UI", 10))
    icon = f2_icon(64)
    app.setWindowIcon(QIcon(icon))
    try:
        icon.save(str(core.HERE / "F2.ico"))
    except Exception:
        pass
    w = MainWindow(); w.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
