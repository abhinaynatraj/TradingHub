"""Tests for find_supporting_fvg — supporting FVG confluence detection."""
import numpy as np
import pandas as pd
import pytest

import model_stats as ms


def _arrs(bars):
    """Build a minimal arrs dict with just the OHLC fields find_supporting_fvg uses."""
    n = len(bars)
    return dict(
        open  = np.array([b[0] for b in bars], dtype='float64'),
        high  = np.array([b[1] for b in bars], dtype='float64'),
        low   = np.array([b[2] for b in bars], dtype='float64'),
        close = np.array([b[3] for b in bars], dtype='float64'),
    )


def test_bullish_strict_fvg_between_sl_and_entry():
    # 5 bars total. FVG forms at index 2 (3-bar pattern using bars 0,1,2).
    # bar 0 high = 100, bar 2 low = 105 → bullish FVG band (100, 105].
    # No subsequent bar dips below 100 → unfilled.
    bars = [
        # (open, high, low, close)
        (95, 100, 92, 99),   # 0 — defines lower edge (high=100)
        (99, 103, 98, 102),  # 1 — middle bar (irrelevant to gap)
        (102, 108, 105, 107),# 2 — defines upper edge (low=105) → FVG forms here
        (107, 110, 106, 109),# 3 — stays above 100, doesn't fill
        (109, 112, 108, 111),# 4 — entry bar (will not be inspected past entry_idx)
    ]
    arrs = _arrs(bars)
    # Long trade: sweep_extreme=98 (below the gap), entry_price=109 (above the gap).
    # Body of gap (100, 105] is fully between 98 and 109 → strict True, loose True.
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=98.0, entry_price=109.0, direction='LONG',
    )
    assert strict is True
    assert loose is True


def test_bullish_loose_only_fvg_extends_below_sl():
    # Bullish FVG forms with bottom BELOW sweep_extreme=98 → loose True, strict False.
    # Bars 0 and 1 highs both kept at 97 (below SL=98) so neither i=2 nor i=3
    # candidate gap can satisfy strict.
    bars = [
        (95,  97, 92, 96),    # 0 — high=97 < SL=98
        (96,  97, 94, 96),    # 1 — high=97 < SL=98
        (96, 105,101,104),    # 2 — low=101 > high[0]=97 → bullish FVG (97, 101]
        (104,108,102,107),    # 3 — also forms FVG (97,102] with high[1]=97; both have bottom=97<98
        (107,110,106,109),    # 4 — entry; not scanned
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=98.0, entry_price=109.0, direction='LONG',
    )
    assert strict is False  # all candidate gap bottoms (97) < sweep_extreme (98)
    assert loose is True    # gap tops (101, 102) <= entry (109)


def test_bullish_fvg_above_entry_both_false():
    # Gap forms ABOVE entry — not supporting. Both False.
    bars = [
        (95, 100, 92, 99),
        (99, 103, 98, 102),
        (102, 108, 105, 107),  # FVG (100, 105]
        (107, 110, 106, 109),
        (109, 112, 108, 111),  # entry
    ]
    arrs = _arrs(bars)
    # Entry below the gap → top (105) > entry (104) → loose False.
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=98.0, entry_price=104.0, direction='LONG',
    )
    assert strict is False
    assert loose is False


def test_bullish_fvg_filled_before_entry_both_false():
    # FVG forms at bar 2, but bar 3 wicks into bottom of gap (low <= 100).
    # Should be treated as filled → both False.
    bars = [
        (95, 100, 92, 99),
        (99, 103, 98, 102),
        (102, 108, 105, 107),  # FVG (100, 105]
        (107, 110, 99, 109),   # low=99 <= 100 → fills the gap
        (109, 112, 108, 111),  # entry
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=98.0, entry_price=111.0, direction='LONG',
    )
    assert strict is False
    assert loose is False


