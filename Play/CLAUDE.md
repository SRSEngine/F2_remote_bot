# CLAUDE.md — Play (the bot) — read this first

## خلاصه برای کاربر (فارسی)
- `Play.py` ربات SBC است (سلول‌به‌سلول در VS Code، یا با دکمه‌ی «Start» پنل ریموت از طریق `run_bot.py`).
- فهرست SBCها از پنل حساب‌ها می‌آید (`Pannel\data\sbcs.json`): هر ست به ترتیب پیدا می‌شود، چالش‌هایش
  (عدد ۱-۴، اسم چالش، یا خالی = تک‌چالشی) اجرا و Submit می‌شود. بازیکن‌ها از CSV همان SBC.
- هر بازیکن: اول در Club جستجو، نبود از Transfer Market خریده می‌شود. فیلترها فقط اگر عوض شده باشند تنظیم می‌شوند.
- پشتیبان‌ها: `Play\Backup\`. گزارش گیر کردن ربات: `New Remote\Report\<ریموت>.log`.
- اگر چت پاک شد: چت جدید باز کنید و بگویید «Play\CLAUDE.md را بخوان».

---
Everything below is for the coding agent. Reply to the user in **Persian only**. Text shown in the remote panel /
bot log must be **English**. Never test against the live remote (use saved screenshots + founder `FileSource`).
Before editing Play.py check VS Code hot-exit backups (`%APPDATA%\Code\Backups\*\file\*` newer than Play.py =
unsaved buffer): if unsaved, don't write the file — give the code in chat. Always back up to `Play\Backup\` first.

## Files
| File | What |
|---|---|
| `Play.py` | the bot. First cell `#%%` = setup + all functions; `# %% Main` = the run; cells after Main = manual tests |
| `run_bot.py` | runs Play.py from the top to the end of the `# %% Main` cell (panel Start launches it; output `run_bot.log`) |
| `report.py` | `Reporter` (other session): `Report\<REMOTE>.log`, shots, `challenge_done(name)` -> `Pannel\data\sbc_progress.json` |
| `region.py` | old standalone region picker (superseded by the picker code inside Play.py) |
| `Backup\` | `Play-before-<change>-<time>.py` copies |

## Building blocks added in the 2026-10-06 .. 10-10 chat (all coordinates = remote frame 1280x720)
- **List pickers** (`pick`, `locate`, `cells`, `cursor`, `go_tab`, `go_cell`, `checked`, `letter_tab`):
  config dicts `REGION_PICK`, `LEAGUE_PICK`, `CLUB_PICK` (no tabs), `RARITY_PICK` (multi-select, green tick).
  OCR of the whole grid with flags/logos masked (`TEXT_X`), highlighted cell = brighter strip, match order:
  exact -> fuzzy 0.85 -> part of the name ("Bournemouth" = "AFC Bournemouth"). Not found -> Down x5 then x1.
- **Filters**: `Region/League/Club` via `set_list_filter(xy, name, PICK, marker, tab, club)`; `Rarity`, `Position`,
  `Pricing` (no-op with `club=True`). `is_off()` = empty/OFF. `club=True` = Club "Player Search" page.
- **Panel navigation** (no templates): `selected_panel` (brightest panel, median > 65) + `GoPanel(name, PANELS)`.
  `MARKET_PANELS` / `MARKET_BY_XY` (FindFilter), `CLUB_PANELS` / `CLUB_BY_XY` (GoFilter club), `CHALLENGE_PANELS` 1-4.
- **SetFilters(row, last, club)**: sets only changed filters (`last_club` / `last_market`, cleared each challenge);
  league change forces Club; price always.
- **Shared regions**: `MULTI, SWAP, REFRESH, FUT2, BUYNOW, SEARCH, STATS`; `on_results()`.
- **Loop helpers**: `enter_slot, search_club, clear_slot, back_to_market, use_club_card`.
- **SBC plan** (2026-10-10): `load_plan()` reads enabled entries of `Pannel\data\sbcs.json`
  (`{"set","challenge","csv","enabled"}`), groups by set, keeps order (no file -> Marquee 1-4).
  `open_set(name)` = old open_marquee with a name (template image if one has that name, else OCR text in `SET_ROW`).
  `back_to_sbc()` = B until "Open SBC", then A. `load_rows(e)` = entry csv, else `<set><challenge>.csv`, `<set>.csv`.
  `open_sbc_challenge(e)`: digits -> `OpenChallenge(n)`; text -> tile whose title contains it; empty -> skipped.
- **Set page** (2026-10-10): `on_set_page()` reads the set name in the blue banner `SET_BANNER (630,112,520,50)`
  ("6 Days Remaining | Marquee Matchups | 1/4 ..."); Marquee also accepts the `V` logo. `CURRENT_SET` is set by the
  main loop. Used by `OpenChallenge`, `Submit(single)` (single-challenge set: done after Congratulations/Claim and out
  of the squad) and after `open_set` (wrong set -> `pause_fix`).
- Platform: `find_platform(platform())` — panel checkbox XS (on = Ser, off = One).

## Not verified on the console (only on screenshots / fake remotes)
- SBC hub layout for non-Marquee sets (`SET_ROW`, 4 columns), `back_to_sbc` path, banner of other sets,
  end screen of single-challenge sets. Ask the user for screenshots before changing these.

## Tests used (scratch scripts, no remote)
- Pickers on screenshots of the country / league / club / rarity lists; panel detection on Transfer Market and Club
  search screenshots; challenge detection (selected, Completed badge) and banner reading on the Marquee page.
- `load_plan` / `load_rows` / `open_sbc_challenge` dry runs with stubbed functions.

## 2026-10-10 .. 10-11 chat (robustness, accounts, 2FA, keyboard, switch) — Persian summary in README-FA.md
- **Every function returns bool, every loop is capped**; `wait(100)` first in each game loop. Failures go to
  `pause_fix(what, hint)` (bot pauses, panel log "⏸ ... failed. Fix it by hand: ..., then press Resume"; Resume
  continues). Main helpers: `handle_popups, at_squad, back_to_squad, run_challenge, do_row, run_row, fill_squad`.
- **Report**: `report.py` Reporter -> `Report\<REMOTE>.log` + `Report\shots\<REMOTE>\` (ASCII names). `my_remote()`
  picks REMOTE from parent pid vs `Controller
