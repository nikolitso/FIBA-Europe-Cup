"""Build head-to-head tables from data/matches.csv + data/teams.csv.

Outputs (data/):  h2h_teams.csv, h2h_countries.csv
Rules: cancelled games are ignored; awarded games (AWA.) count as a win but add
no points; matches between two teams of the same country are skipped in the
country table.
"""
import csv
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).parent / "data"


def load():
    matches = list(csv.DictReader((DATA / "matches.csv").open(encoding="utf-8")))
    country = {r["team"]: r["country"] for r in csv.DictReader((DATA / "teams.csv").open(encoding="utf-8"))}
    return [m for m in matches if m["status"] in ("FT", "AET", "AWA.")], country


def tally(matches, key):
    t = defaultdict(lambda: [0, 0, 0, 0, 0])  # played, a_wins, b_wins, a_pts, b_pts
    for m in matches:
        a, b = key(m["home"]), key(m["away"])
        if a == b:
            continue
        hp, ap = int(m["home_pts"]), int(m["away_pts"])
        home_won = hp > ap
        if m["status"] == "AWA.":
            hp = ap = 0
        if a > b:  # canonical order so each pairing has one row
            a, b, hp, ap, home_won = b, a, ap, hp, not home_won
        r = t[(a, b)]
        r[0] += 1
        r[1 if home_won else 2] += 1
        r[3] += hp
        r[4] += ap
    return t


def write(name, cols, t):
    rows = sorted(t.items(), key=lambda kv: (-kv[1][0], kv[0]))
    with (DATA / name).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols + ["played", "a_wins", "b_wins", "a_points", "b_points"])
        for (a, b), r in rows:
            w.writerow([a, b, *r])
    print(f"{name}: {len(rows)} pairings")


def main():
    matches, country = load()
    write("h2h_teams.csv", ["team_a", "team_b"], tally(matches, lambda x: x))
    write("h2h_countries.csv", ["country_a", "country_b"], tally(matches, lambda x: country[x]))


if __name__ == "__main__":
    main()
