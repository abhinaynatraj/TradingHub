#!/usr/bin/env python3
"""
Layer B validation: sanity checks on the fade fields emitted by
model_stats_fixed_constant.py. Run after each engine execution.

Checks:
  1. fade_summary.trigger_rate is between 0.001 and 0.05 per model
  2. fade_summary.n_triggered matches count of reps with fade_triggered=True
  3. fade_breach_side matches which excursion exceeded its threshold
  4. Strict ordering: mae99_opp => mfe50_opp => anchor (if strongest reached,
     weaker ones must also be reached)

Exits 0 on success, non-zero on any violation.
"""
import json
import sys
from pathlib import Path

JSON_PATH = Path(__file__).parent.parent / 'model_stats_fixed_constant.json'


def validate_model(model_key, model):
    errors = []
    summary = model.get('fade_summary')
    if summary is None:
        errors.append(f'{model_key}: missing fade_summary')
        return errors

    reps = model.get('recent_reps', [])

    # Check 1: trigger rate in sane range (excluded for very small samples)
    if len(reps) >= 100:
        rate = summary['trigger_rate']
        if not (0.001 <= rate <= 0.05):
            errors.append(f'{model_key}: trigger_rate {rate:.4f} outside [0.001, 0.05]')

    # Check 2: n_triggered matches actual count
    actual_triggered = sum(1 for r in reps if r.get('fade_triggered'))
    if actual_triggered != summary['n_triggered']:
        errors.append(f'{model_key}: n_triggered mismatch (summary={summary["n_triggered"]}, actual={actual_triggered})')

    # Check 3 & 4: per-rep consistency
    mae99_up = summary['mae99_up_pct']
    mae99_dn = summary['mae99_down_pct']
    for i, r in enumerate(reps):
        if not r.get('fade_triggered'):
            continue
        side = r.get('fade_breach_side')
        up = r.get('excursion_up_pct', 0)
        dn = r.get('excursion_down_pct', 0)
        # Check 3: side matches a breach
        if side == 'up' and up < mae99_up:
            errors.append(f'{model_key} rep#{i}: side=up but excursion_up_pct={up} < mae99_up={mae99_up}')
        if side == 'down' and dn < mae99_dn:
            errors.append(f'{model_key} rep#{i}: side=down but excursion_down_pct={dn} < mae99_down={mae99_dn}')
        # Check 4: strict ordering
        a = r.get('fade_reached_anchor')
        m = r.get('fade_reached_mfe50_opp')
        m99 = r.get('fade_reached_mae99_opp')
        if m99 and not m:
            errors.append(f'{model_key} rep#{i}: mae99_opp=True but mfe50_opp=False')
        if m and not a:
            errors.append(f'{model_key} rep#{i}: mfe50_opp=True but anchor=False')

    return errors


def main():
    if not JSON_PATH.exists():
        print(f'ERROR: {JSON_PATH} not found', file=sys.stderr)
        sys.exit(2)

    data = json.load(open(JSON_PATH))
    all_errors = []
    for model_key, model in data.items():
        if not isinstance(model, dict) or 'meta' not in model:
            continue
        errors = validate_model(model_key, model)
        all_errors.extend(errors)

    if all_errors:
        print(f'FAIL: {len(all_errors)} violation(s)', file=sys.stderr)
        for e in all_errors[:50]:
            print(f'  {e}', file=sys.stderr)
        sys.exit(1)

    print(f'OK: all fade_summary checks passed for {len([k for k, v in data.items() if isinstance(v, dict)])} models')
    sys.exit(0)


if __name__ == '__main__':
    main()
