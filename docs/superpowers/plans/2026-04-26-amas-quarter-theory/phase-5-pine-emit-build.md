# Phase 5 — Pine Emit + Build Orchestrator

> **Sub-skill:** Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Translate engine outputs into Pine map literals, enforce the source-size budget, ship the `engine/build.py` CLI, and wire the cron hook.

**Prereq:** Phase 1–4 complete.

---

### Task 5.1: Pine map emission

**Files:**
- Create: `engine/pine_emit.py`
- Create: `tests/test_pine_emit.py`

- [ ] **Step 1: Write failing test**

File: `tests/test_pine_emit.py`

```python
"""Tests for Pine map emission. The output must:
1. Be parsable Pine v6 syntax (we verify a few signature features)
2. Stay below the source-size budget
3. Be deterministic (sorted keys → byte-identical output)
"""
from __future__ import annotations

import pandas as pd

from engine.pine_emit import emit_empirical_map, emit_qpair_map


def test_emit_empirical_map_contains_signatures():
    df = pd.DataFrame([
        {"state_key": "v1|sym=NQ|tf=triad|block=09-12|c1cls=line-up|c2q=Q3|c2vh=above|c2vl=above|c2sw_c1h=Y|c2sw_c1l=N|c2_inside=N|midhr=support|mid3h=untouched|box_react=10up_rejected",
         "outcome": "line-up", "p": 0.41, "ci_lo": 0.35, "ci_hi": 0.47, "n": 312},
        {"state_key": "v1|sym=NQ|tf=triad|block=09-12|c1cls=line-up|c2q=Q3|c2vh=above|c2vl=above|c2sw_c1h=Y|c2sw_c1l=N|c2_inside=N|midhr=support|mid3h=untouched|box_react=10up_rejected",
         "outcome": "doji",    "p": 0.59, "ci_lo": 0.53, "ci_hi": 0.65, "n": 312},
    ])
    src = emit_empirical_map(df, name="EMPIRICAL_NQ", tf="triad")
    assert "var map<string, array<float>> EMPIRICAL_NQ" in src
    assert "if barstate.isfirst" in src
    assert "map.put(EMPIRICAL_NQ" in src
    # 6-element value array for triad: [p_lup, p_ldn, p_aup, p_adn, p_doji, n]
    assert "array.from(" in src


def test_emit_empirical_map_deterministic():
    df = pd.DataFrame([
        {"state_key": "key_b", "outcome": "line-up", "p": 0.5, "ci_lo": 0.4, "ci_hi": 0.6, "n": 50},
        {"state_key": "key_a", "outcome": "doji",    "p": 0.7, "ci_lo": 0.6, "ci_hi": 0.8, "n": 50},
    ])
    src1 = emit_empirical_map(df, name="EMPIRICAL_NQ", tf="triad")
    src2 = emit_empirical_map(df.sort_values("state_key", ascending=False),
                              name="EMPIRICAL_NQ", tf="triad")
    assert src1 == src2  # deterministic regardless of input order


def test_emit_qpair_map_contains_signatures():
    from engine.quarter_pair_backtest import QPairRecord
    records = [QPairRecord(state_key="K", pair_id="Q3-Q2-long",
                           wr=0.64, ev=0.28, n=48, ci_lo=0.5, ci_hi=0.78)]
    src = emit_qpair_map(records, name="QPAIR_NQ")
    assert "var map<string, array<float>> QPAIR_NQ" in src
    assert "var map<string, string> QPAIR_NQ_LABELS" in src
    assert "Q3-Q2-long" in src
```

- [ ] **Step 2: Verify FAIL.**

- [ ] **Step 3: Implement `engine/pine_emit.py`**

