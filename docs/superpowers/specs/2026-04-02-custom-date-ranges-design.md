# Custom Date Ranges — Design Spec

## Summary

Add a "Custom" option to the Period dropdown in the Fractal Sweep dashboard that lets the user define 1–4 date ranges, then renders a dedicated comparison view with combined + side-by-side stats, classification breakdowns, MAE/MFE distributions, and a variance comparison chart.

## Approach

Client-side only. Filter `recent_trades` from the full profile data in JS — no changes to `model_stats.py` or the JSON payload. Trade counts per model (144–2,199) are trivial for client-side computation.

## UI: Range Builder

When "Custom" is selected from the Period dropdown:

- A **range builder panel** appears between the selector bar and the tab strip
- Up to **4 range slots**, each with:
  - Start date `<input type="date">`
  - End date `<input type="date">`
  - Auto-assigned color swatch (blue, amber, purple, teal)
  - Remove button (×)
- **"+ Add Range"** button (disabled at 4 ranges)
- **"Apply"** button triggers the custom analysis render
- Ranges persist to `localStorage` key `fractal-custom-ranges`
- Switching away from "Custom" hides the builder and restores normal tab rendering

## Data Flow

1. **Source:** `recent_trades` from the full profile (`activeTF === 'all'` path). Each trade has: `date`, `direction`, `hr`, `mn`, `session`, `dow`, `entry_price`, `sweep_extreme`, `target_price`, `risk_pts`, `r`, `outcome`, `mae_pct`, `mfe_pct`, `dow_name`, `classification`

2. **Filter per range:** For each range, filter trades where `trade.date >= startDate && trade.date <= endDate`

3. **Compute stats per range** via `computeRangeStats(trades)`:
   - **Hero:** count, wins, WR, EV (avg r), PF (sum win r / sum loss |r|), CE (ev_r × pf)
   - **Risk:** max consecutive losses, max DD (sequential equity tracking with $4,500 account / $225 per trade), Sharpe (daily PnL annualized), blown flag
   - **Classification:** group by `classification`, compute WR/EV/PF per group
   - **MAE distribution:** mean, median, mode (binned at 0.01% intervals), std dev
   - **MFE distribution:** mean, median, mode (binned at 0.01% intervals), std dev
   - **By direction:** Long vs Short WR/EV

4. **Combined stats:** Merge all filtered trades into one array, run `computeRangeStats()` on the merged set

5. **Variance comparison data:** Extract per range: `{mae_median, mae_mode, mae_std, mfe_median, mfe_mode, mfe_std, mfe_mae_ratio: mfe_median / mae_median}`

## Custom Tab Layout

When Custom is active, normal tabs (Overview, Edge, Risk, MAE Study, MFE Study, Trades) are **hidden**. A single scrollable view renders vertically:

### A. Combined Hero Tiles
- One row of hero cards for the merged dataset across all ranges
- Cards: WR, EV(R), PF, CE, Total P&L, Sharpe, Max DD, Max L Run
- Subtitle: "Combined · N trades · X ranges"

### B. Side-by-Side Hero Tiles
- Each range gets a compact card row, color-coded by range swatch
- Shows: range dates, trade count, WR, EV, PF, CE, Max DD
- Layout: horizontal grid, 1 column per range (up to 4 columns)

### C. Classification Breakdown
- Table: rows = DWP, DNP, R1, R2, Unclassified
- Columns = each range + Combined
- Cells: trade count, WR, EV

### D. MAE Distribution
- One mini histogram per range (color-coded) + one "Combined" histogram
- Side by side horizontally
- Below each: mode, median, mean, std dev as stat tiles

### E. MFE Distribution
- Same layout as MAE section

### F. MAE/MFE Variance Comparison Chart
- Grouped bar chart
- X-axis: Range 1, Range 2, ..., Combined
- Three bar groups per x-position: MAE, MFE, and MFE/MAE ratio
- Bar height: mode (solid fill) and median (outline/hatched)
- Error whiskers: ±1 std dev (on MAE and MFE bars)
- MFE/MAE ratio bar: median(mfe_pct) / median(mae_pct) — higher = better entry quality relative to excursion
- Key visual for comparing entry/exit quality and efficiency across periods

## Color Assignments

| Range | Swatch | Hex |
|-------|--------|-----|
| 1 | Blue | `#3b82f6` |
| 2 | Amber | `#f59e0b` |
| 3 | Purple | `#8b5cf6` |
| 4 | Teal | `#14b8a6` |
| Combined | White/Gray | `#94a3b8` |

## Persistence

- `localStorage.getItem('fractal-custom-ranges')` → JSON array of `{start: 'YYYY-MM-DD', end: 'YYYY-MM-DD'}` objects
- On page load, if "Custom" was the last selected period (stored separately or inferred), restore the ranges and auto-apply

## Scope

- Dashboard-only change (`model_dashboard.html`)
- No changes to `model_stats.py` or `model_stats.json`
- No new dependencies
- All computation happens in the browser using existing `recent_trades` data
