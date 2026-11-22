
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

    # Padroniza os horários em UTC
    indice = pd.to_datetime(data.index, utc=True)
    data.index = indice

    agora = pd.Timestamp.now(tz="UTC")

    # Remove candles que ainda não tiveram tempo de fechar
    fechamento_estimado = (
        data.index + pd.Timedelta(minutes=minutes)
    )

    data = data.loc[fechamento_estimado <= agora]

    if data.empty:
        raise ValueError(
            f"{asset}: ainda não existem candles fechados disponíveis."
        )

    # Verifica se os dados são recentes
    ultimo_candle = data.index[-1]
    horario_fechamento = (
        ultimo_candle + pd.Timedelta(minutes=minutes)
    )

    atraso = (agora - horario_fechamento).total_seconds()

    limite = 900 if minutes == 1 else 1800

    if atraso < 0 or atraso > limite:
        raise ValueError(
            f"{asset}: dados desatualizados. "
            f"Último candle fechado há "
            f"{int(max(atraso, 0) / 60)} minutos."
        )

    # Verifica se os últimos candles apresentam movimentação
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