```python
"""Emit Pine v6 map literals from engine output DataFrames.

Empirical map values are float arrays:
  triad: [p_lup, p_ldn, p_aup, p_adn, p_doji, n]
  hour:  [p_lup, p_ldn, p_doji, n]

QPair maps require two parallel maps because Pine doesn't have struct values:
  QPAIR_NQ:        key → [wr, ev, n, ci_lo, ci_hi]
  QPAIR_NQ_LABELS: key → pair_id (string for display)
"""
from __future__ import annotations

import pandas as pd

from engine.state_vector import canonical_hash


_TRIAD_OUTCOMES = ("line-up", "line-down", "apex-up", "apex-down", "doji")
_HOUR_OUTCOMES = ("line-up", "line-down", "doji")


def _format_float(x: float) -> str:
    """Quantize to 4 decimal places for compactness in Pine source."""
    return f"{x:.4f}"


def emit_empirical_map(df: pd.DataFrame, name: str, tf: str) -> str:
    """Emit a deterministic Pine map literal for the empirical probability table.

    df schema: state_key, outcome, p, ci_lo, ci_hi, n.
    Aggregates outcomes per state_key into a single fixed-shape array per the tf.
    """
    outcomes = _TRIAD_OUTCOMES if tf == "triad" else _HOUR_OUTCOMES
    pivot = df.pivot_table(
        index="state_key", columns="outcome", values="p", fill_value=0.0,
    )
    n_per_key = df.groupby("state_key")["n"].first()

    lines: list[str] = []
    lines.append(f"var map<string, array<float>> {name} = map.new<string, array<float>>()")
    lines.append("if barstate.isfirst")
    for key in sorted(pivot.index):
        h = canonical_hash(key)
        probs = [pivot.loc[key].get(o, 0.0) for o in outcomes]
        n = int(n_per_key.loc[key])
        vals = [_format_float(p) for p in probs] + [str(n)]
        lines.append(f"    map.put({name}, \"{h}\", array.from({', '.join(vals)}))")
    return "\n".join(lines) + "\n"


def emit_qpair_map(records, name: str) -> str:
    """Emit a Pine map literal for top-1 quarter-pair recommendations.

    Two parallel maps:
      <name>:        key → [wr, ev, n, ci_lo, ci_hi]
      <name>_LABELS: key → pair_id string
    """
    if not records:
        # Empty map shells (Pine requires the variable exist for downstream lookup)
        return (
            f"var map<string, array<float>> {name} = map.new<string, array<float>>()\n"
            f"var map<string, string> {name}_LABELS = map.new<string, string>()\n"
        )
    records = sorted(records, key=lambda r: r.state_key)
    lines: list[str] = []
    lines.append(f"var map<string, array<float>> {name} = map.new<string, array<float>>()")
    lines.append(f"var map<string, string> {name}_LABELS = map.new<string, string>()")
    lines.append("if barstate.isfirst")
    for r in records:
        h = canonical_hash(r.state_key)
        vals = [_format_float(r.wr), _format_float(r.ev), str(r.n),
                _format_float(r.ci_lo), _format_float(r.ci_hi)]
        lines.append(f"    map.put({name}, \"{h}\", array.from({', '.join(vals)}))")
        lines.append(f"    map.put({name}_LABELS, \"{h}\", \"{r.pair_id}\")")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: PASS.**

- [ ] **Step 5: Commit.**

```bash
git add engine/pine_emit.py tests/test_pine_emit.py
git commit -m "feat(quarter-theory): emit deterministic Pine map literals from engine output"
```

---

### Task 5.2: Build orchestrator CLI

**Files:**
- Create: `engine/build.py`
- Create: `tests/test_build.py`
- Create: `pine/quarter_theory.pine` (skeleton with paste-region sentinels — full impl in Phase 6)

- [ ] **Step 1: Create the Pine skeleton with paste-region sentinels**

File: `pine/quarter_theory.pine`

```pinescript
//@version=6
indicator("Amas Quarter Theory", overlay=true,
         max_labels_count=500, max_lines_count=500, max_boxes_count=500)

// Full implementation in Phase 6+. This file currently exists only to host
// the paste region for the generated tables; running it on a chart at this
// stage will display nothing.

// ═══ EMBEDDED EMPIRICAL TABLES ════════════════════════════════════════════════
// PASTE-REGION-START
// (auto-generated by engine/build.py — do not edit by hand)
// (last updated: <pending first build>)
//
// (no tables yet)
//
// PASTE-REGION-END
// ═══════════════════════════════════════════════════════════════════════════════
```

- [ ] **Step 2: Write failing test for the build orchestrator**

File: `tests/test_build.py`

```python
"""Tests for the build.py orchestrator.

The CLI runs the full pipeline: load DB → walk → sample → aggregate →
quarter-pair backtest → emit Pine snippet → write to disk → assert size budget.

We test the unit functions of build.py against synthetic inputs; the full
end-to-end run hits the real DB and is deferred to a smoke test, not unit.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from engine.build import (
    write_generated_tables_pine,
    assert_source_size_under_budget,
    SOURCE_SIZE_BUDGET_BYTES,
)


def test_write_generated_tables_creates_file(tmp_path: Path):
    out = tmp_path / "_generated_tables.pine"
    pine_src = "// dummy\nvar map<string, array<float>> EMPIRICAL_NQ = map.new<string, array<float>>()\n"
    write_generated_tables_pine(out, pine_src, last_updated="2026-04-26 12:00")
    assert out.exists()
    text = out.read_text()
    assert "last updated: 2026-04-26 12:00" in text
    assert "EMPIRICAL_NQ" in text


def test_assert_source_size_passes_under_budget():
    src = "x" * (SOURCE_SIZE_BUDGET_BYTES - 1)
    assert_source_size_under_budget(src)  # should not raise


def test_assert_source_size_fails_over_budget():
    src = "x" * (SOURCE_SIZE_BUDGET_BYTES + 1)
    with pytest.raises(AssertionError, match="source size"):
        assert_source_size_under_budget(src)


def test_determinism_two_runs_same_output(tmp_path: Path):
    """Calling write_generated_tables_pine twice with the same inputs produces
    byte-identical output."""
    src = "// snippet\nvar x = 1\n"
    out1 = tmp_path / "a.pine"
    out2 = tmp_path / "b.pine"
    write_generated_tables_pine(out1, src, last_updated="2026-04-26 12:00")
    write_generated_tables_pine(out2, src, last_updated="2026-04-26 12:00")
    assert out1.read_bytes() == out2.read_bytes()
```

- [ ] **Step 3: Verify FAIL.**

- [ ] **Step 4: Implement `engine/build.py`**

```python
"""Orchestrator: load DB → aggregate → emit Pine → write _generated_tables.pine.

