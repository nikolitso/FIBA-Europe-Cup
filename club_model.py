"""Club-rating model for the FIBA Europe Cup (the EuroCup page's model, adapted), and its backtest against the site's mix.

    python club_model.py

Handicap: margin = hca + r[home] - r[away], fitted on the season's games before the match by weighted ridge
regression: older games fade with a half-life, and each rating is pulled toward a prior with a strength of `k` games.
Prior: last season's final club rating x keep, plus (1 - keep) x the club's country rating (the power-ranking Elo
turned into points); clubs that did not play last season start from the country rating alone, times `new`.
(The EuroCup model scales the prior by roster continuity; there are no box scores for past FIBA seasons, so the
country rating takes that role.)
Total: total = mu + t[home] + t[away], fitted the same way (prior: last season's t x 0.5).

Backtest: every group-stage game between clubs of different countries from 2023-24 on, projected from earlier days
only; settings tuned on 2023-24 and 2024-25, then tested on 2025-26 and 2026-27 (and against the bookmaker where
lines exist).
"""
import itertools
import json
import math
import os
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

import backtest

HERE = Path(__file__).parent
SITE = Path(os.environ.get("FIBA_SITE", r"C:\Users\antonis\Desktop\nikolitso.github.io\fibaeuropecup"))   # FIBA_SITE: set by the GitHub job
ELO_POINTS = 0.060                       # points per country-Elo point, as in the site's mix
TUNE = ["2023-2024", "2024-2025"]
TEST = ["2025-2026", "2026-2027"]


def ridge_margin(games, prior, k, half, today, hca):
    clubs = sorted({c for g in games for c in (g["h"], g["a"])} | set(prior))
    ix = {c: i for i, c in enumerate(clubs)}
    n = len(clubs)
    A, b = np.zeros((n, n)), np.zeros(n)
    for g in games:
        w = 0.5 ** ((today - g["day"]).days / half) if half else 1.0
        i, j = ix[g["h"]], ix[g["a"]]
        y = g["hp"] - g["ap"] - hca
        A[i, i] += w; A[j, j] += w; A[i, j] -= w; A[j, i] -= w
        b[i] += w * y; b[j] -= w * y
    for c, i in ix.items():
        A[i, i] += k; b[i] += k * prior.get(c, 0.0)
    sol = np.linalg.solve(A, b)
    return {c: sol[i] for c, i in ix.items()}


def ridge_total(games, prior, k, half, today, mu):
    clubs = sorted({c for g in games for c in (g["h"], g["a"])} | set(prior))
    ix = {c: i for i, c in enumerate(clubs)}
    n = len(clubs)
    A, b = np.zeros((n, n)), np.zeros(n)
    for g in games:
        w = 0.5 ** ((today - g["day"]).days / half) if half else 1.0
        i, j = ix[g["h"]], ix[g["a"]]
        y = g["hp"] + g["ap"] - mu
        for u in (i, j):
            b[u] += w * y
            for v in (i, j):
                A[u, v] += w
    for c, i in ix.items():
        A[i, i] += k; b[i] += k * prior.get(c, 0.0)
    sol = np.linalg.solve(A, b)
    return {c: sol[i] for c, i in ix.items()}


def country_elo(games):
    """country -> Elo after every game in `games` (same settings as the site's power rankings)"""
    elo = defaultdict(lambda: 1500.0)
    for g in games:
        if not g["ch"] or not g["ca"] or g["ch"] == g["ca"]:
            continue
        x, y = g["ch"], g["ca"]
        exp = 1 / (1 + 10 ** ((elo[y] - (elo[x] + backtest.HCA)) / 400))
        hw = 1 if g["hp"] > g["ap"] else 0
        wd = (elo[x] + backtest.HCA - elo[y]) if hw else (elo[y] - elo[x] - backtest.HCA)
        mult = 1 if g["awa"] else ((abs(g["hp"] - g["ap"]) + 3) ** 0.8) / (7.5 + 0.006 * wd)
        d = backtest.K * mult * (hw - exp)
        elo[x] += d; elo[y] -= d
    return elo


