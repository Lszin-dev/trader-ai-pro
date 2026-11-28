"""Pure reliability helpers, shared by monitor and replay."""
from datetime import datetime, timezone
import numpy as np
import pandas as pd

def validate_ohlc(frame):
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("Candles exigem índice temporal com fuso.")
    if frame.index.hasnans or not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("Timestamps inválidos, duplicados ou fora de ordem.")
    if not (frame.index == frame.index.floor("min")).all():
        raise ValueError("Timestamps fora da grade de um minuto.")
    data = frame[["open", "high", "low", "close"]]
    if data.empty or not np.isfinite(data.to_numpy(dtype=float)).all() or (data <= 0).any().any():
        raise ValueError("OHLC ausente ou não finito/positivo.")
    if ((data.high < data[["open", "close", "low"]].max(axis=1)) |
        (data.low > data[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("OHLC inconsistente: máximas ou mínimas inválidas.")
    return data

def closed_five_minute(frame):
    data = validate_ohlc(frame)
    groups = data.resample("5min", label="left", closed="left")
    result = groups.agg({"open":"first","high":"max","low":"min","close":"last"})
    return result.loc[groups.size() == 5].dropna()

def advance_confirmation(previous, direction, candle_time, max_gap_seconds=180):
    """Only distinct, ordered candle observations count; gaps reset the streak."""
    if direction not in ("CALL", "PUT") or candle_time is None:
        return None, False
    stamp = pd.Timestamp(candle_time)
    if stamp.tzinfo is None or pd.isna(stamp):
        return None, False
    if previous:
        last = pd.Timestamp(previous["candle"])
        delta = (stamp-last).total_seconds()
        if delta <= 0:
            return previous, False
    else:
        delta = float("inf")
    count = previous["count"] + 1 if previous and previous["signal"] == direction and delta <= max_gap_seconds else 1
    return {"signal":direction,"count":count,"candle":stamp.isoformat()}, True

def quote_is_current(quote, now=None, max_age_seconds=15):
    if not quote.get("valid") or quote.get("cached"):
        return False
    try:
        stamp = pd.Timestamp(quote["quote_timestamp"])
        current = pd.Timestamp(datetime.now(timezone.utc) if now is None else now)
        if stamp.tzinfo is None or current.tzinfo is None:
            return False
        age = (current-stamp).total_seconds()
        return -2 <= age <= max_age_seconds
    except (KeyError, ValueError, TypeError, OverflowError):
        return False
