"""Tests for CISD detection: _find_cisd() and find_cisd()."""
import numpy as np
import pytest
from helpers import NS_PER_MIN, BASE_TS
import model_stats as ms


def _make_cisd_arrs(bars_data):
    """Build CISD-TF arrays from (open, close) tuples.

    Each bar gets high=max(o,c)+1, low=min(o,c)-1 for simplicity.
    """
    n = len(bars_data)
    ts_ns = np.array([BASE_TS + i * NS_PER_MIN * 5 for i in range(n)], dtype='int64')
    opens = np.array([b[0] for b in bars_data], dtype='float64')
    closes = np.array([b[1] for b in bars_data], dtype='float64')
    highs = np.maximum(opens, closes) + 1.0
    lows = np.minimum(opens, closes) - 1.0
    trade_dates = np.array(['2020-01-01'] * n)
    hrs = np.array([9] * n, dtype='int32')
    return dict(ts_ns=ts_ns, open=opens, close=closes, high=highs, low=lows,
                trade_date=trade_dates, hr=hrs)


# ── Core backward scan ──────────────────────────────────────────────────────

class TestFindCisdBackwardScan:
    def test_3_consecutive_bearish_long(self):
        """3 bearish candles before return → CISD level = open of earliest."""
        # Bars: [bearish, bearish, bearish, (return bar), bullish-cross]
        bars = [
            (24050, 24040),  # 0: bearish (earliest in run)
            (24040, 24030),  # 1: bearish
            (24030, 24020),  # 2: bearish (nearest to return)
            (24020, 24025),  # 3: return bar (start_idx)
            (24025, 24055),  # 4: crosses above CISD → fire
        ]
        arrs = _make_cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=3, n_bars=100, direction='LONG')
        assert lvl == 24050.0  # open of bar 0 (earliest bearish)
        assert ts == arrs['ts_ns'][4]  # fires on bar 4

    def test_3_consecutive_bullish_short(self):
        """3 bullish candles before return → CISD level = open of earliest."""
        bars = [
            (24000, 24010),  # 0: bullish (earliest)
            (24010, 24020),  # 1: bullish
            (24020, 24030),  # 2: bullish (nearest)
            (24030, 24025),  # 3: return bar
            (24025, 23995),  # 4: crosses below CISD → fire
        ]
        arrs = _make_cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=3, n_bars=100, direction='SHORT')
        assert lvl == 24000.0  # open of bar 0
        assert ts == arrs['ts_ns'][4]

    def test_single_bearish_candle(self):
        """Single bearish candle → CISD level = its open."""
        bars = [
            (24010, 24020),  # 0: bullish (breaks the run)
            (24020, 24010),  # 1: bearish (the only one)
            (24010, 24015),  # 2: return bar
            (24015, 24025),  # 3: crosses above → fire
        ]
        arrs = _make_cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=2, n_bars=100, direction='LONG')
        assert lvl == 24020.0  # open of bar 1
        assert ts == arrs['ts_ns'][3]


class TestCisdDojis:
    def test_dojis_skipped_in_run(self):
        """Dojis (close==open) should be skipped, not break the run."""
        bars = [
            (24050, 24040),  # 0: bearish (earliest)
            (24040, 24040),  # 1: DOJI — skipped
            (24040, 24030),  # 2: bearish
            (24030, 24035),  # 3: return bar
            (24035, 24055),  # 4: crosses above
        ]
        arrs = _make_cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=3, n_bars=100, direction='LONG')
        assert lvl == 24050.0  # open of bar 0, doji didn't break run

    def test_all_dojis_before_return(self):
        """All dojis before return → no opposing run → no CISD."""
        bars = [
            (24020, 24020),  # 0: doji
            (24020, 24020),  # 1: doji
            (24020, 24020),  # 2: doji
            (24020, 24025),  # 3: return bar
            (24025, 24030),  # 4: would-be fire
        ]
        arrs = _make_cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=3, n_bars=100, direction='LONG')
        assert ts is None
        assert lvl is None

    def test_doji_at_nearest_position(self):
        """Doji immediately before return → skip it, find bearish further back."""
        bars = [
            (24040, 24030),  # 0: bearish
            (24030, 24030),  # 1: doji (nearest, skipped)
            (24030, 24035),  # 2: return bar
            (24035, 24045),  # 3: fire
        ]
        arrs = _make_cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=2, n_bars=100, direction='LONG')
        assert lvl == 24040.0  # open of bar 0


class TestCisdNoCisd:
    def test_no_opposing_candle(self):
        """Bullish candle before return in LONG setup → no opposing run."""
        bars = [
            (24010, 24020),  # 0: bullish (wrong direction for LONG)
            (24020, 24025),  # 1: return bar
            (24025, 24035),  # 2: would-be fire
        ]
        arrs = _make_cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=1, n_bars=100, direction='LONG')
        assert ts is None
        assert lvl is None

    def test_no_cross_after_cisd_level(self):
        """CISD level found but price never crosses it → no fire."""
        bars = [
            (24050, 24040),  # 0: bearish
            (24040, 24035),  # 1: return bar
            (24035, 24040),  # 2: close < CISD level (24050), no fire
            (24040, 24045),  # 3: still below CISD level
        ]
        arrs = _make_cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=1, n_bars=3, direction='LONG')
        assert ts is None  # never crossed 24050


