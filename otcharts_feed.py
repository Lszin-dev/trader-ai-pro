"""Read-only OTCharts adapter for broker-aligned market data.

API keys must be supplied through OTCHARTS_API_KEY. Never put a key in source
control. This adapter only reads symbols/candles; it cannot place trades.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import pandas as pd
import requests


BASE_URL = "https://otcharts.com"
SUPPORTED_VENUES = {"iq", "otc", "quotex", "binodex", "forex"}


class OTChartsError(RuntimeError):
    """Raised when the provider refuses or returns unusable market data."""


class OTChartsFeed:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = BASE_URL,
        timeout: int = 15,
        session: Optional[requests.Session] = None,
    ):
        self.api_key = api_key or os.getenv("OTCHARTS_API_KEY")
        if not self.api_key:
            raise OTChartsError("Configure OTCHARTS_API_KEY no ambiente.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": "TRADER-AI-PRO/1.0",
        })

    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response = self.session.get(
                f"{self.base_url}{path}",
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise OTChartsError(f"Falha de conexão com OTCharts: {exc}") from exc

        if response.status_code >= 400:
            try:
                detail = response.json().get("error", response.text)
            except ValueError:
                detail = response.text
            raise OTChartsError(
                f"OTCharts HTTP {response.status_code}: {detail}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise OTChartsError("Resposta JSON inválida do OTCharts.") from exc

        if not isinstance(payload, dict):
            raise OTChartsError("Formato inesperado retornado pelo OTCharts.")
        return payload

    def list_symbols(self, venue: str = "iq") -> List[Dict[str, Any]]:
        venue = venue.lower().strip()
        if venue not in SUPPORTED_VENUES:
            raise ValueError(f"Venue não suportado: {venue}")

        payload = self._get("/v1/symbols", {"venue": venue})
        symbols = payload.get("symbols")
        if not isinstance(symbols, list):
            raise OTChartsError("Catálogo de símbolos ausente ou inválido.")

        normalized = []
        for item in symbols:
            if not isinstance(item, dict) or not item.get("symbol"):
                continue
            normalized.append({
                "symbol": str(item["symbol"]),
                "name": str(item.get("name") or item["symbol"]),
                "open": item.get("open"),
                "payout": item.get("payout"),
                "is_otc": item.get("isOtc"),
            })
        return normalized

    def get_candles(
        self,
        venue: str,
        symbol: str,
        timeframe_seconds: int = 60,
        limit: int = 300,
        now: Optional[Any] = None,
        max_age_seconds: Optional[int] = None,
    ) -> pd.DataFrame:
        venue = venue.lower().strip()
        if venue not in SUPPORTED_VENUES:
            raise ValueError(f"Venue não suportado: {venue}")
        if timeframe_seconds not in (60, 300):
            raise ValueError("Timeframe deve ser 60 (1m) ou 300 (5m).")
        if not symbol or not isinstance(symbol, str):
            raise ValueError("Símbolo inválido.")
        if not 30 <= int(limit) <= 5000:
            raise ValueError("limit deve estar entre 30 e 5000.")

        payload = self._get(
            "/v1/candles",
            {
                "venue": venue,
                "symbol": symbol,
                "tf": timeframe_seconds,
                "limit": int(limit),
            },
        )

        if payload.get("open") is False:
            raise OTChartsError(f"{symbol} está fechado para negociação.")

        gaps = payload.get("gaps") or {}
        if int(gaps.get("missingBars") or 0) > 0:
            raise OTChartsError(
                f"{symbol}: feed contém {gaps['missingBars']} candles ausentes."
            )

        candles = payload.get("candles")
        if not isinstance(candles, list) or len(candles) < 30:
            raise OTChartsError(f"{symbol}: histórico insuficiente.")

        frame = pd.DataFrame(candles)
        required = ["time", "open", "high", "low", "close"]
        if any(column not in frame.columns for column in required):
            raise OTChartsError("Candles sem campos OHLC ou timestamp.")

        for column in ["open", "high", "low", "close", "time"]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(subset=required).copy()
        if frame.empty:
            raise OTChartsError(f"{symbol}: candles inválidos.")

        # OTCharts documents Pocket Option's clock as UTC+2; other books use UTC.
        offset = pd.Timedelta(hours=2) if venue == "otc" else pd.Timedelta(0)
        timestamps = pd.to_datetime(frame["time"], unit="s", utc=True) - offset
        frame.index = pd.DatetimeIndex(timestamps, name="time")
        frame = frame[["open", "high", "low", "close"]].sort_index()
        frame = frame[~frame.index.duplicated(keep="last")]

        reference_time = (
            pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
        )
        if reference_time.tzinfo is None:
            raise ValueError("now precisa conter fuso horário.")
        reference_time = reference_time.tz_convert("UTC")

        # A candle is usable only after its full interval has elapsed.
        candle_close_times = frame.index + pd.Timedelta(seconds=timeframe_seconds)
        frame = frame.loc[candle_close_times <= reference_time]
        if len(frame) < 30:
            raise OTChartsError(f"{symbol}: menos de 30 candles fechados.")

        if max_age_seconds is None:
            max_age_seconds = 90 if timeframe_seconds == 60 else 360
        latest_close = frame.index[-1] + pd.Timedelta(seconds=timeframe_seconds)
        age = (reference_time - latest_close).total_seconds()
        if age < 0 or age > max_age_seconds:
            raise OTChartsError(
                f"{symbol}: último candle fechado está desatualizado ({age:.1f}s)."
            )

        return frame.astype(float)
