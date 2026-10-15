"""How many places either side of each country should feed its group in the projections?

    python places_test.py

Same method as seasons_test.py: every group-stage game from 2018-19 on is projected from earlier games only, with the
site's mix model (5 seasons, recency half-life 18 months), once for each number of places (the same for home and away
side). As on the site, when the two groups have never met the projection falls back to the Elo gap alone. All
settings are scored on the same games.
"""
from statistics import mean

import backtest

PLACES = [0, 1, 2, 3, 4, 5, 6, 8, 10, 15]


def main():
    prepared = backtest.prepare(*backtest.load("men"))
    seasons = prepared[1]
    start = seasons.index("2018-2019")
    runs, elo = {}, {}
    for nn in PLACES:
        rows, _ = backtest.run(prepared, eval_from=start, seasons_back=5, nn=nn, halflife=548)
        runs[nn] = {r["key"]: r for r in rows}
        for r in rows:
            if "elo" in r:
                elo[r["key"]] = r["elo"][0]            # the Elo gap does not depend on the places
        print(f"  ran +-{nn}", flush=True)
    common = [k for k in set.intersection(*(set(v) for v in runs.values())) if k in elo]
    test_seasons = sorted({runs[0][k]["season"] for k in common})
    print(f"\nGames compared: {len(common)} (group stage, 2018-19 to now)\n")
    print(f"{'places':>7}{'winner %':>10}{'hcp error':>11}{'Elo only':>10}{'avg games':>11}{'8+ games':>10}   winner % by test season")
    for nn in PLACES:
        rs = [runs[nn][k] for k in common]
        pred = [r["mix"][0] if "mix" in r else elo[r["key"]] for r in rs]
        hit = [(p > 0) == (r["actual"][0] > 0) for p, r in zip(pred, rs)]
        err = mean(abs(p - r["actual"][0]) for p, r in zip(pred, rs))
        fallback = mean("mix" not in r for r in rs)
        ng = mean(r.get("n_pool", 0) for r in rs)
        eight = mean(r.get("n_pool", 0) >= 8 for r in rs)
        per = []
        for s in test_seasons:
            x = [h for h, r in zip(hit, rs) if r["season"] == s]
            per.append(f"{seasons[s][2:4]}-{seasons[s][7:9]} {mean(x) * 100:4.1f}")
        print(f"{'+-' + str(nn):>7}{mean(hit) * 100:10.1f}{err:11.2f}{fallback * 100:9.0f}%{ng:11.1f}{eight * 100:9.0f}%   " + "  ".join(per))


if __name__ == "__main__":
    main()
