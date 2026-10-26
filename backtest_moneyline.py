"""Backtest of the model-vs-book gap rule on 2025-26, using money lines turned into handicaps.

    python backtest_moneyline.py

There are no handicap lines for most past games, but OddsPortal has the money line of almost every 2025-26 game
(data/oddsportal/2025-2026.txt, closing odds). The money line, margin removed, gives the book's home win chance p;
the handicap it implies is SIGMA x inverse-normal(p). SIGMA is fitted on the 44 games of data/odds_2025-2026.json
that have both a money line and an Asian handicap.

Each game is projected by the club-rating model (predict.py's settings, tuned on 2023-24 and 2024-25, so 2025-26 is
out of sample) from earlier days only. Rule: when the model's handicap differs from the book's, back the side the
model prefers; it wins when the real margin lands on that side of the book's line. Results by size of the gap.
2026-27 games already in the Archive (real handicaps) are shown as a second, live sample.
Break-even at the usual odds (about 1.85 / 1.80) is about 54%.
"""
import json
import math
from datetime import date
from pathlib import Path
from statistics import NormalDist

import club_model as cm
from predict import PARAMS

HERE = Path(__file__).parent
N = NormalDist()
BANDS = [(0, 3), (3, 6), (6, 10), (10, 99)]
BREAK_EVEN = 54.0


def no_vig(o1, o2):
    return (1 / o1) / (1 / o1 + 1 / o2)


def fit_sigma():
    """least-squares SIGMA for: book handicap = SIGMA x inverse-normal(home chance from the money line)"""
    pairs = []
    for g in json.loads((HERE / "data/odds_2025-2026.json").read_text(encoding="utf-8")).values():
        ml = next((g["ha"][b][0] for b in ("Stake.com", "bwin", "Betsson") if g["ha"].get(b)), None)
        ah = next((g["ah"][b] for b in ("Stake.com", "bwin", "Betsson") if g["ah"].get(b)), None)
        if ml and ah and ml[1] and ml[2]:
            z = N.inv_cdf(no_vig(ml[1], ml[2]))
            pairs.append((z, -min(ah, key=lambda x: abs(x[1] - x[2]))[0]))
    return sum(z * h for z, h in pairs) / sum(z * z for z, _ in pairs), len(pairs)


def oddsportal(sigma):
    out = []
    for rec in (HERE / "data/oddsportal/2025-2026.txt").read_text(encoding="utf-8").strip().split("~"):
        d, stage, h, a, hp, ap, o1, o2, _ = rec.split("|")
        if not (o1 and o2):
            continue
        out.append(dict(day=date(int(d[:4]), int(d[4:6]), int(d[6:])), stage=stage or "Main", h=h, a=a,
                        margin=int(hp) - int(ap), book=sigma * N.inv_cdf(no_vig(float(o1), float(o2)))))
    return out


def project(season):
    pr = cm.project_season(cm.games, cm.seasons.index(season), PARAMS)
    by_pair = {}
    for (d, h, a), v in pr.items():
        by_pair.setdefault((h, a), []).append((date.fromisoformat(d), v[0]))
    return by_pair


def model_for(by_pair, g):
    near = [(abs((d - g["day"]).days), m) for d, m in by_pair.get((g["h"], g["a"]), [])]
    near = [x for x in near if x[0] <= 1]
    return min(near)[1] if near else None


def report(title, rows):
    """rows: (model handicap, book handicap, real margin, stage)"""
    print(f"\n{title}")
    print(f"  {'gap':10}{'games':>7}{'model side won':>16}{'95% range':>16}")
    for lo, hi in BANDS + [(6, 99)]:
        sel = [(m, b, r) for m, b, r, _ in rows if lo <= abs(m - b) < hi and r != b]
        n = len(sel)
        if not n:
            continue
        w = sum((r - b > 0) == (m - b > 0) for m, b, r in sel)
        p = w / n
        ci = 1.96 * math.sqrt(p * (1 - p) / n) * 100
        name = f"{lo}+" if hi == 99 else f"{lo}-{hi}"
        flag = "  <- above break-even" if p * 100 - ci > BREAK_EVEN else ""
        print(f"  {name:10}{n:>7}{p * 100:>15.1f}%{f'{max(0, p * 100 - ci):.0f}-{min(100, p * 100 + ci):.0f}%':>16}{flag}")
    miss = lambda i: sum(abs(r[2] - r[i]) for r in rows) / len(rows)
    print(f"  average miss: model {miss(0):.1f}, book {miss(1):.1f} ({len(rows)} games)")


def main():
    sigma, n_fit = fit_sigma()
    print(f"money line -> handicap: SIGMA {sigma:.1f} (fitted on {n_fit} games with both lines)")
    by_pair = project("2025-2026")
    rows, unmatched = [], 0
    for g in oddsportal(sigma):
        m = model_for(by_pair, g)
        if m is None:
            unmatched += 1
            continue
        rows.append((m, g["book"], g["margin"], g["stage"]))
    print(f"2025-26: {len(rows)} games with a model projection and a money line ({unmatched} not matched)")
    report("2025-26, all stages (book line implied by the closing money line)", rows)
    report("2025-26, regular season only", [r for r in rows if r[3] == "Main"])

    rd = lambda f: (lambda t: json.loads(t[t.index("{"):t.rindex("}") + 1]))((cm.SITE / f).read_text(encoding="utf-8"))
    res = {(g["h"], g["a"]): g["hp"] - g["ap"] for g in cm.games if cm.seasons[g["season"]] == "2026-2027"}
    live = [(g["mh"], g["bh"], res[(g["h"], g["a"])], "Main") for sn in rd("archive.js")["list"] for g in sn["games"]
            if g.get("bh") is not None and (g["h"], g["a"]) in res]
    if live:
        report("2026-27 so far, Archive (real handicap lines; model as frozen before the game)", live)


if __name__ == "__main__":
    main()
