import duckdb
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Query a subset (plotting all 4M rows at once is too slow — use daily for overview)
con = duckdb.connect("candle_science.duckdb")
df = con.execute("""
    SELECT 
        DATE_TRUNC('day', timestamp) as date,
        FIRST(open ORDER BY timestamp) as open,
        MAX(high) as high,
        MIN(low) as low,
        LAST(close ORDER BY timestamp) as close,
        SUM(volume) as volume
    FROM nq_1m
    GROUP BY DATE_TRUNC('day', timestamp)
    ORDER BY date
""").df()
con.close()

# Build candlestick chart
fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                    vertical_spacing=0.03,
                    row_heights=[0.75, 0.25])

fig.add_trace(go.Candlestick(
    x=df["date"],
    open=df["open"], high=df["high"],
    low=df["low"], close=df["close"],
    name="NQ1!",
    increasing_line_color="#26a69a",
    decreasing_line_color="#ef5350"
), row=1, col=1)

fig.add_trace(go.Bar(
    x=df["date"], y=df["volume"],
    name="Volume",
    marker_color="#5c6bc0",
    opacity=0.7
), row=2, col=1)

fig.update_layout(
    title="NQ Futures — Daily (2010–2025)",
    xaxis_rangeslider_visible=False,
    template="plotly_dark",
    height=700,
    xaxis=dict(
        rangeselector=dict(buttons=[
            dict(count=3, label="3M", step="month"),
            dict(count=6, label="6M", step="month"),
            dict(count=1, label="1Y", step="year"),
            dict(count=3, label="3Y", step="year"),
            dict(step="all", label="All")
        ])
    )
)

fig.show()