def test_bearish_fvg_does_not_count_for_long():
    # All bars contain a bearish 3-bar gap but no bullish gap. Long trade.
    bars = [
        (110, 112, 108, 109),  # 0 — low=108
        (109, 110, 106, 107),  # 1
        (107, 105, 102, 104),  # 2 — high=105 < low[0]=108 → bearish FVG (105, 108)
        (104, 105, 100, 102),
        (102, 104,  98, 100),  # entry below — but trade is LONG so wrong-side
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=95.0, entry_price=102.0, direction='LONG',
    )
    assert strict is False
    assert loose is False


def test_bearish_strict_fvg_between_entry_and_sl_short():
    # SHORT trade: sweep_extreme is ABOVE entry (sweep of prior high).
    # Bearish FVG should sit with body fully inside [entry, sweep_extreme].
    bars = [
        (110, 112, 108, 109),  # 0 — low=108 → upper edge of bearish gap
        (109, 110, 106, 107),  # 1
        (107, 105, 102, 104),  # 2 — high=105 → lower edge. Bearish gap (105, 108)
        (104, 107, 102, 103),  # 3 — high=107 < 108 → does not fill
        (103, 105, 100, 102),  # 4 — entry
    ]
    arrs = _arrs(bars)
    # Short: sweep_extreme=110 (above), entry=102 (below). Gap (105, 108) is
    # fully inside [102, 110] → strict True, loose True.
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=110.0, entry_price=102.0, direction='SHORT',
    )
    assert strict is True
    assert loose is True


def test_bearish_loose_only_short_extends_above_sl():
    # SHORT: bearish gap with top above sweep_extreme → strict False, loose True.
    bars = [
        (114, 116, 112, 113),  # 0 — low=112
        (113, 114, 110, 111),  # 1
        (111, 109, 106, 108),  # 2 — high=109 → bearish gap (109, 112)
        (108, 110, 106, 107),  # 3 — does not fill (max high in (i,entry)=110 < 112)
        (107, 109, 100, 102),  # 4 — entry
    ]
    arrs = _arrs(bars)
    # sweep_extreme=111 (below the top of gap=112) → strict False
    # gap bottom=109 >= entry=102 → loose True
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=111.0, entry_price=102.0, direction='SHORT',
    )
    assert strict is False
    assert loose is True


def test_bearish_fvg_filled_before_entry_short():
    # SHORT bearish gap that gets filled (a later bar's high reaches the top).
    bars = [
        (114, 116, 112, 113),
        (113, 114, 110, 111),
        (111, 109, 106, 108),  # bearish gap (109, 112)
        (108, 113, 106, 110),  # high=113 >= 112 → fills the gap
        (110, 112, 100, 102),  # entry
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=120.0, entry_price=102.0, direction='SHORT',
    )
    assert strict is False
    assert loose is False


def test_no_gap_in_window_both_false():
    # All consecutive bars overlap — no 3-bar gap exists.
    bars = [
        (100, 102,  99, 101),
        (101, 103, 100, 102),
        (102, 104, 101, 103),
        (103, 105, 102, 104),
        (104, 106, 103, 105),
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=4,
        sweep_extreme=99.0, entry_price=105.0, direction='LONG',
    )
    assert strict is False
    assert loose is False


def test_window_too_small_returns_false():
    # entry_idx=2 means scan range [2, 2) — empty. Both False.
    bars = [
        (95, 100, 92, 99),
        (99, 103, 98, 102),
        (102, 108, 105, 107),
    ]
    arrs = _arrs(bars)
    strict, loose = ms.find_supporting_fvg(
        arrs, window_start_idx=0, entry_idx=2,
        sweep_extreme=98.0, entry_price=109.0, direction='LONG',
    )
    assert strict is False
    assert loose is False


