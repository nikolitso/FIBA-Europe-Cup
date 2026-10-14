# Backtest of the projection model

`python backtest.py men|women` replays history: every group-stage game from 2018-19 (men) / 2015-16 (women) is
projected using only games played on earlier days, then compared with the real result. Errors are average misses in
points; "winner %" is how often the projected handicap picked the winner. There are no historical bookmaker
lines, so this compares model versions with each other, not with the market.

Variants: **base** league average · **site** the model on the site today · **pool** same groups, games in both
directions with home advantage removed · **rec** pool with recent games weighted more · **elo** handicap from the
country Elo gap · **club** handicap from a club-level Elo gap · **mix** average of rec and elo handicap ·
**shr20** mix handicap, total pulled toward the league average when the sample is small.

## Men: 772 games (later seasons 2022-23 to 2026-27, 466 games, not used for any choice)

| Variant | Handicap error | Total error | Winner % |
|---|---|---|---|
| base | 14.78 | 14.20 | 57.0 |
| site (today) | 13.58 | 15.53 | 65.7 |
| pool | 13.19 | 14.65 | 65.7 |
| elo | 12.84 | 14.67 | 66.3 |
| mix | 12.84 | 14.67 | 67.8 |
| shr20 | 12.84 | 14.13 | 67.8 |

## Women: 1,231 games (later seasons 2021-22 to 2026-27, 685 games)

| Variant | Handicap error | Total error | Winner % |
|---|---|---|---|
| base | 18.77 | 14.03 | 54.4 |
| site (today) | 16.24 | 14.91 | 68.2 |
| pool | 15.62 | 14.28 | 70.4 |
| elo | 15.34 | 14.27 | 71.2 |
| mix | 15.27 | 14.27 | 71.7 |
| shr20 | 15.27 | 13.84 | 71.7 |

## Findings

* The handicap side works: every variant beats the league-average baseline, and the best (mix) is about 0.7 to 1.0
  points better than the site model and picks the winner 2 to 3.5 points more often.
* The total side does not: the site's total is worse than simply using the league average (15.53 vs 14.20 men,
  14.91 vs 14.03 women), most of all when the sample has fewer than 8 games. Pulling the total toward the league
  average (shr) brings it back to the baseline, not clearly below it.
* The Elo gap is a better handicap signal than the group averages; averaging the two is best.
* Using games in both directions (pooled) gives 8+ games for 83% of men's games instead of 49%.
* Settings barely matter: places +/-1 to +/-4, 3 to 8 seasons and the recency half-life each move the handicap
  error by 0.3 points or less, so tuning them is not worth it.
* Totals come out 1 to 2 points low on average (scoring is drifting up).
