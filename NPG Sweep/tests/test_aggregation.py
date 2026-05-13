"""Tests for aggregation: agg(), by-hour, by-DOW, filter-combo enumeration."""
import pytest
import aggregation as a


def _row(composite_r, sl_hit=False, hits=None, hour=10, dow=2,
         silver=False, smt=False, direction='SHORT', mae_pts=5.0, mfe_pts=10.0):
    return dict(
        composite_r=composite_r,
        sl_hit=sl_hit,
        hits=hits or [True, True, False, False],
        hour=hour,
        dow=dow,
        silver=silver,
        smt=smt,
        direction=direction,
        mae_pts=mae_pts,
        mfe_pts=mfe_pts,
    )


class TestAgg:
    def test_basic_metrics(self):
        rows = [
            _row(composite_r=1.25, sl_hit=False),
            _row(composite_r=1.25, sl_hit=False),
            _row(composite_r=-0.5, sl_hit=True, hits=[True, False, False, False]),
            _row(composite_r=-1.0, sl_hit=True, hits=[False]*4),
        ]
        s = a.agg(rows)
        assert s['n'] == 4
        # WR = % reaching at least 1.0× projection (level index 1)
        # rows 0, 1 reached 1.0× (hits[1]=True). row 2 only 0.5×. row 3 none.
        assert s['wr'] == pytest.approx(50.0)
        assert s['ev'] == pytest.approx((1.25 + 1.25 - 0.5 - 1.0) / 4)
        # PF = sum positive R / |sum negative R|
        assert s['pf'] == pytest.approx((1.25 + 1.25) / abs(-0.5 + -1.0))


class TestReachRates:
    def test_reach_rate_per_level(self):
        rows = [
            _row(composite_r=0.0, hits=[True, True, True, True]),
            _row(composite_r=0.0, hits=[True, True, False, False]),
            _row(composite_r=0.0, hits=[True, False, False, False]),
            _row(composite_r=0.0, hits=[False, False, False, False]),
        ]
        s = a.reach_rates(rows)
        # 75% reach 0.5×, 50% reach 1.0×, 25% reach 1.5×, 25% reach 2.0×
        assert s == pytest.approx({'0.5x': 75.0, '1.0x': 50.0, '1.5x': 25.0, '2.0x': 25.0})


class TestByHour:
    def test_groups_by_hour(self):
        rows = [
            _row(composite_r=1.0, hour=10),
            _row(composite_r=1.0, hour=10),
            _row(composite_r=-1.0, hour=14),
        ]
        bh = a.by_hour(rows)
        assert bh[10]['n'] == 2
        assert bh[14]['n'] == 1
        assert bh[10]['ev'] == 1.0
        assert bh[14]['ev'] == -1.0
