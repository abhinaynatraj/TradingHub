"""
NQ Futures — Auto Update + Daily Outlook
Fetches any missing data from Databento, updates DuckDB, then prints outlook.
Also sends a Mac notification and optional email when done.

Usage:
    python nq_update_and_outlook.py

Schedule it (runs every morning at 7am):
    Mac/Linux cron:  0 7 * * 1-5 /usr/bin/python3 /path/to/nq_update_and_outlook.py
    Windows Task Scheduler: point to this script
"""

import os
import databento as db
import duckdb
import pandas as pd
import pytz
import subprocess
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

# ── Config ─────────────────────────────────────────────────
DB_PATH     = "NQ_futures.duckdb"
DBN_PATH    = "NQ_1m_latest.dbn"
API_KEY     = os.environ.get("DATABENTO_API_KEY", "")   # set via: export DATABENTO_API_KEY=your_key
DATASET     = "GLBX.MDP3"
SYMBOL      = "NQ.c.0"
SCHEMA      = "ohlcv-1m"
STYPE       = "continuous"
TIMEZONE    = "America/Toronto"

# ── Notification Config ────────────────────────────────────
MAC_NOTIFY          = True          # Mac banner notification
EMAIL_NOTIFY        = False         # Set True to enable email
EMAIL_FROM          = "you@gmail.com"
EMAIL_TO            = "you@gmail.com"
EMAIL_PASSWORD      = "YOUR_APP_PASSWORD"   # Gmail App Password (not your login password)
# Gmail setup: myaccount.google.com → Security → App Passwords


# ──────────────────────────────────────────────────────────
def get_last_timestamp(con):
    """Get the latest timestamp already in the DB."""
    result = con.execute("SELECT MAX(timestamp) FROM nq_1m").fetchone()
    return result[0]


def update_database():
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    print(f"[{now.strftime('%Y-%m-%d %H:%M %Z')}] Connecting to database...")
    con = duckdb.connect(DB_PATH)

    last_ts = get_last_timestamp(con)

    if last_ts is None:
        print("  No data found — doing full download from 2010-01-01")
        start = "2010-01-01"
    else:
        # Start from 1 day before last record to avoid gaps
        start = (last_ts - timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"  Last record: {last_ts}")
        print(f"  Fetching from: {start}")

    # End = yesterday close (futures data has ~15min delay)
    end = now.strftime("%Y-%m-%d")

    if start >= end:
        print("  ✅ Database already up to date — no download needed.")
        con.close()
        return

    # ── Fetch from Databento ───────────────────────────────
    print(f"  Downloading {SYMBOL} {SCHEMA} from {start} → {end}...")
    client = db.Historical(API_KEY)

    # Check cost first
    try:
        cost = client.metadata.get_cost(
            dataset=DATASET,
            symbols=[SYMBOL],
            schema=SCHEMA,
            stype_in=STYPE,
            start=start,
            end=end,
        )
        print(f"  Estimated cost: ${cost:.4f}")
    except Exception as e:
        print(f"  ⚠️  Could not estimate cost: {e}")

    # Download
    data = client.timeseries.get_range(
        dataset=DATASET,
        symbols=[SYMBOL],
        schema=SCHEMA,
        stype_in=STYPE,
        start=start,
        end=end,
    )

    # Save .dbn backup
    data.to_file(DBN_PATH)
    print(f"  Saved raw data to {DBN_PATH}")

    # Convert to DataFrame
    df = data.to_df()
    df = df[["open", "high", "low", "close", "volume"]].reset_index()
    df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(TIMEZONE)

    print(f"  Downloaded {len(df):,} rows")

    # ── Upsert into DuckDB ─────────────────────────────────
    # Delete overlapping rows first, then insert fresh data
    con.execute(f"""
        DELETE FROM nq_1m
        WHERE timestamp >= '{df['timestamp'].min()}'
    """)

    con.execute("INSERT INTO nq_1m SELECT * FROM df")

    total = con.execute("SELECT COUNT(*) FROM nq_1m").fetchone()[0]
    latest = con.execute("SELECT MAX(timestamp) FROM nq_1m").fetchone()[0]

    print(f"  ✅ Database updated — {total:,} total rows, latest: {latest}")
    con.close()


