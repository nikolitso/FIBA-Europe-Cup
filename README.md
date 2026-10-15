# FIBA-Europe-Cup

Match results for the FIBA Europe Cup, 2021-22 to 2026-27 (in progress), with head-to-head tables by team and by country.

| File | Contents |
|---|---|
| `data/matches.csv` | Every match: season, stage, round, date, teams, points, status (FT / AET / AWA. / CAN.) |
| `data/teams.csv` | Team to country mapping (hand-editable) |
| `data/h2h_teams.csv` | Head-to-head record for each pair of teams |
| `data/h2h_countries.csv` | Head-to-head record for each pair of countries (cross-border games only) |

## Rebuild

```
pip install -r requirements.txt
python scrape.py        # results from BetExplorer, all stages
python build_teams.py   # fills in countries for any new teams
python h2h.py           # H2H tables
```

Cancelled games are ignored. Awarded games count as a win with no points.
Results source: BetExplorer.

## Site

`site/` mirrors the live front end (https://antonisnikolitsopoulos.com/fibaeuropecup/), which is served from the `fibaeuropecup/` folder of the website repo. `site/data.js` there covers 2015-16 onwards, so it is no longer produced by `build_site.py` alone. `site/odds.js` holds the bookmaker lines used by the Projections comparison.

### Archive

`site/archive.js` holds one frozen entry per round (model and bookmaker total / handicap, written before the games). To add a round: update `odds.js`, open the Projections tab with the settings to freeze, run `makeSnapshot('YYYY-MM-DD')` in the browser console and add the returned JSON to `archive.js`. Results appear on the Archive tab by themselves once the games are in `data.js`.

## Updating results and odds

```
python update_site.py            # results + odds
python update_site.py results
python update_site.py odds
```

Reads BetExplorer: for the next round on the fixtures page it writes the handicap, total and money line (Stake.com first, then bwin, then Betsson) to `odds.js`. Its `results` step (BetExplorer) is no longer used by `update.py`, which reads results from Flashscore instead. It stops without writing anything if BetExplorer blocks the request (the site is unavailable in some countries).

## One-step update

```
python update.py            # results from Flashscore, odds + fixtures from BetExplorer, then publish
python update.py --no-push  # update the files only
```

Or double-click `Update FIBA Europe Cup.bat` on the Desktop. Results come from Flashscore (`flashscore_results.py`, a headless Chromium via Playwright: `pip install playwright` and `python -m playwright install chromium` once); new games are added, existing rows are never changed. Odds (`update_site.py`) and `fixtures.js` come from BetExplorer and are skipped, keeping the old files, if BetExplorer is blocked. It then commits and pushes the three files in the website repo and mirrors them into `site/` here. It keeps at least 2 s between requests and backs off when BetExplorer answers 429; if it blocks the request nothing is changed.

## Rosters and absences

- `site/rosters.js`: player impact per club (points the side loses without the player), computed from this season's
  FIBA box scores: `impact = min(10, max(0, (EFF/min - 0.25) x minutes per team game) x 0.5 x g/(g+1))`, top 8 per club.
  FIBA blocks headless browsers, so box scores are read through a normal browser session and the file is rewritten
  after each round.
- `site/injuries.js`: players out for the next round, `{"team": ..., "player": ..., "note": ...}` (optional `"impact"`
  for players not in rosters.js). Each listed player moves the model handicap by their impact against their club.

## Club budgets (private)

`data/budgets.csv`: one row per club this season with a budget tier, the figure where one is published, its season,
kind, confidence and source. Tiers: **A** EUR 4m+, **B** EUR 1.5-4m, **C** under EUR 1.5m. `tier_basis` says whether a
tier comes from a published figure or is an estimate still to be confirmed. Only 7 of 50 clubs have a published figure
(searched October 2026); the rest are estimates. Not used by the model yet.
