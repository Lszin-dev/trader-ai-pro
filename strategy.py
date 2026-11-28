"""Motor de estratégia do TRADER AI PRO.

O score retornado por este módulo mede apenas a qualidade/confluência técnica
segundo as regras implementadas. Ele NÃO é probabilidade de acerto.
"""
from __future__ import annotations

from typing import Dict, Tuple

import pandas as pd


MIN_BARS = 30
MIN_TECHNICAL_SCORE = 76.0


def _wait(reason: str, score: float = 0.0, metrics=None, checks=None) -> Dict[str, object]:
    return {
        "signal": "AGUARDAR",
        "reason": reason,
        "score": round(float(score), 1),
        "quality": "AGUARDAR",
        "metrics": metrics or {},
        "checks": checks or {},
    }


def _quality(score: float) -> str:
    if score >= 88:
        return "MUITO FORTE"
    if score >= 82:
        return "FORTE"
    if score >= MIN_TECHNICAL_SCORE:
        return "BOA"
    return "FRACA"


def _trend_ratio(frame: pd.DataFrame, direction: str, periods: int = 3) -> float:
    tail = frame.tail(periods)
    if direction == "CALL":
        aligned = (tail["EMA9"] > tail["EMA21"]) & (tail["MACD"] > tail["MACD_SIGNAL"])
    else:
        aligned = (tail["EMA9"] < tail["EMA21"]) & (tail["MACD"] < tail["MACD_SIGNAL"])
    return float(aligned.mean()) if len(tail) else 0.0


def _direction_score(data_1m: pd.DataFrame, data_5m: pd.DataFrame, direction: str) -> Tuple[float, dict, dict]:
    last_1m = data_1m.iloc[-1]
    last_5m = data_5m.iloc[-1]

    call = direction == "CALL"
    trend_ratio = _trend_ratio(data_5m, direction, periods=3)
    ema_5_ok = last_5m["EMA9"] > last_5m["EMA21"] if call else last_5m["EMA9"] < last_5m["EMA21"]
    macd_5_ok = last_5m["MACD"] > last_5m["MACD_SIGNAL"] if call else last_5m["MACD"] < last_5m["MACD_SIGNAL"]
    position_5_ok = last_5m["close"] > last_5m["EMA9"] if call else last_5m["close"] < last_5m["EMA9"]

    ema_1_ok = last_1m["EMA9"] > last_1m["EMA21"] if call else last_1m["EMA9"] < last_1m["EMA21"]
    macd_1_ok = last_1m["MACD"] > last_1m["MACD_SIGNAL"] if call else last_1m["MACD"] < last_1m["MACD_SIGNAL"]
    position_1_ok = last_1m["close"] > last_1m["EMA9"] if call else last_1m["close"] < last_1m["EMA9"]

    rsi = float(last_1m["RSI"])
    rsi_ok = 45 <= rsi <= 68 if call else 32 <= rsi <= 55

    reference_close = float(data_1m["close"].iloc[-4])
    momentum_delta = float(last_1m["close"] - reference_close)
    momentum_ok = momentum_delta > 0 if call else momentum_delta < 0

    candle_ok = True
    if "open" in data_1m.columns:
        candle_ok = last_1m["close"] >= last_1m["open"] if call else last_1m["close"] <= last_1m["open"]

    atr_1 = float(last_1m["ATR"])
    atr_5 = float(last_5m["ATR"])
    close_1 = float(last_1m["close"])
    close_5 = float(last_5m["close"])
    atr_pct_1 = atr_1 / close_1 if close_1 > 0 else 0.0
    atr_pct_5 = atr_5 / close_5 if close_5 > 0 else 0.0

    ema_gap_5_atr = abs(float(last_5m["EMA9"] - last_5m["EMA21"])) / atr_5 if atr_5 > 0 else 0.0
    gap_strength = min(1.0, ema_gap_5_atr / 0.30)

    score = 0.0
    score += 25.0 * trend_ratio
    score += 8.0 if ema_5_ok else 0.0
    score += 7.0 if macd_5_ok else 0.0
    score += 8.0 if position_5_ok else 0.0
    score += 10.0 * gap_strength
    score += 10.0 if ema_1_ok else 0.0
    score += 9.0 if macd_1_ok else 0.0
    score += 8.0 if position_1_ok else 0.0
    score += 7.0 if rsi_ok else 0.0
    score += 5.0 if momentum_ok else 0.0
    score += 3.0 if candle_ok else 0.0

    checks = {
        "trend_5m_consistent": trend_ratio >= (2 / 3),
        "ema_5m": bool(ema_5_ok),
        "macd_5m": bool(macd_5_ok),
        "price_5m": bool(position_5_ok),
        "ema_1m": bool(ema_1_ok),
        "macd_1m": bool(macd_1_ok),
        "price_1m": bool(position_1_ok),
        "rsi_1m": bool(rsi_ok),
        "momentum_1m": bool(momentum_ok),
        "candle_1m": bool(candle_ok),
    }
    metrics = {
        "rsi_1m": round(rsi, 2),
        "atr_pct_1m": round(atr_pct_1 * 100, 5),
        "atr_pct_5m": round(atr_pct_5 * 100, 5),
        "trend_consistency_5m": round(trend_ratio * 100, 1),
        "ema_gap_5m_atr": round(ema_gap_5_atr, 3),
        "momentum_3m": momentum_delta,
    }
    return min(score, 100.0), metrics, checks


