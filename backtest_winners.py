"""Tune the model to pick winners, then test it on 2025-26 against the bookmaker's favourite.

    python backtest_winners.py

Tuning uses results only (2018-19 to 2024-25): every game is projected from earlier games, and the settings that pick
the winner most often are kept. 2025-26 is not looked at while tuning. Then, on the 2025-26 games that have
OddsPortal closing odds (data/oddsportal/2025-2026.txt), the tuned model's pick is compared with the bookmaker's
favourite (the side with the lower odds).

Settings searched: places either side (nn), seasons in the group sample, recency half-life, and the weight given to
the country Elo gap versus the group estimate (0 = group only, 1 = Elo only); also the club-level Elo.
"""
import itertools
from datetime import date
from pathlib import Path

import backtest

ROOT = Path(__file__).parent
ALL_STAGES = backtest.GROUP_STAGES | {"Second stage", "Play Offs", "Qualification"}
TEST = "2025-2026"


def load_oddsportal():
    rows = []
    for line in (ROOT / "data" / "oddsportal" / f"{TEST}.txt").read_text(encoding="utf-8").strip().split("~"):
        d, stage, h, a, hs, as_, o1, o2, status = line.split("|")
        if not o1 or not o2 or hs == as_:
            continue
        rows.append(dict(day=date(int(d[:4]), int(d[4:6]), int(d[6:])), h=h, a=a, o1=float(o1), o2=float(o2),
                         home_won=int(hs) > int(as_)))
    return rows


def margins(r, w_elo, w_club):
    """The tuned handicap: a weighted mix of the group estimate (rec), the country Elo gap and the club Elo gap."""
    if "rec" not in r:
        return None
    return (1 - w_elo - w_club) * r["rec"][0] + w_elo * r["elo"][0] + w_club * r["club"][0]


def accuracy(rows, w_elo, w_club, only=None):
    pts = [(margins(r, w_elo, w_club), r["actual"][0]) for r in rows if (only is None or only(r))]
    pts = [(m, a) for m, a in pts if m is not None and m != 0]
    return (sum((m > 0) == (a > 0) for m, a in pts) / len(pts), len(pts)) if pts else (0, 0)


def main():
    prepared = backtest.prepare(*backtest.load("men"))
    seasons = prepared[1]
    tune_from, test_idx = seasons.index("2018-2019"), seasons.index(TEST)
    weights = [(we, wc) for we in (0, 0.25, 0.5, 0.75, 1) for wc in (0, 0.25, 0.5) if we + wc <= 1]
    results = []
    for nn, sb, hl in itertools.product((1, 2, 3), (3, 5, 8), (365, 548, 1095)):
        rows, _ = backtest.run(prepared, eval_from=tune_from, seasons_back=sb, nn=nn, halflife=hl, stages=ALL_STAGES)
        tune = [r for r in rows if r["season"] < test_idx]
        for we, wc in weights:
            acc, n = accuracy(tune, we, wc)
            results.append((acc, n, dict(nn=nn, seasons_back=sb, halflife=hl, w_elo=we, w_club=wc), rows))
        print(f"  searched nn={nn} seasons={sb} half-life={hl}", flush=True)
    results.sort(key=lambda x: -x[0])
    print("\nBest settings on 2018-19 to 2024-25 (winner picked, all stages):")
    for acc, n, cfg, _ in results[:8]:
        print(f"  {acc * 100:5.1f}% of {n}  {cfg}")
    site_like = [x for x in results if x[2] == dict(nn=2, seasons_back=5, halflife=548, w_elo=0.5, w_club=0)][0]
    print(f"  (the site's current mix: {site_like[0] * 100:.1f}% of {site_like[1]})")

    # ---- test on 2025-26 against the bookmaker
    odds = load_oddsportal()
    best = results[0]
    print(f"\nTest season {TEST}: OddsPortal games with odds: {len(odds)}")
    for label, (acc, n, cfg, rows) in (("tuned best", best), ("site's mix", site_like)):
        test = {r["key"][1:]: r for r in rows if r["season"] == test_idx}
        both = mw = bw = 0
        unmatched = []
        dis = dis_m = 0
        for o in odds:
            r = test.get((o["h"], o["a"]))
            if not r or abs((date.fromisoformat(r["key"][0]) - o["day"]).days) > 1:
                unmatched.append(f"{o['h']} - {o['a']}")
                continue
            m = margins(r, cfg["w_elo"], cfg["w_club"])
            if m is None or m == 0 or o["o1"] == o["o2"]:
                continue
            both += 1
            model_home, book_home = m > 0, o["o1"] < o["o2"]
            mw += model_home == o["home_won"]
            bw += book_home == o["home_won"]
            if model_home != book_home:
                dis += 1
                dis_m += model_home == o["home_won"]
        print(f"\n  {label} {cfg}")
        print(f"    games compared: {both}   model picked the winner {mw} ({mw / both * 100:.1f}%)   bookmaker {bw} ({bw / both * 100:.1f}%)")
        print(f"    they disagreed on {dis} games: model right {dis_m}, bookmaker right {dis - dis_m}")
        if unmatched:
            print(f"    {len(unmatched)} OddsPortal games not matched to the data (names / not projected): {unmatched[:8]}")

    # hindsight: the best any setting would have done on 2025-26 itself (not a fair test, shown for context)
    hind = []
    for acc, n, cfg, rows in results:
        test = {r["key"][1:]: r for r in rows if r["season"] == test_idx}
        pts = []
        for o in odds:
            r = test.get((o["h"], o["a"]))
            if r and abs((date.fromisoformat(r["key"][0]) - o["day"]).days) <= 1:
                m = margins(r, cfg["w_elo"], cfg["w_club"])
                if m:
                    pts.append(((m > 0) == o["home_won"], (o["o1"] < o["o2"]) == o["home_won"]))
        if pts:
            hind.append((sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts), len(pts), cfg))
    hind.sort(key=lambda x: -x[0])
    print("\nHindsight only (settings picked on 2025-26 itself, so not a real test):")
    for a, b, n, cfg in hind[:3]:
        print(f"  model {a * 100:.1f}% vs bookmaker {b * 100:.1f}% on {n}  {cfg}")


if __name__ == "__main__":
    main()