emotes\*.json`. Read the newest block there first when stuck.
- **START_STEPS**: GotoHome, CheckAccount, CloseRecent, find_platform, FindUltimate, MainUltimate, FindSBC.
- **Accounts (SHARED_REMOTE in Pannel/core.py)**: one remote account per console; bot loops the console's game
  accounts (`console_accounts, next_bot_account`), `read_gamertag` in `GAMERTAG_BOX (104,54,170,28)`,
  `ensure_account` -> `switch_account` if `AUTO_SWITCH`, re-check, else pause. Credit: `active.json[console]`.
- **BUY reprice**: +`BUY_STEP` when no card or 3 failed buys, cap `BUY_MAX_EXTRA`; Y leaves no-results page.
- **Clear_Squad** (CLEAR_NO/CLEAR_YES templates, find thr .85) at challenge start; Submit missing -> clear+refill once.
- **EA 2FA**: `choose_mobile_app`, `totp/fresh_totp` (RFC 6238 from EAGauth), `enter_ea_code` (type, XMenu, Down, A),
  `ea_two_factor` (called by FindUltimate on "Two"/"Enter"). Never print the secret or codes.
- **Xbox keyboard**: `kb_page` (templates `KB letters`/`KB symbols`), `kb_focus, kb_goto, type_text, kb_clear, type_code`.
- **switch_account(gamertag, email)**: guide -> 5th tab (RB) -> Add or switch -> OCR list (`who_lines/who_match`),
  RT page jumps, error if not on the list. `focus_rect(area)` finds the Xbox focus frame colour-independently
  (theme accent varies) — used by kb_focus and guide_focus.
- **Overlays in front of the set page**: `SBC_INTRO = ("Advance (2)", 32,682,167,24)` first-visit intro, and
  `reward_popup()` (Congratulations/Claim). The dimmed set page behind Claim still matches the V logo and
  View Rewards, so `on_set_page` returns False while `reward_popup()`; `wait_set_page` presses A on either (max 8).
  Root cause of "Open challenge Marquee Matchups 2 failed" (C12, 14:02) was Submit returning before the Claim popup.
- Tests: scratch scripts with fake `xbox` + `founder.Remote` returning saved frames, `isolate.py` stubs Reporter
  output and `challenge_done`; md5 of `Pannel\data\*.json` checked before/after.

## Update 2026-10-11 18:05: console name vs remote name
`REMOTE` (e.g. "C32-2", a 2nd remote of the console) is only for the pipe. `CONSOLE` (suffix "-N" stripped) is used
for everything panel-side: accounts, pick, `set_active`/`get_active`, `Reporter(CONSOLE)` (report C32.log).
report.py `challenge_done` now goes through Pannel `core.mark_sbc_done` (locked + atomic). Backups: Play\Backup\*-before-sync-20261011-180541.py.

## Update 2026-10-11 19:30: BUY reprice fix
The "no cards" page (`NO_CARDS`, "Custom Filters") also shows "Y Search" bottom-left, so `on_results()` was True
there and BUY pressed B -> left the market to the squad -> Pricing failed -> reprice never happened (every log entry
"قیمت ... تنظیم نشد"). Now NO_CARDS is checked first (Y), then on_results (B). `BUY_MAX_EXTRA` 500 -> 1000, BUY
loop 30 -> 60. Submit line 1191 `or ("Submit (3)",...)` (tuple always True -> XMenu every loop) fixed by the user.
Backup: Play\Backup\Play-before-reprice-fix-*.py. Not yet verified on the console that Y on NO_CARDS opens filters.

## Update 2026-10-12 12:23: BUY success = back on the squad
Bug (C34 2026-10-11 20:45): buying the only listed card empties the list -> "Custom Filters" (NO_CARDS) flashes ->
BUY logged "no cards found", repriced, pressed Y on the squad (= Club Search) -> 11th player retried forever although
the squad was full with Submit active. Now after Yes, BUY polls ~3 s (every 0.3 s) for `back_on_squad()` (`Swap (5)` 33,650,151,56
or `Sub (5)`) -> Bought; `confirmed` flag (reset on Expired/The bid/Sorry) also checks it first in every loop turn,
before NO_CARDS. Tested on saved shots: Swap (5) matches squad screens only. Backup: Backup\Play-before-buy-squad-check-*.py.

## Update 2026-10-12: out of coins -> next account
`out_of_coins(price)`: `ACTIONS ("Actions", 27,675,95,35)` bottom-left + `COINS_BOX (194,130,143,25)` ("My Coins",
read only when Actions is seen; on the squad that box reads "3 Days Remaining") < price -> BUY returns `NO_COINS`
(checked after each Y in the first loop and every turn of the buy loop). do_row passes it on, run_row raises
`OutOfCoins` (no retries), the account loop catches it: shot "no_coins", report event "✗ کوین تمام", panel log
"Out of coins: <acc>", account added to done_accounts, next account (open_game from Home). Within one run only:
the panel does not remember it, so the next Start tries that account again.
Tested: coin box read 314776 / 314226 on saved market shots; BUY/run_row simulated (scratch sim_buy.py).
Backup: Backup\Play-before-no-coins-*.py.

## Update 2026-10-12: Last error + out of coins in the panel
report.py: `fail`/`pause`/`stopped(text, en=...)`/`crash` also write an English "last error" for the account active on
this console (`Reporter.panel_error` -> Pannel core.set_last_error, data/account_status.json). OutOfCoins in the Main
account loop calls `rep.no_coins(acc.key(), e)` -> core.set_no_coins; `next_bot_account` Auto skips accounts with
no_coins until the user presses Clear in the panel's Status tab ("Last error" column). Stop from the panel is not an error.

## Update 2026-10-12: Club filter on the Club search page
The Club "Player Search" page resets its Club filter every time, so SetFilters(club=True) now sets Club on every
player (`club_again`), unless the row's Club is OFF (already reset). Transfer Market keeps the change memory
(only changed filters; price always). Backup: Backup\Play-before-club-filter-always-*.py.

## Update 2026-10-12: Transfer Market reuses the Club filters
Filters set on the Club search page carry over to the Transfer Market (user, 2026-10-12). do_row now copies
`last_club` into `last_market` before SetFilters(row, last_market), so the market only sets the price (plus any
filter that failed on the Club page). Backup: Backup\Play-before-market-uses-club-filters-*.py.

## Update 2026-10-12: Start / End coins per account
BUY calls `note_coins()` once the results / no-cards page is up: reads `COINS_BOX` only if the "My Coins" label
(`COIN_LABEL` 85,125,110,32) is there, and `save_coins(coins)` -> Pannel `core.set_coins(key, coins, start=...)`:
first read of the account in this bot run = Start Coin, every read = End Coin (`out_of_coins` also saves its read).
Stored in data/account_status.json `[key]["coins"] = {start, start_at, end, end_at}`; `clear_account_status` (panel
Clear) keeps "coins". Panel Status tab: new columns "Start coins" / "End coins" (end red if lower, tooltip = time +
spent); "Last error" moved to column 10, its Clear is enabled only for last_error / no_coins.
Tested: reads 20016 / 12827 / 6 on saved market shots, nothing on the squad; set_coins on a temp copy; panel table
rendered offscreen with fake data; md5 of Pannel/data unchanged. Backups: *-before-coins-*.py in Play\Backup, Pannel\Backup.

## Update 2026-10-12 16:50: Coin (current) column
core.set_coins now stores `now` (every read) and, on the first read of a run, `start` and clears `end`.
`core.finish_coins(key)` sets `end = now`; Play.py `finish_coins(acc)` calls it when an account is done, out of
coins, or (in the Main `finally`) when the run stopped mid-account. Panel Status: Start coins | Coin | End coins |
Last error (col 11); Account column fixed 150 px (elided). Old data without `now` shows end as Coin.
Backups: *-before-coin-now-*.

## Update 2026-10-12 16:5x: coins from the top-right bar before FindSBC
START_STEPS has ("ReadCoins", read_coins_step, False) before FindSBC: `read_top_coins()` finds template "FUT coin"
in the strip `TOP_COIN (700,38,570,40)` (y fixed, x moves), reads from its right edge to the first green column
(the green token icon), Tesseract first (Windows OCR misses short "4K"), then Windows OCR; `coins_value`: "4K"=4000,
"12.5K"=12500, "1.2M". Result -> save_coins (first read of the run = Start Coin). Tested on the user's Store
screenshot (485), the strip shifted -150/+40 px (485) and a frame with the real "4K" glyphs (4000).
Note: another session changed core.set_coins (start / now; End written by core.finish_coins at the end of the
account) and applied the time-based Submit(timeout=40). Backup: Backup\Play-before-top-coins-*.py.

## Update 2026-10-12: REVERTED "Transfer Market reuses the Club filters"
The user checked: Club filters do NOT carry over to the Transfer Market. do_row no longer copies last_club into
last_market; the market keeps its own change memory again (as before 16:06). Backup: Backup\Play-before-revert-market-filters-*.py.

## Update 2026-10-12 17:3x: Quick Sell menu in BUY -> pause
The user split `Coin (2)` (555,184,55,54 = Quick Sell icon of the card's radial menu; A there sells the card) out
of the `Change` check. Now BUY checks it FIRST (that menu's bottom bar also shows "Change Player", which made the
Change branch press B before): fail_shot("Quick Sell menu") + pause_fix("BUY: card menu (Quick Sell) is open"),
then continue after Resume. Verified on C12 1011_152156_001_BUY.png: both Change and Coin (2) match there.

## Update 2026-10-13: Submit vs Claim / Store / end-of-set screens / SBC page
Root cause of the many "Open challenge ... failed" pauses on the Store screen (31 of 37 such shots): after Submit the
set page shows for a moment, Submit returned True there, Claim + Store came later and wait_set_page did not know Store.
- New: `SET_ADVANCE ("Advance (3)", 27,677,92,35)` (end-of-set "MARQUEE MATCHUPS" screen after 4/4, Welcome to SBC),
  `SBC_HUB_TITLE ("SBC", 150,42,70,30)` + `on_sbc_hub()` (sets page, any tab; set name not needed), `store_open()`.
- Submit: Store (or "Open" not on the hub) -> B; Advance (3) -> A; "Open SBC" (Main) -> A; set page counts only if
  still there after 2.5 s (5 s after Claim while the Store has not come yet) with no Claim/Store/Advance on it;
  on the SBC page -> open_set(CURRENT_SET) + wait_set_page (single set: True).
- wait_set_page: Store -> B, Advance (3) -> A (besides Claim and SBC intro).
Checked on saved shots: Store found on 31/37 Open-challenge pauses (the rest = SBC page); "SBC" title only on the 4
SBC-page shots; the end-of-set screen does not look like the set page (no V logo / banner). Simulated (scratch
sim_submit.py): normal, Store 1.5/4/6 s late, 4th challenge -> 2 Advance -> SBC page -> set reopened, no Submit button
-> False after ~5 s. Backup: Backup\Play-before-store-advance-hub-*.py.

## Update 2026-10-13: no duplicate players from the Transfer Market
`SQUAD_NAMES` = names of the players put in the current challenge squad (cleared at challenge start and on the
Clear_Squad rebuild). do_row reads `CLUB_NAME_BOX (236,200,90,19)` before use_club_card -> remember_player(.., "club");
BUY's `bought()` adds the picked card's name. BUY no longer does Right/Down/A on the results: `pick_card()` reads
`MARKET_NAME_BOX (90,312,290,30)` (wide: the left panel shifts ~65 px with/without the green "Market" label) and
`EXPIRED_BOX ("Expired", 278,517,60,18)`; expired or `in_squad(name)` -> next card along `PICK_PATH "RRRRDLLLLD"`,
else A (= Buy Now; the No/Yes dialog follows as before). `PICK_TRIES` 20 cards -> no_new -> reprice ("no new card in
the list"). `same_player`: _norm, 2+ trailing dots = truncated prefix (fuzzy), word subset ("Ampadu" = "Ethan Ampadu"),
fuzzy 0.85. Conservative: a common surname alone ("Smith") also matches "Emile Smith Rowe" -> that card is skipped.
Tested: names on the user's market screenshot ("YoganathaK") and saved shots; pick_card on a fake 2x5 grid; full BUY
simulation (scratch sim_buy.py / sim_pick.py). Club name box not tested on an image (no saved Club results shot).
Backup: Backup\Play-before-squad-names-*.py.
- Panel log: card names (`Card n: <name> -> buy / expired / already in the squad -> next`), `Club player: <name>`, `Squad players (...)` now go through log() (panel + report), not print.
- same_player: "rn" -> "m" on both sides (OCR reads m as rn: "Srnith" = "Smith").
- 2026-10-13: card_name = tight crop around the bright text (`_text_box`, gray > 170) + Tesseract first, Windows OCR
  fallback. Windows OCR on the wide box dropped first letters ("mith", "xaylor", "anilo"); on 118 real market shots the
  new read gave correct names (~107 ms). Backup: Backup\Play-before-name-ocr-*.py.
- Open (not fixed yet, reported to the user): POPUPS contains ("Expired", 278,517,60,18) = the card's Time Remaining
  label, not a popup -> back_to_squad presses A forever on the results page (D11 21:00). Reprice after "3 buys
  failed" pressed nothing when the frame was in transition (neither results nor no-cards) -> FindFilter failed on the
  results page. COINS_BOX width 143 reads "97"+coin icon as 974 (138 reads 97).
- 2026-10-13 21:3x FIXED: reprice waits up to 3 s for the results / no-cards page (Sorry / The bid -> A) before B / Y
  (D11 21:00 reproduced in sim_buy.py scenario 7: old code -> "قیمت تنظیم نشد", new -> reprice + buy).
  COINS_BOX width 143 -> 138 ("97" no longer read as 974). POPUPS "Expired" NOT changed yet (user unsure).
  Backup: Backup\Play-before-reprice-wait-coinbox-*.py.
- 2026-10-13 FIXED: handle_popups ignores the POPUPS "Expired" entry while on_results() (it is the card's Time Remaining
  label there); elsewhere it still counts as a popup. Tested on D11 1013_210034_002 (Expired seen, handle_popups False)
  and a simulated back_to_squad (B, B -> squad). Backup: Backup\Play-before-expired-popup-*.py.
- 2026-10-13: open_set presses A (up to 6x per turn) while `SBC_WELCOME ("Advance (4)", 25,675,100,34)` is seen
  ("Welcome to SBC" slides when entering the sets page). It matched all 8 saved "pause_open_set" shots (that screen was
  their cause) + 2 end-of-set screens. Backup: Backup\Play-before-sbc-welcome-*.py.
- 2026-10-13: `LETS_PLAY ("Let", 587,474,112,25)` = "A Let's Play!" on FC's start screen ("THE WORLD'S GAME") -> A in
  FindUltimate and MainUltimate. It matched 8 saved MainUltimate failure shots (C12, C13, C14, D31, incl. a pause) and
  one EA_two-factor shot (same screen, fading in). Backup: Backup\Play-before-lets-play-*.py.
- 2026-10-13: TurnOff (user's function) fixed: it never pressed A after Up, Up. Now: Xbox(3000) until POWER_MENU
  ("What", 81,151,491,49), Up, Up, A -> True. Called after the account loop only in accounts_mode (panel run) and
  only on a normal finish (not stop / abort / crash), `TURN_OFF_AT_END = True`; RemoteDown during it = console off.
  The Up, Up target is the user's choice (not verified on a screenshot). Backup: Backup\Play-before-turnoff-*.py.
- 2026-10-13: after TurnOff the remote reconnected and woke the console. Now TurnOff success (or RemoteDown during it)
  sets CLOSE_REMOTE; last log "Console off: closing the remote window"; after rep.end the bot calls close_my_remote():
  reads Controller\remotes\<REMOTE>.json, WM_CLOSE to its hwnd (like closing the window by hand), waits 10 s, else
  TerminateProcess + removes the json. Only print after that (log goes through this remote's pipe). Nothing in xbrp /
  Controller changed (user: do not touch the remote). Tested on a fake Tk window (closed by WM_CLOSE in 0.5 s) and a
  windowless process (terminated). Backup: Backup\Play-before-close-remote-*.py.
- 2026-10-14: `email_popup()` = EA "Is your email up to date?" (title text EMAIL_POPUP 400,150,480,50, fuzzy 0.85) ->
  Right (Update email -> Yes), A. In FindUltimate (after Let's Play) and MainUltimate. Only the C12 1010_213126
  MainUltimate shot matches (not the EA 2FA screens that also say "email"). Backup: Backup\Play-before-email-popup-*.py.

## Update 2026-10-14: server / connection loss -> recover and redo the challenge
All 13 saved disconnect messages ("There was a problem connecting to the Football Ultimate Team servers", "error
communicating ...", "You have lost your online connection ...") came in BUY / enter_slot; after Ok the game is on the
Ultimate home (then B -> "Are you sure you want to exit Football Ultimate Team?") or on the FC main menu; back_to_squad
then failed -> pause. Now:
- `wait()` is redefined after `class Abort`: xbox wait (`_xbox_wait`, kept on cell re-run) + `check_server()` at most
  every `SERVER_CHECK_EVERY` 1.5 s. Cheap prefilter `modal_button()` (>= 8 rows with 60 contiguous px > 215 in
  SERVER_BTN 520,370,240,170), then OCR of SERVER_BOX (220,200,840,220): SERVER_WORDS (server/connect/communicat/
  network/disconnect/session/offline/login/log in/sign in/...) AND SERVER_CTX (ultimate team/try again/main menu/ea /
  online/servers/fail/unable) -> log + shot "server_lost" + A + 2 s + `raise ServerLost`. EXIT_FUT dialog -> A (No) +
  ServerLost. On 1210 shots: 11 of 13 caught directly (2 = frames while the Ok button was fading in, caught by the next
  check live), 0 false positives.
- run_plan per set: ServerLost -> need_recover -> `recover_to_set(set, single)` (where_am_i: squad -> B; set -> done;
  hub -> open_set + wait_set_page; fut -> FindSBC; fc -> FindUltimate + MainUltimate; unknown -> B; 12 turns, then
  start_game + open_set) and the SAME challenge again from the start (bought players are in the Club now). A ServerLost
  inside the recovery counts too; > SERVER_RETRIES (4) in a row -> pause_fix("Server connection lost").
- start_game: ServerLost in a step = that try failed; the next try starts at FindUltimate if the game was already open.
- Ultimate entry screens (`entry_screens()` in FindUltimate + MainUltimate): "Press Any Button" (FC title, 15 saved
  MainUltimate failures), "WELCOME BACK ... A Start building my Squad" (3), Xbox game page "RESUME" (6) -> A;
  "Limit Reached" (FUT account creation limit on this console, 3) -> B + `AccountSkip` -> account loop: report
  "✗ اکانت رد شد", panel last error, next account. "Login Failed": not in any saved shot; covered by the login words.
- Tested: detection/entry on all 1210 shots, where_am_i on 6 real screens, run_plan recovery / wait hook /
  recover_to_set simulated (scratch sim_recover.py, test_server.py). Not run on a console yet.
Backups: Backup\Play-before-server-lost-*.py, Play-before-server-lost2-*.py.

## 2026-10-14: live market prices
`New Remote\Prices\sbc_prices.py` (run by F2 in the background) -> `Prices\sbc_prices.json` = cheapest console price
per CSV row (FUT.GG, ~6 min). Play.py: `tag_rows` (run_challenge) + `market_price(row)` (do_row, before the Market
filters) -> BUY(start, cap); cap = CSV + BUY_MAX_EXTRA; stale/missing -> CSV price; `USE_MARKET_PRICES` switch.
Backup: Backup\Play-before-market-prices-20261014-120409.py. Details: `Prices\CLAUDE.md`.
- 2026-10-14: FC offline after 'lost your online connection': top-right 'Press [View] to reconnect' (FC_RECONNECT 1040,40,240,35) -> entry_screens presses View + 5 s; where_am_i treats it as 'fc' (FindUltimate -> entry_screens). Detection of the message itself verified on the user's F31 screenshot; the reconnect text only on a brightened copy (it is dimmed under the dialog). Backup: Backup\Play-before-reconnect-*.py.
- 2026-10-14 FIX after F31/F32 restarted challenges for nothing:
  1) REMOVED the EXIT_FUT check ("want to exit", fuzzy) — it matched the buy dialog "Do you want to get this item ..."
     -> A + ServerLost -> challenge rebuilt (F32 8x, F31 5x). Not asked by the user.
  2) server_text now needs an Ok-sized button: `ok_button_width()` (OK_AREA 400,370,480,170; width of the solid button
     rows) must be 60..120 px (real Ok buttons 71-80) and the text must not contain "is connecting". The normal
     "<gamertag> is connecting to the EA Servers..." screen has "Cancel and Play Offline" (220 px): the bot pressed A
     there and put FC offline (F31 4x). Re-tested on 1222 shots: 11 real messages, 0 false; F31 connecting shots ignored.
  Backup: Backup\Play-before-remove-exitfut-*.py.
- 2026-10-14 (2):
  * check_server: "You are not connected to the EA Servers" -> `EA_RECONNECT ("connect to EA", 500,365,280,70)` -> A
    (Re-connect), 5 s, ServerLost. Matches the user's F31/D13 screenshots and 2 saved D13 MainUltimate shots only.
  * handle_popups: "The controller needs to be paired to a profile" (PAIR_PROFILE 300,290,680,70) -> A (Ok).
  * back_to_squad no longer spams B off the squad: exact `EXIT_FUT_DIALOG ("exit Football Ultimate", 280,250,720,110,
    fuzzy 0.95, only here)` -> A (No) + ServerLost; where_am_i in fut/hub/set/fc -> ServerLost (run_plan recovers).
    ~47 saved back_to_squad pauses ended on that exit dialog. recover_to_set: on the Store first B (RB there only
    changes Store tabs).
  * TurnOff: no wait after the final A; the main block logs once BEFORE TurnOff and calls close_my_remote() right after
    it (no pipe traffic after the power-off: remotectl's auto-reconnect woke the console, F31 off/on every 3-6 min).
  Backup: Backup\Play-before-dc2-*.py.
- 2026-10-14 19:2x: `check_advance()` in `wait()` (before check_server, at most every 1 s): bottom-left
  `ADVANCE_BOX (20,660,240,58)` contains "Advance" (fuzzy .85) -> A, up to 8x until gone. Covers the first-time tips
  (MULTI SWAP in Club, Transfer, challenges, SBC sets: "A Advance"), Welcome to SBC and "... COMPLETED" end-of-set.
  User asked: "if Advance is read bottom-left, press A". On 400 random saved shots: 5 hits, all such screens, no false
  hit (squad / market / club / Multi-Swap). Running bots get it on their next run. Backup: Backup\before-advance-*.py.
- 2026-10-14 20:1x: BUY reprice: on the RESULTS page (e.g. "no new card in the list" = all 20 cards duplicates /
  expired) the bot pressed B, which in the challenge's Transfer Market tab leaves to the SQUAD (D13 20:04, user's
  screenshot), so Pricing failed. Now Y (= "Y Search" -> filters) on both the results and the no-cards page.
  Backup: Backup\before-reprice-Y-*.py.
- 2026-10-14 20:3x: EA authenticator: `_ea_wrong` counts rejected codes across enter_ea_code calls (ea_two_factor is
  called again and again from FindUltimate, so 3-per-call was unlimited); accepted -> 0. `EA_CODE_MAX_WRONG` 3 ->
  shot "EA_code_wrong", counter reset, `raise EACodeFailed` (subclass of AccountSkip) -> the account loop's
  AccountSkip handler: report "✗ اکانت رد شد", panel last error, NEXT account (user changed his mind: skip, not stop).
  Simulated. Backups: Backup/before-ea-3wrong-*.py, before-ea-skip-*.py.
- 2026-10-14 20:5x: switch_account: RT does NOT scroll the "Who are you?" list (B25: same 17 OCR lines after RT ->
  "DONNA is not added on this console" although the console has up to 32 accounts). Now each page = Down x
  `WHO_PAGE_DOWNS` (10); end = "Add new"/"Add guest" seen or names unchanged after the Downs; max_pages 12 (~120 rows).
  Simulated on a fake 32-name list (8 visible): User05 / User30 found, missing name -> False at the end. Not yet
  verified on a console (B25 was being used by hand). Backup: Backup/before-who-scroll-*.py.
- 2026-10-14 21:0x: Pricing big jumps with RB (user): `price_rbs(price)` = 0 below 600, 1 for 600-1200, 2 for
  1200-2200, +1 per 1000 (ceil((price-200)/1000)). RB pressed before the Right/Left loop, number read before each RB
  (stop when >= price) and printed after it; then the old read-every-press Right/Left loop. User's example: 900 = RB +
  3 Right (=> first RB lands on 750). Simulated with RB = 750, 1700, 2700, ...: 900 -> 4 presses (old 16), 2200 -> 7
  (old 30), 5000 -> 8 (old 58). Exact RB landing values not verified on a console. Backup: Backup/before-price-rb-*.py.
- 2026-10-14 22:4x: (1) The "back to Club instead of reprice" the user saw = 59 logged cases of "Card 20 ... -> no new
  card -> FindFilter: به Pricing نرسید -> قیمت تنظیم نشد" = the reprice B bug fixed at 20:1x (Y now); BUY False ->
  run_row retry from enter_slot/Club. (2) pick_card ends early at the list end: `_grid()` = gray MARKET_GRID
  (380,95,850,480), `_same` mean abs diff < GRID_SAME 2.0 after a move = the selection frame did not move. Names are
  NOT compared (a list is often 10x the same player). Down from row 2 on scrolls the list with the frame fixed (identical
  cards look the same) -> not checked (`downs` counter). Down from row 1 that does not move (short row 2) -> Left+Down
  up to 4x before "end". Simulated lists 1-25: no card skipped; early end for 1-5, 13; others run 20 like before.
  (3) switch_account: "Show more" in the Who are you? list (A81 shot) -> focus it + A once (`expanded`), before the
  "Add new" end check. Simulated 6 + Show more -> 32. Backup: Backup/before-list-end-showmore-*.py.
