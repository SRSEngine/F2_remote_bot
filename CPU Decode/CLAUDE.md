# CLAUDE.md — "CPU Decode" remote (read this first)

## خلاصه برای کاربر (فارسی)
این پوشه نسخه‌ی آماده‌ی ریموت سبک ایکس‌باکس (xbrp) با روش «CPU Decode» است:
- روی `xbrp.exe` دوبار کلیک کنید. پنجره‌ی سیاه ندارد. تصویر روی مانیتور سمت راست و پنل «تنظیمات ریموت» کنارش باز می‌شود.
- با پنل در لحظه اندازه (۹۶۰×۵۴۰، ۱۲۸۰×۷۲۰، ۱۹۲۰×۱۰۸۰ تمام‌صفحه) و فریم (۵، ۱۰، ۳۰، ۶۰) عوض می‌شود. آخرین انتخاب ذخیره می‌شود. ✕ پنل، ریموت را می‌بندد.
- گزارش برنامه در `xbrp.log` است. فایل `xbrp_token.json` ورود حساب شماست: این پوشه را به کسی ندهید.
- اگر چت پاک شد: یک چت جدید در همین پوشه یا پوشه‌ی پروژه باز کنید و بگویید «CLAUDE.md را بخوان». همه‌چیز در ادامه نوشته شده است.

---

Everything below is for the coding agent. Reply to the user in **Persian only** (also short status lines).

## 0. Context
- Owner: Persian-speaking user, Windows 11 PC. They run Xbox bots (FBH / "Bot Manager RP v2", process `CustomXBRP.exe`)
  on many consoles and want their own remote viewer with the lowest possible resource use.
- **xbrp** = lightweight Xbox Remote Play *viewer* in Go (video only: no audio; sends an idle gamepad heartbeat and
  anti-idle stick nudges). This folder is the ready-to-use copy of the **cpu** method + live control panel.
