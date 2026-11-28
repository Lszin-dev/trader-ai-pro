"""TRADER AI PRO background monitor.

Observation-only worker. It supports OTCharts, Twelve Data Forex, or legacy
Yahoo Finance. No provider candle is treated as an executable entry quote.
New CALL/PUT signals remain blocked until a live quote is revalidated.
"""
from __future__ import annotations

import logging
import os
import signal
import time
from typing import Dict, List

import pandas as pd

from data_feed import ATIVOS, get_market_data
from historico import avaliar_sinais_pendentes
from indicators import calculate_indicators
from strategy import analyze_market


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
DATA_PROVIDER = os.getenv("DATA_PROVIDER", "auto").strip().lower()
HAS_OTCHARTS = bool(os.getenv("OTCHARTS_API_KEY"))
HAS_TWELVE_DATA = bool(os.getenv("TWELVE_DATA_API_KEY"))
if DATA_PROVIDER == "auto":
    ACTIVE_PROVIDER = "otcharts" if HAS_OTCHARTS else ("twelvedata" if HAS_TWELVE_DATA else "yahoo")
else:
    ACTIVE_PROVIDER = DATA_PROVIDER

if ACTIVE_PROVIDER not in {"otcharts", "twelvedata", "yahoo"}:
    raise ValueError("DATA_PROVIDER deve ser auto, otcharts, twelvedata ou yahoo.")
if ACTIVE_PROVIDER == "otcharts" and not HAS_OTCHARTS:
    raise RuntimeError("DATA_PROVIDER=otcharts exige OTCHARTS_API_KEY.")
if ACTIVE_PROVIDER == "twelvedata" and not HAS_TWELVE_DATA:
    raise RuntimeError("DATA_PROVIDER=twelvedata exige TWELVE_DATA_API_KEY.")

DEFAULT_INTERVAL = "120" if ACTIVE_PROVIDER == "twelvedata" else ("65" if ACTIVE_PROVIDER == "otcharts" else "60")
SCAN_INTERVAL_SECONDS = max(60, int(os.getenv("SCAN_INTERVAL_SECONDS", DEFAULT_INTERVAL)))
OTCHARTS_VENUE = os.getenv("OTCHARTS_VENUE", "iq").strip().lower()
OTCHARTS_MAX_SYMBOLS = max(1, int(os.getenv("OTCHARTS_MAX_SYMBOLS", "5")))
OTCHARTS_SYMBOLS = [
    item.strip()
    for item in os.getenv("OTCHARTS_SYMBOLS", "").split(",")
    if item.strip()
]
TWELVE_DATA_SYMBOLS = [
    item.strip()
    for item in os.getenv("TWELVE_DATA_SYMBOLS", "EUR/USD").split(",")
    if item.strip()
]
CATALOG_REFRESH_SECONDS = 900

RUNNING = True
_SYMBOL_CACHE: List[str] = []
_SYMBOL_CACHE_AT = 0.0

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("trader_ai_pro.worker")


def _stop_worker(signum, _frame):
    global RUNNING
    logger.info("Sinal de encerramento recebido (%s). Finalizando ciclo.", signum)
    RUNNING = False


