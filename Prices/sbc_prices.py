"""SBC card prices - cheapest console market price for every player row of the panel's SBCs.

Source: the public data files FUT.GG publishes on r2.fut.gg (the same files its own site loads):
  manifest.json                     -> current version hash of each file (re-checked every minute)
  player-prices-index.v1.<h>.json   -> card ids (id0 + running sum of d)
  player-prices-ps5-dyn.v1.<h>.json -> price p[i] and status s[i] of card i (console = PS + Xbox market)
  streamlined-pool.v1.<h>.json      -> overall o, rarity r, position pos, nation nat, league lg, club cl
  fc-core-data.v1.<h>.json          -> names of nations / leagues / clubs / rarities
Only files whose hash changed are downloaded again (cache folder). FUT.GG refreshes prices every few minutes.

Rows come from Pannel/data/sbcs.json (enabled entries) + their CSV (same lookup as Play.load_rows).
Row filter columns: Rarity, Region, Pos, Club, League ("OFF" = not set). Price column = current manual price.

Usage:
  python sbc_prices.py            one update, prints the table, writes sbc_prices.json / sbc_prices.csv
  python sbc_prices.py --loop     keep updating (checks the manifest every 60 s, recomputes when prices change)
  python sbc_prices.py --pc       PC market instead of console
"""
import argparse
import csv
import datetime
import difflib
import glob
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                  # ...\New Remote
SBCS_FILE = os.path.join(ROOT, "Pannel", "data", "sbcs.json")  # read only
CSV_DIR = ROOT
CACHE = os.path.join(HERE, "cache")
OUT_JSON = os.path.join(HERE, "sbc_prices.json")
OUT_CSV = os.path.join(HERE, "sbc_prices.csv")
NAMES_FILE = os.path.join(CACHE, "names.json")
STATUS_FILE = os.path.join(HERE, "loop_status.json")   # written after every check (panel countdown)
PLAYERS_FILE = os.path.join(CACHE, "players.json")     # eaId -> card details from the FUT.GG player API
OUT_PLAYERS = os.path.join(HERE, "all_players.json")    # every card + live price (panel Players tab)

GAME = "27"
CDN = "https://r2.fut.gg"
API = "https://www.fut.gg/api/fut"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"
POLL = 60          # seconds between manifest checks in --loop (the site itself checks every 60 s)
TOP = 5            # cheapest cards kept per row
DETAIL_BATCH = 200  # cards per player-API call (details for the Players tab)
DETAIL_CALLS = 25   # API calls per loop poll while details are missing (~35 s; all cards in a few polls)
DETAIL_SINGLE = 100  # one-card calls per poll for cards the list call leaves out (~0.4 s each)

POS = {"GK": 0, "RWB": 2, "RB": 3, "CB": 5, "LB": 7, "LWB": 8, "CDM": 10, "RM": 12, "CM": 14,
       "LM": 16, "CAM": 18, "CF": 21, "RW": 23, "ST": 25, "LW": 27}
QUALITY = {"bronze": (0, 64), "silver": (65, 74), "gold": (75, 99)}
POS_NAME = {v: k for k, v in POS.items()}
STATUS_NAME = {0: "Market", 1: "SBC", 2: "Objective", 3: "Other", 4: "Token"}
BASE_RARITY = 0    # FUT.GG rarity 0 = base card (common + rare); Bronze/Silver/Gold rows use only base cards
TRADEABLE = 0      # status s[i]: 0 = market card, 1 = SBC, 2 = objective, 4 = token
ALIASES = {        # names typed in the CSV / shown in game -> FUT.GG name (keys and values normalized)
    "cote divoire": "ivory coast", "cote divorie": "ivory coast", "cote d ivoire": "ivory coast",
    "turkiye": "turkey", "usa": "united states", "holland": "netherlands", "korea": "korea republic",
}


# ---------------------------------------------------------------- download + cache
def fetch(url, tries=3):
    err = None
    for t in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except Exception as e:      # noqa: BLE001 - network errors of any kind -> retry
            err = e
            time.sleep(2 + 3 * t)
    raise RuntimeError(f"download failed: {url}: {err}")


def manifest():
    return json.loads(fetch(f"{CDN}/{GAME}/manifest.json?t={int(time.time())}"))


