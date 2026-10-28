"""Matchday odds from Flashscore for today's FIBA Europe Cup games, then projections, Archive and publish.

    python matchday_odds.py            # only games of today (Athens) without a line, not yet started
    python matchday_odds.py --all      # every upcoming game on the Flashscore fixtures page without a line

Run every hour from 10:00 to 21:00 by the Windows task "FIBA Europe Cup odds" (scheduled_odds.bat): lines appear on
the morning of the match day, so the 10:00 run usually finds them. The run in the last LATE minutes before a game reads
its line again: the Archive keeps that late line and the first one, so line movement can be measured.
Bookmaker: Bwin.gr, else Stoiximan.gr, PameStoixima, Novibet, Interwetten (bet365 left out: it quotes 1.83 / 1.83 on
every line). Of that bookmaker's lines the main one is the one with the most even pair of odds.
odds.js keeps the site format: sp = handicap on the home side (+ = home underdog), tot = total, ml = money line.
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from flashscore_results import ALIASES

HERE = Path(__file__).parent
SITE = Path(os.environ.get("FIBA_SITE", r"C:\Users\antonis\Desktop\nikolitso.github.io\fibaeuropecup"))   # FIBA_SITE: set by the GitHub job
FIXTURES_URL = "https://www.flashscore.com/basketball/europe/fiba-europe-cup/fixtures/"
BOOKS = ["Bwin.gr", "Stoiximan.gr", "PameStoixima", "Novibet", "Interwetten"]
ATHENS = ZoneInfo("Europe/Athens")
LATE = 90          # minutes: games starting this soon get their line read again (the Archive keeps the first one too)
ROWS = r"""() => [...document.querySelectorAll('.ui-table__row')].map(r => [r.querySelector('img')?.alt || r.querySelector('a[title]')?.title || '', ...r.innerText.split('\n').map(x => x.trim()).filter(Boolean)])"""
LINKS = r"""() => [...document.querySelectorAll('.event__match')].map(e => {
  const a = e.querySelector('a')?.href || '', m = a.match(/match\/basketball\/([^?]+)\/\?mid=(\w+)/);
  return [e.querySelector('.event__homeParticipant, .event__participant--home')?.innerText.trim(),
          e.querySelector('.event__awayParticipant, .event__participant--away')?.innerText.trim(), m ? m[1] : '', m ? m[2] : '']; })"""


def read_js(path):
    s = path.read_text(encoding="utf-8")
    return json.loads(s[s.index("{"):s.rindex("}") + 1])


def num(x):
    try:
        return float(x.replace("+", ""))
    except (ValueError, AttributeError):
        return None


def pick(rows, line):
    """rows: [book, cells...] -> (book, line, o1, o2) for a line market, (book, o1, o2) for the money line"""
    for book in BOOKS:
        got = []
        for r in rows:
            if r[0] != book:
                continue
            v = [num(x) for x in r[1:4 if line else 3]]
            if None not in v and len(v) == (3 if line else 2):
                got.append(v)
        if got:
            v = min(got, key=lambda v: abs(v[1] - v[2])) if line else got[0]
            return (book, *v)
    return None


def rows(page, url):
    for _ in range(3):
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_selector(".ui-table__row", timeout=12000)
        except Exception:
            continue
        page.wait_for_timeout(800)
        return page.evaluate(ROWS)
    return []


def main():
    now = datetime.now(ATHENS)
    stamp, today = now.strftime("%Y-%m-%d %H:%M"), now.strftime("%Y-%m-%d")
    odds_path = SITE / "odds.js"
    odds = read_js(odds_path)
    have = {(o["h"], o["a"]) for o in odds["list"] if not o.get("implied")}   # a handicap implied from a money line is replaced
    fx = [f for f in read_js(SITE / "fixtures.js")["list"] if f[0] > stamp and ("--all" in sys.argv or f[0][:10] == today)]
    soon = lambda f: (datetime.strptime(f[0], "%Y-%m-%d %H:%M").replace(tzinfo=ATHENS) - now).total_seconds() <= LATE * 60
    missing = [(f[2], f[3]) for f in fx if (f[2], f[3]) not in have or soon(f)]    # no line yet, or the late re-read
    if not fx:
        print(f"{stamp}: no FIBA Europe Cup game left today; nothing to do")
        return 0
    if not missing:
        print(f"{stamp}: all {len(fx)} games of today already have a line; nothing to do")
        return 0
    print(f"{stamp}: {len(missing)} games without a line or close to tip-off, reading Flashscore")
    found = []
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page(locale="en-GB", timezone_id="Europe/Athens")
        pg.goto(FIXTURES_URL, wait_until="domcontentloaded", timeout=60000)
        try:
            pg.wait_for_selector(".event__match", timeout=20000)
        except Exception:
            pass
        al = lambda t: ALIASES.get(t, t)
        links = {(al(h), al(a)): (b, m) for h, a, b, m in pg.evaluate(LINKS) if b}
        for h, a in missing:
            if (h, a) not in links:
                print(f"  {h} - {a}: not on the Flashscore fixtures page")
                continue
            base, mid = links[(h, a)]
            root = f"https://www.flashscore.com/match/basketball/{base}/odds/"
            hc = pick(rows(pg, root + f"asian-handicap/ft-including-ot/?mid={mid}"), True)
            if not hc:
                print(f"  {h} - {a}: no line yet")
                continue
            ou = pick(rows(pg, root + f"over-under/ft-including-ot/?mid={mid}"), True)
            ml = pick(rows(pg, root + f"home-away/ft-including-ot/?mid={mid}"), False)
            found.append({"h": h, "a": a, "sp": hc[1], "spH": hc[2], "spA": hc[3],
                          "tot": ou[1] if ou else None, "ov": ou[2] if ou else None, "un": ou[3] if ou else None,
                          "mlH": ml[1] if ml else None, "mlA": ml[2] if ml else None})   # no bookmaker names on the site
            print(f"  {h} - {a}: hcp {hc[1]:+} ({hc[0]}), total {ou[1] if ou else '-'}")
        br.close()
    if not found:
        print("no new lines; nothing published")
        return 0
    keep = [o for o in odds["list"] if (o["h"], o["a"]) not in {(x["h"], x["a"]) for x in found}]
    odds["list"] = keep + found
    for o in odds["list"]:
        o.pop("src", None)
    odds["updated"], odds["source"] = today, "pre-game lines, earlier ones kept"
    head = odds_path.read_text(encoding="utf-8").split("window.ODDS")[0]
    head = "".join(l for l in head.splitlines(True) if not l.startswith("// src ")).replace(" from BetExplorer (Stake.com, else bwin, else Betsson)", "")
    odds_path.write_text(head + 'window.ODDS = {' + json.dumps({k: v for k, v in odds.items() if k != "list"}, ensure_ascii=False)[1:-1]
                         + ', "list": [\n  ' + ",\n  ".join(json.dumps(o, ensure_ascii=False) for o in odds["list"]) + "\n]};\n", encoding="utf-8")
    print(f"odds.js: {len(found)} lines added")
    if subprocess.run([sys.executable, str(HERE / "predict.py")], cwd=HERE).returncode:
        print("predict.py failed; odds.js written but not published")
        return 1
    import update                                         # publish site files and mirror them to this repo
    update.mirror_and_publish("FIBA Europe Cup", "fibaeuropecup", f"FIBA Europe Cup: matchday lines ({stamp})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