def analyze_market(data_1m: pd.DataFrame, data_5m: pd.DataFrame) -> Dict[str, object]:
    """Analisa 1M + 5M e retorna sinal candidato explicável.

    CALL/PUT só são devolvidos quando há tendência consistente em 5M,
    alinhamento em 1M, momentum favorável e score técnico mínimo.
    """
    if len(data_1m) < MIN_BARS or len(data_5m) < MIN_BARS:
        return _wait("Dados insuficientes para confirmar a tendência.")

    required = ["EMA9", "EMA21", "RSI", "MACD", "MACD_SIGNAL", "ATR", "close"]
    for frame in (data_1m, data_5m):
        if any(column not in frame.columns for column in required):
            return _wait("Indicadores obrigatórios ausentes.")
        if frame.iloc[-1][required].isna().any():
            return _wait("Indicadores incompletos.")

    last_1m = data_1m.iloc[-1]
    last_5m = data_5m.iloc[-1]
    if float(last_1m["ATR"]) <= 0 or float(last_5m["ATR"]) <= 0:
        return _wait("Volatilidade insuficiente.")

    close_1 = float(last_1m["close"])
    atr_pct_1 = float(last_1m["ATR"]) / close_1 if close_1 > 0 else 0.0
    if atr_pct_1 < 0.00002:
        return _wait("Volatilidade muito baixa para uma leitura confiável.")
    if atr_pct_1 > 0.02:
        return _wait("Volatilidade anormalmente alta; aguardando estabilização.")

    candidates = []
    for direction in ("CALL", "PUT"):
        score, metrics, checks = _direction_score(data_1m, data_5m, direction)
        hard_checks = (
            checks["trend_5m_consistent"],
            checks["ema_5m"],
            checks["macd_5m"],
            checks["ema_1m"],
            checks["macd_1m"],
            checks["price_1m"],
            checks["rsi_1m"],
            checks["momentum_1m"],
        )
        if all(hard_checks):
            candidates.append((direction, score, metrics, checks))

    if not candidates:
        return _wait("1M e 5M ainda não formaram uma confluência suficientemente consistente.")

    direction, score, metrics, checks = max(candidates, key=lambda item: item[1])
    if score < MIN_TECHNICAL_SCORE:
        return _wait(
            f"Confluência parcial detectada, mas score técnico {score:.1f}/100 abaixo do mínimo {MIN_TECHNICAL_SCORE:.0f}.",
            score,
            metrics,
            checks,
        )

    label = "alta" if direction == "CALL" else "baixa"
    return {
        "signal": direction,
        "reason": (
            f"Confluência de {label} confirmada em 5M e 1M; "
            f"score técnico {score:.1f}/100 ({_quality(score)})."
        ),
        "score": round(score, 1),
        "quality": _quality(score),
        "metrics": metrics,
        "checks": checks,
    }
