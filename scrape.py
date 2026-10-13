"""Scrape FIBA Europe Cup results from BetExplorer into data/matches.csv.

Usage:  python scrape.py            (all seasons, all stages)
        python scrape.py 2023-2024  (one season)
"""
import csv
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://www.betexplorer.com"
COMPETITION = "/basketball/europe/"
SEASONS = ["2021-2022", "2022-2023", "2023-2024", "2024-2025", "2025-2026", "current"]
HEADERS = {"User-Agent": "Mozilla/5.0"}
OUT = Path(__file__).parent / "data" / "matches.csv"
FIELDS = ["season", "stage", "round", "date", "home", "away",
          "home_pts", "away_pts", "status", "match_id"]


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(0.5)
    return BeautifulSoup(r.text, "html.parser")


def slug(season):
    return "fiba-europe-cup" if season == "current" else f"fiba-europe-cup-{season}"


def stages(season):
    soup = get(f"{BASE}{COMPETITION}{slug(season)}/results/")
    seen, out = set(), []
    for a in soup.select('a[href^="?stage="]'):
        if a["href"] not in seen:
            seen.add(a["href"])
            out.append((a.get_text(strip=True), a["href"]))
    return out


def parse_score(text):
    """'78:70 AET' -> (78, 70, 'AET'); 'CAN.' -> (None, None, 'CAN.')"""
    m = re.match(r"(\d+):(\d+)\s*(.*)", text)
    if m:
        return int(m[1]), int(m[2]), m[3] or "FT"
    return None, None, text


def scrape_stage(season, stage, href):
    soup = get(f"{BASE}{COMPETITION}{slug(season)}/results/{href}")
    rows, rnd = [], ""
    for tr in soup.select("table.table-main tr"):
        th = tr.find("th")
        if th:
            rnd = th.get_text(" ", strip=True).replace(" 1 2", "")
            continue
        a = tr.select_one("a.in-match")
        if not a:
            continue
        spans = [s.get_text(strip=True) for s in a.find_all("span", recursive=False)]
        tds = tr.find_all("td")
        hp, ap, status = parse_score(tds[1].get_text(strip=True))
        parts = tds[-1].get_text(strip=True).split(".")
        if len(parts) != 3:  # unplayed fixtures show a time, not a date
            continue
        d, m, y = parts
        y = y or ("2026" if season == "current" else "")  # current season omits the year
        rows.append({
            "season": "2026-2027" if season == "current" else season,
            "stage": stage, "round": rnd, "date": f"{y}-{m}-{d}",
            "home": spans[0], "away": spans[1],
            "home_pts": hp, "away_pts": ap, "status": status,
            "match_id": a["href"].rstrip("/").split("/")[-1],
        })
    return rows


def main():
    wanted = sys.argv[1:] or SEASONS
    rows = []
    for season in wanted:
        for stage, href in stages(season):
            got = scrape_stage(season, stage, href)
            print(f"{season} {stage}: {len(got)}")
            rows += got
    OUT.parent.mkdir(exist_ok=True)
    rows.sort(key=lambda r: (r["season"], r["date"]))
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} matches -> {OUT}")


if __name__ == "__main__":
    main()