def test_strict_implies_loose_invariant_random():
    # Property test: for any inputs the helper accepts, strict ⇒ loose.
    # Place sweep and entry INSIDE the bar range so that some candidate FVGs
    # satisfy loose but not strict — otherwise the strict band is so wide
    # that strict ≡ loose and the property is trivially true.
    rng = np.random.RandomState(7)
    long_loose_only_seen = False
    short_loose_only_seen = False
    for _ in range(200):
        n = 8
        opens  = rng.uniform(95, 110, n)
        closes = opens + rng.uniform(-2, 2, n)
        highs  = np.maximum(opens, closes) + rng.uniform(0, 2, n)
        lows   = np.minimum(opens, closes) - rng.uniform(0, 2, n)
        arrs = dict(open=opens, high=highs, low=lows, close=closes)

        # Random sweep / entry inside the range. For LONG, sweep < entry.
        a, b = sorted([float(rng.uniform(lows.min(), highs.max())),
                       float(rng.uniform(lows.min(), highs.max()))])
        long_sweep, long_entry = a, b
        s, l = ms.find_supporting_fvg(arrs, 0, n, long_sweep, long_entry, 'LONG')
        assert (not s) or l, "strict ⇒ loose violated for LONG"
        if l and not s:
            long_loose_only_seen = True

        # For SHORT, sweep > entry (sweep above price, entry below).
        short_sweep, short_entry = b, a
        s, l = ms.find_supporting_fvg(arrs, 0, n, short_sweep, short_entry, 'SHORT')
        assert (not s) or l, "strict ⇒ loose violated for SHORT"
        if l and not s:
            short_loose_only_seen = True

    # Coverage guards: if the construction never exercises the loose-but-not-
    # strict case, the property test is degenerate and should fail loudly.
    assert long_loose_only_seen,  "LONG: strict-false/loose-true case never exercised"
    assert short_loose_only_seen, "SHORT: strict-false/loose-true case never exercised"


from helpers import NS_PER_MIN, BASE_TS, make_controlled_m1


def _build_long_setup_with_known_geometry():
    """Build a minimal LONG setup that triggers detect_setups_base end-to-end.

    Reuses the bar shape from test_detection.py's `test_long_sweep_detected`,
    which is known to produce a valid LONG setup.
    """
    prior = (24000, 24050, 23950, 24000)  # prior HTF candle
    m1_bars = [
        (23960, 23970, 23940, 23955),  # sweeps below 23950
        (23955, 23960, 23948, 23952),  # still below
        (23952, 23960, 23950, 23955),  # returns above 23950
        (23960, 23965, 23955, 23958),  # bearish (CISD setup)
        (23958, 23970, 23955, 23965),  # crosses above CISD level
    ]
    for _ in range(50):
        m1_bars.append((23965, 23975, 23960, 23970))

    cfg = dict(label='Test', sweep_tf_min=60, cisd_tf_min=5,
               min_range=12, session_hrs=(7.0, 16.0))
    tf_step = NS_PER_MIN * cfg['sweep_tf_min']

    s_ts = np.array([BASE_TS, BASE_TS + tf_step], dtype='int64')
    po, ph, pl, pc = prior
    m1_opens = [b[0] for b in m1_bars]
    m1_highs = [b[1] for b in m1_bars]
    m1_lows  = [b[2] for b in m1_bars]
    m1_closes = [b[3] for b in m1_bars]

    s_arrs = dict(
        ts_ns=s_ts,
        open=np.array([po, m1_opens[0]], dtype='float64'),
        high=np.array([ph, max(m1_highs)], dtype='float64'),
        low=np.array([pl, min(m1_lows)], dtype='float64'),
        close=np.array([pc, m1_closes[-1]], dtype='float64'),
        trade_date=np.array(['2023-11-14', '2023-11-14']),
        yr=np.array([2023, 2023], dtype='int32'),
        dow=np.array([2, 2], dtype='int32'),
        hr=np.array([9, 10], dtype='int32'),
    )

    m1_start = int(BASE_TS + tf_step)
    m1 = make_controlled_m1(m1_bars, start_ts=m1_start)
    m1['hr'][:] = 9

    # CISD-TF: same as 1m (matches the test_detection.py convention)
    c_arrs = dict(
        ts_ns=m1['ts_ns'].copy(),
        open=m1['open'].copy(),
        high=m1['high'].copy(),
        low=m1['low'].copy(),
        close=m1['close'].copy(),
        trade_date=m1['trade_date'].copy(),
        yr=m1['yr'].copy(),
        dow=m1['dow'].copy(),
        hr=m1['hr'].copy(),
    )

    return m1, s_arrs, c_arrs, cfg


