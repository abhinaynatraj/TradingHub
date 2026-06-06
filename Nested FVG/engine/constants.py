"""Constants for the Nested FVG backtest — mirrors Kelli/nested-fvg.pine defaults."""
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / 'Fractal Sweep' / 'candle_science.duckdb'
DATA_DIR = Path(__file__).parent.parent / 'data'

# TF nesting pairs: key -> (ltf_min, htf_min)
PAIRINGS = {
    '1m_5m':  (1, 5),
    '3m_15m': (3, 15),
    '5m_30m': (5, 30),
}

# Fixed-point exit (Pine defaults, in index points)
STOP_PTS    = 15.0
PARTIAL_PTS = 15.0
TARGET_PTS  = 45.0
EXT_PTS     = 60.0

# Detection thresholds (Pine defaults)
MIN_FVG_BP   = 0.15   # min gap size in basis points of price
PROXIMITY_BP = 5.0    # nesting tolerance in basis points
COOLDOWN_BARS = 30    # per-direction cooldown in 1m bars

# Sizing / pricing (repo MNQ convention)
POINT_VALUE_USD = 2.0

# Session: full Globex 18:00 ET -> 16:00 ET. Signals only when hour in this window.
# Represented as the set of ET hours that are IN-session.
SESSION_HOURS = set(range(18, 24)) | set(range(0, 16))  # 18..23 and 0..15
SESSION_END_HOUR = 16  # force-close (expiry) at 16:00 ET

OUTCOMES = ('win', 'loss', 'scratch', 'expired')
