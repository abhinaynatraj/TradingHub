"""Build pipeline orchestrator.

End-to-end:
  1. Load 1m bars for NQ and ES from the shared DuckDB (`engine.db.load_bars`).
  2. Walk every historical triad, sample decision points, aggregate empirical
     probabilities → per-symbol parquet-shape DataFrames
     (`engine.empirical.run_full_empirical`).
  3. Compute the strip-order fallback hierarchy on a representative slice
     (`engine.strip_order.compute_strip_order`).
  4. Emit Pine `map.put()` source via `engine.pine_emit.emit_pine_tables`.
  5. Write artifacts to `data/`:
       - `empirical_nq.parquet`
       - `empirical_es.parquet`
       - `strip_order_v1.json`
       - `_generated_tables.pine` (next to the indicator)
       - `last_build.txt` (status timestamp)
  6. Splice the emitted block into `pine/quarter_theory.pine` between the
     PASTE-REGION sentinels (only if those sentinels exist; otherwise leave
     the indicator untouched and rely on the standalone `_generated_tables`).

Invariants asserted:
  - `_generated_tables.pine` ≤ 900 KB (`pine_emit.assert_size_budget`).
  - Both NQ and ES tables produce at least one state row.

CLI:
  $ python3 engine/build.py                       # full pipeline, both syms
  $ python3 engine/build.py --start 2024-01-01    # custom date window
  $ python3 engine/build.py --sym NQ              # single symbol (skips ES)
  $ python3 engine/build.py --dry-run             # build but don't write files
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

# When invoked as `python3 engine/build.py`, the script's parent dir
# (engine/) is added to sys.path, which makes `from engine import …` fail.
# Add the project root so the package import resolves either way.
_PROJECT_ROOT_FOR_IMPORT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_FOR_IMPORT))

from engine import constants as C
from engine import pine_emit
from engine.db import load_bars
from engine.empirical import run_full_empirical
from engine.strip_order import compute_strip_order


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
PINE_DIR     = PROJECT_ROOT / "pine"

GENERATED_PINE = PINE_DIR / "_generated_tables.pine"
INDICATOR_PINE = PINE_DIR / "quarter_theory.pine"
LAST_BUILD     = DATA_DIR / "last_build.txt"

# Strip-order is computed over the canonical state-vector fields the Pine
# fallback hierarchy walks (see design spec §"Strip order"). We use the same
# field set the empirical table is keyed on; compute_strip_order ranks them
# by mutual information vs the outcome.
_TRIAD_STRIP_FIELDS = (
    "block", "c1cls", "c2q", "c2vh", "c2vl",
    "c2sw_c1h", "c2sw_c1l", "c2_inside",
    "midhr", "mid3h", "box_react",
)
_HOUR_STRIP_FIELDS = (
    "block", "hour_idx", "q",
    "q1cls", "q2cls", "q3cls", "q4cls",
    "sweep_set", "midhr", "box_react",
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _bars_for_sym(sym: str, start: str | None, end: str | None) -> pd.DataFrame:
    table = {"NQ": "nq_1m", "ES": "es_1m"}[sym]
    print(f"  → loading {table}…", flush=True)
    df = load_bars(table, start=start, end=end)
    print(f"    {len(df):,} bars from {df['ts'].iloc[0]} to {df['ts'].iloc[-1]}")
    return df


def _explode_state_key_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Parse `v1|sym=…|tf=…|k=v|k=v|…` keys into per-field columns.

    Used to compute strip-order without re-running the walker. Fields not
    present in a given row become NaN (e.g. hour rows lack `c1cls`).
    """
    if df.empty:
        return df

    def _parse(key: str) -> dict:
        out = {}
        for part in key.split("|"):
            if "=" in part:
                k, v = part.split("=", 1)
                out[k] = v
        return out

    parsed = df["state_key"].map(_parse).tolist()
    fields = pd.DataFrame(parsed)
    return pd.concat([df.reset_index(drop=True), fields], axis=1)


def _strip_order_for_tf(df: pd.DataFrame, tf: str, fields: Iterable[str]) -> list[str]:
    sub = df[df["state_key"].str.contains(f"|tf={tf}|", regex=False)]
    if sub.empty:
        return list(fields)
    sub = _explode_state_key_fields(sub)
    available = [f for f in fields if f in sub.columns]
    if not available:
        return list(fields)
    return compute_strip_order(sub, available)


# ── Pipeline ─────────────────────────────────────────────────────────────


