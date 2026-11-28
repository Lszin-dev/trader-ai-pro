"""TRADER AI PRO background monitor.

Observation-only worker. It can use OTCharts (broker-aligned read-only feed)
when OTCHARTS_API_KEY is configured, or the legacy Yahoo feed otherwise.
It never publishes a signal: entry publication remains blocked until a live
entry quote is revalidated at the exact entry moment and safely persisted.
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
HAS_OTCHARTS = bool(os.getenv("OTCHARTS_API_KEY"))
SCAN_INTERVAL_SECONDS = max(
    30,
    int(os.getenv("SCAN_INTERVAL_SECONDS", "65" if HAS_OTCHARTS else "60")),
)
OTCHARTS_VENUE = os.getenv("OTCHARTS_VENUE", "iq").strip().lower()
OTCHARTS_MAX_SYMBOLS = max(1, int(os.getenv("OTCHARTS_MAX_SYMBOLS", "5")))
OTCHARTS_SYMBOLS = [
    item.strip()
    for item in os.getenv("OTCHARTS_SYMBOLS", "").split(",")
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
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
        }
    )
    counts = data["close"].resample("5min", label="left", closed="left").count()
    result = result.loc[counts == 5].dropna()
    return result


def _get_otcharts_symbols(feed) -> List[str]:
    global _SYMBOL_CACHE, _SYMBOL_CACHE_AT

    if OTCHARTS_SYMBOLS:
        return OTCHARTS_SYMBOLS[:OTCHARTS_MAX_SYMBOLS]

    now = time.monotonic()
    if not _SYMBOL_CACHE or now - _SYMBOL_CACHE_AT >= CATALOG_REFRESH_SECONDS:
        catalogue = feed.list_symbols(OTCHARTS_VENUE)
        _SYMBOL_CACHE = [
            item["symbol"]
            for item in catalogue
            if item.get("open") is not False
        ][:OTCHARTS_MAX_SYMBOLS]
        _SYMBOL_CACHE_AT = now
        logger.info(
            "Catálogo %s atualizado: %s instrumento(s) selecionado(s).",
            OTCHARTS_VENUE,
            len(_SYMBOL_CACHE),
        )
    return list(_SYMBOL_CACHE)


def scan_otcharts_symbol(feed, symbol: str) -> Dict[str, object]:
    asset_key = f"{OTCHARTS_VENUE.upper()}:{symbol}"
    outcome: Dict[str, object] = {
        "asset": asset_key,
        "status": "error",
        "signal": "AGUARDAR",
        "evaluated": 0,
        "reason": "",
    }

    try:
        # One 1m request per symbol/cycle; 5m candles are built locally to
        # conserve the provider's daily request allowance.
        data_1m = feed.get_candles(
            OTCHARTS_VENUE,
            symbol,
            timeframe_seconds=60,
            limit=300,
            max_age_seconds=90,
        )
        data_5m = _resample_5m(data_1m)
        if len(data_5m) < 30:
            raise ValueError("Histórico 5M insuficiente após agregação.")

        outcome["evaluated"] = avaliar_sinais_pendentes(asset_key, data_1m)
        result = analyze_market(
            calculate_indicators(data_1m),
            calculate_indicators(data_5m),
        )
        outcome["signal"] = result.get("signal", "AGUARDAR")
        outcome["reason"] = result.get("reason", "")
        outcome["status"] = "observed"

        if outcome["signal"] in ("CALL", "PUT"):
            logger.warning(
                "%s candidato=%s; não publicado: aguardando cotação "
                "executável e revalidação no instante de entrada. %s",
                asset_key,
                outcome["signal"],
                outcome["reason"],
            )
        else:
            logger.info("%s: sem confirmação. %s", asset_key, outcome["reason"])

    except Exception as exc:
        outcome["reason"] = str(exc)
        logger.warning("%s: monitoramento indisponível: %s", asset_key, exc)

    return outcome


def scan_yahoo_asset(asset: str) -> Dict[str, object]:
    outcome: Dict[str, object] = {
        "asset": asset,
        "status": "error",
        "signal": "AGUARDAR",
        "evaluated": 0,
        "reason": "",
    }
    try:
        data_1m = get_market_data(asset, 1)
        data_5m = get_market_data(asset, 5)
        outcome["evaluated"] = avaliar_sinais_pendentes(asset, data_1m)
        result = analyze_market(
            calculate_indicators(data_1m),
            calculate_indicators(data_5m),
        )
        outcome["signal"] = result.get("signal", "AGUARDAR")
        outcome["reason"] = result.get("reason", "")
        outcome["status"] = "observed"
        if outcome["signal"] in ("CALL", "PUT"):
            logger.warning(
                "%s candidato=%s; não publicado: Yahoo Finance não é "
                "cotação executável da plataforma. %s",
                asset,
                outcome["signal"],
                outcome["reason"],
            )
        else:
            logger.info("%s: sem confirmação. %s", asset, outcome["reason"])
    except Exception as exc:
        outcome["reason"] = str(exc)
        logger.warning("%s: monitoramento indisponível: %s", asset, exc)
    return outcome


def run_cycle() -> Dict[str, int]:
    totals = {"assets": 0, "observed": 0, "errors": 0, "evaluated": 0}

    if HAS_OTCHARTS:
        from otcharts_feed import OTChartsFeed

        feed = OTChartsFeed()
        symbols = _get_otcharts_symbols(feed)
        if not symbols:
            logger.warning("Nenhum instrumento aberto disponível no catálogo %s.", OTCHARTS_VENUE)
        for symbol in symbols:
            if not RUNNING:
                break
            result = scan_otcharts_symbol(feed, symbol)
            totals["assets"] += 1
            totals["evaluated"] += int(result.get("evaluated", 0))
            if result["status"] == "observed":
                totals["observed"] += 1
            else:
                totals["errors"] += 1
    else:
        for asset in ATIVOS:
            if not RUNNING:
                break
            result = scan_yahoo_asset(asset)
            totals["assets"] += 1
            totals["evaluated"] += int(result.get("evaluated", 0))
            if result["status"] == "observed":
                totals["observed"] += 1
            else:
                totals["errors"] += 1

    logger.info("Ciclo concluído: %s", totals)
    return totals


def main():
    signal.signal(signal.SIGTERM, _stop_worker)
    signal.signal(signal.SIGINT, _stop_worker)
    logger.info(
        "TRADER AI PRO monitor iniciado; fonte=%s venue=%s intervalo=%ss modo=OBSERVAÇÃO",
        "OTCharts" if HAS_OTCHARTS else "Yahoo Finance",
        OTCHARTS_VENUE if HAS_OTCHARTS else "Forex",
        SCAN_INTERVAL_SECONDS,
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