def test_detect_setups_base_writes_four_fvg_flags():
    """Smoke test: every trade row carries the four supporting-FVG flag
    fields as booleans, and strict ⇒ loose holds per TF."""
    m1, s_arrs, c_arrs, cfg = _build_long_setup_with_known_geometry()
    rows, _ = ms.detect_setups_base(m1, s_arrs, c_arrs, '1H_5M', cfg)

    assert len(rows) > 0, "expected at least one row from detect_setups_base"
    for row in rows:
        for key in ('passes_fvg_cisd_strict', 'passes_fvg_cisd_loose',
                    'passes_fvg_1m_strict',  'passes_fvg_1m_loose'):
            assert key in row, f"row missing {key}: keys are {list(row.keys())}"
            assert isinstance(row[key], bool), f"{key} is {type(row[key])}, not bool"
        # strict ⇒ loose invariant per TF
        assert (not row['passes_fvg_cisd_strict']) or row['passes_fvg_cisd_loose']
        assert (not row['passes_fvg_1m_strict'])   or row['passes_fvg_1m_loose']


def _wl_fixture_for_fvg_summary():
    """Hand-built minimal trade DataFrame mimicking what detect+resolve produces.
    Six trades with varied flag combinations to verify aggregation cells.

    Note: build_model_stats does many other aggregations (heatmaps, recent_trades,
    etc.) that need typical column shapes. This fixture extends _make_resolved_df's
    style with the four FVG columns added.
    """
    rng = np.random.RandomState(7)
    n = 30
    outcomes = rng.choice(['WIN', 'LOSS'], n, p=[0.5, 0.5])
    r_vals = np.where(outcomes == 'WIN', 1.0, -1.0)

    df = pd.DataFrame({
        'date': [f'2023-{((i % 12) + 1):02d}-{((i % 28) + 1):02d}' for i in range(n)],
        'yr': 2023,
        'dow': rng.choice(range(1, 6), n),
        'direction': rng.choice(['LONG', 'SHORT'], n),
        'ref_range': rng.uniform(15, 60, n),
        'sweep_ext': rng.uniform(3, 20, n),
        'sweep_pct': rng.uniform(0.05, 0.49, n),
        'sweep_extreme': rng.uniform(23900, 24100, n),
        'sweep_mode': 'PREV',
        'cisd_mode': 'CISD',
        'ref_lookback': 1,
        # Deliberately distinct counts so a mask-wiring regression (e.g. swapping
        # cisd_strict and m1_strict) flips literal-count assertions in the test
        # below. n=30; counts chosen to be pairwise distinct.
        'smt':                     [True]*10 + [False]*20,                    # n_smt = 10
        'passes_fvg_cisd_strict':  [True]* 5 + [False]*25,                    # n=5
        'passes_fvg_cisd_loose':   [True]*12 + [False]*18,                    # n=12 — superset of cisd_strict
        'passes_fvg_1m_strict':    [True]* 8 + [False]*22,                    # n=8
        'passes_fvg_1m_loose':     [True]*15 + [False]*15,                    # n=15 — superset of m1_strict
        'hr': rng.choice(range(8, 16), n),
        'mn': rng.choice(range(0, 60, 5), n),
        'session': 'NY1',
        'entry_price': rng.uniform(23900, 24100, n).round(2),
        'base_risk': rng.uniform(10, 80, n).round(2),
        'cisd_level': rng.uniform(23900, 24100, n).round(2),
        'hour_range_pts': rng.uniform(20, 100, n).round(2),
        'rejected_by': '',
        'stop_price': rng.uniform(23850, 24050, n).round(2),
        'target_price': rng.uniform(23950, 24150, n).round(2),
        'risk_pts': rng.uniform(10, 80, n).round(2),
        'outcome': outcomes,
        'r': r_vals,
        'mae_pct': rng.uniform(0.01, 0.5, n).round(4),
        'mfe_pct': rng.uniform(0.05, 2.0, n).round(4),
        'mae_pct_hr': rng.uniform(1, 80, n).round(4),
        'mfe_pct_hr': rng.uniform(5, 300, n).round(4),
    })
    # Enforce strict ⇒ loose per TF (matches engine invariant)
    df.loc[df['passes_fvg_cisd_strict'], 'passes_fvg_cisd_loose'] = True
    df.loc[df['passes_fvg_1m_strict'],   'passes_fvg_1m_loose']   = True
    return df


