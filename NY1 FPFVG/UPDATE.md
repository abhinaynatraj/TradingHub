# NY1 F.P.FVG — Update Notes
**2026-03-28**

---

## What Changed

### 1. Exit Model — Split-Exit (Open Run → TP1 + Runner)

The model previously ran all trades to EOD with no take-profit. It now uses a **split-exit**:

| Leg | Size | Exit condition |
|---|---|---|
| TP1 | 50% | 0.10% (10 bps) in trade's favour |
| Runner | 50% | Stop moves to **breakeven** (entry) after TP1; holds to structural stop or 16:00 ET |

**If TP1 is never reached** — full position exits at the structural stop (−1R, same as before).

**Exit labels:**
- `WIN` — TP1 was hit (runner may close at BE or EOD)
- `LOSS` — structural stop hit before TP1

**Results (NQ, all history — 2,717 trades):**

| | |
|---|---|
| TP1 hit rate | **56.0%** |
| Avg win | **+$127.54** |
| Avg loss | **−$224.37** |

---

### 2. MFE Study — PhD-Level Analysis

Full distributional study on Max Favourable Excursion across all resolved trades.

**Key stats:**

| Metric | Value |
|---|---|
| Mean MFE | 0.3798% |
| Median MFE | 0.1574% |
| Mode MFE | 0.0758% |
| Std Dev | 0.5882% |
| Skewness | 5.45 (heavy right tail) |
| Log-normal goodness (r) | 0.9825 |

**Natural clusters (p33 / p75 breakpoints):**

| Cluster | Range | Trades | Share |
|---|---|---|---|
| Small | 0 – 0.0979% | 897 | 33% |
| Moderate | 0.0979% – 0.4283% | 1,140 | 42% |
| Large | 0.4283%+ | 680 | 25% |

**Breakeven (Protect the Queen) analysis:**

Each MFE trigger level was evaluated for: reach rate, P(positive exit | MFE ≥ X), trades rescued, and EV improvement.

> PTQ selection: highest reach_rate trigger where P(positive exit) ≥ 70% (fallback 50%). Prioritizes practical reach — a level most trades actually hit — over extreme confidence at rarely-reached levels.

---

### 3. MAE Study — PhD-Level Analysis

Full distributional study on Max Adverse Excursion across all resolved trades.

**Key stats:**

| Metric | Value |
|---|---|
| Mean MAE | 0.1698% |
| Median MAE | 0.1427% |
| Mode MAE | 0.1310% |
| Std Dev | 0.1311% |
| Skewness | 10.34 (heavy right tail) |
| Log-normal goodness (r) | 0.9615 |

**Natural clusters (p33 / p75 breakpoints):**

| Cluster | Range | Trades | Share |
|---|---|---|---|
| Tight | 0 – 0.1111% | 897 | 33% |
| Moderate | 0.1111% – 0.2102% | 1,139 | 42% |
| Wide | 0.2102%+ | 681 | 25% |

**SL sweep analysis:**

For each MAE level tested, the sweep measures P(false stop) — trades that touch the level but still recover to hit TP1.

> Optimal SL (opt_sl) selection: tightest MAE threshold where P(genuine loss | MAE ≥ X) ≥ 70% (fallback 50%). Returns None for winners-only data (p_ko=0) — use p90 percentile instead.
> **Conclusion: the structural stop is the natural boundary.** Any fixed % SL tighter than the structural stop cuts a large proportion of legitimate winners.

---

### 4. Dashboard Updates

- **TP1 Rate** hero tile (green ≥ 55%) replaces EOD Rate
- **Exit rules** card updated to describe split-exit model
- **Trades table** — WIN / LOSS badges based on TP1 hit
- **MFE section** rebuilt: stat tiles · histogram · log-normal fit · cluster cards · full percentile table · BE trigger table · Protect the Queen box (♛)
- **MAE section** rebuilt: stat tiles · histogram · log-normal fit · cluster cards · full percentile table · SL sweep table · Stop Loss Insight box (🛡)

---

### 5. Tab Navigation

The single long-scroll page has been replaced with a **5-tab layout**:

| Tab | Content |
|---|---|
| Overview | Hero stats · How It Works |
| Performance | Direction split · DOW/Hour charts · Quarter · Year table · Month chart · Equity curve |
| MFE Study | Full MFE distribution analysis |
| MAE Study | Full MAE distribution analysis |
| Trades | Last 40 trades log |

- Tab buttons sit in the sticky nav bar — no page scrolling required
- Switching tabs scrolls to top and re-renders any canvases that need sizing
- Timeframe selector stays visible across all tabs

---

### 6. Trades Table — TP1 Price Column
**2026-03-28**

A **TP1 $** column has been added to the recent trades table:

- **WIN trades** (TP1+EOD / TP1+STOP): TP1 price shown in green
- **LOSS trades** (STOPPED): TP1 target price shown in faint gray, with a thin progress bar beneath it indicating how far MFE got toward the 0.10% target (turns orange at ≥70%)

---

### 7. Hub Page — Text Fixes
**2026-03-28**

Fixed stale/incorrect text on the Statistic.ally hub page (`index.html`):

- Expanded abbreviation: "First Presented FVG" → **"First Presented Fair Value Gap"**
- Fixed typo: "TP1 (POTQ)" → **"TP1 (PTQ)"**
- Updated position split: "80% / Runner 20%" → **"50% / Runner 50%"** to match current model
- Updated subtitle: "Fixed % Stop" → **"Structural Stop"**
- Updated kv tile: "Position Split 80 / 20" → **"50 / 50"**
