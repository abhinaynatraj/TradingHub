"""Tests for Silver filter — npg's late-week timing + aggressive close gate."""
import pytest
import filters as f


class TestCandleOfDay:
    def test_midnight_is_candle_1(self):
        assert f.candle_of_day(0) == 1   # hour 0–3 → bucket 1

    def test_4am_is_candle_2(self):
        assert f.candle_of_day(4) == 2

    def test_8am_is_candle_3(self):
        assert f.candle_of_day(8) == 3

    def test_noon_is_candle_4(self):
        assert f.candle_of_day(12) == 4

    def test_4pm_is_candle_5(self):
        assert f.candle_of_day(16) == 5

    def test_8pm_is_candle_6(self):
        assert f.candle_of_day(20) == 6


class TestSilverBearish:
    def test_friday_aggressive_close_is_silver(self):
        # Bearish setup: close must be < BOTH prior candles' lows
        # candleOfDay = 5 (hour=16) qualifies on its own
        prev_low = 95.0
        prev_prev_low = 96.0
        last_close = 90.0   # < both prior lows
        hour_et = 16
        is_silver = f.is_silver(direction='SHORT', hour_et=hour_et,
                                last_close=last_close,
                                prev_low=prev_low, prev_prev_low=prev_prev_low,
                                prev_high=110.0, prev_prev_high=109.0)
        assert is_silver is True

    def test_thursday_after_1pm_is_silver(self):
        # Thursday (DOW=4) candle 4 (hour=12) does NOT qualify
        # candleOfDay 4 + hour ≥ 13 → qualifies
        is_silver_12 = f.is_silver(direction='SHORT', hour_et=12,
                                    last_close=90.0,
                                    prev_low=95.0, prev_prev_low=96.0,
                                    prev_high=110.0, prev_prev_high=109.0)
        assert is_silver_12 is False  # candleOfDay=4, hour=12 < 13

        is_silver_13 = f.is_silver(direction='SHORT', hour_et=13,
                                    last_close=90.0,
                                    prev_low=95.0, prev_prev_low=96.0,
                                    prev_high=110.0, prev_prev_high=109.0)
        # hour 13 → candleOfDay = floor(13/4)+1 = 4. Qualifies via 4+hour≥13.
        assert is_silver_13 is True

    def test_close_above_one_prior_low_not_silver(self):
        # candleOfDay qualifies, but close not aggressive enough
        is_silver = f.is_silver(direction='SHORT', hour_et=16,
                                last_close=95.5,    # > prev_low (95)
                                prev_low=95.0, prev_prev_low=96.0,
                                prev_high=110.0, prev_prev_high=109.0)
        assert is_silver is False


class TestSilverBullish:
    def test_friday_aggressive_close_is_silver(self):
        # Bullish: close must be > BOTH prior candles' highs
        is_silver = f.is_silver(direction='LONG', hour_et=16,
                                last_close=115.0,
                                prev_low=95.0, prev_prev_low=96.0,
                                prev_high=110.0, prev_prev_high=112.0)
        assert is_silver is True

    def test_close_below_one_prior_high_not_silver(self):
        is_silver = f.is_silver(direction='LONG', hour_et=16,
                                last_close=111.0,    # < prev_prev_high
                                prev_low=95.0, prev_prev_low=96.0,
                                prev_high=110.0, prev_prev_high=112.0)
        assert is_silver is False


class TestSilverTimingGate:
    def test_morning_hour_no_silver(self):
        # candleOfDay 1, 2, 3 never qualify regardless of close
        for hour in [0, 4, 8]:
            is_silver = f.is_silver(direction='SHORT', hour_et=hour,
                                    last_close=80.0,
                                    prev_low=95.0, prev_prev_low=96.0,
                                    prev_high=110.0, prev_prev_high=109.0)
            assert is_silver is False, f"hour {hour} should not be Silver"
