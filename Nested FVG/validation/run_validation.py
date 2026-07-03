"""Statistical validation of the (de-biased) Nested FVG model.

Reads the per-pairing parquets and produces `validation.json` consumed by the
dashboard's Validation tab. Four dimensions:

  1. Walk-forward / OOS   — rolling train/test windows; EV sign-stability per window.
  2. Block bootstrap       — day-blocked resampling → 95% CI on settled EV (R).
  3. Sensitivity           — yearly EV stability + outlier-day leave-one-out +
                             exit-parameter sweep (re-derived from stored MAE/MFE).
  4. Per-slice scan        — session × direction × SMT cells with EV, CI, n, and a
                             multiple-testing (Bonferroni) flag.

All EV/PF figures EXCLUDE expired trades (consistent with the engine). R is the
per-trade signed return (win=+2, loss=-1, scratch=0). No look-ahead: this only
consumes already-resolved trade rows.

Run:  python3 validation/run_validation.py
"""
import json
from pathlib import Path

import duckdb
import numpy as np

DATA = Path(__file__).parent.parent / 'data'
OUT = Path(__file__).parent.parent / 'data' / 'validation.json'
PAIRINGS = ['1m_5m', '3m_15m', '5m_30m']
RNG_SEED = 12345  # fixed for reproducibility (no Math.random / wall-clock)


def _load_settled(pairing):
    """Return a structured array of settled NQ trades: date, r, pnl_pts, mae_pts,
    mfe_pts, session, direction, smt, yr. Expired excluded."""
    con = duckdb.connect()
    rows = con.execute(f"""
        SELECT date, r, pnl_pts, mae_pts, mfe_pts, session, direction, smt, yr,
               entry_ts_ns
        FROM read_parquet('{DATA / f"trades_{pairing}.parquet"}')
        WHERE instrument='NQ' AND outcome != 'expired'
        ORDER BY entry_ts_ns
    """).fetchall()
    con.close()
    return rows


def _ev(rs):
    return float(np.mean(rs)) if len(rs) else 0.0


def _pf(rs):
    rs = np.asarray(rs, dtype='float64')
    pos = rs[rs > 0].sum()
    neg = -rs[rs < 0].sum()
    return float(pos / neg) if neg > 0 else 0.0


def _wr(rs):
    rs = np.asarray(rs, dtype='float64')
    return float(100.0 * np.mean(rs > 0)) if len(rs) else 0.0


# ── 1. Walk-forward / OOS ────────────────────────────────────────────────────
def walk_forward(rows):
    """Rolling 1-year test windows by calendar year. Each year's EV is fully OOS
    relative to all prior years (no parameters are fit, so every window is OOS by
    construction — this checks sign-stability across regimes)."""
    years = sorted({r[8] for r in rows})
    out = []
    for y in years:
        rs = [r[1] for r in rows if r[8] == y]
        if len(rs) < 50:
            continue
        out.append(dict(year=int(y), n=len(rs), ev_r=round(_ev(rs), 4),
                        pf=round(_pf(rs), 3), wr=round(_wr(rs), 2)))
    n_pos = sum(1 for w in out if w['ev_r'] > 0)
    return dict(windows=out, n_windows=len(out), n_positive=n_pos,
                pct_positive=round(100.0 * n_pos / len(out), 1) if out else 0.0)


# ── 2. Block bootstrap CI ────────────────────────────────────────────────────
def block_bootstrap_ci(rows, n_boot=2000, seed=RNG_SEED):
    """Day-blocked bootstrap: resample whole trading days with replacement to
    preserve intraday autocorrelation, recompute EV each draw → 95% CI.

    A genuine edge has a CI strictly above 0; noise straddles 0; this model is
    expected to sit strictly below 0."""
    # group r by day
    by_day = {}
    for r in rows:
        by_day.setdefault(r[0], []).append(r[1])
    days = list(by_day.values())
    day_arrs = [np.asarray(d, dtype='float64') for d in days]
    n_days = len(day_arrs)
    if n_days < 10:
        return dict(ev_r=round(_ev([r[1] for r in rows]), 4), lo=None, hi=None,
                    n_days=n_days, note='too few days')
    rng = np.random.default_rng(seed)
    boot_evs = np.empty(n_boot, dtype='float64')
    for b in range(n_boot):
        pick = rng.integers(0, n_days, size=n_days)
        cat = np.concatenate([day_arrs[i] for i in pick])
        boot_evs[b] = cat.mean()
    lo, hi = np.percentile(boot_evs, [2.5, 97.5])
    point = _ev([r[1] for r in rows])
    return dict(ev_r=round(point, 4), lo=round(float(lo), 4), hi=round(float(hi), 4),
                n_days=n_days, n_boot=n_boot,
                ci_excludes_zero=bool(hi < 0 or lo > 0),
                sign='negative' if hi < 0 else ('positive' if lo > 0 else 'inconclusive'))


