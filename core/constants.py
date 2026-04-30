"""Shared constants for TradingHub engines.

Import from here to avoid silent divergence between model_stats.py and
ttfm_backtest.py.

DOW CONVENTION NOTE
-------------------
The two engines use different DOW numbering — this is intentional because
each reads from a different source:

  model_stats.py   — uses DuckDB's date_part('dow', ...) → 0=Sun, 1=Mon … 6=Sat
  ttfm_backtest.py — uses pandas dt.dayofweek            → 0=Mon, 1=Tue … 6=Sun

Do NOT unify these without also updating the DuckDB query or the pandas
derivation that depends on them. The constants below cover values that are
truly shared (instrument sizing, timezone string, timestamp precision).
"""

import numpy as np

# ── Timezone ──────────────────────────────────────────────────────────────────
# Timestamps in candle_science.duckdb are stored as America/Toronto.
# Always convert to America/New_York for display and time-window logic.
STORAGE_TZ  = "America/Toronto"
DISPLAY_TZ  = "America/New_York"

# ── Timestamp arithmetic ─────────────────────────────────────────────────────
# Both engines work with int64 nanosecond timestamps internally.
# Use datetime64[ns] when casting — NOT datetime64[us] (pandas 2.0 default).
NS_PER_MIN: np.int64 = np.int64(60_000_000_000)
NS_PER_HOUR: np.int64 = np.int64(60) * NS_PER_MIN

# ── MNQ instrument sizing ─────────────────────────────────────────────────────
# Micro NQ futures: $2.00 per point.  Full NQ = $20.00 per point.
POINT_VALUE_MNQ = 2.0
POINT_VALUE_NQ  = 20.0

# ── RTH session bounds (hour, inclusive start / exclusive end) ─────────────────
RTH_START_HOUR = 7   # 07:00 ET
RTH_END_HOUR   = 16  # 16:00 ET (16:00 bar included for close-of-day)

# ── DOW label maps (kept separate to honour each engine's convention) ─────────
# model_stats.py   → DuckDB dow (0=Sun)
DOW_NAMES_DUCKDB = {0: 'Sun', 1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri', 6: 'Sat'}
# ttfm_backtest.py → pandas dayofweek (0=Mon)
DOW_NAMES_PANDAS = {0: 'Mon', 1: 'Tue', 2: 'Wed', 3: 'Thu', 4: 'Fri'}
