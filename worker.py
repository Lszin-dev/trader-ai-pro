"""TRADER AI PRO background monitor.

Worker de observação contínua. Ele analisa candles, aplica filtros técnicos,
acompanha confirmações consecutivas e, no modo Twelve Data, pode revalidar o
preço no próprio provedor. Isso NÃO substitui a cotação executável da corretora.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import signal
import time
from typing import Dict, List, Optional

import pandas as pd

from data_feed import ATIVOS, get_market_data
from entry_validation import validate_entry_quote
from indicators import calculate_indicators
from market_guard import forex_market_status
from monitor_state import salvar_estado_monitoramento
from strategy import analyze_market
from reliability import advance_confirmation, closed_five_minute, validate_ohlc
from quota_budget import DailyBudget


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
SCAN_INTERVAL_SECONDS = max(120 if ACTIVE_PROVIDER == "twelvedata" else 60, int(os.getenv("SCAN_INTERVAL_SECONDS", DEFAULT_INTERVAL)))
MIN_CANDIDATE_CONFIRMATIONS = max(2, int(os.getenv("MIN_CANDIDATE_CONFIRMATIONS", "2")))
REVALIDATION_COOLDOWN_SECONDS = max(300, int(os.getenv("REVALIDATION_COOLDOWN_SECONDS", "600")))
USAGE_CHECK_INTERVAL_SECONDS = max(900, int(os.getenv("USAGE_CHECK_INTERVAL_SECONDS", "900")))
_DAILY_BUDGET = DailyBudget(min(750, int(os.getenv("DAILY_CREDIT_BUDGET", "750"))))
OTCHARTS_VENUE = os.getenv("OTCHARTS_VENUE", "iq").strip().lower()
OTCHARTS_MAX_SYMBOLS = max(1, int(os.getenv("OTCHARTS_MAX_SYMBOLS", "5")))
OTCHARTS_SYMBOLS = [item.strip() for item in os.getenv("OTCHARTS_SYMBOLS", "").split(",") if item.strip()]
TWELVE_DATA_SYMBOLS = [
    item.strip()
    for item in os.getenv("TWELVE_DATA_SYMBOLS", "EUR/USD").split(",")
    if item.strip()
][:1]
CATALOG_REFRESH_SECONDS = 900

RUNNING = True
_SYMBOL_CACHE: List[str] = []
_SYMBOL_CACHE_AT = 0.0
_CANDIDATE_STATE: Dict[str, Dict[str, object]] = {}
_REVALIDATION_CACHE: Dict[str, Dict[str, object]] = {}
_USAGE_SNAPSHOT: Dict[str, object] = {}
_USAGE_CHECKED_AT = 0.0
_USAGE_DAY = None

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
    return closed_five_minute(data_1m)


def _get_otcharts_symbols(feed) -> List[str]:
    global _SYMBOL_CACHE, _SYMBOL_CACHE_AT
    if OTCHARTS_SYMBOLS:
        return OTCHARTS_SYMBOLS[:OTCHARTS_MAX_SYMBOLS]
    now = time.monotonic()
    if not _SYMBOL_CACHE or now - _SYMBOL_CACHE_AT >= CATALOG_REFRESH_SECONDS:
        catalogue = feed.list_symbols(OTCHARTS_VENUE)
        _SYMBOL_CACHE = [item["symbol"] for item in catalogue if item.get("open") is not False][:OTCHARTS_MAX_SYMBOLS]
        _SYMBOL_CACHE_AT = now
        logger.info("Catálogo %s atualizado: %s instrumento(s).", OTCHARTS_VENUE, len(_SYMBOL_CACHE))
    return list(_SYMBOL_CACHE)


def _recent_prices(data_1m: pd.DataFrame, limit: int = 60) -> List[Dict[str, object]]:
    points = []
    for stamp, value in data_1m["close"].tail(limit).items():
        points.append({"time": pd.Timestamp(stamp).isoformat(), "close": float(value)})
    return points


def _persist_state(provider: str, result: Dict[str, object], data_1m=None) -> None:
    try:
        latest_data = None
        details = {"modo": "OBSERVACAO"}
        details.update(result.get("details") or {})
        if data_1m is not None and not data_1m.empty:
            latest_data = data_1m.index[-1] + pd.Timedelta(minutes=1)
            now = pd.Timestamp.now(tz="UTC")
            details.update({
                "last_close": float(data_1m["close"].iloc[-1]),
                "feed_lag_seconds": round(max(0.0, (now - latest_data).total_seconds()), 1),
                "recent_prices": _recent_prices(data_1m),
            })
        salvar_estado_monitoramento(
            provider=provider,
            ativo=str(result.get("asset", "UNKNOWN")),
            status=str(result.get("status", "error")),
            sinal_candidato=str(result.get("signal", "AGUARDAR")),
            motivo=str(result.get("reason", "")),
            ultimo_dado=latest_data,
            detalhes=details,
        )
    except Exception as exc:
        logger.error("Não foi possível atualizar o estado compartilhado do monitor: %s", exc)


def _analyze_frames(asset_key: str, data_1m: pd.DataFrame) -> Dict[str, object]:
    data_5m = _resample_5m(data_1m)
    if len(data_5m) < 30:
        raise ValueError("Histórico 5M insuficiente após agregar candles 1M fechados.")

    analysis = analyze_market(calculate_indicators(data_1m), calculate_indicators(data_5m))
    signal_value = str(analysis.get("signal", "AGUARDAR"))
    reason = str(analysis.get("reason", ""))
    details = {
        "technical_score": float(analysis.get("score", 0.0)),
        "quality": analysis.get("quality", "AGUARDAR"),
        "metrics": analysis.get("metrics", {}),
        "checks": analysis.get("checks", {}),
    }
    if signal_value in ("CALL", "PUT"):
        logger.warning("%s candidato=%s; ainda não é entrada executável. %s", asset_key, signal_value, reason)
    else:
        logger.info("%s: sem confirmação. %s", asset_key, reason)
    return {"asset": asset_key, "status": "observed", "signal": signal_value, "reason": reason, "details": details}


def _update_candidate_streak(asset: str, signal_value: str, candle_time=None):
    state, advanced = advance_confirmation(
        _CANDIDATE_STATE.get(asset), signal_value, candle_time,
        max_gap_seconds=SCAN_INTERVAL_SECONDS + 60,
    )
    if state is None:
        _CANDIDATE_STATE.pop(asset, None)
        return 0, False
    _CANDIDATE_STATE[asset] = state
    return state["count"], advanced


def _revalidate_twelvedata(feed, symbol: str, asset_key: str) -> Dict[str, object]:
    now_mono = time.monotonic()
    cached = _REVALIDATION_CACHE.get(asset_key)
    if cached and now_mono - float(cached["checked_mono"]) < REVALIDATION_COOLDOWN_SECONDS:
        return {
            "valid": False,
            "provider": "twelvedata",
            "state": "cooldown",
            "reason": "Revalidação recente já utilizada; aguardando novo ciclo permitido para não reutilizar cotação antiga.",
            "checked_at": cached["payload"].get("checked_at"),
            "cached": True,
            "broker_confirmed": False,
        }

    checked_at = datetime.now(timezone.utc).isoformat()
    if not _DAILY_BUDGET.reserve():
        return {"valid": False, "state": "quota_guard", "reason": "Orçamento diário de leituras atingido.", "broker_confirmed": False}
    try:
        quote = feed.get_exchange_rate(symbol=symbol, max_age_seconds=15)
        validation = validate_entry_quote(
            quote["price"], quote["timestamp"], max_age_seconds=15
        )
        payload = {
            "valid": bool(validation["valid"]),
            "provider": "twelvedata",
            "state": "current",
            "price": validation.get("price"),
            "quote_timestamp": validation.get("entry_timestamp"),
            "quote_age_seconds": quote.get("age_seconds"),
            "reason": validation.get("reason"),
            "checked_at": checked_at,
            "cached": False,
            "broker_confirmed": False,
        }
    except Exception as exc:
        payload = {
            "valid": False,
            "provider": "twelvedata",
            "state": "failed",
            "reason": f"Revalidação no provedor falhou: {exc}",
            "checked_at": checked_at,
            "cached": False,
            "broker_confirmed": False,
        }

    _REVALIDATION_CACHE[asset_key] = {"checked_mono": now_mono, "payload": payload}
    return payload


def _refresh_usage(feed) -> Dict[str, object]:
    global _USAGE_SNAPSHOT, _USAGE_CHECKED_AT, _USAGE_DAY
    now_mono = time.monotonic()
    day = datetime.now(timezone.utc).date()
    if day != _USAGE_DAY:
        _USAGE_SNAPSHOT = {}
        _USAGE_CHECKED_AT = 0.0
        _USAGE_DAY = day
    if _USAGE_CHECKED_AT and now_mono - _USAGE_CHECKED_AT < USAGE_CHECK_INTERVAL_SECONDS:
        return dict(_USAGE_SNAPSHOT)
    _USAGE_CHECKED_AT = now_mono
    if not _DAILY_BUDGET.reserve():
        return dict(_USAGE_SNAPSHOT)
    try:
        _USAGE_SNAPSHOT = feed.get_usage()
        _DAILY_BUDGET.sync(_USAGE_SNAPSHOT)
    except Exception as exc:
        logger.warning("Não foi possível consultar cota Twelve Data: %s", exc)
    return dict(_USAGE_SNAPSHOT)


def _quota_near_limit(usage: Dict[str, object]) -> bool:
    try:
        daily = usage.get("daily_usage")
        limit = usage.get("plan_daily_limit")
        if daily is None or limit in (None, 0):
            return False
        return float(daily) / float(limit) >= 0.97
    except (TypeError, ValueError, ZeroDivisionError):
        return False


def scan_otcharts_symbol(feed, symbol: str) -> Dict[str, object]:
    asset_key = f"{OTCHARTS_VENUE.upper()}:{symbol}"
    try:
        data_1m = feed.get_candles(OTCHARTS_VENUE, symbol, timeframe_seconds=60, limit=1000, max_age_seconds=90)
        outcome = _analyze_frames(asset_key, data_1m)
        outcome["evaluated"] = 0  # observation-only: preserve legacy history
        outcome["details"]["candidate_confirmations"] = _update_candidate_streak(asset_key, outcome["signal"], data_1m.index[-1])[0]
        outcome["details"]["required_confirmations"] = MIN_CANDIDATE_CONFIRMATIONS
        _persist_state("otcharts", outcome, data_1m)
        return outcome
    except Exception as exc:
        logger.warning("%s: monitoramento indisponível: %s", asset_key, exc)
        outcome = {"asset": asset_key, "status": "error", "signal": "AGUARDAR", "evaluated": 0, "reason": str(exc), "details": {}}
        _update_candidate_streak(asset_key, "AGUARDAR")
        _persist_state("otcharts", outcome)
        return outcome


def scan_twelvedata_symbol(feed, symbol: str) -> Dict[str, object]:
    asset_key = f"FOREX:{symbol.replace('/', '')}"
    try:
        if not _DAILY_BUDGET.reserve():
            _update_candidate_streak(asset_key, "AGUARDAR")
            outcome = {"asset": asset_key, "status": "observed", "signal": "AGUARDAR", "reason": "Orçamento diário de leituras atingido.", "details": {"quota_guard": True}}
            _persist_state("twelvedata", outcome)
            return outcome
        data_1m = feed.get_candles(symbol=symbol, interval="1min", outputsize=250, max_age_seconds=150)
        outcome = _analyze_frames(asset_key, data_1m)
        streak, advanced = _update_candidate_streak(asset_key, outcome["signal"], data_1m.index[-1])
        outcome["details"]["candidate_confirmations"] = streak
        outcome["details"]["required_confirmations"] = MIN_CANDIDATE_CONFIRMATIONS

        if outcome["signal"] in ("CALL", "PUT"):
            if streak == MIN_CANDIDATE_CONFIRMATIONS and advanced:
                revalidation = _revalidate_twelvedata(feed, symbol, asset_key)
                outcome["details"]["provider_revalidation"] = revalidation
                if revalidation.get("valid"):
                    outcome["reason"] += " Revalidado neste ciclo no provedor; a cotação da corretora ainda precisa coincidir no instante da entrada."
                else:
                    outcome["reason"] += " Candidato bloqueado porque não houve uma revalidação atual válida."
            elif streak >= MIN_CANDIDATE_CONFIRMATIONS:
                outcome["details"]["provider_revalidation"] = {
                    "valid": False,
                    "provider": "twelvedata",
                    "state": "persistent_candidate",
                    "broker_confirmed": False,
                    "reason": "O mesmo candidato continuou ativo; nenhuma cotação antiga é reutilizada como nova entrada.",
                }
                outcome["reason"] += " Candidato persistente; aguardando o setup resetar antes de considerar um novo gatilho."
            else:
                outcome["reason"] += f" Aguardando confirmação consecutiva {streak}/{MIN_CANDIDATE_CONFIRMATIONS}."

        _persist_state("twelvedata", outcome, data_1m)
        return outcome
    except Exception as exc:
        logger.warning("%s: monitoramento indisponível: %s", asset_key, exc)
        outcome = {"asset": asset_key, "status": "error", "signal": "AGUARDAR", "reason": str(exc), "details": {}}
        _update_candidate_streak(asset_key, "AGUARDAR")
        _persist_state("twelvedata", outcome)
        return outcome


def scan_yahoo_asset(asset: str) -> Dict[str, object]:
    try:
        data_1m = get_market_data(asset, 1)
        data_5m = get_market_data(asset, 5)
        validate_ohlc(data_1m)
        validate_ohlc(data_5m)
        evaluated = 0  # observation-only: preserve legacy history
        analysis = analyze_market(calculate_indicators(data_1m), calculate_indicators(data_5m))
        signal_value = str(analysis.get("signal", "AGUARDAR"))
        details = {
            "technical_score": float(analysis.get("score", 0.0)),
            "quality": analysis.get("quality", "AGUARDAR"),
            "metrics": analysis.get("metrics", {}),
            "checks": analysis.get("checks", {}),
            "candidate_confirmations": _update_candidate_streak(asset, signal_value, data_1m.index[-1])[0],
            "required_confirmations": MIN_CANDIDATE_CONFIRMATIONS,
        }
        outcome = {"asset": asset, "status": "observed", "signal": signal_value, "evaluated": evaluated, "reason": analysis.get("reason", ""), "details": details}
        _persist_state("yahoo", outcome, data_1m)
        return outcome
    except Exception as exc:
        logger.warning("%s: monitoramento indisponível: %s", asset, exc)
        outcome = {"asset": asset, "status": "error", "signal": "AGUARDAR", "evaluated": 0, "reason": str(exc), "details": {}}
        _update_candidate_streak(asset, "AGUARDAR")
        _persist_state("yahoo", outcome)
        return outcome


def _closed_market_cycle(totals: Dict[str, int], market: Dict[str, object]) -> None:
    for symbol in TWELVE_DATA_SYMBOLS:
        asset_key = f"FOREX:{symbol.replace('/', '')}"
        outcome = {
            "asset": asset_key,
            "status": "observed",
            "signal": "AGUARDAR",
            "reason": market["reason"],
            "details": {"market_open": False, "market": market},
        }
        _update_candidate_streak(asset_key, "AGUARDAR")
        _persist_state("twelvedata", outcome)
        totals["assets"] += 1
        totals["observed"] += 1


def run_cycle() -> Dict[str, int]:
    started = time.monotonic()
    totals = {"assets": 0, "observed": 0, "errors": 0, "evaluated": 0}
    worker_details: Dict[str, object] = {}
    _persist_state(ACTIVE_PROVIDER, {"asset": "_WORKER", "status": "running", "signal": "AGUARDAR", "reason": "Ciclo de monitoramento iniciado.", "details": {}})

    try:
        if ACTIVE_PROVIDER == "otcharts":
            from otcharts_feed import OTChartsFeed
            feed = OTChartsFeed()
            for symbol in _get_otcharts_symbols(feed):
                if not RUNNING:
                    break
                result = scan_otcharts_symbol(feed, symbol)
                totals["assets"] += 1
                totals["evaluated"] += int(result.get("evaluated", 0))
                totals["observed" if result["status"] == "observed" else "errors"] += 1

        elif ACTIVE_PROVIDER == "twelvedata":
            market = forex_market_status()
            worker_details["market"] = market
            if not market["open"]:
                _closed_market_cycle(totals, market)
            else:
                from twelvedata_feed import TwelveDataFeed
                feed = TwelveDataFeed()
                usage = _refresh_usage(feed)
                if usage:
                    worker_details["api_usage"] = usage
                if _quota_near_limit(usage):
                    reason = "Cota diária da Twelve Data próxima do limite; leituras pausadas para preservar o plano."
                    for symbol in TWELVE_DATA_SYMBOLS:
                        asset_key = f"FOREX:{symbol.replace('/', '')}"
                        _update_candidate_streak(asset_key, "AGUARDAR")
                        outcome = {"asset": asset_key, "status": "observed", "signal": "AGUARDAR", "reason": reason, "details": {"api_usage": usage, "quota_guard": True}}
                        _persist_state("twelvedata", outcome)
                        totals["assets"] += 1
                        totals["observed"] += 1
                else:
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

    except Exception as exc:
        duration = round(time.monotonic() - started, 2)
        worker_details.update({"cycle_duration_seconds": duration, "totals": totals, "credit_budget": _DAILY_BUDGET.snapshot() if ACTIVE_PROVIDER == "twelvedata" else {}})
        _persist_state(ACTIVE_PROVIDER, {"asset": "_WORKER", "status": "error", "signal": "AGUARDAR", "reason": f"Falha no ciclo: {exc}", "details": worker_details})
        raise

    duration = round(time.monotonic() - started, 2)
    worker_details.update({"cycle_duration_seconds": duration, "totals": totals})
    logger.info("Ciclo concluído: %s (%.2fs)", totals, duration)
    _persist_state(ACTIVE_PROVIDER, {"asset": "_WORKER", "status": "observed", "signal": "AGUARDAR", "reason": f"Ciclo concluído: {totals}", "details": worker_details})
    return totals


def main():
    signal.signal(signal.SIGTERM, _stop_worker)
    signal.signal(signal.SIGINT, _stop_worker)
    logger.info("TRADER AI PRO monitor iniciado; fonte=%s intervalo=%ss modo=OBSERVAÇÃO", ACTIVE_PROVIDER, SCAN_INTERVAL_SECONDS)
    if ACTIVE_PROVIDER == "twelvedata":
        logger.info(
            "Twelve Data: símbolos=%s; confirmação=%sx; revalidação do provedor com cooldown=%ss.",
            TWELVE_DATA_SYMBOLS, MIN_CANDIDATE_CONFIRMATIONS, REVALIDATION_COOLDOWN_SECONDS,
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
