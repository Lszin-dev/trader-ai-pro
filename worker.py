"""TRADER AI PRO background monitor.

This worker is deliberately observation-only. It scans the currently supported
Yahoo Finance symbols and evaluates existing pending records. It does not
publish new entries because the current feed has no independently timestamped,
executable quote suitable for anchoring an entry price.
"""
from __future__ import annotations

import logging
import os
import signal
import time
from typing import Dict

from data_feed import ATIVOS, get_market_data
from historico import avaliar_sinais_pendentes
from indicators import calculate_indicators
from strategy import analyze_market


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
SCAN_INTERVAL_SECONDS = max(30, int(os.getenv("SCAN_INTERVAL_SECONDS", "60")))
RUNNING = True

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


def scan_asset(asset: str) -> Dict[str, object]:
    """Scan one configured asset and evaluate its pending historical records."""
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

        # Keep evaluation independent from the Streamlit button.
        outcome["evaluated"] = avaliar_sinais_pendentes(asset, data_1m)

        analyzed_1m = calculate_indicators(data_1m)
        analyzed_5m = calculate_indicators(data_5m)
        result = analyze_market(analyzed_1m, analyzed_5m)

        outcome["signal"] = result.get("signal", "AGUARDAR")
        outcome["reason"] = result.get("reason", "")
        outcome["status"] = "observed"

        # Do not register a new signal from a candle close with a future entry
        # time. A provider quote with its own timestamp is required first.
        if outcome["signal"] in ("CALL", "PUT"):
            logger.warning(
                "%s candidate=%s; not published: feed has no validated "
                "executable quote. reason=%s",
                asset,
                outcome["signal"],
                outcome["reason"],
            )
        else:
            logger.info("%s: no confirmed setup. %s", asset, outcome["reason"])

    except Exception as exc:
        outcome["reason"] = str(exc)
        logger.warning("%s: scan unavailable: %s", asset, exc)

    return outcome


def run_cycle() -> Dict[str, int]:
    """Run one full scan over configured symbols."""
    totals = {"assets": 0, "observed": 0, "errors": 0, "evaluated": 0}
    for asset in ATIVOS:
        if not RUNNING:
            break
        result = scan_asset(asset)
        totals["assets"] += 1
        totals["evaluated"] += int(result.get("evaluated", 0))
        if result["status"] == "observed":
            totals["observed"] += 1
        else:
            totals["errors"] += 1
    logger.info("Cycle completed: %s", totals)
    return totals


def main():
    signal.signal(signal.SIGTERM, _stop_worker)
    signal.signal(signal.SIGINT, _stop_worker)
    logger.info(
        "TRADER AI PRO monitor started; assets=%s interval=%ss mode=OBSERVATION_ONLY",
        len(ATIVOS),
        SCAN_INTERVAL_SECONDS,
    )

    while RUNNING:
        started = time.monotonic()
        run_cycle()
        elapsed = time.monotonic() - started
        wait_seconds = max(1, SCAN_INTERVAL_SECONDS - int(elapsed))
        for _ in range(wait_seconds):
            if not RUNNING:
                break
            time.sleep(1)

    logger.info("TRADER AI PRO monitor stopped cleanly.")


if __name__ == "__main__":
    main()