- Source code and full history: `C:\Users\Reach\Desktop\New folder (3)` — read its `CLAUDE.md`, `docs/HANDOFF.md`
  (sections 10 and 11) and `docs/EXPERIMENTS.md` (experiments #1-#58).
- Live results dashboard (Claude artifact): https://claude.ai/artifact/818qcoKuHBpHpEt5MNqKne
  (db collections `runs`, `ranking` with field `total`, doc `meta/status`; written with the ArtifactData tool).
- Account has one console: "XBOX" (Xbox Series S). FBH may stream a DIFFERENT console (user confirmed on 2026-10-02).

## 1. Files in this folder
| File | What |
|---|---|
| `xbrp.exe` | windowsgui build (no console window) of the project, built 2026-10-02 19:24 with transport-cc + watchdog |
| `avcodec-62.dll`, `avutil-60.dll`, `swresample-6.dll` | FFmpeg decoder used by `-decoder ffmpeg` (preset cpu) |
| `openh264-2.6.0-win64.dll` | Cisco OpenH264, fallback CPU decoder |
| `xbrp-settings.json` | options for a double-click start (keys = command-line flag names); the panel saves `window` and `drawfps` here |
| `xbrp_token.json` | Microsoft login (refresh token). SECRET: never print, log, upload or commit it |
| `xbrp.log`, `xbrp-previous.log` | log of the current / previous run (no console, so the log goes here) |
| `CLAUDE.md` | this file |

Current settings (user's last panel choice): `{"preset": "cpu", "panel": true, "window": "1280x720", "drawfps": 5}`.

## 2. What a double-click start does
- No arguments -> `loadSettings()` applies `xbrp-settings.json` (settings.go). Started WITH arguments (scripts) the file is ignored.
- preset `cpu` = `-decoder ffmpeg -render d3d -drawfps 10 -bitrate 2500` (only for flags not set): FFmpeg decodes on the CPU
  (GPU Video Decode engine stays at 0 %, like FBH), Direct3D 11 flip-model swap chain draws, `b=AS:2500` caps the video.
- The console always sends 1280x720 H.264 at 60 fps, ~2.0-2.5 Mbit/s. All frames are decoded; only `drawfps` of them are drawn.
- Window opens on the monitor with hardware overlay planes (MPO): `\\.\DISPLAY1` (right monitor, HDMI, x 1920-3840),
  at x = left+16, y = bottom - height - 90. There DWM adds almost nothing.
- windowsgui build (noconsole.go): stdout/stderr go to `xbrp.log`; login code and fatal errors appear in Persian message boxes;
  with several consoles on the account it stops and asks for `"console": "<name>"` in the settings file.
- Auto-reconnect on session end; anti-idle nudge (LeftThumbX 3000/32767 for 150 ms) on the server's idle warning and every 8 min
  (the server warns after ~10 min without input and kicks 120 s later).

## 3. Control panel (`-panel`, panel.go)
- Dark Xbox-style window painted by hand (GDI+ rounded shapes, GDI text, Segoe UI + Segoe MDL2 Assets icons), green
  (#107C10) = chosen option, hover/pressed colors, DWM rounded corners + green border. Owned by the video window
  (always above it, also in full screen; closes with it). Drag by the top bar. ✕ (or closing the panel) closes the remote.
- Sizes: 960x540, 1280x720 (1:1 pixels = sharpest), 1920x1080 = borderless full screen on the video's monitor.
  FPS: 5 / 10 / 30 / 60 (60 = draw every picture). Changes are live (`setSize`, `setFPS` on the window thread).
- Size changes only the window, not the stream quality (1920x1080 is the 720p picture upscaled).
- Test hook: send `WM_COMMAND` (wParam = id: 101-103 sizes, 201-204 fps, 1 = close) to window class `XBRPPanel`;
  the video window class is `XBRPVideo`. Project script: `scripts\panel_check.ps1`.

## 4. Network / stability (important history)
- Old fixes: RTX repair stream, NACK every 20 ms, time-based samplebuilder (250 ms), SPS/PPS cache, 4 MB UDP buffer.
- REMB is OFF: sending REMB made the console collapse its bitrate (#41).
- **transport-cc (TWCC) feedback is ON** (`-twcc`, `webrtc.ConfigureTWCCSender`), since 2026-10-02 19:18.
  Before it, after a Wi-Fi hiccup the console flooded ~10 Mbit/s of probe packets (~3000 small packets/s), throttled
  the video to ~0.1 Mbit/s and 2-19 fps and never recovered (sessions collapsed 40 s to 4 min after start).
  With TWCC: 6-min test and a 13-min user session at 60 fps / 2.0-2.2 Mbit/s, no collapse (#58).
  Log line to check: `Console answer (video): ... | transport-cc on`.
- Watchdog (stream.go, `slowFPS` = 20): fewer than 20 decoded fps for 3 stats intervals (~30 s) ends the session and the
  reconnect loop opens a fresh one (log: `Session ended (video stayed below 20 fps for 30 s) - reconnecting`).
- The PC is on Wi-Fi (old TP-Link Wireless-N adapter, 300 Mbps link). A wired LAN (console first) is recommended;
  no code change is needed for a cable (WebRTC uses whatever interface Windows routes).

## 5. Measured numbers (this PC; scripts\measure.ps1)
- The user's metric is TOTAL GPU = 3D + Video Decode + extra DWM, plus picture quality by eye.
- 15-s demo, total GPU: cpu 1.9 % < mpv (old player) 9.2 % < smooth 11.7 % < lite 12.0 % < full 15.3 %
  (GPU-decode presets pay ~11 % Video Decode). Quality by eye: lite low, smooth/cpu/full fair, mpv best (60 fps).
- cpu preset, 1280x720 window, 20 s each: 30 fps 1.6 % total GPU / CPU 0.51 %; 10 fps 1.0 % / 0.54 %; 5 fps 0.7 % / 0.44 %.
  Full screen costs ~2x GPU (30 fps full screen 2.9 %). RAM 33-35 MB. Video Decode 0.
- 6-min TWCC test: CPU 0.43 %, viewer 3D 1.3 %, RAM 35 MB, 0 dropped.
- FBH reference (user's numbers): CPU ~0.2 %, 3D ~2 %, Video Decode 0, RAM ~105 MB.
- Pitfall: a frozen/throttled stream decodes almost nothing, so CPU looks LOWER. Never call that an improvement.

## 6. Rebuild, test, deploy
- Go is portable: `C:\Users\Reach\Desktop\New folder (3)\.tools\go\bin\go.exe` (go1.27.1); pion/webrtc v4.0.10, interceptor v0.1.37.
- Console build (tests, scripts): `go build -trimpath -ldflags "-s -w" -o xbrp.exe .`
- This folder's build: `go build -trimpath -ldflags "-s -w -H windowsgui" -o xbrp-gui.exe .` then copy it here as `xbrp.exe`
  (only while the remote is closed: the exe is locked while running).
- Measure this copy: `powershell -ExecutionPolicy Bypass -File scripts\measure.ps1 -Seconds 60 -Exe "C:\Users\Reach\Desktop\New Remote\CPU Decode\xbrp.exe" -XbrpArgs "-preset cpu -panel -window 1280x720 -drawfps 10"`
  (add `-AllowFBH` when FBH streams another console). It prints JSON: cpu_percent, gpu_process, viewer_3d, valid, ...
- Visual demo of all modes: `demo.bat` / `scripts\demo.ps1` in the project. Console-free tests: `-play results\dump-2500.h264`.
- Read the log of a running console build: `scripts\read_console.ps1 -ProcessId <pid>`; this folder's build writes `xbrp.log`.

## 7. Rules
- Never print/log/commit tokens (`xbrp_token.json`, gsToken, MSA/XSTS). Don't share this folder.
- One stream per console. If `CustomXBRP.exe` (FBH) runs, ask the user which console it streams before starting xbrp.
- Don't modify anything in `C:\Bot Manager RP v2` (licensed reference product) and don't decompile it.
- Ask before installing system-wide software; Go modules / DLLs inside the project folder are fine.
- If a login is needed the program shows a code (message box) -> ask the user to enter it at microsoft.com/link.
- The user watches tests live: keep windows visible (ontop), keep waits short, show results as tables, write in Persian.

## 8. Open items
- At 60 fps in a window only ~54 of 60 pictures are shown on the live stream (present waits with SetMaximumFrameLatency(1));
  latency 2 would show all 60 at the cost of up to one frame of delay. Ask the user before changing.
- `-res 1080` (console sending 1080p) not tested: sharper full screen, ~2x CPU decode.
- FBH not re-measured on the same screen with a visible window.

## 9. Timeline of the 2026-10-02 chat
1. Visual demo of 5 modes (lite, smooth, cpu, full, mpv), 15 s each (`scripts\demo.ps1`, `demo.bat`).
2. User: rank by TOTAL GPU -> cpu method is lightest. Tests of cpu at 30/10/5 fps and 1280x720 (#50-#55).
3. Built the live panel + settings file; deployed this folder; redesigned the panel in Xbox style on request.
4. User's question: resize changes only the window size, not the stream quality.
5. Incident: video collapse after Wi-Fi hiccups -> watchdog, then transport-cc feedback (real fix). No-console build + xbrp.log.
6. User asked about LAN cable: works, recommended (console first).

## 10. Gamepad control (added 2026-10-02 evening)
- Source: pad.go (hub: state, text commands, latency probe, snap), ctlserver.go (pipe/TCP/UDP/WM_COPYDATA/keys/XInput),
  input.go sends the hub's pad state at once on the stream's "input" data channel (23-byte gamepad record, buttons
  Nexus=1<<1 Menu View A B X Y Up Down Left Right LB RB LS RS=1<<15; triggers u16; sticks i16, y up).
- Each remote writes `..\Controller\remotes\<console>.json` (pipe `\.\pipe\xbrp-<console>`, tcp, udp, hwnd). Flags: -ctl (on),
  -ctldir, -ctlname, -keys (keyboard on the video window, default OFF), -xinput N. Hub command `xinput N` switches at run time.
- Tool + docs: `C:\Users\Reach\Desktop\New Remote\Controller` (xbpad.exe, src\, README-FA.md, comparison-FA.md, results\).
- Results: pipe best (local 0.05 ms, end-to-end ~110-125 ms); tcp/udp/wmcopy/keys same range; XInput ~145 ms;
  SendInput unreliable (Windows focus lock); cloud InjectKey ~1.2-1.3 s, only A B X Y dpad Nexus Menu View; SmartGlass UDP 5050 no answer.
  Isolation test: every method reached only its own remote.
- Console gotchas: on Home, B resumes the suspended game (FC 25); Nexus in a game opens the guide. Use D-pad left/right for tests.
- Previous exe kept as `xbrp-before-controller.exe`.

## Update 2026-10-05: stream status + reconnect in the panel
- Panel shows a status line refreshed every second (health.go): green "healthy" (>= 50 fps, no lost packets),
  yellow "weak", red "down" (< 15 fps or no update for 3 s), blue "connecting / reconnecting", with fps and Mbit/s.
- Button "اتصال دوباره" (id 301) ends the session; the normal reconnect opens a new one (~11 s, tested live).
- Broken-picture guard for FFmpeg: when packets are lost for good before a frame (PrevDroppedPackets > 0), that frame
  is not shown, the last clean picture stays (up to 3 s, freezeMaxNoEC) and a keyframe is requested. Before, FFmpeg
  showed smeared green blocks until the next keyframe (it never reports broken frames).
- Test scripts must find windows by THEIR OWN process id (scripts/panel_check.ps1 FindOwn): a class-name search once
  drove and closed the user's running remote.

## Update 2026-10-08: game pad buttons in the panel
- Panel section "دسته": LT LB View Xbox Menu RB RT, D-pad (left cross), LS / RS (middle), Y X B A (right cross,
  Xbox colors). Mouse down = button down, mouse up = button up (held at least 80 ms), via the same pad hub
  (`hub.handle("panel", "down a")`) that Play.py uses through the pipe. Panel ids 401+ (`padKeys`).
- Panel height is now 462 px at 100 % scaling.

## 12. Bot control from the panel (2026-10-08)
- Panel (panel.go, now 380x700): row «ربات» with شروع / توقف موقت↔ادامه / توقف (ids 501/502/503, WM_COMMAND test hook)
  and an 8-line bot log box above the hint. Repeated lines count up (×N). Lines with digits/Latin are drawn LTR with
  U+200E marks after Persian phrases (botctl.go ltrSafe) so numbers keep their order.
- New file botctl.go (state run/pause/stop/wait + log ring). New pipe commands in pad.go:
  `log <text>`, `bot`, `bot run|pause|stop|wait`, `health` (ok/weak/down/connecting/reconnecting, "none" = no stream,
  e.g. -play), `reconnect` (= panel button).
- Python: `Controller\remotectl.py` (Control: checkpoint = log + bot state + health; down -> wait 8 s -> reconnect up to
  3x45 s -> RemoteDown). xbox.py: checkpoint before every press/down/stick, `wait()` honours pause/stop, new exports
  `log`, `wait_start`, `bot_check`, `BotStopped`, `RemoteDown`. founder.py: checkpoint + one log line per top-level
  see/find/read/... (nested calls not logged), `until()` checks pause/stop, `Remote.snap` retries 3x with health check.
  Old xbrp ("err unknown command") -> all of this silently off. Play.py needs no change.
- Deployed: xbrp.exe and xbrp-multi.exe replaced (old ones kept as *-before-botctl-<time>.exe). Tested offline with
  `-play results\dump1.h264 -panel -ctlname BOTTEST -ctldir <temp>` (never touch the user's live remote).
- 2026-10-09: panel Start can LAUNCH the bot. Busy bots ask `bot seen <pid> <run>` (remotectl: run id per process,
  renewed per IPython cell via pre_run_cell). Start: paused -> resume; a bot asked within 3 s -> just run; else launch
  `python -u ..\Play\run_bot.py` (flags -botscript/-botpython; hidden, output in Play\run_bot.log). Stop stops only the
  busy run (a new run/cell clears it); a panel-launched bot still alive 10 s after Stop is killed.
  `Play\run_bot.py` execs Play.py from the top to the end of the `# %% Main` cell (test cells after Main are skipped).
  Tested with a fake bot via -botscript on the BOTTEST play-file remote (7/7). Old exes: *-before-start-<time>.exe.
- 2026-10-09: panel checkbox «XS» (id 504, next to «ربات»): on = platform "Ser", off = "One"; saved as "xs" in
  xbrp-settings.json (flag -xs, default true). Pipe: `platform` -> "ok Ser|One", `xs on|off`. Python: xbox.platform().
  Play.py Main calls find_platform(platform()). Old exes: *-before-xs-<time>.exe.
- 2026-10-09: pipe server grows instances on demand (always one free, max 255; was fixed 4 -> 'Errno 22' when busy). xbox.py pipe method sends control commands on its button connection (2 connections per Python process). Old exes: *-before-pipes-<time>.exe.

## Update 2026-10-10: panel and logs in English
- User rule: the whole remote panel and its reports must be ENGLISH (still talk to the user in Persian).
  Translated: panel labels/buttons/status (panel.go), bot states and bot log lines (botctl.go, pad.go), message boxes
  (main.go, auth.go, noconsole.go; no RTL flags), Python log lines sent to the panel (Controller/remotectl.py,
  Controller/xbox.py checkpoints, Founder/founder.py `_describe`). Section labels are left-aligned now.
- New text shown in the panel or in xbrp.log must be English.

## Update 2026-10-10 (panel docking)
- The panel opens right next to the remote (on its right; on its left if there is no room) and follows it when the remote window moves or changes size.
- The panel title bar has a minimize button (WM_COMMAND id 2): it minimizes the remote, and the panel hides and comes back with it (owned window).
- Clicking the panel brings the remote up right under it (WM_ACTIVATE), so both come to the front together.
- Code: `ctlPanel.dock()` in panel.go, WM_MOVE in win_window.go. Backups: `*-before-dock-<stamp>.exe`.

## Update 2026-10-11: Founder (image find + OCR) summary
- Founderounder.py: see() = template first, then text (find_text); SEE_IMAGE 0.90 / SEE_TEXT 0.95 (0.8 accepted
  "25 Xbox Seri" for "27 XBOX Ser"); contains() exact by default; text matching normalizes OCR look-alikes (q=g, 0=o, 1=l).
- CPU: MAX_AGE 0.3 s frame reuse, regrab after every press (remotectl.mark_input/input_seq hooked in xbox.py),
  OCR cache by region pixels, POLL 0.25 s. Offline: 21 -> 12 snaps per 3 s wait, Python CPU 344 -> 172 ms. Backup Play\Backupefore-perf-*.
- GPU: Python side uses none (measured offline). gpu_watch.ps1 in Founder reads per-process GPU/CPU counters only.
  Biggest remaining cost = savePNG per snap on the video window thread (per-pixel float YUV->RGB + PNG); shared memory not done.
- Minimized remote: decode + hub.onFrame (snap) continue, only drawing is skipped (win_window.go IsIconic check).
- Play.py templates = Screenshot\Shots (RemoteShot crops, 1:1 at 100% DPI). pick.py = region/template picker on the stream picture.


## Update 2026-10-10/11: F2 account panel (New Remote\Pannel) + per-account SBC progress
Built a PySide6 control panel, renamed **F2**, in `C:\Users\Reach\Desktop\New Remote\Pannel`
(panel.py UI, core.py data/remotes, remoteio.py pipe/snap bridge, mslogin.py MS login; README-FA.md; data/, tokens/, logs/).
Four tabs: Accounts (import CSV `Console,Gamertag,MicrosoftEmail,MicrosoftPass,MicrosoftGauth,EAEmail,EAPass,EAGauth,Platform`),
Monitor (responsive wall of live thumbnails via `snap`, bot Start/Pause/Stop, Show/Hide window), SBCs (set/challenge/csv list,
seeded from Marquee{n}.csv), Status (per-account row). UI is English; chat stays Persian.

Key design:
- **Per ACCOUNT, not console.** Many accounts share a console (Console column groups them) and run one at a time.
  Tokens `tokens\acct_<emailslug>.json`; progress `data\sbc_progress.json` keyed by account email; `data\active.json`
  = which account is on each console now.
- **SHARED_REMOTE=True** (core.py): one remote per console stays open; the BOT switches game accounts on the console
  (Play.py `switch_account`/`next_bot_account`/`AUTO_SWITCH`), verifies the Home gamertag and calls
  `panel_core.set_active(acc, REMOTE)` so progress lands on the right account.
- **Bot hook**: Play\report.py `Reporter.challenge_done(n)` writes "Marquee n" (or the SBC name) into sbc_progress.json
  under active.json's account; Play.py calls it at the two challenge-complete points. Backups in Play\Backup\before-*.
- Launch: `xbrp-multi.exe -token <acct.json> -preset cpu -panel -ctlname <console> -xs=<series>`. Panel sends `bot wait`
  on launch (xbrp defaults bot.state to run) so a fresh tile shows WAITING+Start, not RUNNING; sends `xs on/off` to
  match the console's current account; reads `bot`/`health` every ~1.2 s, snaps every ~5 s; closing F2 closes all remotes.
- Tile: blue border before start and when done; green Start / red Stop two-state button synced with bot.state.

Login: xbrp only has device-code; the panel does email/pass/Gauth(TOTP) via Playwright on system Edge/Chrome, clicks
"Use your password", captures the code redirect, saves refresh_token. Deps PySide6/requests/pyotp/playwright installed.

CAUTION learned 2026-10-11: never run panel.MainWindow()/shutdown()/the SnapWorker against live data in a test — the
worker probes live remotes and shutdown()/_terminate_all() CLOSES them. Accounts source CSV: Desktop\template2.csv.
