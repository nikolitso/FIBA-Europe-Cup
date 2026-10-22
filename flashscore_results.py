"""Add new FIBA Europe Cup results from Flashscore to the site's data.js.

    python flashscore_results.py

Opens Flashscore's results page for the current season in a headless browser (Playwright + Chromium), reads every
finished game and adds the ones that are not in data.js yet. Existing rows are never changed. Round labels follow
the site's convention: regular-season games become "Group X - N. Round" (the group comes from earlier games of either
club); other stages keep Flashscore's round name. Stops without writing anything if a club has no country yet.
"""
import json
import re
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

SITE = Path(r"C:\Users\antonis\Desktop\nikolitso.github.io\fibaeuropecup")
URL = "https://www.flashscore.com/basketball/europe/fiba-europe-cup/results/"
SEASON = "2026-2027"
ALIASES = {"BC Kalev": "BC Kalev/Cramo"}          # Flashscore renamed the club; keep the name its earlier games use

# runs inside the page: one line per header / game, the same way it was read by hand in the browser
EXTRACT = r"""async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  for (let i = 0; i < 40 && !document.querySelector('.event__match'); i++) await sleep(500);
  await sleep(800);
  for (let i = 0; i < 30; i++) {
    const b = document.querySelector('button[data-testid="wcl-buttonLink"]');
    if (!b || !/show more/i.test(b.innerText)) break;
    b.click(); await sleep(1500);
  }
  const root = document.querySelector('.sportName');
  if (!root) return [];
  const out = []; let stage = '', round = '';
  for (const e of root.children) {
    if (e.className.includes('headerLeague__wrapper')) { stage = e.innerText.split('\n')[0].replace(/^FIBA Europe Cup\s*-?\s*/, '').trim() || 'Main'; continue; }
    if (e.classList.contains('event__round')) { round = e.innerText.trim(); continue; }
    if (!e.classList.contains('event__match')) continue;
    const t = e.innerText.split('\n').map(x => x.trim()).filter(Boolean);
    const q = s => e.querySelector(s)?.innerText.trim() || '';
    out.push({stage, round, when: t[0], flag: ['AOT', 'Awarded', 'Cancelled', 'Postponed', 'Abandoned'].includes(t[1]) ? t[1] : '',
              home: q('.event__homeParticipant'), away: q('.event__awayParticipant'),
              hp: q('.event__score--home'), ap: q('.event__score--away')});
  }
  return out;
}"""


def read_flashscore():
    """The page fills in with JavaScript, sometimes slowly: wait for the games and try up to three times."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        rows = []
        for attempt in range(3):
            page = browser.new_page(locale="en-GB", timezone_id="Europe/Athens")
            try:
                page.goto(URL, wait_until="domcontentloaded", timeout=60000)
                try:                                      # privacy-friendly choice on the cookie banner, if shown
                    page.click("#onetrust-reject-all-handler", timeout=4000)
                except Exception:
                    pass
                page.wait_for_selector(".event__match", timeout=30000)
                page.wait_for_timeout(1500)
                rows = page.evaluate(EXTRACT)
            except Exception as e:
                print(f"  Flashscore attempt {attempt + 1} failed: {e.__class__.__name__}")
            page.close()
            if rows:
                break
        browser.close()
    return rows


def update():
    js = (SITE / "data.js").read_text(encoding="utf-8")
    pre, data = js[:js.index("{")], json.loads(js[js.index("{"):js.rindex("}") + 1])
    rows = read_flashscore()
    if not rows:
        raise SystemExit("Flashscore returned no games; data.js left untouched.")
    cur = [m for m in data["matches"] if m[0] == SEASON]
    group = {}
    for m in cur:
        if m[1] == "Main" and m[2].startswith("Group"):
            group[m[4]] = group[m[5]] = m[2].split(" - ")[0]
    have = {(m[4], m[5]): date.fromisoformat(m[3]) for m in cur}
    start = int(SEASON[:4])
    new, unknown = [], set()
    for r in rows:
        if r["flag"] in ("Cancelled", "Postponed", "Abandoned") or not (r["hp"].isdigit() and r["ap"].isdigit()):
            continue
        m = re.match(r"(\d\d)\.(\d\d)\.(\d{4})?", r["when"])
        if not m:
            continue
        day = date(int(m[3]) if m[3] else (start if int(m[2]) >= 7 else start + 1), int(m[2]), int(m[1]))
        h, a = ALIASES.get(r["home"], r["home"]), ALIASES.get(r["away"], r["away"])
        if (h, a) in have and abs((have[(h, a)] - day).days) <= 1:
            continue                                      # already in the data
        for t in (h, a):
            if t not in data["teams"]:
                unknown.add(t)
        hp, ap = int(r["hp"]), int(r["ap"])
        status = "AWA." if r["flag"] == "Awarded" or {hp, ap} == {0, 20} else "AET" if r["flag"] == "AOT" else "FT"
        n = re.search(r"(\d+)", r["round"])
        if r["stage"] == "Main":
            g = group.get(h) or group.get(a)
            rnd = f"{g} - {n[1]}. Round" if g and n else (f"Round {n[1]}" if n else r["round"].title())
        else:
            rnd = r["round"].title()
        new.append([SEASON, r["stage"], rnd, day.isoformat(), h, a, hp, ap, status])
    if unknown:
        raise SystemExit(f"Clubs without a country in data.js: {sorted(unknown)}. Add them to teams first; nothing written.")
    if new:
        data["matches"] = data["matches"] + sorted(new, key=lambda m: m[3])
        (SITE / "data.js").write_text(pre + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"results (Flashscore): {len(rows)} games read, {len(new)} new")
    for m in new:
        print("  +", m[3], m[2], m[4], "-", m[5], f"{m[6]}-{m[7]}")
    return len(new)


if __name__ == "__main__":
    update()
