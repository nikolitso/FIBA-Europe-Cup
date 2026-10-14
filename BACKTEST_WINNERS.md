# Picking winners: model vs bookmaker (2025-26)

`python backtest_winners.py` tunes the model on results only (2018-19 to 2024-25, 27 setting combinations x 13
weightings, every game projected from earlier games), then tests on 2025-26 against OddsPortal closing odds
(`data/oddsportal/2025-2026.txt`, 144 games with odds; the bookmaker's pick is the side with the lower odds).
OddsPortal shows no odds for earlier seasons from Greece, so the bookmaker can only be compared on 2025-26.

| 2025-26, same games | Model picked the winner | Bookmaker's favourite won |
|---|---|---|
| Tuned on 2018-19 to 2024-25 (nn 1, 3 seasons, half-life 1 year, Elo weight 0.5) | 64.2% of 123 | 74.0% |
| The site's current model (nn 2, 5 seasons, half-life 18 months, Elo weight 0.5) | 66.7% of 135 | 76.3% |
| Best setting chosen with hindsight on 2025-26 itself (not a fair test) | 71.2% of 132 | 75.8% |

When the model and the bookmaker picked different winners (22-23 games), the bookmaker was right 17-18 times.

Conclusion: on results and country/club ratings alone the model picks the winner about 10 points less often than
the bookmaker, and even settings fitted to 2025-26 after the fact stay about 5 points behind. Its disagreements with
the market are mostly wrong, so they are not a signal to follow.
