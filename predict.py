"""Live FIBA Europe Cup projections -> site projections.js, and the Archive (archive.js) frozen from them.

    python predict.py

Model: club_model.py (the EuroCup page's club-rating model) with the settings tuned in its backtest. Upcoming games
come from fixtures.js; absences from injuries.js, each player worth his impact from rosters.js (or the entry's own
"impact"). Only the week (Monday to Sunday) of the next game is projected, as on the EuroCup page.

Archive: every upcoming game with a bookmaker line (odds.js) is (re)written into archive.js on every run until its
tip-off and never after, so the Archive keeps model and line as they stood before the game. Entries made by the
earlier model (model "mix", frozen from the Projections tab) are never touched.
"""
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import club_model as cm

SITE = Path(r"C:\Users\antonis\Desktop\nikolitso.github.io\fibaeuropecup")
PARAMS = {"half": 480, "k": 4.0, "keep": 0.85, "new": 1.0}   # club_model.py backtest, tuned on 2023-24 and 2024-25
SPREAD = 14.9                       # RMSE of the model's misses in that backtest: win chance = phi(handicap / SPREAD)
SEASON = "2026-2027"
ATHENS = ZoneInfo("Europe/Athens")


def read_js(path):
    s = path.read_text(encoding="utf-8")
    return json.loads(s[s.index("{"):s.rindex("}") + 1])


def write_js(path, comment, var, obj, one_per_line=None):
    body = json.dumps(obj, ensure_ascii=False)
    if one_per_line:                                   # one archive day per line, readable in a diff
        body = '{"list": [\n' + ",\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in obj["list"]) + "\n]}"
    path.write_text(comment + f"window.{var} = " + body + ";\n", encoding="utf-8")


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def absences(club, out, rosters):
    imp = {p[0]: p[1] for p in rosters.get(club, [])}
    return [[x["player"], round(x.get("impact", imp.get(x["player"], 0.0)), 1), x.get("note", "")] for x in out if x["team"] == club]


def main():
    now = datetime.now(ATHENS)
    today, stamp = now.date(), now.strftime("%Y-%m-%d %H:%M")
    si = cm.seasons.index(SEASON)
    S = cm.Season(cm.games, si, PARAMS)
    played = [g for g in S.cur if g["day"] <= today]
    ratings = cm.ridge_margin(played, S.pr, PARAMS["k"], PARAMS["half"], today, S.hca) if played else S.pr
    mu = (S.mu0 * 60 + sum(g["hp"] + g["ap"] for g in played)) / (60 + len(played))
    totals = cm.ridge_total(played, S.pt, PARAMS["k"], PARAMS["half"], today, mu) if played else S.pt
    injuries = read_js(SITE / "injuries.js").get("out", [])
    rosters = read_js(SITE / "rosters.js")["teams"]
    fx = [f for f in read_js(SITE / "fixtures.js")["list"] if f[0] > stamp]
    if fx:                                                # only the week (Monday to Sunday) of the next game
        first = date.fromisoformat(fx[0][0][:10])
        monday = first - timedelta(days=first.weekday())
        fx = [f for f in fx if (date.fromisoformat(f[0][:10]) - monday).days <= 6]
    rate = lambda c: ratings.get(c, S.pr.get(c, 0.0))
    rows = []
    for when, rnd, h, a in fx:
        oh, oa = absences(h, injuries, rosters), absences(a, injuries, rosters)
        adj = sum(x[1] for x in oa) - sum(x[1] for x in oh)           # missing players cost their side points
        mh = S.hca + rate(h) - rate(a) + adj
        mt = mu + totals.get(h, 0.0) + totals.get(a, 0.0)
        rows.append({"when": when, "round": rnd, "h": h, "a": a, "mh": round(mh, 1), "mt": round(mt, 1),
                     "ph": round(phi(mh / SPREAD), 3), "rh": round(rate(h), 1), "ra": round(rate(a), 1),
                     "adj": round(adj, 1), "outH": oh, "outA": oa})
    count = lambda c: sum(1 for g in played if c in (g["h"], g["a"]))
    main_clubs = {c for g in S.cur if g["stage"] == "Main" for c in (g["h"], g["a"])}   # Regular Season clubs only
    table = sorted(({"c": c, "r": round(rate(c), 1), "prior": round(S.pr.get(c, 0.0), 1), "g": count(c)}
                    for c in main_clubs), key=lambda x: -x["r"])
    write_js(SITE / "projections.js",
             "// Model projections for the next games (predict.py, club-rating model): results + absences, independent of the bookmaker.\n"
             "// mh = handicap home minus away, mt = total, ph = home win chance, rh / ra = club ratings, adj = absences, outH / outA = [player, impact, note].\n",
             "PROJ", {"updated": stamp, "hca": round(S.hca, 1), "spread": SPREAD, "games": len(played), "params": PARAMS,
                      "list": rows, "ratings": table})
    print(f"projections.js: {len(rows)} games, home advantage {S.hca:.1f}, {len(table)} clubs rated")
    freeze(rows, stamp, len(played))


def freeze(rows, stamp, n_games):
    path = SITE / "archive.js"
    arch = read_js(path)
    odds = {(o["h"], o["a"]): o for o in read_js(SITE / "odds.js")["list"]}
    snaps = {sn["date"]: sn for sn in arch["list"]}
    n = 0
    for r in rows:
        o = odds.get((r["h"], r["a"]))
        if not o or r["when"] <= stamp:                     # no line yet, or already started: leave as it is
            continue
        day = r["when"][:10]
        sn = snaps.setdefault(day, {"date": day, "round": r["round"], "taken": stamp[:10],
                                    "sample": "club-rating model (results + absences)", "games": []})
        old = next((g for g in sn["games"] if g["h"] == r["h"] and g["a"] == r["a"]), None)
        if old and old.get("model") != "club":              # frozen by the earlier model: never touched
            continue
        entry = {"when": r["when"][11:], "h": r["h"], "a": r["a"], "model": "club", "mh": r["mh"], "mt": r["mt"],
                 "adj": r["adj"], "out": [[r["h"]] + x for x in r["outH"]] + [[r["a"]] + x for x in r["outA"]],
                 "pH": r["ph"], "n": n_games, "bh": -o["sp"], "bt": o.get("tot"), "mlH": o.get("mlH"), "mlA": o.get("mlA"),
                 "src": (o.get("src") or [""])[0], "taken": stamp}
        if old:
            sn["games"][sn["games"].index(old)] = entry
        else:
            sn["games"].append(entry)
            sn["games"].sort(key=lambda g: (g["when"], g["h"]))
        n += 1
    arch["list"] = sorted(snaps.values(), key=lambda s: s["date"])
    write_js(path, "// Frozen projections vs bookmaker lines, one entry per day. Games of the club-rating model (model \"club\") are\n"
                   "// rewritten by predict.py on every update until tip-off, never after; earlier \"mix\" days were frozen from the Projections tab.\n"
                   "// mh / bh = model / book handicap home minus away, mt / bt = totals, n = games behind the projection.\n",
             "ARCHIVE", arch, one_per_line=True)
    print(f"archive.js: {n} games frozen this run")


if __name__ == "__main__":
    main()
