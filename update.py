"""One-step updater for the FIBA Europe Cup site.

    python update.py             # results, fixtures and odds (all from Flashscore), then publish
    python update.py --no-push   # update the files only, do not commit or push

Steps
  1. results  - new 2026-27 games from Flashscore (headless browser) -> fibaeuropecup/data.js  (flashscore_results.py)
  2. fixtures - upcoming games and kick-off times (Athens), Flashscore fixtures page -> fibaeuropecup/fixtures.js
  3. odds     - handicap / total / money line for every upcoming game without one -> fibaeuropecup/odds.js
                (matchday_odds.py: Bwin.gr, else Stoiximan.gr, PameStoixima, Novibet, Interwetten)
  4. publish  - commit and push the files in the website repo, mirror them into this repo's site/ and push

If the fixtures or odds step fails, that file is left as it was and the new results are still published. The Archive
tab (frozen projections) is not touched here; its results fill in by themselves.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

import flashscore_results
import matchday_odds
import update_site

HERE = Path(__file__).parent
SITE = update_site.SITE                                   # website repo folder: nikolitso.github.io/fibaeuropecup
WEBSITE_REPO = SITE.parent
FILES = ["data.js", "fixtures.js", "odds.js", "projections.js", "archive.js"]
ATHENS = ZoneInfo("Europe/Athens")
FIXTURES = r"""() => [...document.querySelectorAll('.event__round, .event__match')].map(e => e.classList.contains('event__round')
  ? [e.innerText.trim()]
  : [(e.querySelector('.event__time, .event__stageTime') || {}).innerText?.trim() || '',
     e.querySelector('.event__homeParticipant, .event__participant--home')?.innerText.trim(),
     e.querySelector('.event__awayParticipant, .event__participant--away')?.innerText.trim()])"""

SHOW_MORE = r"""() => { const b = [...document.querySelectorAll('button')].find(e => /^show more matches$/i.test(e.innerText?.trim() || ''));
  if (b) b.click(); return !!b; }"""         # clicked in the page: the cookie banner can cover it for a real click


def update_fixtures():
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page(locale="en-GB", timezone_id="Europe/Athens")   # Flashscore then shows Athens times
        pg.goto(matchday_odds.FIXTURES_URL, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_selector(".event__match", timeout=20000)
        for _ in range(10):                               # the page lists a few rounds; "Show more games" loads the rest
            n = pg.locator(".event__match").count()
            if not pg.evaluate(SHOW_MORE):
                break
            try:
                pg.wait_for_function(f"document.querySelectorAll('.event__match').length > {n}", timeout=10000)
            except Exception:
                break
        items = pg.evaluate(FIXTURES)
        br.close()
    now = datetime.now(ATHENS)
    al = lambda t: flashscore_results.ALIASES.get(t, t)
    rows, rnd = [], ""
    for it in items:
        if len(it) == 1:                                  # "ROUND 5", or a stage name
            n = re.search(r"ROUND (\d+)", it[0].upper())
            rnd = f"Round {n[1]}" if n else it[0].title()
            continue
        m = re.match(r"(\d\d)\.(\d\d)\.\s+(\d\d):(\d\d)", it[0])
        if not (m and it[1] and it[2]):                   # no kick-off time yet
            continue
        year = now.year + (1 if int(m[2]) < now.month - 6 else 0)   # the season runs into next year
        when = datetime(year, int(m[2]), int(m[1]), int(m[3]), int(m[4]))
        if when >= now.replace(tzinfo=None) - timedelta(hours=3):   # fixtures only, never a played game
            rows.append([when.strftime("%Y-%m-%d %H:%M"), rnd, al(it[1]), al(it[2])])
    if not rows:
        raise SystemExit("No fixtures with a kick-off time found; fixtures.js left untouched.")
    rows.sort()
    path = SITE / "fixtures.js"
    old = len(update_site.read_js(path)[1]["list"]) if path.exists() else 0
    path.write_text("// Upcoming fixtures (Athens time): [when, round, home, away]. Source: Flashscore.\n"
                    "window.FIXTURES = " + json.dumps({"updated": now.date().isoformat(), "source": "Flashscore", "list": rows},
                                                     ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"fixtures: {len(rows)} upcoming games (was {old}), next: {rows[0][0]} {rows[0][2]} - {rows[0][3]}")


def update_odds():
    matchday_odds.main(all_games=True, publish=False)


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
    if os.environ.get("FIBA_NO_MIRROR"):                  # the GitHub job publishes the site only
        return
    for f in FILES:
        shutil.copy2(SITE / f, HERE / "site" / f)
    publish(HERE, [f"site/{f}" for f in FILES], f"Mirror live site data ({label})")


def main():
    push = "--no-push" not in sys.argv
    try:
        flashscore_results.update()
    except SystemExit as e:                               # e.g. a new club without a country: nothing written
        print(e)
        print("Nothing was published.")
        sys.exit(1)
    for step in (update_fixtures, update_odds):            # odds read the new fixtures
        try:
            step()
        except Exception as e:                            # Flashscore slow or changed: keep the old file
            print(f"{step.__name__}: skipped ({e})")
    # club-rating projections and the Archive frozen from them; a separate process so it reads the new results
    if subprocess.run([sys.executable, str(HERE / "predict.py")], cwd=HERE).returncode:
        print("predict: failed, projections.js / archive.js left as they were")
    if push:
        mirror_and_publish("FIBA Europe Cup", "fibaeuropecup", f"FIBA Europe Cup: update results, odds and fixtures ({time.strftime('%Y-%m-%d %H:%M')})")
    print("done")


if __name__ == "__main__":
    main()
