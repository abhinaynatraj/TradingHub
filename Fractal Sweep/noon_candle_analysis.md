# 12pm Hourly Candle Analysis — NQ & ES
*Analysis date: 2026-03-27*

---

## 1. Average 12pm Hourly Candle Size

True hourly candles aggregated from 1-minute data, 9am–3pm ET window.

### NQ (Nasdaq Futures)

| Period | 12pm Hour | All Hours Avg | 12pm vs Avg |
|--------|-----------|---------------|-------------|
| 1Y | 99.3 pts / 0.43% | 118.3 pts / 0.52% | -16% quieter |
| 3Y | 81.8 pts / 0.42% | 96.7 pts / 0.49% | -15% quieter |
| 5Y | 78.0 pts / 0.47% | 94.1 pts / 0.57% | -17% quieter |

### ES (S&P Futures)

| Period | 12pm Hour | All Hours Avg | 12pm vs Avg |
|--------|-----------|---------------|-------------|
| 1Y | 21.8 pts / 0.35% | 25.4 pts / 0.41% | -14% quieter |
| 3Y | 17.3 pts / 0.31% | 20.2 pts / 0.37% | -14% quieter |
| 5Y | 17.2 pts / 0.35% | 20.5 pts / 0.42% | -16% quieter |

> The 12pm hour is consistently ~15% quieter than the average trading hour.

---

## 2. 12pm Hourly Candle Range Distribution

### NQ

| Stat | 1Y pts | 1Y % | 3Y pts | 3Y % | 5Y pts | 5Y % |
|------|--------|------|--------|------|--------|------|
| **Mean** | 99.3 | 0.433% | 81.8 | 0.417% | 78.0 | 0.470% |
| **Median** | 81.5 | 0.343% | 68.3 | 0.356% | 67.0 | 0.397% |
| **Mode** | 64.0 | 0.210% | 64.0 | 0.270% | 46.0 | 0.350% |
| StdDev | 66.1 | 0.326% | 52.6 | 0.257% | 49.0 | 0.297% |
| 25th % | 54.8 | 0.231% | 47.8 | 0.260% | 46.0 | 0.274% |
| 75th % | 122.3 | 0.513% | 99.0 | 0.501% | 94.3 | 0.586% |
| Min / Max | 8.8 / 417.8 | 0.03% / 2.37% | — | — | — | — |

### ES

| Stat | 1Y pts | 1Y % | 3Y pts | 3Y % | 5Y pts | 5Y % |
|------|--------|------|--------|------|--------|------|
| **Mean** | 21.8 | 0.347% | 17.3 | 0.312% | 17.2 | 0.353% |
| **Median** | 17.5 | 0.269% | 14.3 | 0.265% | 14.5 | 0.290% |
| **Mode** | 12.25 | 0.120% | 12.0 | 0.190% | 11.5 | 0.190% |
| StdDev | 15.5 | 0.280% | 12.1 | 0.211% | 11.5 | 0.237% |
| 25th % | 12.0 | 0.185% | 9.75 | 0.185% | 9.5 | 0.191% |
| 75th % | 26.5 | 0.401% | 21.5 | 0.379% | 21.8 | 0.452% |
| Min / Max | 3.0 / 111.3 | 0.04% / 2.12% | — | — | — | — |

> Mean > Median > Mode gap indicates right-skewed distribution — a small number of high-volatility days inflate the average. The "typical" day is better described by the median.

---

## 3. 13:00 Hour — Sweep of 12pm Candle High/Low → Hit Mid

**Setup definition:**
- Within the 13:00 hour, price sweeps the 12pm candle high (goes above) or low (goes below)
- After the sweep, price returns back into the 12pm range
- Price then reaches the 12pm candle midpoint `(high + low) / 2`

### NQ — Unfiltered

| Period | High Swept | → Hit Mid | Low Swept | → Hit Mid | Either Swept | → Hit Mid |
|--------|-----------|-----------|-----------|-----------|--------------|-----------|
| 1Y | 135/253 (53%) | 45/135 **33%** | 112/253 (44%) | 45/112 **40%** | 227/253 (90%) | 85/227 **37%** |
| 3Y | 411/769 (53%) | 138/411 **34%** | 338/769 (44%) | 139/338 **41%** | 678/769 (88%) | 257/678 **38%** |
| 5Y | 660/1251 (53%) | 217/660 **33%** | 545/1251 (44%) | 212/545 **39%** | 1093/1251 (87%) | 396/1093 **36%** |

### ES — Unfiltered

| Period | High Swept | → Hit Mid | Low Swept | → Hit Mid | Either Swept | → Hit Mid |
|--------|-----------|-----------|-----------|-----------|--------------|-----------|
| 1Y | 138/253 (55%) | 46/138 **33%** | 116/253 (46%) | 45/116 **39%** | 227/253 (90%) | 87/227 **38%** |
| 3Y | 417/769 (54%) | 132/417 **32%** | 347/769 (45%) | 133/347 **38%** | 688/769 (90%) | 249/688 **36%** |
| 5Y | 650/1251 (52%) | 196/650 **30%** | 552/1251 (44%) | 207/552 **38%** | 1089/1251 (87%) | 380/1089 **35%** |

---

## 4. Filtered to 12pm Candle ≤ Median % Size

### NQ

| Period | Median Filter | High Swept | → Hit Mid | Low Swept | → Hit Mid | Either | → Hit Mid |
|--------|--------------|-----------|-----------|-----------|-----------|--------|-----------|
| 1Y | ≤ 0.343% | 61% | 34% | 43% | 47% | 93% | **40%** |
| 3Y | ≤ 0.356% | 61% | 34% | 45% | 51% | 92% | **46%** |
| 5Y | ≤ 0.397% | 59% | 39% | 44% | 48% | 90% | **43%** |