def blob(key, man):
    """File `key` in the version the manifest names; from the cache if already downloaded."""
    h = man[key]
    path = os.path.join(CACHE, f"{key}.v1.{h}.json")
    if not os.path.exists(path):
        data = fetch(f"{CDN}/{GAME}/{key}.v1.{h}.json")
        os.makedirs(CACHE, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        for old in glob.glob(os.path.join(CACHE, f"{key}.v1.*.json")):   # keep only the newest version
            if old != path:
                try:
                    os.remove(old)
                except OSError:
                    pass
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- card data
class Market:
    """All cards of the game with price, aligned by index (same check as FUT.GG's own code)."""

    def __init__(self, man, pc=False):
        key = "player-prices-pc-dyn" if pc else "player-prices-ps5-dyn"
        idx, pr, pool = blob("player-prices-index", man), blob(key, man), blob("streamlined-pool", man)
        self.core = blob("fc-core-data", man)
        n = len(pr["p"])
        if n != len(idx["d"]) + 1 or pool["n"] != n or pool["id0"] != idx["id0"] or \
                pool["idn"] != idx["id0"] + sum(idx["d"]):
            raise RuntimeError("price / pool files do not match (FUT.GG is publishing) - try again")
        ids, a = [], idx["id0"]
        for i in range(n):
            if i:
                a += idx["d"][i - 1]
            ids.append(a)
        self.ids, self.p, self.s = ids, pr["p"], pr["s"]
        self.o, self.r, self.pos = pool["o"], pool["r"], pool["pos"]
        self.nat, self.lg, self.cl = pool["nat"], pool["lg"], pool["cl"]
        # pool["e"] is not used: it is FUT.GG's solver flag and leaves out almost every bronze card
        self.version = man[key]
        self.published = man.get("_published_at", {}).get(key)
        self.n = n

    def find(self, f):
        """Market cards that match filter f, cheapest first: [(price, index)]."""
        out = []
        q, rar, pos = f.get("quality"), f.get("rarity"), f.get("pos")
        nat, lg, cl = f.get("nation"), f.get("league"), f.get("club")
        for i in range(self.n):
            p = self.p[i]
            if p <= 0 or self.s[i] != TRADEABLE:
                continue
            if q and not (q[0] <= self.o[i] <= q[1] and self.r[i] == BASE_RARITY):
                continue
            if rar is not None and self.r[i] != rar:
                continue
            if pos is not None and self.pos[i] != pos:
                continue
            if nat is not None and self.nat[i] != nat:
                continue
            if lg is not None and self.lg[i] != lg:
                continue
            if cl is not None and self.cl[i] != cl:
                continue
            out.append((p, i))
        out.sort()
        return out


# ---------------------------------------------------------------- names
def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def off(v):
    return not str(v or "").strip() or str(v).strip().upper() == "OFF"


def match(name, items):
    """items = [(eaId, name, extra)]. exact -> part of the name -> fuzzy 0.8 (like the bot's pickers).
    Returns the matching items, best first."""
    k = norm(name)
    k = ALIASES.get(k, k)
    exact = [it for it in items if norm(it[1]) == k]
    if exact:
        return exact
    part = [it for it in items if k and len(norm(it[1])) > 2 and (k in norm(it[1]) or norm(it[1]) in k)]
    if part:
        return sorted(part, key=lambda it: abs(len(norm(it[1])) - len(k)))
    names = {norm(it[1]): it for it in items}
    close = difflib.get_close_matches(k, list(names), n=3, cutoff=0.8)
    return [names[c] for c in close]


class Names:
    def __init__(self, core):
        self.nations = [(int(x["eaId"]), x["name"], None) for x in core["nations"]]
        self.leagues = [(int(x["eaId"]), x["name"], None) for x in core["leagues"]]
        self.clubs = [(int(x["eaId"]), x["name"], (int(x.get("leagueEaId") or 0), bool(x.get("isWomen"))))
                      for x in core["clubs"]]
        self.rarities = [(int(x["eaId"]), x["name"], None) for x in core["rarities"]]
        self.rarities += [(0, "Common", None)]              # base cards: FUT.GG keeps common + rare as 0
        self.by_id = {"nation": {i: n for i, n, _ in self.nations}, "league": {i: n for i, n, _ in self.leagues},
                      "club": {i: n for i, n, _ in self.clubs}, "rarity": {i: n for i, n, _ in self.rarities}}

    def row_filter(self, row):
        """CSV row -> (filter dict, list of problems)."""
        f, bad = {}, []
        rar = str(row.get("Rarity") or "").strip()
        if not off(rar):
            if norm(rar) in QUALITY:
                f["quality"] = QUALITY[norm(rar)]
            else:
                m = match(rar, self.rarities)
                if m:
                    f["rarity"] = m[0][0]
                else:
                    bad.append(f"Rarity '{rar}' unknown")
        pos = str(row.get("Pos") or "").strip().upper()
        if not off(pos):
            if pos in POS:
                f["pos"] = POS[pos]
            else:
                bad.append(f"Pos '{pos}' unknown")
        for col, key, items in (("Region", "nation", self.nations), ("League", "league", self.leagues)):
            v = row.get(col)
            if not off(v):
                m = match(v, items)
                if m:
                    f[key] = m[0][0]
                else:
                    bad.append(f"{col} '{v}' unknown")
        v = row.get("Club")
        if not off(v):
            m = match(v, self.clubs)
            if "league" in f:                                   # same name in two leagues -> the row's league
                m = [c for c in m if c[2][0] == f["league"]] or m
            m = sorted(m, key=lambda c: c[2][1])                # men's club before women's club
            if m:
                f["club"] = m[0][0]
            else:
                bad.append(f"Club '{v}' unknown")
        return f, bad

    def describe(self, f):
        parts = []
        if "quality" in f:
            parts.append(next(k for k, v in QUALITY.items() if v == f["quality"]).title())
        for key in ("rarity", "nation", "league", "club"):
            if key in f:
                parts.append(self.by_id[key].get(f[key], str(f[key])))
        if "pos" in f:
            parts.append(next(k for k, v in POS.items() if v == f["pos"]))
        return " | ".join(parts) or "any"


def player_names(ids):
    """eaId -> card name (FUT.GG player list API, cached in cache/names.json)."""
    try:
        with open(NAMES_FILE, encoding="utf-8") as fh:
            names = json.load(fh)
    except (OSError, ValueError):
        names = {}
    need = [i for i in dict.fromkeys(ids) if str(i) not in names]
    for k in range(0, len(need), 30):
        part = need[k:k + 30]
        try:
            d = json.loads(fetch(f"{API}/players/v2/{GAME}/?ids={','.join(map(str, part))}&count={len(part)}"))
            for x in d.get("data", []):
                names[str(x["eaId"])] = x.get("commonName") or x.get("cardName") or x.get("lastName") or ""
        except Exception as e:      # noqa: BLE001 - names are optional
            print("player names not loaded:", e)
            break
    if need:
        os.makedirs(CACHE, exist_ok=True)
        with open(NAMES_FILE, "w", encoding="utf-8") as fh:
            json.dump(names, fh, ensure_ascii=False)
    return {int(k): v for k, v in names.items()}


# ---------------------------------------------------------------- all players (panel Players tab)
PLAYER_COLS = ["eaId", "name", "ovr", "pos", "alt", "rarity", "rarity_id", "nation", "league", "club",
               "price", "prev", "status", "s1", "s2", "s3", "s4", "s5", "s6", "wf", "sm", "foot", "age",
               "height", "url"]
_no_details = set()     # ids the list API did not return -> asked one by one (player-item-definitions)
_dead = set()           # not found one by one either (asked again after a restart)


def load_details():
    try:
        with open(PLAYERS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def detail_row(x):
    fs = x.get("faceStatsV2") or {}
    keys = (("gkFaceDiving", "gkFaceHandling", "gkFaceKicking", "gkFaceReflexes", "gkFaceSpeed",
             "gkFacePositioning") if x.get("position") == "GK" else
            ("facePace", "faceShooting", "facePassing", "faceDribbling", "faceDefending", "facePhysicality"))
    return {"name": x.get("commonName") or x.get("cardName") or x.get("lastName") or "",
            "alt": ",".join(x.get("alternativePositions") or []), "rarity": x.get("rarityName") or "",
            "stats": [fs.get(k) or 0 for k in keys], "wf": x.get("weakFoot") or 0, "sm": x.get("skillMoves") or 0,
            "foot": x.get("foot") or "", "age": x.get("age") or 0, "height": x.get("height") or 0,
            "url": x.get("url") or ""}


def detail_def(x):
    """Same as detail_row, for the one-card endpoint (player-item-definitions; other field layout)."""
    keys = (("gkFaceDiving", "gkFaceHandling", "gkFaceKicking", "gkFaceReflexes", "gkFaceSpeed",
             "gkFacePositioning") if x.get("position") == POS["GK"] else
            ("facePace", "faceShooting", "facePassing", "faceDribbling", "faceDefending", "facePhysicality"))
    rar = x.get("rarity")
    age, b = 0, x.get("birthDate")
    if b:
        t = datetime.date.today()
        y, md = divmod(int(b), 10000)
        age = t.year - y - (md > t.month * 100 + t.day)
    return {"name": x.get("commonName") or x.get("lastName") or "",
            "alt": ",".join(POS_NAME.get(q, str(q)) for q in x.get("alternativePositionIds") or []),
            "rarity": rar.get("name", "") if isinstance(rar, dict) else "",
            "stats": [x.get(k) or 0 for k in keys], "wf": x.get("weakFoot") or 0, "sm": x.get("skillMoves") or 0,
            "foot": {1: "Right", 2: "Left"}.get(x.get("foot"), ""), "age": age, "height": x.get("height") or 0,
            "url": x.get("url") or ""}


def fill_details(market, details, calls=DETAIL_CALLS):
    """Download details of cards missing from cache/players.json, market cards first, at most `calls`
    API calls. Returns how many cards were added."""
    order = sorted(range(market.n), key=lambda i: (market.s[i] != TRADEABLE or market.p[i] <= 0, -market.o[i]))
    need = [market.ids[i] for i in order
            if str(market.ids[i]) not in details and market.ids[i] not in _no_details]
    added = 0
    for k in range(0, min(len(need), calls * DETAIL_BATCH), DETAIL_BATCH):
        part = need[k:k + DETAIL_BATCH]
        try:
            d = json.loads(fetch(f"{API}/players/v2/{GAME}/?ids={','.join(map(str, part))}&count={len(part)}"))
        except Exception as e:      # noqa: BLE001 - details are optional, try again next poll
            print("player details not loaded:", e)
            break
        got = set()
        for x in d.get("data", []):
            got.add(x["eaId"])
            details[str(x["eaId"])] = detail_row(x)
            added += 1
        _no_details.update(i for i in part if i not in got)
    single = [i for i in need if i in _no_details and i not in _dead][:DETAIL_SINGLE]
    for i in single:
        try:
            x = json.loads(fetch(f"{API}/player-item-definitions/{GAME}/{i}/", tries=1)).get("data")
        except Exception:           # noqa: BLE001 - 404 = unknown card
            x = None
        if x:
            details[str(i)] = detail_def(x)
            added += 1
        else:
            _dead.add(i)
    if added:
        tmp = PLAYERS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(details, f, ensure_ascii=False, separators=(",", ":"))
        replace(tmp, PLAYERS_FILE)
    return added


def previous_prices(version):
    """eaId -> price before the current FUT.GG publish (from the all_players.json we wrote last)."""
    try:
        with open(OUT_PLAYERS, encoding="utf-8") as f:
            old = json.load(f)
        c = {k: n for n, k in enumerate(old["cols"])}
        same = old.get("version") == version
        return {r[c["eaId"]]: r[c["prev"] if same else c["price"]] for r in old["rows"]}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def write_players(market, details):
    core = market.core
    nat = {int(x["eaId"]): x["name"] for x in core["nations"]}
    lg = {int(x["eaId"]): x["name"] for x in core["leagues"]}
    cl = {int(x["eaId"]): x["name"] for x in core["clubs"]}
    rar = {int(x["eaId"]): x["name"] for x in core["rarities"]}
    rar[BASE_RARITY] = "Common/Rare"
    prev = previous_prices(market.version)
    rows = []
    for i in range(market.n):
        e, p = market.ids[i], market.p[i]
        d = details.get(str(e)) or {}
        st = d.get("stats") or [0] * 6
        rows.append([e, d.get("name", ""), market.o[i], POS_NAME.get(market.pos[i], str(market.pos[i])),
                     d.get("alt", ""), d.get("rarity") or rar.get(market.r[i], str(market.r[i])), market.r[i],
                     nat.get(market.nat[i], ""), lg.get(market.lg[i], ""), cl.get(market.cl[i], ""),
                     p, prev.get(e, p), STATUS_NAME.get(market.s[i], str(market.s[i])), *st,
                     d.get("wf", 0), d.get("sm", 0), d.get("foot", ""), d.get("age", 0), d.get("height", 0),
                     d.get("url", "")])
    pub = (datetime.datetime.fromtimestamp(market.published).isoformat(timespec="seconds")
           if market.published else None)
    doc = {"updated": datetime.datetime.now().isoformat(timespec="seconds"), "prices_published": pub,
           "version": market.version, "cols": PLAYER_COLS, "rows": rows}
    tmp = OUT_PLAYERS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    replace(tmp, OUT_PLAYERS)


# ---------------------------------------------------------------- SBC rows (same as Play.load_plan / load_rows)
def load_entries():
    try:
        with open(SBCS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print("SBC list of the panel not read:", e)
        return []
    out = []
    for r in data:
        if isinstance(r, str):
            r = {"set": r}
        st = str(r.get("set") or r.get("name") or "").strip()
        if st and r.get("enabled", True):
            out.append({"set": st, "challenge": str(r.get("challenge") or "").strip(),
                        "csv": str(r.get("csv") or "").strip()})
    return out


def load_rows(e):
    cands = [e["csv"]] if e.get("csv") else []
    cands += [os.path.join(CSV_DIR, f"{e['set']}{e.get('challenge', '')}.csv"),
              os.path.join(CSV_DIR, f"{e['set']}.csv")]
    for path in cands:
        if path and os.path.exists(path):
            with open(path, newline="", encoding="utf-8-sig") as f:
                return path, list(csv.DictReader(f))
    return None, []


def sbc_files_stamp():
    """Changes when sbcs.json or one of its CSV files is edited -> recompute without waiting for new prices."""
    files = [SBCS_FILE] + [load_rows(e)[0] or "" for e in load_entries()]
    return tuple((p, os.path.getmtime(p)) for p in files if p and os.path.exists(p))


# ---------------------------------------------------------------- one update
def update(market):
    names = Names(market.core)
    results, ids = [], []
    for e in load_entries():
        path, rows = load_rows(e)
        sbc = f"{e['set']} {e['challenge']}".strip()
        if not rows:
            print(f"{sbc}: no CSV found")
            continue
        for n, row in enumerate(rows, 1):
            f, bad = names.row_filter(row)
            cards = market.find(f) if not bad else []
            top = cards[:TOP]
            ids += [market.ids[i] for _, i in top]
            try:
                csv_price = int(str(row.get("Price") or "0").strip())
            except ValueError:
                csv_price = None
            results.append({
                "sbc": sbc, "set": e["set"], "challenge": e["challenge"], "csv": path, "row": n,
                "filter": {k: row.get(k) for k in ("Rarity", "Region", "Pos", "Club", "League")},
                "matched": names.describe(f), "problems": bad,
                "csv_price": csv_price, "cheapest": top[0][0] if top else None, "count": len(cards),
                "cards": [{"eaId": market.ids[i], "price": p, "overall": market.o[i]} for p, i in top],
            })
    pn = player_names(ids)
    for r in results:
        for c in r["cards"]:
            c["name"] = pn.get(c["eaId"], "")
    return results


def replace(tmp, path):
    """os.replace with retries: on Windows it fails while a bot is reading the file (or Excel has the CSV open)."""
    for t in range(25):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.2)
    os.remove(tmp)
    print(f"{os.path.basename(path)} is locked (open in another program?) - not updated this time")


def single_instance():
    """Only one --loop at a time (the panel starts one; a second panel or a manual run must not double it).
    Returns the open lock file (keep it) or None when another loop holds the lock."""
    import msvcrt
    os.makedirs(CACHE, exist_ok=True)
    f = open(os.path.join(CACHE, "loop.lock"), "a+")
    try:
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        return f
    except OSError:
        f.close()
        return None


def save(results, market, pc):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    pub = datetime.datetime.fromtimestamp(market.published).isoformat(timespec="seconds") if market.published else None
    doc = {"updated": now, "prices_published": pub, "platform": "pc" if pc else "console",
           "source": "fut.gg", "rows": results}
    tmp = OUT_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    replace(tmp, OUT_JSON)
    tmp = OUT_CSV + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["SBC", "Row", "Rarity", "Region", "Pos", "Club", "League", "CSV Price", "Cheapest",
                    "Cards", "Cheapest cards", "Problems"])
        for r in results:
            fl = r["filter"]
            w.writerow([r["sbc"], r["row"], fl["Rarity"], fl["Region"], fl["Pos"], fl["Club"], fl["League"],
                        r["csv_price"], r["cheapest"], r["count"],
                        "; ".join(f"{c['name']} {c['overall']} {c['price']}" for c in r["cards"]),
                        "; ".join(r["problems"])])
    replace(tmp, OUT_CSV)
    return now, pub


def show(results, now, pub):
    print(f"\nUpdated {now}  (FUT.GG prices published {pub})")
    last = None
    for r in results:
        if r["sbc"] != last:
            print(f"\n== {r['sbc']}")
            last = r["sbc"]
        if r["problems"]:
            print(f"  {r['row']:>2}. {r['matched']:<45} !! {'; '.join(r['problems'])}")
            continue
        best = r["cards"][0] if r["cards"] else None
        who = f"{best['name']} {best['overall']}" if best else "no card on the market"
        print(f"  {r['row']:>2}. {r['matched']:<45} csv {str(r['csv_price']):>6}  cheapest "
              f"{str(r['cheapest']):>7}  ({r['count']} cards, {who})")


def write_status(man, key, error=None):
    """loop_status.json for the panel timer: when we checked, when we check next, when FUT.GG published and
    about how often it publishes (median gap of the last publish times we saw, default 6 min)."""
    now = time.time()
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            hist = json.load(f).get("history", [])
    except (OSError, ValueError):
        hist = []
    pub = (man or {}).get("_published_at", {}).get(key)
    if pub and pub not in hist:
        hist = (hist + [pub])[-8:]
    gaps = sorted(b - a for a, b in zip(hist, hist[1:]) if 120 <= b - a <= 1800)
    interval = gaps[len(gaps) // 2] if gaps else 360
    doc = {"checked": now, "next_check": now + POLL, "poll": POLL, "published": pub,
           "interval": interval, "next_publish": (pub + interval) if pub else None,
           "error": error, "history": hist}
    tmp = STATUS_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        replace(tmp, STATUS_FILE)
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--loop", action="store_true", help="keep updating")
    ap.add_argument("--pc", action="store_true", help="PC market prices instead of console")
    ap.add_argument("--quiet", action="store_true", help="no table, one line per update")
    a = ap.parse_args()
    key = "player-prices-pc-dyn" if a.pc else "player-prices-ps5-dyn"
    lock = single_instance() if a.loop else True
    if not lock:
        print("another price loop is already running - exit")
        return 3
    seen, market, details = None, None, load_details()
    while True:
        man, err = None, None
        try:
            man = manifest()
            stamp = (man.get(key), man.get("streamlined-pool"), man.get("fc-core-data"), sbc_files_stamp())
            if stamp != seen:
                market = Market(man, a.pc)
                results = update(market)
                now, pub = save(results, market, a.pc)
                seen = stamp
                if a.quiet:
                    print(f"{now}: {len(results)} rows updated (prices published {pub})")
                else:
                    show(results, now, pub)
                write_players(market, details)
            if market is not None:
                added = fill_details(market, details)
                if added:
                    write_players(market, details)
                    print(f"{datetime.datetime.now():%H:%M:%S}: details of {added} more cards "
                          f"({len(details)} of {market.n})")
        except Exception as e:      # noqa: BLE001 - keep the loop alive, try again next poll
            err = str(e)
            print(f"{datetime.datetime.now():%H:%M:%S} update failed: {e}")
            if not a.loop:
                return 1
        if a.loop:
            write_status(man, key, err)
        if not a.loop:
            return 0
        time.sleep(POLL)


if __name__ == "__main__":
    sys.exit(main())
