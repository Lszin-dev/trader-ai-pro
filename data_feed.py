
import yfinance as yf
import pandas as pd


def get_market_data(asset, minutes):

    if asset == "EURUSD":
        ticker = "EURUSD=X"

    elif asset == "EURUSD-OTC":
        raise ValueError(
            "EUR/USD-OTC não está disponível nesta fonte gratuita."
        )

    else:
        raise ValueError("Ativo não reconhecido.")

    if minutes not in [1, 5]:
        raise ValueError("Use timeframe de 1 ou 5 minutos.")

    interval = "1m" if minutes == 1 else "5m"

    data = yf.Ticker(ticker).history(
        period="1d",
        interval=interval,
        auto_adjust=False
    )

    if data.empty:
        raise ValueError("A fonte não retornou candles.")

    data.columns = [
        str(column).lower() for column in data.columns
    ]

    required = ["open", "high", "low", "close"]

    if not all(column in data.columns for column in required):
        raise ValueError("Formato de dados inesperado.")

    data = data[required].copy()
    data = data.dropna()
    data = data.sort_index()

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
            f"Dados desatualizados: último candle há "
            f"{int(max(atraso, 0) / 60)} minutos. "
            "Não é seguro gerar sinais."
        )

    ultimos = data.tail(5)

    sem_movimento = (
        (ultimos["open"] == ultimos["close"]).all()
        and (ultimos["high"] == ultimos["low"]).all()
        and (ultimos["close"].nunique() == 1)
    )

    if sem_movimento:
        raise ValueError(
            "Candles sem movimentação. "
            "Aguardando dados com variação de preço."
        )

    return data
