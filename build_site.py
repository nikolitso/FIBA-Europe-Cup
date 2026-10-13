"""Write site/data.js (matches + team countries) for the static front end.

Open site/index.html in a browser after running this.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"


def main():
    matches = list(csv.DictReader((DATA / "matches.csv").open(encoding="utf-8")))
    teams = {r["team"]: r["country"] for r in csv.DictReader((DATA / "teams.csv").open(encoding="utf-8"))}
    played = [
        [m["season"], m["stage"], m["round"], m["date"], m["home"], m["away"],
         int(m["home_pts"]), int(m["away_pts"]), m["status"]]
        for m in matches if m["status"] in ("FT", "AET", "AWA.")
    ]
    out = ROOT / "site" / "data.js"
    out.parent.mkdir(exist_ok=True)
    out.write_text(
        "window.DATA = " + json.dumps({"matches": played, "teams": teams}, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    print(f"{len(played)} matches, {len(teams)} teams -> {out}")


if __name__ == "__main__":
    main()