def run_build(
    *,
    start: str | None = None,
    end: str | None = None,
    syms: tuple[str, ...] = ("NQ", "ES"),
    dry_run: bool = False,
) -> dict:
    """Run the full pipeline. Returns a status dict with paths + sizes."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PINE_DIR.mkdir(parents=True, exist_ok=True)

    empirical: dict[str, pd.DataFrame] = {}
    print(f"=== build start ({datetime.now(timezone.utc).isoformat()}) ===")

    for sym in syms:
        print(f"[{sym}] running empirical pipeline…")
        bars = _bars_for_sym(sym, start, end)
        df = run_full_empirical(bars, sym=sym)
        if df.empty:
            raise RuntimeError(
                f"[{sym}] empirical pipeline produced no rows — check date range / data."
            )
        print(f"    {df['state_key'].nunique():,} unique states · {df['n'].sum():,} samples total")
        empirical[sym] = df

    # Use NQ for the canonical strip-order (NQ has the longest history /
    # cleanest data). Falls back to whichever sym ran if NQ wasn't requested.
    primary = empirical.get("NQ", next(iter(empirical.values())))
    strip_order = {
        "schema": C.SCHEMA_VERSION,
        "triad":  _strip_order_for_tf(primary, "triad", _TRIAD_STRIP_FIELDS),
        "hour":   _strip_order_for_tf(primary, "hour",  _HOUR_STRIP_FIELDS),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    print(f"[strip-order] triad fields ranked: {strip_order['triad'][:5]}…")
    print(f"[strip-order] hour  fields ranked: {strip_order['hour'][:5]}…")

    # Emit Pine source (always need both NQ and ES, even if empty — the
    # consumer expects all four maps to be declared).
    nq_df = empirical.get("NQ", pd.DataFrame(columns=primary.columns))
    es_df = empirical.get("ES", pd.DataFrame(columns=primary.columns))
    pine_source = pine_emit.emit_pine_tables(nq_df, es_df, schema_version=C.SCHEMA_VERSION)
    pine_emit.assert_size_budget(pine_source)
    pine_size = len(pine_source.encode("utf-8"))
    print(f"[pine] emitted {pine_size:,} bytes ({pine_size/1024:.1f} KB) — under {pine_emit.MAX_BYTES//1024} KB budget")

    if dry_run:
        print("[dry-run] skipping all writes")
        return {
            "dry_run": True,
            "pine_size_bytes": pine_size,
            "syms": list(empirical.keys()),
            "states_per_sym": {s: int(d["state_key"].nunique()) for s, d in empirical.items()},
        }

    # Write artifacts.
    written: list[str] = []

    for sym, df in empirical.items():
        out = DATA_DIR / f"empirical_{sym.lower()}.parquet"
        df.to_parquet(out, index=False)
        written.append(str(out))

    strip_path = DATA_DIR / "strip_order_v1.json"
    strip_path.write_text(json.dumps(strip_order, indent=2) + "\n")
    written.append(str(strip_path))

    GENERATED_PINE.write_text(pine_source)
    written.append(str(GENERATED_PINE))

    # Splice into the indicator file iff sentinels exist (otherwise leave
    # the indicator untouched and let the user paste manually).
    spliced = False
    if INDICATOR_PINE.exists():
        try:
            pine_emit.splice_into_pine_file(str(INDICATOR_PINE), pine_source)
            spliced = True
            written.append(str(INDICATOR_PINE) + " (PASTE-REGION updated)")
        except ValueError as e:
            # Sentinels missing — that's fine, just write the standalone file.
            print(f"[pine] not splicing into indicator: {e}")

    LAST_BUILD.write_text(
        f"build_at={datetime.now(timezone.utc).isoformat()}\n"
        f"schema={C.SCHEMA_VERSION}\n"
        f"pine_size_bytes={pine_size}\n"
        f"states_nq={int(empirical['NQ']['state_key'].nunique()) if 'NQ' in empirical else 0}\n"
        f"states_es={int(empirical['ES']['state_key'].nunique()) if 'ES' in empirical else 0}\n"
        f"spliced_indicator={spliced}\n"
    )
    written.append(str(LAST_BUILD))

    print("\n=== build OK ===")
    for p in written:
        print(f"  wrote {p}")

    if not spliced:
        print(
            f"\nNext: copy the contents of {GENERATED_PINE.name} into "
            f"{INDICATOR_PINE.name} between the PASTE-REGION sentinels "
            f"(or add the sentinels first if they're missing)."
        )

    return {
        "dry_run": False,
        "pine_size_bytes": pine_size,
        "syms": list(empirical.keys()),
        "states_per_sym": {s: int(d["state_key"].nunique()) for s, d in empirical.items()},
        "spliced_indicator": spliced,
        "written": written,
    }


# ── CLI ──────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run the empirical build pipeline.")
    p.add_argument("--start", help="Inclusive start date YYYY-MM-DD (NY tz)")
    p.add_argument("--end",   help="Exclusive end date YYYY-MM-DD (NY tz)")
    p.add_argument("--sym",   choices=["NQ", "ES", "both"], default="both",
                   help="Which symbol to build (default: both).")
    p.add_argument("--dry-run", action="store_true",
                   help="Run pipeline but skip all file writes.")
    args = p.parse_args(argv)

    syms: tuple[str, ...] = ("NQ", "ES") if args.sym == "both" else (args.sym,)

    try:
        run_build(start=args.start, end=args.end, syms=syms, dry_run=args.dry_run)
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
