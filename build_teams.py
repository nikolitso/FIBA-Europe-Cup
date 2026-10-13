"""Build data/teams.csv (team -> country) from BetExplorer team pages.

Country = most common domestic-league country on the team's page (international
competitions are ignored). Edit data/teams.csv by hand to fix any mistakes;
teams already in the file keep their country on re-runs.
"""
import csv
import re
import time
from collections import Counter
from pathlib import Path

import requests

BASE = "https://www.betexplorer.com"
DATA = Path(__file__).parent / "data"
HEADERS = {"User-Agent": "Mozilla/5.0"}
INTERNATIONAL = {"Europe", "World", "Club Friendly"}


def fetch(url):
    time.sleep(0.4)
    r = requests.get(BASE + url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def main():
    matches = list(csv.DictReader((DATA / "matches.csv").open(encoding="utf-8")))
    sample = {}  # team -> a match url where it appears
    for m in matches:
        for t in (m["home"], m["away"]):
            sample.setdefault(t, m)

    existing = {}
    path = DATA / "teams.csv"
    if path.exists():
        existing = {r["team"]: r for r in csv.DictReader(path.open(encoding="utf-8"))}

    rows = []
    for team in sorted(sample):
        if team in existing and existing[team]["country"]:
            rows.append(existing[team])
            continue
        m = sample[team]
        html = fetch(f"/basketball/europe/{'fiba-europe-cup' if m['season']=='2026-2027' else 'fiba-europe-cup-'+m['season']}/x/{m['match_id']}/")
        links = re.findall(r'href="(/basketball/team/[^"]+)"', html)
        # first link is home team, second is away
        url = links[0] if team == m["home"] else links[-1]
        page = fetch(url)
        countries = re.findall(r'<img src="https://cci\.betexplorer\.com/[^"]+" alt="([^"]+)"></i>', page)
        c = Counter(x for x in countries if x not in INTERNATIONAL)
        country = c.most_common(1)[0][0] if c else ""
        rows.append({"team": team, "country": country, "betexplorer_url": url})
        print(f"{team:28} {country}")

    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["team", "country", "betexplorer_url"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} teams -> {path}")


if __name__ == "__main__":
    main()