Asserts the source-size budget. Deterministic output (sorted keys, fixed
formatting). Hooks: --validate-only, --since, --symbol.
"""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

import pandas as pd

from engine import constants as C
from engine.db import load_bars
from engine.empirical import run_full_empirical
from engine.pine_emit import emit_empirical_map, emit_qpair_map
from engine.quarter_pair_backtest import run_full_qpair


# Hard limit: 900 KB. Pine's source budget is ~1 MB; 10% headroom.
SOURCE_SIZE_BUDGET_BYTES = 900 * 1024


def assert_source_size_under_budget(src: str) -> None:
    size = len(src.encode("utf-8"))
    assert size <= SOURCE_SIZE_BUDGET_BYTES, (
        f"source size {size} bytes exceeds budget {SOURCE_SIZE_BUDGET_BYTES}. "
        f"Mitigate by: 1) compact key encoding (already used), "
        f"2) quantize probabilities further, 3) drop low-n keys, "
        f"4) split into per-block tables."
    )


def write_generated_tables_pine(out_path: Path, pine_src: str, last_updated: str) -> None:
    """Write the generated tables file with a header banner.

    The full file content is what gets pasted into pine/quarter_theory.pine
    between PASTE-REGION-START and PASTE-REGION-END sentinels.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    banner = (
        "// (auto-generated by engine/build.py — do not edit by hand)\n"
        f"// (last updated: {last_updated})\n"
    )
    out_path.write_text(banner + pine_src)