class TestCisdScanOrigin:
    def test_scan_from_return_bar_not_sweep(self):
        """CISD scans backward from ret_bar, not from sweep bar."""
        # Setup: sweep at bar 1, return at bar 5, CISD run at bars 3-4
        bars = [
            (24010, 24020),  # 0: bullish
            (24020, 24010),  # 1: sweep bar (bearish)
            (24010, 24020),  # 2: bullish (breaks any run from sweep)
            (24030, 24020),  # 3: bearish (part of run before return)
            (24020, 24010),  # 4: bearish (nearest to return)
            (24010, 24015),  # 5: return bar (start_idx)
            (24015, 24035),  # 6: crosses CISD level → fire
        ]
        arrs = _make_cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=5, n_bars=100, direction='LONG')
        # Should find run at bars 3-4, CISD level = open of bar 3
        assert lvl == 24030.0
        assert ts == arrs['ts_ns'][6]

    def test_cisd_fires_many_bars_later(self):
        """CISD fires 10+ bars after return — still valid with no bar limit."""
        bars = [
            (24050, 24040),  # 0: bearish
            (24040, 24045),  # 1: return bar
        ]
        # Add 10 bars that stay below CISD level
        for i in range(10):
            bars.append((24045, 24042))
        # Bar that finally crosses
        bars.append((24045, 24055))

        arrs = _make_cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=1, n_bars=100, direction='LONG')
        assert lvl == 24050.0
        assert ts == arrs['ts_ns'][12]  # fires on bar 12


class TestCisdEdgeCases:
    def test_run_extends_to_start_of_data(self):
        """Bearish run extends all the way to bar 0."""
        bars = [
            (24060, 24050),  # 0: bearish (earliest possible)
            (24050, 24040),  # 1: bearish
            (24040, 24030),  # 2: bearish
            (24030, 24035),  # 3: return
            (24035, 24065),  # 4: fire
        ]
        arrs = _make_cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=3, n_bars=100, direction='LONG')
        assert lvl == 24060.0  # open of bar 0

    def test_multiple_runs_separated_by_same_direction(self):
        """Two opposing runs separated by a same-direction candle → only nearest used."""
        bars = [
            (24080, 24070),  # 0: bearish (older run)
            (24070, 24060),  # 1: bearish
            (24060, 24070),  # 2: BULLISH — breaks the run
            (24070, 24060),  # 3: bearish (newer run start)
            (24060, 24050),  # 4: bearish (newer run)
            (24050, 24055),  # 5: return
            (24055, 24075),  # 6: fire
        ]
        arrs = _make_cisd_arrs(bars)
        ts, lvl = ms._find_cisd(arrs['open'], arrs['close'], arrs['ts_ns'],
                                start_idx=5, n_bars=100, direction='LONG')
        # Should use the newer run (bars 3-4), not the older one (bars 0-1)
        assert lvl == 24070.0  # open of bar 3


class TestFindCisdWrapper:
    def test_find_cisd_uses_searchsorted(self):
        """find_cisd() converts timestamp to index via searchsorted."""
        bars = [
            (24050, 24040),  # 0: bearish
            (24040, 24035),  # 1: return bar
            (24035, 24055),  # 2: fire
        ]
        arrs = _make_cisd_arrs(bars)
        return_ts = int(arrs['ts_ns'][1])
        ts, lvl = ms.find_cisd(arrs, return_ts, 'LONG', max_bars=None, cisd_mode='CISD')
        assert lvl == 24050.0
        assert ts == arrs['ts_ns'][2]

    def test_find_cisd_max_bars_none(self):
        """max_bars=None → scans to end of data."""
        bars = [(24050, 24040), (24040, 24035)]
        # Add 100 bars below CISD level, then one that crosses
        for _ in range(100):
            bars.append((24035, 24032))
        bars.append((24035, 24055))

        arrs = _make_cisd_arrs(bars)
        return_ts = int(arrs['ts_ns'][1])
        ts, lvl = ms.find_cisd(arrs, return_ts, 'LONG', max_bars=None, cisd_mode='CISD')
        assert lvl == 24050.0
        assert ts is not None

    def test_find_cisd_out_of_range_timestamp(self):
        """Timestamp beyond data → returns None."""
        bars = [(24050, 24040), (24040, 24035)]
        arrs = _make_cisd_arrs(bars)
        future_ts = int(arrs['ts_ns'][-1] + NS_PER_MIN * 1000)
        ts, lvl = ms.find_cisd(arrs, future_ts, 'LONG', max_bars=None, cisd_mode='CISD')
        assert ts is None
        assert lvl is None