def _resample_5m(data_1m: pd.DataFrame) -> pd.DataFrame:
    """Build closed five-minute candles from the validated one-minute feed."""
    data = data_1m[["open", "high", "low", "close"]].copy()
    result = data.resample("5min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    counts = data["close"].resample("5min", label="left", closed="left").count()
    return result.loc[counts == 5].dropna()


def _get_otcharts_symbols(feed) -> List[str]:
    global _SYMBOL_CACHE, _SYMBOL_CACHE_AT
    if OTCHARTS_SYMBOLS:
        return OTCHARTS_SYMBOLS[:OTCHARTS_MAX_SYMBOLS]
    now = time.monotonic()
    if not _SYMBOL_CACHE or now - _SYMBOL_CACHE_AT >= CATALOG_REFRESH_SECONDS:
        catalogue = feed.list_symbols(OTCHARTS_VENUE)
        _SYMBOL_CACHE = [
            item["symbol"] for item in catalogue if item.get("open") is not False
        ][:OTCHARTS_MAX_SYMBOLS]
        _SYMBOL_CACHE_AT = now
        logger.info("Catálogo %s atualizado: %s instrumento(s).", OTCHARTS_VENUE, len(_SYMBOL_CACHE))
    return list(_SYMBOL_CACHE)


def _analyze_frames(asset_key: str, data_1m: pd.DataFrame) -> Dict[str, object]:
    data_5m = _resample_5m(data_1m)
    if len(data_5m) < 30:
        raise ValueError("Histórico 5M insuficiente após agregar candles 1M fechados.")
    result = analyze_market(
        calculate_indicators(data_1m),
        calculate_indicators(data_5m),
    )
    signal = result.get("signal", "AGUARDAR")
    reason = result.get("reason", "")
    if signal in ("CALL", "PUT"):
        logger.warning(
            "%s candidato=%s; NÃO PUBLICADO: falta cotação executável ao vivo "
            "e revalidação no instante de entrada. %s", asset_key, signal, reason
        )
    else:
        logger.info("%s: sem confirmação. %s", asset_key, reason)
    return {"asset": asset_key, "status": "observed", "signal": signal, "reason": reason}


def scan_otcharts_symbol(feed, symbol: str) -> Dict[str, object]:
    asset_key = f"{OTCHARTS_VENUE.upper()}:{symbol}"
    try:
        data_1m = feed.get_candles(
            OTCHARTS_VENUE, symbol, timeframe_seconds=60, limit=1000, max_age_seconds=90
        )
        outcome = _analyze_frames(asset_key, data_1m)
        outcome["evaluated"] = avaliar_sinais_pendentes(asset_key, data_1m)
        return outcome
    except Exception as exc:
        logger.warning("%s: monitoramento indisponível: %s", asset_key, exc)
        return {"asset": asset_key, "status": "error", "signal": "AGUARDAR", "evaluated": 0, "reason": str(exc)}


def scan_twelvedata_symbol(feed, symbol: str) -> Dict[str, object]:
    asset_key = f"FOREX:{symbol.replace('/', '')}"
    try:
        data_1m = feed.get_candles(
            symbol=symbol, interval="1min", outputsize=250, max_age_seconds=150
        )
        # Do not evaluate legacy history with a different price source.
        return _analyze_frames(asset_key, data_1m)
    except Exception as exc:
        logger.warning("%s: monitoramento indisponível: %s", asset_key, exc)
        return {"asset": asset_key, "status": "error", "signal": "AGUARDAR", "reason": str(exc)}


def scan_yahoo_asset(asset: str) -> Dict[str, object]:
    try:
        data_1m = get_market_data(asset, 1)
        data_5m = get_market_data(asset, 5)
        evaluated = avaliar_sinais_pendentes(asset, data_1m)
        result = analyze_market(calculate_indicators(data_1m), calculate_indicators(data_5m))
        signal_value = result.get("signal", "AGUARDAR")
        if signal_value in ("CALL", "PUT"):
            logger.warning("%s candidato=%s; NÃO PUBLICADO: Yahoo não é cotação executável da plataforma. %s", asset, signal_value, result.get("reason", ""))
        else:
            logger.info("%s: sem confirmação. %s", asset, result.get("reason", ""))
        return {"asset": asset, "status": "observed", "signal": signal_value, "evaluated": evaluated, "reason": result.get("reason", "")}
    except Exception as exc:
        logger.warning("%s: monitoramento indisponível: %s", asset, exc)
        return {"asset": asset, "status": "error", "signal": "AGUARDAR", "evaluated": 0, "reason": str(exc)}


def run_cycle() -> Dict[str, int]:
    totals = {"assets": 0, "observed": 0, "errors": 0, "evaluated": 0}
    if ACTIVE_PROVIDER == "otcharts":
        from otcharts_feed import OTChartsFeed
        feed = OTChartsFeed()
        symbols = _get_otcharts_symbols(feed)
        for symbol in symbols:
            if not RUNNING:
                break
            result = scan_otcharts_symbol(feed, symbol)
            totals["assets"] += 1
            totals["evaluated"] += int(result.get("evaluated", 0))
            totals["observed" if result["status"] == "observed" else "errors"] += 1
    elif ACTIVE_PROVIDER == "twelvedata":
        from twelvedata_feed import TwelveDataFeed
        feed = TwelveDataFeed()
        for symbol in TWELVE_DATA_SYMBOLS:
            if not RUNNING:
                break
            result = scan_twelvedata_symbol(feed, symbol)
            totals["assets"] += 1
            totals["observed" if result["status"] == "observed" else "errors"] += 1
    else:
        for asset in ATIVOS:
            if not RUNNING:
                break
            result = scan_yahoo_asset(asset)
            totals["assets"] += 1
            totals["evaluated"] += int(result.get("evaluated", 0))
            totals["observed" if result["status"] == "observed" else "errors"] += 1
    logger.info("Ciclo concluído: %s", totals)
    return totals


def main():
    signal.signal(signal.SIGTERM, _stop_worker)
    signal.signal(signal.SIGINT, _stop_worker)
    logger.info(
        "TRADER AI PRO monitor iniciado; fonte=%s intervalo=%ss modo=OBSERVAÇÃO",
        ACTIVE_PROVIDER, SCAN_INTERVAL_SECONDS
    )
    if ACTIVE_PROVIDER == "twelvedata":
        logger.info(
            "Twelve Data: símbolos=%s. Ciclo mínimo de 120s para preservar a cota gratuita; "
            "candles servem para análise, não para preço de entrada.",
            TWELVE_DATA_SYMBOLS
        )
    while RUNNING:
        started = time.monotonic()
        try:
            run_cycle()
        except Exception:
            logger.exception("Falha não tratada no ciclo do monitor.")
        elapsed = time.monotonic() - started
        wait_seconds = max(1, SCAN_INTERVAL_SECONDS - int(elapsed))
        for _ in range(wait_seconds):
            if not RUNNING:
                break
            time.sleep(1)
    logger.info("TRADER AI PRO monitor encerrado.")


if __name__ == "__main__":
    main()
