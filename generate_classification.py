import pandas as pd
import numpy as np

# -----------------------------
# LOAD INTRADAY DATA
# -----------------------------

df = pd.read_csv("intraday_5m.csv")

df["Datetime"] = pd.to_datetime(df["Datetime"])
df["Date"] = df["Datetime"].dt.date


# -----------------------------
# DETECT HALF DAYS
# -----------------------------

bars_per_day = df.groupby("Date").size()

# normal futures session ≈ 288 five-minute bars
FULL_DAY_THRESHOLD = 250

half_days = bars_per_day[bars_per_day < FULL_DAY_THRESHOLD].index


# -----------------------------
# BUILD DAILY OHLC
# -----------------------------

daily = df.groupby("Date").agg({
    "Open": "first",
    "High": "max",
    "Low": "min",
    "Close": "last"
}).reset_index()

daily["range"] = daily["High"] - daily["Low"]
daily["body"] = abs(daily["Close"] - daily["Open"])

# close location value
daily["clv"] = (daily["Close"] - daily["Low"]) / daily["range"]

# rolling volatility baseline
daily["avg_range"] = daily["range"].rolling(20).mean()

daily["range_ratio"] = daily["range"] / daily["avg_range"]


# -----------------------------
# CLASSIFICATION FUNCTION
# -----------------------------

def classify_day(row):

    if row["Date"] in half_days:
        return "HALF_DAY"

    if pd.isna(row["avg_range"]):
        return None

    clv = row["clv"]
    rr = row["range_ratio"]

    # directional closes near extremes
    if clv > 0.8 or clv < 0.2:

        # strong expansion
        if rr > 1.3:
            return "DNP"

        else:
            return "DWP"

    # rotational closes near middle
    else:

        if rr < 0.8:
            return "R1"

        else:
            return "R2"


daily["DayType"] = daily.apply(classify_day, axis=1)


# -----------------------------
# REMOVE HALF DAYS FOR RESEARCH
# -----------------------------

clean_daily = daily[daily["DayType"] != "HALF_DAY"]


print(daily[["Date","Open","High","Low","Close","DayType"]])