# Risk of Ruin Card — Design Spec

## Summary

Add a Monte Carlo Risk of Ruin percentage card to the Overview tab's hero metrics grid in the Fractal Sweep model dashboard.

## Calculation

- **Method**: Monte Carlo simulation (50,000 iterations)
- **Inputs per simulation**: `win_rate`, `avg_win_usd`, `avg_loss_usd`, `account_size` from the active profile's `risk_stats` and `meta`
- **Sequence length**: The profile's actual trade count (`risk_stats.trades`)
- **Ruin condition**: Equity reaches $0
- **Result**: `RoR% = (ruined simulations / 50,000) * 100`

Each simulation:
1. Start with `account_size`
2. For each trade in the sequence, generate a random number. If < `win_rate`, add `avg_win_usd`; otherwise subtract `avg_loss_usd`
3. If equity <= 0 at any point, mark as ruined and stop that simulation

## Caching

Cache the computed RoR keyed by `${fullKey}_${activeProfile}_${activeTF}` so switching tabs doesn't retrigger 50k simulations. Invalidate on any dropdown change that alters the underlying data.

## Card Presentation

- **Label**: "Risk of Ruin"
- **Value**: Percentage with 1 decimal (e.g., "0.3%"), or "<0.1%" when non-zero but rounds to 0, or "0%" when truly zero
- **Subtitle**: "50k MC sims"
- **Color thresholds**: green < 1%, amber 1-5%, red > 5%
- **Placement**: Immediately after the existing "Blown" card in the hero metrics grid
- **Styling**: Identical to all other hero cards (same CSS class, same font hierarchy)

## Scope

- Dashboard-only change (`model_dashboard.html`)
- No changes to `model_stats.py` or `model_stats.json`
- No new dependencies
