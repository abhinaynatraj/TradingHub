"""Single source of truth for risk, sizing, and outcome-resolver constants.

Per the Amas Models design spec, Category F (Risk arithmetic): no model file
redefines these values. If a model needs different sizing, it consults
POINT_VALUES[table_name].
"""
from typing import Optional

# Risk gates — applied to every setup before the outcome resolver runs.
# Setups with risk_pts > MAX_RISK_PTS are rejected. With MIN_RISK_PTS = None
# there is no lower floor; arbitrarily tight stops pass.
MIN_RISK_PTS: Optional[float] = None
MAX_RISK_PTS: float = 20.0  # = $400 / $20-per-NQ-point (NQ mini)

# Outcome resolver lookback. A trade unresolved within this many 1m bars is EXPIRED
# (excluded from WR/EV but counted in N). Matches Fractal Sweep.
OUTCOME_MAX_BARS: int = 1440  # 24h of 1m bars

# Per-trade risk in USD. Drives sizing for both NQ and ES via POINT_VALUES.
RISK_PER_TRADE_USD: float = 400.0

# Per-instrument point values (mini contracts). Mapped by DuckDB table name
# (matches the --table CLI arg).
POINT_VALUES: dict[str, float] = {
    "nq_1m": 20.0,  # NQ mini, $20/pt
    "es_1m": 50.0,  # ES mini, $50/pt
}
