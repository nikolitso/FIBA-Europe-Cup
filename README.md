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

Reads BetExplorer: results for the current season replace the 2026-27 rows in the site's `data.js`; for the next round on the fixtures page it writes the handicap, total and money line (Stake.com first, then bwin, then Betsson) to `odds.js`. It stops without writing anything if BetExplorer blocks the request (the site is unavailable in some countries). Then commit and push the site repo's `fibaeuropecup/` folder. `fixtures.js` (the match list and kick-off times) still comes from Flashscore.

## One-step update

```
python update.py            # results + odds + fixtures from BetExplorer, then publish
python update.py --no-push  # update the files only
```

Or double-click `Update FIBA Europe Cup.bat` on the Desktop. It runs `update_site.py` (results, odds) and refreshes `fixtures.js`, then commits and pushes the three files in the website repo and mirrors them into `site/` here. It keeps at least 2 s between requests and backs off when BetExplorer answers 429; if it blocks the request nothing is changed.
