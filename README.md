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
