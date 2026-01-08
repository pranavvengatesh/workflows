import yfinance as yf
import pandas as pd
import requests
import time
import os
from datetime import datetime

# =================================================
# TELEGRAM CONFIG
# =================================================
BOT_TOKEN = "8203480467:AAFEdb9TdfN4vOjSyewSdOQLRp9SMb_BU-A"
CHAT_ID = "1610629871"


# =================================================
# PATHS
# =================================================
CSV_FILE = "nifty_500.csv"
ALERT_LOG = "alerted_weekly.txt"

# 🔥 FAST + SLOW HALF BAT SUPPORT
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
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

# =================================================
# ALERT DEDUP
# =================================================
def already_alerted(symbol):
    if not os.path.exists(ALERT_LOG):
        return False
    wk = datetime.now().strftime("%Y-%W")
    return f"{symbol}|{wk}" in open(ALERT_LOG).read()

def mark_alerted(symbol):
    wk = datetime.now().strftime("%Y-%W")
    with open(ALERT_LOG, "a") as f:
        f.write(f"{symbol}|{wk}\n")

# =================================================
# WEEKLY DATA
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
# TREND FILTER
# =================================================
def bullish_trend(df):
    ema50 = df["Close"].ewm(span=50).mean().iloc[-1].item()
    ema200 = df["Close"].ewm(span=200).mean().iloc[-1].item()
    close = df["Close"].iloc[-1].item()
    return ema50 > ema200 and close > ema200

# =================================================
# SWING DETECTOR (PRICE STRUCTURE BASED)
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

    move_pct = (high - low) / low
    if move_pct < 0.06:   # >= 6% impulse (FAST MARKETS)
        return None

    return low, high

# =================================================
# HALF BAT ENTRY (MATCHES YOUR CHART)
# =================================================
def half_bat_entry(df):
    if not bullish_trend(df):
        return None

    best = None
    best_range = 0

    for lb in LOOKBACKS:
        swing = get_half_bat_swing(df, lb)
        if not swing:
            continue

        low, high = swing
        if (high - low) > best_range:
            best = (low, high)
            best_range = high - low

    if not best:
        return None

    swing_low, swing_high = best

    fib_50 = swing_high - (swing_high - swing_low) * 0.50
    fib_618 = swing_high - (swing_high - swing_low) * 0.618
    fib_786 = swing_high - (swing_high - swing_low) * 0.786

    close = df["Close"].iloc[-1].item()
    open_ = df["Open"].iloc[-1].item()
    low = df["Low"].iloc[-1].item()

    prev_close = df["Close"].iloc[-2].item()
    prev_low = df["Low"].iloc[-2].item()

    # ❌ Invalid deep pullback
    if close < fib_786:
        return None

    # ✅ FRESH TOUCH ONLY
    touched = (
        (prev_low > fib_618 and low <= fib_618)
        or
        (prev_close > fib_50 and close <= fib_50)
    )

    if not touched:
        return None

    # ✅ Bullish confirmation candle
    if close > open_:
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

        df = get_weekly(sym)
        if df is None:
            continue

        result = half_bat_entry(df)
        if result:
            f618, f50 = result
            found = True

            send_alert(
                f"🚨 WEEKLY HALF BAT ENTRY\n"
                f"{sym}\n"
                f"PRZ: {f618} – {f50}\n"
                f"Fast impulse | Fresh pullback ✅"
            )
            mark_alerted(sym)

        time.sleep(1.2)

    if not found:
        send_alert("ℹ️ Weekly scan complete — No Half Bat setups")

# =================================================
# RUN
# =================================================
if __name__ == "__main__":
    send_alert("✅ Half Bat Scanner Started")
    run_scanner()
