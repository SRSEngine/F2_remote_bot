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
    """Background: every ~5 s, snap each running remote + read bot state/health.
    All pipe IO stays on this thread; bot commands come through a queue."""
    update = Signal(str, object, str, str, bool)  # console, QImage|None, botstate, health, running

    def __init__(self, interval=5.0):
        super().__init__()
        self.interval = interval
        self.consoles: list[str] = []
        self._links = {}
        self._cmds: "queue.Queue[tuple]" = queue.Queue()
        self._stop = False

    def set_consoles(self, consoles):
        self.consoles = list(consoles)

    def enqueue(self, console: str, action: str):
        self._cmds.put((console, action))

    def stop(self):
        self._stop = True

    def _link(self, console):
        import remoteio
        if console not in self._links:
            self._links[console] = remoteio.RemoteLink(console)
        return self._links[console]

    def _drain_cmds(self):
        import remoteio  # noqa
        while True:
            try:
                console, action = self._cmds.get_nowait()
            except queue.Empty:
                return
            link = self._link(console)
            if action == "start":
                link.bot_start()
            elif action == "pause":
                st = link.bot_state()
                link.bot_resume() if st == "pause" else link.bot_pause()
            elif action == "stop":
                link.bot_stop()

    @staticmethod
    def _qimage(bgr):
        if bgr is None:
            return None
        import numpy as np
        if not bgr.flags["C_CONTIGUOUS"]:
            bgr = np.ascontiguousarray(bgr)
        h, w = bgr.shape[:2]
        return QImage(bytes(bgr.data), w, h, 3 * w, QImage.Format_BGR888).copy()

    def run(self):
        import remoteio  # loads founder; may take a moment
        while not self._stop:
            self._drain_cmds()
            for console in list(self.consoles):
                if self._stop:
                    break
                if not remoteio.is_running(console):
                    self.update.emit(console, None, "", "", False)
                    continue
                link = self._link(console)
                state = link.bot_state()
                health = link.health()
                img = self._qimage(link.snap_bgr())
                self.update.emit(console, img, state, health, True)
            # responsive wait
            steps = max(1, int(self.interval / 0.2))
            for _ in range(steps):
                if self._stop or not self._cmds.empty():
                    break
                time.sleep(0.2)


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
        self.ident_lbl.setText(self.ident_lbl.fontMetrics().elidedText(ident, Qt.ElideRight, self.TW))

    def set_account(self, account):
        self.account = account
        self._set_ident()
        self.plat_lbl.setText(" Series " if self._is_series() else " One ")

    def _fill_combo(self):
        """Auto + every account of this console with its SBC progress; selects self.pick."""
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
                    complete=None, progress=None):
        self.running = running
        self.botstate = botstate
        if token_saved is not None:
            self.token_saved = token_saved
        if complete is not None:
            self.complete = complete
        if progress is not None:
            got, total = progress
            self.prog.setText(f"SBC {got}/{total}" if total else "")
            self.prog.setStyleSheet(f"color:{GREEN2 if got and got >= total else MUTED}; font-size:11px;")
        color, label = BOT_UI.get(botstate, BOT_UI[""])
        if not running:
            color, label = "#3a3a3a", "OFF"
            if self.complete:
                color, label = GREEN2, "DONE ✓ all accounts"
        self.setStyleSheet(
            f"RemoteTile {{ background:{CARD}; border:2px solid {color}; border-radius:12px; }}")
        self.status.setText(label)
        self.status.setStyleSheet(f"color:{color}; font-weight:700; font-size:12px;")
        if not running:
            self.thumb.setText("OFF"); self.thumb.setPixmap(QPixmap())
        # account picker: locked while the remote runs (its token belongs to the running account);
        # refresh the SBC counts when off, unless the list is open right now
        self.combo.setEnabled(not running)
        if not running and not self.combo.view().isVisible():
            self._fill_combo()
        # rebuild buttons for the current mode
        self._clear_btnrow()
        if running:
            b_start = QPushButton("Start"); b_start.setObjectName("primary")
            b_start.clicked.connect(lambda: self.botStart.emit(self.console))
            b_pause = QPushButton("Resume" if botstate == "pause" else "Pause"); b_pause.setObjectName("warn")
            b_pause.clicked.connect(lambda: self.botPause.emit(self.console))
            b_stop = QPushButton("Stop"); b_stop.setObjectName("danger")
            b_stop.clicked.connect(lambda: self.botStop.emit(self.console))
            for b in (b_start, b_pause, b_stop):
                b.setFixedHeight(28); b.setMinimumWidth(62); self.btnrow.addWidget(b)
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
        COLS = 5
        for idx, console in enumerate(sorted(self.remotes.keys(), key=lambda s: (len(s), s))):
            rem = self.remotes[console]
            tile = RemoteTile(console, rem.account, self._accounts(console), self._pick_key(console))
            tile.pickAccount.connect(self.on_pick)
            tile.startRemote.connect(self.start_remote)
            tile.loginBrowser.connect(lambda c: self.start_remote(c, force_login=True, show_browser=True))
            tile.deleteToken.connect(self.on_delete_token)
            tile.resetProgress.connect(self.on_reset_progress)
            tile.botStart.connect(lambda c: self.worker.enqueue(c, "start"))
            tile.botPause.connect(lambda c: self.worker.enqueue(c, "pause"))
            tile.botStop.connect(lambda c: self.worker.enqueue(c, "stop"))
            tile.toggleWindow.connect(self.on_toggle_window)
            self.tiles[console] = tile
            tile.apply_state(False, "", "", token_saved=rem.has_token(),
                             complete=self._tile_complete(console),
                             progress=core.done_count(rem.account.key()))
            self.grid.addWidget(tile, idx // COLS, idx % COLS)
        self.worker.set_consoles(list(self.remotes.keys()))
        self._update_summary()

    def _accounts(self, console):
        return core.consoles(self.accounts_tab.accounts).get(console, [])

    def _pick_account(self, console, accs):
        # a manual pick (account dropdown on the tile) wins; otherwise the first unfinished account
        return self._manual(console) or core.next_account(accs) or accs[0]

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
        if not rem or (rem.proc and rem.is_alive()):
            return                                   # running: the dropdown is locked anyway
        picks = self.state.setdefault("pick", {})
        if key:
            picks[console] = key
        else:
            picks.pop(console, None)
        core.save_state(self.state)
        accs = self._accounts(console)
        rem.account = self._manual(console) or core.next_account(accs) or accs[0]
        tile = self.tiles.get(console)
        if tile:
            tile.set_account(rem.account)
            tile.apply_state(False, "", "", token_saved=rem.has_token(),
                             complete=self._tile_complete(console),
                             progress=core.done_count(rem.account.key()))
            self._set_status(console, "MANUAL: " + (rem.account.Gamertag or rem.account.key())
                             if key else "AUTO", BLUE if key else MUTED)

    # ---- snapshot updates ----
    def on_update(self, console, qimage, botstate, health, running):
        self.last[console] = (running, botstate, health)
        tile = self.tiles.get(console)
        if not tile:
            return
        rem = self.remotes.get(console)
        accs = self._accounts(console)
        # --- rotation: active account finished all SBCs -> next account on this console ---
        # (Auto only: a hand-picked account just runs; the user decides what comes next)
        if (running and rem and core.is_complete(rem.account.key()) and console not in self._advancing
                and self._manual(console) is None):
            self._advancing.add(console)
            QTimer.singleShot(0, lambda c=console: self._advance(c))
            return
        got, total = core.done_count(rem.account.key()) if rem else (0, 0)
        tile.apply_state(running, botstate, health,
                         token_saved=rem.has_token() if rem else None,
                         complete=self._tile_complete(console),
                         progress=(got, total))
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

    def _stop_console(self, console):
        rem = self.remotes.get(console)
        if rem and rem.proc and rem.is_alive():
            rem.stop()
            return
        import remoteio
        info = remoteio.running_remote(console)
        if info:
            try:
                import ctypes
                h = ctypes.windll.kernel32.OpenProcess(1, False, int(info["pid"]))
                ctypes.windll.kernel32.TerminateProcess(h, 0)
                ctypes.windll.kernel32.CloseHandle(h)
            except Exception:
                pass
        if rem:
            rem.status = "stopped"; rem.started_at = 0.0

    # ---- window show/hide ----
    def on_toggle_window(self, console):
        import remoteio
        hwnd = remoteio.window_hwnd(console)
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
        prog = core.load_progress()
        for a in self._accounts(console):
            prog.pop(a.key(), None)
        core.save_progress(prog)
        self.rebuild()

    # ---- start / login ----
    def start_remote(self, console, force_login=False, show_browser=False):
        rem = self.remotes.get(console)
        if not rem:
            return
        accs = self._accounts(console)
        manual = self._manual(console)
        if manual is not None:
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
        core.set_active(a, console)        # tell the bot which account this is
        if not a.MicrosoftEmail or not a.MicrosoftPass:
            tile = self.tiles.get(console)
            if tile:
                tile.status.setText("NO CREDENTIALS"); tile.status.setStyleSheet(f"color:{RED};font-weight:700;")
            return
        tok = rem.token_path()
        if force_login and tok.exists():
            try: tok.unlink()
            except Exception: pass
        if tok.exists():
            self._launch(console); return
        tile = self.tiles.get(console)
        if tile:
            tile.status.setText("SIGNING IN..."); tile.status.setStyleSheet(f"color:{BLUE};font-weight:700;")
        th = LoginThread(rem, show=self.show_cb.isChecked() or show_browser)
        th.log.connect(lambda c, line: self._set_status(c, line, BLUE))
        th.done.connect(self._on_login_done)
        self.threads[console] = th
        th.start()

    def _set_status(self, console, text, color=MUTED):
        tile = self.tiles.get(console)
        if tile:
            tile.status.setText(text[:40]); tile.status.setStyleSheet(f"color:{color};font-weight:700;font-size:11px;")

    def _on_login_done(self, console, ok, message):
        if ok:
            self._launch(console)
        else:
            self._set_status(console, message, RED)

    def _launch(self, console):
        rem = self.remotes.get(console)
        try:
            rem.launch_xbrp(minimized=True)
            self._set_status(console, "STARTING...", GREEN2)
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

    def on_stop_all(self):
        res = QMessageBox.question(self, "Stop all", "Close all running remotes?",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if res != QMessageBox.Yes:
            return
        import remoteio
        for console, rem in self.remotes.items():
            if rem.proc and rem.is_alive():
                rem.stop()
            else:
                info = remoteio.running_remote(console)
                if info:
                    try:
                        import ctypes
                        h = ctypes.windll.kernel32.OpenProcess(1, False, int(info["pid"]))
                        ctypes.windll.kernel32.TerminateProcess(h, 0)
                        ctypes.windll.kernel32.CloseHandle(h)
                    except Exception:
                        pass

    def _check_exits(self):
        self._update_summary()

    def _update_summary(self):
        try:
            import remoteio
            run = sum(1 for c in self.remotes if remoteio.is_running(c))
        except Exception:
            run = 0
        self.summary.setText(f"{len(self.remotes)} consoles  •  {run} active remotes")

    def shutdown(self):
        try:
            self.worker.stop(); self.worker.wait(2000)
        except Exception:
            pass


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
    COLS = ["Console", "Account", "Platform", "Used", "Token", "Remote", "Bot", "SBCs"]

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
        bar.addStretch(1); bar.addWidget(self.count)
        lay.addLayout(bar)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (0, 2, 3, 4, 5, 6, 7):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        lay.addWidget(self.table)

    def refresh(self):
        try:
            import remoteio
        except Exception:
            remoteio = None
        accounts = self.accounts_tab.accounts
        groups = core.consoles(accounts)
        remotes = self.mon_tab.remotes
        self.table.setRowCount(0)
        online = 0
        for a in accounts:
            console = (a.Console or "").strip()
            if not console:
                continue
            r = self.table.rowCount(); self.table.insertRow(r)
            rem = remotes.get(console)
            used = bool(rem and rem.account.key() == a.key())
            running, botstate, health = self.mon_tab.last.get(console, (None, "", ""))
            if running is None and remoteio is not None:
                running = remoteio.is_running(console)
            token_ok = (core.TOKENS_DIR / f"acct_{core.acct_slug(a.key())}.json").exists()
            if running and used:
                online += 1
            got, total = core.done_count(a.key())
            acc_done = total > 0 and got >= total

            def cell(text, color=TEXT, bold=False):
                it = QTableWidgetItem(text)
                it.setForeground(QColor(color))
                if bold:
                    f = it.font(); f.setBold(True); it.setFont(f)
                return it

            self.table.setItem(r, 0, cell(console, GREEN2, True))
            self.table.setItem(r, 1, cell(a.Gamertag or a.MicrosoftEmail or a.EAEmail or "-"))
            self.table.setItem(r, 2, cell("Series" if "one" not in (a.Platform or "").lower() else "One", MUTED))
            self.table.setItem(r, 3, cell("running" if (used and running) else "yes" if used else "standby",
                                          GREEN2 if used else MUTED))
            self.table.setItem(r, 4, cell("saved" if token_ok else "-", GREEN2 if token_ok else MUTED))
            self.table.setItem(r, 5, cell("running" if (used and running) else "stopped",
                                          GREEN2 if (used and running) else MUTED))
            if used and running:
                color, label = BOT_UI.get(botstate, BOT_UI[""])
                self.table.setItem(r, 6, cell(label, color, True))
            else:
                self.table.setItem(r, 6, cell("-", MUTED))
            self.table.setItem(r, 7, cell(f"{got}/{total}" + (" ✓" if acc_done else ""),
                                          GREEN2 if acc_done else (TEXT if got else MUTED), acc_done))
        self.count.setText(f"{len(accounts)} accounts  •  {len(groups)} consoles  •  {online} active")


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
    w = MainWindow(); w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
