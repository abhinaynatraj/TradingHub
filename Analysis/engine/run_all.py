"""Top-level driver — builds bars, runs both studies, writes parquet + manifest.

Run from repo root:
    python Analysis/engine/run_all.py
or from anywhere:
    python -m Analysis.engine.run_all
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Ensure local imports work whether invoked as script or module
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bars
import breakout_study
import quarter_study


SCHEMA_VERSION = 1


def main(start: str | None = None, end: str | None = None) -> None:
    out_root = HERE.parent / 'data'
    out_breakout = out_root / 'breakout'
    out_quarters = out_root / 'quarters'
    out_breakout.mkdir(parents=True, exist_ok=True)
    out_quarters.mkdir(parents=True, exist_ok=True)

    db = bars.db_path()
    if not db.exists():
        print(f"[run_all] ERROR: shared DuckDB not found at {db}", file=sys.stderr)
        sys.exit(1)

    print(f"[run_all] Loading 1-min bars (start={start}, end={end})...")
    minutes = bars.load_minutes(start=start, end=end)
    print(f"[run_all] Loaded {len(minutes):,} 1-min rows")

    hourly, quarters = bars.build_all_from_minutes(minutes)
    n_input_hours = (minutes['ny_ts'].dt.floor('h')).nunique()
    n_dropped = n_input_hours - len(hourly)
    print(f"[run_all] Built {len(hourly):,} hourly bars (dropped {n_dropped:,} incomplete hours)")

    # Breakout study
    print(f"[run_all] Running breakout study...")
    classified = breakout_study.classify(hourly)
    events = breakout_study.attach_followthrough(classified, minutes)
    events.to_parquet(out_breakout / 'breakouts.parquet', index=False)
    summaries = breakout_study.build_summaries(events)
    for name, df in summaries.items():
        df.to_parquet(out_breakout / f'summary_{name}.parquet', index=False)

    n_bull = int((events['breakout'] == 'bullish').sum())
    n_bear = int((events['breakout'] == 'bearish').sum())
    print(f"[run_all]   {n_bull:,} bullish breakouts, {n_bear:,} bearish breakouts")

    # Quarter study
    print(f"[run_all] Running quarter study...")
    features = quarter_study.build_features(hourly, quarters)
    features.to_parquet(out_quarters / 'quarter_features.parquet', index=False)
    q_summaries = quarter_study.build_summaries(features)
    for name, df in q_summaries.items():
        if len(df):
            df.to_parquet(out_quarters / f'{name}.parquet', index=False)

    # Manifest
    manifest = {
        'schema_version': SCHEMA_VERSION,
        'run_timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'date_range_start': str(hourly['hour_start_et'].min()) if len(hourly) else None,
        'date_range_end': str(hourly['hour_start_et'].max()) if len(hourly) else None,
        'total_hours': int(len(hourly)),
        'hours_dropped': int(n_dropped),
        'n_bullish_breakouts': n_bull,
        'n_bearish_breakouts': n_bear,
        'years_covered': sorted(int(y) for y in hourly['year'].unique()),
    }
    (out_root / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(f"[run_all] Wrote manifest: {out_root / 'manifest.json'}")
    print(f"[run_all] Done.")


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--start', help="ISO date (NY local), e.g. 2020-01-01")
    p.add_argument('--end', help="ISO date (NY local), exclusive")
    args = p.parse_args()
    main(start=args.start, end=args.end)