def build_for_symbol(sym: str, start: str | None = None, end: str | None = None) -> str:
    """Build empirical + qpair Pine snippets for one symbol. Returns the combined source."""
    table = C.TABLE_FOR_SYMBOL[sym]
    df = load_bars(table, start=start, end=end)
    print(f"[{sym}] loaded {len(df)} bars from {table}")

    emp = run_full_empirical(df, sym=sym)
    print(f"[{sym}] {emp.state_key.nunique()} empirical state-keys, {len(emp)} rows")

    triad_emp = emp[emp["state_key"].str.contains("|tf=triad|")]
    hour_emp = emp[emp["state_key"].str.contains("|tf=hour|")]

    pine_src = ""
    pine_src += emit_empirical_map(triad_emp, name=f"EMPIRICAL_{sym}_TRIAD", tf="triad")
    pine_src += emit_empirical_map(hour_emp, name=f"EMPIRICAL_{sym}_HOUR", tf="hour")

    qpair = run_full_qpair(df, sym=sym, min_n=30)
    print(f"[{sym}] {len(qpair)} qpair recommendations")
    pine_src += emit_qpair_map(qpair, name=f"QPAIR_{sym}")

    return pine_src


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", choices=("NQ", "ES", "BOTH"), default="BOTH")
    parser.add_argument("--since", default=None, help="YYYY-MM-DD")
    parser.add_argument("--until", default=None, help="YYYY-MM-DD")
    parser.add_argument("--validate-only", action="store_true",
                        help="Re-run parity tests, don't rebuild tables")
    args = parser.parse_args(argv)

    here = Path(__file__).parent.parent
    out_dir = here / "pine"
    out_path = out_dir / "_generated_tables.pine"

    if args.validate_only:
        # Phase 9 implements parity. For now, this is a placeholder.
        print("validate-only: parity check is implemented in Phase 9.")
        return 0

    syms = ["NQ", "ES"] if args.symbol == "BOTH" else [args.symbol]
    pine_src = ""
    for sym in syms:
        pine_src += f"// ── {sym} tables ─────────────────────────────────────────────\n"
        pine_src += build_for_symbol(sym, start=args.since, end=args.until)
        pine_src += "\n"

    assert_source_size_under_budget(pine_src)

    last_updated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    write_generated_tables_pine(out_path, pine_src, last_updated=last_updated)
    size_kb = len(pine_src.encode("utf-8")) / 1024
    print(f"\n✓ Wrote {out_path} ({size_kb:.1f} KB)\n")
    print("Next: open pine/quarter_theory.pine and replace contents between")
    print("      PASTE-REGION-START and PASTE-REGION-END with this file's contents.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: PASS.** Run `python3 -m pytest tests/test_build.py -v`.

- [ ] **Step 6: Commit.**

```bash
git add engine/build.py tests/test_build.py pine/quarter_theory.pine
git commit -m "feat(quarter-theory): add build.py CLI and Pine paste-region skeleton"
```

---

### Task 5.3: Daily-update cron hook

**Files:**
- Create: `engine/daily_update.py`
- Modify: `Statistic.ally/Fractal Sweep/engine/daily_update.py` (add hook at end — discuss with user before running on real cron)
- Create: `tests/test_daily_update.py`

- [ ] **Step 1: Write a test that just verifies the script is callable**

File: `tests/test_daily_update.py`

```python
"""Test that daily_update.py is importable and runnable as a script.
Doesn't exercise the full pipeline — that's covered by test_build.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_daily_update_is_runnable_help():
    here = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-c", "import engine.daily_update"],
        cwd=here, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"import failed: {result.stderr}"
```

- [ ] **Step 2: Implement `engine/daily_update.py`**

```python
"""Daily Quarter Theory rebuild. Called by Fractal Sweep cron after Databento fetch.

Runs build.py, writes status to data/last_build.txt. The user re-pastes the
generated snippet into Pine on whatever cadence they want (weekly/monthly).
"""
from __future__ import annotations

import datetime
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent     # Amas Quarter Theory/
BUILD_PY = HERE / "engine" / "build.py"
NOTIF = HERE / "data" / "last_build.txt"


def main() -> int:
    NOTIF.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.datetime.now().isoformat(timespec="seconds")
    result = subprocess.run([sys.executable, str(BUILD_PY)],
                            cwd=HERE, capture_output=True, text=True)
    finished = datetime.datetime.now().isoformat(timespec="seconds")
    NOTIF.write_text(
        f"started: {started}\n"
        f"finished: {finished}\n"
        f"status: {'OK' if result.returncode == 0 else 'FAILED'}\n"
        f"---STDOUT---\n{result.stdout}\n"
        f"---STDERR---\n{result.stderr}\n"
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: PASS. Commit.**

```bash
git add engine/daily_update.py tests/test_daily_update.py
git commit -m "feat(quarter-theory): add daily_update cron-callable wrapper"
```

- [ ] **Step 4: Document the Fractal Sweep hook (don't edit yet — wait for user approval)**

Create `docs/cron_hook.md`:

```markdown
# Cron hook into Fractal Sweep

To enable daily auto-rebuild, append to `Statistic.ally/Fractal Sweep/engine/daily_update.py`:

\`\`\`python
import subprocess

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # Statistic.ally/
QT_DAILY = REPO_ROOT / "Amas Quarter Theory" / "engine" / "daily_update.py"
if QT_DAILY.exists():
    subprocess.run(
        [sys.executable, str(QT_DAILY)],
        cwd=QT_DAILY.parent.parent,
        check=False,  # don't fail Fractal Sweep cron on Quarter Theory failures
    )
\`\`\`

This change is INTENTIONALLY not made automatically — it touches the production
cron path. Apply manually after a clean local run of:

\`\`\`bash
cd "Statistic.ally/Amas Quarter Theory"
python3 engine/daily_update.py
cat data/last_build.txt
\`\`\`
```

```bash
git add docs/cron_hook.md
git commit -m "docs(quarter-theory): document Fractal Sweep cron hook (manual install)"
```

---

### Phase 5 smoke test

- [ ] **Run pytest:** `python3 -m pytest tests/ -q`. Expect ~100+ passed.

- [ ] **End-to-end build on real data:**

```bash
cd "Statistic.ally/Amas Quarter Theory"
python3 engine/build.py --symbol NQ --since 2024-01-02 --until 2024-02-01
```
Expected output: shows bar count, state-key count, qpair record count, "✓ Wrote pine/_generated_tables.pine (X.X KB)" with size under 900 KB.

- [ ] **Verify generated file looks sensible:**

```bash
head -40 pine/_generated_tables.pine
wc -c pine/_generated_tables.pine
```
Expected: file under 900 * 1024 bytes (`wc -c < FILE` returns < 921600).

**End of Phase 5.** Move to [Phase 6 — Pine indicator skeleton](phase-6-pine-skeleton.md).