# ──────────────────────────────────────────────────────────
def get_outlook():
    con = duckdb.connect(DB_PATH)
    tz  = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    tomorrow = (now + timedelta(days=1)).strftime("%A, %B %-d, %Y")

    LEVEL_DAYS = 20
    VP_LOOKBACK = 5
    TICK_SIZE = 25

    daily = con.execute(f"""
        SELECT
            DATE_TRUNC('day', timestamp)                AS date,
            FIRST(open  ORDER BY timestamp)             AS open,
            MAX(high)                                   AS high,
            MIN(low)                                    AS low,
            LAST(close  ORDER BY timestamp)             AS close,
            SUM(volume)                                 AS volume
        FROM nq_1m
        WHERE timestamp >= NOW() - INTERVAL '{LEVEL_DAYS} days'
        GROUP BY DATE_TRUNC('day', timestamp)
        ORDER BY date
    """).df()

    last_close    = daily["close"].iloc[-1]
    last_date     = daily["date"].iloc[-1]
    swing_high    = daily["high"].max()
    swing_low     = daily["low"].min()
    avg_close     = daily["close"].mean()
    high_3d       = daily["high"].iloc[-3:].max()
    low_3d        = daily["low"].iloc[-3:].min()
    high_5d       = daily["high"].iloc[-5:].max()
    low_5d        = daily["low"].iloc[-5:].min()
    prev          = daily.iloc[-1]
    prev_high     = prev["high"]
    prev_low      = prev["low"]
    prev_close    = prev["close"]
    prev_open     = prev["open"]
    prev_range    = prev_high - prev_low
    prev_midpoint = (prev_high + prev_low) / 2

    vp = con.execute(f"""
        SELECT
            ROUND(close / {TICK_SIZE}) * {TICK_SIZE}    AS level,
            SUM(volume)                                 AS vol
        FROM nq_1m
        WHERE timestamp >= NOW() - INTERVAL '{VP_LOOKBACK} days'
        GROUP BY ROUND(close / {TICK_SIZE}) * {TICK_SIZE}
        ORDER BY vol DESC
        LIMIT 15
    """).df()

    hvn_top3 = vp["level"].iloc[:3].tolist()
    lvn      = vp.sort_values("vol").iloc[0]["level"]

    prev_date_str = last_date.strftime("%Y-%m-%d")
    hourly = con.execute(f"""
        SELECT
            HOUR(timestamp)                         AS hour,
            MAX(high)                               AS high,
            MIN(low)                                AS low,
            LAST(close ORDER BY timestamp)          AS close,
            SUM(volume)                             AS volume
        FROM nq_1m
        WHERE CAST(timestamp AS DATE) = '{prev_date_str}'
        GROUP BY HOUR(timestamp)
        ORDER BY hour
    """).df()

    am_high = hourly[hourly["hour"] < 12]["high"].max()  if not hourly.empty else None
    pm_high = hourly[hourly["hour"] >= 12]["high"].max() if not hourly.empty else None
    am_low  = hourly[hourly["hour"] < 12]["low"].min()   if not hourly.empty else None
    pm_low  = hourly[hourly["hour"] >= 12]["low"].min()  if not hourly.empty else None

    # Bias
    bias_score = 0
    bias_notes = []
    if last_close > avg_close:
        bias_score += 1; bias_notes.append("Close above 20d average")
    else:
        bias_score -= 1; bias_notes.append("Close below 20d average")
    if last_close > prev_midpoint:
        bias_score += 1; bias_notes.append("Close above prior day midpoint")
    else:
        bias_score -= 1; bias_notes.append("Close below prior day midpoint")
    daily["up"] = daily["close"] > daily["open"]
    last3 = daily["up"].iloc[-3:].tolist()
    if all(last3):
        bias_score += 1; bias_notes.append("3 consecutive up days")
    elif not any(last3):
        bias_score -= 1; bias_notes.append("3 consecutive down days")
    if last_close > high_5d * 0.998:
        bias_score += 1; bias_notes.append("Close near 5d high")
    elif last_close < low_5d * 1.002:
        bias_score -= 1; bias_notes.append("Close near 5d low")

    if   bias_score >=  2: bias = "🟢 BULLISH"
    elif bias_score <= -2: bias = "🔴 BEARISH"
    else:                  bias = "🟡 NEUTRAL"

    con.close()

    sep = "=" * 58
    print(f"\n{sep}")
    print(f"  NQ FUTURES DAILY OUTLOOK — {tomorrow}")
    print(f"  Generated: {now.strftime('%Y-%m-%d %H:%M %Z')}")
    print(sep)
    print(f"\n📊 LAST SESSION ({prev_date_str})")
    print(f"   Open:      {prev_open:>10.2f}")
    print(f"   High:      {prev_high:>10.2f}")
    print(f"   Low:       {prev_low:>10.2f}")
    print(f"   Close:     {prev_close:>10.2f}")
    print(f"   Range:     {prev_range:>10.2f} pts")
    print(f"   Midpoint:  {prev_midpoint:>10.2f}")
    if am_high and pm_high:
        print(f"\n   AM High:   {am_high:>10.2f}   AM Low:  {am_low:.2f}")
        print(f"   PM High:   {pm_high:>10.2f}   PM Low:  {pm_low:.2f}")
    print(f"\n📍 KEY LEVELS")
    print(f"   {'Level':<30} {'Price':>10}")
    print(f"   {'-'*42}")
    print(f"   {'20d Swing High':<30} {swing_high:>10.2f}")
    print(f"   {'3d High':<30} {high_3d:>10.2f}")
    print(f"   {'Prior Day High':<30} {prev_high:>10.2f}")
    print(f"   {'Prior Day Midpoint':<30} {prev_midpoint:>10.2f}")
    print(f"   {'20d Avg Close':<30} {avg_close:>10.2f}")
    print(f"   {'Prior Day Low':<30} {prev_low:>10.2f}")
    print(f"   {'3d Low':<30} {low_3d:>10.2f}")
    print(f"   {'20d Swing Low':<30} {swing_low:>10.2f}")
    print(f"\n🔥 HIGH VOLUME NODES (last {VP_LOOKBACK}d)")
    for i, lvl in enumerate(hvn_top3):
        tag = " ← POC" if i == 0 else ""
        print(f"   {lvl:.2f}{tag}")
    print(f"\n🕳  LOW VOLUME NODE:  {lvn:.2f}  (fast move zone)")
    print(f"\n⚖️  BIAS: {bias}")
    for note in bias_notes:
        print(f"   • {note}")
    bull_t1 = round(hvn_top3[0] + 100, -1)
    bull_t2 = round(high_3d,           -1)
    bear_t1 = round(hvn_top3[0] - 100, -1)
    bear_t2 = round(low_3d,            -1)
    print(f"\n📈 SCENARIOS")
    print(f"""
   BULLISH — Hold above {hvn_top3[0]:.0f} (POC)
     Target 1: {bull_t1:.0f}
     Target 2: {bull_t2:.0f}  (3d high)
     Invalidate: Break below {prev_low:.0f}

   BEARISH — Fail at {hvn_top3[0]:.0f} and break {prev_low:.0f}
     Target 1: {bear_t1:.0f}
     Target 2: {bear_t2:.0f}  (3d low)
     Invalidate: Reclaim {prev_high:.0f}

   CHOP — HVN cluster likely contains price between
     {min(hvn_top3):.0f} — {max(hvn_top3):.0f}
""")
    print(f"⚠️  WATCH")
    print(f"   • Check overnight/pre-market vs {hvn_top3[0]:.0f} POC — sets the tone")
    print(f"   • LVN at {lvn:.0f} = fast move zone if tagged")
    print(f"   • Prior day range was {prev_range:.0f} pts — size positions accordingly")
    print(f"\n{sep}\n")


