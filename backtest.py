"""Walk-forward backtest of the projection model.

    python backtest.py [men|women]

Every group-stage game from EVAL_FROM onwards is projected using only games played on earlier days (rankings
included), then scored against the real result. This answers "which version of the model is better" on hundreds
of games instead of the handful that the Archive collects. There are no historical bookmaker lines, so variants
are compared with each other and with simple baselines, not with the market.

Variants
  base   league average handicap and total
  site   what the site does now: countries +/-N places in the Elo ranking, home group at home vs away group away
  pool   same groups, but games in both directions, home advantage taken out of every score
  rec    pool + recent games count more (half-life in days)
  elo    handicap from the country Elo gap (points per Elo point fitted before EVAL_FROM), total from rec
  club   handicap from a club-level Elo gap (fitted the same way), total from rec
  mix    handicap = average of rec and elo, total from rec
"""
import json
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

PATHS = {
    "men": Path(r"C:\Users\antonis\Desktop\nikolitso.github.io\fibaeuropecup\data.js"),
    "women": Path(r"C:\Users\antonis\Desktop\eurocup-women\site\data.js"),
}
GROUP_STAGES = {"Main", "First stage", "Preliminary"}   # the group stage has had three names over the years
K, HCA = 20, 75                                         # Elo settings, as on the site
MIN_GAMES = 8


def load(kind):
    s = PATHS[kind].read_text(encoding="utf-8")
    d = json.loads(s[s.index("{"):s.rindex("}") + 1])
    return d["matches"], d["teams"]


def prepare(matches, teams):
    """Games in date order, each with the Elo information as it stood just before the game."""
    seasons = sorted({m[0] for m in matches})
    games = []
    for m in sorted(matches, key=lambda m: m[3]):
        season, stage, _, day, h, a, hp, ap, status = m
        games.append(dict(season=seasons.index(season), stage=stage, day=date.fromisoformat(day), h=h, a=a,
                          ch=teams.get(h), ca=teams.get(a), hp=hp, ap=ap, awa=status == "AWA."))
    elo, club = defaultdict(lambda: 1500.0), defaultdict(lambda: 1500.0)
    i = 0
    while i < len(games):
        j = i
        while j < len(games) and games[j]["day"] == games[i]["day"]:
            j += 1
        order = [c for c, _ in sorted(elo.items(), key=lambda x: -x[1])]      # snapshot before this day
        for g in games[i:j]:
            g["order"] = order
            g["cdiff"] = elo.get(g["ch"], 1500.0) - elo.get(g["ca"], 1500.0) + HCA if g["ch"] != g["ca"] else None
            g["kdiff"] = club.get(g["h"], 1500.0) - club.get(g["a"], 1500.0) + HCA
        for g in games[i:j]:                                                    # then update with the day's games
            for table, x, y in ((club, g["h"], g["a"]),) + (((elo, g["ch"], g["ca"]),) if g["ch"] != g["ca"] else ()):
                exp = 1 / (1 + 10 ** ((table[y] - (table[x] + HCA)) / 400))
                home_won = 1 if g["hp"] > g["ap"] else 0
                margin = abs(g["hp"] - g["ap"])
                wd = (table[x] + HCA - table[y]) if home_won else (table[y] - table[x] - HCA)
                mult = 1 if g["awa"] else ((margin + 3) ** 0.8) / (7.5 + 0.006 * wd)
                delta = K * mult * (home_won - exp)
                table[x] += delta
                table[y] -= delta
        i = j
    return games, seasons


def peers(order, c, n):
    if c not in order:
        return None
    i = order.index(c)
    return set(order[max(0, i - n):i + n + 1])


def group_pred(sub, gh, ga, home_adv, pooled, halflife, today):
    """Average score of the home group and the away group over past games between the two groups.

    Venue-specific (the site): only games with the home group at home, raw scores.
    Pooled: games in both directions, home advantage taken out of every score and put back for this game.
    """
    sh = sa = w = 0.0
    n = 0
    half = home_adv / 2
    for g in sub:
        wt = 0.5 ** ((today - g["day"]).days / halflife) if halflife else 1.0
        if g["ch"] in gh and g["ca"] in ga:                    # home group played at home
            sh += wt * (g["hp"] - half if pooled else g["hp"])
            sa += wt * (g["ap"] + half if pooled else g["ap"])
            w += wt
            n += 1
        if pooled and g["ca"] in gh and g["ch"] in ga:         # home group played away
            sh += wt * (g["ap"] + half)
            sa += wt * (g["hp"] - half)
            w += wt
            n += 1
    if not w:
        return None
    if pooled:
        return sh / w + half, sa / w - half, n
    return sh / w, sa / w, n


