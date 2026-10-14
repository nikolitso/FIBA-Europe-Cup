"""One-step updater for the FIBA Europe Cup site.

    python update.py             # results + odds + fixtures from BetExplorer, then publish
    python update.py --no-push   # update the files only, do not commit or push

Steps
  1. results  - 2026-27 games on BetExplorer's results pages  -> fibaeuropecup/data.js          (update_site.py)
  2. odds     - handicap / total / money line, next round     -> fibaeuropecup/odds.js          (update_site.py;
                Stake.com, else bwin, else Betsson)
  3. fixtures - upcoming games and kick-off times (Athens)    -> fibaeuropecup/fixtures.js
  4. publish  - commit and push the three files in the website repo, mirror them into this repo's site/ and push

Nothing is written or published if BetExplorer blocks the request (it is unavailable in some countries): run it
again later. The Archive tab (frozen projections) is not touched here; its results fill in by themselves.
"""
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

import update_site

HERE = Path(__file__).parent
SITE = update_site.SITE                                   # website repo folder: nikolitso.github.io/fibaeuropecup
WEBSITE_REPO = SITE.parent
FILES = ["data.js", "fixtures.js", "odds.js"]
COMP = update_site.COMP
STRIP_W = False                                           # the women's site strips BetExplorer's trailing " W"
H = {"User-Agent": "Mozilla/5.0"}
BE_TZ = timezone(timedelta(hours=1))                      # BetExplorer shows UTC+1; checked against Flashscore times
ATHENS = ZoneInfo("Europe/Athens")

# BetExplorer limits fast clients (HTTP 429): keep at least 2 s between requests and back off when it says slow down
_real_get, _last = requests.get, [0.0]


def _polite_get(url, **kw):
    for wait in (0, 30, 60, 120):
        time.sleep(wait)
        time.sleep(max(0.0, 2.0 - (time.time() - _last[0])))
        r = _real_get(url, **kw)
        _last[0] = time.time()
        if r.status_code != 429:
            return r
        print("  BetExplorer says slow down (429): waiting before retrying ...")
    return r


requests.get = _polite_get


def update_fixtures():
    r = requests.get(update_site.BASE + COMP + "fixtures/", headers=H, timeout=30)
    r.raise_for_status()
    if "unavailable in" in r.text[:2000] or r.url.endswith(".html"):
        raise SystemExit(f"BetExplorer blocked the request ({r.url}); nothing written.")
    soup = BeautifulSoup(r.text, "html.parser")
    today = datetime.now(ATHENS).date()
    rows, hdr = [], ""
    for tr in soup.select("table.table-main tr"):
        th = tr.find("th")
        if th:
            hdr = th.get_text(" ", strip=True)
            continue
        a = tr.select_one("a.in-match")
        t = tr.select_one("td.table-main__datetime")
        m = re.match(r"(?:(Today|Tomorrow)|(\d\d)\.(\d\d)\.)\s+(\d\d):(\d\d)", t.get_text(strip=True)) if t else None
        if not (a and m):                                 # no kick-off time yet
            continue
        if m[1]:
            d = today + timedelta(days=1 if m[1] == "Tomorrow" else 0)
        else:
            d = datetime(today.year, int(m[3]), int(m[2])).date()
            if d < today - timedelta(days=30):
                d = d.replace(year=d.year + 1)
        when = datetime(d.year, d.month, d.day, int(m[4]), int(m[5]), tzinfo=BE_TZ).astimezone(ATHENS)
        sp = [s.get_text(strip=True) for s in a.find_all("span")]
        if STRIP_W:
            sp = [re.sub(r" W$", "", x) for x in sp]
        n = re.search(r"(\d+)\. Round", hdr)
        rows.append([when.strftime("%Y-%m-%d %H:%M"), f"Round {n[1]}" if n else hdr.title(), sp[0], sp[1]])
    if not rows:
        raise SystemExit("No fixtures with a kick-off time found; fixtures.js left untouched.")
    rows.sort()
    path = SITE / "fixtures.js"
    old = len(update_site.read_js(path)[1]["list"]) if path.exists() else 0
    path.write_text("// Upcoming fixtures (Athens time): [when, round, home, away]. Source: BetExplorer.\n"
                    "window.FIXTURES = " + json.dumps({"updated": today.isoformat(), "source": "BetExplorer", "list": rows},
                                                     ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"fixtures: {len(rows)} upcoming games (was {old}), next: {rows[0][0]} {rows[0][2]} - {rows[0][3]}")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")


def publish(repo, paths, message):
    git(repo, "add", *paths)
    if git(repo, "diff", "--cached", "--quiet", "--", *paths).returncode == 0:
        print(f"  {repo.name}: nothing new to publish")
        return
    c = git(repo, "commit", "-m", message, "--", *paths)
    if c.returncode:
        raise SystemExit(f"commit failed in {repo}: {c.stdout}{c.stderr}")
    p = git(repo, "push")
    if p.returncode:                                      # the remote moved on: rebase our commit and try again
        git(repo, "pull", "--rebase", "--autostash")
        p = git(repo, "push")
    if p.returncode:
        raise SystemExit(f"push failed in {repo}: {p.stdout}{p.stderr}")
    print(f"  {repo.name}: published")


def mirror_and_publish(label, subfolder, message):
    print("publishing:")
    publish(WEBSITE_REPO, [f"{subfolder}/{f}" for f in FILES], message)
    for f in FILES:
        shutil.copy2(SITE / f, HERE / "site" / f)
    publish(HERE, [f"site/{f}" for f in FILES], f"Mirror live site data ({label})")


def main():
    push = "--no-push" not in sys.argv
    try:
        update_site.update_results()
        update_site.update_odds()
        update_fixtures()
    except (SystemExit, requests.RequestException) as e:   # blocked, rate-limited or offline: stop cleanly
        print(e)
        print("Nothing was published. BetExplorer may be blocking or limiting requests: try again in a few minutes.")
        sys.exit(1)
    if push:
        mirror_and_publish("FIBA Europe Cup", "fibaeuropecup", f"FIBA Europe Cup: update results, odds and fixtures ({time.strftime('%Y-%m-%d %H:%M')})")
    print("done")


if __name__ == "__main__":
    main()
