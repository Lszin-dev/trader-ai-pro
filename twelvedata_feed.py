"""Twelve Data read-only Forex feed with conservative validation.

A chave fica somente em ``TWELVE_DATA_API_KEY`` e é enviada no cabeçalho HTTP.
Candles são usados para análise técnica. O endpoint de exchange rate pode
revalidar um candidato no provedor, mas não substitui a cotação da corretora.
"""
from __future__ import annotations

import math
import os
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import requests
from reliability import validate_ohlc
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE_URL = "https://api.twelvedata.com"


class TwelveDataError(RuntimeError):
    """Raised when Twelve Data returns unavailable or invalid market data."""


class TwelveDataFeed:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = BASE_URL,
        timeout: int = 15,
        session: Optional[requests.Session] = None,
    ):
        self.api_key = api_key or os.getenv("TWELVE_DATA_API_KEY")
        if not self.api_key:
            raise TwelveDataError("Configure TWELVE_DATA_API_KEY no ambiente.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        if session is None:
            self.session = requests.Session()
            retry = Retry(
                total=2,
                connect=2,
                read=0,
                status=0,
                backoff_factor=0.4,
                status_forcelist=(500, 502, 503, 504),
                allowed_methods=frozenset({"GET"}),
                raise_on_status=False,
            )
            adapter = HTTPAdapter(max_retries=retry)
            self.session.mount("https://", adapter)
        else:
            self.session = session

        self.session.headers.update({
            "Authorization": f"apikey {self.api_key}",
            "Accept": "application/json",
            "User-Agent": "TRADER-AI-PRO/2.0",
        })

    def _get(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response = self.session.get(
                f"{self.base_url}/{endpoint.lstrip('/')}",
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise TwelveDataError(
                f"Falha de conexão com Twelve Data: {type(exc).__name__}."
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise TwelveDataError("Resposta JSON inválida da Twelve Data.") from exc

        if response.status_code >= 400:
            message = payload.get("message", "requisição recusada") if isinstance(payload, dict) else "requisição recusada"
            code = payload.get("code", response.status_code) if isinstance(payload, dict) else response.status_code
            raise TwelveDataError(
                f"Twelve Data HTTP {response.status_code} (código {code}): {str(message).replace(self.api_key, '[oculto]')}"
            )

        if not isinstance(payload, dict):
            raise TwelveDataError("Formato inesperado retornado pela Twelve Data.")

        if payload.get("status") == "error":
            message = str(payload.get("message") or "erro informado pelo provedor")
            code = payload.get("code", "desconhecido")
            raise TwelveDataError(f"Twelve Data código {code}: {message.replace(self.api_key, '[oculto]')}")

        return payload

    def get_candles(
        self,
        symbol: str = "EUR/USD",
        interval: str = "1min",
        outputsize: int = 250,
        now: Optional[Any] = None,
        max_age_seconds: int = 150,
    ) -> pd.DataFrame:
        """Return only closed, recent OHLC candles indexed in UTC."""
        if interval != "1min":
            raise ValueError("Este monitor utiliza candles de 1 minuto.")
        if not symbol or not isinstance(symbol, str) or "/" not in symbol:
            raise ValueError("Símbolo Forex inválido. Use o formato EUR/USD.")
        if not 30 <= int(outputsize) <= 5000:
            raise ValueError("outputsize deve estar entre 30 e 5000.")
        if max_age_seconds < 60:
            raise ValueError("max_age_seconds deve ser de pelo menos 60 segundos.")

        payload = self._get("time_series", {
            "symbol": symbol,
            "interval": interval,
            "outputsize": int(outputsize),
            "timezone": "UTC",
            "format": "JSON",
        })

        values = payload.get("values")
        if not isinstance(values, list) or len(values) < 30:
            raise TwelveDataError(f"{symbol}: histórico insuficiente ou mercado sem dados.")

        frame = pd.DataFrame(values)
        required = ["datetime", "open", "high", "low", "close"]
        if any(column not in frame.columns for column in required):
            raise TwelveDataError("Resposta de candles sem campos OHLC ou datetime.")

        for column in ["open", "high", "low", "close"]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        timestamps = pd.to_datetime(frame["datetime"], utc=True, errors="coerce")
        frame.index = pd.DatetimeIndex(timestamps, name="time")
        frame = frame[["open", "high", "low", "close"]]
        frame = frame.sort_index()
        try:
            validate_ohlc(frame)
        except ValueError as exc:
            raise TwelveDataError(str(exc)) from exc

        if frame.empty or len(frame) < 30:
            raise TwelveDataError(f"{symbol}: candles válidos insuficientes.")
        if not np.isfinite(frame.to_numpy(dtype=float)).all() or (frame <= 0).any().any():
            raise TwelveDataError(f"{symbol}: candle contém preço inválido.")

        reference_time = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
        if reference_time.tzinfo is None:
            raise ValueError("now precisa conter fuso horário.")
        reference_time = reference_time.tz_convert("UTC")

        candle_close_times = frame.index + pd.Timedelta(minutes=1)
        frame = frame.loc[candle_close_times <= reference_time]
        if len(frame) < 30:
            raise TwelveDataError(f"{symbol}: menos de 30 candles de 1 minuto fechados.")

        latest_close = frame.index[-1] + pd.Timedelta(minutes=1)
        age = (reference_time - latest_close).total_seconds()
        if age < 0 or age > max_age_seconds:
            raise TwelveDataError(
                f"{symbol}: último candle fechado desatualizado ({age:.1f}s; limite {max_age_seconds}s)."
            )

        last_five = frame.tail(5)
        if last_five["close"].nunique() == 1 and (last_five["high"] == last_five["low"]).all():
            raise TwelveDataError(f"{symbol}: feed sem variação de preço nos últimos candles.")

        return frame.astype(float)

    def get_exchange_rate(
        self,
        symbol: str = "EUR/USD",
        now: Optional[Any] = None,
        max_age_seconds: int = 15,
    ) -> Dict[str, Any]:
        """Read a timestamped real-time Forex rate for provider-side revalidation."""
        if not symbol or not isinstance(symbol, str) or "/" not in symbol:
            raise ValueError("Símbolo Forex inválido. Use o formato EUR/USD.")
        if max_age_seconds < 1:
            raise ValueError("max_age_seconds deve ser positivo.")

        payload = self._get("exchange_rate", {
            "symbol": symbol,
            "timezone": "UTC",
            "format": "JSON",
        })
        try:
            price = float(payload["rate"])
            timestamp = int(payload["timestamp"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TwelveDataError("Resposta de exchange rate sem preço/timestamp válidos.") from exc

        if not math.isfinite(price) or price <= 0:
            raise TwelveDataError("Exchange rate retornou preço inválido.")

        quote_time = pd.to_datetime(timestamp, unit="s", utc=True)
        reference_time = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
        if reference_time.tzinfo is None:
            raise ValueError("now precisa conter fuso horário.")
        reference_time = reference_time.tz_convert("UTC")
        age = (reference_time - quote_time).total_seconds()
        if age < -2:
            raise TwelveDataError("Exchange rate retornou timestamp no futuro.")
        if age > max_age_seconds:
            raise TwelveDataError(
                f"Exchange rate desatualizado ({age:.1f}s; limite {max_age_seconds}s)."
            )

        return {
            "symbol": str(payload.get("symbol") or symbol),
            "price": price,
            "timestamp": quote_time.isoformat(),
            "age_seconds": round(age, 3),
        }

    def get_usage(self) -> Dict[str, Any]:
        """Return provider usage metadata; daily fields exist only on Basic."""
        payload = self._get("api_usage", {})
        if "current_usage" not in payload or "plan_limit" not in payload:
            raise TwelveDataError("Resposta de consumo/cota inválida da Twelve Data.")
        return {
            "timestamp": payload.get("timestamp"),
            "current_usage": payload.get("current_usage"),
            "plan_limit": payload.get("plan_limit"),
            "daily_usage": payload.get("daily_usage"),
            "plan_daily_limit": payload.get("plan_daily_limit"),
            "plan_category": payload.get("plan_category"),
        }