# ── 3a. Yearly stability (reuses walk_forward windows) ───────────────────────
# ── 3b. Outlier leave-one-out ────────────────────────────────────────────────
def outlier_sensitivity(rows):
    """Leave-one-day-out: how much does the single best/worst day move aggregate
    EV? A result driven by a few outlier days is fragile."""
    by_day = {}
    for r in rows:
        by_day.setdefault(r[0], []).append(r[1])
    day_sum = {d: float(np.sum(v)) for d, v in by_day.items()}
    total = sum(r[1] for r in rows)
    n = len(rows)
    base_ev = total / n
    best_day = max(day_sum, key=day_sum.get)
    worst_day = min(day_sum, key=day_sum.get)
    n_best = len(by_day[best_day]); n_worst = len(by_day[worst_day])
    ev_wo_best = (total - day_sum[best_day]) / (n - n_best) if n - n_best else 0.0
    ev_wo_worst = (total - day_sum[worst_day]) / (n - n_worst) if n - n_worst else 0.0
    return dict(base_ev_r=round(base_ev, 4),
                best_day=best_day, best_day_sum_r=round(day_sum[best_day], 2),
                ev_without_best=round(ev_wo_best, 4),
                worst_day=worst_day, worst_day_sum_r=round(day_sum[worst_day], 2),
                ev_without_worst=round(ev_wo_worst, 4),
                n_days=len(by_day))


# ── 3c. Exit-parameter sweep (re-derived from stored MAE/MFE) ────────────────
def exit_param_sweep(rows):
    """Approximate EV under alternative fixed stop/target distances, re-derived
    from each trade's MAE/MFE (the max adverse/favorable excursion in points).

    For a candidate (stop, target) with the same 50% scale-out semantics:
      - if MAE >= stop BEFORE MFE >= partial -> we can't know intrabar order from
        MAE/MFE alone, so we use a CONSERVATIVE rule: stop hit if mae>=stop;
        else win if mfe>=target; else scratch if mfe>=partial; else flat(expire-like).
    This is an APPROXIMATION (no intrabar sequence), flagged as such. It shows
    whether the loss is specific to the 15/45 choice or pervasive across exits."""
    mae = np.array([r[3] for r in rows], dtype='float64')
    mfe = np.array([r[4] for r in rows], dtype='float64')
    grid = []
    for stop in (10.0, 15.0, 20.0, 25.0):
        for target in (30.0, 45.0, 60.0):
            partial = stop  # mirror the engine (partial == stop distance)
            stopped = mae >= stop
            won = (~stopped) & (mfe >= target)
            scratched = (~stopped) & (~won) & (mfe >= partial)
            flat = (~stopped) & (~won) & (~scratched)
            # blended R per the 50% scale-out (risk unit = stop)
            r = np.where(stopped, -1.0,
                 np.where(won, 0.5 * (partial / stop) + 0.5 * (target / stop),
                 np.where(scratched, 0.0, 0.0)))
            # exclude 'flat' (expire-like) from EV like the engine excludes expired
            settled = ~flat
            ev = float(r[settled].mean()) if settled.any() else 0.0
            grid.append(dict(stop=stop, target=target, n_settled=int(settled.sum()),
                             ev_r=round(ev, 4)))
    return dict(grid=grid,
                note='Approximation from stored MAE/MFE; ignores intrabar order '
                     '(conservative: a bar touching both stop and target counts as stop).')


# ── 3d. Filter sensitivity (min-bp / proximity proxies via gap sizes) ────────
def gap_size_sensitivity(pairing):
    """EV as a function of requiring a LARGER minimum LTF gap (a stricter min-bp
    proxy). If a bigger/cleaner gap helped, EV would rise with the threshold."""
    con = duckdb.connect()
    pq = str(DATA / f"trades_{pairing}.parquet")
    out = []
    for pct in (0, 25, 50, 75, 90):
        row = con.execute(f"""
            SELECT COUNT(*) n, AVG(r) ev
            FROM read_parquet('{pq}')
            WHERE instrument='NQ' AND outcome != 'expired'
              AND gap_ltf_pts >= (SELECT quantile_cont(gap_ltf_pts, {pct/100.0})
                                  FROM read_parquet('{pq}')
                                  WHERE instrument='NQ' AND outcome != 'expired')
        """).fetchone()
        out.append(dict(min_gap_pctile=pct, n=int(row[0]),
                        ev_r=round(float(row[1]), 4) if row[1] is not None else 0.0))
    con.close()
    return out


