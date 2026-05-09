# Daily Probability Zones

Empirical study of how Daily Segment Probabilities (DSP) — the published "Daily High/Low Probability Zones" indicator at [Analysis/pine/](../Analysis/pine/) … wait, actually the FS-companion lives at [Fractal Sweep/pine/daily_high_low_probability_zones.pine](../Fractal Sweep/pine/daily_high_low_probability_zones.pine) — interacts with Fractal Sweep entries.

Hypothesis: a Fractal Sweep long entered when price is *above* the historically-most-likely "day high" segment is fading the day's tail; one entered *below* it has room to run. If true, DSP segment context should stratify FS WR/EV.

## Stack

- Python 3.14 · DuckDB 1.4.4 · pandas
- Standalone HTML dashboard, zero CDN deps

## Folder layout

```
Daily Probability Zones/
├── model_dashboard.html        DSP × Fractal Sweep dashboard
├── model_stats.json            engine output (gitignored)
├── engine/
│   ├── distributions.py        per-date 250d-prior segment distributions
│   ├── join.py                 attach DSP context to FS recent_trades
│   └── build.py                orchestrator
├── docs/
│   └── methodology.md
└── tests/
```

## Running

```bash
python3 engine/build.py                  # build model_stats.json
python3 -m pytest tests/ -q
```

## Methodology

1. Compute the daily H/L series from `nq_1m` (NY tz, drop zero-range days).
2. For each eligible date `d`, build the segment distribution from days `[d-251, d-1]` strictly. Pick `top_h`, `top_l`.
3. Read `Fractal Sweep/model_stats.json` `recent_trades` (All Time, both models, `simple_1r` profile).
4. For each FS trade, look up the DSP context for that date and bin the **entry price** as a percent of the prior day's range. Attach `dsp_*` fields.
5. Aggregate WR/EV by DSP entry segment, top-segment proximity, direction.

See `docs/methodology.md` for the full spec.

## Database

Read-only from `../Fractal Sweep/candle_science.duckdb`.
