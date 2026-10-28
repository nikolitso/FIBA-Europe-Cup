"""Update the live site's results and bookmaker odds from BetExplorer.

    python update_site.py            # results + odds
    python update_site.py results    # results only
    python update_site.py odds       # odds only

Results: every 2026-27 game on BetExplorer's results pages replaces the 2026-27 rows in the site's data.js.
Odds:    for the next round on the fixtures page, the handicap (AH), total (O/U) and money line (H/A) are
         written to odds.js. Bookmaker order: Stake.com, then bwin, then Betsson (the first one that offers the
         market for that match); if none of them does, the average of the other bookmakers. Where a bookmaker
         lists several lines, the one whose two odds are closest to each other is used.
The script stops without writing anything if BetExplorer blocks the request (it is unavailable in some countries).
After running, copy the files to the site repo's folder as usual and push (the default SITE path is the local checkout).
"""
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

import scrape

SITE = Path(os.environ.get("FIBA_SITE", r"C:\Users\antonis\Desktop\nikolitso.github.io\fibaeuropecup"))   # FIBA_SITE: set by the GitHub job
BASE = "https://www.betexplorer.com"
COMP = "/basketball/europe/fiba-europe-cup/"
BOOKS = ["Stake.com", "bwin", "Betsson"]          # bookmaker preference, in this order (per market, per match)
SEASON = "2026-2027"
H = {"User-Agent": "Mozilla/5.0"}


def read_js(path):
    s = path.read_text(encoding="utf-8")
    return s[:s.index("{")], json.loads(s[s.index("{"):s.rindex("}") + 1])


def update_results():
    pre, data = read_js(SITE / "data.js")
    rows = []
    for stage, href in scrape.stages("current"):
        rows += scrape.scrape_stage("current", stage, href)
    new = [[r["season"], r["stage"], r["round"], r["date"], r["home"], r["away"], int(r["home_pts"]), int(r["away_pts"]), r["status"]]
           for r in rows if r["home_pts"] not in (None, "") and r["status"] in ("FT", "AET", "AWA.")]
    if not new:
        raise SystemExit("No 2026-27 results found; data.js left untouched.")
    unknown = sorted({t for r in new for t in (r[4], r[5]) if t not in data["teams"]})
    if unknown:
        raise SystemExit(f"Clubs without a country in data.js: {unknown}. Add them to teams first.")
    old = [m for m in data["matches"] if m[0] == SEASON]
    known = {(m[4], m[5]): m[3] for m in old}      # "Yesterday" / "Today" are only approximate: keep a date we already have
    for r in new:
        d0 = known.get((r[4], r[5]))
        if d0 and abs((date.fromisoformat(d0) - date.fromisoformat(r[3])).days) <= 1:
            r[3] = d0
    keep = [m for m in data["matches"] if m[0] != SEASON]
    data["matches"] = keep + sorted(new, key=lambda m: m[3])
    (SITE / "data.js").write_text(pre + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    before = {(m[3], m[4], m[5]) for m in old}
    added = [m for m in new if (m[3], m[4], m[5]) not in before]
    print(f"results: {len(new)} games in {SEASON} ({len(added)} new)")
    for m in added:
        print("  +", m[3], m[4], m[5], f"{m[6]}-{m[7]}")


def odds_rows(match_id, kind):
    r = requests.get(f"{BASE}/match-odds-old/{match_id}/0/{kind}/1/en/", headers=H, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.json()["odds"], "html.parser")
    out = []
    for tr in soup.select("table tbody tr[data-bookie-id]"):
        logo = tr.select_one("span.in-bookmaker-logo")
        name = logo["title"] if logo and logo.has_attr("title") else tr.get_text(" ", strip=True)
        line = tr.select_one("td.table-main__doubleparameter")
        odds = [float(td["data-odd"]) for td in tr.select("td.table-main__detail-odds") if td.has_attr("data-odd")]
        if len(odds) >= 2:
            out.append((name, float(line.get_text(strip=True)) if line else None, odds[:2]))
    time.sleep(0.3)
    return out


def pick(rows):
    for book in BOOKS:
        mine = [(l, o) for n, l, o in rows if n == book]
        if mine:
            line, odds = min(mine, key=lambda x: abs(x[1][0] - x[1][1]))
            return line, odds[0], odds[1], book
    by = {}                                     # none of the preferred bookmakers: average the others per line
    for _, l, o in rows:
        by.setdefault(l, []).append(o)
    avg = [(l, [sum(x[i] for x in v) / len(v) for i in (0, 1)]) for l, v in by.items() if len(v) >= 2]
    if not avg:
        return None
    line, odds = min(avg, key=lambda x: abs(x[1][0] - x[1][1]))
    return line, odds[0], odds[1], "average"


def update_odds():
    soup = BeautifulSoup(requests.get(BASE + COMP + "fixtures/", headers=H, timeout=30).text, "html.parser")
    fx, hdr = [], ""
    for tr in soup.select("table.table-main tr"):
        th = tr.find("th")
        if th:
            hdr = th.get_text(" ", strip=True)
            continue
        a = tr.select_one("a.in-match")
        m = re.search(r"(\d+)\. Round", hdr)
        if a and m:
            sp = [s.get_text(strip=True) for s in a.find_all("span")]
            fx.append((int(m[1]), sp[0], sp[1], a["href"].rstrip("/").split("/")[-1]))
    if not fx:
        raise SystemExit("No fixtures found; odds.js left untouched.")
    nxt = min(f[0] for f in fx)
    out = []
    for _, h, a, mid in [f for f in fx if f[0] == nxt]:
        ah, ou, ha = (pick(odds_rows(mid, k)) for k in ("ah", "ou", "ha"))
        if not (ah and ou):
            print("  no handicap / total line yet:", h, "-", a)
            continue
        out.append({"h": h, "a": a, "sp": ah[0], "spH": ah[1], "spA": ah[2], "tot": ou[0], "ov": ou[1], "un": ou[2],
                    "mlH": ha[1] if ha else None, "mlA": ha[2] if ha else None})   # no bookmaker names on the site
    if not out:
        raise SystemExit("No odds found; odds.js left untouched.")
    head = ("// Bookmaker lines for upcoming fixtures, keyed by the fixture's home and away club.\n"
            "// sp = handicap on the home side (+ means the home side is the underdog), spH / spA = its odds home / away,\n"
            "// tot = points total, ov / un = odds over / under, mlH / mlA = money line odds (null when not offered).\n")
    body = ",\n".join("  " + json.dumps(o, ensure_ascii=False) for o in out)
    (SITE / "odds.js").write_text(
        head + 'window.ODDS = {"updated": "' + time.strftime("%Y-%m-%d") + '", "source": "pre-game lines", "list": [\n' + body + "\n]};\n",
        encoding="utf-8")
    print(f"odds: round {nxt}, {len(out)} matches")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "results"):
        update_results()
    if what in ("all", "odds"):
        update_odds()