# ── 4. Per-slice scan with multiple-testing flag ─────────────────────────────
def slice_scan(rows):
    """EV + bootstrap CI for every session × direction × SMT cell. Flags any cell
    whose CI is above 0 AFTER Bonferroni correction for the number of cells tested."""
    cells = {}
    for r in rows:
        key = (r[5], r[6], bool(r[7]))  # session, direction, smt
        cells.setdefault(key, []).append(r[1])
    n_tests = len(cells)
    alpha = 0.05 / max(1, n_tests)  # Bonferroni
    pct_lo = 100 * (alpha / 2)
    pct_hi = 100 * (1 - alpha / 2)
    rng = np.random.default_rng(RNG_SEED + 7)
    out = []
    for (sess, dirn, smt), rs in cells.items():
        arr = np.asarray(rs, dtype='float64')
        n = len(arr)
        ev = float(arr.mean()) if n else 0.0
        lo = hi = None
        survives = False
        if n >= 100:
            boot = np.array([rng.choice(arr, size=n, replace=True).mean()
                             for _ in range(1000)])
            lo, hi = np.percentile(boot, [pct_lo, pct_hi])
            survives = bool(lo > 0)  # positive even after Bonferroni
        out.append(dict(session=sess, direction=dirn, smt=smt, n=n,
                        ev_r=round(ev, 4),
                        ci_lo=round(float(lo), 4) if lo is not None else None,
                        ci_hi=round(float(hi), 4) if hi is not None else None,
                        survives_bonferroni=survives))
    out.sort(key=lambda c: c['ev_r'], reverse=True)
    # For any cell that survives Bonferroni, attach a per-year EV breakdown so the
    # dashboard can show whether it's regime-stable or a multiple-testing fluke.
    survivors = [c for c in out if c['survives_bonferroni']]
    for c in survivors:
        yearly = {}
        for r in rows:
            if r[5] == c['session'] and r[6] == c['direction'] and bool(r[7]) == c['smt']:
                yearly.setdefault(int(r[8]), []).append(r[1])
        c['yearly'] = [dict(year=y, n=len(v), ev_r=round(float(np.mean(v)), 4))
                       for y, v in sorted(yearly.items())]
        c['n_positive_years'] = sum(1 for yr in c['yearly'] if yr['ev_r'] > 0)
        c['n_years'] = len(c['yearly'])
    return dict(n_cells=n_tests, bonferroni_alpha=round(alpha, 5),
                bonferroni_note='Bonferroni applied per-pairing; the true family across '
                                'all 3 pairings is ~3x larger, so a single survivor is '
                                'a HYPOTHESIS to forward-test, not a validated edge.',
                any_survives=any(c['survives_bonferroni'] for c in out),
                cells=out)


def main():
    result = dict(schema_version=1, pairings={},
                  method=dict(
                      note='All EV/PF exclude expired trades. R = signed per-trade '
                           'return (win=+2, loss=-1, scratch=0). Bootstrap is '
                           'day-blocked (2000 draws) to respect intraday '
                           'autocorrelation. Slice scan uses Bonferroni correction.',
                      seed=RNG_SEED))
    for p in PAIRINGS:
        print(f'[validate] {p}')
        rows = _load_settled(p)
        print(f'  {len(rows):,} settled trades')
        result['pairings'][p] = dict(
            n_settled=len(rows),
            aggregate=dict(ev_r=round(_ev([r[1] for r in rows]), 4),
                           pf=round(_pf([r[1] for r in rows]), 3),
                           wr=round(_wr([r[1] for r in rows]), 2)),
            walk_forward=walk_forward(rows),
            bootstrap=block_bootstrap_ci(rows),
            outlier=outlier_sensitivity(rows),
            exit_sweep=exit_param_sweep(rows),
            gap_sensitivity=gap_size_sensitivity(p),
            slice_scan=slice_scan(rows),
        )
        b = result['pairings'][p]['bootstrap']
        print(f"  EV {b['ev_r']:+.4f}  95% CI [{b['lo']}, {b['hi']}]  -> {b['sign']}")

    OUT.write_text(json.dumps(result, indent=2))
    print(f'[done] wrote {OUT}')

    # console verdict
    print('\n=== VERDICT ===')
    for p in PAIRINGS:
        b = result['pairings'][p]['bootstrap']
        s = result['pairings'][p]['slice_scan']
        print(f"{p:<8} EV {b['ev_r']:+.4f} CI[{b['lo']},{b['hi']}] {b['sign']:<13} "
              f"| any slice survives Bonferroni: {s['any_survives']}")


if __name__ == '__main__':
    main()
