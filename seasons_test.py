"""How many seasons should the projections' sample use?

    python seasons_test.py

Every group-stage game from 2018-19 on is projected from earlier games only, with the site's mix model (places +-2,
recency half-life 18 months), once for each sample length: 1 season (the current one) up to all seasons. All lengths
are scored on the same games (those every length can project), so the comparison is like for like.
"""
from statistics import mean

import backtest

LENGTHS = list(range(1, 12))          # 11 = every season since 2015-16


def main():
    prepared = backtest.prepare(*backtest.load("men"))
    seasons = prepared[1]
    start = seasons.index("2018-2019")
    runs = {}
    for sb in LENGTHS:
        rows, _ = backtest.run(prepared, eval_from=start, seasons_back=sb, nn=2, halflife=548)
        runs[sb] = {r["key"]: r for r in rows if "mix" in r}
        print(f"  ran {sb} season(s)", flush=True)
    common = set.intersection(*(set(v) for v in runs.values()))
    print(f"\nGames every sample length can project: {len(common)} (group stage, 2018-19 to now)\n")
    print(f"{'seasons':>8}{'winner %':>10}{'hcp error':>11}   winner % by test season")
    test_seasons = sorted({runs[1][k]["season"] for k in common})
    for sb in LENGTHS:
        rs = [runs[sb][k] for k in common]
        acc = mean((r["mix"][0] > 0) == (r["actual"][0] > 0) for r in rs)
        err = mean(abs(r["mix"][0] - r["actual"][0]) for r in rs)
        per = []
        for s in test_seasons:
            x = [r for r in rs if r["season"] == s]
            per.append(f"{seasons[s][2:4]}-{seasons[s][7:9]} {mean((r['mix'][0] > 0) == (r['actual'][0] > 0) for r in x) * 100:4.1f}")
        label = "all" if sb == LENGTHS[-1] else str(sb)
        print(f"{label:>8}{acc * 100:10.1f}{err:11.2f}   " + "  ".join(per))


if __name__ == "__main__":
    main()