def run(prepared, eval_from=3, seasons_back=5, nn=2, halflife=548):
    games, seasons = prepared
    rows = []
    # points per Elo point, fitted on group-stage games before the evaluation seasons
    train = [g for g in games if g["season"] < eval_from and g["stage"] in GROUP_STAGES and not g["awa"]]
    fit = lambda key: (sum(g[key] * (g["hp"] - g["ap"]) for g in train if g[key] is not None) /
                       max(1e-9, sum(g[key] ** 2 for g in train if g[key] is not None)))
    b_c, b_k = fit("cdiff"), fit("kdiff")
    for idx, g in enumerate(games):
        if g["season"] < eval_from or g["stage"] not in GROUP_STAGES or g["awa"] or g["ch"] == g["ca"]:
            continue
        past = [x for x in games[:idx] if x["day"] < g["day"] and not x["awa"] and x["ch"] != x["ca"]]
        sub = [x for x in past if x["stage"] in GROUP_STAGES and g["season"] - seasons_back < x["season"] <= g["season"]]
        if len(sub) < 20:
            continue
        home_adv = sum(x["hp"] - x["ap"] for x in sub) / len(sub)
        avg_total = sum(x["hp"] + x["ap"] for x in sub) / len(sub)
        gh, ga = peers(g["order"], g["ch"], nn), peers(g["order"], g["ca"], nn)
        actual = (g["hp"] - g["ap"], g["hp"] + g["ap"])
        r = {"actual": actual, "season": g["season"], "base": (home_adv, avg_total)}
        if gh and ga:
            s = group_pred(sub, gh, ga, home_adv, False, 0, g["day"])
            p = group_pred(sub, gh, ga, home_adv, True, 0, g["day"])
            c = group_pred(sub, gh, ga, home_adv, True, halflife, g["day"])
            r["n_site"], r["n_pool"] = (s[2] if s else 0), (p[2] if p else 0)
            if s:
                r["site"] = (s[0] - s[1], s[0] + s[1])
            if p:
                r["pool"] = (p[0] - p[1], p[0] + p[1])
            if c:
                r["rec"] = (c[0] - c[1], c[0] + c[1])
                r["elo"] = (b_c * g["cdiff"], c[0] + c[1])
                r["club"] = (b_k * g["kdiff"], c[0] + c[1])
                r["mix"] = ((c[0] - c[1] + b_c * g["cdiff"]) / 2, c[0] + c[1])
                tot = c[0] + c[1]
                for k in (10, 20, 40):                         # total pulled toward the league average when few games
                    r[f"shr{k}"] = (r["mix"][0], avg_total + (tot - avg_total) * c[2] / (c[2] + k))
        rows.append(r)
    return rows, (b_c, b_k)


def score(rows, key, only=None):
    pts = [r for r in rows if key in r and (only is None or only(r))]
    if not pts:
        return None
    mh = sum(abs(r[key][0] - r["actual"][0]) for r in pts) / len(pts)
    mt = sum(abs(r[key][1] - r["actual"][1]) for r in pts) / len(pts)
    acc = sum((r[key][0] > 0) == (r["actual"][0] > 0) for r in pts) / len(pts)
    bias = sum(r[key][1] - r["actual"][1] for r in pts) / len(pts)
    return len(pts), mh, mt, acc, bias


def table(title, rows, only, keys):
    print(f"\n{title}")
    print(f"{'variant':8}{'games':>7}{'hcp err':>9}{'tot err':>9}{'winner %':>10}{'tot bias':>10}")
    for k in keys:
        s = score(rows, k, only)
        if s:
            print(f"{k:8}{s[0]:7d}{s[1]:9.2f}{s[2]:9.2f}{s[3] * 100:10.1f}{s[4]:10.2f}")


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "men"
    # men: history from 2015-16, evaluate from 2018-19; women: history from 2012-13, evaluate from 2015-16
    eval_from = 3
    prepared = prepare(*load(kind))
    rows, (b_c, b_k) = run(prepared, eval_from=eval_from)
    keys = ["base", "site", "pool", "rec", "elo", "club", "mix", "shr10", "shr20", "shr40"]
    print(f"{kind}: {len(rows)} group-stage games projected; points per Elo point: country {b_c:.3f}, club {b_k:.3f}")
    table("All games where the variant can make a projection", rows, None, keys)
    common = lambda r: r.get("n_site", 0) >= MIN_GAMES
    table(f"Only games where the site model has {MIN_GAMES}+ games (what the site would compare)", rows, common, keys)
    thin = lambda r: 1 <= r.get("n_site", 0) < MIN_GAMES
    table(f"Only games where the site model has fewer than {MIN_GAMES} games", rows, thin, keys)
    split = eval_from + (len(prepared[1]) - eval_from) // 2          # tune on the earlier half, check on the later half
    table(f"Earlier seasons ({prepared[1][eval_from]} to {prepared[1][split - 1]})", rows, lambda r: r["season"] < split, keys)
    table(f"Later seasons ({prepared[1][split]} to {prepared[1][-1]}), not used for any choice above", rows, lambda r: r["season"] >= split, keys)
    print("\nSweeps of the 'mix' variant (handicap error / winner % on all projected games):")
    for label, kw in [("places +/-1", dict(nn=1)), ("places +/-2 (default)", dict()), ("places +/-3", dict(nn=3)), ("places +/-4", dict(nn=4)),
                      ("3 seasons", dict(seasons_back=3)), ("8 seasons", dict(seasons_back=8)),
                      ("half-life 1 year", dict(halflife=365)), ("half-life 3 years", dict(halflife=1095)), ("no recency", dict(halflife=0))]:
        rr, _ = run(prepared, eval_from=eval_from, **kw)
        sc, st = score(rr, "mix"), score(rr, "shr20")
        print(f"  {label:24} games {sc[0]:4d}  handicap err {sc[1]:5.2f}  winner {sc[3] * 100:4.1f}%  total err {st[2]:5.2f}")
    n_ok = sum(1 for r in rows if r.get("n_site", 0) >= MIN_GAMES)
    print(f"\ncoverage: site model has {MIN_GAMES}+ games for {n_ok} of {len(rows)} games ({n_ok / len(rows) * 100:.0f}%); "
          f"pooled version for {sum(1 for r in rows if r.get('n_pool', 0) >= MIN_GAMES)}")


if __name__ == "__main__":
    main()
