
import yfinance as yf
import pandas as pd


ATIVOS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCHF": "USDCHF=X",
    "EURGBP": "EURGBP=X",
}


def get_market_data(asset, minutes):

    if asset not in ATIVOS:
        raise ValueError("Ativo não reconhecido ou indisponível.")

    if minutes not in [1, 5]:
        raise ValueError("Use timeframe de 1 ou 5 minutos.")

    ticker = ATIVOS[asset]
    interval = "1m" if minutes == 1 else "5m"

    data = yf.Ticker(ticker).history(
        period="1d",
        interval=interval,
        auto_adjust=False
    )

    if data.empty:
        raise ValueError(f"Sem candles disponíveis para {asset}.")

    data.columns = [str(c).lower() for c in data.columns]

    required = ["open", "high", "low", "close"]

    if not all(c in data.columns for c in required):
        raise ValueError("Formato de dados inesperado.")

    data = data[required].copy()
    data = data.dropna().sort_index()

    if data.empty:
        raise ValueError("Nenhum candle válido.")

    ultimo_candle = pd.Timestamp(data.index[-1])

    if ultimo_candle.tzinfo is None:
        ultimo_candle = ultimo_candle.tz_localize("UTC")
    else:
        ultimo_candle = ultimo_candle.tz_convert("UTC")

    agora = pd.Timestamp.now(tz="UTC")
    atraso = (agora - ultimo_candle).total_seconds()

    limite = 900 if minutes == 1 else 1800

    if atraso < 0 or atraso > limite:
        raise ValueError(
            f"{asset}: dados desatualizados. "
            f"Último candle há {int(max(atraso, 0) / 60)} minutos."
        )

    ultimos = data.tail(5)

    sem_movimento = (
        (ultimos["open"] == ultimos["close"]).all()
        and (ultimos["high"] == ultimos["low"]).all()
        and (ultimos["close"].nunique() == 1)
    )

    if sem_movimento:
        raise ValueError(
            f"{asset}: candles sem movimentação. "
            "Não é seguro gerar sinais."
        )

    return data
