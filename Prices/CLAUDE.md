# CLAUDE.md - Prices (SBC card prices) - read this first

## خلاصه برای کاربر (فارسی)
- `sbc_prices.py` برای هر ردیف CSV هر SBC فعال پنل، ارزان‌ترین قیمت کارت‌های مطابق فیلتر را در مارکت کنسول پیدا می‌کند.
- اجرا: `python sbc_prices.py` یک بار. `python sbc_prices.py --loop` همیشه به‌روز. FUT.GG حدود هر ۶ دقیقه قیمت تازه می‌دهد.
- خروجی: `sbc_prices.csv` برای دیدن، `sbc_prices.json` برای ربات.
- پنل F2 این ابزار را خودش در پس‌زمینه اجرا می‌کند. تب Prices پنل همین جدول را نشان می‌دهد و با هر قیمت تازه به‌روز می‌شود.
- تب Players پنل: همه کارت‌های بازی (حدود ۲۰ هزار) با مشخصات و قیمت لحظه‌ای کنسول، با جستجو و فیلتر و مرتب‌سازی؛ با هر قیمت تازه خودش به‌روز می‌شود.
- ربات قبل از هر خرید از مارکت قیمت شروع را از این فایل می‌خواند؛ قدیمی‌تر از ۲۰ دقیقه → قیمت CSV.

---
Agent notes (reply to the user in Persian; tool output is English).

## Source (found 2026-10-14)
FUT.GG publishes static JSON on `https://r2.fut.gg/27/` (no Cloudflare challenge; `www.fut.gg/api/fut/player-prices/*`
IS behind a challenge - do not try to bypass it). `manifest.json` gives a hash per file; file URL = `<key>.v1.<hash>.json`.
- `player-prices-index`: `id0` + deltas `d` -> eaId of card i. `player-prices-ps5-dyn` (console, PS+Xbox shared market):
  `p[i]` price (0 = none/extinct), `s[i]` status (0 market, 1 SBC, 2 objective, 4 token). `-pc-dyn` for PC.
- `streamlined-pool`: `o` overall, `r` rarity eaId (0 = base common+rare), `pos` EA position id (primary only),
  `nat`, `lg`, `cl`. Its `e` flag is NOT platform availability (it is 0 for almost all bronzes) - not used.
- `fc-core-data`: names of nations/leagues/clubs/rarities. Card names: `www.fut.gg/api/fut/players/v2/27/?ids=..`
  (open API), cached in `cache/names.json`.
- Alignment check (same as the site): len(p) == len(d)+1 == pool.n, pool.id0 == id0, pool.idn == id0+sum(d).
- Prices republished about every 6 min (`_published_at` in manifest). The loop polls the manifest every 60 s.

## Matching rules
Bronze/Silver/Gold = overall 0-64 / 65-74 / 75+ and base rarity only. Other rarities by name. Names: exact ->
part of the name -> fuzzy 0.8, plus `ALIASES` (e.g. Cote d'Ivoire -> Ivory Coast). Club with the same name:
the row's league first, men's club before women's. Rows read like Play.load_plan/load_rows (sbcs.json read only).

## Wiring (2026-10-14 12:10)
- Panel: `panel.PriceService` starts `python -u sbc_prices.py --loop --quiet` (no window, log `Prices/prices.log`,
  reset at 1 MB), restarts it 30 s after an exit, stops it on F2 close. Exit code 3 = another loop holds
  `cache/loop.lock` (msvcrt) -> retry in 5 min. Header label: green <=10 min, orange <=20, red older; tooltip details.
- Play.py: `tag_rows(e, rows)` in run_challenge stores `_csv_price/_set/_challenge/_row`; `market_price(row)` in
  do_row right before the Market SetFilters: start = min(valid_price(cheapest), cap), cap = CSV + BUY_MAX_EXTRA,
  falls back to the CSV price when the file is missing/older than `PRICE_MAX_AGE` (20 min)/row filter changed/no card.
  `BUY(price, cap)` reprices up to cap. `USE_MARKET_PRICES = False` = old behaviour. Log line: "Price N (why; CSV, cap)".
- Panel tab `PricesTab` (2026-10-14 15:35): same columns as sbc_prices.csv, rebuilt when `PriceService.version`
  changes (new json read by the 5 s tick). Header 'Prices' button switches to it. Backup: Pannel/Backup/panel-before-prices-tab-20261014-153454.py.
- Countdown (2026-10-14 15:40): the loop writes `Prices/loop_status.json` after every check (checked, next_check,
  published, interval = median gap of the last 8 publish times, default 360 s, next_publish). PricesTab.tick_timer
  (1 s, only while visible) shows 'Next refresh in m:ss', 'any moment now' when overdue, red when the loop is silent
  for > 3 polls. Backup: Pannel/Backup/panel-before-prices-timer-20261014-153707.py.
- Writer retries os.replace (Windows refuses while a bot or Excel has the file open).
- Tests: scratch test_price.py (7 market_price cases), sim_buy2.py (old BUY scenarios + cap 8/9), test_service.py
  (start / second instance exit 3 / restart / stop). Not yet run on the console.

- Players tab (2026-10-15): the loop also writes `all_players.json` (every card: cols list + rows; `price`, `prev` =
  price at the previous publish, status, names of nation/league/club/rarity, 6 face stats, wf/sm/foot/age/height/url)
  after each SBC save. Details come from `players/v2/27/?ids=` (200 per call, DETAIL_CALLS per poll); cards that call
  leaves out (~460 special cards) via `player-item-definitions/27/<id>/` (other field layout, `detail_def`),
  DETAIL_SINGLE per poll. Cached in `cache/players.json`. Panel `PlayersTab` (QTableView + PlayersModel, filter/sort in
  Python) reloads when the file mtime changes. `PriceCountdown` is shared by Prices and Players tabs.
  Backups: Pannel/Backup/panel-before-players-tab-20261015-121630.py, sbc_prices-before-players-20261015-121630.py.

## Limits
- Position filter uses primary position only; the in-game filter may also list alternative positions.
- FUT.GG prices lag a few minutes; the BUY reprice covers that.