# ──────────────────────────────────────────────────────────
def mac_notify(title, message):
    """Send a Mac banner notification."""
    try:
        script = f'display notification "{message}" with title "{title}" sound name "Ping"'
        subprocess.run(["osascript", "-e", script], check=True)
        print("  🔔 Mac notification sent")
    except Exception as e:
        print(f"  ⚠️  Mac notification failed: {e}")


def send_email(subject, body):
    """Send outlook via Gmail."""
    try:
        msg = MIMEMultipart()
        msg["From"]    = EMAIL_FROM
        msg["To"]      = EMAIL_TO
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print(f"  📧 Email sent to {EMAIL_TO}")
    except Exception as e:
        print(f"  ⚠️  Email failed: {e}")


def build_outlook_text():
    """Returns the outlook as a plain string (for email)."""
    import io, sys
    buffer = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buffer
    get_outlook()
    sys.stdout = old_stdout
    return buffer.getvalue()


# ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    update_database()

    # Build outlook text (used for both print + email)
    outlook_text = build_outlook_text()
    print(outlook_text)

    tz       = pytz.timezone(TIMEZONE)
    now      = datetime.now(tz)
    tomorrow = (now + timedelta(days=1)).strftime("%A %b %-d")

    # Mac notification
    if MAC_NOTIFY:
        # Extract bias line for the notification subtitle
        bias_line = next((l.strip() for l in outlook_text.splitlines() if "BIAS:" in l), "Ready")
        mac_notify(
            title=f"NQ Outlook — {tomorrow}",
            message=bias_line
        )

    # Email
    if EMAIL_NOTIFY:
        send_email(
            subject=f"NQ Futures Outlook — {tomorrow}",
            body=outlook_text
        )