class Season:
    """Everything fixed at the start of a season: priors, home advantage, league total."""

    def __init__(self, games, si, p):
        prev = [g for g in games if g["season"] == si - 1 and not g["awa"]]
        cur = [g for g in games if g["season"] == si and not g["awa"]]
        before = [g for g in games if g["season"] < si]
        elo = country_elo(before)
        clubs = {c for g in cur for c in (g["h"], g["a"])}
        cs = [elo[c] for c in {teams_of(g, s) for g in cur for s in "ha"} if c]
        mean_elo = sum(cs) / len(cs) if cs else 1500.0
        crat = lambda club: ELO_POINTS * (elo[club_country[club]] - mean_elo) if club_country.get(club) else 0.0
        self.hca = sum(g["hp"] - g["ap"] for g in prev) / len(prev) if prev else 4.0
        self.mu0 = sum(g["hp"] + g["ap"] for g in prev) / len(prev) if prev else 160.0
        today = max(g["day"] for g in prev) if prev else None
        r_end = ridge_margin(prev, {}, 2.0, 0, today, self.hca) if prev else {}
        t_end = ridge_total(prev, {}, 2.0, 0, today, self.mu0) if prev else {}
        pr = {}
        for c in clubs:
            pr[c] = p["keep"] * r_end[c] + (1 - p["keep"]) * crat(c) if c in r_end else p["new"] * crat(c)
        m = sum(pr.values()) / len(pr)
        self.pr = {c: v - m for c, v in pr.items()}
        self.pt = {c: t_end.get(c, 0.0) * 0.5 for c in clubs}
        self.cur = cur


def teams_of(g, side):
    return g["ch"] if side == "h" else g["ca"]


def project_season(games, si, p, eval_keys=None):
    """(date iso, h, a) -> (handicap, total, home win chance) for every game of season si, from earlier days only"""
    S = Season(games, si, p)
    out, by_day = {}, defaultdict(list)
    for g in S.cur:
        by_day[g["day"]].append(g)
    for day in sorted(by_day):
        todo = [g for g in by_day[day] if eval_keys is None or (day.isoformat(), g["h"], g["a"]) in eval_keys]
        if not todo:
            continue
        before = [g for g in S.cur if g["day"] < day]
        r = ridge_margin(before, S.pr, p["k"], p["half"], day, S.hca) if before else S.pr
        mu = (S.mu0 * 60 + sum(g["hp"] + g["ap"] for g in before)) / (60 + len(before))
        t = ridge_total(before, S.pt, p["k"], p["half"], day, mu) if before else S.pt
        for g in todo:
            h = S.hca + r.get(g["h"], S.pr.get(g["h"], 0)) - r.get(g["a"], S.pr.get(g["a"], 0))
            out[(day.isoformat(), g["h"], g["a"])] = (h, mu + t.get(g["h"], 0) + t.get(g["a"], 0))
    return out


def metrics(pairs):
    """pairs: [(projected handicap, actual margin)] -> n, winner %, avg miss, rmse"""
    pairs = [(m, a) for m, a in pairs if m is not None and m != 0 and a != 0]
    n = len(pairs)
    if not n:
        return 0, 0, 0, 0
    return (n, sum((m > 0) == (a > 0) for m, a in pairs) / n * 100,
            sum(abs(a - m) for m, a in pairs) / n, math.sqrt(sum((a - m) ** 2 for m, a in pairs) / n))


def book_lines():
    """(h, a, season) -> (book handicap, book total or None) for 2025-26 (BetExplorer file) and 2026-27 (site)"""
    out = {}
    old = json.loads((HERE / "data/odds_2025-2026.json").read_text(encoding="utf-8"))
    for g in old.values():
        for b in ("Stake.com", "bwin", "Betsson"):
            L = g["ah"].get(b) or []
            if L:
                sp = min(L, key=lambda x: abs(x[1] - x[2]))[0]
                out[(g["home"], g["away"], "2025-2026")] = (-sp, None)
                break
    rd = lambda f: (lambda t: json.loads(t[t.index("{"):t.rindex("}") + 1]))((SITE / f).read_text(encoding="utf-8"))
    for sn in rd("archive.js")["list"]:
        for g in sn["games"]:
            out[(g["h"], g["a"], "2026-2027")] = (g["bh"], g.get("bt"))
    for g in rd("market.js")["list"]:
        out.setdefault((g["h"], g["a"], "2026-2027"), (g["bh"], g.get("bt")))
    return out


matches, teams = backtest.load("men")
club_country = teams
games, seasons = backtest.prepare(matches, teams)