### ES

| Period | Median Filter | High Swept | → Hit Mid | Low Swept | → Hit Mid | Either | → Hit Mid |
|--------|--------------|-----------|-----------|-----------|-----------|--------|-----------|
| 1Y | ≤ 0.269% | 61% | 36% | 43% | 39% | 91% | **40%** |
| 3Y | ≤ 0.265% | 60% | 38% | 46% | 42% | 92% | **42%** |
| 5Y | ≤ 0.290% | 56% | 35% | 45% | 43% | 89% | **41%** |

> Filtering to smaller 12pm candles improves mid-hit rates. Low sweeps consistently outperform high sweeps.

---

## 5. Targeting 65% Mid-Hit Rate — NQ

Best combinations found (3Y window, 13:00 hour only):

| Filter | Sweeps | Hit Mid | Rate |
|--------|--------|---------|------|
| Low sweep + ≤ p15 (0.222%) + Wed | 16 | 13/16 | **81.2%** |
| Low sweep + ≤ p10 (0.196%) + Tue-Wed | 17 | 12/17 | **70.6%** |
| Low sweep + ≤ p15 (0.222%) + Tue-Wed | 31 | 22/31 | **71.0%** ← best sample |
| Low sweep + ≤ p25 (0.269%) + Tue | 20 | 13/20 | **65.0%** |

**Best NQ setup: Low sweep + 12pm candle ≤ 0.222% + Tuesday or Wednesday → 71% (31 sweeps, 3Y)**

For ES, size + DOW filters alone plateau around 60%. Additional context needed.

### Candle Size → Implied Win Rate (NQ, low sweep, 13+14:00, 3Y)

| 12pm candle size | Win rate |
|-----------------|----------|
| ≤ 0.269% (p25) | ~69.5% |
| ≤ 0.356% (p50 / median) | ~62.1% |
| No filter | ~53.1% |

> A 0.356% candle (3Y median) implies ~62% — not 65%. You need ≤ ~0.27% to reach the higher-confidence zone.

---

## 6. % of Times the Other Extreme is Also Swept (13:00 hour)

### NQ (3Y)

| Filter | High first → also sweeps low | Low first → also sweeps high | Both swept |
|--------|------------------------------|------------------------------|------------|
| No filter | 10.5% | 10.4% | 9.2% |
| ≤ median | 13.3% | 16.2% | 13.2% |
| ≤ p25 | 18.1% | 19.0% | **17.6%** |

### ES (3Y)

| Filter | High first → also sweeps low | Low first → also sweeps high | Both swept |
|--------|------------------------------|------------------------------|------------|
| No filter | 11.0% | 11.1% | 9.9% |
| ≤ median | 13.9% | 15.0% | 13.2% |
| ≤ p25 | 17.0% | **24.1%** | 18.7% |

> Sweeping both extremes is rare (~9-10% unfiltered). Rises to ~18-25% on tighter candles. ES low-swept-first is more likely to also sweep the high (directional asymmetry).

---

## 7. Extended Window: 13:00 + 14:00 Hours

Extending the sweep/mid window from 13:00 only to 13:00+14:00 significantly improves all metrics.

### NQ

| Metric | Filter | 13:00 only | 13+14:00 |
|--------|--------|-----------|----------|
| Low swept → hit mid | No filter (3Y) | 41.1% | **53.1%** |
| Low swept → hit mid | ≤ median (3Y) | 50.0% | **62.1%** |
| Low swept → hit mid | ≤ p25 (3Y) | 60.2% | **69.5% ✓** |
| Low swept → hit mid | ≤ p25 (5Y) | 54.1% | **65.1% ✓** |
| Both extremes swept | ≤ p25 (3Y) | 17.6% | **35.2%** |

### ES

| Metric | Filter | 13:00 only | 13+14:00 |
|--------|--------|-----------|----------|
| Low swept → hit mid | No filter (3Y) | 38.3% | **55.2%** |
| Low swept → hit mid | ≤ median (3Y) | 42.0% | **59.4%** |
| Low swept → hit mid | ≤ p25 (3Y) | 49.0% | **64.0% ~** |
| Low swept → hit mid | ≤ p25 (1Y) | 46.4% | **68.4% ✓** |
| Both extremes swept | ≤ p25 (3Y) | 18.7% | **39.9%** |

> Extending to 14:00 adds ~13-15 percentage points across the board. NQ low sweep ≤ p25 hits 65%+ on both 3Y and 5Y windows.

---

## Key Takeaways

1. **The 12pm candle is ~15% quieter** than the average hourly candle — noon is a structural dead zone
2. **Low sweeps outperform high sweeps** by ~10pp consistently across both instruments and all timeframes
3. **Tighter 12pm candles produce higher win rates** — the p25 threshold (~0.27% NQ, ~0.19% ES) is the key filter
4. **NQ is the stronger setup**: Low sweep + ≤ p25 + Tue/Wed → **71%** in 13:00 hour alone
5. **Extending to 14:00 pushes NQ to 69.5%** (3Y) and **ES to 64-68%** with the p25 filter
6. **Sweeping both extremes is rare** (~9%) but rises to ~35-40% when extending to 14:00
7. **A 0.356% NQ candle (median) implies ~62% win rate** — need ≤ 0.27% for 65%+

---

*Data source: `candle_science.duckdb` — NQ/ES 1-minute bars*
*All timestamps converted to America/New_York (ET)*
