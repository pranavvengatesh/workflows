import yfinance as yf
import pandas as pd
import requests
import time
import os
from datetime import datetime

# =================================================
# TELEGRAM CONFIG (use secrets in GitHub later)
# =================================================
BOT_TOKEN = "8203480467:AAFEdb9TdfN4vOjSyewSdOQLRp9SMb_BU-A"
CHAT_ID = "1610629871"

# =================================================
# PATHS
# =================================================
CSV_FILE = "nifty_500.csv"
ALERT_LOG = "alerted_daily.txt"

# 🔥 SAME LOOKBACKS AS YOUR PERFECT VERSION
LOOKBACKS = [10, 12, 15, 20, 30, 40]

# =================================================
# LOAD SYMBOLS
# =================================================
def load_symbols():
    df = pd.read_csv(CSV_FILE)
    col = "Symbol" if "Symbol" in df.columns else "SYMBOL"
    return [s.strip() + ".NS" for s in df[col].dropna().unique()]

# =================================================
# TELEGRAM ALERT
# =================================================
def send_alert(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=10)

# =================================================
# DAILY ALERT DEDUP
# =================================================
def already_alerted(symbol):
    if not os.path.exists(ALERT_LOG):
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    return f"{symbol}|{today}" in open(ALERT_LOG).read()

def mark_alerted(symbol):
    today = datetime.now().strftime("%Y-%m-%d")
    with open(ALERT_LOG, "a") as f:
        f.write(f"{symbol}|{today}\n")

# =================================================
# WEEKLY DATA (STRUCTURE)
# =================================================
def get_weekly(symbol):
    try:
        df = yf.download(
            symbol, period="5y", interval="1wk",
            auto_adjust=False, progress=False
        )

        if df.empty or len(df) < 40:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        return df.dropna()
    except:
        return None

# =================================================
# DAILY DATA (ENTRY CHECK)
# =================================================
def get_daily(symbol):
    try:
        df = yf.download(
            symbol, period="3mo", interval="1d",
            auto_adjust=False, progress=False
        )

        if df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        return df.dropna()
    except:
        return None

# =================================================
# TREND FILTER (UNCHANGED)
# =================================================
def bullish_trend(df):
    ema50 = df["Close"].ewm(span=50).mean().iloc[-1].item()
    ema200 = df["Close"].ewm(span=200).mean().iloc[-1].item()
    close = df["Close"].iloc[-1].item()
    return ema50 > ema200 and close > ema200

# =================================================
# SWING DETECTOR (UNCHANGED – YOUR LOGIC)
# =================================================
def get_half_bat_swing(df, lookback):
    recent = df.tail(lookback)

    low_idx = recent["Low"].idxmin()
    after_low = df.loc[low_idx:]

    if len(after_low) < 4:
        return None

    high_idx = after_low["High"].idxmax()
    if high_idx <= low_idx:
        return None

    low = df.loc[low_idx, "Low"]
    high = df.loc[high_idx, "High"]

    if (high - low) / low < 0.06:
        return None

    return low, high

# =================================================
# WEEKLY STRUCTURE + DAILY ENTRY
# =================================================
def half_bat_entry(df_weekly, df_daily):
    if not bullish_trend(df_weekly):
        return None

    best = None
    best_range = 0

    # 🔒 SAME SWING SELECTION AS YOUR PERFECT CODE
    for lb in LOOKBACKS:
        swing = get_half_bat_swing(df_weekly, lb)
        if not swing:
            continue

        low, high = swing
        if (high - low) > best_range:
            best = (low, high)
            best_range = high - low

    if not best:
        return None

    swing_low, swing_high = best

    fib_50  = swing_high - (swing_high - swing_low) * 0.50
    fib_618 = swing_high - (swing_high - swing_low) * 0.618
    fib_786 = swing_high - (swing_high - swing_low) * 0.786

    # ❌ Weekly invalidation
    if df_weekly["Low"].min() < fib_786:
        return None

    # =================================================
    # DAILY ENTRY CHECK (THIS IS THE ONLY NEW PART)
    # =================================================
    last = df_daily.iloc[-1]
    prev = df_daily.iloc[-2]

    touched_today = (
        (prev["Low"] > fib_618 and last["Low"] <= fib_618)
        or
        (prev["Close"] > fib_50 and last["Close"] <= fib_50)
    )

    # Daily confirmation candle
    if touched_today and last["Close"] > last["Open"]:
        return round(fib_618, 2), round(fib_50, 2)

    return None

# =================================================
# SCANNER
# =================================================
def run_scanner():
    symbols = load_symbols()
    found = False

    for i, sym in enumerate(symbols, 1):
        print(f"{i}/{len(symbols)} → {sym}")

        if already_alerted(sym):
            continue

        df_weekly = get_weekly(sym)
        df_daily = get_daily(sym)

        if df_weekly is None or df_daily is None:
            continue

        result = half_bat_entry(df_weekly, df_daily)
        if result:
            f618, f50 = result
            found = True

            send_alert(
                f"🚨 HALF BAT DAILY ENTRY\n"
                f"{sym}\n"
                f"Weekly PRZ: {f618} – {f50}\n"
                f"Daily touch confirmed ✅"
            )

            mark_alerted(sym)

        time.sleep(1.2)

    if not found:
        send_alert("ℹ️ Daily check complete — No PRZ entries today")

# =================================================
# RUN
# =================================================
if __name__ == "__main__":
    run_scanner()