def main():
    first = seasons.index(TUNE[0])
    mix_rows, _ = backtest.run((games, seasons), eval_from=first, seasons_back=5, nn=3, halflife=548)
    mix = {r["key"]: (r["mix"][0] if "mix" in r else r.get("elo", (None,))[0], r["actual"][0], seasons[r["season"]]) for r in mix_rows}
    keys = {k for k, v in mix.items() if v[0] is not None}
    print(f"evaluation games (group stage, different countries, with a mix projection): {len(keys)}")

    grid = [dict(half=h, k=k, keep=kp, new=nw) for h, k, kp, nw in
            itertools.product((120, 240, 480), (2.0, 4.0, 8.0), (0.5, 0.7, 0.85, 1.0), (1.0, 1.5, 2.0))]
    proj_cache = {}

    def run(p):
        key = tuple(sorted(p.items()))
        if key not in proj_cache:
            out = {}
            for s in TUNE + TEST:
                out.update(project_season(games, seasons.index(s), p, keys))
            proj_cache[key] = out
        return proj_cache[key]

    def score(p, which):
        pr = run(p)
        return metrics([(pr[k][0], mix[k][1]) for k in keys if mix[k][2] in which and k in pr])

    res = sorted(((score(p, TUNE), p) for p in grid), key=lambda x: x[0][2])   # lowest handicap miss on the tuning seasons
    best = res[0][1]
    print("\nBest settings on 2023-24 and 2024-25 (by handicap miss):")
    for s, p in res[:5]:
        print(f"  miss {s[2]:.2f}  winners {s[1]:.1f}%  {p}")

    print(f"\n{'season':12}{'games':>6}{'club: winners':>15}{'miss':>7}{'rmse':>7}{'mix: winners':>15}{'miss':>7}{'rmse':>7}")
    pr = run(best)
    for s in TUNE + TEST + ["all test"]:
        which = TEST if s == "all test" else [s]
        c = metrics([(pr[k][0], mix[k][1]) for k in keys if mix[k][2] in which and k in pr])
        m = metrics([(mix[k][0], mix[k][1]) for k in keys if mix[k][2] in which and k in pr])
        bl = metrics([((pr[k][0] + mix[k][0]) / 2, mix[k][1]) for k in keys if mix[k][2] in which and k in pr])
        tag = " (tuned on)" if s in TUNE else ""
        print(f"{s + tag:24}{c[0]:>0}  {c[1]:6.1f}%{c[2]:7.1f}{c[3]:7.1f}   {m[1]:6.1f}%{m[2]:7.1f}{m[3]:7.1f}   blend {bl[1]:5.1f}%{bl[2]:6.1f}{bl[3]:6.1f}")

    # against the bookmaker
    lines = book_lines()
    print("\nAgainst the bookmaker (games with a line):")
    print(f"{'season':12}{'games':>6}{'miss club':>11}{'mix':>7}{'book':>7}{'winners club':>14}{'mix':>6}{'book':>6}{'club 5+ apart: its way':>25}{'mix 5+ apart':>15}")
    for s in TEST:
        rows = []
        for k in keys:
            if mix[k][2] != s or k not in pr:
                continue
            ln = lines.get((k[1], k[2], s))
            if ln:
                rows.append((pr[k][0], mix[k][0], ln[0], mix[k][1], (pr[k][0] + mix[k][0]) / 2))
        if not rows:
            continue
        n = len(rows)
        miss = lambda i: sum(abs(r[3] - r[i]) for r in rows) / n
        win = lambda i: sum((r[i] > 0) == (r[3] > 0) for r in rows if r[i] != 0) / n * 100
        def way(i):
            x = [(r[i] > r[2]) == (r[3] > r[2]) for r in rows if abs(r[i] - r[2]) >= 5 and r[3] != r[2]]
            return f"{sum(x)} of {len(x)}" if x else "–"
        print(f"{s:12}{n:>6}{miss(0):>11.1f}{miss(1):>7.1f}{miss(2):>7.1f}{win(0):>13.0f}%{win(1):>5.0f}%{win(2):>5.0f}%{way(0):>25}{way(1):>15}"
              f"   blend: miss {miss(4):.1f}, winners {win(4):.0f}%, 5+ apart {way(4)}")

    # totals (2026-27 lines only)
    tot = []
    for k in keys:
        if mix[k][2] == "2026-2027" and k in pr:
            ln = lines.get((k[1], k[2], "2026-2027"))
            g = next(x for x in games if x["day"].isoformat() == k[0] and x["h"] == k[1] and x["a"] == k[2])
            if ln and ln[1] is not None:
                tot.append((pr[k][1], ln[1], g["hp"] + g["ap"]))
    if tot:
        n = len(tot)
        print(f"\nTotals 2026-27 ({n} games with a line): miss model {sum(abs(t[2] - t[0]) for t in tot) / n:.1f}, "
              f"book {sum(abs(t[2] - t[1]) for t in tot) / n:.1f}")
    print("\nchosen settings:", best)


if __name__ == "__main__":
    main()
