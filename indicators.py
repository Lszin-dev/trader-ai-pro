
import pandas as pd


def calculate_indicators(data):

    data = data.copy()

    # Médias móveis exponenciais
    data["EMA9"] = data["close"].ewm(
        span=9, adjust=False
    ).mean()

    data["EMA21"] = data["close"].ewm(
        span=21, adjust=False
    ).mean()

    # RSI
    delta = data["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1/14, adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1/14, adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(0, float("nan"))

    data["RSI"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = data["close"].ewm(
        span=12, adjust=False
    ).mean()

    ema26 = data["close"].ewm(
        span=26, adjust=False
    ).mean()

    data["MACD"] = ema12 - ema26

    data["MACD_SIGNAL"] = data["MACD"].ewm(
        span=9, adjust=False
    ).mean()

    # ATR
    previous_close = data["close"].shift(1)

    tr = pd.concat([
        data["high"] - data["low"],
        (data["high"] - previous_close).abs(),
        (data["low"] - previous_close).abs()
    ], axis=1).max(axis=1)

    data["ATR"] = tr.rolling(14).mean()

    return data