def test_fvg_summary_block_exists_with_expected_keys():
    df = _wl_fixture_for_fvg_summary()
    cfg = dict(label='Test', sweep_tf_min=60, cisd_tf_min=5,
               min_range=12, session_hrs=(7.0, 16.0))
    stats = ms.build_model_stats(df, trading_days=100, model_key='1H_5M',
                                  model_cfg=cfg,
                                  stop_mult=1.0, target_mult=1.0,
                                  profile_key='simple_1r', profile_type='mult')
    assert 'fvg_summary' in stats
    fs = stats['fvg_summary']
    expected = ['cisd_strict', 'cisd_loose', 'no_cisd_fvg',
                'm1_strict',   'm1_loose',   'no_m1_fvg',
                'any_strict',  'any_loose',
                'cisd_strict_smt', 'm1_strict_smt', 'any_strict_smt']
    for key in expected:
        assert key in fs, f"fvg_summary missing key: {key}"
        leaf = fs[key]
        for leaf_key in ('n', 'wins', 'wr', 'ev', 'pf'):
            assert leaf_key in leaf, f"fvg_summary[{key!r}] missing {leaf_key}"


def test_fvg_summary_counts_match_masks():
    """Verify each cell's `n` matches the literal count expected from the
    deterministic fixture. Catches mask-wiring regressions: if the engine
    swaps cisd and m1 masks, the literal-count assertions break."""
    df = _wl_fixture_for_fvg_summary()
    cfg = dict(label='Test', sweep_tf_min=60, cisd_tf_min=5,
               min_range=12, session_hrs=(7.0, 16.0))
    stats = ms.build_model_stats(df, trading_days=100, model_key='1H_5M',
                                  model_cfg=cfg,
                                  stop_mult=1.0, target_mult=1.0,
                                  profile_key='simple_1r', profile_type='mult')
    fs = stats['fvg_summary']

    # Fixture has these distinct counts (n=30):
    #   cisd_strict=5, cisd_loose=12, m1_strict=8, m1_loose=15, smt=10.
    # Strict rows are subsets of their loose counterparts (indices 0..N-1 each).
    # any_strict = cisd_strict ∪ m1_strict = indices 0..7 = 8.
    # any_loose  = cisd_loose  ∪ m1_loose  = indices 0..14 = 15.
    # cisd_strict_smt: cisd_strict (0..4) ∩ smt (0..9) = 5.
    # m1_strict_smt:   m1_strict   (0..7) ∩ smt (0..9) = 8.
    # any_strict_smt:  any_strict  (0..7) ∩ smt (0..9) = 8.
    assert fs['cisd_strict']['n']     == 5
    assert fs['cisd_loose']['n']      == 12
    assert fs['no_cisd_fvg']['n']     == 18   # 30 - 12
    assert fs['m1_strict']['n']       == 8
    assert fs['m1_loose']['n']        == 15
    assert fs['no_m1_fvg']['n']       == 15   # 30 - 15
    assert fs['any_strict']['n']      == 8    # m1_strict ⊃ cisd_strict (since 0..4 ⊂ 0..7)
    assert fs['any_loose']['n']       == 15   # m1_loose  ⊃ cisd_loose
    assert fs['cisd_strict_smt']['n'] == 5
    assert fs['m1_strict_smt']['n']   == 8
    assert fs['any_strict_smt']['n']  == 8
