"""Backtest the model against real bookmaker odds (2025-26 FIBA Europe Cup).

    python backtest_vs_book.py [season]

Needs data/odds_<season>.json from scrape_odds.py. Every game of the season that has odds is projected by each model
variant using only games played on earlier days (backtest.py), and compared with the bookmaker on the same game:
  * winner picked    - did the favourite (model: positive handicap; book: lower money line) win?
  * Brier / log-loss - how good the win probabilities are (model: normal curve on the projected handicap with a
                       spread fitted on earlier seasons; book: money line odds with the margin removed)
  * handicap error   - average miss of the projected handicap against the real margin (book: its Asian handicap)
Bookmaker order: Stake.com, then bwin, then Betsson, then the average of all bookmakers. The odds BetExplorer shows
after a game are closing odds, which is the hardest benchmark.
"""
import json
import math
import sys
from pathlib import Path

import backtest

ROOT = Path(__file__).parent
BOOKS = ["Stake.com", "bwin", "Betsson"]
VARIANTS = ["site", "pool", "rec", "elo", "mix"]


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def pick_ml(entry):
    for b in BOOKS:
        if entry["ha"].get(b):
            _, o1, o2 = entry["ha"][b][0]
            return o1, o2, b
    lines = [x for x in entry["ha"]["avg"] if x[3] >= 2]
    if lines:
        _, o1, o2, _n = lines[0]
        return o1, o2, "average"
    return None


def pick_ah(entry):
    """The handicap line whose two odds are closest to each other (the main line), from the preferred bookmaker."""
    for b in BOOKS:
        rows = entry["ah"].get(b)
        if rows:
            l, o1, o2 = min(rows, key=lambda x: abs(x[1] - x[2]))
            return l, b
    rows = [x for x in entry["ah"]["avg"] if x[3] >= 2]
    if rows:
        l, o1, o2, _n = min(rows, key=lambda x: abs(x[1] - x[2]))
        return l, "average"
    return None


def main():
    season_label = sys.argv[1] if len(sys.argv) > 1 else "2025-2026"
    odds = json.loads((ROOT / "data" / f"odds_{season_label}.json").read_text(encoding="utf-8"))
    by_key = {(e["date"], e["home"], e["away"]): e for e in odds.values()}
    prepared = backtest.prepare(*backtest.load("men"))
    seasons = prepared[1]
    sidx = seasons.index(season_label)

    # spread of the miss, fitted on the group-stage games before this season, one value per variant
    past, _ = backtest.run(prepared, eval_from=3)
    past = [r for r in past if r["season"] < sidx]
    sigma = {}
    for v in VARIANTS:
        res = [r[v][0] - r["actual"][0] for r in past if v in r]
        sigma[v] = math.sqrt(sum(x * x for x in res) / len(res))
    print("spread of the miss (points) fitted before this season:", {k: round(x, 1) for k, x in sigma.items()})

    rows, _ = backtest.run(prepared, eval_from=sidx, only_season=sidx, stages=backtest.GROUP_STAGES | {"Second stage", "Play Offs", "Qualification"})
    games = []
    for r in rows:
        e = by_key.get(r["key"])
        if not e:
            continue
        ml, ah = pick_ml(e), pick_ah(e)
        if not ml or not ah:
            continue
        o1, o2, src = ml
        pb = (1 / o1) / (1 / o1 + 1 / o2)
        margin = r["actual"][0]
        games.append(dict(r=r, pb=pb, bh=-ah[0], src=src, margin=margin, home_won=margin > 0, n=r.get("n_site", 0)))
    print(f"{season_label}: {len(rows)} games projected, {len(games)} with money line and handicap odds")
    if not games:
        return

    def report(title, subset):
        subset = [g for g in subset]
        if not subset:
            return
        print(f"\n{title} ({len(subset)} games)")
        print(f"{'':10}{'winner %':>10}{'brier':>8}{'log-loss':>10}{'hcp err':>9}")
        n = len(subset)
        pickb = [(g["pb"] > 0.5) == g["home_won"] for g in subset]
        brier = sum((g["pb"] - g["home_won"]) ** 2 for g in subset) / n
        ll = -sum(math.log(g["pb"] if g["home_won"] else 1 - g["pb"]) for g in subset) / n
        herr = sum(abs(g["bh"] - g["margin"]) for g in subset) / n
        print(f"{'bookmaker':10}{sum(pickb) / n * 100:10.1f}{brier:8.3f}{ll:10.3f}{herr:9.2f}")
        for v in VARIANTS:
            sub = [g for g in subset if v in g["r"]]
            if not sub:
                continue
            m = len(sub)
            pm = [min(max(phi(g["r"][v][0] / sigma[v]), 1e-4), 1 - 1e-4) for g in sub]
            acc = sum((g["r"][v][0] > 0) == g["home_won"] for g in sub) / m
            br = sum((p - g["home_won"]) ** 2 for p, g in zip(pm, sub)) / m
            l2 = -sum(math.log(p if g["home_won"] else 1 - p) for p, g in zip(pm, sub)) / m
            he = sum(abs(g["r"][v][0] - g["margin"]) for g in sub) / m
            print(f"{v:10}{acc * 100:10.1f}{br:8.3f}{l2:10.3f}{he:9.2f}")
        # does the model add anything to the market? blend the book probability with the model's
        for w in (0.2, 0.4):
            sub = [g for g in subset if "mix" in g["r"]]
            bl = [min(max((1 - w) * g["pb"] + w * phi(g["r"]["mix"][0] / sigma["mix"]), 1e-4), 1 - 1e-4) for g in sub]
            l3 = -sum(math.log(p if g["home_won"] else 1 - p) for p, g in zip(bl, sub)) / len(sub)
            acc = sum((p > 0.5) == g["home_won"] for p, g in zip(bl, sub)) / len(sub)
            print(f"{'blend ' + str(int(w * 100)) + '%':10}{acc * 100:10.1f}{'':8}{l3:10.3f}")
        dis = [g for g in subset if "mix" in g["r"] and (g["r"]["mix"][0] > 0) != (g["pb"] > 0.5)]
        if dis:
            mw = sum((g["r"]["mix"][0] > 0) == g["home_won"] for g in dis)
            print(f"  when mix and the book favour different sides ({len(dis)} games): mix right {mw}, book right {len(dis) - mw}")

    report("All games with odds", games)
    report("Group games only (Main + Second stage)", [g for g in games if g["r"]["stage"] in ("Main", "Second stage")])
    report("Only games where the site model has 8+ games", [g for g in games if g["n"] >= 8])
    for src in sorted({g["src"] for g in games}):
        c = [g for g in games if g["src"] == src]
        print(f"\nmoney line source {src}: {len(c)} games")


if __name__ == "__main__":
    main()
