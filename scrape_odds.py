"""Collect BetExplorer's odds for finished FIBA Europe Cup games, for backtesting the model against the market.

    python scrape_odds.py [season]        # default 2025-2026

For every game of the season in data/matches.csv it asks BetExplorer for the home/away (money line) and Asian
handicap odds and keeps, per market, the lines of Stake.com, bwin and Betsson plus the average of all bookmakers.
These are the odds BetExplorer still shows after the game (closing odds). Output: data/odds_<season>.json,
written after every game so an interrupted run resumes where it stopped. Requests are spaced 10 s apart and back
off when BetExplorer answers 429.
"""
import csv
import json
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
BOOKS = ["Stake.com", "bwin", "Betsson"]
H = {"User-Agent": "Mozilla/5.0"}
_last = [0.0]
GAP = 10.0                                              # seconds between requests: BetExplorer limits fast clients


def get(url):
    for wait in (0, 60, 120, 240, 480):
        time.sleep(wait)
        time.sleep(max(0.0, GAP - (time.time() - _last[0])))
        r = requests.get(url, headers=H, timeout=60)
        _last[0] = time.time()
        if r.status_code == 429:
            print("  429, waiting ...", flush=True)
            continue
        r.raise_for_status()
        if "unavailable in" in r.text[:2000]:
            raise SystemExit("BetExplorer blocked the request; stopping.")
        return r
    raise SystemExit("BetExplorer keeps answering 429; stopping. Run again later to resume.")


def market(match_id, kind):
    soup = BeautifulSoup(get(f"https://www.betexplorer.com/match-odds-old/{match_id}/0/{kind}/1/en/").json()["odds"], "html.parser")
    rows = []
    for tr in soup.select("table tbody tr[data-bookie-id]"):
        logo = tr.select_one("span.in-bookmaker-logo")
        name = logo["title"] if logo and logo.has_attr("title") else "?"
        line = tr.select_one("td.table-main__doubleparameter")
        odds = [float(td["data-odd"]) for td in tr.select("td.table-main__detail-odds") if td.has_attr("data-odd")]
        if len(odds) >= 2:
            rows.append((name, float(line.get_text(strip=True)) if line else None, odds[0], odds[1]))
    out = {b: [[l, a, c] for n, l, a, c in rows if n == b] for b in BOOKS}
    by = {}
    for n, l, a, c in rows:
        by.setdefault(l, []).append((a, c))
    out["avg"] = [[l, sum(x[0] for x in v) / len(v), sum(x[1] for x in v) / len(v), len(v)] for l, v in by.items()]
    return out


def main():
    season = sys.argv[1] if len(sys.argv) > 1 else "2025-2026"
    path = ROOT / "data" / f"odds_{season}.json"
    done = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    games = [r for r in csv.DictReader((ROOT / "data" / "matches.csv").open(encoding="utf-8"))
             if r["season"] == season and r["status"] in ("FT", "AET") and r["match_id"]]
    todo = [g for g in games if g["match_id"] not in done]
    print(f"{season}: {len(games)} games, {len(done)} already done, {len(todo)} to fetch", flush=True)
    for i, g in enumerate(todo, 1):
        done[g["match_id"]] = {"date": g["date"], "home": g["home"], "away": g["away"], "stage": g["stage"],
                               "hp": int(g["home_pts"]), "ap": int(g["away_pts"]),
                               "ha": market(g["match_id"], "ha"), "ah": market(g["match_id"], "ah")}
        path.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
        if i % 10 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
